"""
tests/test_tools.py

Pytest tests for the three FitFindr tools.

Run all tests with:
    pytest tests/

Tests for search_listings do not require a GROQ_API_KEY.
Tests for the LLM-based tools (suggest_outfit, create_fit_card) that actually
call the API are skipped when GROQ_API_KEY is not set.
"""

import os
import pytest

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

GROQ_KEY_AVAILABLE = bool(os.getenv("GROQ_API_KEY"))


# ─────────────────────────────────────────────
# search_listings tests (no API key required)
# ─────────────────────────────────────────────

def test_search_returns_results():
    """A broad, common keyword should return at least one listing."""
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    assert isinstance(results, list)
    assert len(results) > 0, "Expected at least one result for 'vintage graphic tee'"


def test_search_empty_results():
    """An impossible query should return an empty list, not raise an exception."""
    results = search_listings("designer ballgown", size="XXS", max_price=5.0)
    assert results == [], f"Expected empty list, got {results}"


def test_search_price_filter():
    """All returned listings should have price <= max_price."""
    max_price = 20.0
    results = search_listings("vintage", size=None, max_price=max_price)
    for item in results:
        assert item["price"] <= max_price, (
            f"Item '{item['title']}' costs ${item['price']} but max_price was ${max_price}"
        )


def test_search_size_filter():
    """All returned listings should match the requested size."""
    results = search_listings("jacket", size="M", max_price=None)
    for item in results:
        # "M" should appear as a size component (e.g. "M", "S/M", "M/L")
        size_parts = item["size"].upper().replace("/", " ").split()
        assert "M" in size_parts, (
            f"Item '{item['title']}' has size '{item['size']}' — expected 'M' as a component"
        )


def test_search_returns_list_of_dicts():
    """Results should be a list of dicts with expected fields."""
    results = search_listings("denim", size=None, max_price=None)
    assert isinstance(results, list)
    if results:
        item = results[0]
        for field in ["id", "title", "price", "size", "platform", "style_tags"]:
            assert field in item, f"Expected field '{field}' missing from listing"


def test_search_sorted_by_relevance():
    """
    The top result for a specific query should be more relevant than later results.
    We check that the first result contains more query keywords than the last.
    """
    results = search_listings("vintage graphic tee streetwear", size=None, max_price=None)
    if len(results) >= 2:
        # Count keyword hits in first vs last result
        keywords = ["vintage", "graphic", "tee", "streetwear"]
        def count_hits(item):
            text = (item["title"] + " " + " ".join(item["style_tags"])).lower()
            return sum(1 for kw in keywords if kw in text)
        assert count_hits(results[0]) >= count_hits(results[-1]), (
            "Expected top result to be at least as relevant as the last result"
        )


def test_search_no_size_filter_when_none():
    """Passing size=None should not filter by size — more results expected."""
    with_size = search_listings("vintage", size="M", max_price=None)
    without_size = search_listings("vintage", size=None, max_price=None)
    assert len(without_size) >= len(with_size), (
        "Removing size filter should return same or more results"
    )


# ─────────────────────────────────────────────
# suggest_outfit tests
# ─────────────────────────────────────────────

@pytest.mark.skipif(not GROQ_KEY_AVAILABLE, reason="GROQ_API_KEY not set")
def test_suggest_outfit_returns_string():
    """suggest_outfit should return a non-empty string."""
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    assert results, "Need at least one listing to test suggest_outfit"
    result = suggest_outfit(results[0], get_example_wardrobe())
    assert isinstance(result, str)
    assert len(result) > 0, "suggest_outfit returned an empty string"


@pytest.mark.skipif(not GROQ_KEY_AVAILABLE, reason="GROQ_API_KEY not set")
def test_suggest_outfit_empty_wardrobe():
    """
    suggest_outfit with an empty wardrobe should return useful styling advice,
    not an empty string or exception.
    """
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    assert results, "Need at least one listing to test suggest_outfit"
    result = suggest_outfit(results[0], get_empty_wardrobe())
    assert isinstance(result, str), "Expected a string, not an exception"
    assert len(result) > 10, (
        f"Expected a substantive response for empty wardrobe, got: '{result}'"
    )


# ─────────────────────────────────────────────
# create_fit_card tests
# ─────────────────────────────────────────────

def test_create_fit_card_empty_outfit_returns_error_string():
    """
    create_fit_card with an empty outfit string should return an error message
    string — NOT raise an exception.
    """
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    assert results, "Need at least one listing to test create_fit_card"

    result = create_fit_card("", results[0])
    assert isinstance(result, str), "Expected a string, not an exception"
    assert "error" in result.lower() or "cannot" in result.lower(), (
        f"Expected an error message string for empty outfit, got: '{result}'"
    )


def test_create_fit_card_whitespace_outfit_returns_error_string():
    """
    create_fit_card with a whitespace-only outfit should also return an error string.
    """
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    assert results
    result = create_fit_card("   ", results[0])
    assert isinstance(result, str)
    assert "error" in result.lower() or "cannot" in result.lower()


@pytest.mark.skipif(not GROQ_KEY_AVAILABLE, reason="GROQ_API_KEY not set")
def test_create_fit_card_returns_string():
    """create_fit_card with valid inputs should return a non-empty string."""
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    assert results
    outfit = "Pair with baggy jeans and chunky sneakers for a 90s streetwear look."
    result = create_fit_card(outfit, results[0])
    assert isinstance(result, str)
    assert len(result) > 10, "Expected a substantive caption"


@pytest.mark.skipif(not GROQ_KEY_AVAILABLE, reason="GROQ_API_KEY not set")
def test_create_fit_card_varies_on_same_input():
    """
    Running create_fit_card multiple times on the same input should produce
    different outputs (due to temperature=1.2). We check 3 runs.
    """
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    assert results
    outfit = "Pair with baggy jeans and chunky sneakers."
    item = results[0]

    outputs = {create_fit_card(outfit, item) for _ in range(3)}
    assert len(outputs) > 1, (
        "Expected varied outputs from create_fit_card across multiple runs. "
        "If all outputs are identical, try increasing LLM temperature."
    )
