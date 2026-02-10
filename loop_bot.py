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
# Note: We removed the START/END hour because the 24-Hour Rule handles timing better.
AUTO_ACCEPT_MIN_HOURS = 6.0    # Auto-Accept only if 6+ hours

# 5. NOISE FILTER 🔇
# Only send a notification if the job is at least this long.
NOTIFICATION_MIN_HOURS = 5.0

# --- 🧠 SYSTEM MEMORY ---
LOGIN_FAIL_COUNT = 0
LAST_HEARTBEAT_DATE = None

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
        # Navigate to Active Jobs to see what we already have
        page.goto("https://westcontracosta.eschoolsolutions.com/ui/#/substitute/jobs/active", wait_until="networkidle")
        time.sleep(3) # Short wait
        
        # Simple scrape of dates from the table
        # (This relies on the date text being visible in the rows)
        content = page.content()
        # Find all dates in MM/DD/YYYY format
        found_dates = re.findall(r'\d{2}/\d{2}/\d{4}', content)
        for date in found_dates:
            blocked_dates.add(date)
            
    except Exception as e:
        print(f"   ⚠️ Could not load schedule: {e}")
        
    return blocked_dates

def attempt_auto_accept(page, row_element):
    """
    Tries to click Accept. Returns True if successful.
    """
    print(f"   ⚔️ FIGHTING FOR JOB...")
    
    # STUBBORN MODE: 150 attempts
    max_attempts = 150 
    attempt_count = 0
    
    while row_element.is_visible() and attempt_count < max_attempts:
        attempt_count += 1
        try:
            # Try to find the accept button/icon
            accept_btn = row_element.locator("a, button, i").last
            if accept_btn.is_visible():
                accept_btn.click()
                
                # Look for Confirm Modal
                try:
                    confirm_btn = page.locator('button:has-text("Confirm")')
                    confirm_btn.wait_for(state="visible", timeout=2000)
                    confirm_btn.click()
                    return True # We clicked confirm!
                except:
                    pass # Confirm didn't appear, loop again
            else:
                return False # Button gone
        except:
            time.sleep(0.5)

    return False

def parse_row_data(row_element):
    """
    Extracts cleaner data from a row.
    Returns: (Full Text, Date String, Duration Hours)
    """
    if not row_element.is_visible(): return None, None, 0
    
    text = row_element.inner_text()
    clean_text = " ".join(text.split()) # Remove extra whitespace
    
    # Extract Date
    date_match = re.search(r'\d{2}/\d{2}/\d{4}', clean_text)
    date_str = date_match.group(0) if date_match else "Unknown"

    # Extract Time & Duration
    # Looks for pattern like "08:00 AM - 03:00 PM"
    time_matches = re.findall(r'\d{1,2}:\d{2}\s?[AP]M', clean_text)
    duration = 0.0
    
    if len(time_matches) >= 2:
        try:
            fmt = "%I:%M %p"
            t1 = datetime.strptime(time_matches[0], fmt)
            t2 = datetime.strptime(time_matches[1], fmt)
            diff = t2 - t1
            duration = diff.total_seconds() / 3600.0
        except:
            pass
            
    return clean_text, date_str, duration

