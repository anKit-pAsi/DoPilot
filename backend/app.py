import json
import os
import sqlite3
import requests
import warnings

warnings.filterwarnings("ignore")

from dotenv import load_dotenv
from flask import Flask, jsonify, request, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

from automation_engine import run_browser_automation
import gmail_engine

load_dotenv("Api.env")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dopilot_super_secret_key_123")

CORS(app, supports_credentials=True, resources={r"/api/*": {"origins": "*"}})

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def init_db():
    conn = sqlite3.connect('dopilot.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    conn.commit()
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

    try:
        conn = sqlite3.connect('dopilot.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)", 
                       (name, email, hashed_password))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Account created successfully!"})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Email already registered."}), 400

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    conn = sqlite3.connect('dopilot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, password FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()

    if user and check_password_hash(user[2], password):
        session["user_id"] = user[0]
        session["user_name"] = user[1]
        return jsonify({
            "success": True, 
            "message": "Login successful!",
            "user": {"id": user[0], "name": user[1], "email": email}
        })
    else:
        return jsonify({"success": False, "message": "Invalid email or password."}), 401

@app.route("/api/execute", methods=["POST"])
def execute():
    data = request.get_json(silent=True) or {}
    user_prompt = data.get("prompt", "").strip()

    if not user_prompt:
        return jsonify({"success": False, "message": "Please enter a prompt."}), 400

    prompt_lower = user_prompt.lower()

    # Direct Check: Agar Email / Gmail task hai toh Web Search bypass karein
    if any(k in prompt_lower for k in ["email", "gmail", "mail", "ankit"]):
        # Extract target person dynamically
        target = "user"
        for word in ["from", "to", "for", "name"]:
            if word in prompt_lower.split():
                parts = prompt_lower.split(word)
                if len(parts) > 1:
                    target = parts[1].strip().split()[0]
                    break
        
        gmail_res = gmail_engine.process_user_email_command(target)
        return jsonify({
            "success": True,
            "action_required": False,
            "tool_name": "gmail_automation",
            "result": gmail_res
        })

    # Standard Gemini Intent AI Route
    default_url = "https://www.google.com"
    system_instruction = f"""You are DoPilot, an AI execution assistant created by Ankit Paswan.
Analyze the user's input and classify it into JSON format:

CASE 1: If action requires Web Search or Scraping:
{{
  "action_required": true,
  "tool_name": "web_automation",
  "category": "Web Search",
  "action_title": "Search & Extract Data",
  "message": "I have created an execution plan based on your request. Please approve to proceed.",
  "parameters": [
    {{"label": "URL", "value": "{default_url}"}},
    {{"label": "Query", "value": "{user_prompt}"}}
  ]
}}

CASE 2: General Chat or Information:
{{
  "action_required": false,
  "result": "<Direct Answer>"
}}"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": system_instruction + "\n\nUser Input: " + user_prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024, "response_mime_type": "application/json"}
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        res_data = response.json()

        if response.status_code == 200:
            raw_text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
            parsed_res = json.loads(raw_text)
            return jsonify({"success": True, "action_required": parsed_res.get("action_required", False), "parsed_action": parsed_res, "result": parsed_res.get("result", parsed_res.get("message"))})
        else:
            return jsonify({"success": False, "message": "Gemini API Error"}), response.status_code
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/execute-task", methods=["POST"])
@app.route("/api/run-action", methods=["POST"])
def handle_realtime_execution():
    data = request.get_json(silent=True) or {}
    params = data.get("parameters", [])
    target_url = "https://www.google.com"
    query = "DoPilot AI"

    if isinstance(params, list):
        for p in params:
            if isinstance(p, dict):
                if p.get("label", "").lower() == "url":
                    target_url = p.get("value", target_url)
                elif p.get("label", "").lower() in ["query", "search query"]:
                    query = p.get("value", query)

    result = run_browser_automation(target_url, query)
    return jsonify({"success": True, "data": result})

@app.route("/api/send-email", methods=["POST"])
def send_email_route():
    data = request.get_json(silent=True) or {}
    result = gmail_engine.send_email_direct(data.get("to_email"), data.get("subject", "No Subject"), data.get("body", ""))
    return jsonify(result)

if __name__ == "__main__":
    print("🚀 DoPilot Server Started on http://127.0.0.1:5000")
    app.run(debug=True, port=5000)