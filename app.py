from flask import Flask, request, jsonify, render_template
import requests
from bs4 import BeautifulSoup
from collections import Counter, defaultdict

app = Flask(__name__)

def exact_anagrams(rack: str) -> list[str]:
    """3+ letter anagrams from AllScrabbleWords using only the rack letters."""
    url = f"https://www.allscrabblewords.com/unscramble/{rack.lower()}"
    soup = BeautifulSoup(requests.get(url, timeout=10).text, "html.parser")

    def ok(word):
        return len(word) >= 3 and not (Counter(word) - Counter(rack.lower()))

    words = {a.text.strip().lower() for a in
             soup.select("div.panel-body.unscrambled li > a") if ok(a.text)}
    return sorted(words)

def format_groups(words, cols: int = 5) -> str:
    """Return the nicely formatted, clickable word list."""
    from collections import defaultdict

    # group words by first letter
    groups = defaultdict(list)
    for w in words:
        groups[w[0]].append(w.upper())          # store ALL-CAPS version

    lines = []
    for idx, letter in enumerate(sorted(groups), 1):
        # break each letter group into rows of <cols> words
        rows = [
            groups[letter][i : i + cols]
            for i in range(0, len(groups[letter]), cols)
        ]
        for r, row in enumerate(rows):
            prefix = (
                f"{idx:>3}. {letter.upper()}: "  # first row in the group
                if r == 0
                else " " * (len(f"{idx:>3}. {letter.upper()}: "))
            )
            # every word becomes a clickable span
            line_body = " ".join(
                f'<span class="word" data-w="{w}">{w}</span>' for w in row
            )
            lines.append(prefix + line_body)
        lines.append("")                         # blank line between groups

    return "\n".join(lines)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api")
def api():
    rack = request.args.get("rack", "").strip()
    if not rack:
        return jsonify(error="rack param missing"), 400
    words = exact_anagrams(rack)
    return format_groups(words) or "(No 3+-letter anagrams)"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
