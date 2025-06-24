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

# --- Config ---
SHEET_NAME = "Unscrambled Words"  # Must match your actual sheet name
GOOGLE_CREDS_PATH = "/etc/secrets/google_creds.json"

# --- Optional: Hard blacklist ---
HARD_BLACKLIST = {
    "PRE", "BUM"
}

# --- Word scraper from AllScrabbleWords ---
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
        if len(w) >= 3 and not (Counter(w) - have) and w not in HARD_BLACKLIST
    }
    return sorted(words)

# --- HTML formatter for frontend ---
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

# --- Google Sheets logger with full error reporting ---
def log_to_google_sheets(new_words: set[str]):
    try:
        with open("/etc/secrets/google_creds.json") as f:
            creds_dict = json.load(f)
    except Exception as e:
        print("❌ Could not load Google credentials:", e)
        traceback.print_exc()
        return

    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).sheet1

        existing = set(cell.upper() for cell in sheet.col_values(1) if cell.strip())
        words_to_add = sorted(w for w in new_words if w not in existing)

        if words_to_add:
            sheet.append_rows([[w] for w in words_to_add])
            print(f"✅ Logged {len(words_to_add)} new words to Google Sheets.")
        else:
            print("ℹ️ No new words to log.")
    except Exception as e:
        print("❌ Failed to log to Google Sheets:", e)
        traceback.print_exc()

# --- Routes ---
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

    # ✅ Attempt to log to Google Sheets
    log_to_google_sheets(set(words))

    return format_groups(words) or "(No 3+-letter anagrams)"

# --- Local run ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
