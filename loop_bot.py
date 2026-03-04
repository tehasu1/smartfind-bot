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

# 1. MASTER SWITCH
AUTO_ACCEPT_ENABLED = True 

# 2. SAFETY SWITCHES 🛡️
ENABLE_24H_RULE = True   # Set to False if you want to pick up last-minute shifts

# 3. HARD BLACKOUT SETTINGS 🚫 (Ignored entirely)
MANUAL_BLACKOUT_DATES = [
    # BLOCK 1: March 21 - March 29
    "03/21/2026", "03/22/2026", "03/23/2026", "03/24/2026", "03/25/2026",
    "03/26/2026", "03/27/2026", "03/28/2026", "03/29/2026",
    
    # BLOCK 2: April 30 - May 10
    "04/30/2026", 
    "05/01/2026", "05/02/2026", "05/03/2026", "05/04/2026", "05/05/2026",
    "05/06/2026", "05/07/2026", "05/08/2026", "05/09/2026", "05/10/2026"
]
BLACKOUT_RANGE_START = None
BLACKOUT_RANGE_END   = None

# 3.5 NOTIFY-ONLY DATES ⚠️ (No Combat, but sends Push)
NOTIFY_ONLY_DATES = [
    "03/30/2026", "03/31/2026", "04/01/2026", "04/02/2026", "04/03/2026", 
    "04/04/2026", "04/05/2026", "04/06/2026", "04/07/2026", "04/08/2026", 
    "04/09/2026", "04/10/2026"
]

# 4. STRICT TARGET SCHOOLS 🎯
TARGET_HIGH_SCHOOLS = [
    "EL CERRITO HIGH",
    "RICHMOND HIGH SCHOOL",
    "PINOLE HIGH SCHOOL",
    "KENNEDY HIGH",
    "DE ANZA HIGH",
    "HERCULES HIGH SCHOOL"
]

# 5. SETTINGS
AUTO_ACCEPT_MIN_HOURS = 4.5    # Auto-Accept only if 4.5+ hours
AUTO_ACCEPT_MAX_HOURS = 9.0    # Ignore jobs longer than 9 hours
AUTO_ACCEPT_PREP_CUTOFF = 15   # 3:00 PM (The day before)

# 6. NOISE FILTER 🔇
NOTIFICATION_MIN_HOURS = 4.5   # Only notify if 4.5+ hours

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
def is_target_school(clean_msg):
    msg_upper = clean_msg.upper()
    
    if any(hs in msg_upper for hs in TARGET_HIGH_SCHOOLS):
        return True
        
    if "MIDDLE" in msg_upper and "SP ED" in msg_upper:
        return True
        
    return False

def check_24h_rule(job_date_str):
    if not ENABLE_24H_RULE:
        return True 

    try:
        job_dt = datetime.strptime(job_date_str, "%m/%d/%Y")
        now_pst = datetime.utcnow() - timedelta(hours=8)
        
        if (job_dt - now_pst).total_seconds() < 86400:
            print(f"      🛑 24H RULE: Job on {job_date_str} starts too soon (<24h).")
            return False
        return True 
    except Exception as e:
        print(f"      ⚠️ Date Parse Error: {e}")
        return False

def check_prep_deadline(job_date_str):
    try:
        now = datetime.now()
        job_dt = datetime.strptime(job_date_str, "%m/%d/%Y")
        day_before = job_dt - timedelta(days=1)
        cutoff_time = day_before.replace(hour=AUTO_ACCEPT_PREP_CUTOFF, minute=0, second=0, microsecond=0)
        
        if now > cutoff_time:
            return True # Too late
        else:
            return False # Safe
    except Exception:
        return True

def get_active_dates(page):
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
        time.sleep(3)
        content = page.content()
        found_dates = re.findall(r'\d{2}/\d{2}/\d{4}', content)
        for date in found_dates:
            blocked_dates.add(date)
    except Exception as e:
        print(f"   ⚠️ Could not load schedule: {e}")
        
    return blocked_dates

# ==========================================
# 🤖 BROWSER ACTIONS
# ==========================================
def attempt_auto_accept(page, row_element, job_details):
    print(f"   ⚔️ ENGAGING COMBAT MODE (4 Minutes)...")
    max_attempts = 500 
    attempt_count = 0
    
    while attempt_count < max_attempts:
        attempt_count += 1
        
        if not row_element.is_visible():
            print("      ✨ The job row is gone. Assuming success.")
            return True

        try:
            page.locator("a:has-text('Accept'), button:has-text('Accept')").first.click(timeout=500)
        except:
            try:
                row_element.locator("td").last.locator("a, button, i").first.click(timeout=500)
            except:
                pass 

        try:
            confirm_btn = page.locator("button:has-text('Confirm')")
            if confirm_btn.is_visible():
                confirm_btn.click(timeout=500)
                print("      ✅ Clicked Confirm!")
        except:
            pass
        
        try:
            if page.locator("div:has-text('substitute called by the system')").is_visible():
                time.sleep(1)
                continue 
        except:
            pass
            
        time.sleep(0.3)
        
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
        try:
            fmt = "%I:%M %p"
            t1 = datetime.strptime(time_matches[0], fmt)
            t2 = datetime.strptime(time_matches[1], fmt)
            duration = (t2 - t1).total_seconds() / 3600.0
            time_display = f"{time_matches[0]} - {time_matches[1]}"
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

