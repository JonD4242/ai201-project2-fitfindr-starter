"""
tools.py

The FitFindr tools. Each tool is a standalone function that can be called
and tested independently before being wired into the agent loop.

Required tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str

Stretch tools:
    compare_price(item)                             → str
    get_trending_styles(size)                       → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def _size_matches(listing_size: str, requested_size: str) -> bool:
    """
    Check whether a requested size matches a listing's size field.

    Splits the listing size by '/' and whitespace to get individual parts.
    "S/M" → ["S", "M"] → matches "M" but "XL (oversized)" → ["XL", ...] does NOT match "L".
    """
    parts = re.split(r"[/\s]+", listing_size.upper())
    return requested_size.upper() in parts


def _score_listing(listing: dict, keywords: list[str]) -> int:
    """
    Score a listing by how many keywords appear anywhere in its text fields.
    """
    searchable = " ".join([
        listing["title"],
        listing["description"],
        listing["category"],
        " ".join(listing["style_tags"]),
        " ".join(listing["colors"]),
        listing.get("brand") or "",
    ]).lower()

    return sum(1 for kw in keywords if kw in searchable)


def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for.
        size:        Size string to filter by, or None to skip size filtering.
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts sorted by relevance. Empty list if
        nothing matches — does NOT raise an exception.
    """
    listings = load_listings()

    filtered = listings
    if max_price is not None:
        filtered = [l for l in filtered if l["price"] <= max_price]
    if size is not None:
        filtered = [l for l in filtered if _size_matches(l["size"], size)]

    keywords = description.lower().split()
    scored = [(listing, _score_listing(listing, keywords)) for listing in filtered]
    matched = [(listing, score) for listing, score in scored if score > 0]
    matched.sort(key=lambda x: x[1], reverse=True)

    return [listing for listing, _ in matched]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key. May be empty.

    Returns:
        A non-empty string with outfit suggestions or general styling advice.
    """
    client = _get_groq_client()

    item_desc = (
        f"{new_item['title']} "
        f"(${new_item['price']:.2f}, from {new_item['platform']}, "
        f"condition: {new_item['condition']})"
    )

    if not wardrobe.get("items"):
        prompt = (
            f"A user just thrifted: {item_desc}.\n\n"
            "They haven't described their wardrobe yet. Give them practical general "
            "styling advice for this piece:\n"
            "- What types of bottoms/tops/shoes typically pair well with it\n"
            "- What vibe or aesthetic it suits\n"
            "- 1-2 specific outfit ideas using common wardrobe staples\n\n"
            "Keep the tone conversational and friendly, 3-4 sentences."
        )
    else:
        wardrobe_lines = "\n".join(
            f"  - {item['name']} ({', '.join(item['colors'])})"
            for item in wardrobe["items"]
        )
        prompt = (
            f"A user just thrifted: {item_desc}.\n\n"
            f"Their current wardrobe includes:\n{wardrobe_lines}\n\n"
            "Suggest 1-2 specific outfit combinations using the new thrifted piece "
            "and named items from their wardrobe. Be specific — call out which pieces "
            "to combine and describe the overall look. "
            "Keep the tone conversational and friendly, 3-4 sentences."
        )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
    )
    return response.choices[0].message.content


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–3 sentence casual Instagram-style caption, or an error message
        string if outfit is empty — does NOT raise an exception.
    """
    if not outfit or not outfit.strip():
        return (
            "Error: Cannot generate a fit card without an outfit suggestion. "
            "Make sure suggest_outfit ran successfully before calling create_fit_card."
        )

    client = _get_groq_client()

    prompt = (
        f"Write a 2-3 sentence Instagram caption for this thrifted outfit.\n\n"
        f"Thrifted piece: {new_item['title']} — ${new_item['price']:.2f} from {new_item['platform']}\n"
        f"Outfit: {outfit}\n\n"
        "Rules:\n"
        "- Write in casual, lowercase, first-person tone (like a real person posting, not a brand)\n"
        "- Mention the item name, price, and platform naturally (once each)\n"
        "- Capture the specific vibe of the outfit\n"
        "- No hashtags\n"
        "- 2-3 sentences only"
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=1.2,
    )
    return response.choices[0].message.content


