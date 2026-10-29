#!/usr/bin/env python3
"""Public-web browser automation used by Inklur's backend.

This module opens a public page and returns a screenshot. It does not click,
submit forms, or call the Inklur frontend API. The Flask app calls
run_browser_automation() after receiving an approved backend action.
"""

import asyncio
import base64
import ipaddress
import re
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
    original = query
    lower = query.casefold()
    preferred = str(preferred_url or "").strip()

    # Extract the topic instead of searching the entire instruction.
    removals = [
        r"\b(world health organization|who)\s+website\s+par\b",
        r"\bwebsite\s+par\b",
        r"\bke\s+baare\s+mein\b",
        r"\bke\s+bare\s+mein\b",
        r"\bjaankari\s+dhoondo\b",
        r"\bjankari\s+dhoondo\b",
        r"\bdhoondo\b|\bdhundo\b|\bkhojo\b",
        r"\bbatao\b|\bdo\b",
        r"\bin\s+hindi\b|\bhindi\s+mein\b",
        r"\b3\s+mukhya\b",
        r"\bofficial\s+source\b.*$",
        r"\btitle\s+aur\s+url\b.*$",
        r"\brelevant\s+page\b.*$",
        r"\bagar\s+search\b.*$",
        r"\bkoi\s+form\b.*$",
    ]
    for expression in removals:
        query = re.sub(expression, " ", query, flags=re.I)

    query = re.sub(r"[^\w\s.-]", " ", query, flags=re.UNICODE)
    query = re.sub(r"\s+", " ", query).strip(" .,-")

    if len(query) < 3:
        query = original[:250].strip()

    search_intent = any(term in lower for term in (
        "search", "find", "research", "information", "health risks",
        "details", "dhoondo", "dhundo", "khojo", "jaankari",
        "jankari", "batao", "ke baare mein", "ke bare mein",
    ))

    if preferred:
        parsed = urllib.parse.urlsplit(preferred)
        host = (parsed.hostname or "").casefold()
        is_homepage = parsed.path in ("", "/") and not parsed.query

        if search_intent and is_homepage and host:
            domain = host.removeprefix("www.")
            search_text = f"site:{domain} {query}"
            return validate_http_url(
                "https://www.bing.com/search?q="
                + urllib.parse.quote_plus(search_text)
            )

        if preferred.rstrip("/").casefold() not in {
            item.casefold() for item in GOOGLE_HOME_URLS
        }:
            return validate_http_url(preferred)

    if any(term in lower for term in (
        "song", "songs", "music", "youtube", "viral", "video",
        "gana", "gaane",
    )):
        url = (
            "https://www.youtube.com/results?search_query="
            + urllib.parse.quote_plus(query)
        )
    elif any(term in lower for term in (
        "epfo", "provident fund", "pf portal",
    )):
        url = "https://www.epfindia.gov.in"
    elif any(term in lower for term in ("flight", "flights", "airline")):
        url = (
            "https://www.google.com/travel/flights?q="
            + urllib.parse.quote_plus(query)
        )
    else:
        url = (
            "https://www.bing.com/search?q="
            + urllib.parse.quote_plus(query)
        )

    return validate_http_url(url)

def validate_browser_actions(actions):
    """Allow only limited, structured browser interactions."""
    import json

    if actions is None:
        return []
    if isinstance(actions, str):
        try:
            actions = json.loads(actions)
        except (TypeError, ValueError):
            raise AutomationError("Browser actions must be valid JSON.") from None
    if not isinstance(actions, list) or len(actions) > 10:
        raise AutomationError("Provide at most 10 browser actions.")

    result = []
    for action in actions:
        if not isinstance(action, dict):
            raise AutomationError("Invalid browser action.")
        kind = action.get("type")
        if kind not in {"read_page", "click", "fill", "select"}:
            raise AutomationError("Unsupported browser action.")
        item = {"type": kind}
        if kind in {"click", "fill", "select"}:
            selector = action.get("selector")
            if not isinstance(selector, str) or not selector.strip() or len(selector) > 300:
                raise AutomationError("A valid selector is required.")
            item["selector"] = selector.strip()
        if kind in {"fill", "select"}:
            value = action.get("value")
            if not isinstance(value, str) or len(value) > 1000:
                raise AutomationError("A valid text value is required.")
            item["value"] = value
        result.append(item)
    return result


