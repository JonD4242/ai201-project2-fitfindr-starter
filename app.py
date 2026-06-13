"""
app.py

Gradio interface for FitFindr — now with stretch features:
  - Price comparison panel
  - Trending styles panel
  - Style profile memory (save/load wardrobe across sessions)
  - Retry logic is handled in agent.py; search adjustments shown in listing panel

Run with:
    python app.py
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe
from utils.profile import save_profile, load_profile, profile_exists


# ── query handler ─────────────────────────────────────────────────────────────

def _format_listing(item: dict, adjustment: str | None = None) -> str:
    """Format a listing dict into a readable string for the output panel."""
    colors = ", ".join(item.get("colors", []))
    tags = ", ".join(item.get("style_tags", []))
    brand = item.get("brand") or "Unknown"
    text = (
        f"Title:     {item['title']}\n"
        f"Price:     ${item['price']:.2f}\n"
        f"Platform:  {item['platform']}\n"
        f"Size:      {item['size']}\n"
        f"Condition: {item['condition']}\n"
        f"Colors:    {colors}\n"
        f"Brand:     {brand}\n"
        f"Style:     {tags}\n\n"
        f"{item['description']}"
    )
    if adjustment:
        text = adjustment + "\n\n" + text
    return text


def handle_query(
    user_query: str,
    wardrobe_choice: str,
) -> tuple[str, str, str, str, str]:
    """
    Called by Gradio when the user submits a query.

    Returns a tuple of 5 strings mapping to the 5 output panels:
        (listing_text, outfit_suggestion, fit_card, price_comparison, trending_styles)
    """
    if not user_query or not user_query.strip():
        return "Please enter a search query.", "", "", "", ""

    # Select wardrobe
    if wardrobe_choice == "Saved profile":
        wardrobe = load_profile() or get_example_wardrobe()
    elif wardrobe_choice == "Example wardrobe":
        wardrobe = get_example_wardrobe()
    else:
        wardrobe = get_empty_wardrobe()

    session = run_agent(query=user_query.strip(), wardrobe=wardrobe)

    if session["error"]:
        return session["error"], "", "", "", ""

    listing_text = _format_listing(
        session["selected_item"],
        adjustment=session.get("search_adjustment"),
    )

    return (
        listing_text,
        session["outfit_suggestion"] or "",
        session["fit_card"] or "",
        session["price_comparison"] or "",
        session["trending_styles"] or "",
    )


def handle_save_profile(wardrobe_choice: str) -> str:
    """Save the currently selected wardrobe to disk."""
    if wardrobe_choice == "Empty wardrobe (new user)":
        return "Nothing to save — choose 'Example wardrobe' first."
    if wardrobe_choice == "Saved profile":
        wardrobe = load_profile() or get_example_wardrobe()
    else:
        wardrobe = get_example_wardrobe()
    result = save_profile(wardrobe)
    return f"✅ {result}"


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # triggers error path
    "vintage jacket size XXS under $20",     # triggers retry logic
]


def build_interface():
    # Build wardrobe choices — include "Saved profile" only if one exists
    wardrobe_choices = ["Example wardrobe", "Empty wardrobe (new user)"]
    if profile_exists():
        wardrobe_choices.insert(0, "Saved profile")

    with gr.Blocks(title="FitFindr") as demo:
        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas, price checks, and trend inspiration.
Describe what you're looking for — include size and price to filter results.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            with gr.Column(scale=1):
                wardrobe_choice = gr.Radio(
                    choices=wardrobe_choices,
                    value=wardrobe_choices[0],
                    label="Wardrobe",
                )
                save_btn = gr.Button("💾 Save wardrobe to profile", size="sm")
                save_status = gr.Textbox(label="", lines=1, interactive=False, show_label=False)

        submit_btn = gr.Button("Find it", variant="primary")

        # Row 1: Core results
        with gr.Row():
            listing_output = gr.Textbox(
                label="🛍️ Top listing found",
                lines=10,
                interactive=False,
            )
            outfit_output = gr.Textbox(
                label="👗 Outfit idea",
                lines=10,
                interactive=False,
            )
            fitcard_output = gr.Textbox(
                label="✨ Your fit card",
                lines=10,
                interactive=False,
            )

        # Row 2: Stretch feature outputs
        with gr.Row():
            price_output = gr.Textbox(
                label="💰 Price check",
                lines=6,
                interactive=False,
            )
            trending_output = gr.Textbox(
                label="🔥 Trending styles",
                lines=6,
                interactive=False,
            )

        gr.Examples(
            examples=[[q, wardrobe_choices[0]] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        # Wire up buttons
        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output,
                     price_output, trending_output],
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output,
                     price_output, trending_output],
        )
        save_btn.click(
            fn=handle_save_profile,
            inputs=[wardrobe_choice],
            outputs=[save_status],
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
