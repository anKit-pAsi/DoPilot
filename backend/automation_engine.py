import sys
import asyncio
import base64
import urllib.parse
from io import BytesIO
from PIL import Image
from playwright.async_api import async_playwright

# Windows Proactor Event Loop fix
if sys.platform == 'win32':
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def execute_single_browser(preferred_url, search_query):
    print("🚀 [Inklur] Launching Direct Playwright Chromium Engine...")
    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1024, 'height': 640},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            target_title = "Inklur Task Execution"
            query_lower = (search_query or "").lower()

            nav_url = ""
            if preferred_url and preferred_url not in ["https://www.google.com", "https://google.com"]:
                nav_url = preferred_url
            else:
                if any(k in query_lower for k in ["song", "songs", "music", "youtube", "viral", "video", "gana", "gaane"]):
                    nav_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(search_query)}"
                elif any(k in query_lower for k in ["epfo", "provident fund", "pf portal"]):
                    nav_url = "https://www.epfindia.gov.in"
                elif any(k in query_lower for k in ["flight", "flights", "airline"]):
                    nav_url = f"https://www.google.com/travel/flights?q={urllib.parse.quote_plus(search_query)}"
                else:
                    nav_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(search_query)}"

            try:
                await page.goto(nav_url, timeout=20000, wait_until="domcontentloaded")
                target_title = await page.title()
            except Exception as e:
                print(f"⚠️ Navigation warning: {e}, opening fallback...")
                await page.goto(f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(search_query)}", timeout=15000)
                target_title = await page.title()

            try:
                await page.wait_for_timeout(3500)
            except:
                pass

            raw_screenshot = await page.screenshot(type="png", full_page=False)
            await browser.close()

            if not raw_screenshot:
                return {"status": "error", "error": "Empty screenshot bytes", "screenshot": None}

            img = Image.open(BytesIO(raw_screenshot))
            img = img.resize((1024, 640), Image.Resampling.LANCZOS)
            
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=75, optimize=True)
            compressed_bytes = buffer.getvalue()
            
            b64_str = base64.b64encode(compressed_bytes).decode("utf-8")
            preview_img = f"data:image/jpeg;base64,{b64_str}"
            
            return {
                "status": "success",
                "engine": "Playwright-Chromium-Direct",
                "page_title": target_title,
                "target_url": page.url,
                "screenshot": preview_img,
                "message": "Successfully captured live browser screenshot!"
            }

        except Exception as e:
            if browser:
                try:
                    await browser.close()
                except:
                    pass
            print(f"❌ Automation Error: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "screenshot": None
            }

def run_browser_automation(preferred_url, search_query):
    try:
        return asyncio.run(execute_single_browser(preferred_url, search_query))
    except Exception as e:
        return {
            "status": "error",
            "error": f"Execution Failed: {str(e)}",
            "screenshot": None
        }