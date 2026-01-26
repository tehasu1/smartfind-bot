import os
import time
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
SF_USERNAME = os.getenv("SF_USERNAME")
SF_PASSWORD = os.getenv("SF_PASSWORD")

def run_login():
    print("🚀 Starting Sniper Login...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        print("🌐 Going to West Contra Costa...")
        page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitAction.do")
        
        print("⏳ Waiting 5 seconds...")
        time.sleep(5)

        # We know from your output that the boxes are in Frame #0 (The Main Frame)
        # So we don't need to loop. We just grab the main frame.
        frame = page.frames[0] 
        
        try:
            print("🎯 Target: #userId")
            # force=True tells it: "I don't care if something is covering the box, click it anyway"
            frame.locator("#userId").click(force=True)
            frame.locator("#userId").fill(SF_USERNAME, force=True)
            print("✅ Username Typed")
            
            print("🎯 Target: #userPin")
            frame.locator("#userPin").click(force=True)
            frame.locator("#userPin").fill(SF_PASSWORD, force=True)
            print("✅ Password Typed")
            
            print("👇 Pressing Enter...")
            frame.locator("#userPin").press("Enter")
            
            # Wait to see success
            time.sleep(10)
            
        except Exception as e:
            # THIS TIME, we print the actual error so we know what broke
            print(f"❌ CRASHED: {e}")

        print("👀 Closing...")
        browser.close()

if __name__ == "__main__":
    run_login()
    