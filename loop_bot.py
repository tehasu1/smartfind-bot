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
    except Exception as e:
        print(f"❌ Push failed: {e}")

def get_active_job_ids(page):
    try:
        # Give the JS extra time to render the table
        time.sleep(10)
        
        # Pull text from everywhere
        main_text = page.locator("body").inner_text()
        frame_text = ""
        try:
            # SmartFind often uses frames; this targets the first child frame safely
            if len(page.frames) > 1:
                frame_text = page.frames[1].locator("body").inner_text()
        except:
            pass
            
        combined = (main_text + " " + frame_text).lower()
        
        if "no jobs available" in combined:
            return set()

        # Look for 6+ digit numbers (Job IDs)
        found_ids = set(re.findall(r"\b\d{6,10}\b", combined))
        # Filter out the year
        found_ids.discard("2026")
        return found_ids
    except Exception as e:
        print(f"   ⚠️ Scrape Error: {e}")
        return set()

def run_check(known_jobs):
    now = datetime.now().strftime("%I:%M %p")
    print(f"[{now}] 🚀 Scanning SmartFind...")
    
    with sync_playwright() as p:
        # --- THE FIX: LIGHTWEIGHT LAUNCH ---
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--no-zygote",
                "--single-process" # Reduces memory footprint significantly
            ]
        )
        # ----------------------------------
        
        context = browser.new_context()
        # Set a long timeout so it doesn't give up too fast
        context.set_default_timeout(60000) 
        page = context.new_page()
        
        try:
            # Login with a longer wait
            page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitAction.do", wait_until="networkidle", timeout=60000)
            
            frame = page.frames[0]
            frame.locator("#userId").wait_for(state="visible")
            frame.locator("#userId").fill(SF_USERNAME)
            frame.locator("#userPin").fill(SF_PASSWORD)
            frame.locator("#userPin").press("Enter")
            
            page.wait_for_load_state('networkidle')

            # Navigate to Jobs
            page.locator("#available-tab-link").wait_for(state="visible")
            page.locator("#available-tab-link").click()
            
            current_ids = get_active_job_ids(page)
            
            if not current_ids:
                print("   ✅ Clean scan.")
                known_jobs.clear()
            else:
                new_jobs = current_ids - known_jobs
                if new_jobs:
                    print(f"   🚨 NEW JOBS: {new_jobs}")
                    send_push(f"🚨 {len(new_jobs)} NEW JOBS: #{', #'.join(new_jobs)}")
                    known_jobs.update(new_jobs)
                else:
                    print(f"   🤫 Jobs present, already notified.")
                    
        except Exception as e:
            print(f"   ❌ Error during scan: {e}")
        finally:
            # ALWAYS close browser to free up RAM
            browser.close()

if __name__ == "__main__":
    print("🤖 Bot Online. Low-Memory Mode Active.")
    known_jobs = set()
    while True:
        run_check(known_jobs)
        print("   ⏳ Sleeping 60s...\n")
        time.sleep(60)