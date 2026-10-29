#!/usr/bin/env python3
"""Inklur backend tests. backend folder me chalao: python test_run.py

Temporary database use hota hai. AI, Gmail aur browser calls fake hote hain,
isliye koi real email nahi jaata aur koi paid API call nahi hoti.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_DIR = Path(__file__).resolve().parent
TEMP_DIR = tempfile.mkdtemp(prefix="inklur-test-")

# App import se pehle environment set karo
os.environ["INKLUR_DB_PATH"] = str(Path(TEMP_DIR) / "test_inklur.db")
os.environ["DOPILOT_DB_PATH"] = str(Path(TEMP_DIR) / "no_legacy.db")
os.environ["SECRET_KEY"] = "test-only-secret"
os.environ["GEMINI_API_KEY"] = ""
os.environ["OPENROUTER_API_KEY"] = ""

sys.path.insert(0, str(PROJECT_DIR))
import app as inklur  # noqa: E402
from automation_engine import _submitted_values_visible  # noqa: E402

PASSWORD = "safe-test-password-123"


class InklurApiTests(unittest.TestCase):
    def test_submission_verification_accepts_values_and_new_confirmation(self):
        before = "Form ready"
        after = "Inklur Test User inklur.test@example.com Mirzapur, Uttar Pradesh Thanks for submitting"
        self.assertTrue(_submitted_values_visible(
            before, after,
            ["Inklur Test User", "inklur.test@example.com", "Mirzapur, Uttar Pradesh"],
            "Thanks for submitting",
        ))

    def test_submission_verification_rejects_missing_value(self):
        before = "Form ready"
        after = "Inklur Test User inklur.test@example.com Thanks for submitting"
        self.assertFalse(_submitted_values_visible(
            before, after,
            ["Inklur Test User", "inklur.test@example.com", "Mirzapur, Uttar Pradesh"],
            "Thanks for submitting",
        ))

    def test_submission_verification_rejects_confirmation_already_visible(self):
        before = "Thanks for submitting"
        after = "Inklur Test User inklur.test@example.com Thanks for submitting"
        self.assertFalse(_submitted_values_visible(
            before, after, ["Inklur Test User", "inklur.test@example.com"],
            "Thanks for submitting",
        ))

    def test_submission_verification_allows_preexisting_field_values_if_confirmation_is_new(self):
        before = "Option Inklur Test User"
        after = "Option Inklur Test User Thanks for submitting"
        self.assertTrue(_submitted_values_visible(
            before, after, ["Inklur Test User"], "Thanks for submitting",
        ))

    def test_submission_verification_rejects_empty_values(self):
        self.assertFalse(_submitted_values_visible("Before", "After", [], "Thanks"))


    def setUp(self):
        inklur.app.config.update(TESTING=True)
        self.client = inklur.app.test_client()
        self.email = "tester_%s@example.com" % os.urandom(4).hex()

    def signup_and_login(self):
        signup = self.client.post("/api/signup", json={
            "name": "Tester", "email": self.email, "password": PASSWORD,
        })
        self.assertEqual(signup.status_code, 200)
        login = self.client.post("/api/login", json={
            "email": self.email, "password": PASSWORD,
        })
        self.assertEqual(login.status_code, 200)
        return login

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])

    def test_login_sets_httponly_cookie_and_session_persists(self):
        login = self.signup_and_login()
        cookie_header = login.headers.get("Set-Cookie", "")
        self.assertIn(inklur.SESSION_COOKIE_NAME, cookie_header)
        self.assertIn("HttpOnly", cookie_header)
        self.assertNotIn("token", login.get_json()["user"])

        me = self.client.get("/api/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.get_json()["user"]["email"], self.email)

    def test_logout_ends_session(self):
        self.signup_and_login()
        self.assertEqual(self.client.post("/api/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/me").status_code, 401)

    def test_wrong_password_rejected(self):
        self.client.post("/api/signup", json={
            "name": "Tester", "email": self.email, "password": PASSWORD,
        })
        response = self.client.post("/api/login", json={
            "email": self.email, "password": "wrong-password",
        })
        self.assertEqual(response.status_code, 401)

    def test_chat_prompt_returns_no_approval_card(self):
        self.signup_and_login()
        with mock.patch.object(inklur, "call_llm_json", return_value=(
            {"action_required": False, "result": "Hello!"}, None,
        )):
            response = self.client.post("/api/execute", json={"prompt": "hi, kaise ho?"})
        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(data["action_required"])
        self.assertEqual(data["result"], "Hello!")

    def test_web_prompt_returns_approval_card(self):
        self.signup_and_login()
        plan = {
            "action_required": True,
            "tool_name": "web_automation",
            "action_title": "Search public web",
            "message": "Review",
            "parameters": [{"label": "Query", "value": "AI tools"}],
        }
        with mock.patch.object(inklur, "call_llm_json", return_value=(plan, None)):
            response = self.client.post("/api/execute", json={"prompt": "web se AI tools dhoondo"})
        data = response.get_json()
        self.assertTrue(data["action_required"])
        self.assertEqual(data["tool_name"], "web_automation")
        labels = [p["label"] for p in data["parsed_action"]["parameters"]]
        self.assertIn("URL", labels)

    def test_email_prompt_requires_login(self):
        response = self.client.post("/api/execute", json={"prompt": "Alice se email dikhao"})
        self.assertEqual(response.status_code, 401)

    def test_email_word_alone_is_not_gmail_search(self):
        self.signup_and_login()
        with mock.patch.object(inklur, "call_llm_json", return_value=(
            {"action_required": False, "result": "Email is electronic mail."}, None,
        )), mock.patch.object(inklur.gmail_engine, "process_user_email_command") as gmail:
            response = self.client.post("/api/execute", json={"prompt": "email kya hota hai?"})
        self.assertEqual(response.get_json()["tool_name"], "chat")
        gmail.assert_not_called()

    def test_email_search_routes_to_gmail_engine(self):
        self.signup_and_login()
        fake_result = {"status": "success", "target_email": "alice@example.com"}
        with mock.patch.object(
            inklur.gmail_engine, "process_user_email_command", return_value=fake_result
        ) as gmail:
            response = self.client.post("/api/execute", json={"prompt": "Find email from Alice"})
        self.assertEqual(response.get_json()["tool_name"], "gmail_automation")
        gmail.assert_called_once()

    def test_browser_task_requires_login(self):
        response = self.client.post("/api/execute-task", json={"parameters": []})
        self.assertEqual(response.status_code, 401)

    def test_browser_task_runs_for_logged_in_user(self):
        self.signup_and_login()

        plan = {
            "action_required": True,
            "tool_name": "web_automation",
            "action_title": "Search public web",
            "message": "Review",
            "parameters": [{"label": "Query", "value": "test"}],
        }

        with mock.patch.object(
            inklur, "call_llm_json", return_value=(plan, None)
        ):
            approval_response = self.client.post(
                "/api/execute",
                json={"prompt": "web par test search karo"},
            )

        self.assertEqual(approval_response.status_code, 200)
        approval_data = approval_response.get_json()
        approval_id = approval_data["approval_id"]
        self.assertTrue(approval_id)

        fake = {
            "status": "success",
            "screenshot": "data:image/jpeg;base64,AAAA",
        }

        with mock.patch.object(
            inklur, "run_browser_automation", return_value=fake
        ) as browser:
            response = self.client.post(
                "/api/execute-task",
                json={"approval_id": approval_id},
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["screenshot"], "data:image/jpeg;base64,AAAA")
        self.assertNotIn("screenshot", data["data"])
        browser.assert_called_once()
    def test_check_email_requires_login(self):
        response = self.client.post("/api/check-email-notifications", json={})
        self.assertEqual(response.status_code, 401)

    def test_check_email_returns_items_for_logged_in_user(self):
        self.signup_and_login()
        with mock.patch.object(inklur.inbox_queue, "poll_new_emails", return_value=[
            {"email_id": "abc123def456", "sender_name": "Bob", "sender_email": "bob@example.com",
             "subject": "Hi", "snippet": "Hello", "is_automated": False},
        ]):
            response = self.client.post("/api/check-email-notifications", json={})
        data = response.get_json()
        self.assertTrue(data["has_notification"])
        self.assertEqual(data["items"][0]["email_id"], "abc123def456")

    def test_dismiss_and_prepare_reject_bad_email_id(self):
        self.signup_and_login()
        bad = self.client.post("/api/dismiss-email-notification", json={"email_id": "../../x"})
        self.assertEqual(bad.status_code, 400)
        bad = self.client.post("/api/prepare-email-reply", json={"email_id": "x y"})
        self.assertEqual(bad.status_code, 400)

    def test_send_email_requires_login(self):
        response = self.client.post("/api/send-email", json={
            "to_email": "bob@example.com", "subject": "Hi", "body": "Hello",
        })
        self.assertEqual(response.status_code, 401)

    def test_send_email_without_approval_is_blocked(self):
        self.signup_and_login()
        with mock.patch.object(inklur.gmail_engine, "send_email_direct") as sender:
            response = self.client.post("/api/send-email", json={
                "to_email": "bob@example.com",
                "subject": "Hi",
                "body": "Hello",
            })
        self.assertEqual(response.status_code, 403)
        sender.assert_not_called()

    def test_email_approval_rejects_changed_content(self):
        self.signup_and_login()
        content = {
            "to_email": "bob@example.com",
            "subject": "Approved subject",
            "body": "Approved body",
            "email_id": None,
        }
        approval = self.client.post("/api/approve-email-send", json=content)
        self.assertEqual(approval.status_code, 200)
        approval_id = approval.get_json()["approval_id"]

        changed = dict(content)
        changed["body"] = "Changed after approval"
        with mock.patch.object(inklur.gmail_engine, "send_email_direct") as sender:
            response = self.client.post("/api/send-email", json={
                **changed, "approval_id": approval_id,
            })
        self.assertEqual(response.status_code, 403)
        sender.assert_not_called()

    def test_email_approval_can_only_be_used_once(self):
        self.signup_and_login()
        content = {
            "to_email": "bob@example.com",
            "subject": "One-time test",
            "body": "Test body",
            "email_id": None,
        }
        approval = self.client.post("/api/approve-email-send", json=content)
        self.assertEqual(approval.status_code, 200)
        approval_id = approval.get_json()["approval_id"]

        with mock.patch.object(
            inklur.gmail_engine,
            "send_email_direct",
            return_value={"status": "success"},
        ) as sender:
            first = self.client.post("/api/send-email", json={
                **content, "approval_id": approval_id,
            })
            second = self.client.post("/api/send-email", json={
                **content, "approval_id": approval_id,
            })

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(sender.call_count, 1)


    def test_unknown_endpoint_returns_json(self):
        response = self.client.get("/api/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.get_json()["success"])


if __name__ == "__main__":
    unittest.main(verbosity=2)