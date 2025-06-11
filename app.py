# app.py  –  Flask backend (scrapes AllScrabbleWords.com)
# -------------------------------------------------------
from collections import Counter, defaultdict
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, render_template, jsonify

app = Flask(__name__,
            static_url_path="",
            static_folder="static",
            template_folder="templates")

# ---- permanent blacklist (always hidden) ---------------
HARD_BLACKLIST = {
    "PRE", "BUM",  # add more here if you like
}

# ---- helper: scrape & filter ----------------------------
def scrape_words(rack: str) -> list[str]:
    url = f"https://www.allscrabblewords.com/unscramble/{rack.lower()}"
    html = requests.get(url, timeout=10).text
    soup = BeautifulSoup(html, "html.parser")

    raw = (
        a.text.strip().upper()
        for a in soup.select("div.panel-body.unscrambled li > a")
    )
    have = Counter(rack)
    words = {
        w for w in raw
        if len(w) >= 3 and not (Counter(w) - have)  # exact anagram only
        and w not in HARD_BLACKLIST
    }
    return sorted(words)

# ---- helper: HTML formatter (unchanged) -----------------
def format_groups(words: list[str], cols: int = 5) -> str:
    groups = defaultdict(list)
    for w in words:
        groups[w[0]].append(w)

    lines = []
    for idx, letter in enumerate(sorted(groups), 1):
        rows = [groups[letter][i : i + cols]
                for i in range(0, len(groups[letter]), cols)]
        for r, row in enumerate(rows):
            prefix = f"{idx:>3}. {letter}: " if r == 0 \
                     else " " * (len(f"{idx:>3}. {letter}: "))
            line_body = " ".join(
                f'<span class="word" data-w="{w}">{w}</span>' for w in row
            )
            lines.append(prefix + line_body)
        lines.append("")
    return "\n".join(lines)

# ---- routes ---------------------------------------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api")
def api():
    rack = request.args.get("rack", "").strip().upper()
    if not rack:
        return jsonify(error="rack param missing"), 400

    dyn = {w.strip().upper()
           for w in request.args.get("blacklist", "").split(",") if w.strip()}

    words = [w for w in scrape_words(rack) if w not in dyn]
    return format_groups(words) or "(No 3+-letter anagrams)"

# ---- local run ------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
