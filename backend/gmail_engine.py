import os
import base64
import warnings
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

warnings.filterwarnings("ignore")

# Read & Send Scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def get_gmail_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


def process_user_email_command(target_name, custom_message=None):
    """
    User jiska bhi naam bolega usko search karega aur custom message generate karega.
    """
    try:
        service = get_gmail_service()
        # Search query based on user target
        query = f"{target_name}"
        
        results = service.users().messages().list(userId='me', q=query, maxResults=1).execute()
        messages = results.get('messages', [])

        if not messages:
            return {
                "status": "error",
                "message": f"No email found for '{target_name}'."
            }

        msg_id = messages[0]['id']
        message = service.users().messages().get(userId='me', id=msg_id).execute()
        headers = message['payload']['headers']
        
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
        sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
        snippet = message.get('snippet', '')

        # User customized message ya default dynamic response
        if custom_message:
            proposed_reply = custom_message
        else:
            proposed_reply = f"Hi {target_name.capitalize()}, thanks for your email regarding '{subject}'. Hope you are doing well!"

        return {
            "status": "success",
            "target_person": sender,
            "subject": subject,
            "snippet": snippet,
            "proposed_reply": proposed_reply,
            "message_id": msg_id
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


def send_email_direct(to_email, subject, body_text):
    """
    Direct Email Bhejega
    """
    try:
        service = get_gmail_service()
        message = MIMEText(body_text)
        message['to'] = to_email
        message['subject'] = f"Re: {subject}" if not subject.startswith("Re:") else subject
        
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        sent = service.users().messages().send(userId='me', body={'raw': raw_message}).execute()

        return {"status": "success", "sent_id": sent['id']}
    except Exception as e:
        return {"status": "error", "error": str(e)}