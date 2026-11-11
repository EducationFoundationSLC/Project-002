""""Ask AI": answer plain-English questions about the property data with Claude.

How it works:
  1. The website sends the question to the server (POST /api/ask).
  2. We send the question to Claude, along with a description of our database
     and two tools Claude can use:
       - run_sql: run a read-only SQL query and see the results
       - show_on_website: show a set of properties in the website's table and map
  3. Claude decides which tools to call. We run them and send back the results.
     This repeats until Claude writes its answer.

Safety: Claude's SQL runs on a read-only connection, and an "authorizer" blocks
anything other than reading (no changes, no attaching other files). Queries
that run too long are stopped.

Setup: install the SDK (pip install anthropic) and set the ANTHROPIC_API_KEY
environment variable before starting the server.
"""
import json
import os
import secrets
import sqlite3
import time
from collections import OrderedDict, defaultdict, deque

try:
    import anthropic
except ImportError:  # the rest of the website works without the SDK
    anthropic = None

MODEL = os.environ.get("ASK_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("ASK_EFFORT", "medium")  # low | medium | high
QUESTIONS_PER_HOUR = int(os.environ.get("ASK_QUESTIONS_PER_HOUR", "30"))  # per visitor
MAX_TOOL_ROUNDS = 8           # stop Claude from looping forever
MAX_ROWS_SHOWN_TO_CLAUDE = 50  # rows of a run_sql result sent back to Claude
MAX_SELECTION = 25000          # properties a show_on_website query may select
QUERY_SECONDS = 5              # time limit for one query

# Models that support the server-side refusal fallback.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5",
                   "claude-fable-5-1", "claude-fable-5-2"}

# Website filter names Claude may use with show_on_website (see server.py).
WEBSITE_FILTERS = [
    "category", "land_use", "jurisdiction", "zip", "exemption", "q",
    "just_min", "just_max", "assessed_min", "assessed_max", "taxable_min", "taxable_max",
    "tax_min", "tax_max", "year_min", "year_max", "area_min", "area_max",
    "acres_min", "acres_max", "beds_min", "baths_min",
    "sale_price_min", "sale_price_max", "sold_after", "sold_before",
    "pool", "homestead", "out_of_state", "improved", "exempt",
]
SORT_COLUMNS = ["est_tax", "just_value", "assessed_value", "taxable_value", "exemption_value",
                "year_built", "living_area", "acres", "last_sale_date", "last_sale_price",
                "address", "owner"]

TOOLS = [
    {
        "name": "run_sql",
        "description": (
            "Run one read-only SQLite SELECT query on the property database and get up to "
            f"{MAX_ROWS_SHOWN_TO_CLAUDE} rows back. Use it to count, add up, compare, or look up "
            "anything. Only SELECT (and WITH ... SELECT) is allowed."),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "A single SQLite SELECT statement."}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "show_on_website",
        "description": (
            "Show a set of properties in the website's results table and map, replacing the "
            "current filters. Use it whenever the user wants to see, list, or map properties. "
            "Prefer website filters when they can express the request. When they can't (for "
            "example two exemptions that must BOTH apply), set id_query to a SELECT that returns "
            "a property_id column; it is combined with the filters (both must match). "
            "Returns how many properties are shown."),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "filters": {
                    "type": "array",
                    "description": "Website filters. Multi-value filters take comma-separated values.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "enum": WEBSITE_FILTERS},
                            "value": {"type": "string"},
                        },
                        "required": ["name", "value"],
                        "additionalProperties": False,
                    },
                },
                "id_query": {"type": "string",
                             "description": "Optional SELECT returning property_id. Empty string if not needed."},
                "label": {"type": "string", "description": "Short description of the selection, e.g. 'Senior + disabled veteran'."},
                "sort": {"type": "string", "enum": SORT_COLUMNS},
                "direction": {"type": "string", "enum": ["asc", "desc"]},
            },
            "required": ["filters", "id_query", "label", "sort", "direction"],
            "additionalProperties": False,
        },
    },
]

