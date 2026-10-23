#!/usr/bin/env python3
"""Inklur inbox queue engine for background email polling and notifications."""

import os
import sqlite3
from contextlib import closing

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("INKLUR_DB_PATH", os.path.join(BASE_DIR, "inklur.db"))


def ensure_inbox_schema():
    """Ensure inbox tracking tables exist in the database."""
    try:
        with closing(sqlite3.connect(DB_PATH, timeout=10)) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS inbox_queue_items (
                    user_email TEXT NOT NULL,
                    email_id TEXT NOT NULL,
                    sender_name TEXT,
                    sender_email TEXT,
                    subject TEXT,
                    snippet TEXT,
                    is_automated INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_email, email_id)
                )"""
            )
            connection.commit()
    except sqlite3.Error:
        pass


def poll_new_emails(user_email):
    """Fetch pending inbox notifications for the user."""
    ensure_inbox_schema()
    try:
        with closing(sqlite3.connect(DB_PATH, timeout=10)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """SELECT email_id, sender_name, sender_email, subject, snippet, is_automated, status 
                   FROM inbox_queue_items 
                   WHERE lower(user_email) = lower(?) AND status = 'pending' 
                   ORDER BY created_at DESC LIMIT 20""",
                (user_email,),
            ).fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error:
        return []


def get_pending_item(user_email, email_id):
    """Get a specific pending email item for review/reply preparation."""
    ensure_inbox_schema()
    try:
        with closing(sqlite3.connect(DB_PATH, timeout=10)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """SELECT email_id, sender_name, sender_email, subject, snippet, is_automated, status 
                   FROM inbox_queue_items 
                   WHERE lower(user_email) = lower(?) AND email_id = ? AND status = 'pending'""",
                (user_email, email_id),
            ).fetchone()
            return dict(row) if row else None
    except sqlite3.Error:
        return None


def ignore_item(user_email, email_id):
    """Mark an inbox notification as dismissed/ignored."""
    ensure_inbox_schema()
    try:
        with closing(sqlite3.connect(DB_PATH, timeout=10)) as connection:
            connection.execute(
                """UPDATE inbox_queue_items SET status = 'ignored' 
                   WHERE lower(user_email) = lower(?) AND email_id = ?""",
                (user_email, email_id),
            )
            connection.commit()
    except sqlite3.Error:
        pass


def mark_sent(user_email, email_id):
    """Mark an inbox notification item as successfully replied/sent."""
    ensure_inbox_schema()
    try:
        with closing(sqlite3.connect(DB_PATH, timeout=10)) as connection:
            connection.execute(
                """UPDATE inbox_queue_items SET status = 'sent' 
                   WHERE lower(user_email) = lower(?) AND email_id = ?""",
                (user_email, email_id),
            )
            connection.commit()
    except sqlite3.Error:
        pass