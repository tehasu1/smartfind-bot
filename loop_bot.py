import os
import time
import http.client
import urllib.parse
import ssl
import re
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta

load_dotenv()
SF_USERNAME = os.getenv("SF_USERNAME")
SF_PASSWORD = os.getenv("SF_PASSWORD")
PUSHOVER_USER = os.getenv("PUSHOVER_USER")
PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN")

# --- 🎛️ CONTROL PANEL ---

# 1. MASTER SWITCH
# True = Hunter Mode (Auto-Accepts jobs).
# False = Watcher Mode (Only notifies you).
AUTO_ACCEPT_ENABLED = True 

# 2. BLACKOUT SETTINGS 🚫
# A. Single Days (e.g. random doctor appointments)
MANUAL_BLACKOUT_DATES = [
    # "02/14/2026", 
]

# B. Date Range (e.g. Vacations) - MM/DD/YYYY
# Set to None if you don't have a vacation planned.
BLACKOUT_RANGE_START = "03/23/2026"
BLACKOUT_RANGE_END   = "05/10/2026"

# 3. STRICT HIGH SCHOOL LIST
AUTO_ACCEPT_SCHOOLS = [
    "EL CERRITO HIGH",
    "RICHMOND HIGH SCHOOL",
    "PINOLE HIGH SCHOOL",
    "KENNEDY HIGH",
    "DE ANZA HIGH",
    "HERCULES HIGH SCHOOL"
]

# 4. SETTINGS
AUTO_ACCEPT_START_HOUR = 6     # 6:00 AM
AUTO_ACCEPT_END_HOUR = 22      # 10:00 PM
AUTO_ACCEPT_MIN_HOURS = 6.0    # Minimum shift duration

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

def get_active_dates(page):
    """Scrapes schedule AND generates blackout dates from the control panel."""
    print("   ...Checking Schedule for conflicts")
    blocked_dates = set()
    
    # 1. Add Single Manual Dates
    for date in MANUAL_BLACKOUT_DATES:
        blocked_dates.add(date)

    # 2. Add Date Range (Vacation Mode)
    if BLACKOUT_RANGE_START and BLACKOUT_RANGE_END:
        try:
            start = datetime.strptime(BLACKOUT_RANGE_START, "%m/%d/%Y")
            end = datetime.strptime(BLACKOUT_RANGE_END, "%m/%d/%Y")
            delta = end - start
            for i in range(delta.days + 1):
                day = start + timedelta(days=i)
                blocked_dates.add(day.strftime("%m/%d/%Y"))
            print(f"   🏖️ Vacation Mode: Blocking {delta.days + 1} days ({BLACKOUT_RANGE_START} - {BLACKOUT_RANGE_END})")
        except ValueError:
            print("   ⚠️ Error: Check your Blackout Date formats (MM/DD/YYYY)")

    # 3. Add Scraped Dates from Website
    try:
        page.goto("https://westcontracosta.eschoolsolutions.com/ui/#/substitute/jobs/active", wait_until="networkidle")
        time.sleep(5)
        rows = page.locator("tr").all()
        for row in rows:
            if not row.is_visible(): continue
            text = row.inner_text()
            date_match = re.search(r'\d{2}/\d{2}/\d{4}', text)
            if date_match:
                blocked_dates.add(date_match.group(0))
    except Exception as e:
        print(f"   ⚠️ Could not load schedule: {e}")
        
    return blocked_dates

def attempt_auto_accept(page, row_element, job_details):
    """
    COMBAT MODE: Repeats the accept/confirm cycle until the job is secured.
    """
    print(f"   ⚔️ ENGAGING COMBAT MODE for: {job_details}")
    
    attempt_count = 0
    max_attempts = 30 
    
    while row_element.is_visible() and attempt_count < max_attempts:
        attempt_count += 1
        print(f"      👊 Attempt {attempt_count}/{max_attempts}...")

        try:
            # 1. Click Green Checkmark
            accept_btn = row_element.locator("td").last.locator("a, button, i").first
            if accept_btn.is_visible():
                accept_btn.click()
            else:
                print("      ❌ Green button disappeared.")
                return False 

            # 2. Click Confirm (The Popup)
            try:
                confirm_btn = page.get_by_role("button", name="Confirm")
                confirm_btn.wait_for(state="visible", timeout=1500)
                confirm_btn.click()
                print("      👉 Clicked 'Confirm'")
            except:
                print("      ⚠️ Popup failed to appear/click. Retrying cycle...")
                continue 

            # 3. Check for the Red "Held by System" Banner
            time.sleep(1.5)
            red_banner = page.get_by_text("substitute called by the system")
            
            if red_banner.is_visible():
                print("      ⛔ BLOCKED: Job held by system. Mashing again in 1s...")
                continue
            
            # 4. Check Success
            if not row_element.is_visible():
                print("      ✨ Job row vanished. Assuming VICTORY.")
                return True
            
            print("      ❓ Row still visible, no error. Clicking again to be sure.")

        except Exception as e:
            print(f"      ⚠️ Combat Loop Error: {e}")
            time.sleep(1)

    if attempt_count >= max_attempts:
        print("      ❌ Max attempts reached. Walking away.")
        return False

    return True