def run_check(known_jobs):
    global LOGIN_FAIL_COUNT, LAST_HEARTBEAT_DATE
    
    # Current Time (PST approx)
    now_pst = datetime.utcnow() - timedelta(hours=8)
    
    # --- 💓 HEARTBEAT ---
    if now_pst.hour == 6 and now_pst.minute < 5:
        today_str = now_pst.strftime("%Y-%m-%d")
        if LAST_HEARTBEAT_DATE != today_str:
            send_push("🟢 Daily Heartbeat: Bot is active and scanning.", title="System Status")
            LAST_HEARTBEAT_DATE = today_str

    print(f"\n[{now_pst.strftime('%I:%M %p')}] 🚀 Scanning SmartFind...")
    
    # --- MEMORY FIX: LAUNCH OPTIONS ---
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
        # Create context with standard viewport
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()
        
        try:
            # 1. LOGIN
            print("   ...Logging in")
            page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitAction.do", timeout=60000)
            
            # Simple Login Fill
            if page.is_visible("#userId"):
                page.fill("#userId", SF_USERNAME)
                page.fill("#userPin", SF_PASSWORD)
                page.click("button:has-text('Sign In')")
                page.wait_for_load_state("networkidle")
            
            # Check success
            if "Sign Out" in page.content() or "Search" in page.content():
                LOGIN_FAIL_COUNT = 0
            else:
                LOGIN_FAIL_COUNT += 1
                print(f"   ⚠️ Login Failed ({LOGIN_FAIL_COUNT})")
                if LOGIN_FAIL_COUNT >= 5:
                    send_push("🔴 CRITICAL: Bot cannot login.", title="Login Error")
                return 

            # 2. GET BLOCKED DATES (Schedule)
            print("   ...Checking Schedule")
            blocked_dates = get_active_dates(page)

            # 3. GO TO AVAILABLE JOBS
            print("   ...Checking Available Jobs")
            page.goto("https://westcontracosta.eschoolsolutions.com/searchJobsAction.do", timeout=60000)
            
            # Handle "No Jobs"
            if "No jobs available" in page.content():
                print("   ✅ Clean scan (No jobs visible).")
                # Clear cache occasionally so we don't hold old jobs forever
                if len(known_jobs) > 50: known_jobs.clear()
                return

            print("   👀 Jobs Detected. Analyzing...")
            
            # Find Rows
            rows = page.locator("tr.searchResult").all()
            
            for row in rows:
                clean_msg, job_date_str, duration = parse_row_data(row)
                
                if not clean_msg: continue
                
                # Unique ID for this job
                fingerprint = clean_msg + str(duration)
                
                # SKIP IF:
                if job_date_str in blocked_dates:
                    continue # Already working that day
                
                if fingerprint in known_jobs:
                    continue # Already saw this scan

                # --- ⚡ DECISION LOGIC ---
                accepted = False
                
                if AUTO_ACCEPT_ENABLED:
                    # 1. School Check
                    is_green_list = False
                    for school in AUTO_ACCEPT_SCHOOLS:
                        if school in clean_msg.upper():
                            is_green_list = True
                            break
                    
                    # 2. Duration Check
                    is_long_enough = duration >= AUTO_ACCEPT_MIN_HOURS
                    
                    # 3. 24-Hour Rule Check (The New Safety)
                    is_safe_time = check_24h_rule(job_date_str)
                    
                    if is_green_list and is_long_enough and is_safe_time:
                        # ALL SYSTEMS GO - FIGHT! ⚔️
                        success = attempt_auto_accept(page, row)
                        if success:
                            send_push(f"🎉 SECURED JOB ({duration}h): {clean_msg}")
                            accepted = True
                            blocked_dates.add(job_date_str)
                        else:
                            send_push(f"⚠️ LOST FIGHT FOR: {clean_msg}")
                            accepted = True # Mark as "handled" so we don't spam
                    else:
                        # Log why we skipped
                        if not is_green_list: print(f"      🔸 Skipped (Not Green List)")
                        elif not is_long_enough: print(f"      🔸 Skipped (Too Short: {duration}h)")
                        elif not is_safe_time: print(f"      🔸 Skipped (24h Rule)")
                
                # --- 🔔 NOTIFICATION LOGIC ---
                # If we didn't accept it, maybe we should notify?
                if not accepted:
                    if duration >= NOTIFICATION_MIN_HOURS:
                        print(f"   🚨 NEW LISTING: {clean_msg}")
                        send_push(f"🚨 NEW JOB: {clean_msg}")
                    
                    known_jobs.add(fingerprint)

        except Exception as e:
            print(f"   ❌ Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    known_jobs = set()
    print("🤖 Bot Active. FEATURES: STUBBORN | BLACKOUTS | 24H RULE | LOW-MEM")
    while True:
        run_check(known_jobs)
        # Random sleep to avoid bot detection patterns (3-5 mins)
        sleep_sec = 180 + (60 * (int(str(time.time())[-1]) % 3)) 
        print(f"   💤 Sleeping for {sleep_sec//60} mins...")
        time.sleep(sleep_sec)