import os
import time
import http.client
import urllib.parse
import ssl
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# 1. Load all secrets
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

def run_alpha_bot():
    print("🚀 Starting Alpha Bot...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        print("🌐 Navigating...")
        page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitAction.do")
        
        # --- STEP 1: LOGIN ---
        try:
            # We stick with the Frame logic because we know it works for the login screen
            frame = page.frames[0]
            print("⚡️ Waiting for login box...")
            frame.locator("#userId").wait_for(state="visible", timeout=10000)
            
            print("🔑 Logging in...")
            frame.locator("#userId").fill(SF_USERNAME, force=True)
            frame.locator("#userPin").fill(SF_PASSWORD, force=True)
            frame.locator("#userPin").press("Enter")
            
            # Wait for the page to reload into the Dashboard
            print("⏳ Waiting for Dashboard to load...")
            page.wait_for_load_state('networkidle')
            
        except Exception as e:
            print(f"❌ CRASHED during Login: {e}")
            return

        # --- STEP 2: CLICK "AVAILABLE JOBS" ---
        print("🔍 Looking for 'Available Jobs' tab (#available-tab-link)...")
        try:
            # 1. Wait for the tab to actually appear
            # We don't use the frame here because usually the dashboard is the main page
            page.locator("#available-tab-link").wait_for(state="visible", timeout=15000)
            
            # 2. Click it
            print("👇 Clicking 'Available Jobs'...")
            page.locator("#available-tab-link").click()
            
            # 3. Wait for the jobs to load
            print("⏳ Waiting for job list...")
            time.sleep(5)
            
            # 4. VERIFICATION
            # After clicking, we expect to see a "Search" button or list of jobs
            content = page.content()
            if "Search" in content or "Job" in content:
                print("✅ WE ARE ON THE JOBS PAGE!")
                send_push("✅ Bot Success: I am looking at the Job List.")
            else:
                print("⚠️ I clicked the tab, but I'm not sure if the list loaded.")

        except Exception as e:
            print(f"❌ Failed to click the tab: {e}")
            print("Debug: Dumping page content to see what's wrong...")
            # print(page.content()) # Uncomment if you need to debug deeply

        print("👀 Keeping open for 10 seconds...")
        time.sleep(10)
        browser.close()

if __name__ == "__main__":
    run_alpha_bot()