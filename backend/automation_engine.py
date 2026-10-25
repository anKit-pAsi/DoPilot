#!/usr/bin/env python3
"""Public-web browser automation used by Inklur's backend.

This module opens a public page and returns a screenshot. It does not click,
submit forms, or call the Inklur frontend API. The Flask app calls
run_browser_automation() after receiving an approved backend action.
"""

import asyncio
import base64
import ipaddress
import socket
import sys
import urllib.parse


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TOTAL_TIMEOUT_SECONDS = 60
NAVIGATION_TIMEOUT_MILLISECONDS = 20_000
DNS_TIMEOUT_SECONDS = 5
SAFE_INLINE_SCHEMES = {"about", "blob", "data"}
GOOGLE_HOME_URLS = {
    "https://www.google.com",
    "https://google.com",
    "http://www.google.com",
    "http://google.com",
    "www.google.com",
    "google.com",
}


if sys.platform == "win32":
    # Playwright launches Chromium subprocesses on Windows.
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except (AttributeError, RuntimeError):
        pass


class AutomationError(RuntimeError):
    """Safe, user-facing error raised by the browser engine."""


def log(message):
    try:
        print(str(message), flush=True)
    except UnicodeEncodeError:
        print(str(message).encode("ascii", "replace").decode("ascii"), flush=True)


def _clean_search_query(value):
    return str(value or "").strip()[:500] or "Inklur AI"


def _is_globally_routable_address(address):
    if address.version == 6 and address.ipv4_mapped:
        address = address.ipv4_mapped

    return (
        address.is_global
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
    )


def validate_http_url(url):
    """Validate URL structure before navigation; network access is checked per request."""
    value = str(url or "").strip()
    if not value or any(ord(char) < 32 for char in value):
        raise AutomationError("The requested website URL is invalid.")

    if "://" not in value:
        value = "https://" + value

    try:
        parsed = urllib.parse.urlsplit(value)
        scheme = parsed.scheme.lower()
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise AutomationError("The requested website URL is invalid.") from None

    if scheme not in {"http", "https"} or not host:
        raise AutomationError("Only public HTTP or HTTPS websites can be opened.")
    if parsed.username or parsed.password:
        raise AutomationError(
            "URLs containing embedded usernames or passwords are not allowed."
        )

    clean_host = host.rstrip(".").lower()
    if (
        clean_host == "localhost"
        or clean_host.endswith(".localhost")
        or clean_host.endswith(".local")
        or clean_host.endswith(".internal")
        or clean_host.endswith(".lan")
    ):
        raise AutomationError("Local and private network addresses are blocked.")

    try:
        literal_address = ipaddress.ip_address(clean_host.split("%", 1)[0])
    except ValueError:
        literal_address = None

    if literal_address is not None and not _is_globally_routable_address(literal_address):
        raise AutomationError("Local and private network addresses are blocked.")

    if port is not None and not 1 <= port <= 65535:
        raise AutomationError("The requested website URL has an invalid port.")

    return value


async def host_is_public(host, port):
    """Allow a host only when all resolved addresses are globally routable."""
    clean_host = str(host or "").rstrip(".").split("%", 1)[0].lower()
    if not clean_host:
        return False

    try:
        try:
            addresses = [ipaddress.ip_address(clean_host)]
        except ValueError:
            loop = asyncio.get_running_loop()
            infos = await asyncio.wait_for(
                loop.getaddrinfo(
                    clean_host,
                    port,
                    type=socket.SOCK_STREAM,
                    proto=socket.IPPROTO_TCP,
                ),
                timeout=DNS_TIMEOUT_SECONDS,
            )
            addresses = [
                ipaddress.ip_address(info[4][0].split("%", 1)[0])
                for info in infos
            ]

        if not addresses:
            return False

        for address in addresses:
            if not _is_globally_routable_address(address):
                return False

        return True

    except (OSError, ValueError, asyncio.TimeoutError):
        return False


async def _abort_request(route):
    try:
        await route.abort("blockedbyclient")
    except Exception:
        # A request can finish while the route callback is handling it.
        pass


def make_request_guard():
    """Route every HTTP(S) request, including redirects and page subresources."""

    async def guard(route):
        try:
            request_url = route.request.url
            parsed = urllib.parse.urlsplit(request_url)
            scheme = parsed.scheme.lower()

            if scheme in SAFE_INLINE_SCHEMES:
                await route.continue_()
                return

            if scheme not in {"http", "https"} or not parsed.hostname:
                await _abort_request(route)
                return

            try:
                port = parsed.port or (443 if scheme == "https" else 80)
            except ValueError:
                await _abort_request(route)
                return

            if await host_is_public(parsed.hostname, port):
                await route.continue_()
            else:
                log("Blocked a request to a non-public network address.")
                await _abort_request(route)

        except Exception:
            # Fail closed: never leave a failed route unresolved or continue it.
            await _abort_request(route)

    return guard


