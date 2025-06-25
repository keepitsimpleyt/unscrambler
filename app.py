from collections import Counter, defaultdict
from flask import Flask, request, render_template, jsonify
from bs4 import BeautifulSoup
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import traceback

app = Flask(__name__,
            static_url_path="",
            static_folder="static",
            template_folder="templates")

SHEET_NAME = "Unscrambled Words"
GOOGLE_CREDS_PATH = "/etc/secrets/google_creds.json"

# --- Scraper ---
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
        if len(w) >= 3 and not (Counter(w) - have)
    }
    return sorted(words)

# --- Formatter for HTML display ---
def format_groups(words: list[str], cols: int = 5) -> str:
    groups = defaultdict(list)
    for w in words:
        groups[w[0]].append(w)

    lines = []
    for idx, letter in enumerate(sorted(groups), 1):
        rows = [groups[letter][i:i+cols] for i in range(0, len(groups[letter]), cols)]
        for r, row in enumerate(rows):
            prefix = f"{idx:>3}. {letter}: " if r == 0 else " " * (len(f"{idx:>3}. {letter}: "))
            line_body = " ".join(f'<span class="word" data-w="{w}">{w}</span>' for w in row)
            lines.append(prefix + line_body)
        lines.append("")
    return "\n".join(lines)

# --- Shared Google Sheets auth ---
def get_sheet(tab_name: str):
    with open("/etc/secrets/google_creds.json") as f:
        creds_dict = json.load(f)
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).worksheet(tab_name)

# --- Logger ---
def log_words_to_tab(words: set[str], tab_name: str):
    try:
        sheet = get_sheet(tab_name)
        sheet.append_rows([[w] for w in sorted(words)])
        print(f"✅ Logged {len(words)} to '{tab_name}' tab.")
    except Exception as e:
        print(f"❌ Failed to log to '{tab_name}' tab:", e)
        traceback.print_exc()

# --- Blacklist fetcher ---
def get_blacklist() -> set[str]:
    try:
        sheet = get_sheet("Blacklist")
        return {cell.strip().upper() for cell in sheet.col_values(1) if cell.strip()}
    except Exception as e:
        print("❌ Failed to load blacklist:", e)
        traceback.print_exc()
        return set()

# --- Routes ---
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api")
def api():
    rack = request.args.get("rack", "").strip().upper()
    if not rack:
        return jsonify(error="rack param missing"), 400

    whitelist_words = {
        w.strip().upper()
        for w in request.args.get("whitelist", "").split(",") if w.strip()
    }

    blacklist_words = {
        w.strip().upper()
        for w in request.args.get("blacklist", "").split(",") if w.strip()
    }

    # 1. Scrape
    scraped_words = scrape_words(rack)

    # 2. Log all scraped words to "Unscrambled Words"
    log_words_to_tab(set(scraped_words), "Unscrambled Words")

    # 3. Log manual whitelist/blacklist
    if whitelist_words:
        log_words_to_tab(whitelist_words, "Whitelist")
    if blacklist_words:
        log_words_to_tab(blacklist_words, "Blacklist")

    # 4. Filter for display only
    def get_whitelist() -> set[str]:
        try:
            sheet = get_sheet("Whitelist")
            return {cell.strip().upper() for cell in sheet.col_values(1) if cell.strip()}
        except Exception as e:
            print("❌ Failed to load whitelist:", e)
            traceback.print_exc()
            return set()

    # 4. Combine scraped + whitelisted, remove blacklisted
    live_blacklist = get_blacklist()
    live_whitelist = get_whitelist()
    combined_words = set(scraped_words).union(live_whitelist)
    display_words = sorted(w for w in combined_words if w not in live_blacklist)


    return format_groups(display_words) or "(No 3+-letter anagrams)"

# --- Local run ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
