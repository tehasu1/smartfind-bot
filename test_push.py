import http.client
import urllib.parse
import ssl
import os
from dotenv import load_dotenv # New tool to read the .env file

# 1. Load the secrets from the .env file
load_dotenv()

# 2. Automatically grab the keys
USER_KEY = os.getenv("PUSHOVER_USER")
API_TOKEN = os.getenv("PUSHOVER_TOKEN")

def send_test_notification():
    # Safety Check: Did it find the keys?
    if not USER_KEY or not API_TOKEN:
        print("❌ Error: Could not find keys in .env file!")
        print("Make sure your .env file is saved and has PUSHOVER_USER and PUSHOVER_TOKEN inside.")
        return

    print("🚀 Attempting to send message...")
    
    # SSL Bypass (for Mac)
    context = ssl._create_unverified_context()
    
    conn = http.client.HTTPSConnection("api.pushover.net:443", context=context)
    
    payload = urllib.parse.urlencode({
        "token": API_TOKEN,
        "user": USER_KEY,
        "message": "✅ It works! Reading keys automatically from .env",
        "title": "VS Code Success"
    })
    
    headers = { "Content-type": "application/x-www-form-urlencoded" }
    
    try:
        conn.request("POST", "/1/messages.json", payload, headers)
        response = conn.getresponse()
        
        if response.status == 200:
            print("✅ Message sent successfully!")
        else:
            print(f"⚠️ Failed. Server said: {response.status} {response.reason}")
            print(response.read().decode())
            
    except Exception as e:
        print(f"❌ Connection Error: {e}")

if __name__ == "__main__":
    send_test_notification()