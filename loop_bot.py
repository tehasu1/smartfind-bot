import os
import time
import http.client
import urllib.parse
import ssl
import re
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from datetime import datetime

load_dotenv()
SF_USERNAME = os.getenv("SF_USERNAME")
SF_PASSWORD = os.getenv("SF_PASSWORD")
PUSHOVER_USER = os.getenv("PUSHOVER_USER")
PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN")

def send_push(message):
    try:
        context = ssl._create_unverified_context()
        conn = http.client.HTTPSConnection("api.pushover.net:443", context=context)
        payload = urllib.parse.urlencode({
            "token": PUSHOVER_TOKEN,
            "user": PUSHOVER_USER,
            "message": message,
            "title": "SmartFind Bot"
        })
        conn.request("POST", "/1/messages.json", payload, {"Content-type": "application/x-www-form-urlencoded"})
        conn.getresponse()
    except:
        pass

def get_active_dates(page):
    print("   ...Checking Schedule for conflicts")
    blocked_dates = set()
    try:
        page.goto("https://westcontracosta.eschoolsolutions.com/ui/#/substitute/jobs/active", wait_until="networkidle")
        time.sleep(5)
        rows = page.locator("tr").all()
        for row in rows:
            if not row.is_visible(): continue
            text = row.inner_text()
            date_match = re.search(r'\d{2}/\d{2}/\d{4}', text)
            if date_match:
                blocked_dates.add(date_match.group(0))
    except Exception as e:
        print(f"   ⚠️ Could not load schedule: {e}")
    return blocked_dates

def parse_row_to_clean_string(row_element):
    if not row_element.is_visible(): return None, None
    text_list = row_element.inner_text().split('\n')
    clean_items = [item.strip() for item in text_list if item.strip()]
    clean_items = [x for x in clean_items if x not in ["Decline", "Accept", "Details", "Select"]]
    if not clean_items: return None, None
    full_string = " ".join(clean_items)
    if not re.search(r'\d', full_string): return None, None

    date_match = re.search(r'\d{2}/\d{2}/\d{4}', full_string)
    date_str = date_match.group(0) if date_match else "Unknown"

    time_matches = re.findall(r'\d{1,2}:\d{2}\s?[AP]M', full_string)
    time_display = ""
    if len(time_matches) >= 2:
        time_display = f"{time_matches[0]} - {time_matches[1]}"
    elif len(time_matches) == 1:
        time_display = time_matches[0]

    content_items = []
    for x in clean_items:
        if date_str in x: continue
        if x in time_matches: continue
        if x in ["Wednesday", "Thursday", "Friday", "Monday", "Tuesday", "Saturday", "Sunday"]: continue
        content_items.append(x)

    formatted_msg = f"📅 {date_str}"
    if content_items:
        formatted_msg += f" | 🏫 {content_items[-1]}"
    if time_display:
        formatted_msg += f" | ⏰ {time_display}"

    return formatted_msg, date_str

def run_check(known_jobs):
    now = datetime.now().strftime("%I:%M %p")
    print(f"[{now}] 🚀 Scanning SmartFind...")
    
    with sync_playwright() as p:
        # --- STABILITY UPDATE ---
        # Added args to prevent crashing in Docker/Railway
        browser = p.chromium.launch(
            headless=True, 
            args=[
                "--no-sandbox", 
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",  # Critical for preventing crashes
                "--disable-gpu",
                "--single-process"
            ]
        )
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        
        try:
            # 1. LOGIN
            print("   ...Logging in")
            page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitAction.do", wait_until="networkidle")
            try:
                page.locator("#userId").fill(SF_USERNAME, timeout=2000)
                page.locator("#userPin").fill(SF_PASSWORD, timeout=2000)
                page.locator("#userPin").press("Enter")
            except:
                for frame in page.frames:
                    try:
                        frame.locator("#userId").fill(SF_USERNAME, timeout=1000)
                        frame.locator("#userPin").fill(SF_PASSWORD, timeout=1000)
                        frame.locator("#userPin").press("Enter")
                        break
                    except: continue

            page.wait_for_load_state("networkidle")
            time.sleep(5) 

            # 2. GET BLOCKED DATES
            blocked_dates = get_active_dates(page)
            if blocked_dates:
                print(f"   🚫 Blocked Dates: {blocked_dates}")

            # 3. GO TO AVAILABLE JOBS
            print("   ...Checking Available Jobs")
            page.goto("https://westcontracosta.eschoolsolutions.com/ui/#/substitute/jobs/available", wait_until="networkidle")
            time.sleep(8)

            # 4. SCAN
            if "there are no jobs available" in page.locator("body").inner_text().lower():
                print("   ✅ Clean scan (No jobs visible).")
                known_jobs.clear()
                return

            print("   👀 Jobs detected. analyzing...")
            new_jobs_found = []
            current_scan_signatures = set()
            rows = page.locator("tr").all()
            
            for row in rows:
                clean_msg, job_date = parse_row_to_clean_string(row)
                if clean_msg:
                    fingerprint = clean_msg
                    
                    if job_date in blocked_dates:
                        print(f"      🔸 IGNORED (Conflict): {clean_msg}")
                        continue
                    
                    if fingerprint in known_jobs:
                        print(f"      🔸 IGNORED (Duplicate): {clean_msg}")
                        current_scan_signatures.add(fingerprint)
                        continue

                    print(f"   🚨 NEW LISTING: {clean_msg}")
                    new_jobs_found.append(clean_msg)
                    current_scan_signatures.add(fingerprint)

            if new_jobs_found:
                msg = f"🚨 {len(new_jobs_found)} NEW JOB(S):\n"
                for job in new_jobs_found:
                    msg += f"{job}\n"
                send_push(msg)
                known_jobs.update(current_scan_signatures)

        except Exception as e:
            print(f"   ❌ Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    known_jobs = set()
    print("🤖 Bot Active. Stability Mode.")
    while True:
        run_check(known_jobs)
        time.sleep(60)