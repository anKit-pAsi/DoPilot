from automation_engine import run_browser_automation

def test():
    print("🚀 Testing DoPilot Light Execution Engine...")
    result = run_browser_automation("https://html.duckduckgo.com/html/", "DoPilot AI")
    print("\n--- EXECUTION RESULT ---")
    print(result)

if __name__ == "__main__":
    test()