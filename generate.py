
"""
The one place FitFindr talks to the model.

Handles caching, request pacing, retries, token tracking,
and readable model errors.
"""

import hashlib
import json
import os
import re
import sys
import time

import config


_call_times: list[float] = []
_session_calls = 0
_cache_hits = 0
_prompt_tokens = 0
_output_tokens = 0
_client = None
_budget_warned = False


class QuotaGuard(Exception):
    """Raised when a session exceeds its request budget."""


class ModelUnavailable(Exception):
    """Raised when the model cannot be reached."""


# ─── Cache ───────────────────────────────────────────────────────


def _cache_key(
    prompt: str,
    system: str | None,
    temperature: float,
) -> str:
    blob = json.dumps(
        [config.MODEL, system or "", prompt, temperature],
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _cache_read(key: str) -> str | None:
    path = config.CACHE_DIR / f"{key}.json"

    if not path.exists():
        return None

    try:
        return json.loads(
            path.read_text(encoding="utf-8")
        )["response"]
    except Exception:
        return None


def _cache_write(key: str, response: str) -> None:
    config.CACHE_DIR.mkdir(exist_ok=True)

    path = config.CACHE_DIR / f"{key}.json"
    path.write_text(
        json.dumps({"response": response}),
        encoding="utf-8",
    )


def clear_cache() -> int:
    """Delete cached responses and return the number removed."""

    if not config.CACHE_DIR.exists():
        return 0

    files = list(config.CACHE_DIR.glob("*.json"))

    for file in files:
        file.unlink()

    return len(files)


# ─── Pacing and guards ───────────────────────────────────────────


def _wait_for_slot() -> None:
    """Wait if the per-minute request limit has been reached."""

    now = time.monotonic()

    _call_times[:] = [
        t for t in _call_times if now - t < 60.0
    ]

    if len(_call_times) < config.REQUESTS_PER_MINUTE:
        return

    sleep_for = 60.0 - (now - _call_times[0]) + 0.1

    if sleep_for > 0:
        if sleep_for >= 1.0:
            print(
                f"  [rate limit] "
                f"{config.REQUESTS_PER_MINUTE} requests used this "
                f"minute. Waiting {sleep_for:.0f}s. This is normal.",
                file=sys.stderr,
                flush=True,
            )

        time.sleep(sleep_for)

        _call_times[:] = [
            t for t in _call_times
            if time.monotonic() - t < 60.0
        ]


def _check_budget() -> None:
    global _budget_warned

    if _session_calls < config.SESSION_REQUEST_BUDGET:
        return

    if not _budget_warned:
        _budget_warned = True

    raise QuotaGuard(
        f"This session has made {_session_calls} requests, which is the "
        f"budget set in config.py (SESSION_REQUEST_BUDGET).\n"
        f"That usually means a loop is running away rather than that you've "
        f"done {_session_calls} requests' worth of real work.\n"
        f"Stop the program and look for the loop. If you really do need more, "
        f"raise the number in config.py — but look first."
    )


def usage() -> str:
    """Return model call and token usage for this session."""

    tokens = ""

    if _prompt_tokens or _output_tokens:
        tokens = (
            f", {_prompt_tokens} prompt + "
            f"{_output_tokens} output tokens"
        )

    return (
        f"{_session_calls} model calls this session"
        f"{f', {_cache_hits} served from cache' if _cache_hits else ''}"
        f"{tokens}"
    )


def call_count() -> int:
    return _session_calls


def token_counts() -> dict:
    return {
        "prompt": _prompt_tokens,
        "output": _output_tokens,
        "total": _prompt_tokens + _output_tokens,
    }


def _record_tokens(response) -> None:
    """Record token counts without interrupting successful calls."""

    global _prompt_tokens, _output_tokens

    try:
        meta = getattr(response, "usage_metadata", None)

        if meta is None:
            return

        prompt = getattr(meta, "prompt_token_count", None)
        output = getattr(meta, "candidates_token_count", None)

        if isinstance(prompt, int):
            _prompt_tokens += prompt

        if isinstance(output, int):
            _output_tokens += output

    except Exception:
        pass


# ─── Model call helpers ──────────────────────────────────────────


def _explain(exc: Exception) -> str:
    """Convert provider errors into readable messages."""

    message = str(exc).lower()

    if (
        "api key" in message
        or "api_key" in message
        or "unauthenticated" in message
    ):
        return (
            "The model rejected your API key. "
            "Check GEMINI_API_KEY in your .env file, "
            "or create a fresh key at aistudio.google.com."
        )

    if "not found" in message or "404" in message:
        return (
            f"The model name '{config.MODEL}' did not resolve. "
            "If you changed AI201_MODEL in your .env, put it back. "
            "Otherwise post in the help channel."
        )

    if (
        "connection" in message
        or "timeout" in message
        or "network" in message
    ):
        return (
            "Couldn't reach the model. "
            "Check your internet connection and try again."
        )

    return f"Couldn't reach the model: {exc}"


def _retry_delay(exc: Exception, attempt: int) -> float:
    """Use provider retry hints or exponential backoff."""

    error_text = str(exc)

    match = (
        re.search(
            r"retry in (\d+(?:\.\d+)?)\s*s",
            error_text,
            re.IGNORECASE,
        )
        or re.search(
            r"""retryDelay['"]?\s*:\s*['"](\d+(?:\.\d+)?)s""",
            error_text,
        )
    )

    hinted = float(match.group(1)) + 1.0 if match else 0.0

    return min(65.0, max(2.0 ** attempt, hinted))


def _get_client():
    global _client

    if _client is None:
        from google import genai

        key = os.getenv("GEMINI_API_KEY", "").strip()

        if not key:
            raise RuntimeError(
                "No GEMINI_API_KEY found.\n"
                "Copy .env.example to .env and paste your key in, "
                "then try again. `python test.py` will confirm "
                "it's working."
            )

        _client = genai.Client(api_key=key)

    return _client


# ─── Main model call ─────────────────────────────────────────────


def generate(
    prompt: str,
    system: str | None = None,
    cache: bool = True,
    temperature: float | None = None,
) -> str:
    """
    Send a prompt to the model and return its response.

    Retries temporary 429 and 503 errors.
    Does not retry invalid API keys or other permanent errors.
    """

    global _session_calls, _cache_hits

    use_cache = cache and config.CACHE_ENABLED

    temperature = (
        config.TEMPERATURE
        if temperature is None
        else temperature
    )

    key = _cache_key(prompt, system, temperature)

    # Check cache
    if use_cache:
        hit = _cache_read(key)

        if hit is not None:
            _cache_hits += 1
            return hit

    _check_budget()

    last_error: Exception | None = None

    for attempt in range(config.MAX_RETRIES):
        _wait_for_slot()

        try:
            client = _get_client()

            _call_times.append(time.monotonic())
            _session_calls += 1

            call_config = {
                "temperature": temperature
            }

            if system:
                call_config["system_instruction"] = system

            kwargs = {
                "model": config.MODEL,
                "contents": prompt,
                "config": call_config,
            }

            response = client.models.generate_content(**kwargs)

            _record_tokens(response)

            response_text = (response.text or "").strip()

            if use_cache:
                _cache_write(key, response_text)

            return response_text

        except Exception as exc:
            last_error = exc
            message = str(exc).lower()

            # Existing 429 rate-limit detection
            rate_limited = (
                "429" in message
                or ("resource" in message and "exhaust" in message)
                or ("rate" in message and "limit" in message)
            )

            # Unit 4 Milestone 5 improvement:
            # Retry temporary Gemini 503 errors.
            temporary_unavailable = (
                "503" in message
                or "high demand" in message
            )

            if not (rate_limited or temporary_unavailable):
                raise ModelUnavailable(_explain(exc)) from exc

            # Stop cleanly when retries are exhausted.
            if attempt == config.MAX_RETRIES - 1:
                break

            backoff = _retry_delay(exc, attempt)

            error_type = (
                "rate limit"
                if rate_limited
                else "temporary unavailable"
            )

            print(
                f"  [{error_type}] Waiting {backoff:.0f}s "
                f"before retry "
                f"(attempt {attempt + 1} of "
                f"{config.MAX_RETRIES}).",
                file=sys.stderr,
                flush=True,
            )

            time.sleep(backoff)

    raise ModelUnavailable(
        f"The model is still unavailable after "
        f"{config.MAX_RETRIES} attempts. "
        f"Please try again later. Last error: {last_error}"
    )
