
"""
FitFindr planning loop — Unit 4.

The agent:
1. Parses the user's query.
2. Searches thrift listings through MCP.
3. Stops if no listing matches.
4. Selects the best result.
5. Suggests an outfit.
6. Creates a fit card.

Each step is recorded in a trace for debugging and evaluation.
"""

import re

import config
import trace

from mcp_client import call_tool
from tools import suggest_outfit, create_fit_card
from generate import ModelUnavailable


# ── session state ─────────────────────────────────────────────────────────────

def new_session(query: str, wardrobe: dict) -> dict:
    """Create a new session for one FitFindr interaction."""

    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
    }


# ── query parsing ─────────────────────────────────────────────────────────────

def parse_query(query: str) -> dict:
    """Extract description, size, and maximum price from the query."""

    description = query.strip()
    size = None
    max_price = None

    price_match = re.search(
        r"(?:under|below|max(?:imum)?|less than)\s*\$?\s*(\d+(?:\.\d+)?)",
        query,
        re.IGNORECASE,
    )

    if price_match:
        max_price = float(price_match.group(1))

        description = re.sub(
            r"(?:under|below|max(?:imum)?|less than)\s*\$?\s*\d+(?:\.\d+)?",
            "",
            description,
            flags=re.IGNORECASE,
        )

    size_match = re.search(
        r"\bsize\s+([A-Za-z0-9/]+)",
        query,
        re.IGNORECASE,
    )

    if size_match:
        size = size_match.group(1)

        description = re.sub(
            r"\bsize\s+[A-Za-z0-9/]+",
            "",
            description,
            flags=re.IGNORECASE,
        )

    description = re.sub(
        r"\b(?:looking for|find me|search for|i want|i need)\b",
        "",
        description,
        flags=re.IGNORECASE,
    )

    description = description.replace(",", " ")
    description = " ".join(description.split())

    return {
        "description": description,
        "size": size,
        "max_price": max_price,
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """Run the FitFindr agent and record its decisions."""

    trace.start_trace()

    session = new_session(query, wardrobe)
    iteration_count = 0

    # Step 1: Parse query
    iteration_count += 1
    trace.check_iterations(iteration_count)

    session["parsed"] = parse_query(session["query"])

    trace.step(
        "parse_query",
        inputs={"query": session["query"]},
        returned=session["parsed"],
    )

    description = session["parsed"]["description"]
    size = session["parsed"]["size"]
    max_price = session["parsed"]["max_price"]

    # Step 2: Search listings via MCP
    iteration_count += 1
    trace.check_iterations(iteration_count)

    search_inputs = {
        "description": description,
        "size": size,
        "max_price": max_price,
    }

    session["search_results"] = call_tool(
        "search_listings",
        search_inputs,
    )

    trace.step(
        "search_listings (via MCP)",
        inputs=search_inputs,
        returned=session["search_results"],
    )

    # Branch: stop when no results are found
    if not session["search_results"]:
        session["error"] = (
            "I couldn't find a matching item. Try increasing your budget, "
            "changing the size, or using a broader item description."
        )

        trace.step(
            "empty_search_branch",
            inputs={"results_count": 0},
            returned=session["error"],
            note="No matching listings; stopping before outfit and fit card.",
        )

        return session

    # Step 3: Select the best result
    iteration_count += 1
    trace.check_iterations(iteration_count)

    session["selected_item"] = session["search_results"][0]

    trace.step(
        "select_best_item",
        inputs=session["search_results"],
        returned=session["selected_item"],
    )

    # Step 4: Suggest outfit
    iteration_count += 1
    trace.check_iterations(iteration_count)

    outfit_inputs = {
        "new_item": session["selected_item"],
        "wardrobe": session["wardrobe"],
    }

    try:
        session["outfit_suggestion"] = suggest_outfit(
            session["selected_item"],
            session["wardrobe"],
        )

        trace.step(
            "suggest_outfit",
            inputs=outfit_inputs,
            returned=session["outfit_suggestion"],
        )

        # Step 5: Create fit card
        iteration_count += 1
        trace.check_iterations(iteration_count)

        fit_card_inputs = {
            "outfit": session["outfit_suggestion"],
            "new_item": session["selected_item"],
        }

        session["fit_card"] = create_fit_card(
            session["outfit_suggestion"],
            session["selected_item"],
        )

        trace.step(
            "create_fit_card",
            inputs=fit_card_inputs,
            returned=session["fit_card"],
        )

    except ModelUnavailable as exc:
        session["error"] = (
            f"The styling model is unavailable: {exc} "
            "Please check your API key or internet connection and try again."
        )

        trace.step(
            "model_unavailable",
            returned=session["error"],
            note="Model request failed; stopping the agent.",
        )

    return session


# ── running it directly ───────────────────────────────────────────────────────

def _show(session: dict) -> None:

    if session["error"]:
        print(f"  stopped: {session['error']}")
        print(
            f"  fit_card is {session['fit_card']!r} "
            "— it should still be None here if generation stopped"
        )
        return

    item = session["selected_item"] or {}

    print(
        f"  found:    {item.get('title')} — "
        f"${item.get('price')} on {item.get('platform')}"
    )

    print(f"  outfit:   {session['outfit_suggestion']}")
    print(f"  fit card: {session['fit_card']}")


if __name__ == "__main__":

    from utils.data_loader import get_example_wardrobe

    print("=== A query the data can match ===")

    _show(
        run_agent(
            query="looking for a vintage graphic tee under $30",
            wardrobe=get_example_wardrobe(),
        )
    )

    print("\n=== A query it can't ===")

    _show(
        run_agent(
            query="designer ballgown size XXS under $5",
            wardrobe=get_example_wardrobe(),
        )
    )

    print(
        "\nThe second one should stop before the fit card. "
        "If both paths look the same,\n"
        "the branch isn't doing anything yet."
    )
