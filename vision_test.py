from playwright.sync_api import sync_playwright
import time

def run_vision_test():
    print("🚀 Starting Vision Test...")
    
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # Use the specific URL that worked for you before
        print("🌐 Going to West Contra Costa...")
        page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitAction.do")
        
        print("⏳ Waiting 5 seconds for everything to load...")
        time.sleep(5)
        
        print(f"\n🔎 FOUND {len(page.frames)} FRAMES (Windows) on this page.")
        print("Scanning each one for input boxes...\n")
        
        # Loop through every "window" (frame) on the page
        for i, frame in enumerate(page.frames):
            try:
                # Look for ANY input box in this frame
                inputs = frame.locator("input").all()
                
                if len(inputs) > 0:
                    print(f"✅ FRAME #{i}: Found {len(inputs)} boxes!")
                    print(f"   Frame URL: {frame.url}")
                    
                    # Print the details of each box found
                    for box in inputs:
                        name = box.get_attribute("name") or "No Name"
                        box_id = box.get_attribute("id") or "No ID"
                        box_type = box.get_attribute("type") or "text"
                        
                        # We only care about text/password boxes
                        if box_type not in ["hidden", "submit", "checkbox"]:
                            print(f"      👉 Found Box: Type='{box_type}' | Name='{name}' | ID='{box_id}'")
                            
                            # HIGHLIGHT IT so you can see it on screen!
                            box.evaluate("el => el.style.border = '5px solid red'")
                    print("-" * 40)
                    
            except Exception as e:
                print(f"⚠️ Could not scan Frame #{i}: {e}")

        print("\n👀 Check the browser! I highlighted the boxes in RED if I found them.")
        print("Keeping open for 20 seconds...")
        time.sleep(20)
        browser.close()

if __name__ == "__main__":
    run_vision_test()