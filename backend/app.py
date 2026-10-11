import json
import os
import sqlite3
import requests
import warnings
import traceback

warnings.filterwarnings("ignore")

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

# Importing Custom Engines
import automation_engine
import gmail_engine

load_dotenv("Api.env")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "inklur_super_secret_key_123")

CORS(app, supports_credentials=True, resources={r"/api/*": {"origins": "*"}})

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def init_db():
    conn = None
    try:
        conn = sqlite3.connect('inklur.db')
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                gmail_token TEXT,
                is_gmail_connected INTEGER DEFAULT 0
            )
        ''')
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        if "gmail_token" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN gmail_token TEXT")
        if "is_gmail_connected" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN is_gmail_connected INTEGER DEFAULT 0")
        conn.commit()
    except Exception as e:
        print(f"Database Init Error: {e}")
    finally:
        if conn:
            conn.close()

init_db()

@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not name or not email or not password:
        return jsonify({"success": False, "message": "All fields are required."}), 400

    hashed_password = generate_password_hash(password)
    conn = None
    try:
        conn = sqlite3.connect('inklur.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)", (name, email, hashed_password))
        conn.commit()
        return jsonify({"success": True, "message": "Account created successfully!"})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Email already registered."}), 400
    except Exception as e:
        return jsonify({"success": False, "message": "Internal Server Error."}), 500
    finally:
        if conn:
            conn.close()

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password are required."}), 400

    conn = None
    try:
        conn = sqlite3.connect('inklur.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, password, is_gmail_connected FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
    except Exception as e:
        return jsonify({"success": False, "message": "Database error during login."}), 500
    finally:
        if conn:
            conn.close()

    if user and check_password_hash(user[2], password):
        return jsonify({
            "success": True, 
            "message": "Login successful!",
            "user": {
                "id": user[0], 
                "name": user[1], 
                "email": email,
                "is_gmail_connected": bool(user[3]) if len(user) > 3 and user[3] else False
            }
        })
    else:
        return jsonify({"success": False, "message": "Invalid email or password."}), 401

@app.route("/api/execute", methods=["POST"])
def execute():
    data = request.get_json(silent=True) or {}
    user_prompt = data.get("prompt", "").strip()
    user_email = data.get("user_id") 

    if not user_prompt:
        return jsonify({"success": False, "message": "Please enter a prompt."}), 400

    prompt_lower = user_prompt.lower()

    def run_smart_fallback(reason=""):
        print(f"⚠️ Using Smart Fallback due to: {reason}")
        gmail_keywords = ["send email", "email to", "mail to", "send an email", "check email", "read email"]
        if any(kw in prompt_lower for kw in gmail_keywords):
            target = "user"
            for word in [" to ", " from ", " for "]:
                if word in prompt_lower:
                    parts = prompt_lower.split(word)
                    if len(parts) > 1:
                        target = parts[1].strip().split()[0]
                        break
            try:
                gmail_res = gmail_engine.process_user_email_command(target, user_email=user_email)
                return jsonify({"success": True, "action_required": False, "tool_name": "gmail_automation", "result": gmail_res})
            except Exception as e:
                return jsonify({"success": True, "action_required": False, "tool_name": "gmail_automation", "result": f"Opened Gmail dashboard. Target: {target}"})

        return jsonify({
            "success": True,
            "action_required": True,
            "parsed_action": {
                "action_required": True,
                "tool_name": "web_automation",
                "category": "Web Search",
                "action_title": "Search & Extract Data",
                "message": "Executed via Smart Fallback Engine.",
                "parameters": [
                    {"label": "URL", "value": "https://www.google.com"},
                    {"label": "Query", "value": user_prompt}
                ]
            },
            "result": "Task routed successfully via fallback engine."
        })

    if not GEMINI_API_KEY:
        return run_smart_fallback("API Key missing")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GEMINI_API_KEY}",
        "HTTP-Referer": "https://inklur.local",
        "X-Title": "Inklur AI",
        "Content-Type": "application/json"
    }

    system_instruction = """You are Inklur, an autonomous AI execution assistant. Classify input strictly into JSON:
CASE 1 (Web Search / Scraping): {"action_required": true, "tool_name": "web_automation", "action_title": "Search & Extract Data", "message": "Fetching live data...", "parameters": [{"label": "URL", "value": "https://www.google.com"}, {"label": "Query", "value": "core query details"}]}
CASE 2 (Email): {"action_required": false, "tool_name": "gmail_automation", "target_name": "name"}
CASE 3 (Chat): {"action_required": false, "tool_name": "chat", "result": "answer"}"""

    payload = {
        "model": "openrouter/free",
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 512
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        if response.status_code != 200:
            return run_smart_fallback(f"API Status Code {response.status_code}")

        res_data = response.json()
        if "choices" in res_data:
            raw_text = res_data["choices"][0]["message"]["content"].strip()
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()
                
            parsed_res = json.loads(raw_text)
            
            if parsed_res.get("tool_name") == "gmail_automation":
                target = parsed_res.get("target_name", "user").strip()
                try:
                    gmail_res = gmail_engine.process_user_email_command(target, user_email=user_email)
                    return jsonify({"success": True, "action_required": False, "tool_name": "gmail_automation", "result": gmail_res})
                except:
                    pass

            return jsonify({
                "success": True, 
                "action_required": parsed_res.get("action_required", False), 
                "parsed_action": parsed_res, 
                "result": parsed_res.get("result", parsed_res.get("message", "Task processed."))
            })
        else:
            return run_smart_fallback("Invalid JSON structure")
    except Exception as e:
        return run_smart_fallback(str(e))

@app.route("/api/execute-task", methods=["POST"])
@app.route("/api/run-action", methods=["POST"])
def handle_realtime_execution():
    data = request.get_json(silent=True) or {}
    params = data.get("parameters", [])
    target_url = "https://www.google.com"
    query = "Inklur AI"

    if isinstance(params, list):
        for p in params:
            if isinstance(p, dict):
                label = p.get("label", "").lower()
                if label == "url":
                    target_url = p.get("value", target_url)
                elif label in ["query", "search query"]:
                    query = p.get("value", query)

    try:
        result = automation_engine.run_browser_automation(target_url, query)
        return jsonify({
            "success": True, 
            "screenshot": result.get("screenshot") if isinstance(result, dict) else None,
            "data": result
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/check-email-notifications", methods=["POST"])
def check_email_notifications():
    data = request.get_json(silent=True) or {}
    user_email = data.get("user_email")
    if not user_email:
        return jsonify({"success": False, "error": "User email missing"}), 400

    try:
        unread_data = gmail_engine.check_new_incoming_emails(user_email=user_email)
        if unread_data and unread_data.get("has_new"):
            return jsonify({"success": True, "has_notification": True, "data": unread_data})
        return jsonify({"success": True, "has_notification": False})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/send-email", methods=["POST"])
def send_email_route():
    data = request.get_json(silent=True) or {}
    user_email = data.get("user_email")
    to_email = data.get("to_email")
    
    if not to_email:
        return jsonify({"success": False, "error": "Target email is required"}), 400

    try:
        result = gmail_engine.send_email_direct(
            to_email, 
            data.get("subject", "No Subject"), 
            data.get("body", ""),
            user_email=user_email
        )
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    print("🚀 Inklur Server Started on http://127.0.0.1:5000")
    app.run(debug=True, port=5000)