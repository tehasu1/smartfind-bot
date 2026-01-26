from playwright.sync_api import sync_playwright

def debug_login():
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        print("🌐 Opening page...")
        page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitActionDiv.do?uiNew=1")
        
        print("🛑 PAUSING! Look for the 'Playwright Inspector' window.")
        # This command freezes the bot and opens the Inspector tools
        page.pause() 

if __name__ == "__main__":
    debug_login()