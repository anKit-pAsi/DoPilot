import json
from automation_engine import run_browser_automation

def test():
    print("🚀 Testing Inklur AI Execution Engine (Playwright)...")
    
    # Run the race among Playwright browsers
    result = run_browser_automation("https://google.com", "Inklur AI automation")
    
    print("\n--- ⚡ EXECUTION RESULT ---")
    
    # 🚨 FIX: Terminal Spam Protection
    # Agar screenshot generated hai, toh uski lambi string ko terminal pe truncate kar do
    if isinstance(result, dict) and result.get("screenshot"):
        # Hum asli result ko change nahi kar rahe, sirf print karne ke liye ek copy bana rahe hain
        print_safe_result = result.copy()
        print_safe_result["screenshot"] = result["screenshot"][:60] + "... [BASE64 IMAGE DATA HIDDEN FOR TERMINAL READABILITY]"
    else:
        print_safe_result = result

    # Pretty-print the result (indent=4 makes it look neat and readable)
    print(json.dumps(print_safe_result, indent=4))

if __name__ == "__main__":
    test()