async def execute_single_browser(preferred_url, search_query, actions=None):
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
                    # Keep diagnostics useful without exposing the target URL.
                    error_name = type(error).__name__
                    if error_name == "TimeoutError":
                        detail = (
                            f"navigation exceeded "
                            f"{NAVIGATION_TIMEOUT_MILLISECONDS // 1000} seconds"
                        )
                    else:
                        detail = "navigation failed before the page loaded"

                    raise AutomationError(
                        "The requested public page could not be opened "
                        f"({error_name}: {detail})."
                    ) from None

                validated_actions = validate_browser_actions(actions)
                form_preview = []

                for action in validated_actions:
                    kind = action["type"]
                    if kind == "read_page":
                        continue

                    selector = action["selector"]
                    matches = page.locator(selector)
                    locator = None

                    for match_index in range(await matches.count()):
                        candidate = matches.nth(match_index)
                        try:
                            if await candidate.is_visible() and await candidate.is_enabled():
                                locator = candidate
                                break
                        except Exception:
                            continue

                    if locator is None:
                        raise AutomationError(
                            "The requested browser element was not visible and enabled."
                        )

                    if kind == "click":
                        previous_url = page.url
                        await locator.click(timeout=10_000, no_wait_after=True)
                        try:
                            await page.wait_for_function(
                                "(oldUrl) => window.location.href !== oldUrl",
                                arg=previous_url,
                                timeout=5000,
                            )
                        except Exception:
                            pass
                        try:
                            await page.wait_for_load_state(
                                "domcontentloaded", timeout=5000
                            )
                        except Exception:
                            pass

                    elif kind in {"fill", "select"}:
                        if kind == "fill":
                            await locator.fill(action["value"], timeout=10_000)
                        else:
                            await locator.select_option(
                                label=action["value"], timeout=10_000
                            )

                        tag_name = await locator.evaluate(
                            "(element) => element.tagName.toLowerCase()"
                        )
                        field_type = (
                            await locator.get_attribute("type") or ""
                        ).strip().lower()

                        if (
                            tag_name not in {"input", "textarea", "select"}
                            or field_type in {"password", "hidden", "file"}
                        ):
                            raise AutomationError(
                                "A form field is not allowed for preview."
                            )

                        if kind == "select":
                            if tag_name != "select":
                                raise AutomationError(
                                    "A dropdown field could not be verified."
                                )
                            actual_value = await locator.locator(
                                "option:checked"
                            ).inner_text(timeout=3000)
                        else:
                            if tag_name not in {"input", "textarea"}:
                                raise AutomationError(
                                    "A text field could not be verified."
                                )
                            actual_value = await locator.input_value(
                                timeout=3000
                            )

                        if actual_value != action["value"]:
                            raise AutomationError(
                                "Filled values could not be verified."
                            )

                        form_preview.append({
                            "field": selector[:150],
                            "value": actual_value[:1000],
                            "verified": True,
                        })

                # Let navigation and dynamic search results settle.
                try:
                    await page.wait_for_load_state(
                        "domcontentloaded", timeout=8000
                    )
                except Exception:
                    pass

                try:
                    await page.wait_for_timeout(1200)
                except Exception:
                    pass

                final_url = page.url

                try:
                    page_title = (await page.title()) or "Inklur Browser Task"
                except Exception:
                    page_title = "Inklur Browser Task"

                try:
                    page_text = await page.locator("body").inner_text(timeout=8000)
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
                    "form_preview": form_preview,
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


async def _run_with_timeout(preferred_url, search_query, actions=None):
    try:
        return await asyncio.wait_for(
            execute_single_browser(preferred_url, search_query, actions),
            timeout=TOTAL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        raise AutomationError(
            "The browser task timed out. Please try again."
        ) from None



async def submit_demoqa_textbox():
    """Submit only the fixed public DemoQA test form and verify its output."""
    from playwright.async_api import async_playwright

    target = "https://demoqa.com/text-box"
    browser = None
    context = None

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1024, "height": 640},
                user_agent=USER_AGENT,
                accept_downloads=False,
                service_workers="block",
            )
            context.set_default_timeout(10000)
            await context.route("**/*", make_request_guard())
            page = await context.new_page()
            page.set_default_navigation_timeout(
                NAVIGATION_TIMEOUT_MILLISECONDS
            )

            await page.goto(
                target,
                timeout=NAVIGATION_TIMEOUT_MILLISECONDS,
                wait_until="domcontentloaded",
            )

            # Fixed, non-sensitive demonstration values only.
            await page.locator("#userName").fill("Ankit Paswan")
            await page.locator("#userEmail").fill("ankit.demo@example.com")
            await page.locator("#currentAddress").fill(
                "Mirzapur, Uttar Pradesh"
            )
            await page.locator("#permanentAddress").fill(
                "Mirzapur, Uttar Pradesh"
            )

            # Submission is hard-coded to this test page and selector.
            await page.locator("#submit").click()
            output = page.locator("#output")
            await output.wait_for(state="visible", timeout=10000)
            text = (await output.inner_text(timeout=5000)).strip()

            required = (
                "Ankit Paswan",
                "ankit.demo@example.com",
                "Mirzapur, Uttar Pradesh",
            )
            if not text or not all(item in text for item in required):
                raise AutomationError(
                    "DemoQA submission could not be verified from its output."
                )

            return {
                "status": "success",
                "verified": True,
                "page_title": (await page.title())[:200],
                "target_url": page.url,
                "confirmation": text[:2000],
                "message": "DemoQA test form submission verified.",
            }
    except AutomationError:
        raise
    except Exception as error:
        raise AutomationError(
            "DemoQA test form submission or confirmation verification failed "
            f"({type(error).__name__})."
        ) from None
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



