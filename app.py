# app.py  –  Flask backend (LOCAL word-list, same UI)
# ------------------------------------------
#
# pip install flask wordfreq beautifulsoup4  (bs4 only if you still keep the old scraper somewhere)
#
# Start locally:  python app.py
# Render/Web host: same Procfile / gunicorn start cmd
# ------------------------------------------
from collections import Counter, defaultdict
from flask import Flask, request, render_template, jsonify
from wordfreq import zipf_frequency, top_n_list

app = Flask(__name__, static_url_path="", static_folder="static", template_folder="templates")

# ── 1 · Build an in-memory COMMON word set ──────────────────────────────────
ZIPF_THRESHOLD = 3.5          # adjust up (stricter) or down (looser)
MAX_WORDS      = 250_000      # pull this many from wordfreq’s ranked list

COMMON_WORDS = {
    w.upper()
    for w in top_n_list("en", MAX_WORDS)
    if len(w) >= 3 and zipf_frequency(w, "en") >= ZIPF_THRESHOLD
}

# ── 2 · Hard-wired blacklist always applied ────────────────────────────────
HARD_BLACKLIST = {
    "PRE", "BUM",  # existing examples
    # add more permanent junk words here if you’d like
}

# ── 3 · Helper: exact anagrams using local list ────────────────────────────
def exact_anagrams(rack: str) -> list[str]:
    have = Counter(rack)
    return sorted(
        w for w in COMMON_WORDS
        if not (Counter(w) - have)                 # can be built
        and w not in HARD_BLACKLIST               # drop permanent junk
    )

# ── 4 · Helper: format list to clickable HTML (same as before) ─────────────
def format_groups(words: list[str], cols: int = 5) -> str:
    groups = defaultdict(list)
    for w in words:
        groups[w[0]].append(w)                    # already ALL-CAPS

    lines: list[str] = []
    for idx, letter in enumerate(sorted(groups), 1):
        rows = [groups[letter][i : i + cols] for i in range(0, len(groups[letter]), cols)]
        for r, row in enumerate(rows):
            prefix = f"{idx:>3}. {letter}: " if r == 0 else " " * (len(f"{idx:>3}. {letter}: "))
            line_body = " ".join(
                f'<span class="word" data-w="{w}">{w}</span>' for w in row
            )
            lines.append(prefix + line_body)
        lines.append("")                          # blank line between letter blocks
    return "\n".join(lines)

# ── 5 · Routes ──────────────────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api")
def api():
    rack = request.args.get("rack", "").strip().upper()
    if not rack:
        return jsonify(error="rack param missing"), 400

    # dynamic (per-browser) blacklist comes from JS as comma list
    dyn = {w.strip().upper() for w in request.args.get("blacklist", "").split(",") if w.strip()}

    words = [w for w in exact_anagrams(rack) if w not in dyn]
    return format_groups(words) or "(No 3+-letter anagrams)"

# ── 6 · Run locally (Render uses gunicorn cmd) ──────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
