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
AUTO_ACCEPT_ENABLED = True 

# 2. BLACKOUT SETTINGS 🚫
MANUAL_BLACKOUT_DATES = []
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
AUTO_ACCEPT_MIN_HOURS = 6.0    # Min duration
AUTO_ACCEPT_PREP_CUTOFF = 15   # 3:00 PM (The day before)

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

def check_prep_deadline(job_date_str):
    """
    Checks if it is too late to accept the job based on the 3:00 PM day-before rule.
    Returns True if it IS too late (don't accept).
    Returns False if we are safe (accept).
    """
    try:
        now = datetime.now()
        job_dt = datetime.strptime(job_date_str, "%m/%d/%Y")
        day_before = job_dt - timedelta(days=1)
        # Set cutoff to 3:00 PM (15:00) on the day before
        cutoff_time = day_before.replace(hour=AUTO_ACCEPT_PREP_CUTOFF, minute=0, second=0, microsecond=0)
        
        if now > cutoff_time:
            return True # Too late
        else:
            return False # Safe
            
    except Exception:
        # If we can't read the date, assume it's risky and return True (Too late)
        return True

def get_active_dates(page):
    """Scrapes schedule AND generates blackout dates."""
    print("   ...Checking Schedule for conflicts")
    blocked_dates = set()
    
    for date in MANUAL_BLACKOUT_DATES:
        blocked_dates.add(date)

    if BLACKOUT_RANGE_START and BLACKOUT_RANGE_END:
        try:
            start = datetime.strptime(BLACKOUT_RANGE_START, "%m/%d/%Y")
            end = datetime.strptime(BLACKOUT_RANGE_END, "%m/%d/%Y")
            delta = end - start
            for i in range(delta.days + 1):
                day = start + timedelta(days=i)
                blocked_dates.add(day.strftime("%m/%d/%Y"))
        except ValueError:
            print("   ⚠️ Error: Check Blackout Date formats")

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
    print(f"   ⚔️ ENGAGING COMBAT MODE for: {job_details}")
    attempt_count = 0
    max_attempts = 30 
    
    while row_element.is_visible() and attempt_count < max_attempts:
        attempt_count += 1
        print(f"      👊 Attempt {attempt_count}/{max_attempts}...")
        try:
            accept_btn = row_element.locator("td").last.locator("a, button, i").first
            if accept_btn.is_visible():
                accept_btn.click()
            else:
                print("      ❌ Green button disappeared.")
                return False 

            try:
                confirm_btn = page.get_by_role("button", name="Confirm")
                confirm_btn.wait_for(state="visible", timeout=1500)
                confirm_btn.click()
            except:
                continue 

            time.sleep(1.5)
            red_banner = page.get_by_text("substitute called by the system")
            if red_banner.is_visible():
                continue
            
            if not row_element.is_visible():
                return True
        except Exception:
            time.sleep(1)

    return False

def parse_row_to_clean_string(row_element):
    if not row_element.is_visible(): return None, None, 0
    text_list = row_element.inner_text().split('\n')
    clean_items = [item.strip() for item in text_list if item.strip()]
    clean_items = [x for x in clean_items if x not in ["Decline", "Accept", "Details", "Select"]]
    if not clean_items: return None, None, 0
    full_string = " ".join(clean_items)
    if not re.search(r'\d', full_string): return None, None, 0

    date_match = re.search(r'\d{2}/\d{2}/\d{4}', full_string)
    date_str = date_match.group(0) if date_match else "Unknown"

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
            
            login_success = False
            try:
                page.locator("#userId").fill(SF_USERNAME, timeout=2000)
                page.locator("#userPin").fill(SF_PASSWORD, timeout=2000)
                page.locator("#userPin").press("Enter")
                login_success = True
            except:
                pass
            
            if not login_success:
                for frame in page.frames:
                    try:
                        frame.locator("#userId").fill(SF_USERNAME, timeout=1000)
                        frame.locator("#userPin").fill(SF_PASSWORD, timeout=1000)
                        frame.locator("#userPin").press("Enter")
                        break
                    except:
                        continue

            page.wait_for_load_state("networkidle")
            time.sleep(5) 

            # 2. GET BLOCKED DATES
            blocked_dates = get_active_dates(page)

            # 3. GO TO AVAILABLE JOBS
            print("   ...Checking Available Jobs")
            page.goto("https://westcontracosta.eschoolsolutions.com/ui/#/substitute/jobs/available", wait_until="networkidle")
            time.sleep(8)

            if "there are no jobs available" in page.locator("body").inner_text().lower():
                print("   ✅ Clean scan (No jobs visible).")
                known_jobs.clear()
                return

            print("   👀 Jobs detected. Analyzing...")
            new_jobs_found = []
            current_scan_signatures = set()
            rows = page.locator("tr").all()
            
            for row in rows:
                clean_msg, job_date_str, duration = parse_row_to_clean_string(row)
                if clean_msg:
                    fingerprint = clean_msg
                    
                    if job_date_str in blocked_dates:
                        print(f"      🔸 IGNORED (Conflict/Blackout): {clean_msg}")
                        continue
                    
                    if fingerprint in known_jobs:
                        current_scan_signatures.add(fingerprint)