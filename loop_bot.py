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
ENABLE_24H_RULE = True   

MANUAL_BLACKOUT_DATES = [
    # April 30 - May 10
    "04/30/2026", 
    "05/01/2026", "05/02/2026", "05/03/2026", "05/04/2026", "05/05/2026",
    "05/06/2026", "05/07/2026", "05/08/2026", "05/09/2026", "05/10/2026"
]
BLACKOUT_RANGE_START = None
BLACKOUT_RANGE_END   = None
NOTIFY_ONLY_DATES = []

TARGET_HIGH_SCHOOLS = [
    "EL CERRITO",
    "RICHMOND HIGH",
    "PINOLE",
    "KENNEDY",
    "DE ANZA",
    "HERCULES HIGH"
]

AUTO_ACCEPT_MIN_HOURS = 4.5    
AUTO_ACCEPT_MAX_HOURS = 9.0    
NOTIFICATION_MIN_HOURS = 4.5   

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
            return False
        return True 
    except:
        return False

def get_active_dates(page):
    blocked_dates = set()
    for date in MANUAL_BLACKOUT_DATES:
        blocked_dates.add(date)
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
def attempt_auto_accept(page, row_element, job_details):
    print(f"   ⚔️ ENGAGING COMBAT MODE...")
    
    # SAFETY NET KEEPS THE BOT FROM CRASHING SILENTLY
    try:
        max_loops = 15 # ~45 seconds of fighting
        loop_count = 0
        
        while loop_count < max_loops:
            loop_count += 1
            
            # 1. RESTORED PROVEN CLICK LOGIC: Target the Icon specifically
            try:
                print(f"      👉 [Attempt {loop_count}] Clicking Accept icon...")
                accept_cell = row_element.locator("td").last
                icon = accept_cell.locator("svg, i, span, img, a, button").first
                
                if icon.is_visible():
                    icon.click(force=True, timeout=2000)
                else:
                    accept_cell.click(force=True, timeout=2000)
            except Exception as e:
                print("      ⚠️ Failed to click the Accept column. Retrying...")
                time.sleep(1)
                continue

            # 2. Wait for the Custom Modal to appear
            try:
                print("      ⏳ Checking for Confirm Modal...")
                confirm_btn = page.locator("button:has-text('Confirm')").first
                confirm_btn.wait_for(state="visible", timeout=3000) 
                
                print("      👉 Modal found! Clicking Confirm...")
                confirm_btn.click(force=True)
                
                # 3. Smarter Victory Detection
                print("      🧘 Waiting for server success banner (up to 20s)...")
                for _ in range(20):
                    try:
                        page_text = page.locator("body").inner_text().lower()
                        if "success" in page_text or "successfully accepted" in page_text or "job number" in page_text:
                            print("      ✨ SUCCESS! Found confirmation message on page.")
                            return "WON"
                    except:
                        pass
                    
                    if not row_element.is_visible():
                        print("      ✨ SUCCESS! The job row disappeared.")
                        return "WON"
                        
                    time.sleep(1)

                print("      ❌ The job row never disappeared.")
                return "LOST"
                
            except Exception as e:
                print("      ⚠️ Modal blocked (Job likely 'Under Review'). Retrying loop...")
                time.sleep(1) 
                continue

        print("      ❌ Max attempts reached. The job is permanently gone or locked.")
        return "LOST"

    except Exception as fatal_error:
        print(f"      🔴 FATAL COMBAT CRASH: {fatal_error}")
        return f"CRASH: {fatal_error}"

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

    time_matches = re.findall(r'\d{1,2}:\d{2}\s?[aApP][mM]', full_string)
    time_display = ""
    duration = 0.0

    if len(time_matches) >= 2:
        try:
            fmt = "%I:%M %p"
            t1 = datetime.strptime(time_matches[0].strip().upper(), fmt)
            t2 = datetime.strptime(time_matches[-1].strip().upper(), fmt)
            
            duration = (t2 - t1).total_seconds() / 3600.0
            if duration < 0: 
                duration += 24.0
                time_display = f"{time_matches[0].strip()} - {time_matches[-1].strip()}"
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
        page.on("dialog", lambda dialog: dialog.accept())
        
        try:
            page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitAction.do", wait_until="networkidle")
            
            login_success = False
            try:
                page.locator("#userId").fill(SF_USERNAME, timeout=2000)
                page.locator("#userPin").fill(SF_PASSWORD, timeout=2000)
                page.locator("#userPin").press("Enter")
                login_success = True
            except:
                for frame in page.frames:
                    try:
                        frame.locator("#userId").fill(SF_USERNAME, timeout=1000)
                        frame.locator("#userPin").fill(SF_PASSWORD, timeout=1000)
                        frame.locator("#userPin").press("Enter")
                        login_success = True
                        break
                    except:
                        continue
            
            if not login_success:
                LOGIN_FAIL_COUNT += 1
                if LOGIN_FAIL_COUNT >= 5:
                    send_push("🔴 CRITICAL: Bot cannot login (5 failures). Check password or site.", title="Login Error")
                    LOGIN_FAIL_COUNT = 0 
                return 

            LOGIN_FAIL_COUNT = 0
            page.wait_for_load_state("networkidle")
            time.sleep(5) 

            blocked_dates = get_active_dates(page)

            page.goto("https://westcontracosta.eschoolsolutions.com/ui/#/substitute/jobs/available", wait_until="networkidle")
            time.sleep(8)

            if "there are no jobs available" in page.locator("body").inner_text().lower():
                known_jobs.clear()
                return

            new_jobs_found = []
            current_scan_signatures = set()
            rows = page.locator("tr").all()
            
            for row in rows:
                clean_msg, job_date_str, duration = parse_row_to_clean_string(row)
                if clean_msg:
                    fingerprint = clean_msg
                    
                    if job_date_str in blocked_dates:
                        continue
                        
                    try:
                        job_dt_check = datetime.strptime(job_date_str, "%m/%d/%Y")
                        if job_dt_check.weekday() == 1:
                            continue
                    except:
                        pass
                    
                    if fingerprint in known_jobs:
                        current_scan_signatures.add(fingerprint)
                        continue

                    if not is_target_school(clean_msg):
                        current_scan_signatures.add(fingerprint)
                        continue
                        
                    if duration > AUTO_ACCEPT_MAX_HOURS:
                        current_scan_signatures.add(fingerprint)
                        continue

                    accepted = False
                    fought_and_lost = False 
                    
                    if AUTO_ACCEPT_ENABLED:
                        is_notify_only = job_date_str in NOTIFY_ONLY_DATES
                        if not is_notify_only:
                            is_safe_time = check_24h_rule(job_date_str)
                            is_long_enough = duration >= AUTO_ACCEPT_MIN_HOURS
                            
                            if is_long_enough and is_safe_time:
                                send_push(f"⚡ COMBAT MODE INITIATED:\n{clean_msg}")
                                
                                result = attempt_auto_accept(page, row, clean_msg)
                                
                                if result == "WON":
                                    send_push(f"🎉 SECURED JOB ({duration}h):\n{clean_msg}")
                                    accepted = True
                                    blocked_dates.add(job_date_str)
                                elif result == "LOST":
                                    send_push(f"⚠️ LOST FIGHT FOR:\n{clean_msg}")
                                    fought_and_lost = True 
                                else:
                                    send_push(f"🔴 COMBAT CRASHED:\n{clean_msg}\n{result}")
                                    fought_and_lost = True

                    if not accepted and not fought_and_lost:
                        if duration >= NOTIFICATION_MIN_HOURS:
                            new_jobs_found.append(clean_msg)
                        current_scan_signatures.add(fingerprint)

            if new_jobs_found:
                msg = f"🚨 {len(new_jobs_found)} NEW TARGET JOB(S):\n"
                for job in new_jobs_found:
                    msg += f"{job}\n"
                send_push(msg)
                known_jobs.update(current_scan_signatures)

        except Exception as global_error:
            print(f"❌ Global Error: {global_error}")
        finally:
            browser.close()

if __name__ == "__main__":
    known_jobs = set()
    print("🤖 Bot Active. FEATURES: PROVEN-ICON-CLICK | CRASH-REPORTER")
    while True:
        run_check(known_jobs)
        time.sleep(60)