# ==========================================
# 🚀 MAIN LOOP
# ==========================================
def run_check(known_jobs):
    global LOGIN_FAIL_COUNT, LAST_HEARTBEAT_DATE
    
    now_pst = datetime.utcnow() - timedelta(hours=8)
    
    if now_pst.hour == 6 and now_pst.minute < 5:
        today_str = now_pst.strftime("%Y-%m-%d")
        if LAST_HEARTBEAT_DATE != today_str:
            send_push("🟢 Daily Heartbeat: Bot is active and scanning.", title="System Status")
            LAST_HEARTBEAT_DATE = today_str

    print(f"[{now_pst.strftime('%I:%M %p')}] 🚀 Scanning SmartFind...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, 
            args=[
                "--no-sandbox", 
                "--disable-setuid-sandbox", 
                "--disable-dev-shm-usage", 
                "--disable-gpu", 
                "--single-process", 
                "--no-zygote",
                "--disable-extensions"
            ]
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
                        login_success = True
                        break
                    except:
                        continue
            
            if login_success:
                if LOGIN_FAIL_COUNT > 0:
                    print(f"   ✅ Login recovered! (Previously failed {LOGIN_FAIL_COUNT} times)")
                LOGIN_FAIL_COUNT = 0
            else:
                LOGIN_FAIL_COUNT += 1
                print(f"   ⚠️ Login Failed! (Attempt {LOGIN_FAIL_COUNT}/5)")
                if LOGIN_FAIL_COUNT >= 5:
                    send_push("🔴 CRITICAL: Bot cannot login (5 failures). Check password or site.", title="Login Error")
                    LOGIN_FAIL_COUNT = 0 
                return 

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
                        
                    try:
                        job_dt_check = datetime.strptime(job_date_str, "%m/%d/%Y")
                        if job_dt_check.weekday() == 1:
                            print(f"      🔸 IGNORED (Tuesday Blackout): {clean_msg}")
                            continue
                    except:
                        pass
                    
                    if fingerprint in known_jobs:
                        current_scan_signatures.add(fingerprint)
                        continue

                    # --- STRICT SCHOOL FILTER ---
                    if not is_target_school(clean_msg):
                        print(f"      🔸 IGNORED (Not Target HS or MS SP ED): {clean_msg}")
                        current_scan_signatures.add(fingerprint)
                        continue
                        
                    # --- MAX HOURS FILTER ---
                    if duration > AUTO_ACCEPT_MAX_HOURS:
                        print(f"      🔸 IGNORED (Too Long: {duration}h): {clean_msg}")
                        current_scan_signatures.add(fingerprint)
                        continue

                    # --- ⚡ AUTO-ACCEPT LOGIC ---
                    accepted = False
                    fought_and_lost = False 
                    
                    if AUTO_ACCEPT_ENABLED:
                        is_notify_only = job_date_str in NOTIFY_ONLY_DATES
                        
                        if is_notify_only:
                            print(f"      🔸 Auto-Accept Skipped (Notify-Only Date: {job_date_str})")
                        else:
                            is_too_late = check_prep_deadline(job_date_str)
                            is_safe_time = check_24h_rule(job_date_str)
                            is_long_enough = duration >= AUTO_ACCEPT_MIN_HOURS
                            
                            if is_long_enough and not is_too_late and is_safe_time:
                                
                                print(f"   ⚡ Sending immediate notification for combat mode...")
                                send_push(f"⚡ COMBAT MODE INITIATED:\n{clean_msg}")
                                
                                success = attempt_auto_accept(page, row, clean_msg)
                                if success:
                                    send_push(f"🎉 SECURED JOB ({duration}h):\n{clean_msg}")
                                    accepted = True
                                    blocked_dates.add(job_date_str)
                                else:
                                    send_push(f"⚠️ LOST FIGHT FOR:\n{clean_msg}")
                                    fought_and_lost = True 
                            else:
                                if not is_safe_time:
                                    print(f"      🔸 Auto-Accept Skipped (24h Rule)")
                                elif is_too_late:
                                    print(f"      🔸 Auto-Accept Skipped (Too Late to Prepare)")
                                elif not is_long_enough:
                                    print(f"      🔸 Auto-Accept Skipped (Too Short: {duration}h)")
                    else:
                        print("      🔸 Auto-Accept Disabled")

                    if not accepted and not fought_and_lost:
                        if duration >= NOTIFICATION_MIN_HOURS:
                            print(f"   🚨 NEW TARGET LISTING: {clean_msg}")
                            new_jobs_found.append(clean_msg)
                        current_scan_signatures.add(fingerprint)

            if new_jobs_found:
                msg = f"🚨 {len(new_jobs_found)} NEW TARGET JOB(S):\n"
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
    print("🤖 Bot Active. FEATURES: MAX 9H | 4.5H-MIN | STRICT-FILTER | IMMEDIATE-PUSH")
    while True:
        run_check(known_jobs)
        time.sleep(60)