SYSTEM_TEMPLATE = """You answer questions about St. Lucie County, Florida property records for a
property-tax website built by an after-school class. The data comes from the county Property
Appraiser's public records and the county GIS parcel maps.

Answer in plain, friendly language that an 8th grader can follow. Keep answers short: a few
sentences, or a short list or small table. Give exact numbers from the data. Never guess a number:
if you need one, query it. If the data can't answer the question, say so.

When the user wants to see or list properties, call show_on_website so they appear in the
website's table and map, then tell them how many are shown. Use run_sql for counts, totals,
averages and lookups. Owner names are public records here; it's fine to show them, but never
guess anything personal about an owner.

Taxes: est_tax is our estimate of the yearly bill ({rates_year} final millage rates) =
est_ad_valorem (value-based taxes) + non_ad_valorem (flat fees). Money columns are in dollars.
Dates are text 'YYYY-MM-DD'.

DATABASE (SQLite)
{schema}

Useful values:
- property.category: {categories}
- property.jurisdiction: {jurisdictions}
- exemptions.exemption_group (also the website's "exemption" filter): {exemption_groups}
- Flags (0/1): property.pool, property.homestead, property.out_of_state_owner

Website filters for show_on_website: category, land_use (land_use_desc values), jurisdiction,
zip, exemption (exemption_group values) take comma-separated lists (OR'd). Ranges use _min/_max:
just, assessed, taxable, tax (est_tax), year (year_built), area (living_area), acres,
sale_price; beds_min, baths_min; sold_after/sold_before (YYYY-MM-DD). Yes/no filters take "1"
or "0": pool, homestead, out_of_state, improved (has buildings), exempt (has any exemption).
q is a text search on address, owner, parcel and subdivision.
"""

# ---------------------------------------------------------------------------
# Running Claude's SQL safely

def _authorizer(action, arg1, arg2, db_name, trigger):
    """Called by SQLite for every step of a query: allow reading only."""
    allowed = (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
               getattr(sqlite3, "SQLITE_RECURSIVE", 33))
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


def run_query(db_path, sql, max_rows):
    """Run one read-only query. Returns (column names, rows, more_rows_exist)."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        con.set_authorizer(_authorizer)
        deadline = time.monotonic() + QUERY_SECONDS
        # Returning non-zero from the progress handler stops the query.
        con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        cur = con.execute(sql)  # sqlite3 refuses to run more than one statement
        rows = cur.fetchmany(max_rows + 1)
        columns = [d[0] for d in cur.description or []]
        return columns, rows[:max_rows], len(rows) > max_rows
    finally:
        con.close()


# Saved id_query results, so the website can page through them (newest kept).
SELECTIONS = OrderedDict()


def save_selection(ids):
    token = secrets.token_urlsafe(8)
    SELECTIONS[token] = ids
    while len(SELECTIONS) > 200:
        SELECTIONS.popitem(last=False)
    return token


def selection_ids(token):
    if token not in SELECTIONS:
        raise ValueError("This AI selection has expired. Ask the question again.")
    return SELECTIONS[token]


# ---------------------------------------------------------------------------

def describe_schema(db_path):
    """A compact description of the tables Claude may query."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        lines = []
        for table in ("property", "exemptions", "sales", "other_assessments", "levies", "legal"):
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
            lines.append(f"- {table}({', '.join(cols)})")
        lines.append("- parcel_geom(property_id, source, min_lat, min_lon, max_lat, max_lon) "
                     "[parcel outline bounding box; don't select the rings column]")
        lines.append("All tables join on property_id. property has one row per property.")
        values = lambda sql: "; ".join(r[0] for r in con.execute(sql))
        return SYSTEM_TEMPLATE.format(
            schema="\n".join(lines),
            rates_year=con.execute("SELECT value FROM meta WHERE key='rates_year'").fetchone()[0],
            categories=values("SELECT DISTINCT category FROM property ORDER BY 1"),
            jurisdictions=values("SELECT DISTINCT jurisdiction FROM property WHERE jurisdiction <> '' ORDER BY 1"),
            exemption_groups=values("SELECT DISTINCT exemption_group FROM exemptions ORDER BY 1"),
        )
    finally:
        con.close()


_system_prompt = None
_recent = defaultdict(deque)  # visitor -> times of recent questions


def _rate_limited(visitor):
    now = time.time()
    times = _recent[visitor]
    while times and now - times[0] > 3600:
        times.popleft()
    if len(times) >= QUESTIONS_PER_HOUR:
        return True
    times.append(now)
    return False