def choose_nav_url(preferred_url, search_query):
    query = _clean_search_query(search_query)
    query_lower = query.casefold()
    preferred = str(preferred_url or "").strip()

    if preferred and preferred.rstrip("/").casefold() not in {
        item.casefold() for item in GOOGLE_HOME_URLS
    }:
        return validate_http_url(preferred)

    if any(
        term in query_lower
        for term in (
            "song",
            "songs",
            "music",
            "youtube",
            "viral",
            "video",
            "gana",
            "gaane",
        )
    ):
        url = (
            "https://www.youtube.com/results?search_query="
            + urllib.parse.quote_plus(query)
        )
    elif any(
        term in query_lower
        for term in ("epfo", "provident fund", "pf portal")
    ):
        url = "https://www.epfindia.gov.in"
    elif any(
        term in query_lower
        for term in ("flight", "flights", "airline")
    ):
        url = (
            "https://www.google.com/travel/flights?q="
            + urllib.parse.quote_plus(query)
        )
    else:
        url = (
            "https://html.duckduckgo.com/html/?q="
            + urllib.parse.quote_plus(query)
        )

    return validate_http_url(url)


async def execute_single_browser(preferred_url, search_query):
    query = _clean_search_query(search_query)
    navigation_url = choose_nav_url(preferred_url, query)

    try:
        from playwright.async_api import async_playwright
    except ImportError as error:
        raise AutomationError(
            "Playwright is not installed. Run: python -m pip install playwright"
        ) from error

    browser = None
    context = None

    try:
        async with async_playwright() as playwright:
            try:
                browser = await playwright.chromium.launch(headless=True)
            except Exception as error:
                raise AutomationError(
                    "Chromium is not installed. Run: python download_browsers.py"
                ) from error

            try:
                context = await browser.new_context(
                    viewport={"width": 1024, "height": 640},
                    user_agent=USER_AGENT,
                    accept_downloads=False,
                    service_workers="block",
                )
                context.set_default_timeout(10_000)
                await context.route("**/*", make_request_guard())

                page = await context.new_page()
                page.set_default_navigation_timeout(
                    NAVIGATION_TIMEOUT_MILLISECONDS
                )

                try:
                    await page.goto(
                        navigation_url,
                        timeout=NAVIGATION_TIMEOUT_MILLISECONDS,
                        wait_until="domcontentloaded",
                    )
                except Exception as error:
                    # Avoid logging full URLs, query strings, or page content.
                    raise AutomationError(
                        "The requested public page could not be opened "
                        f"({type(error).__name__})."
                    ) from None

                try:
                    await page.wait_for_timeout(800)
                    page_title = (await page.title()) or "Inklur Browser Task"
                except Exception:
                    page_title = "Inklur Browser Task"

                final_url = page.url
                try:
                    page_text = await page.locator("body").inner_text(timeout=3000)
                    page_text = str(page_text)[:6000]
                except Exception:
                    page_text = ""

                screenshot = await page.screenshot(
                    type="jpeg",
                    quality=70,
                    full_page=False,
                )
                if not screenshot:
                    raise AutomationError("The page screenshot could not be created.")

                screenshot_data = base64.b64encode(screenshot).decode("ascii")
                return {
                    "status": "success",
                    "engine": "Playwright-Chromium",
                    "page_title": str(page_title)[:200],
                    "target_url": final_url,
                    "page_text": page_text,
                    "screenshot": "data:image/jpeg;base64," + screenshot_data,
                    "message": "Public page opened and screenshot captured.",
                }

            finally:
                if context is not None:
                    try:
                        await context.close()
                    except Exception:
                        pass

                if browser is not None:
                    try:
                        await browser.close()
                    except Exception:
                        pass

    except AutomationError:
        raise
    except Exception as error:
        log(f"Browser automation failed ({type(error).__name__}).")
        raise AutomationError(
            "Browser automation failed. Please try again."
        ) from None


async def _run_with_timeout(preferred_url, search_query):
    try:
        return await asyncio.wait_for(
            execute_single_browser(preferred_url, search_query),
            timeout=TOTAL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        raise AutomationError(
            "The browser task timed out. Please try again."
        ) from None


def run_browser_automation(preferred_url, search_query):
    """Synchronous entry point used by app.py."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise AutomationError(
            "This synchronous browser entry point cannot run inside an active event loop."
        )

    try:
        return asyncio.run(
            _run_with_timeout(preferred_url, search_query)
        )
    except AutomationError as error:
        log(str(error))
        raise
    except Exception as error:
        log(f"Browser automation failed ({type(error).__name__}).")
        raise AutomationError(
            "Browser automation failed. Please try again."
        ) from None


if __name__ == "__main__":
    print("automation_engine.py is imported by app.py; use download_browsers.py to install Chromium.")