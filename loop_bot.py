import os
import time
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

def run_check():
    now = datetime.now().strftime("%I:%M %p")
    print(f"[{now}] 🚀 Scanning SmartFind (Modern UI)...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--single-process"])
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        
        try:
            # --- 1. LOGIN ---
            print("   ...Logging in")
            # We still login at the standard portal
            page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitAction.do", wait_until="networkidle")
            
            try:
                page.locator("#userId").fill(SF_USERNAME, timeout=2000)
                page.locator("#userPin").fill(SF_PASSWORD, timeout=2000)
                page.locator("#userPin").press("Enter")
            except:
                # Fallback for frames
                for frame in page.frames:
                    try:
                        frame.locator("#userId").fill(SF_USERNAME, timeout=1000)
                        frame.locator("#userPin").fill(SF_PASSWORD, timeout=1000)
                        frame.locator("#userPin").press("Enter")
                        break
                    except: continue

            # Wait for login to complete
            page.wait_for_load_state("networkidle")
            time.sleep(5) 

            # --- 2. GO TO MODERN DASHBOARD ---
            print("   ...Loading Job Board")
            # This is the specific URL you provided
            page.goto("https://westcontracosta.eschoolsolutions.com/ui/#/substitute/jobs/available", wait_until="networkidle")
            
            # SPAs (Single Page Apps) take a moment to "build" the page after loading
            time.sleep(8)

            # --- 3. CHECK FOR THE "NO JOBS" SIGN ---
            combined_text = page.locator("body").inner_text().lower()
            
            # The specific phrase from your screenshot
            no_jobs_marker = "there are no jobs available"
            
            if "dates on your profile" in combined_text and "job search" not in combined_text:
                 print("   ❌ STUCK: Login might have failed or redirected to profile.")
                 return

            if no_jobs_marker in combined_text:
                print("   ✅ Clean scan (Found 'No jobs' message).")
            else:
                # IF THE MESSAGE IS GONE, SEND ALERT
                print("   🚨 ALERT: The 'No Jobs' message is missing!")
                
                # Try to grab a snippet of text for the notification
                # In the modern UI, job cards usually have a 'Date' or 'Location' label
                preview = "Check SmartFind immediately!"
                try:
                    # Look for the first bold text or list item
                    preview = page.locator(".job-list-item").first.inner_text().replace("\n", " ")[:100]
                except:
                    pass

                send_push(f"🚨 JOB DETECTED: {preview}")

        except Exception as e:
            print(f"   ❌ Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    print("🤖 Bot Active. Modern UI Mode.")
    while True:
        run_check()
        time.sleep(60)