"""
utils/profile.py

Style profile memory — saves and loads a user's wardrobe across sessions.
Profile is stored as a JSON file at ~/.fitfindr_profile.json.
"""

import json
import os

PROFILE_PATH = os.path.expanduser("~/.fitfindr_profile.json")


def save_profile(wardrobe: dict) -> str:
    """
    Save the user's wardrobe to disk so it persists across sessions.

    Args:
        wardrobe: A wardrobe dict with an 'items' key.

    Returns:
        A confirmation string.
    """
    data = {"wardrobe": wardrobe}
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return f"Wardrobe saved ({len(wardrobe.get('items', []))} items)."


def load_profile() -> dict | None:
    """
    Load the user's saved wardrobe from disk.

    Returns:
        The saved wardrobe dict, or None if no profile exists yet.
    """
    if not os.path.exists(PROFILE_PATH):
        return None
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("wardrobe")


def profile_exists() -> bool:
    """Return True if a saved profile exists on disk."""
    return os.path.exists(PROFILE_PATH)


def delete_profile() -> str:
    """Delete the saved profile from disk."""
    if os.path.exists(PROFILE_PATH):
        os.remove(PROFILE_PATH)
        return "Profile deleted."
    return "No profile found to delete."
