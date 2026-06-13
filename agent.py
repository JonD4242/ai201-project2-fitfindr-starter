"""
agent.py

The FitFindr planning loop. Orchestrates all tools in response to a natural
language user query, passing state between them via a session dict.

Stretch features added:
  - Retry logic: if search returns empty, retries with loosened constraints
  - Price comparison: runs compare_price() on the selected item
  - Trend awareness: runs get_trending_styles() alongside the main flow
"""

import re

from tools import (
    search_listings,
    suggest_outfit,
    create_fit_card,
    compare_price,
    get_trending_styles,
)


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """Initialize and return a fresh session dict for one user interaction."""
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "search_adjustment": None,   # set if retry logic loosened the search
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "price_comparison": None,    # stretch: compare_price result
        "trending_styles": None,     # stretch: get_trending_styles result
        "error": None,
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query
    using regex patterns. No LLM call needed — fast and free.
    """
    size_pattern = re.compile(
        r'\bsize\s+([A-Za-z]{1,3})\b|\b(XS|S|M|L|XL|XXL|XXXL)\b',
        re.IGNORECASE,
    )
    price_pattern = re.compile(
        r'(?:under|below|max|for)\s+\$?(\d+(?:\.\d+)?)'
        r'|\$(\d+(?:\.\d+)?)\s*(?:max|or\s+less|and\s+under)?',
        re.IGNORECASE,
    )

    size_match = size_pattern.search(query)
    price_match = price_pattern.search(query)

    size = None
    if size_match:
        raw = size_match.group(1) or size_match.group(2)
        size = raw.upper()

    max_price = None
    if price_match:
        raw_price = price_match.group(1) or price_match.group(2)
        max_price = float(raw_price)

    description = query
    for pattern in [
        r'\bsize\s+[A-Za-z]{1,3}\b',
        r'\b(?:under|below|max|for)\s+\$?\d+(?:\.\d+)?\b',
        r'\$\d+(?:\.\d+)?(?:\s+(?:max|or\s+less|and\s+under))?\b',
        r'\b(XS|S|M|L|XL|XXL|XXXL)\b',
        r'\bin\b',
    ]:
        description = re.sub(pattern, '', description, flags=re.IGNORECASE)

    filler = re.compile(
        r"^(?:i'?m?\s+)?(?:looking\s+for|want|need|find\s+me|i\s+want)\s+(?:a\s+|an\s+)?",
        re.IGNORECASE,
    )
    description = filler.sub('', description)
    description = re.sub(r'[,;]+', ' ', description)
    description = re.sub(r'\s+', ' ', description).strip()

    return {
        "description": description or query,
        "size": size,
        "max_price": max_price,
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Planning loop:
        1. Initialize session.
        2. Parse query → description, size, max_price.
        3. Call search_listings(). If empty, retry with loosened constraints
           (drop size first, then price). [STRETCH: retry logic]
        4. If still empty → set error, return early.
        5. Select top result → session["selected_item"].
        6. Call compare_price() on the selected item. [STRETCH]
        7. Call get_trending_styles() for style inspiration. [STRETCH]
        8. Call suggest_outfit() with selected item + wardrobe.
        9. Call create_fit_card() with outfit + selected item.
        10. Return completed session.

    Args:
        query:    Natural language user request.
        wardrobe: User's wardrobe dict.

    Returns:
        Session dict. Check session["error"] first — if set, the interaction
        ended early and outfit_suggestion / fit_card will be None.
        Check session["search_adjustment"] to see if retry logic changed the search.
    """
    # Step 1: Initialize session
    session = _new_session(query, wardrobe)

    # Step 2: Parse the query
    parsed = _parse_query(query)
    session["parsed"] = parsed
    description = parsed["description"]
    size = parsed["size"]
    max_price = parsed["max_price"]

    # Step 3: Search with retry logic (STRETCH)
    try:
        results = search_listings(description, size=size, max_price=max_price)
        adjustments = []

        # Retry 1: drop size filter if it's too restrictive
        if not results and size is not None:
            results = search_listings(description, size=None, max_price=max_price)
            if results:
                adjustments.append(f"removed size filter (no '{size}' listings found)")
                session["parsed"]["size"] = None

        # Retry 2: drop price filter if still nothing
        if not results and max_price is not None:
            results = search_listings(description, size=None, max_price=None)
            if results:
                adjustments.append(f"removed price limit (nothing under ${max_price:.0f})")
                session["parsed"]["max_price"] = None

        if adjustments:
            session["search_adjustment"] = (
                "⚠️ Search was broadened: " + " and ".join(adjustments) + "."
            )

        session["search_results"] = results

    except Exception as e:
        session["error"] = f"Search failed unexpectedly: {e}"
        return session

    # Step 4: If still no results after retries, stop here
    if not results:
        parts = [f"'{description}'"]
        if size:
            parts.append(f"size {size}")
        if max_price is not None:
            parts.append(f"under ${max_price:.0f}")
        session["error"] = (
            f"No listings found for {' in '.join(parts)}. "
            "Try different keywords, a different size, or a higher budget."
        )
        return session

    # Step 5: Pick the top result
    session["selected_item"] = results[0]

    # Step 6: Price comparison (STRETCH) — runs independently, won't block other tools
    try:
        session["price_comparison"] = compare_price(session["selected_item"])
    except Exception as e:
        session["price_comparison"] = f"Price comparison unavailable: {e}"

    # Step 7: Trending styles (STRETCH) — uses parsed size for relevance
    try:
        session["trending_styles"] = get_trending_styles(session["parsed"].get("size"))
    except Exception as e:
        session["trending_styles"] = f"Trend data unavailable: {e}"

    # Step 8: Suggest outfit
    try:
        session["outfit_suggestion"] = suggest_outfit(
            session["selected_item"],
            session["wardrobe"],
        )
    except Exception as e:
        session["error"] = f"Outfit suggestion failed: {e}"
        return session

    # Step 9: Create fit card
    try:
        session["fit_card"] = create_fit_card(
            session["outfit_suggestion"],
            session["selected_item"],
        )
    except Exception as e:
        session["error"] = f"Fit card generation failed: {e}"
        return session

    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        if session["search_adjustment"]:
            print(f"Note: {session['search_adjustment']}\n")
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nPrice check: {session['price_comparison']}")
        print(f"\nTrending: {session['trending_styles'][:200]}...")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== Retry path: impossible size, will drop size filter ===\n")
    session2 = run_agent(
        query="vintage graphic tee size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    if session2["search_adjustment"]:
        print(f"Adjustment: {session2['search_adjustment']}")
    if session2["error"]:
        print(f"Error: {session2['error']}")
    else:
        print(f"Found after retry: {session2['selected_item']['title']}")

    print("\n\n=== No-results path ===\n")
    session3 = run_agent(
        query="designer ballgown size XXS under $1",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error: {session3['error']}")
