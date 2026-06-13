# FitFindr

A multi-tool AI agent that helps users find secondhand clothing and figure out how to style it. Given a natural language query, FitFindr searches a mock thrift listings dataset, suggests outfit combinations using the user's wardrobe, and generates a shareable Instagram-style caption — all in one flow.

Built for AI201 (Applications of AI Engineering), Week 2 Project.

---

## Demo

> Record your demo video and add the link here before submitting.

---

## Setup

**Prerequisites:** Python 3.10+, a free [Groq API key](https://console.groq.com) (no credit card required — same account from Project 1).

```bash
# 1. Clone your fork
git clone https://github.com/YOUR-USERNAME/ai201-project2-fitfindr-starter.git
cd ai201-project2-fitfindr-starter

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Mac/Linux
# .venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add your Groq API key
echo "GROQ_API_KEY=your_key_here" > .env

# 5. Run the app
python app.py
```

Open the URL shown in your terminal (usually `http://localhost:7860`).

---

## Tool Inventory

### Tool 1: `search_listings`

**Function signature:** `search_listings(description: str, size: str | None, max_price: float | None) -> list[dict]`

**Purpose:** Searches the mock listings dataset and returns a ranked list of items matching the user's description, with optional size and price filters.

**Inputs:**
- `description` (str) — Keywords describing what the user wants, e.g. `"vintage graphic tee"`. Used for keyword scoring.
- `size` (str | None) — Clothing size like `"M"` or `"XL"`. Matching is done by splitting the listing's size field (e.g. `"S/M"` → `["S","M"]`) so `"M"` matches `"S/M"` but not `"XL"`. Pass `None` to skip size filtering.
- `max_price` (float | None) — Maximum price in USD, inclusive. Pass `None` to skip price filtering.

**Output:** A list of listing dicts sorted by relevance score (how many description keywords appear in the listing's title, description, category, style tags, colors, and brand). Returns `[]` if nothing matches — never raises an exception.

Each listing dict has: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand`, `platform`.

---

### Tool 2: `suggest_outfit`

**Function signature:** `suggest_outfit(new_item: dict, wardrobe: dict) -> str`

**Purpose:** Uses the Groq LLM (`llama-3.3-70b-versatile`) to suggest 1–2 outfit combinations using the thrifted item and the user's wardrobe. If the wardrobe is empty, gives general styling advice instead.

**Inputs:**
- `new_item` (dict) — A listing dict from `search_listings`. Uses `title`, `price`, `platform`, and `condition` in the prompt.
- `wardrobe` (dict) — A wardrobe dict with an `items` key containing a list of wardrobe item dicts. Each item has `name`, `colors`, and `style_tags`. May have an empty `items` list.

**Output:** A non-empty string with outfit suggestions (3–4 sentences). If `wardrobe["items"]` is empty, the response contains general styling advice for the item type rather than references to specific wardrobe pieces.

---

### Tool 3: `create_fit_card`

**Function signature:** `create_fit_card(outfit: str, new_item: dict) -> str`

**Purpose:** Uses the Groq LLM to generate a casual, shareable 2–3 sentence Instagram/TikTok-style caption for the outfit. Uses `temperature=1.2` to produce different output each time.

**Inputs:**
- `outfit` (str) — The outfit suggestion string from `suggest_outfit`. If empty or whitespace-only, the function returns an error message string without calling the LLM.
- `new_item` (dict) — The listing dict. Uses `title`, `price`, and `platform` to make the caption specific.

**Output:** A 2–3 sentence string written in casual, lowercase, first-person tone. Mentions the item, price, and platform naturally once each. Returns a descriptive error message string if `outfit` is empty — no exception raised.

---

## How the Planning Loop Works

The planning loop runs inside `run_agent()` in `agent.py`. Each call handles one complete user interaction and stores all state in a session dict.

**Step 1 — Parse the query.** The agent uses regex to extract three things from the user's natural language input: a description (the clothing keywords), a size (if mentioned), and a max price (if mentioned). For example, `"vintage graphic tee under $30, size M"` becomes `{description: "vintage graphic tee", size: "M", max_price: 30.0}`. Regex was chosen over an LLM call because these patterns are predictable and regex is free, fast, and doesn't require an API round-trip.

**Step 2 — Search.** The agent calls `search_listings(description, size, max_price)` and stores the results in `session["search_results"]`.

**Step 3 — Branch on search results.** This is the critical decision point. If `search_results` is empty, the agent sets `session["error"]` to a specific, actionable message ("No listings found for 'designer ballgown' in size XXS under $5. Try broadening your search...") and returns the session immediately. `suggest_outfit` and `create_fit_card` are never called with empty input. If results exist, the agent picks `results[0]` as `session["selected_item"]` and continues.

**Step 4 — Suggest outfit.** The agent calls `suggest_outfit(session["selected_item"], session["wardrobe"])` and stores the result in `session["outfit_suggestion"]`.

**Step 5 — Create fit card.** The agent calls `create_fit_card(session["outfit_suggestion"], session["selected_item"])` and stores the result in `session["fit_card"]`.

**Step 6 — Return.** The fully populated session dict is returned. `app.py` maps the session keys to the three Gradio output panels.

The loop terminates after at most one pass — it does not retry or loop indefinitely.

---

## State Management

All state for a single user interaction lives in one Python dictionary (`session`) initialized at the start of `run_agent()`. This dictionary is the only way data moves between tools — no global variables, no re-prompting the user.

The flow:
1. `session["parsed"]` is set after query parsing. Contains `description`, `size`, `max_price`.
2. `session["search_results"]` is set after `search_listings` runs.
3. `session["selected_item"]` is set to `search_results[0]`. This is the exact same dict that gets passed into `suggest_outfit` — no copies, no re-entry.
4. `session["outfit_suggestion"]` is set after `suggest_outfit`. This exact string is passed into `create_fit_card`.
5. `session["fit_card"]` is set after `create_fit_card`.
6. `session["error"]` is set (and the session returned early) if any step fails.

The wardrobe is stored in `session["wardrobe"]` from the very beginning so it's available at any point without re-asking the user.

---

## Error Handling

**`search_listings` — no results:**
The function always returns a list (empty `[]` if no matches) — it never raises an exception. In `run_agent()`, the agent checks `if not results` immediately after the call. If true, it constructs a specific error message that tells the user which search parameters returned nothing and what to try instead (e.g., "No listings found for 'vintage graphic tee' in size XXS under $10. Try broadening your search — remove the size filter or raise your budget."). The session is returned immediately without calling `suggest_outfit` or `create_fit_card`.

During testing, I confirmed this by running:
```
python -c "from tools import search_listings; print(search_listings('designer ballgown', 'XXS', 1.0))"
```
Output: `[]` — no exception, no crash.

**`suggest_outfit` — empty wardrobe:**
Before building the prompt, the function checks `if not wardrobe.get("items")`. If the list is empty, it constructs a general styling prompt ("give general pairing advice for this item type") instead of a specific wardrobe-based prompt. The LLM call still runs and returns a useful string. The user sees practical advice rather than a crash or empty output.

During testing, I confirmed this by running `suggest_outfit(results[0], get_empty_wardrobe())` and receiving a full, useful styling suggestion.

**`create_fit_card` — empty outfit string:**
At the very start of the function, before any LLM call: `if not outfit or not outfit.strip(): return "Error: Cannot generate a fit card without an outfit suggestion."`. This returns a descriptive error string rather than raising an exception. The agent can surface this to the user cleanly.

During testing, I confirmed this by running:
```
python -c "from tools import search_listings, create_fit_card; r = search_listings('vintage tee', None, None); print(create_fit_card('', r[0]))"
```
Output: `"Error: Cannot generate a fit card without an outfit suggestion..."` — no exception.

---

## Spec Reflection

**One way the spec helped:** Writing out the planning loop logic in `planning.md` before coding made it very clear that the `if not results: return early` branch had to come *before* calling `suggest_outfit`. Without the spec, it would have been easy to accidentally call `suggest_outfit(None, wardrobe)` and get a confusing error. The spec also made the session dict structure obvious — having all the keys written out meant I never had to think mid-implementation about what to name them.

**One way implementation diverged from the spec:** The spec described the planning loop as checking "what's been returned so far" in a loop-like structure. In practice, the implementation is a linear sequence with an early-return branch — there's no actual loop construct (`while`, `for`). This is actually cleaner for this agent because the tool order never changes. The project guidance notes that "your planning loop doesn't have to be complex to be real" — what matters is that the agent *responds to what it receives*, which the `if not results: return` branch achieves without needing a loop.

---

## AI Usage

**Instance 1 — Implementing `search_listings`:**
I provided Claude the Tool 1 block from `planning.md` (inputs with types and meanings, return value description including what fields each listing dict contains, and the failure mode: return `[]` not raise). I asked it to implement the function using `load_listings()` from `utils/data_loader.py` with keyword scoring. Before running the output, I reviewed it to confirm it: (1) calls `load_listings()` rather than re-implementing file reading, (2) applies all three filters, (3) scores by keyword overlap not exact match, and (4) returns `[]` for no matches. I revised the size-matching logic — the initial version used a simple `size in listing["size"]` which would incorrectly match "L" inside "XL". I changed it to split on "/" and whitespace so "M" only matches listings where "M" is a whole component.

**Instance 2 — Implementing `run_agent`:**
I provided Claude the Architecture Mermaid diagram and the Planning Loop + State Management sections from `planning.md`. I asked it to implement `run_agent()` in `agent.py` following the session dict structure already defined by `_new_session()`. Before running the output, I checked that the generated code: (1) branched on the `search_results` being empty before calling `suggest_outfit`, (2) stored values in the session dict (`session["selected_item"] = results[0]`) rather than passing them as direct local arguments, and (3) wrapped each tool call in a try/except that sets `session["error"]` rather than crashing. I added the try/except blocks myself since the first version let exceptions propagate unhandled.
