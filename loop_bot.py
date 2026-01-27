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
        # Launch with options to prevent crashing
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--single-process"])
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()
        
        try:
            # --- LOGIN ---
            print("   ...Logging in")
            page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitAction.do", wait_until="networkidle")
            
            # Try filling login in main page first, then frame if needed
            try:
                page.locator("#userId").fill(SF_USERNAME, timeout=2000)
                page.locator("#userPin").fill(SF_PASSWORD, timeout=2000)
                page.locator("#userPin").press("Enter")
            except:
                if page.frames:
                    frame = page.frames[0]
                    frame.locator("#userId").fill(SF_USERNAME)
                    frame.locator("#userPin").fill(SF_PASSWORD)
                    frame.locator("#userPin").press("Enter")
            
            page.wait_for_load_state("networkidle")

            # --- SMART NAVIGATION (The Fix) ---
            print("   ...Looking for Job Link")
            
            # Strategy: Click the text "Available Jobs" directly
            # If that fails, try "Job Search" (which showed up in your logs)
            try:
                # Try specific tab first
                page.get_by_role("link", name="Available Jobs").click(timeout=5000)
                print("   ✅ Clicked 'Available Jobs' link")
            except:
                try:
                    # Fallback to general search text
                    page.get_by_text("Job Search").click(timeout=5000)
                    print("   ✅ Clicked 'Job Search' text")
                except:
                    # Last resort: Try the 'Search' button often found in header
                    page.get_by_role("link", name="Search").first.click(timeout=5000)
                    print("   ✅ Clicked generic 'Search' link")

            # Wait for the table to actually appear
            time.sleep(10)

            # --- PREVIEW CHECK ---
            combined_text = page.locator("body").inner_text().lower()
            for frame in page.frames:
                try: combined_text += " " + frame.locator("body").inner_text().lower()
                except: pass

            # Print a snippet to verify we are on the right page now
            print(f"   🔎 NEW PREVIEW: {combined_text[:150]}...")

            # --- FIND IDS ---
            # Search for 6-10 digit job numbers
            current_ids = set(re.findall(r"\b\d{6,10}\b", combined_text))
            
            # Cleanup common false positives
            for bad_num in ["2025", "2026", "0423", "1280", "800", SF_USERNAME]:
                current_ids.discard(bad_num)

            if not current_ids:
                # Only trust "Clean Scan" if we see the words "no jobs" or "list"
                if "no jobs" in combined_text or "list" in combined_text or "search results" in combined_text:
                    print("   ✅ Verified Empty List.")
                    known_jobs.clear()
                else:
                    print("   ⚠️ Scan ambiguous (Might still be on wrong page).")
            else:
                new_jobs = current_ids - known_jobs
                if new_jobs:
                    print(f"   🚨 NEW JOBS: {new_jobs}")
                    send_push(f"🚨 FOUND {len(new_jobs)} JOBS: {', '.join(new_jobs)}")
                    known_jobs.update(new_jobs)
                else:
                    print(f"   🤫 Jobs present, already notified.")

        except Exception as e:
            print(f"   ❌ Navigation Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    known_jobs = set()
    print("🤖 Bot Active. Navigation Fix Applied.")
    while True:
        run_check(known_jobs)
        time.sleep(60)