import os
import json
import sqlite3
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

# Yahan apna wahi email daalna jis se tumne Inklur par signup kiya hai
USER_EMAIL = "ankitpasi628@gmail.com" 

def connect_my_gmail():
    print(f"🚀 Initiating Gmail Connection for {USER_EMAIL}...")
    
    if not os.path.exists('credentials.json'):
        print("❌ Error: 'credentials.json' file nahi mili! Google Cloud Console se file yahan rakho.")
        return

    # Browser me Google Login popup open karega
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)

    token_json = creds.to_json()

    # Token ko direct Inklur Database me save kar dega
    try:
        with sqlite3.connect('inklur.db') as conn:
            cursor = conn.cursor()
            # Check if user exists first
            cursor.execute("SELECT id FROM users WHERE email = ?", (USER_EMAIL,))
            if not cursor.fetchone():
                print(f"❌ Error: {USER_EMAIL} database me nahi hai. Pehle Inklur UI me signup karo.")
                return
                
            cursor.execute("UPDATE users SET gmail_token = ?, is_gmail_connected = 1 WHERE email = ?", (token_json, USER_EMAIL))
            conn.commit()
            
        print(f"✅ Badiya! Gmail successfully connected for {USER_EMAIL}!")
        print("Ab tum Inklur UI me wapas jaa kar AI commands run kar sakte ho.")
        
    except Exception as e:
        print(f"❌ Database update error: {e}")

if __name__ == "__main__":
    connect_my_gmail()