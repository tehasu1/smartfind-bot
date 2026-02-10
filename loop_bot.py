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
AUTO_ACCEPT_MIN_HOURS = 6.0    # Auto-Accept only if 6+ hours
AUTO_ACCEPT_PREP_CUTOFF = 15   # 3:00 PM (The day before) - Legacy setting, kept for safety

# 5. NOISE FILTER 🔇
# Only send a notification if the job is at least this long.
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
def check_prep_deadline(job_date_str):
    """
    Checks if it is too late to accept the job based on the 3:00 PM day-before rule.
    """
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

def check_24h_rule(job_date_str):
    """
    Returns True if the job is SAFE to accept (starts more than 24 hours from now).
    Returns False if the job is TOO SOON (starts within 24 hours).
    """
    try:
        # Parse the job date (e.g. "02/12/2026")
        job_dt = datetime.strptime(job_date_str, "%m/%d/%Y")
        
        # Current time in PST (UTC - 8)
        now_pst = datetime.utcnow() - timedelta(hours=8)
        
        # Calculate time until job
        time_until_job = job_dt - now_pst
        
        # If less than 24 hours (1 day), reject it.
        if time_until_job.total_seconds() < 86400:
            print(f"      🛑 24H RULE: Job on {job_date_str} starts too soon ({time_until_job.days} days).")
            return False # Too soon
        
        return True # Safe
        
    except Exception as e:
        print(f"      ⚠️ Date Parse Error: {e}")
        return False # Play it safe

def get_active_dates(page):
    """Scrapes schedule AND generates blackout dates."""
    print("   ...Checking Schedule for conflicts")
    blocked_dates = set()
    
    # 1. Add Manual Blackouts
    for date in MANUAL_BLACKOUT_DATES:
        blocked_dates.add(date)

    # 2. Add Range Blackouts
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

    # 3. Scrape Active Jobs
    try:
        page.goto("https://westcontracosta.eschoolsolutions.com/ui/#/substitute/jobs/active", wait_until="networkidle")
        time.sleep(3)
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

# ==========================================
# 🤖 BROWSER ACTIONS
# ==========================================
def attempt_auto_accept(page, row_element, job_details):
    print(f"   ⚔️ ENGAGING COMBAT MODE for: {job_details}")
    attempt_count = 0
    # STUBBORN MODE: 150 attempts (~4 minutes)
    max_attempts = 150 
    
    while row_element.is_visible() and attempt_count < max_attempts:
        attempt_count += 1
        # print(f"      👊 Attempt {attempt_count}/{max_attempts}...") # Uncomment for extreme debug
        try:
            accept_btn = row_element.locator("td").last.locator("a, button, i").first
            if accept_btn.is_visible():
                accept_btn.click()
            else:
                print("      ❌ Green button disappeared.")
                return False 

            try:
                # Try to find and click confirm
                confirm_btn = page.get_by_role("button", name="Confirm")
                if confirm_btn.is_visible():
                    confirm_btn.click()
                    return True # Success if we clicked confirm
            except:
                pass 

            # Check for red error banner
            time.sleep(1.0)
            red_banner = page.get_by_text("substitute called by the system")
            if red_banner.is_visible():
                # Just keep looping, don't exit
                continue
            
            if not row_element.is_visible():
                return True
        except Exception:
            time.sleep(0.5)

    return False

