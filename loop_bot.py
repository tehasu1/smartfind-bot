import os
import time
import re
import http.client
import urllib.parse
import ssl
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

def run_check(known_jobs):
    now = datetime.now().strftime("%I:%M %p")
    print(f"[{now}] 🚀 Scanning SmartFind...")
    
    with sync_playwright() as p:
        # Launch with heavy anti-crash arguments
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox", "--single-process"])
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()
        
        try:
            # --- LOGIN ---
            print("   ...Logging in")
            page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitAction.do", wait_until="networkidle")
            
            # Handle Login Frame
            if page.frames:
                frame = page.frames[0]
                try:
                    frame.locator("#userId").fill(SF_USERNAME)
                    frame.locator("#userPin").fill(SF_PASSWORD)
                    frame.locator("#userPin").press("Enter")
                except:
                    # Sometimes the login is on the main page, not a frame
                    page.locator("#userId").fill(SF_USERNAME)
                    page.locator("#userPin").fill(SF_PASSWORD)
                    page.locator("#userPin").press("Enter")
            
            page.wait_for_load_state("networkidle")

            # --- CLICK 'AVAILABLE JOBS' ---
            print("   ...Navigating to Jobs Tab")
            # We force a click on the tab.
            # Note: We use a broad selector that finds the link by text "Available" if ID fails
            try:
                page.locator("#available-tab-link").click(timeout=5000)
            except:
                # Fallback: Try clicking by text
                page.get_by_text("Available Jobs").click()
                
            # Wait for the table to appear
            time.sleep(10)

            # --- DEBUG: WHAT DO WE SEE? ---
            # Grab text from ALL frames
            combined_text = page.locator("body").inner_text()
            for frame in page.frames:
                try:
                    combined_text += " " + frame.locator("body").inner_text()
                except:
                    pass
            
            combined_text = combined_text.lower()
            
            # *** PRINT THE EVIDENCE ***
            # This will show up in Railway logs so we know if we are on the right page
            print(f"   🔎 PAGE PREVIEW: {combined_text[:200]}...") 
            
            # --- FIND JOBS ---
            if "no jobs available" in combined_text:
                print("   ✅ Site explicitly says: 'No jobs available'")
                current_ids = set()
            else:
                # Broadest search possible: Any 6-10 digit number
                current_ids = set(re.findall(r"\b\d{6,10}\b", combined_text))
                current_ids.discard("2025")
                current_ids.discard("2026")
                
                # Filter out the user's own phone number/ID if it appears
                current_ids.discard(SF_USERNAME) 

            # --- NOTIFICATIONS ---
            if not current_ids:
                print(f"   ✅ Clean scan. (Found 0 IDs)")
                known_jobs.clear()
            else:
                new_jobs = current_ids - known_jobs
                if new_jobs:
                    print(f"   🚨 NEW JOBS FOUND: {new_jobs}")
                    send_push(f"🚨 FOUND {len(new_jobs)} JOBS: {', '.join(new_jobs)}")
                    known_jobs.update(new_jobs)
                else:
                    print(f"   🤫 Jobs present ({len(current_ids)}), already notified.")

        except Exception as e:
            print(f"   ❌ Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    known_jobs = set()
    print("🤖 Bot Active. DEBUG MODE.")
    send_push("Bot Restarted: Debug Mode")
    while True:
        run_check(known_jobs)
        time.sleep(60)