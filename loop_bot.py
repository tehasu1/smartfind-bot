import os
import time
import http.client
import urllib.parse
import ssl
import re
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta

# ==========================================
# ⚙️ CONFIGURATION
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

# ==========================================
# 📟 NOTIFICATION SYSTEM
# ==========================================
def send_push(message, title="SmartFind Bot"):
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
    except:
        pass

# ==========================================
# 🛡️ RULES & LOGIC
# ==========================================
def check_24h_rule(job_date_str):
    try:
        job_dt = datetime.strptime(job_date_str, "%m/%d/%Y")
        now_pst = datetime.utcnow() - timedelta(hours=8)
        if (job_dt - now_pst).total_seconds() < 86400:
            print(f"      🛑 Too Soon: Job on {job_date_str} starts in <24h.")
            return False
        return True
    except:
        return False

def get_active_dates(page):
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
        page.goto("https://westcontracosta.eschoolsolutions.com/ui/#/substitute/jobs/active", wait_until="networkidle")
        time.sleep(3)
        content = page.content()
        found_dates = re.findall(r'\d{2}/\d{2}/\d{4}', content)
        for date in found_dates:
            blocked_dates.add(date)
    except:
        pass
    return blocked_dates

# ==========================================
# 🤖 BROWSER ACTIONS
# ==========================================
def attempt_auto_accept(page, row_element):
    print(f"   ⚔️ ENGAGING COMBAT MODE...")
    max_attempts = 150 
    attempt_count = 0
    while row_element.is_visible() and attempt_count < max_attempts:
        attempt_count += 1
        try:
            # FIX: Look for TEXT "Accept" instead of guessing the column position
            # This matches any link (a) or button that contains the word "Accept"
            accept_btn = row_element.locator("a, button").filter(has_text="Accept").first
            
            if accept_btn.is_visible():
                accept_btn.click()
            else:
                # Fallback: Try the old way if text fails
                fallback_btn = row_element.locator("td").last.locator("a, button, i").first
                if fallback_btn.is_visible():
                    fallback_btn.click()
                else:
                    print("      ❌ Green button disappeared.")
                    return False 

            try:
                confirm_btn = page.get_by_role("button", name="Confirm")
                confirm_btn.wait_for(state="visible", timeout=1500)
                confirm_btn.click()
                return True
            except:
                pass
            
            time.sleep(1)
            try:
                if page.get_by_text("substitute called by the system").is_visible():
                    continue
            except:
                pass     
        except:
            time.sleep(0.5)
    return False

def parse_row_data(row_element):
    if not row_element.is_visible(): return None, None, 0
    text = row_element.inner_text()
    clean_text = " ".join(text.split())
    date_match = re.search(r'\d{2}/\d{2}/\d{4}', clean_text)
    date_str = date_match.group(0) if date_match else "Unknown"
    
    time_matches = re.findall(r'\d{1,2}:\d{2}\s?[AP]M', clean_text)
    duration = 0.0
    if len(time_matches) >= 2:
        try:
            fmt = "%I:%M %p"
            t1 = datetime.strptime(time_matches[0], fmt)
            t2 = datetime.strptime(time_matches[1], fmt)
            duration = (t2 - t1).total_seconds() / 3600.0
        except:
            pass
            
    clean_msg = clean_text
    for skip in ["Accept", "Decline", "Details", "Select", "Job Number", "Date", "Time", "Location"]:
        clean_msg = clean_msg.replace(skip, "")
    
    return clean_msg[:100], date_str, duration

# ==========================================
# 🚀 MAIN LOOP
# ==========================================
def run_check(known_jobs):
    global LOGIN_FAIL_COUNT, LAST_HEARTBEAT_DATE
    now_pst = datetime.utcnow() - timedelta(hours=8)
    
    if now_pst.hour == 6 and now_pst.minute < 5:
        today_str = now_pst.strftime("%Y-%m-%d")
        if LAST_HEARTBEAT_DATE != today_str:
            send_push("🟢 Daily Heartbeat", title="System Status")
            LAST_HEARTBEAT_DATE = today_str

    print(f"\n[{now_pst.strftime('%I:%M %p')}] 🚀 Scanning SmartFind...")
    
    launch_options = {
        "headless": True, 
        "args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--single-process", "--no-zygote", "--disable-extensions"]
    }
    
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_options)
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()
        
        try:
            # 1. LOGIN
            print("   ...Logging in")
            try:
                page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitAction.do", wait_until="networkidle", timeout=60000)
            except:
                print("   ⚠️ Page Timeout (Retrying navigation...)")

            login_success = False
            
            if "Sign Out" in page.content() or "Search" in page.content():
                 login_success = True
            
            if not login_success:
                try:
                    if page.locator("#userId").is_visible():
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
                        login_success = True
                        break
                    except:
                        continue

            if login_success:
                try: page.wait_for_load_state("networkidle", timeout=10000)
                except: pass
                
                if "Sign Out" in page.content() or "Search" in page.content():
                    LOGIN_FAIL_COUNT = 0
                else:
                    LOGIN_FAIL_COUNT += 1
            else:
                LOGIN_FAIL_COUNT += 1
                print(f"   ⚠️ Login Failed ({LOGIN_FAIL_COUNT}/5)")
                return 

            # 2. SCHEDULE
            blocked_dates = get_active_dates(page)

            # 3. JOBS
            print("   ...Checking Available Jobs")
            page.goto("https://westcontracosta.eschoolsolutions.com/searchJobsAction.do", wait_until="networkidle", timeout=60000)
            
            if "No jobs available" in page.content():
                print("   ✅ Clean scan.")
                if len(known_jobs) > 50: known_jobs.clear()
                return

            rows = page.locator("tr.searchResult").all()
            for row in rows:
                clean_msg, job_date_str, duration = parse_row_data(row)
                if not clean_msg: continue
                
                fingerprint = clean_msg + str(duration)
                if job_date_str in blocked_dates or fingerprint in known_jobs: continue

                accepted = False
                if AUTO_ACCEPT_ENABLED:
                    is_green = any(s in clean_msg.upper() for s in AUTO_ACCEPT_SCHOOLS)
                    is_long = duration >= AUTO_ACCEPT_MIN_HOURS
                    is_safe = check_24h_rule(job_date_str)
                    
                    if is_green and is_long and is_safe:
                        if attempt_auto_accept(page, row):
                            send_push(f"🎉 SECURED: {clean_msg}")
                            accepted = True
                            blocked_dates.add(job_date_str)
                        else:
                            send_push(f"⚠️ LOST FIGHT: {clean_msg}")
                            accepted = True 

                if not accepted:
                    if duration >= NOTIFICATION_MIN_HOURS:
                        print(f"   🚨 NEW: {clean_msg}")
                        send_push(f"🚨 NEW: {clean_msg}")
                    known_jobs.add(fingerprint)

        except Exception as e:
            print(f"   ❌ Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    known_jobs = set()
    print("🤖 Bot Active. FEATURES: ORIGINAL-LOGIC | 24H RULE | TEXT-SELECTOR")
    while True:
        run_check(known_jobs)
        time.sleep(60)