def parse_row_to_clean_string(row_element):
    """
    Parses a table row into usable data.
    """
    if not row_element.is_visible(): return None, None, 0
    text_list = row_element.inner_text().split('\n')
    clean_items = [item.strip() for item in text_list if item.strip()]
    clean_items = [x for x in clean_items if x not in ["Decline", "Accept", "Details", "Select"]]
    if not clean_items: return None, None, 0
    full_string = " ".join(clean_items)
    if not re.search(r'\d', full_string): return None, None, 0

    # Extract Date
    date_match = re.search(r'\d{2}/\d{2}/\d{4}', full_string)
    date_str = date_match.group(0) if date_match else "Unknown"

    # Extract Time & Duration
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

    # Clean up School Name
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
    
    # Calculate PST Time
    now = datetime.utcnow() - timedelta(hours=8)
    current_hour = now.hour
    
    # --- 💓 HEARTBEAT ---
    if current_hour == 6 and now.minute < 5:
        today_str = now.strftime("%Y-%m-%d")
        if LAST_HEARTBEAT_DATE != today_str:
            send_push("🟢 Daily Heartbeat: Bot is active and scanning.", title="System Status")
            LAST_HEARTBEAT_DATE = today_str

    print(f"\n[{now.strftime('%I:%M %p')}] 🚀 Scanning SmartFind...")
    
    # --- LAUNCH BROWSER ---
    # These args are critical for Railway stability
    launch_options = {
        "headless": True, 
        "args": [
            "--no-sandbox", 
            "--disable-setuid-sandbox", 
            "--disable-dev-shm-usage", 
            "--disable-gpu", 
            "--single-process", 
            "--no-zygote",
            "--disable-extensions"
        ]
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_options)
        
        # --- SESSION HANDLING ---
        # Try to load cookies from previous run to speed up login
        context = None
        if os.path.exists(SESSION_FILE):
            try:
                # print("   🍪 Loading Saved Session...")
                context = browser.new_context(storage_state=SESSION_FILE, viewport={'width': 1920, 'height': 1080})
            except:
                print("   ⚠️ Session file corrupt, starting fresh.")
                context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        else:
            context = browser.new_context(viewport={'width': 1920, 'height': 1080})
            
        page = context.new_page()
        
        try:
            # 1. LOGIN ROUTINE
            # print("   ...Navigating to Login")
            try:
                page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitAction.do", wait_until="networkidle", timeout=45000)
            except:
                print("   ⚠️ Page load timeout (Network glitch).")
                return

            # Check if we are already logged in (via cookies)
            if "Sign Out" in page.content() or "Search" in page.content():
                # print("   ✅ Already Logged In")
                LOGIN_FAIL_COUNT = 0
            else:
                # Perform Login
                print("   ...Entering Credentials")
                
                # Fallback to ensure we find the fields
                try:
                    page.wait_for_selector("#userId", timeout=5000)
                    page.fill("#userId", SF_USERNAME)
                    page.fill("#userPin", SF_PASSWORD)
                    
                    # FIX: Use Keyboard 'Enter' instead of clicking the button
                    page.keyboard.press("Enter")
                    
                    try:
                        page.wait_for_load_state("networkidle", timeout=30000)
                    except:
                        pass
                except Exception as e:
                    print(f"   ❌ Login Form Error: {e}")
            
            # Verify Login Success
            if "Sign Out" in page.content() or "Search" in page.content():
                LOGIN_FAIL_COUNT = 0
                # Save the fresh session
                context.storage_state(path=SESSION_FILE)
            else:
                LOGIN_FAIL_COUNT += 1
                print(f"   ⚠️ Login Failed! (Attempt {LOGIN_FAIL_COUNT}/5)")
                if LOGIN_FAIL_COUNT >= 5:
                    send_push("🔴 CRITICAL: Bot cannot login (5 failures). Check password or site.", title="Login Error")
                    LOGIN_FAIL_COUNT = 0 
                return 

            # 2. GET BLOCKED DATES
            blocked_dates = get_active_dates(page)

            # 3. GO TO AVAILABLE JOBS
            print("   ...Checking Available Jobs")
            page.goto("https://westcontracosta.eschoolsolutions.com/searchJobsAction.do", wait_until="networkidle")
            
            # Wait a moment for table to populate
            time.sleep(2)

            if "No jobs available" in page.content():
                print("   ✅ Clean scan (No jobs visible).")
                if len(known_jobs) > 100: known_jobs.clear() # Clear cache if it gets too big
                return

            print("   👀 Jobs detected. Analyzing...")
            new_jobs_found = []
            current_scan_signatures = set()
            rows = page.locator("tr").all()
            
            for row in rows:
                clean_msg, job_date_str, duration = parse_row_to_clean_string(row)
                
                # Filter out garbage rows
                if not clean_msg: continue
                
                fingerprint = clean_msg + str(duration)
                
                # --- FILTER: BLACKOUTS ---
                if job_date_str in blocked_dates:
                    # print(f"      🔸 IGNORED (Conflict/Blackout): {clean_msg}")
                    continue
                
                # --- FILTER: SEEN JOBS ---
                if fingerprint in known_jobs:
                    current_scan_signatures.add(fingerprint)
                    continue

                # --- ⚡ AUTO-ACCEPT LOGIC ---
                accepted = False
                fought_and_lost = False 
                
                if AUTO_ACCEPT_ENABLED:
                    # Check 1: 3PM Prep Rule (Legacy)
                    is_too_late = check_prep_deadline(job_date_str)
                    
                    # Check 2: 24 Hour Rule (New Safety)
                    is_safe_time = check_24h_rule(job_date_str)

                    # Check 3: School & Duration
                    is_green_list = any(school.upper() in clean_msg.upper() for school in AUTO_ACCEPT_SCHOOLS)
                    is_long_enough = duration >= AUTO_ACCEPT_MIN_HOURS
                    
                    if is_green_list and is_long_enough and not is_too_late and is_safe_time:
                        # ALL GREEN - FIGHT!
                        success = attempt_auto_accept(page, row, clean_msg)
                        if success:
                            send_push(f"🎉 SECURED JOB ({duration}h): {clean_msg}")
                            accepted = True
                            blocked_dates.add(job_date_str)
                        else:
                            send_push(f"⚠️ LOST FIGHT FOR: {clean_msg}")
                            fought_and_lost = True 
                    else:
                        # Debug: Why did we skip?
                        if is_too_late:
                            print(f"      🔸 Skipped (Too Late to Prepare)")
                        elif not is_safe_time:
                            print(f"      🔸 Skipped (Starts < 24h)")
                        elif not is_green_list:
                            print(f"      🔸 Skipped (Not High School)")
                        elif not is_long_enough:
                            print(f"      🔸 Skipped (Too Short: {duration}h)")
                else:
                    print("      🔸 Skipped (Auto-Accept Disabled)")

                # --- 🔔 NOTIFICATION LOGIC ---
                if not accepted and not fought_and_lost:
                    if duration >= NOTIFICATION_MIN_HOURS:
                        print(f"   🚨 NEW LISTING: {clean_msg}")
                        new_jobs_found.append(clean_msg)
                    else:
                        print(f"      😶 Muted (Too short: {duration}h)")
                        
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
    print("🤖 Bot Active. FEATURES: SESSION | STUBBORN | 24H RULE | LOW-MEM")
    while True:
        run_check(known_jobs)
        # Fast Sleep (60s)
        time.sleep(60)