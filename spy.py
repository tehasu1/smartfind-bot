from playwright.sync_api import sync_playwright

def find_box_names():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("🕵️‍♀️ Spying on the login page...")
        # Your specific district URL
        page.goto("https://westcontracosta.eschoolsolutions.com/logOnInitActionDiv.do?uiNew=1")
        
        # Find all input boxes
        inputs = page.locator("input").all()
        
        print("\n--- FOUND THESE BOXES ---")
        for i in inputs:
            # Get the 'name', 'id', and 'placeholder' of each box
            name = i.get_attribute("name")
            id_attr = i.get_attribute("id")
            type_attr = i.get_attribute("type")
            
            if type_attr not in ["hidden", "submit"]:
                print(f"Box Type: {type_attr}")
                print(f"  -> Name: {name}")
                print(f"  -> ID:   {id_attr}")
                print("-------------------------")
        
        browser.close()

if __name__ == "__main__":
    find_box_names()