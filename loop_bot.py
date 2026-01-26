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
        print(f"📲 PUSH SENT: {message}")
    except Exception as e:
        print(f"❌ Push failed: {e}")

def run_check():
    # Print current time
    now = datetime.now().strftime("%I:%M %p")
    print(f"[{now}] 🚀 Scanning SmartFind...")
    
    with sync_playwright() as p:
        # headless=True means INVISIBLE browser. Change to False if you want to see it.
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            # --- LOGIN ---
            page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitAction.do")
            
            frame = page.frames[0]
            # Wait for login box
            frame.locator("#userId").wait_for(state="visible", timeout=10000)
            
            frame.locator("#userId").fill(SF_USERNAME, force=True)
            frame.locator("#userPin").fill(SF_PASSWORD, force=True)
            frame.locator("#userPin").press("Enter")
            
            page.wait_for_load_state('networkidle')

            # --- CHECK JOBS ---
            # Click the tab
            page.locator("#available-tab-link").wait_for(state="visible", timeout=15000)
            page.locator("#available-tab-link").click()
            
            # Wait for text to load
            time.sleep(5) 
            
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
            else:
                # Double Check
                if "date" in combined_text or "job" in combined_text or "location" in combined_text:
                    print("   🚨 JOB DETECTED!")
                    send_push("🚨 JOBS AVAILABLE! Go to SmartFind now!")
                else:
                    print("   ⚠️ Scan ambiguous. No alert sent.")

        except Exception as e:
            print(f"   ❌ Error checking jobs: {e}")

        browser.close()

if __name__ == "__main__":
    print("🤖 Bot is Online. Press Ctrl+C to stop.")
    
    while True:
        run_check()
        print("   ⏳ Sleeping for 60 seconds...\n")
        time.sleep(60)