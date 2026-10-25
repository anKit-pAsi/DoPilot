/* ==========================================
   INKLUR CONFIG
========================================== */

const API_BASE = "";
const CONTACT_EMAIL = "build@inklur.ai";
const MAX_HISTORY_ITEMS = 40;
const EMAIL_POLL_INTERVAL_MS = 60_000;

let chatHistory = readMigratedJSON("inklur_history", "dopilot_history", []);
let currentUser = getPublicUser(
    readMigratedJSON("inklur_user", "dopilot_user", null)
);
let currentPendingAction = null;
let currentApprovalId = null;
let currentContacts = [];
let pendingIncomingEmail = null;
let pendingDirectEmail = null;
let isExecuting = false;
let isSendingEmail = false;
let isCheckingEmail = false;
let emailPollTimer = null;
let toastTimer = null;
let previousFocus = null;

if (!Array.isArray(chatHistory)) {
    chatHistory = [];
}

/* ==========================================
   STORAGE & API HELPERS
========================================== */

function readMigratedJSON(newKey, legacyKey, fallback) {
    try {
        let raw = localStorage.getItem(newKey);

        if (!raw && legacyKey) {
            raw = localStorage.getItem(legacyKey);
            if (raw) localStorage.setItem(newKey, raw);
        }

        if (legacyKey) localStorage.removeItem(legacyKey);
        return raw ? JSON.parse(raw) : fallback;
    } catch {
        return fallback;
    }
}

function safeSave(key, value) {
    try {
        if (value === null || value === undefined) {
            localStorage.removeItem(key);
        } else {
            localStorage.setItem(key, JSON.stringify(value));
        }
    } catch {
        console.warn("Browser storage is unavailable.");
    }
}

function getPublicUser(user) {
    if (!user || typeof user !== "object" || typeof user.email !== "string") {
        return null;
    }

    // Never retain access tokens in browser storage.
    return {
        id: user.id ?? null,
        name: typeof user.name === "string" ? user.name : "",
        email: user.email
    };
}

function savePublicUser(user) {
    currentUser = getPublicUser(user);
    safeSave("inklur_user", currentUser);
}

function clearPublicUser() {
    currentUser = null;

    try {
        localStorage.removeItem("inklur_user");
        localStorage.removeItem("dopilot_user");
    } catch {
        // Storage may be disabled.
    }
}

function escapeHTML(value) {
    if (value === null || value === undefined) return "";

    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function friendlyNetworkError(error) {
    if (error?.name === "AbortError") {
        return "The request took too long. Please try again.";
    }
    if (error instanceof TypeError) {
        return "Could not reach the Inklur server. Please try again.";
    }
    return error?.message || "Something went wrong. Please try again.";
}

async function apiRequest(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(
        () => controller.abort(),
        options.timeoutMs || 30_000
    );
    const headers = { Accept: "application/json" };
    const fetchOptions = {
        method: options.method || "POST",
        headers,
        credentials: "include",
        signal: controller.signal
    };

    if (options.body !== undefined) {
        headers["Content-Type"] = "application/json";
        fetchOptions.body = JSON.stringify(options.body);
    }

    try {
        const response = await fetch(`${API_BASE}${path}`, fetchOptions);
        let data = null;

        try {
            data = await response.json();
        } catch {
            // Handle invalid or empty JSON below.
        }

        if (response.status === 401 && currentUser) {
            handleSessionExpired();
        }

        if (!response.ok) {
            throw new Error(
                data?.message ||
                data?.error ||
                `Request failed (HTTP ${response.status}).`
            );
        }

        if (!data || typeof data !== "object") {
            throw new Error("The server returned an invalid response.");
        }

        return data;
    } finally {
        clearTimeout(timeout);
    }
}

function postJSON(path, body = {}, timeoutMs = 30_000) {
    return apiRequest(path, { method: "POST", body, timeoutMs });
}

function getJSON(path, timeoutMs = 15_000) {
    return apiRequest(path, { method: "GET", timeoutMs });
}

function newIdempotencyKey() {
    return window.crypto?.randomUUID
        ? window.crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function handleSessionExpired() {
    const hadUser = Boolean(currentUser);
    clearPublicUser();
    stopEmailPolling();
    updateNavUI();

    if (hadUser) {
        showToast("🔒 Your session expired. Please log in again.", 4500);
    }
}

/* ==========================================
   STARTUP
========================================== */

document.addEventListener("DOMContentLoaded", async () => {
    injectRuntimeStyles();
    renderHistoryList();
    updateNavUI();
    initAutoResizeTextarea();
    initMailtoLinks();
    initModalControls();
    initMobileNav();
    await restoreSession();
});

async function restoreSession() {
    try {
        const result = await getJSON("/api/me");

        if (result.success && result.user) {
            savePublicUser(result.user);
            updateNavUI();
            startEmailPolling();
            return;
        }
    } catch {
        // No active session. The user can log in normally.
    }

    clearPublicUser();
    updateNavUI();
}

/* ==========================================
   TOAST & RUNTIME STYLES
========================================== */

function injectRuntimeStyles() {
    if (document.getElementById("inklur-runtime-styles")) return;

    const style = document.createElement("style");
    style.id = "inklur-runtime-styles";
    style.textContent = `
        .glass-card {
            background: rgba(15, 23, 42, .85);
            border: 1px solid rgba(255, 255, 255, .1);
            border-radius: 12px;
            padding: 14px 16px;
            color: #e2e8f0;
            line-height: 1.8;
            overflow-wrap: anywhere;
        }
        .history-item {
            padding: 8px 12px;
            border-radius: 8px;
            color: #cbd5e1;
            font-size: 14px;
            overflow-wrap: anywhere;
        }
        .inklur-toast {
            position: fixed;
            left: 50%;
            bottom: 28px;
            transform: translateX(-50%) translateY(20px);
            background: #0f172a;
            border: 1px solid #6366f1;
            color: #f8fafc;
            padding: 12px 20px;
            border-radius: 12px;
            font-size: 14px;
            line-height: 1.5;
            text-align: center;
            max-width: calc(100% - 32px);
            box-shadow: 0 10px 30px rgba(0, 0, 0, .5);
            z-index: 10000;
            opacity: 0;
            pointer-events: none;
            transition: opacity .25s ease, transform .25s ease;
        }
        .inklur-toast.show {
            opacity: 1;
            transform: translateX(-50%) translateY(0);
        }
        .action-card button:disabled {
            opacity: .6;
            cursor: not-allowed;
        }
        @media (prefers-reduced-motion: reduce) {
            .inklur-toast { transition: none; }
        }
    `;
    document.head.appendChild(style);
}

function showToast(message, duration = 3500) {
    let toast = document.getElementById("inklurToast");

    if (!toast) {
        toast = document.createElement("div");
        toast.id = "inklurToast";
        toast.className = "inklur-toast";
        toast.setAttribute("role", "status");
        toast.setAttribute("aria-live", "polite");
        document.body.appendChild(toast);
    }

    toast.textContent = message;
    void toast.offsetWidth;
    toast.classList.add("show");

    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), duration);
}

