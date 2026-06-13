"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract a description, size, and max_price from a natural language query
    using regex patterns.

    We use regex rather than an LLM call here because:
    - It's fast and free (no API call)
    - These patterns are predictable enough for regex to handle reliably
    - It keeps the agent lean

    Examples:
        "vintage graphic tee under $30, size M"
        → {"description": "vintage graphic tee", "size": "M", "max_price": 30.0}

        "90s track jacket in size L"
        → {"description": "90s track jacket", "size": "L", "max_price": None}

        "flowy midi skirt under $40"
        → {"description": "flowy midi skirt", "size": None, "max_price": 40.0}
    """
    # --- Extract size ---
    # Matches: "size M", "size XL", standalone "M" / "XL" etc.
    size_pattern = re.compile(
        r'\bsize\s+([A-Za-z]{1,3})\b|\b(XS|S|M|L|XL|XXL|XXXL)\b',
        re.IGNORECASE,
    )
    size_match = size_pattern.search(query)
    size = None
    if size_match:
        raw = size_match.group(1) or size_match.group(2)
        size = raw.upper()

    # --- Extract price ---
    # Matches: "under $30", "below 40", "$25 max", "for $20"
    price_pattern = re.compile(
        r'(?:under|below|max|for)\s+\$?(\d+(?:\.\d+)?)'
        r'|\$(\d+(?:\.\d+)?)\s*(?:max|or\s+less|and\s+under)?',
        re.IGNORECASE,
    )
    price_match = price_pattern.search(query)
    max_price = None
    if price_match:
        raw_price = price_match.group(1) or price_match.group(2)
        max_price = float(raw_price)

    # --- Build description by removing the size and price fragments ---
    description = query
    for pattern in [
        r'\bsize\s+[A-Za-z]{1,3}\b',
        r'\b(?:under|below|max|for)\s+\$?\d+(?:\.\d+)?\b',
        r'\$\d+(?:\.\d+)?(?:\s+(?:max|or\s+less|and\s+under))?\b',
        r'\b(XS|S|M|L|XL|XXL|XXXL)\b',
        r'\bin\b',    # "in size M" → clean up leftover "in"
    ]:
        description = re.sub(pattern, '', description, flags=re.IGNORECASE)

    # Clean up filler phrases and extra whitespace
    filler = re.compile(
        r"^(?:i'?m?\s+)?(?:looking\s+for|want|need|find\s+me|i\s+want)\s+(?:a\s+|an\s+)?",
        re.IGNORECASE,
    )
    description = filler.sub('', description)
    description = re.sub(r'[,;]+', ' ', description)   # remove stray punctuation
    description = re.sub(r'\s+', ' ', description).strip()

    # Fall back to full query if parsing strips everything
    if not description:
        description = query

    return {
        "description": description,
        "size": size,
        "max_price": max_price,
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    Planning loop logic:
        1. Initialize session.
        2. Parse the query → extract description, size, max_price.
        3. Call search_listings().
           → If no results: set session["error"] and return early.
           → If results: pick the top result and continue.
        4. Call suggest_outfit() with the selected item and wardrobe.
        5. Call create_fit_card() with the outfit suggestion and selected item.
        6. Return the completed session.
    """
    # Step 1: Initialize session
    session = _new_session(query, wardrobe)

    # Step 2: Parse the user's query into structured parameters
    parsed = _parse_query(query)
    session["parsed"] = parsed

    description = parsed["description"]
    size = parsed["size"]
    max_price = parsed["max_price"]

    # Step 3: Search for listings
    try:
        results = search_listings(description, size=size, max_price=max_price)
    except Exception as e:
        session["error"] = f"Search failed unexpectedly: {e}"
        return session

    session["search_results"] = results

    # Branch: no results → stop here, do NOT call the other tools
    if not results:
        parts = [f"'{description}'"]
        if size:
            parts.append(f"size {size}")
        if max_price is not None:
            parts.append(f"under ${max_price:.0f}")
        search_summary = " in ".join(parts)

        session["error"] = (
            f"No listings found for {search_summary}. "
            "Try broadening your search — remove the size filter, raise your "
            "budget, or use different keywords."
        )
        return session

    # Step 4: Pick the top result and store it in session state
    session["selected_item"] = results[0]

    # Step 5: Suggest an outfit using the selected item and wardrobe
    try:
        session["outfit_suggestion"] = suggest_outfit(
            session["selected_item"],
            session["wardrobe"],
        )
    except Exception as e:
        session["error"] = f"Outfit suggestion failed: {e}"
        return session

    # Step 6: Generate the fit card caption
    try:
        session["fit_card"] = create_fit_card(
            session["outfit_suggestion"],
            session["selected_item"],
        )
    except Exception as e:
        session["error"] = f"Fit card generation failed: {e}"
        return session

    # Step 7: Return the fully populated session
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
