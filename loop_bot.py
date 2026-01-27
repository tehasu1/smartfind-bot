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
        # Force a large desktop window to ensure the sidebar/menu is visible
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        
        try:
            # --- LOGIN ---
            print("   ...Logging in")
            page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitAction.do", wait_until="networkidle")
            
            # Login (Handle main page vs frame)
            logged_in = False
            try:
                page.locator("#userId").fill(SF_USERNAME, timeout=2000)
                page.locator("#userPin").fill(SF_PASSWORD, timeout=2000)
                page.locator("#userPin").press("Enter")
                logged_in = True
            except:
                for frame in page.frames:
                    try:
                        frame.locator("#userId").fill(SF_USERNAME, timeout=1000)
                        frame.locator("#userPin").fill(SF_PASSWORD, timeout=1000)
                        frame.locator("#userPin").press("Enter")
                        logged_in = True
                        break
                    except: continue

            page.wait_for_load_state("networkidle")
            # WAIT EXTRA TIME FOR THE DASHBOARD TO LOAD
            time.sleep(8) 

            # --- NAVIGATION DIAGNOSTIC ---
            print("   ...Analyzing Dashboard Links")
            
            # 1. DUMP LINKS (Debug): What buttons can the bot actually see?
            all_links = []
            for frame in page.frames + [page]:
                try: 
                    links = frame.locator("a").all_inner_texts()
                    all_links.extend([l for l in links if l.strip()])
                except: pass
            
            # Print the first 5 links to see if we are on the right track
            print(f"   🔎 VISIBLE MENU ITEMS: {all_links[:5]}...")

            # --- NAVIGATION ATTEMPT ---
            print("   ...Attempting to Click 'Available Jobs'")
            clicked = False
            
            # Try 1: The ID '#available-tab-link'
            for frame in page.frames + [page]:
                if clicked: break
                try:
                    frame.locator("#available-tab-link").click(force=True, timeout=2000)
                    print("   👉 Clicked ID '#available-tab-link'")
                    clicked = True
                except: continue
            
            # Try 2: The Text "Available Jobs"
            if not clicked:
                for frame in page.frames + [page]:
                    if clicked: break
                    try:
                        frame.get_by_text("Available Jobs").click(force=True, timeout=2000)
                        print("   👉 Clicked text 'Available Jobs'")
                        clicked = True
                    except: continue

            # Try 3: The Text "Search" (Fallback)
            if not clicked:
                for frame in page.frames + [page]:
                    if clicked: break
                    try:
                        frame.get_by_text("Search").first.click(force=True, timeout=2000)
                        print("   👉 Clicked text 'Search'")
                        clicked = True
                    except: continue

            # WAIT FOR TABLE LOAD
            time.sleep(10)

            # --- VERIFY & SCAN ---
            combined_text = ""
            for frame in page.frames + [page]:
                try: combined_text += " " + frame.locator("body").inner_text()
                except: pass
            
            # Check if we are still on the profile page
            if "dates on your profile" in combined_text.lower():
                print("   ❌ STUCK: Still on Profile Page. Navigation failed.")
            else:
                print("   ✅ Navigation Successful (Profile text gone).")

            # FIND JOBS (6-digits)
            current_ids = set(re.findall(r"\b(\d{6})\b", combined_text))
            
            # Clean up junk
            for bad in ["2025", "2026", "1920", "1080", SF_USERNAME]:
                current_ids.discard(bad)

            if not current_ids:
                print("   ✅ Clean scan.")
                known_jobs.clear()
            else:
                new_jobs = current_ids - known_jobs
                if new_jobs:
                    print(f"   🚨 NEW JOBS: {new_jobs}")
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
    print("🤖 Bot Active. Navigation Diagnostics Mode.")
    while True:
        run_check(known_jobs)
        time.sleep(60)