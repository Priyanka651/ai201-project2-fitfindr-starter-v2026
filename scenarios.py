
"""
Evaluation scenarios for FitFindr — Unit 4, Milestone 3.

Each criterion from criteria.md has a corresponding scenario.
run_eval.py executes each scenario five times.
"""

SCENARIOS = [
    {
        # Criterion 1: Complete the full three-tool workflow.
        "name": "matching query completes",
        "query": "vintage graphic tee under $30",
        "wardrobe": "example",
        "criterion": 1,
    },
    {
        # Criterion 2: Stop when no listing matches.
        "name": "impossible query stops early",
        "query": "designer ballgown size XXS under $5",
        "wardrobe": "example",
        "criterion": 2,
    },
    {
        # Criterion 3: Preserve the selected item's ID.
        "name": "selected item consistency",
        "query": "vintage graphic tee under $30",
        "wardrobe": "example",
        "criterion": 3,
    },
    {
        # Criterion 4: Fit card describes the selected item.
        "name": "fit card item description",
        "query": "vintage graphic tee under $30",
        "wardrobe": "example",
        "criterion": 4,
    },
    {
        # Criterion 5: All search results respect max_price.
        "name": "maximum price filtering",
        "query": "vintage graphic tee under $20",
        "wardrobe": "example",
        "criterion": 5,
    },
    {
        # Additional diagnostic: No saved wardrobe items.
        "name": "empty wardrobe",
        "query": "denim jacket under $50",
        "wardrobe": "empty",
        "criterion": None,
    },
]

WARDROBES = ("example", "empty")


def validate() -> list[str]:
    """Check scenarios for missing or invalid values."""
    problems = []

    for i, scenario in enumerate(SCENARIOS, 1):
        if not scenario.get("query", "").strip():
            problems.append(f"scenario {i} has no query")

        if scenario.get("wardrobe") not in WARDROBES:
            problems.append(
                f"scenario {i} has wardrobe "
                f"{scenario.get('wardrobe')!r} — "
                f"it should be one of {WARDROBES}"
            )

    return problems
