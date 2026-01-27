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
            time.sleep(8) 

            # --- GOD MODE NAVIGATION ---
            print("   ...Injecting JavaScript Click")
            
            navigated = False
            
            # STRATEGY: Execute raw JavaScript inside every frame
            # This bypasses "visibility" checks and forces the event.
            for frame in page.frames + [page]:
                if navigated: break
                try:
                    # 1. Try to click the ID '#available-tab-link' using internal JS
                    # This is much stronger than page.click()
                    frame.evaluate("document.getElementById('available-tab-link').click()")
                    print("   👉 JS Injection: Triggered '#available-tab-link'")
                    navigated = True
                except:
                    # 2. Try to find the link by text content via JS (XPath equivalent)
                    try:
                        frame.evaluate("""
                            const links = document.querySelectorAll('a');
                            for (let link of links) {
                                if (link.innerText.includes('Available Jobs')) {
                                    link.click();
                                    break;
                                }
                            }
                        """)
                        print("   👉 JS Injection: Triggered Text Match 'Available Jobs'")
                        navigated = True
                    except: continue

            # Wait to see if the page reacted
            time.sleep(10)

            # --- VERIFY ---
            combined_text = ""
            for frame in page.frames + [page]:
                try: combined_text += " " + frame.locator("body").inner_text()
                except: pass
            
            if "dates on your profile" in combined_text.lower():
                print("   ❌ STUCK on Profile. JS Click failed.")
            else:
                print("   ✅ SUCCESS: Profile text gone. We are on the Jobs List.")

            # --- SCAN ---
            # Look for 6 digit numbers
            current_ids = set(re.findall(r"\b(\d{6})\b", combined_text))
            
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
    print("🤖 Bot Active. JS Injection Mode.")
    while True:
        run_check(known_jobs)
        time.sleep(60)