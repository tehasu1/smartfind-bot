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

            # --- 3. INTELLIGENT SCAN ---
            # Check if the "No Jobs" message exists
            body_text = page.locator("body").inner_text().lower()
            if "there are no jobs available" in body_text:
                print("   ✅ Clean scan (No jobs visible).")
                known_jobs.clear() # Clear memory so we re-notify if a job leaves and comes back
                return

            # IF WE ARE HERE, JOBS EXIST.
            # We need to find the rows to avoid duplicate alerts.
            print("   👀 Jobs detected. Analyzing rows...")
            
            current_scan_signatures = set()
            new_jobs_found = []

            # Grab all table rows (tr)
            rows = page.locator("tr").all()
            
            for row in rows:
                text = row.inner_text().strip()
                # Skip headers and empty rows
                if not text or "Date" in text or "Classification" in text:
                    continue
                
                # Create a "Fingerprint" (The unique text of this job)
                # We use the first 50 chars which usually contains Date/Time/Location
                fingerprint = text[:50]
                current_scan_signatures.add(fingerprint)

                # Check if we already know this job
                if fingerprint not in known_jobs:
                    print(f"   🚨 NEW LISTING: {text[:40]}...")
                    new_jobs_found.append(text)
            
            # Update our memory
            # We add the new ones to known_jobs
            # We DO NOT clear known_jobs here, so we remember them next loop
            if new_jobs_found:
                # Create a nice message for the push notification
                msg = f"🚨 {len(new_jobs_found)} NEW JOB(S)!\n"
                for job in new_jobs_found:
                    msg += f"- {job[:100]}...\n" # First 100 chars of details
                
                send_push(msg)
                known_jobs.update(current_scan_signatures)
            else:
                print(f"   🤫 Jobs are present, but we already notified you about them.")

        except Exception as e:
            print(f"   ❌ Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    # This set lives in memory and remembers jobs between scans
    known_jobs = set()
    print("🤖 Bot Active. Duplicate Protection Enabled.")
    while True:
        run_check(known_jobs)
        time.sleep(60)