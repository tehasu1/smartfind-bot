import os
import sys
import time
import http.client
import urllib.parse
import ssl
import re
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# ==========================================
# ⚙️ CONFIGURATION & SECRETS
# ==========================================
load_dotenv()
SF_USERNAME = os.getenv("SF_USERNAME")
SF_PASSWORD = os.getenv("SF_PASSWORD")
PUSHOVER_USER = os.getenv("PUSHOVER_USER")
PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN")

# --- 🎛️ CONTROL PANEL ---
AUTO_ACCEPT_ENABLED = True 
MANUAL_BLACKOUT_DATES = []
BLACKOUT_RANGE_START = "03/23/2026"
BLACKOUT_RANGE_END   = "05/10/2026"

AUTO_ACCEPT_SCHOOLS = [
    "EL CERRITO HIGH",
    "RICHMOND HIGH SCHOOL",
    "PINOLE HIGH SCHOOL",
    "KENNEDY HIGH",
    "DE ANZA HIGH",
    "HERCULES HIGH SCHOOL"
]

AUTO_ACCEPT_MIN_HOURS = 6.0
NOTIFICATION_MIN_HOURS = 5.0

# --- 🧠 SYSTEM MEMORY ---
LOGIN_FAIL_COUNT = 0
LAST_HEARTBEAT_DATE = None
SESSION_FILE = "state.json"

# ==========================================
# 📟 NOTIFICATION SYSTEM
# ==========================================
def send_push(message, title="SmartFind Bot"):
    """Sends a notification via Pushover."""
    print(f"   📲 PUSH: {message}")
    try:
        context = ssl._create_unverified_context()
        conn = http.client.HTTPSConnection("api.pushover.net:443", context=context)
        payload = urllib.parse.urlencode({
            "token": PUSHOVER_TOKEN,
            "user": PUSHOVER_USER,
            "message": message,
            "title": title
        })
        conn.request("POST", "/1/messages.json", payload, {"Content-type": "application/x-www-form-urlencoded"})
        conn.getresponse()
    except Exception as e:
        print(f"   ⚠️ Push Failed: {e}")

# ==========================================
# 🛡️ RULES & LOGIC
# ==========================================
def check_24h_rule(job_date_str):
    """
    Returns True if the job is SAFE to accept (starts more than 24 hours from now).
    """
    try:
        job_dt = datetime.strptime(job_date_str, "%m/%d/%Y")
        now_pst = datetime.utcnow() - timedelta(hours=8)
        time_until_job = job_dt - now_pst
        
        if time_until_job.total_seconds() < 86400:
            print(f"      🛑 24H RULE: Job on {job_date_str} starts too soon.")
            return False
        return True
    except Exception as e:
        return False 

def get_active_dates(page):
    """Scrapes schedule AND generates blackout dates."""
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
        except:
            pass

    try:
        # We use a faster wait here
        page.goto("https://westcontracosta.eschoolsolutions.com/ui/#/substitute/jobs/active", wait_until="domcontentloaded")
        time.sleep(2)
        rows = page.locator("tr").all()
        for row in rows:
            if not row.is_visible(): continue
            text = row.inner_text()
            date_match = re.search(r'\d{2}/\d{2}/\d{4}', text)
            if date_match:
                blocked_dates.add(date_match.group(0))
    except:
        pass
    return blocked_dates

# ==========================================
# 🤖 BROWSER ACTIONS
# ==========================================
def attempt_auto_accept(page, row_element, job_details):
    print(f"   ⚔️ ENGAGING COMBAT MODE for: {job_details}")
    attempt_count = 0
    max_attempts = 150 
    
    while row_element.is_visible() and attempt_count < max_attempts:
        attempt_count += 1
        try:
            accept_btn = row_element.locator("td").last.locator("a, button, i").first
            if accept_btn.is_visible():
                accept_btn.click()
            else:
                return False 

            try:
                confirm_btn = page.get_by_role("button", name="Confirm")
                if confirm_btn.is_visible():
                    confirm_btn.click()
                    return True
            except:
                pass 

            time.sleep(1.0)
            if page.get_by_text("substitute called by the system").is_visible():
                continue
            
            if not row_element.is_visible():
                return True
        except:
            time.sleep(0.5)
    return False

def parse_row_to_clean_string(row_element):
    if not row_element.is_visible(): return None, None, 0
    text_list = row_element.inner_text().split('\n')
    clean_items = [item.strip() for item in text_list if item.strip()]
    clean_items = [x for x in clean_items if x not in ["Decline", "Accept", "Details", "Select"]]
    if not clean_items: return None, None, 0
    full_string = " ".join(clean_items)
    
    date_match = re.search(r'\d{2}/\d{2}/\d{4}', full_string)
    date_str = date_match.group(0) if date_match else "Unknown"

    time_matches = re.findall(r'\d{1,2}:\d{2}\s?[AP]M', full_string)
    time_display = ""
    duration = 0.0

    if len(time_matches) >= 2:
        try:
            fmt = "%I:%M %p"
            t1 = datetime.strptime(time_matches[0], fmt)
            t2 = datetime.strptime(time_matches[1], fmt)
            duration = (t2 - t1).total_seconds() / 3600.0
            time_display = f"{time_matches[0]} - {time_matches[1]}"
        except:
            pass

    content_items = [x for x in clean_items if date_str not in x and x not in time_matches]
    formatted_msg = f"📅 {date_str}"
    if content_items: formatted_msg += f" | 🏫 {content_items[-1]}"
    if time_display: formatted_msg += f" | ⏰ {time_display}"

    return formatted_msg, date_str, duration

