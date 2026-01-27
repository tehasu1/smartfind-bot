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

def attempt_login(page):
    print("   ...Logging in")
    page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitAction.do", wait_until="networkidle")
    
    # Try main page login first
    try:
        page.locator("#userId").fill(SF_USERNAME, timeout=2000)
        page.locator("#userPin").fill(SF_PASSWORD, timeout=2000)
        page.locator("#userPin").press("Enter")
        return
    except:
        pass

    # Try searching frames for login
    for frame in page.frames:
        try:
            frame.locator("#userId").fill(SF_USERNAME, timeout=1000)
            frame.locator("#userPin").fill(SF_PASSWORD, timeout=1000)
            frame.locator("#userPin").press("Enter")
            return
        except:
            continue

def navigate_to_jobs(page):
    print("   ...Hunting for Job Link")
    # Give the dashboard a moment to render
    page.wait_for_timeout(5000)
    
    clicked = False
    
    # METHOD 1: Look for the ID '#available-tab-link' in ALL FRAMES
    # This is the most reliable method if we can find it.
    for frame in page.frames + [page]:
        if clicked: break
        try:
            # We use force=True to bypass "element is hidden" checks
            link = frame.locator("#available-tab-link")
            if link.count() > 0:
                print("   👉 Found ID '#available-tab-link', clicking...")
                link.click(force=True, timeout=2000)
                clicked = True
                break
        except:
            continue

    # METHOD 2: Look for text "Job Search" or "Available Jobs"
    if not clicked:
        print("   ⚠️ ID not found. Trying text search...")
        for frame in page.frames + [page]:
            if clicked: break
            try:
                # Try explicit text match
                frame.get_by_text("Job Search").click(force=True, timeout=1000)
                print("   👉 Clicked text 'Job Search'")
                clicked = True
            except:
                try:
                    frame.get_by_text("Available Jobs").click(force=True, timeout=1000)
                    print("   👉 Clicked text 'Available Jobs'")
                    clicked = True
                except:
                    continue
    
    if not clicked:
        print("   ❌ CRITICAL: Could not find any navigation link.")
        # DEBUG: Print all links found to see what is actually there
        print("   🔎 DUMPING ALL LINKS ON PAGE:")
        links = page.locator("a").all_inner_texts()
        print(links[:20]) # Show first 20 links

def run_check(known_jobs):
    now = datetime.now().strftime("%I:%M %p")
    print(f"[{now}] 🚀 Scanning SmartFind...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--single-process"])
        # Use Desktop Viewport to prevent "Hamburger Menu" hiding links
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        
        try:
            attempt_login(page)
            page.wait_for_load_state("networkidle")
            
            navigate_to_jobs(page)
            
            # Wait for table
            time.sleep(8)

            # --- PREVIEW & SCAN ---
            combined_text = ""
            for frame in page.frames + [page]:
                try: combined_text += " " + frame.locator("body").inner_text().lower()
                except: pass

            # DEBUG: Did we make it?
            if "job search" in combined_text or "available jobs" in combined_text:
                print("   ✅ Navigation seems successful.")
            else:
                print(f"   🔎 Current View: {combined_text[:100]}...")

            # Regex Scan
            current_ids = set(re.findall(r"\b\d{6,10}\b", combined_text))
            for bad in ["2025", "2026", SF_USERNAME, "0423", "1080", "1920"]:
                current_ids.discard(bad)

            if not current_ids:
                print("   ✅ Clean scan.")
                known_jobs.clear()
            else:
                new_jobs = current_ids - known_jobs
                if new_jobs:
                    print(f"   🚨 NEW JOBS: {new_jobs}")
                    send_push(f"🚨 {len(new_jobs)} NEW JOBS: #{', #'.join(new_jobs)}")
                    known_jobs.update(new_jobs)
                else:
                    print(f"   🤫 Jobs present, already notified.")

        except Exception as e:
            print(f"   ❌ Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    known_jobs = set()
    print("🤖 Bot Active. 'Search & Destroy' Mode.")
    while True:
        run_check(known_jobs)
        time.sleep(60)