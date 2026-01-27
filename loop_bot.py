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

def parse_row_to_clean_string(row_element):
    """
    Extracts meaningful data from a row and formats it nicely.
    Returns None if the row is invalid/hidden.
    """
    # 1. VISIBILITY CHECK: Ignore hidden mobile-view rows
    if not row_element.is_visible():
        return None

    # Get all text pieces split by newline
    text_list = row_element.inner_text().split('\n')
    
    # Clean up whitespace and remove empty strings
    clean_items = [item.strip() for item in text_list if item.strip()]
    
    # Filter out common junk words
    clean_items = [x for x in clean_items if x not in ["Decline", "Accept", "Details", "Select"]]

    if not clean_items:
        return None

    # 2. DATA EXTRACTION
    # We try to identify parts based on your screenshot structure:
    # [Day, Date, Time, Name, Classification, Location]
    
    # Join everything first to search for patterns
    full_string = " ".join(clean_items)
    
    # If no numbers (dates/times) are present, it's not a job row
    if not re.search(r'\d', full_string):
        return None

    # Attempt to format nicely
    # We look for the date (MM/DD/YYYY)
    date_match = re.search(r'\d{2}/\d{2}/\d{4}', full_string)
    date_str = date_match.group(0) if date_match else "Unknown Date"

    # We try to create a readable summary
    # We remove the day/date from the list to avoid repetition, then join the rest
    # This is a heuristic; it formats: "Date | Rest of Info"
    formatted_msg = f"📅 {date_str}"
    
    # Add the rest of the info (Location, Class, etc.)
    # We skip the first few items if they look like dates/days to reduce clutter
    content_items = [x for x in clean_items if not re.search(r'\d{2}/\d{2}/\d{4}', x) and x not in ["Wednesday", "Thursday", "Friday", "Monday", "Tuesday"]]
    
    if content_items:
        formatted_msg += f" | {content_items[-1]}" # Location is usually last
        if len(content_items) > 1:
            formatted_msg += f" | {content_items[0]}" # Classification is usually first/middle

    return formatted_msg

def run_check(known_jobs):
    now = datetime.now().strftime("%I:%M %p")
    print(f"[{now}] 🚀 Scanning SmartFind...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--single-process"])
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        
        try:
            # --- 1. LOGIN ---
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

            # --- 2. GO TO JOB BOARD ---
            print("   ...Checking Job List")
            page.goto("https://westcontracosta.eschoolsolutions.com/ui/#/substitute/jobs/available", wait_until="networkidle")
            time.sleep(8)

            # --- 3. CHECK FOR NO JOBS ---
            if "there are no jobs available" in page.locator("body").inner_text().lower():
                print("   ✅ Clean scan (No jobs visible).")
                known_jobs.clear()
                return

            # --- 4. SMART ROW PARSING ---
            print("   👀 Jobs detected. Parsing rows...")
            
            new_jobs_found = []
            current_scan_signatures = set()

            rows = page.locator("tr").all()
            
            for row in rows:
                # Use our new smart parser
                clean_msg = parse_row_to_clean_string(row)
                
                if clean_msg:
                    # Create a simple signature to track duplicates
                    # We just use the full string as the ID
                    fingerprint = clean_msg
                    current_scan_signatures.add(fingerprint)

                    if fingerprint not in known_jobs:
                        print(f"   🚨 NEW LISTING: {clean_msg}")
                        new_jobs_found.append(clean_msg)

            # --- 5. NOTIFY ---
            if new_jobs_found:
                msg = f"🚨 {len(new_jobs_found)} NEW JOB(S):\n"
                for job in new_jobs_found:
                    msg += f"{job}\n"
                
                send_push(msg)
                known_jobs.update(current_scan_signatures)
            else:
                print(f"   🤫 Jobs present, but already notified.")

        except Exception as e:
            print(f"   ❌ Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    known_jobs = set()
    print("🤖 Bot Active. Smart-Parse Mode.")
    while True:
        run_check(known_jobs)
        time.sleep(60)