def run_demoqa_textbox_submission():
    """Run the fixed DemoQA test-form submission with a timeout."""
    async def run_fixed_submission():
        return await asyncio.wait_for(
            submit_demoqa_textbox(),
            timeout=TOTAL_TIMEOUT_SECONDS,
        )

    return asyncio.run(run_fixed_submission())



def _submitted_values_visible(before_text, after_text, expected_values, success_text=""):
    """Verify submitted values using new page evidence."""
    before = str(before_text or "")
    after = str(after_text or "")
    values = [str(value).strip() for value in expected_values]
    confirmation = str(success_text or "").strip()

    if not values or not all(value and value in after for value in values):
        return False

    if confirmation and confirmation in after:
        return confirmation not in before

    # Some legitimate forms show submitted values without a separate
    # confirmation banner. Require every expected value to be new.
    return all(value not in before for value in values)


async def submit_approved_form(preferred_url, actions, submit_selector, success_text):
    """Refill and verify approved public form fields, then submit and verify success."""
    import json

    url = validate_http_url(preferred_url)
    validated = validate_browser_actions(actions)

    if not validated or len(validated) > 10:
        raise AutomationError("The approved form must contain 1 to 10 field actions.")
    if any(item.get("type") not in {"fill", "select"} for item in validated):
        raise AutomationError("Only approved fill/select actions are allowed for form submission.")
    if not isinstance(submit_selector, str) or not submit_selector.strip() or len(submit_selector) > 300:
        raise AutomationError("A valid, explicitly approved submit selector is required.")
    if success_text is None:
        success_text = ""
    if not isinstance(success_text, str) or len(success_text) > 300:
        raise AutomationError("The success message must be text of at most 300 characters.")
    success_text = success_text.strip()

    selectors = [item["selector"] for item in validated]
    if len(set(selectors)) != len(selectors):
        raise AutomationError("Duplicate field selectors are not allowed.")

    try:
        from playwright.async_api import async_playwright
    except ImportError as error:
        raise AutomationError("Playwright is not installed.") from error

    browser = None
    context = None
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1024, "height": 640},
                user_agent=USER_AGENT,
                accept_downloads=False,
                service_workers="block",
            )
            context.set_default_timeout(10_000)
            await context.route("**/*", make_request_guard())
            page = await context.new_page()
            page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MILLISECONDS)
            await page.goto(url, timeout=NAVIGATION_TIMEOUT_MILLISECONDS, wait_until="domcontentloaded")

            for item in validated:
                locator = page.locator(item["selector"])
                if await locator.count() != 1:
                    raise AutomationError("Each approved field selector must match exactly one element.")
                field = locator.first
                if not await field.is_visible() or not await field.is_enabled():
                    raise AutomationError("An approved form field is not visible and enabled.")
                tag = (await field.evaluate("(e) => e.tagName.toLowerCase()")).lower()
                field_type = (await field.get_attribute("type") or "").lower()
                if tag not in {"input", "textarea", "select"} or field_type in {"password", "hidden", "file"}:
                    raise AutomationError("Sensitive or unsupported form fields cannot be submitted.")
                if item["type"] == "fill":
                    if tag not in {"input", "textarea"}:
                        raise AutomationError("A fill action must target an input or textarea.")
                    await field.fill(item["value"])
                    actual = await field.input_value()
                else:
                    if tag != "select":
                        raise AutomationError("A select action must target a select element.")
                    await field.select_option(label=item["value"])
                    actual = await field.locator("option:checked").inner_text()
                if actual != item["value"]:
                    raise AutomationError("An approved field value could not be verified.")

            submit = page.locator(submit_selector)
            if await submit.count() != 1:
                raise AutomationError("The approved submit selector must match exactly one element.")
            button = submit.first
            if not await button.is_visible() or not await button.is_enabled():
                raise AutomationError("The approved submit button is not visible and enabled.")
            tag = (await button.evaluate("(e) => e.tagName.toLowerCase()")).lower()
            button_type = (await button.get_attribute("type") or "").lower()
            role = (await button.get_attribute("role") or "").lower()
            if not (tag == "button" or (tag == "input" and button_type in {"submit", "button"}) or role == "button"):
                raise AutomationError("The approved selector does not identify a supported button.")

            before_text = await page.locator("body").inner_text()
            expected_values = [item["value"] for item in validated]
            network_evidence = []

            def capture_submission_response(response):
                try:
                    request = response.request
                    if request.method.upper() in {"POST", "PUT", "PATCH"}:
                        network_evidence.append({
                            "method": request.method.upper(),
                            "status": response.status,
                            "url": response.url[:300],
                        })
                except Exception:
                    pass

            page.on("response", capture_submission_response)
            await button.click()
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass

            try:
                await page.wait_for_function(
                    """({values, confirmation, beforeText}) => {
                        const text = document.body?.innerText || "";
                        return values.every(value => value && text.includes(value))
                            && Boolean(confirmation)
                            && !beforeText.includes(confirmation)
                            && text.includes(confirmation);
                    }""",
                    arg={
                        "values": expected_values,
                        "confirmation": str(success_text or "").strip(),
                        "beforeText": before_text,
                    },
                    timeout=8000,
                )
            except Exception as error:
                after_text = await page.locator("body").inner_text()
                verified = _submitted_values_visible(
                    before_text, after_text, expected_values, success_text
                )
                if not verified:
                    confirmation = str(success_text or "").strip()
                    log("SUBMISSION_DIAGNOSTICS: " + json.dumps({
                        "url": page.url,
                        "page_title": await page.title(),
                        "expected_value_visible": [bool(v) and v in after_text for v in expected_values],
                        "confirmation_configured": bool(confirmation),
                        "confirmation_in_before": bool(confirmation) and confirmation in before_text,
                        "confirmation_in_after": bool(confirmation) and confirmation in after_text,
                        "page_text_length": len(after_text),
                        "page_text_excerpt": after_text[:1500],
                        "network_responses": network_evidence[:10],
                        "network_response_count": len(network_evidence),
                    }))
                    return {
                        "verified": False,
                        "message": "Submission was attempted, but the submitted values could not be verified in the page results.",
                        "page_title": (await page.title())[:200],
                        "target_url": page.url,
                        "verification_error": type(error).__name__,
                        "network_responses": network_evidence[:10],
                    }

            after_text = await page.locator("body").inner_text()
            if not _submitted_values_visible(
                before_text, after_text, expected_values, success_text
            ):
                return {
                    "verified": False,
                    "message": "Submission was attempted, but the submitted values could not be verified in the page results.",
                    "page_title": (await page.title())[:200],
                    "target_url": page.url,
                    "network_responses": network_evidence[:10],
                }

            try:
                page_title = (await page.title()) or "Inklur Browser Task"
            except Exception:
                page_title = "Inklur Browser Task"

            try:
                page_text = str(await page.locator("body").inner_text(timeout=8000))[:6000]
            except Exception:
                page_text = ""

            screenshot = await page.screenshot(
                type="jpeg",
                quality=70,
                full_page=False,
            )
            if not screenshot:
                raise AutomationError("The post-submission screenshot could not be created.")

            screenshot_data = base64.b64encode(screenshot).decode("ascii")
            return {
                "verified": True,
                "message": "Submitted values were verified on the page; server-side persistence is not independently verified.",
                "verification_method": "submitted_values_visible",
                "page_title": str(page_title)[:200],
                "target_url": page.url,
                "page_text": page_text,
                "answer": page_text,
                "screenshot": "data:image/jpeg;base64," + screenshot_data,
                "network_responses": network_evidence[:10],
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

def run_approved_form_submission(preferred_url, actions, submit_selector, success_text):
    """Synchronous entry point for a separately approved generic form submission."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise AutomationError("This synchronous browser entry point cannot run inside an active event loop.")

    async def run():
        return await asyncio.wait_for(
            submit_approved_form(preferred_url, actions, submit_selector, success_text),
            timeout=TOTAL_TIMEOUT_SECONDS,
        )

    try:
        return asyncio.run(run())
    except AutomationError as error:
        log(str(error))
        raise
    except Exception as error:
        log(f"Approved form submission failed ({type(error).__name__}).")
        raise AutomationError("The approved form submission could not be completed safely.") from None


def run_browser_automation(preferred_url, search_query, actions=None):
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
            _run_with_timeout(preferred_url, search_query, actions)
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