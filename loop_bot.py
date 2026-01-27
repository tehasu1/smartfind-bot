import os
import time
import http.client
import urllib.parse
import ssl
import re
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

def clean_text(text):
    """
    Takes messy text with newlines and double spaces and flattens it.
    Example: "Teacher   \n   \n  Math" -> "Teacher | Math"
    """
    if not text: return ""
    # Replace newlines with a pipe separator for readability
    text = text.replace("\n", " | ")
    # Collapse multiple spaces into one
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

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
            # Check for "No Jobs" sign
            body_text = page.locator("body").inner_text().lower()
            if "there are no jobs available" in body_text:
                print("   ✅ Clean scan (No jobs visible).")
                known_jobs.clear() 
                return

            # --- 4. ROW ANALYSIS ---
            print("   👀 Jobs detected. Cleaning data...")
            
            current_scan_signatures = set()
            new_jobs_found = []

            # Grab all table rows
            rows = page.locator("tr").all()
            
            for row in rows:
                raw_text = row.inner_text()
                cleaned = clean_text(raw_text)
                
                # --- FILTER TRASH ---
                # 1. Skip empty rows
                if len(cleaned) < 10: continue
                # 2. Skip Headers (Rows that contain "Date" and "Location" usually are headers)
                if "Date" in cleaned and "Location" in cleaned: continue
                # 3. Skip rows that don't have a number (Jobs ALWAYS have a date like 01/27 or a time like 8:00)
                if not re.search(r'\d', cleaned): continue
                
                # --- SAVE ---
                # Use the first 60 chars as the unique fingerprint
                fingerprint = cleaned[:60]
                current_scan_signatures.add(fingerprint)

                if fingerprint not in known_jobs:
                    print(f"   🚨 NEW LISTING: {cleaned[:40]}...")
                    new_jobs_found.append(cleaned)

            # --- NOTIFY ---
            if new_jobs_found:
                # Limit to 3 jobs per push so it doesn't get cut off
                display_jobs = new_jobs_found[:3]
                
                msg = f"🚨 {len(new_jobs_found)} NEW LISTING(S):\n"
                for job in display_jobs:
                    # formatting: Cut off at 100 chars to keep it readable
                    msg += f"🔹 {job[:100]}...\n"
                
                if len(new_jobs_found) > 3:
                    msg += f"plus {len(new_jobs_found)-3} more..."

                send_push(msg)
                known_jobs.update(current_scan_signatures)
            else:
                print(f"   🤫 Jobs present, but no new unique rows found.")

        except Exception as e:
            print(f"   ❌ Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    known_jobs = set()
    print("🤖 Bot Active. Clean Format Mode.")
    while True:
        run_check(known_jobs)
        time.sleep(60)