# ── Stretch Tool 4: compare_price ─────────────────────────────────────────────

def compare_price(item: dict) -> str:
    """
    [STRETCH] Estimate whether an item's price is fair based on comparable
    listings in the dataset.

    Finds listings in the same category with overlapping style tags, calculates
    their average price, and compares it to the item's price. No LLM needed —
    this is pure data analysis.

    Args:
        item: A listing dict (the item to evaluate).

    Returns:
        A string with a verdict (great deal / fair / above average), the price
        context, and the cheapest comparable alternative found.
    """
    listings = load_listings()

    # Find listings in the same category (excluding the item itself)
    same_category = [
        l for l in listings
        if l["category"] == item["category"] and l["id"] != item["id"]
    ]

    if not same_category:
        return f"No comparable listings found to assess ${item['price']:.2f}."

    # Find listings with overlapping style tags for a tighter comparison
    item_tags = set(item.get("style_tags", []))
    similar = [
        l for l in same_category
        if set(l.get("style_tags", [])) & item_tags
    ]

    # Use similar listings if we have enough, otherwise fall back to category
    comparison_pool = similar if len(similar) >= 3 else same_category
    pool_label = "similar style" if comparison_pool is similar else item["category"]

    avg_price = sum(l["price"] for l in comparison_pool) / len(comparison_pool)
    item_price = item["price"]
    diff_pct = ((item_price - avg_price) / avg_price) * 100

    if diff_pct <= -25:
        verdict = "🟢 Great deal"
        context = f"This is {abs(diff_pct):.0f}% below the {pool_label} average (${avg_price:.2f})."
    elif diff_pct <= 5:
        verdict = "🟡 Fair price"
        context = f"This is in line with the {pool_label} average (${avg_price:.2f})."
    elif diff_pct <= 25:
        verdict = "🟠 Slightly above average"
        context = f"This is {diff_pct:.0f}% above the {pool_label} average (${avg_price:.2f})."
    else:
        verdict = "🔴 Above average"
        context = f"This is {diff_pct:.0f}% above the {pool_label} average (${avg_price:.2f})."

    cheapest = min(comparison_pool, key=lambda l: l["price"])
    alt_text = (
        f"Cheapest comparable: \"{cheapest['title']}\" "
        f"at ${cheapest['price']:.2f} on {cheapest['platform']}."
    )

    return (
        f"{verdict} — ${item_price:.2f}\n"
        f"{context}\n"
        f"{alt_text}\n"
        f"(Based on {len(comparison_pool)} comparable listings)"
    )


# ── Stretch Tool 5: get_trending_styles ───────────────────────────────────────

def get_trending_styles(size: str | None = None) -> str:
    """
    [STRETCH] Uses the LLM to surface currently popular thrift/secondhand styles.

    Since we can't scrape live fashion platforms, we use the LLM's knowledge
    of fashion trends to give the user relevant style inspiration.

    Args:
        size: Optional size to make recommendations more relevant, or None.

    Returns:
        A short list of trending styles with one sentence each describing
        the vibe and key thriftable pieces.
    """
    client = _get_groq_client()

    size_context = f" for someone who wears size {size}" if size else ""

    prompt = (
        f"You are a secondhand fashion expert. Name 3-4 styles that are currently "
        f"trending in thrift and vintage fashion{size_context}.\n\n"
        "For each style:\n"
        "- Give it a short name (e.g. 'Dark Academia', '90s Streetwear')\n"
        "- One sentence describing the vibe\n"
        "- 2-3 specific thriftable pieces that define the look\n\n"
        "Keep it practical, specific, and focused on pieces someone would actually find secondhand."
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return response.choices[0].message.content
