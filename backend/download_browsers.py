import subprocess
import sys

def install_playwright_browsers():
    print("🚀 Initiating Playwright Browser Setup for Inklur Engine...")
    print("📥 Downloading Chromium, Firefox, and WebKit (This might take a minute or two)...\n")
    
    # Step 1: Execute Playwright Browser Download Command (Installs ALL required browsers)
    cmd = [sys.executable, "-m", "playwright", "install"]
    
    try:
        # capture_output=True hata diya hai taaki terminal me live progress bar (MBs downloading) dikhe
        subprocess.run(cmd, check=True)
        print("\n✅ All Playwright Browser Binaries Successfully Installed & Ready for the Race!")
        
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error Installing Playwright Browser Binaries (Exit Code: {e.returncode})")
        print("\n💡 Troubleshooting Tip 1: Run 'pip install playwright' first if not installed.")
        print("💡 Troubleshooting Tip 2: If on Linux, you might need system dependencies. Run: 'playwright install-deps'")
        
    except Exception as ex:
        print(f"\n❌ Unexpected Error: {str(ex)}")

if __name__ == "__main__":
    install_playwright_browsers()