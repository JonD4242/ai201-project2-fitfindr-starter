"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
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

    We split the listing size by '/' and whitespace to get individual parts.
    For example:
      - "S/M" → ["S", "M"]  → matches "M"
      - "XL (oversized)" → ["XL", "(oversized)"] → matches "XL", NOT "L"
      - "M" → ["M"] → matches "M"

    This avoids "L" accidentally matching "XL".
    """
    parts = re.split(r"[/\s]+", listing_size.upper())
    return requested_size.upper() in parts


def _score_listing(listing: dict, keywords: list[str]) -> int:
    """
    Score a listing by how many keywords appear anywhere in its text fields.

    We build one big lowercase string from all searchable fields and count
    how many unique keywords appear in it.
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
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform
    """
    listings = load_listings()

    # Step 1: Apply hard filters (price and size)
    filtered = listings

    if max_price is not None:
        filtered = [l for l in filtered if l["price"] <= max_price]

    if size is not None:
        filtered = [l for l in filtered if _size_matches(l["size"], size)]

    # Step 2: Score remaining listings by keyword overlap with description
    keywords = description.lower().split()
    scored = [
        (listing, _score_listing(listing, keywords))
        for listing in filtered
    ]

    # Step 3: Drop listings with zero keyword matches
    matched = [(listing, score) for listing, score in scored if score > 0]

    # Step 4: Sort by score, highest first
    matched.sort(key=lambda x: x[1], reverse=True)

    # Return just the listing dicts (not the scores)
    return [listing for listing, _ in matched]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offers general styling advice for the item
        rather than raising an exception or returning an empty string.
    """
    client = _get_groq_client()

    # Build a short description of the new item for the prompt
    item_desc = (
        f"{new_item['title']} "
        f"(${new_item['price']:.2f}, from {new_item['platform']}, "
        f"condition: {new_item['condition']})"
    )

    if not wardrobe.get("items"):
        # Empty wardrobe — give general advice instead of crashing
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
        # Build a list of their wardrobe items for the prompt
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
        A 2–3 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, returns a descriptive error message
        string — does NOT raise an exception.
    """
    # Guard: return an error string (not an exception) for empty outfit input
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
        "- 2-3 sentences only\n"
        "- Make it sound like something someone would actually caption a photo with"
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=1.2,  # Higher temperature = more varied outputs each time
    )
    return response.choices[0].message.content
