import os
import json
import base64
import sqlite3
import requests
import warnings
from email.utils import parseaddr
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

warnings.filterwarnings("ignore")

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


def get_gmail_service(user_email=None):
    """
    Strictly user ke token ko DB se fetch karta hai. Agar expire ho, toh refresh karke DB me hi wapas save karta hai.
    """
    creds = None
    
    if user_email:
        clean_email = user_email.strip().lower()
        try:
            with sqlite3.connect('inklur.db') as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT gmail_token FROM users WHERE email = ?", (clean_email,))
                row = cursor.fetchone()
                
                if row and row[0]:
                    token_info = json.loads(row[0])
                    creds = Credentials.from_authorized_user_info(token_info, SCOPES)
                else:
                    raise ValueError(f"Gmail is not connected for user: {clean_email}")
        except Exception as e:
            raise ValueError(f"Database error while fetching Gmail token: {e}")
            
    else:
        # Fallback ONLY for server admin / local testing
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        else:
            raise ValueError("No global token.json found. Please authenticate the server first.")

    # Token Refresh & Secure Save Logic
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        
        if user_email:
            with sqlite3.connect('inklur.db') as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET gmail_token = ? WHERE email = ?", (creds.to_json(), clean_email))
                conn.commit()
        else:
            with open('token.json', 'w') as token:
                token.write(creds.to_json())

    if not creds or not creds.valid:
        raise ValueError("Invalid Gmail Credentials. User needs to re-authenticate Gmail.")

    return build('gmail', 'v1', credentials=creds)


def generate_friendly_reply_with_gemini(sender_name, email_subject, email_snippet):
    """
    Gemini 3.8 Flash API se contextual, natural aur friendly reply generate karta hai.
    """
    if not GEMINI_API_KEY:
        return f"Hi {sender_name}, thank you for reaching out regarding '{email_subject}'. I have received your message and will get back to you shortly."

    system_instruction = """You are an AI execution assistant for Inklur.
Read the incoming email snippet and write a polite, natural, friendly, and helpful reply on behalf of the user.
Keep it concise and professional. Do NOT include placeholders like [Your Name] or [Sender Name]. Just provide the final email body."""

    user_content = f"Sender: {sender_name}\nSubject: {email_subject}\nSnippet: {email_snippet}\n\nDraft friendly reply:"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": system_instruction + "\n\n" + user_content}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 256}
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            res_data = response.json()
            return res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
        else:
            print(f"⚠️ Gemini API Error: {response.text}")
    except Exception as e:
        print(f"⚠️ Gemini Reply Generation Warning: {e}")

    return f"Hi {sender_name}, thanks for reaching out regarding '{email_subject}'! I will review this and get back to you soon."


def extract_clean_email(raw_sender):
    """
    Properly extracts email using Python's standard email library.
    """
    name, email_address = parseaddr(raw_sender)
    return email_address if email_address else raw_sender


def check_new_incoming_emails(user_email=None):
    """
    Real-time Polling: Inbox me Unread Emails find karke AI draft tayar karta hai.
    """
    try:
        service = get_gmail_service(user_email=user_email)
        results = service.users().messages().list(userId='me', q='is:unread category:primary', maxResults=1).execute()
        messages = results.get('messages', [])

        if not messages:
            return {"has_new": False}

        msg_id = messages[0]['id']
        message = service.users().messages().get(userId='me', id=msg_id).execute()
        headers = message['payload']['headers']

        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
        sender_raw = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
        snippet = message.get('snippet', '')

        sender_email = extract_clean_email(sender_raw)
        
        parsed_name = parseaddr(sender_raw)[0]
        sender_name = parsed_name if parsed_name else sender_email.split('@')[0]

        proposed_reply = generate_friendly_reply_with_gemini(sender_name, subject, snippet)

        return {
            "has_new": True,
            "email_id": msg_id,
            "sender": sender_name,
            "email": sender_email,
            "subject": subject,
            "snippet": snippet,
            "proposed_reply": proposed_reply
        }

    except ValueError as ve:
        return {"has_new": False, "error": str(ve)}
    except Exception as e:
        return {"has_new": False, "error": f"API Error: {str(e)}"}


def process_user_email_command(target_name, custom_message=None, user_email=None):
    """
    User Prompt aane par target search karta hai aur disambiguation list return karta hai.
    """
    try:
        service = get_gmail_service(user_email=user_email)
        query = f"{target_name}"
        
        results = service.users().messages().list(userId='me', q=query, maxResults=15).execute()
        messages = results.get('messages', [])

        if not messages:
            return {
                "status": "error",
                "message": f"No email found matching '{target_name}'."
            }

        unique_contacts = {}
        
# Har message ka sirf Header (metadata) fetch karo fast processing ke liye
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id'], format='metadata', metadataHeaders=['From', 'Subject']).execute()
            headers = msg_data['payload']['headers']
            
            sender_raw = next((h['value'] for h in headers if h['name'] == 'From'), None)
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            
            if sender_raw:
                sender_email = extract_clean_email(sender_raw)
                parsed_name = parseaddr(sender_raw)[0]
                sender_name = parsed_name if parsed_name else sender_email.split('@')[0]

                # 🚨 FIX 2: STRICT CHECK - Target name MUST be in the sender's real name or email!
                # Isse Instagram wale emails automatically ignore ho jayenge
                if target_name.lower() in sender_name.lower() or target_name.lower() in sender_email.lower():
                    if sender_email not in unique_contacts:
                        unique_contacts[sender_email] = {
                            "name": sender_name,
                            "email": sender_email,
                            "raw_sender": sender_raw,
                            "msg_id": msg['id'],
                            "subject": subject
                        }

        contacts_list = list(unique_contacts.values())

        if len(contacts_list) == 0:
            return {
                "status": "error",
                "message": f"Could not find any exact contact matching '{target_name}'."
            }
        contact = contacts_list[0]
        full_msg = service.users().messages().get(userId='me', id=contact['msg_id']).execute()
        snippet = full_msg.get('snippet', '')

        if custom_message:
            proposed_reply = custom_message
        else:
            proposed_reply = generate_friendly_reply_with_gemini(contact['name'], contact['subject'], snippet)

        return {
            "status": "success",
            "target_person": contact['raw_sender'],
            "target_email": contact['email'],
            "subject": contact['subject'],
            "snippet": snippet,
            "proposed_reply": proposed_reply,
            "message_id": contact['msg_id']
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


def send_email_direct(to_email, subject, body_text, user_email=None):
    """
    User Approval ke baad Email dispatch karta hai.
    """
    try:
        service = get_gmail_service(user_email=user_email)
        clean_to = extract_clean_email(to_email)

        message = MIMEText(body_text)
        message['to'] = clean_to
        message['subject'] = f"Re: {subject}" if not subject.lower().startswith("re:") else subject
        
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        sent = service.users().messages().send(userId='me', body={'raw': raw_message}).execute()

        return {"status": "success", "sent_id": sent['id']}
    except Exception as e:
        return {"status": "error", "error": str(e)}