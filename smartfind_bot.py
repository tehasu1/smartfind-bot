import os
import time
import http.client
import urllib.parse
import ssl
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

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

def run_bot():
    print("🚀 SmartFind Bot Scanning...")
    
    with sync_playwright() as p:
        # Keep headless=False for now so you can verify it works
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # --- LOGIN ---
        try:
            print("🌐 Logging in...")
            page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitAction.do")
            
            frame = page.frames[0]
            frame.locator("#userId").wait_for(state="visible", timeout=10000)
            
            frame.locator("#userId").fill(SF_USERNAME, force=True)
            frame.locator("#userPin").fill(SF_PASSWORD, force=True)
            frame.locator("#userPin").press("Enter")
            
            page.wait_for_load_state('networkidle')
            
        except Exception as e:
            print(f"❌ Login Failed: {e}")
            return

        # --- CHECK JOBS ---
        try:
            print("🔍 Checking 'Available Jobs'...")
            
            # Click the tab
            page.locator("#available-tab-link").wait_for(state="visible", timeout=15000)
            page.locator("#available-tab-link").click()
            
            print("⏳ Reading the screen...")
            time.sleep(5) # Give the list time to appear
            
            # --- ROBUST TEXT CHECK ---
            # We grab the text from the main page AND the frame
            main_text = page.locator("body").inner_text().lower()
            
            # Try to get frame text too, just to be safe
            try:
                frame_text = page.frames[0].locator("body").inner_text().lower()
            except:
                frame_text = ""

            combined_text = main_text + " " + frame_text

            # The exact phrase we are looking for (in lowercase)
            target_phrase = "no jobs available"
            
            if target_phrase in combined_text:
                print(f"😴 Result: No jobs found. (Detected '{target_phrase}')")
            else:
                # Double Check: If we don't see "No Jobs", do we see "Date" or "Job ID"?
                if "date" in combined_text or "job" in combined_text or "location" in combined_text:
                    print("🚨 JOB DETECTED!")
                    send_push("🚨 JOBS AVAILABLE! Go to SmartFind now!")
                else:
                    # If we see NEITHER, print what we see so we can debug
                    print("⚠️ I am confused. I don't see 'No Jobs', but I don't see a list either.")
                    print(f"--- SCREEN TEXT DUMP ---\n{combined_text[:200]}...\n------------------------")
                    send_push("⚠️ Bot needs a checkup (False Positive suspected).")

        except Exception as e:
            print(f"⚠️ Error checking jobs: {e}")

        # Keep open briefly
        time.sleep(5)
        browser.close()
        print("✅ Scan complete.")

if __name__ == "__main__":
    run_bot()