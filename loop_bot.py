import os
import time
import re
import http.client
import urllib.parse
import ssl
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from datetime import datetime

# 1. Load secrets
load_dotenv()
SF_USERNAME = os.getenv("SF_USERNAME")
SF_PASSWORD = os.getenv("SF_PASSWORD")
PUSHOVER_USER = os.getenv("PUSHOVER_USER")
PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN")

def send_push(message):
    """Sends a notification to Pushover"""
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
        
        response = conn.getresponse()
        print(f"📲 PUSH RESULT: {response.status} {response.reason}")
    except Exception as e:
        print(f"❌ Push failed: {e}")

def get_active_job_ids(page):
    """
    Scrapes the page for unique Job IDs.
    Returns a SET of strings, e.g., {'392810', '492102'}
    """
    try:
        # Get all text from the main body and the frame
        main_text = page.locator("body").inner_text()
        try:
            frame_text = page.frames[0].locator("body").inner_text()
        except:
            frame_text = ""
        
        combined_text = (main_text + "\n" + frame_text)

        # CHECK 1: Is the list empty?
        if "no jobs available" in combined_text.lower():
            return set() # Return empty set

        # CHECK 2: Extract Job IDs
        # Looks for patterns like "Job ID: 123456" or "Job 123456"
        # \d{5,} means "look for 5 or more digits in a row" to avoid finding dates/times
        found_ids = set(re.findall(r"(?:Job|ID)\D{0,10}(\d{5,})", combined_text, re.IGNORECASE))
        
        # Fallback: If we see "Date/Location" but Regex found NO IDs, 
        # return a dummy ID so we still get an alert.
        if not found_ids and ("date" in combined_text.lower() or "location" in combined_text.lower()):
            return {"UNKNOWN_JOB"}

        return found_ids

    except Exception as e:
        print(f"   ⚠️ Error reading IDs: {e}")
        return set()

def run_bot():
    print("🤖 Bot is Online. Tracking unique Job IDs.")
    
    # MEMORY: Keeps track of jobs we already notified about
    # We start empty. The first scan will find existing jobs and notify.
    known_jobs = set()

    # Send startup test
    send_push("✅ Bot Online: Intelligent Job Tracking Active.")

    while True:
        now = datetime.now().strftime("%I:%M %p")
        print(f"[{now}] 🚀 Scanning SmartFind...")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            try:
                # --- LOGIN ---
                page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitAction.do")
                frame = page.frames[0]
                frame.locator("#userId").wait_for(state="visible", timeout=10000)
                frame.locator("#userId").fill(SF_USERNAME, force=True)
                frame.locator("#userPin").fill(SF_PASSWORD, force=True)
                frame.locator("#userPin").press("Enter")
                page.wait_for_load_state('networkidle')

                # --- NAVIGATE ---
                page.locator("#available-tab-link").wait_for(state="visible", timeout=15000)
                page.locator("#available-tab-link").click()
                time.sleep(15) # Wait for table to load
                
                # --- INTELLIGENT SCAN ---
                current_jobs = get_active_job_ids(page)
                
                if not current_jobs:
                    print(f"   ✅ Clean scan: No jobs found.")
                    # If list is empty, clear memory so we can re-alert if they come back later
                    known_jobs.clear()
                
                else:
                    # LOGIC: Find jobs that are in 'current' but NOT in 'known'
                    new_jobs = current_jobs - known_jobs
                    
                    if new_jobs:
                        print(f"   🚨 NEW JOBS DETECTED: {new_jobs}")
                        
                        if "UNKNOWN_JOB" in new_jobs:
                            msg = "🚨 JOBS AVAILABLE! (ID not read, check site!)"
                        else:
                            # Create a nice message like: "New Jobs: #12345, #67890"
                            ids_str = ", #".join(new_jobs)
                            msg = f"🚨 {len(new_jobs)} NEW JOBS: #{ids_str}"
                        
                        send_push(msg)
                        
                        # Add these new jobs to our memory
                        known_jobs.update(new_jobs)
                    else:
                        print(f"   🤫 Jobs present ({current_jobs}), but already notified.")

            except Exception as e:
                print(f"   ❌ Error during scan: {e}")

            browser.close()
        
        print("   ⏳ Sleeping for 60 seconds...\n")
        time.sleep(60)

if __name__ == "__main__":
    run_bot()