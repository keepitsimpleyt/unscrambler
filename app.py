from collections import Counter, defaultdict
from flask import Flask, request, render_template, jsonify
from bs4 import BeautifulSoup
import requests, gspread, json, traceback
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(
    __name__,
    static_url_path="",
    static_folder="static",
    template_folder="templates",
)

SHEET_NAME = "Unscrambled Words"
GOOGLE_CREDS_PATH = "/etc/secrets/google_creds.json"

# ──────────────────────────────────────────────────────────
# Scraper
def scrape_words(rack: str) -> list[str]:
    url = f"https://www.allscrabblewords.com/unscramble/{rack.lower()}"
    html = requests.get(url, timeout=10).text
    soup = BeautifulSoup(html, "html.parser")

    raw = (
        a.text.strip().upper()
        for a in soup.select("div.panel-body.unscrambled li > a")
    )
    have = Counter(rack)
    return sorted({w for w in raw if len(w) >= 3 and not (Counter(w) - have)})


# ──────────────────────────────────────────────────────────
# Google-Sheets helpers
def _sheet(tab: str):
    with open("/etc/secrets/google_creds.json") as f:
        creds_dict = json.load(f)
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).worksheet(tab)


def log_words(words: set[str], tab: str):
    if not words:
        return
    try:
        _sheet(tab).append_rows([[w] for w in sorted(words)])
        print(f"✅ Logged {len(words)} to '{tab}'")
    except Exception as e:
        print(f"❌ Log failure ({tab}):", e)
        traceback.print_exc()


def get_tab_words(tab: str) -> set[str]:
    try:
        return {c.strip().upper() for c in _sheet(tab).col_values(1) if c.strip()}
    except Exception as e:
        print(f"❌ Load failure ({tab}):", e)
        traceback.print_exc()
        return set()


# ──────────────────────────────────────────────────────────
# HTML formatter
def format_groups(words: list[str], cols: int = 5) -> str:
    from collections import defaultdict

    groups = defaultdict(list)
    for w in words:
        groups[w[0]].append(w)

    lines = []

    # 🔥 1. Show 6- and 7-letter words first
    top_words = [w for w in words if len(w) in (6, 7)]
    if top_words:
        lines.append("🔥 Longest Words:\n")
        for i in range(0, len(top_words), cols):
            row = top_words[i:i+cols]
            line = " ".join(f'<span class="word" data-w="{w}">{w}</span>' for w in row)
            lines.append(f"     {line}")
        lines.append("")

    # 📦 2. Group everything except 3-letter words
    for idx, letter in enumerate(sorted(groups), 1):
        group = [w for w in groups[letter] if len(w) > 3]
        if not group:
            continue
        rows = [group[i:i+cols] for i in range(0, len(group), cols)]
        for r, row in enumerate(rows):
            prefix = f"{idx:>3}. {letter}: " if r == 0 else " " * (len(f"{idx:>3}. {letter}: "))
            line_body = " ".join(f'<span class="word" data-w="{w}">{w}</span>' for w in row)
            lines.append(prefix + line_body)
        lines.append("")

    # 👇 3. Always show 3-letter words last
    bottom_3 = [w for w in words if len(w) == 3]
    if bottom_3:
        lines.append("🔻 3-letter Words:\n")
        for i in range(0, len(bottom_3), cols):
            row = bottom_3[i:i+cols]
            line = " ".join(f'<span class="word" data-w="{w}">{w}</span>' for w in row)
            lines.append(f"     {line}")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api")
def api():
    rack = request.args.get("rack", "").strip().upper()
    if not rack:
        return jsonify(error="rack param missing"), 400

    # optional query additions
    req_whitelist = {
        w.strip().upper()
        for w in request.args.get("whitelist", "").split(",")
        if w.strip()
    }
    req_blacklist = {
        w.strip().upper()
        for w in request.args.get("blacklist", "").split(",")
        if w.strip()
    }

    # new: "X or more letters" filter — defaults to 3
    min_length_param = request.args.get("min_length", "3").strip()
    try:
        min_length = int(min_length_param)
    except ValueError:
        return jsonify(error="min_length must be a number"), 400

    # 1️⃣ scrape
    scraped = scrape_words(rack)
    log_words(set(scraped), "Unscrambled Words")

    # 2️⃣ persist any manual adds
    if req_whitelist:
        log_words(req_whitelist, "Whitelist")
    if req_blacklist:
        log_words(req_blacklist, "Blacklist")

    # 3️⃣ gather live lists
    live_blacklist = get_tab_words("Blacklist")
    live_whitelist = get_tab_words("Whitelist")

    # 4️⃣ whitelist words valid for this rack
    rack_counter = Counter(rack)
    valid_whitelist = {
        w
        for w in live_whitelist
        if len(w) >= 3 and not (Counter(w) - rack_counter)
    }

    # 5️⃣ build display set
    display_set = set(scraped)
    display_set.update(valid_whitelist)
    display_set.difference_update(live_blacklist)

    # 6️⃣ apply min_length filter
    display_words = sorted(w for w in display_set if len(w) >= min_length)

    return format_groups(display_words) or "(No 3+-letter anagrams)"


# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
