#!/usr/bin/env python3
"""Download and verify the Chromium binary used by Inklur's Playwright backend.

This is a setup utility only. It does not start/call the local Inklur server and
must not contain the frontend API_BASE URL. The backend automation_engine.py
uses the installed Chromium binary when it launches Playwright.

Usage:
    python download_browsers.py
    python download_browsers.py --with-deps  # Linux only; may install OS packages
"""

import argparse
import importlib.util
import platform
import subprocess
import sys
from importlib import metadata

INSTALL_TIMEOUT_SECONDS = 30 * 60
VERIFY_TIMEOUT_MILLISECONDS = 15_000


def say(message):
    """Print safely on Windows consoles with limited Unicode support."""
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        safe_message = str(message).encode("ascii", "replace").decode("ascii")
        print(safe_message, flush=True)


def playwright_installed():
    try:
        return importlib.util.find_spec("playwright") is not None
    except (ImportError, ValueError):
        return False


def playwright_version():
    try:
        return metadata.version("playwright")
    except metadata.PackageNotFoundError:
        return "unknown"


def verify_chromium():
    """Launch Chromium against about:blank and always close it afterwards."""
    browser = None

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(
                    "about:blank",
                    wait_until="load",
                    timeout=VERIFY_TIMEOUT_MILLISECONDS,
                )
            finally:
                if browser is not None:
                    browser.close()

        return True, None
    except Exception as error:
        return False, error


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Install and verify Playwright Chromium for Inklur."
    )
    parser.add_argument(
        "--with-deps",
        action="store_true",
        help="Also install Linux system dependencies (may require sudo).",
    )
    args = parser.parse_args(argv)

    if args.with_deps and not sys.platform.startswith("linux"):
        parser.error(
            "--with-deps is supported only on Linux. On Windows/macOS, omit it."
        )

    return args


def main(argv=None):
    args = parse_args(argv)
    say("Inklur Playwright Chromium setup")
    say(f"Python executable: {sys.executable}")
    say(f"Operating system: {platform.system()}")

    if not playwright_installed():
        say("Playwright Python package is not installed in this Python environment.")
        say(f'Install it with: "{sys.executable}" -m pip install playwright')
        return 1

    say(f"Playwright version: {playwright_version()}")
    say("Installing Chromium only; Firefox and WebKit are not needed.")

    command = [sys.executable, "-m", "playwright", "install"]
    if args.with_deps:
        command.append("--with-deps")
    command.append("chromium")

    try:
        # Keep stdout attached so Playwright can show live download progress.
        completed = subprocess.run(
            command,
            check=False,
            timeout=INSTALL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        say("Chromium installation timed out after 30 minutes. Check the network and retry.")
        return 1
    except KeyboardInterrupt:
        say("Installation cancelled by the user.")
        return 130
    except OSError as error:
        say(f"Could not start the Playwright installer: {error}")
        return 1

    if completed.returncode != 0:
        say(f"Playwright installer exited with code {completed.returncode}.")
        if sys.platform.startswith("linux") and not args.with_deps:
            say(
                "If Linux system libraries are missing, retry with: "
                "python download_browsers.py --with-deps"
            )
        return completed.returncode or 1

    say("Chromium download finished. Verifying a headless launch...")
    verified, error = verify_chromium()
    if not verified:
        say(f"Chromium could not launch: {error}")
        if sys.platform.startswith("linux") and not args.with_deps:
            say(
                "On Linux, install system libraries with: "
                "python download_browsers.py --with-deps"
            )
        return 1

    say("Chromium installed and verified successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())