# ==========================================
# 🚀 MAIN LOOP
# ==========================================
def run_check(known_jobs):
    global LOGIN_FAIL_COUNT, LAST_HEARTBEAT_DATE
    
    now = datetime.utcnow() - timedelta(hours=8)
    if now.hour == 6 and now.minute < 5 and LAST_HEARTBEAT_DATE != now.strftime("%Y-%m-%d"):
        send_push("🟢 Daily Heartbeat", title="System Status")
        LAST_HEARTBEAT_DATE = now.strftime("%Y-%m-%d")

    print(f"\n[{now.strftime('%I:%M %p')}] 🚀 Scanning SmartFind...")
    
    launch_options = {
        "headless": True, 
        "args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--single-process", "--no-zygote", "--disable-extensions"]
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_options)
        
        # Session Handling
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        if os.path.exists(SESSION_FILE):
            try: context = browser.new_context(storage_state=SESSION_FILE, viewport={'width': 1920, 'height': 1080})
            except: pass
            
        page = context.new_page()
        
        try:
            # 1. LOGIN (With Timeout Fix)
            # We use 'domcontentloaded' which is faster/safer than 'networkidle'
            try:
                page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitAction.do", wait_until="domcontentloaded", timeout=60000)
            except:
                print("   ⚠️ Page load timeout (Retrying...)")
                return

            if "Sign Out" in page.content() or "Search" in page.content():
                LOGIN_FAIL_COUNT = 0
            else:
                # Fill Credentials
                try:
                    page.wait_for_selector("#userId", timeout=5000)
                    page.fill("#userId", SF_USERNAME)
                    page.fill("#userPin", SF_PASSWORD)
                    
                    # FIX: Use Enter Key on the password field
                    page.locator("#userPin").press("Enter")
                    
                    try: page.wait_for_load_state("domcontentloaded", timeout=30000)
                    except: pass
                except Exception as e:
                    print(f"   ❌ Login Form Error: {e}")
            
            # Verify Login
            if "Sign Out" in page.content() or "Search" in page.content():
                LOGIN_FAIL_COUNT = 0
                context.storage_state(path=SESSION_FILE)
            else:
                LOGIN_FAIL_COUNT += 1
                print(f"   ⚠️ Login Failed ({LOGIN_FAIL_COUNT}/5)")
                if LOGIN_FAIL_COUNT >= 5:
                    send_push("🔴 CRITICAL: Bot cannot login.", title="Login Error") 
                    LOGIN_FAIL_COUNT = 0
                return 

            # 2. SCHEDULE
            blocked_dates = get_active_dates(page)

            # 3. AVAILABLE JOBS
            print("   ...Checking Available Jobs")
            page.goto("https://westcontracosta.eschoolsolutions.com/searchJobsAction.do", wait_until="domcontentloaded", timeout=60000)
            
            # Wait for table to actually appear
            try: page.wait_for_selector("table", timeout=5000)
            except: pass

            if "No jobs available" in page.content():
                print("   ✅ Clean scan (No jobs visible).")
                if len(known_jobs) > 100: known_jobs.clear()
                return

            print("   👀 Jobs detected. Analyzing...")
            new_jobs_found = []
            current_scan_signatures = set()
            rows = page.locator("tr").all()
            
            for row in rows:
                clean_msg, job_date_str, duration = parse_row_to_clean_string(row)
                if not clean_msg: continue
                
                fingerprint = clean_msg + str(duration)
                if job_date_str in blocked_dates or fingerprint in known_jobs:
                    current_scan_signatures.add(fingerprint)
                    continue

                accepted = False
                fought_and_lost = False 
                
                if AUTO_ACCEPT_ENABLED:
                    is_safe_time = check_24h_rule(job_date_str)
                    is_green_list = any(school.upper() in clean_msg.upper() for school in AUTO_ACCEPT_SCHOOLS)
                    is_long_enough = duration >= AUTO_ACCEPT_MIN_HOURS
                    
                    if is_green_list and is_long_enough and is_safe_time:
                        success = attempt_auto_accept(page, row, clean_msg)
                        if success:
                            send_push(f"🎉 SECURED JOB: {clean_msg}")
                            accepted = True
                            blocked_dates.add(job_date_str)
                        else:
                            send_push(f"⚠️ LOST FIGHT: {clean_msg}")
                            fought_and_lost = True 
                    else:
                        if not is_safe_time: print(f"      🔸 Skipped (Starts < 24h)")
                        elif not is_green_list: print(f"      🔸 Skipped (Not Green List)")

                if not accepted and not fought_and_lost:
                    if duration >= NOTIFICATION_MIN_HOURS:
                        print(f"   🚨 NEW LISTING: {clean_msg}")
                        new_jobs_found.append(clean_msg)
                    current_scan_signatures.add(fingerprint)

            if new_jobs_found:
                msg = "\n".join(new_jobs_found)
                send_push(f"🚨 {len(new_jobs_found)} NEW JOB(S):\n{msg}")
                known_jobs.update(current_scan_signatures)

        except Exception as e:
            print(f"   ❌ Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    known_jobs = set()
    print("🤖 Bot Active. FEATURES: SESSION | STUBBORN | 24H RULE | LOW-MEM")
    while True:
        run_check(known_jobs)
        time.sleep(60)