def setup_problem():
    """Why Ask AI can't run on this computer, or None if it can."""
    if anthropic is None:
        return "The Anthropic Python package isn't installed. Run: pip install anthropic"
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return ("No Anthropic API key is set up. Set the ANTHROPIC_API_KEY environment variable "
                "and restart the server (see README).")
    return None


def answer(question, history, current_filters, visitor, db_path, count_properties):
    """Answer one question. count_properties(filters) returns how many properties match.

    Returns {"answer": text, "queries": [...], "show": {...} or None}.
    """
    global _system_prompt
    problem = setup_problem()
    if problem:
        return {"error": problem}
    if _rate_limited(visitor):
        return {"error": f"You've asked {QUESTIONS_PER_HOUR} questions this hour. Please wait a while."}
    if _system_prompt is None:
        _system_prompt = describe_schema(db_path)

    # Earlier questions and answers (text only) so follow-ups like "now just in 34953" work.
    messages = []
    for turn in history[-6:]:
        if turn.get("role") in ("user", "assistant") and isinstance(turn.get("content"), str):
            messages.append({"role": turn["role"], "content": turn["content"][:3000]})
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    shown = {k: v for k, v in sorted(current_filters.items()) if k in WEBSITE_FILTERS}
    messages.append({"role": "user", "content":
                     f"{question}\n\n(The website currently shows filters: {json.dumps(shown) if shown else 'none'})"})

    queries, show = [], None

    def run_tool(name, args):
        """Run one tool call from Claude. Returns the text sent back to Claude."""
        nonlocal show
        if name == "run_sql":
            queries.append(args["query"])
            columns, rows, more = run_query(db_path, args["query"], MAX_ROWS_SHOWN_TO_CLAUDE)
            result = {"columns": columns, "rows": rows}
            if more:
                result["note"] = f"Only the first {MAX_ROWS_SHOWN_TO_CLAUDE} rows are shown."
            return json.dumps(result, default=str)
        if name == "show_on_website":
            filters = {}
            for f in args["filters"]:
                filters[f["name"]] = f["value"]
            if args["id_query"].strip():
                queries.append(args["id_query"])
                columns, rows, more = run_query(db_path, args["id_query"], MAX_SELECTION)
                if "property_id" not in columns:
                    raise ValueError("id_query must return a property_id column")
                if more:
                    raise ValueError(f"id_query matched more than {MAX_SELECTION} properties; narrow it down")
                i = columns.index("property_id")
                filters["selection"] = save_selection(sorted({r[i] for r in rows if r[i] is not None}))
                filters["selection_label"] = args["label"][:80]
            total = count_properties(filters)  # also checks the filter values are valid
            show = {"filters": filters, "sort": args["sort"], "dir": args["direction"],
                    "label": args["label"], "total": total}
            return json.dumps({"properties_shown": total})
        raise ValueError(f"Unknown tool {name}")

    client = anthropic.Anthropic()
    extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"} if MODEL in FALLBACK_MODELS else {}
    for _ in range(MAX_TOOL_ROUNDS):
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=[{"type": "text", "text": _system_prompt, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            messages=messages,
            output_config={"effort": EFFORT},
            **extra,
        )
        if response.stop_reason == "refusal":
            return {"answer": "Sorry, I can't help with that question.", "queries": queries, "show": show}
        # Keep Claude's whole reply (including its tool calls) in the conversation.
        messages.append({"role": "assistant", "content": response.content})
        tool_calls = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason == "pause_turn":
            continue
        if not tool_calls:
            text = "\n".join(b.text for b in response.content if b.type == "text").strip()
            return {"answer": text or "(No answer.)", "queries": queries, "show": show}
        results = []
        for call in tool_calls:
            try:
                content, is_error = run_tool(call.name, call.input), False
            except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
                content, is_error = f"Error: {e}", True  # Claude reads the error and tries again
            results.append({"type": "tool_result", "tool_use_id": call.id,
                            "content": content, "is_error": is_error})
        messages.append({"role": "user", "content": results})  # all results in one message
    return {"answer": "Sorry, that question took too many steps. Try asking it a simpler way.",
            "queries": queries, "show": show}
