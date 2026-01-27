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
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--single-process"])
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        
        try:
            # --- LOGIN ---
            print("   ...Logging in")
            page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitAction.do", wait_until="networkidle")
            
            # Login Logic (Try main page + frames)
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

            # --- NAVIGATE ---
            print("   ...Hunting for Job Link")
            page.wait_for_timeout(5000)
            
            clicked = False
            for frame in page.frames + [page]:
                if clicked: break
                try:
                    frame.locator("#available-tab-link").click(force=True, timeout=2000)
                    clicked = True
                except:
                    try: 
                        frame.get_by_text("Job Search").click(force=True, timeout=1000)
                        clicked = True
                    except: continue
            
            time.sleep(10) # Wait for table to load

            # --- EXTRACT TEXT ---
            combined_text = ""
            for frame in page.frames + [page]:
                try: combined_text += " " + frame.locator("body").inner_text()
                except: pass
            
            # --- DEBUG: WHAT DOES THE BOT SEE? ---
            # If we find nothing, this log will tell us if we are on the wrong page
            print(f"   🔎 RAW TEXT SAMPLE: {combined_text[:100].replace(chr(10), ' ')}...")

            # --- BROAD SEARCH (Removed the '#' requirement) ---
            # Look for ANY 6-digit number
            current_ids = set(re.findall(r"\b(\d{6})\b", combined_text))
            
            # Filter out junk (Years, User ID, common pixel widths)
            for bad in ["2025", "2026", "1920", "1080", SF_USERNAME]:
                current_ids.discard(bad)

            if not current_ids:
                print("   ✅ Clean scan (No 6-digit numbers found).")
                known_jobs.clear()
            else:
                new_jobs = current_ids - known_jobs
                if new_jobs:
                    print(f"   🚨 NEW JOBS: {new_jobs}")
                    # We manually add the '#' back for the notification text so it looks nice
                    formatted_ids = [f"#{jid}" for jid in new_jobs]
                    send_push(f"🚨 {len(new_jobs)} JOBS FOUND: {', '.join(formatted_ids)}")
                    known_jobs.update(new_jobs)
                else:
                    print(f"   🤫 Jobs present ({len(current_ids)}), already notified.")

        except Exception as e:
            print(f"   ❌ Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    known_jobs = set()
    print("🤖 Bot Active. Broad Search Mode.")
    while True:
        run_check(known_jobs)
        time.sleep(60)