/* ==========================================
   NAVIGATION, PRICING & MAIL LINKS
========================================== */

function scrollToPrompt() {
    const input = document.getElementById("userInput");
    if (!input) return;

    input.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => input.focus(), 300);
}

function toggleMobileNav(forceState) {
    const nav = document.getElementById("primaryNav");
    const button = document.querySelector(".mobile-menu-toggle");
    if (!nav || !button) return;

    const open = typeof forceState === "boolean"
        ? forceState
        : !nav.classList.contains("is-open");

    nav.classList.toggle("is-open", open);
    button.setAttribute("aria-expanded", String(open));
    button.setAttribute(
        "aria-label",
        open ? "Close navigation menu" : "Open navigation menu"
    );
}

function initMobileNav() {
    const nav = document.getElementById("primaryNav");
    if (!nav) return;

    nav.addEventListener("click", (event) => {
        if (event.target instanceof Element && event.target.closest("a")) {
            toggleMobileNav(false);
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") toggleMobileNav(false);
    });
}

function selectPlan(planName) {
    if (planName === "Starter") {
        if (currentUser) {
            showToast("🚀 You're all set! Try the demo above.");
            scrollToPrompt();
        } else {
            openAuthModal("signup");
        }
        return;
    }

    joinEarlyAccess(planName);
}

async function copyToClipboard(text) {
    try {
        if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(text);
            return true;
        }
    } catch {
        // The mail link remains available.
    }
    return false;
}

async function joinEarlyAccess(planName) {
    const label = planName && planName !== "Early Access"
        ? planName
        : "Early Access / Beta Program";

    const copied = await copyToClipboard(CONTACT_EMAIL);
    showToast(
        copied
            ? `📧 Opening your email app… (${CONTACT_EMAIL} is also copied)`
            : `📧 Opening your email app… If nothing opens, write to ${CONTACT_EMAIL}`
    );

    window.location.href =
        `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(`Inklur ${label}`)}`;
}

function initMailtoLinks() {
    document.addEventListener("click", async (event) => {
        if (!(event.target instanceof Element)) return;

        const link = event.target.closest('a[href^="mailto:"]');
        if (!link) return;

        const address = (link.getAttribute("href") || "")
            .replace(/^mailto:/i, "")
            .split("?")[0] || CONTACT_EMAIL;

        const copied = await copyToClipboard(address);
        showToast(
            copied
                ? `📧 Opening your email app… (${address} is also copied)`
                : `📧 Opening your email app… If nothing opens, write to ${address}`
        );
    });
}

/* ==========================================
   USE CASE TABS
========================================== */

const useCaseData = {
    email: '"Summarize my important emails and prepare replies for my approval."',
    research: '"Find the top 5 competitors in the AI agent space and create a comparison table."',
    data: '"Extract all invoice amounts from these attached PDFs and put them into a Google Sheet."',
    automation: '"When someone fills out my website form, add them to Mailchimp and send a welcome email."'
};

const useCaseTitles = {
    email: "Email Automation",
    research: "Deep Research",
    data: "Data Extraction",
    automation: "Workflow Automation"
};

