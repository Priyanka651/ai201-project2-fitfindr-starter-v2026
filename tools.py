from generate import generate
import config
from generate import generate
from utils.data_loader import load_listings


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:

    listings = load_listings()

    keywords = {
        word.strip(".,!?-").lower()
        for word in description.split()
        if word.strip(".,!?-")
    }

    matches = []

    for listing in listings:

        # Filter by maximum price
        if max_price is not None and listing["price"] > max_price:
            continue

        # Filter by size
        if size:
            requested_size = size.strip().lower()

            listing_sizes = (
                listing["size"]
                .lower()
                .replace("(", " ")
                .replace(")", " ")
                .replace("/", " ")
                .replace("-", " ")
                .split()
            )

            if requested_size not in listing_sizes:
                continue

        # Create searchable text
        searchable_parts = [
            listing["title"],
            listing["description"],
            listing["category"],
            " ".join(listing["style_tags"]),
            " ".join(listing["colors"]),
            listing["brand"] or "",
        ]

        searchable_text = " ".join(searchable_parts).lower()

        # Calculate keyword match score
        score = sum(
            1
            for keyword in keywords
            if keyword in searchable_text
        )

        if score > 0:
            matches.append((score, listing))

    # Sort best matches first
    matches.sort(
        key=lambda item: item[0],
        reverse=True
    )

    return [
        listing
        for _, listing in matches[:config.SEARCH_RESULT_LIMIT]
    ]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:

    wardrobe_items = wardrobe.get("items", [])

    # Empty wardrobe case
    if not wardrobe_items:
        prompt = f"""
You are a fashion styling assistant.

The user is considering this thrifted item:

Title: {new_item.get('title')}
Category: {new_item.get('category')}
Colors: {new_item.get('colors')}
Style tags: {new_item.get('style_tags')}

The user's wardrobe is empty.

Give one or two short and practical general styling ideas for this item.
"""

        return generate(prompt)

    # Format wardrobe items
    wardrobe_text = "\n".join(
        f"- {item.get('name')} | "
        f"category: {item.get('category')} | "
        f"colors: {item.get('colors')} | "
        f"style: {item.get('style_tags')}"
        for item in wardrobe_items
    )

    prompt = f"""
You are a fashion styling assistant.

The user is considering this thrifted item:

Title: {new_item.get('title')}
Category: {new_item.get('category')}
Colors: {new_item.get('colors')}
Style tags: {new_item.get('style_tags')}

The user already owns these wardrobe items:

{wardrobe_text}

Suggest one or two outfits using the new item with specific pieces
from the user's wardrobe.

Keep the suggestions short, clear, and practical.
"""

    return generate(prompt)


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:

    # Guard against empty outfit
    if not outfit or not outfit.strip():
        return "No outfit suggestion was provided, so a fit card could not be created."

    prompt = f"""
You are writing a short social-media-style fit card.

New thrifted item:
Title: {new_item.get('title')}
Price: ${new_item.get('price')}
Platform: {new_item.get('platform')}
Colors: {new_item.get('colors')}
Style tags: {new_item.get('style_tags')}

Outfit suggestion:
{outfit}

Write a natural two-to-four sentence caption someone could actually post.

Requirements:
- Mention the thrifted item.
- Mention its price exactly once.
- Mention the platform exactly once.
- Describe the outfit vibe.
- Keep it short and natural.
"""

    return generate(prompt)