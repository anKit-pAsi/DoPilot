import subprocess
import sys

def install_playwright_browsers():
    print("Downloading Playwright Chromium Browsers...")
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        print("✅ Chromium Browser Successfully Installed!")
    except Exception as e:
        print("❌ Error installing browser:", e)

if __name__ == "__main__":
    install_playwright_browsers()