function showUseCase(type, button) {
    const box = document.getElementById("usecase-box");
    if (!box || !useCaseTitles[type]) return;

    document.querySelectorAll(".tab-btn").forEach((tab) => {
        tab.classList.remove("active");
        tab.setAttribute("aria-pressed", "false");
    });

    if (button) {
        button.classList.add("active");
        button.setAttribute("aria-pressed", "true");
    }

    box.innerHTML =
        `<h3>${escapeHTML(useCaseTitles[type])}</h3>` +
        `<p>${escapeHTML(useCaseData[type])}</p>`;
}

/* ==========================================
   PROMPT TEXTAREA
========================================== */

function initAutoResizeTextarea() {
    const input = document.getElementById("userInput");
    if (!input) return;

    input.addEventListener("input", autoResizeInput);
    autoResizeInput();
}

function autoResizeInput() {
    const input = document.getElementById("userInput");
    if (!input) return;

    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 250)}px`;
    input.classList.toggle("overflow-active", input.scrollHeight > 250);
}

function handleEnter(event) {
    if (
        event.key === "Enter" &&
        !event.shiftKey &&
        !event.isComposing
    ) {
        event.preventDefault();
        sendPrompt();
    }
}

/* ==========================================
   EMAIL NOTIFICATION & TWO-STEP APPROVAL
========================================== */

function startEmailPolling() {
    if (!currentUser || emailPollTimer) return;

    checkForIncomingEmails();
    emailPollTimer = setInterval(
        checkForIncomingEmails,
        EMAIL_POLL_INTERVAL_MS
    );
}

function stopEmailPolling() {
    if (!emailPollTimer) return;
    clearInterval(emailPollTimer);
    emailPollTimer = null;
}

document.addEventListener("visibilitychange", () => {
    if (!document.hidden && currentUser) checkForIncomingEmails();
});

async function checkForIncomingEmails() {
    if (!currentUser || isCheckingEmail || document.hidden) return;

    isCheckingEmail = true;

    try {
        const result = await postJSON("/api/check-email-notifications", {});
        if (!result.success || !result.has_notification || !result.data) return;

        const email = normalizeIncomingEmail(result.data);
        if (!email?.emailId) return;

        if (pendingIncomingEmail?.emailId === email.emailId) return;

        pendingIncomingEmail = email;
        renderEmailNotificationCard();
    } catch (error) {
        if (error.status === 401) stopEmailPolling();
    } finally {
        isCheckingEmail = false;
    }
}

function normalizeIncomingEmail(data) {
    if (!data || typeof data !== "object") return null;

    return {
        emailId: String(data.email_id || data.id || ""),
        sender: String(data.sender || "Unknown sender"),
        email: String(data.email || ""),
        subject: String(data.subject || "No subject"),
        snippet: String(data.snippet || ""),
        proposedReply: "",
        status: "pending"
    };
}

function renderEmailNotificationCard() {
    const status = document.getElementById("demoStatus");
    const email = pendingIncomingEmail;
    if (!status || !email) return;

    status.style.display = "block";
    status.innerHTML = `
        <div class="action-card" id="incomingEmailCard"
             style="margin-top:15px;padding:18px;border:1px solid #3b82f6;border-radius:12px;background:#0f172a;text-align:left;">
            <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-bottom:12px;border-bottom:1px solid #1e293b;padding-bottom:8px;">
                <span style="background:#1e1b4b;color:#818cf8;padding:4px 10px;border-radius:20px;font-size:.8rem;font-weight:600;">
                    📧 New Email
                </span>
                <span style="color:#fbbf24;font-size:.8rem;font-weight:600;">
                    Approve before drafting
                </span>
            </div>
            <p style="margin:4px 0;font-size:.9rem;color:#f8fafc;">
                <strong>From:</strong> ${escapeHTML(email.sender)}
                ${email.email ? `(${escapeHTML(email.email)})` : ""}
            </p>
            <p style="margin:4px 0 10px;font-size:.9rem;color:#38bdf8;">
                <strong>Subject:</strong> ${escapeHTML(email.subject)}
            </p>
            <div style="background:#1e293b;padding:10px;border-radius:6px;font-size:.85rem;color:#cbd5e1;margin-bottom:12px;border:1px solid #334155;">
                ${escapeHTML(email.snippet)}
            </div>
            <div id="emailCardActions" style="display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap;">
                <button type="button" onclick="dismissEmailCard()"
                        style="background:#475569;color:white;border:0;padding:8px 16px;border-radius:6px;font-weight:600;cursor:pointer;">
                    Cancel
                </button>
                <button type="button" onclick="prepareEmailReply()"
                        style="background:#2563eb;color:white;border:0;padding:8px 18px;border-radius:6px;font-weight:600;cursor:pointer;">
                    Approve &amp; Prepare Draft
                </button>
            </div>
        </div>
    `;
}

async function prepareEmailReply() {
    const email = pendingIncomingEmail;
    const actions = document.getElementById("emailCardActions");

    if (!email?.emailId || email.status !== "pending") return;

    email.status = "preparing";
    if (actions) {
        actions.innerHTML =
            '<span role="status" aria-live="polite" style="color:#93c5fd;">Preparing your draft…</span>';
    }

    try {
        const result = await postJSON("/api/prepare-email-reply", {
            email_id: email.emailId
        });

        if (!result.success) {
            throw new Error(result.message || "Could not prepare the draft.");
        }

        const data = result.data || result;
        email.proposedReply = String(data.proposed_reply || data.draft || "");
        email.status = "drafted";
        renderEmailDraftCard();
    } catch (error) {
        email.status = "pending";
        showEmailCardError(error);
    }
}

function renderEmailDraftCard() {
    const status = document.getElementById("demoStatus");
    const email = pendingIncomingEmail;
    if (!status || !email) return;

    status.style.display = "block";
    status.innerHTML = `
        <div class="action-card" id="incomingEmailCard"
             style="margin-top:15px;padding:18px;border:1px solid #3b82f6;border-radius:12px;background:#0f172a;text-align:left;">
            <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-bottom:12px;border-bottom:1px solid #1e293b;padding-bottom:8px;">
                <span style="background:#1e1b4b;color:#818cf8;padding:4px 10px;border-radius:20px;font-size:.8rem;font-weight:600;">
                    📧 Reply Draft
                </span>
                <span style="color:#fbbf24;font-size:.8rem;font-weight:600;">
                    Review and edit before sending
                </span>
            </div>
            <p style="margin:4px 0;font-size:.9rem;color:#f8fafc;">
                <strong>To:</strong> ${escapeHTML(email.email || email.sender)}
            </p>
            <p style="margin:4px 0 10px;font-size:.9rem;color:#38bdf8;">
                <strong>Subject:</strong> ${escapeHTML(email.subject)}
            </p>
            <label for="autoEmailReplyText"
                   style="display:block;color:#fbbf24;font-size:.85rem;font-weight:600;margin-bottom:5px;">
                Proposed reply
            </label>
            <textarea id="autoEmailReplyText" maxlength="10000"
                      style="width:100%;min-height:120px;background:#0f172a;color:#f8fafc;border:1px solid #475569;border-radius:6px;padding:10px;font:inherit;resize:vertical;">${escapeHTML(email.proposedReply)}</textarea>
            <div id="emailCardActions" style="display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap;margin-top:12px;">
                <button type="button" onclick="dismissEmailCard()"
                        style="background:#475569;color:white;border:0;padding:8px 16px;border-radius:6px;font-weight:600;cursor:pointer;">
                    Cancel draft
                </button>
                <button type="button" onclick="approveAndSendEmail()"
                        style="background:#16a34a;color:white;border:0;padding:8px 18px;border-radius:6px;font-weight:600;cursor:pointer;">
                    Approve &amp; Send Reply
                </button>
            </div>
        </div>
    `;
}

async function dismissEmailCard() {
    const email = pendingIncomingEmail;
    if (!email?.emailId) {
        removeEmailCard();
        return;
    }

    try {
        const result = await postJSON("/api/dismiss-email-notification", {
            email_id: email.emailId
        });

        if (!result.success) {
            throw new Error(result.message || "Could not cancel this email.");
        }

        removeEmailCard();
    } catch (error) {
        showEmailCardError(error);
    }
}

async function approveAndSendEmail() {
    const email = pendingIncomingEmail;
    const box = document.getElementById("autoEmailReplyText");
    const actions = document.getElementById("emailCardActions");

    if (!email?.emailId || !box || isSendingEmail) return;

    const body = box.value.trim();
    if (!body) {
        showToast("Please add a reply before sending.");
        box.focus();
        return;
    }

    isSendingEmail = true;
    if (actions) {
        actions.innerHTML =
            '<span role="status" aria-live="polite" style="color:#93c5fd;">Sending reply…</span>';
    }

    try {
        const result = await postJSON("/api/send-email", {
            email_id: email.emailId,
            to_email: email.email,
            subject: email.subject,
            body,
            idempotency_key: newIdempotencyKey()
        });

        if (result.status !== "success" && !result.success) {
            throw new Error(result.message || result.error || "Reply was not sent.");
        }

        if (actions) {
            actions.innerHTML =
                '<span role="status" aria-live="polite" style="color:#34d399;font-weight:600;">✅ Reply sent successfully.</span>';
        }

        email.status = "sent";
        pendingIncomingEmail = null;
        showToast("✅ Reply sent successfully.");
    } catch (error) {
        showEmailCardError(error);
    } finally {
        isSendingEmail = false;
    }
}

function removeEmailCard() {
    document.getElementById("incomingEmailCard")?.remove();
    pendingIncomingEmail = null;
}

function showEmailCardError(error) {
    const actions = document.getElementById("emailCardActions");
    const message = escapeHTML(friendlyNetworkError(error));

    if (actions) {
        actions.innerHTML = `<span role="alert" style="color:#f87171;">${message}</span>`;
    } else {
        showToast(friendlyNetworkError(error), 5000);
    }
}

/* ==========================================
   PROMPT EXECUTION & RESPONSE
========================================== */

function setExecuting(state) {
    isExecuting = state;
    const button = document.querySelector(".send-btn");

    if (button) {
        button.disabled = state;
        button.textContent = state ? "Working… ⏳" : "Execute 🚀";
    }
}

async function sendPrompt() {
    if (isExecuting) return;

    const input = document.getElementById("userInput");
    const status = document.getElementById("demoStatus");
    if (!input || !status) return;

    const text = input.value.trim();
    status.style.display = "block";

    if (!text) {
        status.innerHTML =
            '<div class="glass-card" role="alert">⚠️ Please enter a prompt for Inklur.</div>';
        input.focus();
        return;
    }

    status.innerHTML =
        '<div class="glass-card" role="status" aria-live="polite">⏳ Inklur is analyzing your task…</div>';
    setExecuting(true);

    try {
        const result = await postJSON(
            "/api/execute",
            { prompt: text, history: chatHistory.slice(-20) },
            60_000
        );

        if (!result.success) {
            throw new Error(result.message || result.error || "Request failed.");
        }

        const historyText =
            result.result ||
            result.message ||
            result.parsed_action?.message ||
            "Task analyzed.";

        chatHistory.push({ sender: "user", text });
        chatHistory.push({
            sender: "model",
            text: typeof historyText === "string"
                ? historyText
                : JSON.stringify(historyText)
        });

        chatHistory = chatHistory.slice(-MAX_HISTORY_ITEMS);
        safeSave("inklur_history", chatHistory);
        renderHistoryList();
        displayAIResponse(result, status);

        input.value = "";
        input.style.height = "auto";
        input.classList.remove("overflow-active");
    } catch (error) {
        status.innerHTML =
            `<div class="glass-card" role="alert">❌ ${escapeHTML(friendlyNetworkError(error))}</div>`;
    } finally {
        setExecuting(false);
    }
}

function displayAIResponse(data, status) {
    if (!status || !data) return;

    if (data.tool_name === "gmail_automation") {
        displayGmailResponse(data.result || {}, status);
        return;
    }

    const raw = data.result ??
        data.parsed_action?.message ??
        "Task analyzed successfully.";

    const text = typeof raw === "string" ? raw : JSON.stringify(raw, null, 2);

    let html = `
        <div>
            🚀 <strong>Inklur Response:</strong>
            <div class="glass-card" style="margin-top:6px;white-space:pre-wrap;">
                ${escapeHTML(text)}
            </div>
        </div>
    `;

    if (data.action_required && data.parsed_action) {
        currentPendingAction = data.parsed_action;
        currentApprovalId =
            data.approval_id ||
            data.parsed_action.approval_id ||
            null;

        const action = data.parsed_action;
        const parameters = Array.isArray(action.parameters)
            ? action.parameters
            : [];

        const parametersHTML = parameters.map((param) => `
            <div style="display:flex;justify-content:space-between;gap:12px;margin-bottom:4px;font-size:.85rem;">
                <span style="color:#94a3b8;">${escapeHTML(param.label)}:</span>
                <span style="color:#f1f5f9;text-align:right;overflow-wrap:anywhere;">
                    ${escapeHTML(param.value)}
                </span>
            </div>
        `).join("");

        html += `
            <div class="action-card" id="activeActionCard"
                 style="margin-top:15px;padding:16px;border:1px solid #3b82f6;border-radius:10px;background:#0f172a;text-align:left;">
                <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-bottom:10px;">
                    <span style="color:#818cf8;font-size:.8rem;font-weight:600;">
                        ⚡ ${escapeHTML(action.tool_name || "System Automation")}
                    </span>
                    <span id="cardStatusBadge" style="color:#fbbf24;font-size:.8rem;font-weight:600;">
                        Pending approval
                    </span>
                </div>
                <h3 style="margin:0 0 10px;color:#f8fafc;font-size:.95rem;">
                    ${escapeHTML(action.action_title || "Task Execution Plan")}
                </h3>
                <div style="background:#1e293b;padding:10px;border-radius:6px;margin-bottom:12px;">
                    ${parametersHTML}
                </div>
                <div id="cardActionsGroup" style="display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap;">
                    <button type="button" onclick="cancelAction()"
                            style="background:#475569;color:white;border:0;padding:8px 14px;border-radius:6px;font-weight:600;cursor:pointer;">
                        Cancel
                    </button>
                    <button type="button" onclick="approveAction()"
                            ${currentApprovalId ? "" : "disabled"}
                            style="background:#16a34a;color:white;border:0;padding:8px 14px;border-radius:6px;font-weight:600;cursor:pointer;">
                        Approve &amp; Execute
                    </button>
                </div>
                ${currentApprovalId ? "" : '<p role="alert" style="margin-top:10px;color:#fca5a5;font-size:.85rem;">The server did not provide a verifiable approval. Please run the task again.</p>'}
            </div>
        `;
    }

    status.innerHTML = html;
}

function displayGmailResponse(result, status) {
    if (result.status === "multiple_found" && Array.isArray(result.contacts)) {
        currentContacts = result.contacts.slice(0, 10);

        const contacts = currentContacts.map((contact, index) => `
            <div style="background:#1e293b;border:1px solid #334155;padding:10px;margin-bottom:8px;border-radius:8px;display:flex;justify-content:space-between;align-items:center;gap:10px;">
                <div style="min-width:0;">
                    <div style="font-size:.8rem;color:#94a3b8;">Option ${index + 1}</div>
                    <div style="font-weight:600;color:#f8fafc;">
                        ${escapeHTML(contact.name)}
                    </div>
                    <div style="font-size:.8rem;color:#38bdf8;overflow-wrap:anywhere;">
                        ${escapeHTML(contact.email)}
                    </div>
                </div>
                <button type="button" onclick="handleContactSelection(${index})"
                        style="background:#6366f1;color:white;border:0;padding:6px 14px;border-radius:6px;cursor:pointer;">
                    Select
                </button>
            </div>
        `).join("");

        status.innerHTML = `
            <div class="glass-card" style="margin-top:10px;border-color:#fbbf24;">
                <h3 style="margin:0 0 12px;color:#fbbf24;font-size:1rem;">
                    🔍 Multiple contacts found
                </h3>
                <p style="margin-bottom:12px;font-size:.9rem;color:#cbd5e1;">
                    ${escapeHTML(result.message || "Choose the correct contact.")}
                </p>
                <div style="max-height:250px;overflow-y:auto;">${contacts}</div>
            </div>
        `;
        return;
    }

    if (result.status !== "success") {
        status.innerHTML =
            `<div class="glass-card" role="alert" style="color:#f87171;">❌ ${escapeHTML(result.message || result.error || "Email task failed.")}</div>`;
        return;
    }

    pendingDirectEmail = {
        emailId: String(result.message_id || result.email_id || ""),
        toEmail: String(result.target_email || ""),
        subject: String(result.subject || "No subject")
    };

    status.innerHTML = `
        <div class="glass-card" style="margin-top:10px;text-align:left;border-color:#3b82f6;">
            <h3 style="margin:0 0 10px;color:#38bdf8;font-size:1rem;">
                📧 Review email draft
            </h3>
            <p style="margin:4px 0;font-size:.9rem;">
                <strong>To:</strong> ${escapeHTML(pendingDirectEmail.toEmail)}
            </p>
            <p style="margin:4px 0 10px;font-size:.9rem;">
                <strong>Subject:</strong> ${escapeHTML(pendingDirectEmail.subject)}
            </p>
            <label for="emailMessage" style="display:block;color:#fbbf24;margin:10px 0 6px;font-size:.9rem;font-weight:600;">
                Proposed reply — edit before sending
            </label>
            <textarea id="emailMessage" maxlength="10000"
                      style="width:100%;min-height:110px;background:#1e293b;color:#f8fafc;border:1px solid #475569;border-radius:6px;padding:8px;font:inherit;resize:vertical;">${escapeHTML(result.proposed_reply || "")}</textarea>
            <button type="button" onclick="sendDirectEmail()"
                    style="margin-top:12px;width:100%;background:#2563eb;color:white;border:0;padding:10px;border-radius:6px;font-weight:bold;cursor:pointer;">
                Approve &amp; Send Email
            </button>
        </div>
    `;
}

function handleContactSelection(index) {
    const contact = currentContacts[index];
    const input = document.getElementById("userInput");
    if (!contact || !input) return;

    input.value = `Send an email to ${contact.email}`;
    autoResizeInput();
    sendPrompt();
}

/* ==========================================
   APPROVE OR CANCEL A PLANNED ACTION
========================================== */

async function approveAction() {
    if (!currentApprovalId || !currentPendingAction || isExecuting) return;

    const badge = document.getElementById("cardStatusBadge");
    const actions = document.getElementById("cardActionsGroup");
    isExecuting = true;

    if (badge) badge.textContent = "Running…";
    if (actions) {
        actions.innerHTML =
            '<span role="status" aria-live="polite" style="color:#93c5fd;">Running approved task…</span>';
    }

    try {
        const result = await postJSON(
            "/api/execute-task",
            { approval_id: currentApprovalId },
            120_000
        );

        if (!result.success) {
            throw new Error(result.message || result.error || "Execution failed.");
        }

        if (badge) {
            badge.textContent = "Completed";
            badge.style.color = "#34d399";
        }

        const data = result.data || result;
        const screenshot = safeScreenshotDataURL(result.screenshot || data.screenshot);
        const answer = String(data.answer || "").trim();

        if (actions && (screenshot || answer)) {
            actions.innerHTML = `
                <div style="width:100%;margin-top:10px;">
                    <div style="color:#34d399;font-weight:600;margin-bottom:8px;">
                        ✅ Browser result
                    </div>
                    ${answer ? `<div style="padding:12px;margin-bottom:10px;border:1px solid #334155;border-radius:8px;white-space:pre-wrap;color:inherit;">${escapeHTML(answer)}</div>` : ""}
                    ${screenshot ? `<div style="border:2px solid #334155;border-radius:8px;overflow:hidden;"><img src="${screenshot}" alt="Screenshot of the approved browser task" style="width:100%;height:auto;display:block;"></div>` : ""}
                </div>
            `;
        } else if (actions) {
            actions.innerHTML =
                '<span role="status" style="color:#34d399;font-weight:600;">✅ Task completed, but no page answer was returned.</span>';
        }

        currentPendingAction = null;
        currentApprovalId = null;
    } catch (error) {
        if (badge) {
            badge.textContent = "Failed";
            badge.style.color = "#fda4af";
        }

        if (actions) {
            actions.innerHTML =
                `<span role="alert" style="color:#f87171;">${escapeHTML(friendlyNetworkError(error))}</span>`;
        }
    } finally {
        isExecuting = false;
    }
}

function safeScreenshotDataURL(value) {
    if (typeof value !== "string" || value.length > 8_000_000) return "";

    return /^data:image\/(?:jpeg|png);base64,[A-Za-z0-9+/=_-]+$/.test(value)
        ? value
        : "";
}

async function cancelAction() {
    const approvalId = currentApprovalId;
    const badge = document.getElementById("cardStatusBadge");
    const actions = document.getElementById("cardActionsGroup");

    if (approvalId) {
        try {
            await postJSON("/api/cancel-action", { approval_id: approvalId });
        } catch (error) {
            showToast(friendlyNetworkError(error), 5000);
        }
    }

    if (badge) {
        badge.textContent = "Cancelled";
        badge.style.color = "#f87171";
    }

    if (actions) {
        actions.innerHTML =
            '<span role="status" style="color:#f87171;font-weight:600;">Task cancelled.</span>';
    }

    currentPendingAction = null;
    currentApprovalId = null;
}

/* ==========================================
   SEND A DIRECT EMAIL
========================================== */

async function sendDirectEmail() {
    const box = document.getElementById("emailMessage");
    if (!pendingDirectEmail || !box || isSendingEmail) return;

    const body = box.value.trim();
    if (!body) {
        showToast("Please write a message before sending.");
        box.focus();
        return;
    }

    isSendingEmail = true;
    const button = document.querySelector(
        "#demoStatus button[onclick='sendDirectEmail()']"
    );
    if (button) {
        button.disabled = true;
        button.textContent = "Sending…";
    }

    try {
        const result = await postJSON("/api/send-email", {
            email_id: pendingDirectEmail.emailId || null,
            to_email: pendingDirectEmail.toEmail,
            subject: pendingDirectEmail.subject,
            body,
            idempotency_key: newIdempotencyKey()
        });

        if (result.status !== "success" && !result.success) {
            throw new Error(result.message || result.error || "Email was not sent.");
        }

        const status = document.getElementById("demoStatus");
        if (status) {
            status.innerHTML =
                `<div class="glass-card" role="status" style="color:#34d399;">✅ Email sent successfully to ${escapeHTML(pendingDirectEmail.toEmail)}.</div>`;
        }

        pendingDirectEmail = null;
        showToast("✅ Email sent successfully.");
    } catch (error) {
        if (button) {
            button.disabled = false;
            button.textContent = "Approve & Send Email";
        }
        showToast(`❌ ${friendlyNetworkError(error)}`, 5000);
    } finally {
        isSendingEmail = false;
    }
}

/* ==========================================
   CHAT HISTORY
========================================== */

function renderHistoryList() {
    const list = document.getElementById("historyList");
    if (!list) return;

    list.replaceChildren();

    chatHistory
        .filter((message) => message && message.sender === "user")
        .forEach((message) => {
            const item = document.createElement("div");
            item.className = "history-item";
            item.textContent = `💬 ${String(message.text || "")}`;
            list.appendChild(item);
        });
}

function clearHistory() {
    chatHistory = [];

    try {
        localStorage.removeItem("inklur_history");
        localStorage.removeItem("dopilot_history");
    } catch {
        // Storage may be disabled.
    }

    renderHistoryList();

    const status = document.getElementById("demoStatus");
    if (status) {
        status.style.display = "block";
        status.innerHTML =
            '<div class="glass-card" role="status">Started a fresh conversation.</div>';
    }
}

/* ==========================================
   LOGIN / SIGNUP MODAL
========================================== */


function initModalControls() {
    const modal = document.getElementById("authModal");
    if (!modal) return;

    modal.addEventListener("click", (event) => {
        if (event.target === modal) closeAuthModal();
    });

    document.addEventListener("keydown", (event) => {
        if (modal.getAttribute("aria-hidden") === "true") return;
        if (event.key === "Escape") {
            closeAuthModal();
            return;
        }
        if (event.key !== "Tab") return;

        const controls = modal.querySelectorAll(
            'button:not([disabled]), input:not([disabled]), a[href], textarea:not([disabled])'
        );
        if (!controls.length) {
            event.preventDefault();
            modal.focus();
            return;
        }

        const first = controls[0];
        const last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    });
}

function openAuthModal(mode) {
    const modal = document.getElementById("authModal");
    if (!modal) return;

    previousFocus = document.activeElement;
    modal.style.display = "flex";
    modal.setAttribute("aria-hidden", "false");
    toggleAuthMode(mode || "login");

    const selector = mode === "signup" ? "#signupName" : "#loginEmail";
    setTimeout(() => modal.querySelector(selector)?.focus(), 0);
}

function closeAuthModal() {
    const modal = document.getElementById("authModal");
    if (!modal) return;

    modal.style.display = "none";
    modal.setAttribute("aria-hidden", "true");
    clearAuthAlert();

    if (previousFocus && typeof previousFocus.focus === "function") {
        previousFocus.focus();
    }
}

function toggleAuthMode(mode) {
    const modal = document.getElementById("authModal");
    const login = document.getElementById("loginFormContainer");
    const signup = document.getElementById("signupFormContainer");
    if (!login || !signup) return;

    const isLogin = mode === "login";
    login.style.display = isLogin ? "block" : "none";
    signup.style.display = isLogin ? "none" : "block";
    modal?.setAttribute("aria-labelledby", isLogin ? "loginHeading" : "signupHeading");
    clearAuthAlert();
}

function showAuthAlert(msg, isError = true) {
    const alertBox = document.getElementById("authAlert");
    if (alertBox) {
        alertBox.style.color = isError ? "#f87171" : "#4ade80";
        alertBox.innerText = msg;
    }
}

function clearAuthAlert() {
    const alertBox = document.getElementById("authAlert");
    if (alertBox) alertBox.innerText = "";
}

async function handleLogin(event) {
    event?.preventDefault();
    const email = document.getElementById("loginEmail")?.value.trim() || "";
    const password = document.getElementById("loginPassword")?.value || "";

    if (!email || !password) {
        showAuthAlert("Please enter both email and password.");
        return;
    }

    try {
        const data = await postJSON("/api/login", { email, password }, 20000);
        if (!data.success || !data.user) {
            showAuthAlert(data.message || "Invalid credentials.");
            return;
        }

        savePublicUser(data.user);
        showAuthAlert("Login successful.", false);
        updateNavUI();
        startEmailPolling();
        setTimeout(closeAuthModal, 500);
    } catch (error) {
        showAuthAlert(friendlyNetworkError(error));
    }
}

async function handleSignup(event) {
    event?.preventDefault();
    const name = document.getElementById("signupName")?.value.trim() || "";
    const email = document.getElementById("signupEmail")?.value.trim() || "";
    const password = document.getElementById("signupPassword")?.value || "";

    if (!name || !email || !password) {
        showAuthAlert("All fields are required.");
        return;
    }
    if (password.length < 12) {
        showAuthAlert("Use a password with at least 12 characters.");
        return;
    }

    try {
        const data = await postJSON("/api/signup", { name, email, password }, 20000);
        if (!data.success) {
            showAuthAlert(data.message || "Signup failed.");
            return;
        }

        showAuthAlert("Account created. You can now log in.", false);
        toggleAuthMode("login");
        const loginEmail = document.getElementById("loginEmail");
        if (loginEmail) {
            loginEmail.value = email;
            loginEmail.focus();
        }
    } catch (error) {
        showAuthAlert(friendlyNetworkError(error));
    }
}

async function handleLogout() {
    stopEmailPolling();
    try {
        await postJSON("/api/logout", {});
    } catch {
        // Clear local UI state even if the server is unavailable.
    }

    clearPublicUser();
    pendingIncomingEmail = null;
    pendingDirectEmail = null;
    currentPendingAction = null;
    currentApprovalId = null;
    updateNavUI();
    showToast("👋 You've been logged out.");
}

function toggleProfileDropdown(event, forceState) {
    if (event) event.stopPropagation();
    const dropdown = document.getElementById("profileDropdown");
    if (!dropdown) return;

    if (typeof forceState === "boolean") {
        dropdown.classList.toggle("show", forceState);
    } else {
        dropdown.classList.toggle("show");
    }
}

window.addEventListener("click", function () {
    const dropdown = document.getElementById("profileDropdown");
    if (dropdown && dropdown.classList.contains("show")) {
        dropdown.classList.remove("show");
    }
});

function updateNavUI() {
    const navContainer = document.getElementById("authNavContainer");
    if (!navContainer) return;

    if (currentUser) {
        navContainer.innerHTML = `
            <div class="profile-menu-container" onmouseenter="toggleProfileDropdown(event, true)" onmouseleave="toggleProfileDropdown(event, false)">
                <div class="profile-badge" onclick="toggleProfileDropdown(event, true)">
                    <span>👤 ${escapeHTML(currentUser.name || "User")}</span>
                    <span style="font-size: 0.7rem; color: #94a3b8;">▼</span>
                </div>

                <div class="profile-dropdown" id="profileDropdown">
                    <button onclick="openProfileSettings()">✏️ Edit Profile</button>
                    <button onclick="joinEarlyAccess('Early Access')">⚡ Early Access</button>
                    <button class="logout-btn" onclick="handleLogout()">🚪 Logout</button>
                </div>
            </div>
        `;
    } else {
        navContainer.innerHTML = `
            <button class="btn-header" style="background: transparent; border: 1px solid #334155; color: #f8fafc;" onclick="openAuthModal('login')">
                Login / Sign Up
            </button>
        `;
    }
}

function openProfileSettings() {
    showToast("✏️ Edit profile feature coming soon!");
}

function togglePasswordVisibility(inputId, btn) {
    const input = document.getElementById(inputId);
    if (!input) return;

    if (input.type === "password") {
        input.type = "text";
        if (btn) btn.innerHTML = '<span aria-hidden="true">🙈</span>';
    } else {
        input.type = "password";
        if (btn) btn.innerHTML = '<span aria-hidden="true">👁️</span>';
    }
}