def parse_row_to_clean_string(row_element):
    """Returns: (formatted_msg, date_str, duration_hours)"""
    if not row_element.is_visible(): return None, None, 0
    text_list = row_element.inner_text().split('\n')
    clean_items = [item.strip() for item in text_list if item.strip()]
    clean_items = [x for x in clean_items if x not in ["Decline", "Accept", "Details", "Select"]]
    if not clean_items: return None, None, 0
    full_string = " ".join(clean_items)
    if not re.search(r'\d', full_string): return None, None, 0

    date_match = re.search(r'\d{2}/\d{2}/\d{4}', full_string)
    date_str = date_match.group(0) if date_match else "Unknown"

    # --- TIME & DURATION ---
    time_matches = re.findall(r'\d{1,2}:\d{2}\s?[AP]M', full_string)
    time_display = ""
    duration = 0.0

    if len(time_matches) >= 2:
        start_str = time_matches[0]
        end_str = time_matches[1]
        time_display = f"{start_str} - {end_str}"
        try:
            fmt = "%I:%M %p"
            t1 = datetime.strptime(start_str, fmt)
            t2 = datetime.strptime(end_str, fmt)
            diff = t2 - t1
            duration = diff.total_seconds() / 3600.0
        except:
            duration = 0.0
    elif len(time_matches) == 1:
        time_display = time_matches[0]

    # --- CONTENT EXTRACTION ---
    content_items = []
    for x in clean_items:
        if date_str in x: continue
        if x in time_matches: continue
        if x in ["Wednesday", "Thursday", "Friday", "Monday", "Tuesday", "Saturday", "Sunday"]: continue
        content_items.append(x)

    formatted_msg = f"📅 {date_str}"
    if content_items:
        formatted_msg += f" | 🏫 {content_items[-1]}"
    if time_display:
        formatted_msg += f" | ⏰ {time_display}"

    return formatted_msg, date_str, duration

def run_check(known_jobs):
    now = datetime.now()
    current_hour = now.hour
    print(f"[{now.strftime('%I:%M %p')}] 🚀 Scanning SmartFind...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, 
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--single-process"]
        )
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        
        try:
            # 1. LOGIN
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

            # 2. GET BLOCKED DATES (Web Schedule + Manual Range)
            blocked_dates = get_active_dates(page)

            # 3. GO TO AVAILABLE JOBS
            print("   ...Checking Available Jobs")
            page.goto("https://westcontracosta.eschoolsolutions.com/ui/#/substitute/jobs/available", wait_until="networkidle")
            time.sleep(8)

            # 4. SCAN
            if "there are no jobs available" in page.locator("body").inner_text().lower():
                print("   ✅ Clean scan (No jobs visible).")
                known_jobs.clear()
                return

            print("   👀 Jobs detected. Analyzing...")
            new_jobs_found = []
            current_scan_signatures = set()
            rows = page.locator("tr").all()
            
            for row in rows:
                clean_msg, job_date, duration = parse_row_to_clean_string(row)
                if clean_msg:
                    fingerprint = clean_msg
                    
                    if job_date in blocked_dates:
                        print(f"      🔸 IGNORED (Conflict/Blackout): {clean_msg}")
                        continue
                    
                    if fingerprint in known_jobs:
                        current_scan_signatures.add(fingerprint)
                        continue

                    # --- ⚡ AUTO-ACCEPT LOGIC ---
                    accepted = False
                    if AUTO_ACCEPT_ENABLED:
                        if AUTO_ACCEPT_START_HOUR <= current_hour < AUTO_ACCEPT_END_HOUR:
                            # 1. Check School Name
                            is_green_list = any(school.upper() in clean_msg.upper() for school in AUTO_ACCEPT_SCHOOLS)
                            
                            # 2. Check Duration
                            is_long_enough = duration >= AUTO_ACCEPT_MIN_HOURS
                            
                            if is_green_list and is_long_enough:
                                success = attempt_auto_accept(page, row, clean_msg)
                                if success:
                                    send_push(f"🎉 SECURED JOB ({duration}h): {clean_msg}")
                                    accepted = True
                                    blocked_dates.add(job_date)
                                else:
                                    send_push(f"⚠️ LOST FIGHT FOR: {clean_msg}")
                            else:
                                if not is_green_list:
                                    print(f"      🔸 Skipped (Not High School)")
                                elif not is_long_enough:
                                    print(f"      🔸 Skipped (Too Short: {duration}h)")
                        else:
                            print(f"      🔸 Skipped (Outside Hours)")
                    else:
                        print("      🔸 Skipped (Auto-Accept Disabled)")

                    if not accepted:
                        print(f"   🚨 NEW LISTING: {clean_msg}")
                        new_jobs_found.append(clean_msg)
                        current_scan_signatures.add(fingerprint)

            if new_jobs_found:
                msg = f"🚨 {len(new_jobs_found)} NEW JOB(S):\n"
                for job in new_jobs_found:
                    msg += f"{job}\n"
                send_push(msg)
                known_jobs.update(current_scan_signatures)

        except Exception as e:
            print(f"   ❌ Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    known_jobs = set()
    print("🤖 Bot Active. VACATION MODE ENABLED 🏖️")
    print(f"   🚫 Blackout Range: {BLACKOUT_RANGE_START} to {BLACKOUT_RANGE_END}")
    while True:
        run_check(known_jobs)
        time.sleep(60)