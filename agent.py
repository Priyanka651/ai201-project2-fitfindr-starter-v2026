"""
The FitFindr planning loop.

The agent:
1. Parses the user's query.
2. Searches thrift listings.
3. Stops if no listing matches.
4. Selects the best result.
5. Suggests an outfit.
6. Creates a fit card.
"""

import re

import config
import trace
from tools import search_listings, suggest_outfit, create_fit_card
from generate import ModelUnavailable


# ── session state ─────────────────────────────────────────────────────────────

def new_session(query: str, wardrobe: dict) -> dict:
    """
    Create a new session for one FitFindr interaction.
    """

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
    """
    Parse the user's query into:
    - description
    - size
    - max_price
    """

    description = query.strip()
    size = None
    max_price = None

    # Find price patterns such as:
    # under $30
    # below $30
    # max $30
    price_match = re.search(
        r"(?:under|below|max(?:imum)?|less than)\s*\$?\s*(\d+(?:\.\d+)?)",
        query,
        re.IGNORECASE,
    )

    if price_match:
        max_price = float(price_match.group(1))

        # Remove price phrase from description
        description = re.sub(
            r"(?:under|below|max(?:imum)?|less than)\s*\$?\s*\d+(?:\.\d+)?",
            "",
            description,
            flags=re.IGNORECASE,
        )

    # Find explicit size such as:
    # size M
    # size S/M
    # size XL
    # size W30
    size_match = re.search(
        r"\bsize\s+([A-Za-z0-9/]+)",
        query,
        re.IGNORECASE,
    )

    if size_match:
        size = size_match.group(1)

        # Remove size phrase from description
        description = re.sub(
            r"\bsize\s+[A-Za-z0-9/]+",
            "",
            description,
            flags=re.IGNORECASE,
        )

    # Remove common request phrases so the description
    # focuses on the item itself.
    description = re.sub(
        r"\b(?:looking for|find me|search for|i want|i need)\b",
        "",
        description,
        flags=re.IGNORECASE,
    )

    # Clean extra commas and spaces
    description = description.replace(",", " ")
    description = " ".join(description.split())

    return {
        "description": description,
        "size": size,
        "max_price": max_price,
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Run the FitFindr planning loop once and return the completed session.
    """

    session = new_session(query, wardrobe)

    iteration_count = 0

    # ── Step 1: Parse query ────────────────────────────────────────────────

    iteration_count += 1
    trace.check_iterations(iteration_count) # type: ignore

    session["parsed"] = parse_query(session["query"])

    # Read parsed values back from session
    description = session["parsed"]["description"]
    size = session["parsed"]["size"]
    max_price = session["parsed"]["max_price"]

    # ── Step 2: Search listings ────────────────────────────────────────────

    iteration_count += 1
    trace.check_iterations(iteration_count)

    session["search_results"] = search_listings(
        description=description,
        size=size,
        max_price=max_price,
    )

    # ── BRANCH: Stop if nothing matched ────────────────────────────────────

    if not session["search_results"]:
        session["error"] = (
            "I couldn't find a matching item. Try increasing your budget, "
            "changing the size, or using a broader item description."
        )
        return session

    # ── Step 3: Select first/best result ───────────────────────────────────

    iteration_count += 1
    trace.check_iterations(iteration_count)

    session["selected_item"] = session["search_results"][0]

    # ── Step 4: Suggest outfit ─────────────────────────────────────────────

    iteration_count += 1
    trace.check_iterations(iteration_count)

    # Important: read selected item from session
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"],
        session["wardrobe"],
    )

    # ── Step 5: Create fit card ────────────────────────────────────────────

    iteration_count += 1
    trace.check_iterations(iteration_count)

    # Again, read previous results back from session
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"],
        session["selected_item"],
    )

    return session


# ── running it directly ───────────────────────────────────────────────────────

def _show(session: dict) -> None:

    if session["error"]:
        print(f"  stopped: {session['error']}")
        print(
            f"  fit_card is {session['fit_card']!r} "
            "— it should still be None here"
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