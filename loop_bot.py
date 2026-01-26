import os
import time
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
    """Sends a notification with detailed error logging"""
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
        
        if response.status != 200:
            print(f"⚠️ Pushover Error Details: {response.read().decode()}")

    except Exception as e:
        print(f"❌ Push failed: {e}")

def check_for_jobs():
    """
    Returns TRUE if jobs are found, FALSE if no jobs.
    Does not handle notifications itself anymore.
    """
    # Print current time
    now = datetime.now().strftime("%I:%M %p")
    print(f"[{now}] 🚀 Scanning SmartFind...")
    
    jobs_found = False # Default to False

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

            # --- CHECK JOBS ---
            page.locator("#available-tab-link").wait_for(state="visible", timeout=15000)
            page.locator("#available-tab-link").click()
            
            time.sleep(15) # Wait for load
            
            # --- ROBUST TEXT CHECK ---
            main_text = page.locator("body").inner_text().lower()
            try:
                frame_text = page.frames[0].locator("body").inner_text().lower()
            except:
                frame_text = ""
            
            combined_text = main_text + " " + frame_text
            target_phrase = "no jobs available"
            
            if target_phrase in combined_text:
                print(f"   ✅ Clean scan: No jobs found.")
                jobs_found = False
            else:
                # Double Check
                if "date" in combined_text or "job" in combined_text or "location" in combined_text:
                    print("   🚨 JOB DETECTED (Scan Positive)")
                    jobs_found = True
                else:
                    print("   ⚠️ Scan ambiguous. Assuming no jobs.")
                    jobs_found = False

        except Exception as e:
            print(f"   ❌ Error checking jobs: {e}")
            # If error, assume False to be safe/avoid spam
            jobs_found = False

        browser.close()
        return jobs_found

if __name__ == "__main__":
    print("🤖 Bot is Online. Press Ctrl+C to stop.")
    
    # --- STARTUP TEST ---
    print("📲 Sending Startup Test...")
    send_push("✅ Bot Online: Anti-Spam Mode Active.")
    # --------------------

    # State Variable: Remembers if we already yelled about the current job
    already_alerted = False

    while True:
        # Run the check and get the result (True/False)
        has_jobs = check_for_jobs()

        if has_jobs:
            if already_alerted:
                # We saw this job last time. Stay silent.
                print("   🤫 Jobs still there. Keeping quiet.")
            else:
                # NEW JOB DETECTED! Send the alert.
                send_push("🚨 JOBS AVAILABLE! Go to SmartFind now!")
                already_alerted = True # Mark as "Seen"
        else:
            # No jobs found. Reset the flag.
            # Next time a job appears, it will be treated as "New".
            already_alerted = False

        print("   ⏳ Sleeping for 60 seconds...\n")
        time.sleep(60)