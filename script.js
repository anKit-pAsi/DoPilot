/* ==========================================
    GLOBAL STATES & INITIALIZATION
========================================== */
let chatHistory = JSON.parse(localStorage.getItem("dopilot_history")) || [];
let currentUser = JSON.parse(localStorage.getItem("dopilot_user")) || null;
let currentPendingAction = null;

document.addEventListener('DOMContentLoaded', () => {
    renderHistoryList();
    updateNavUI();
    initAutoResizeTextarea();
    
    // Har 15 Seconds me Unread Incoming Emails check honge
    // setInterval(checkForIncomingEmails, 15000);
});

/* ==========================================
    UI HELPER FUNCTIONS (Try Demo, Use Cases, Pricing)
========================================== */
function scrollToPrompt() {
    const input = document.getElementById("userInput");
    if (input) {
        input.scrollIntoView({ behavior: "smooth", block: "center" });
        setTimeout(() => input.focus(), 500); 
    }
}

function selectPlan(planName) {
    alert(`🚀 Thanks for choosing the ${planName}! This feature is in early development. Waitlist functionality coming soon.`);
}

const useCaseData = {
    email: '"Summarize my important emails and prepare replies for my approval."',
    research: '"Find the top 5 competitors in the AI agent space and create a comparison table."',
    data: '"Extract all invoice amounts from these attached PDFs and put them into a Google Sheet."',
    automation: '"When someone fills out my website form, add them to Mailchimp and send a welcome email."'
};

const useCaseTitles = {
    email: 'Email Automation',
    research: 'Deep Research',
    data: 'Data Extraction',
    automation: 'Workflow Automation'
};

function showUseCase(type, btnElement) {
    const allTabs = document.querySelectorAll('.tab-btn');
    allTabs.forEach(tab => tab.classList.remove('active'));
    btnElement.classList.add('active');

    const contentBox = document.getElementById('usecase-box');
    if (contentBox) {
        contentBox.innerHTML = `
            <h4>${useCaseTitles[type]}</h4>
            <p>${useCaseData[type]}</p>
        `;
    }
}

/* ==========================================
    DYNAMIC TEXTAREA AUTO-RESIZE & ENTER KEY
========================================== */
function initAutoResizeTextarea() {
    const userInput = document.getElementById("userInput");
    if (userInput) {
        userInput.addEventListener("input", autoResizeInput);
    }
}

function autoResizeInput() {
    const userInput = document.getElementById("userInput");
    if (userInput) {
        userInput.style.height = "auto";
        userInput.style.height = userInput.scrollHeight + "px";
        
        if (userInput.scrollHeight > 250) {
            userInput.classList.add("overflow-active");
        } else {
            userInput.classList.remove("overflow-active");
        }
    }
}

function handleEnter(event) {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendPrompt();
    }
}

/* ==========================================
    REAL-TIME INCOMING EMAIL WATCHER
========================================== */
async function checkForIncomingEmails() {
    if (!currentUser || !currentUser.email) return;

    try {
        const response = await fetch("http://127.0.0.1:5000/api/check-email-notifications", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_email: currentUser.email })
        });
        const res = await response.json();

        if (res.success && res.has_notification) {
            renderEmailApprovalCard(res.data);
        }
    } catch (err) {
        // Background polling silent check
    }
}

function renderEmailApprovalCard(emailData) {
    const statusElement = document.getElementById("demoStatus");
    if (!statusElement) return;

    statusElement.style.display = "block";
    
    statusElement.innerHTML = `
        <div class="action-card" id="incomingEmailCard" style="margin-top: 15px; padding: 18px; border: 1px solid #3b82f6; border-radius: 12px; background: #0f172a; text-align: left; box-shadow: 0 10px 30px rgba(59, 130, 246, 0.25);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; border-bottom: 1px solid #1e293b; padding-bottom: 8px;">
                <span style="background: #1e1b4b; color: #818cf8; padding: 4px 10px; border-radius: 20px; font-size: 0.8rem; font-weight: 600; border: 1px solid #3730a3;">
                    📧 New Email Received
                </span>
                <span style="background: #065f46; color: #34d399; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600;">
                    AI Friendly Reply Ready
                </span>
            </div>

            <div style="margin-bottom: 10px;">
                <p style="margin: 2px 0; font-size: 0.9rem; color: #f8fafc;"><strong>From:</strong> ${escapeHTML(emailData.sender)} (${escapeHTML(emailData.email)})</p>
                <p style="margin: 2px 0; font-size: 0.9rem; color: #38bdf8;"><strong>Subject:</strong> ${escapeHTML(emailData.subject)}</p>
            </div>

            <div style="background: #1e293b; padding: 10px; border-radius: 6px; font-size: 0.85rem; color: #cbd5e1; margin-bottom: 12px; border: 1px solid #334155;">
                "${escapeHTML(emailData.snippet)}"
            </div>

            <div style="margin-bottom: 12px;">
                <label style="color: #fbbf24; font-size: 0.85rem; font-weight: 600; display: block; margin-bottom: 4px;">
                    🤖 Proposed Friendly Reply (Editable):
                </label>
                <textarea id="autoEmailReplyText" style="width: 100%; height: 80px; background: #0f172a; color: #f8fafc; border: 1px solid #475569; border-radius: 6px; padding: 8px; font-family: inherit; font-size: 0.9rem; resize: vertical;">${escapeHTML(emailData.proposed_reply)}</textarea>
            </div>

            <div id="emailCardActions" style="display: flex; gap: 10px; justify-content: flex-end;">
                <button onclick="dismissEmailCard()" style="background: #475569; color: white; border: none; padding: 8px 16px; border-radius: 6px; font-weight: 600; cursor: pointer;">
                    ✕ Ignore
                </button>
                <button onclick="approveAndSendEmail('${escapeHTML(emailData.email)}', '${escapeHTML(emailData.subject)}')" style="background: #16a34a; color: white; border: none; padding: 8px 18px; border-radius: 6px; font-weight: 600; cursor: pointer;">
                    🚀 Confirm & Send Reply
                </button>
            </div>
        </div>
    `;
}

async function approveAndSendEmail(toEmail, subject) {
    const replyText = document.getElementById("autoEmailReplyText").value;
    const actionsGroup = document.getElementById("emailCardActions");

    if (actionsGroup) {
        actionsGroup.innerHTML = `<span style="color: #60a5fa; font-weight: 600;">Sending Email... ⏳</span>`;
    }

    try {
        const res = await fetch("http://127.0.0.1:5000/api/send-email", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
                to_email: toEmail, 
                subject: subject, 
                body: replyText,
                user_email: currentUser ? currentUser.email : null
            })
        });
        const data = await res.json();

        if (data.status === "success" || data.success) {
            if (actionsGroup) {
                actionsGroup.innerHTML = `<span style="color: #34d399; font-weight: bold;">✅ Reply Sent Successfully!</span>`;
            }
        } else {
            throw new Error(data.message || "Failed to send");
        }
    } catch (err) {
        if (actionsGroup) {
            actionsGroup.innerHTML = `<span style="color: #f87171;">❌ Error sending email.</span>`;
        }
    }
}

function dismissEmailCard() {
    const card = document.getElementById("incomingEmailCard");
    if (card) card.remove();
}

/* ==========================================
    PROMPT EXECUTION ENGINE
========================================== */
async function sendPrompt() {
    const input = document.getElementById("userInput");
    const status = document.getElementById("demoStatus");

    if (!input || !status) return;

    const text = input.value.trim();
    if (text === "") {
        status.style.display = "block";
        status.innerHTML = "<div class='glass-card'>⚠️ Please enter a prompt for Inklur.</div>";
        return;
    }

    status.style.display = "block";
    status.innerHTML = "<div class='glass-card'>⏳ Inklur is analyzing your task...</div>";

    try {
        const response = await fetch("http://127.0.0.1:5000/api/execute", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                prompt: text,
                user_id: currentUser ? currentUser.email : null,
                history: chatHistory || []
            })
        });

        const data = await response.json();

        if (data.success) {
            let historyText = data.result || data.message;
            if (data.tool_name === "gmail_automation" && data.result && data.result.target_person) {
                historyText = `Gmail Task Processed for '${data.result.target_person}'`;
            }

            chatHistory.push({ sender: "user", text: text });
            chatHistory.push({ sender: "model", text: typeof historyText === "string" ? historyText : "Task Executed" });
            localStorage.setItem("dopilot_history", JSON.stringify(chatHistory));
            renderHistoryList();

            displayAIResponse(data, status);
            
            input.value = "";
            input.style.height = "auto";
            input.classList.remove("overflow-active");
            
        } else {
            status.innerHTML = "<div class='glass-card'>❌ Error: " + escapeHTML(data.message) + "</div>";
        }

    } catch (error) {
        console.error("Backend Error:", error);
        status.innerHTML = "<div class='glass-card'>❌ Could not connect to Python Server. Make sure 'python app.py' is running.</div>";
    }
}

function displayAIResponse(data, statusElement) {
    // 1. Handle Gmail Automation Workflow
    if (data.tool_name === "gmail_automation") {
        const res = data.result;

        // SCENARIO A: Multiple Contacts Found (Disambiguation)
        if (res && res.status === "multiple_found") {
            let optionsHtml = res.contacts.map((contact, index) => {
                const safeEmail = JSON.stringify(contact.email).replace(/"/g, '&quot;');
                const safeName = escapeHTML(contact.name);
                
                return `
                <div style="background: #1e293b; border: 1px solid #334155; padding: 10px; margin-bottom: 8px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <div style="font-size: 0.8rem; color: #94a3b8;">Option ${index + 1}</div>
                        <div style="font-weight: 600; color: #f8fafc; font-size: 0.95rem;">${safeName}</div>
                        <div style="font-size: 0.80rem; color: #38bdf8;">${escapeHTML(contact.email)}</div>
                    </div>
                    <button onclick='handleContactSelection(${safeEmail})' style="background: #6366f1; color: white; border: none; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 0.85rem; font-weight: bold; transition: 0.2s;">
                        Select
                    </button>
                </div>
            `;
            }).join('');

            statusElement.innerHTML = `
                <div class="glass-card" style="margin-top: 10px; background: #0f172a; border-radius: 12px; padding: 18px; border: 1px solid #fbbf24;">
                    <h4 style="margin: 0 0 12px 0; color: #fbbf24;">🔍 Multiple Contacts Found</h4>
                    <p style="font-size: 0.9rem; color: #cbd5e1; margin-bottom: 12px;">${escapeHTML(res.message)}</p>
                    <div style="max-height: 250px; overflow-y: auto; padding-right: 5px;">
                        ${optionsHtml}
                    </div>
                </div>
            `;
            return;
        }

        // SCENARIO B: Single Exact Match Found
        if (res && res.status === "success") {
            const safeTarget = JSON.stringify(res.target_email || res.target_person).replace(/"/g, '&quot;');
            const safeSubject = JSON.stringify(res.subject).replace(/"/g, '&quot;');

            statusElement.innerHTML = `
                <div class="glass-card" style="margin-top: 10px; text-align: left; background: #0f172a; border-radius: 12px; padding: 18px; color: #F8FAFC; border: 1px solid #3b82f6;">
                    <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #334155; padding-bottom: 10px;">
                        <h4 style="margin: 0; color: #38BDF8;">📧 Target Email Detected</h4>
                        <span style="background: #10B981; color: #000; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: bold;">Gmail Active</span>
                    </div>

                    <div style="margin-top: 12px;">
                        <p style="margin: 4px 0; font-size: 0.9rem;"><strong>Sender:</strong> <span style="color: #94A3B8;">${escapeHTML(res.target_person)}</span></p>
                        <p style="margin: 4px 0; font-size: 0.9rem;"><strong>Subject:</strong> <span style="color: #94A3B8;">${escapeHTML(res.subject)}</span></p>
                        <div style="background: #1e293b; padding: 10px; border-radius: 6px; font-size: 0.85rem; color: #CBD5E1; margin-top: 8px; border: 1px solid #334155;">
                            "${escapeHTML(res.snippet)}"
                        </div>
                    </div>

                    <div style="margin-top: 14px;">
                        <h5 style="color: #F59E0B; margin: 0 0 6px 0; font-size: 0.9rem;">🤖 Proposed AI Response:</h5>
                        <textarea id="emailMessage" style="width: 100%; height: 75px; background: #1e293b; color: #F8FAFC; border: 1px solid #475569; border-radius: 6px; padding: 8px; font-family: inherit; resize: vertical;">${escapeHTML(res.proposed_reply)}</textarea>
                    </div>

                    <button onclick='sendDirectEmail(${safeTarget}, ${safeSubject})' style="margin-top: 12px; width: 100%; background: #2563EB; color: white; border: none; padding: 10px; border-radius: 6px; font-weight: bold; cursor: pointer; transition: 0.2s;">
                        🚀 Confirm & Send Email Now
                    </button>
                </div>
            `;
            return;
        } 
        
        statusElement.innerHTML = `<div class='glass-card' style='color: #EF4444;'>❌ ${escapeHTML(res ? res.message : "Email fetch failed")}</div>`;
        return;
    }

    // 2. Handle Standard AI Text Responses & Web Automation
    let resultText = data.result || (data.parsed_action ? data.parsed_action.message : "Task analyzed successfully.");
    
    let messageHTML = `
        🚀 <strong>Inklur Response:</strong>
        <div class='glass-card' style="margin-top: 6px;">
            ${escapeHTML(resultText)}
        </div>
    `;

    if (data.action_required && data.parsed_action) {
        const action = data.parsed_action;
        currentPendingAction = action;

        let paramsHtml = "";
        if (action.parameters && Array.isArray(action.parameters)) {
            paramsHtml = action.parameters.map(param => `
                <div style="display:flex; justify-content:space-between; margin-bottom: 4px; font-size: 0.85rem;">
                    <span style="color: #94a3b8; font-weight: 500;">${escapeHTML(param.label)}:</span>
                    <span style="color: #f1f5f9; font-weight: 600;">${escapeHTML(param.value)}</span>
                </div>
            `).join('');
        }

        messageHTML += `
            <div class="action-card" id="activeActionCard" style="margin-top: 15px; padding: 16px; border: 1px solid #3b82f6; border-radius: 10px; background: #0f172a; text-align: left;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <span style="background: #1e1b4b; color: #818cf8; padding: 3px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; border: 1px solid #3730a3;">
                        ⚡ ${escapeHTML(action.tool_name || 'System Automation')}
                    </span>
                    <span id="cardStatusBadge" style="background: #451a03; color: #fbbf24; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600;">
                        Pending Approval
                    </span>
                </div>

                <h4 style="margin: 0 0 10px 0; color: #f8fafc; font-size: 0.95rem;">${escapeHTML(action.action_title || 'Task Execution Plan')}</h4>
                
                <div style="background: #1e293b; padding: 10px; border-radius: 6px; margin-bottom: 12px;">
                    ${paramsHtml}
                </div>

                <div id="cardActionsGroup" style="display: flex; gap: 10px; justify-content: flex-end;">
                    <button onclick="cancelAction()" style="background: #475569; color: white; border: none; padding: 8px 14px; border-radius: 6px; font-weight: 600; cursor: pointer;">
                        ✕ Cancel
                    </button>
                    <button onclick="approveAction()" style="background: #16a34a; color: white; border: none; padding: 8px 14px; border-radius: 6px; font-weight: 600; cursor: pointer;">
                        ✓ Approve & Execute
                    </button>
                </div>
            </div>
        `;
    }

    statusElement.innerHTML = messageHTML;
}

function handleContactSelection(exactEmail) {
    const input = document.getElementById("userInput");
    input.value = `Send an email to ${exactEmail}`;
    sendPrompt();
}

async function approveAction() {
    const badge = document.getElementById("cardStatusBadge");
    const actionsGroup = document.getElementById("cardActionsGroup");

    if (badge) {
        badge.style.background = "#1e3a8a";
        badge.style.color = "#93c5fd";
        badge.innerText = "Running... ⏳";
    }

    if (actionsGroup) {
        actionsGroup.innerHTML = `<span style="color: #60a5fa;">Launching Playwright Engine...</span>`;
    }

    try {
        const response = await fetch("http://127.0.0.1:5000/api/execute-task", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(currentPendingAction || {})
        });

        const resData = await response.json();

        if (resData.success) {
            if (badge) {
                badge.style.background = "#064e3b";
                badge.style.color = "#34d399";
                badge.innerText = "Completed ✓";
            }
            
            // 🛠️ FIX: Screenshot extraction (Supports direct, nested data, or data.screenshot)
            const base64Screenshot = resData.screenshot || (resData.data && resData.data.screenshot);

            if (actionsGroup) {
                if (base64Screenshot) {
                    actionsGroup.innerHTML = `
                        <div style="width: 100%; margin-top: 10px;">
                            <div style="color: #34d399; font-weight: 600; margin-bottom: 8px;">
                                ✅ Live Browser Result:
                            </div>
                            <div style="border: 2px solid #334155; border-radius: 8px; overflow: hidden;">
                                <img src="${base64Screenshot}" alt="Browser Screenshot" style="width: 100%; height: auto; display: block;" />
                            </div>
                        </div>
                    `;
                } else {
                    actionsGroup.innerHTML = `<span style="color: #34d399; font-weight: bold;">✅ Task Executed Successfully (No screenshot captured)</span>`;
                }
            }
        } else {
            throw new Error(resData.error || "Execution failed");
        }
    } catch (err) {
        if (badge) {
            badge.style.background = "#831843";
            badge.innerText = "Failed ❌";
        }
        if (actionsGroup) {
            actionsGroup.innerHTML = `<span style="color: #f87171;">Error: ${escapeHTML(err.message)}</span>`;
        }
    }
}

function cancelAction() {
    const badge = document.getElementById("cardStatusBadge");
    const actionsGroup = document.getElementById("cardActionsGroup");

    if (badge) {
        badge.style.background = "#4c0519";
        badge.style.color = "#f87171";
        badge.innerText = "Cancelled";
    }

    if (actionsGroup) {
        actionsGroup.innerHTML = `<span style="color: #f87171; font-weight: 600; font-size: 0.85rem;">Task Cancelled</span>`;
    }
}

async function sendDirectEmail(toEmail, subject) {
    const bodyText = document.getElementById("emailMessage").value;
    const status = document.getElementById("demoStatus");
    
    try {
        const res = await fetch("http://127.0.0.1:5000/api/send-email", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
                to_email: toEmail, 
                subject: subject, 
                body: bodyText,
                user_email: currentUser ? currentUser.email : null
            })
        });
        const data = await res.json();
        
        if (data.status === "success" || data.success) {
            alert("✅ Email Sent Successfully!");
            if (status) {
                status.innerHTML = `<div class='glass-card' style='color: #10B981;'>✅ Email sent successfully to ${escapeHTML(toEmail)}!</div>`;
            }
        } else {
            alert("❌ Failed to send email: " + (data.error || "Unknown error"));
        }
    } catch (err) {
        alert("❌ Network Error: Server unreachable.");
    }
}

/* ==========================================
    CHAT HISTORY & AUTH MANAGEMENT
========================================== */
function renderHistoryList() {
    const listDiv = document.getElementById("historyList");
    if (!listDiv) return;
    listDiv.innerHTML = "";

    chatHistory.filter(msg => msg.sender === "user").forEach(msg => {
        const item = document.createElement("div");
        item.className = "history-item";
        item.innerText = "💬 " + msg.text;
        listDiv.appendChild(item);
    });
}

function clearHistory() {
    chatHistory = [];
    localStorage.removeItem("dopilot_history");
    renderHistoryList();
    const status = document.getElementById("demoStatus");
    if (status) status.innerHTML = "<div class='glass-card'>Started a fresh new conversation!</div>";
}

function openAuthModal(mode) {
    const modal = document.getElementById("authModal");
    if (modal) {
        modal.style.display = "flex";
        toggleAuthMode(mode);
    }
}

function closeAuthModal() {
    const modal = document.getElementById("authModal");
    if (modal) {
        modal.style.display = "none";
        clearAuthAlert();
    }
}

function toggleAuthMode(mode) {
    const loginBox = document.getElementById("loginFormContainer");
    const signupBox = document.getElementById("signupFormContainer");
    clearAuthAlert();

    if (mode === "login") {
        loginBox.style.display = "block";
        signupBox.style.display = "none";
    } else {
        loginBox.style.display = "none";
        signupBox.style.display = "block";
    }
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

async function handleLogin() {
    const email = document.getElementById("loginEmail").value.trim();
    const password = document.getElementById("loginPassword").value;

    if (!email || !password) {
        showAuthAlert("Please enter both email and password.");
        return;
    }

    try {
        const response = await fetch("http://127.0.0.1:5000/api/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email, password: password })
        });

        const data = await response.json();

        if (data.success) {
            currentUser = data.user;
            localStorage.setItem("dopilot_user", JSON.stringify(currentUser));
            showAuthAlert("Login Successful!", false);
            setTimeout(() => {
                closeAuthModal();
                updateNavUI();
            }, 1000);
        } else {
            showAuthAlert(data.message || "Invalid credentials.");
        }
    } catch (err) {
        console.error(err);
        showAuthAlert("Could not connect to Python backend.");
    }
}

async function handleSignup() {
    const name = document.getElementById("signupName").value.trim();
    const email = document.getElementById("signupEmail").value.trim();
    const password = document.getElementById("signupPassword").value;

    if (!name || !email || !password) {
        showAuthAlert("All fields are required.");
        return;
    }

    try {
        const response = await fetch("http://127.0.0.1:5000/api/signup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: name, email: email, password: password })
        });

        const data = await response.json();

        if (data.success) {
            showAuthAlert("Account created! Switching to Login...", false);
            setTimeout(() => {
                toggleAuthMode("login");
                document.getElementById("loginEmail").value = email;
            }, 1500);
        } else {
            showAuthAlert(data.message || "Signup failed.");
        }
    } catch (err) {
        console.error(err);
        showAuthAlert("Could not connect to Python backend.");
    }
}

function handleLogout() {
    currentUser = null;
    localStorage.removeItem("dopilot_user");
    updateNavUI();
}

// Hover & Click supported dropdown toggler
function toggleProfileDropdown(event, forceState) {
    if (event) event.stopPropagation();
    const dropdown = document.getElementById("profileDropdown");
    if (!dropdown) return;

    if (typeof forceState === "boolean") {
        if (forceState) {
            dropdown.classList.add("show");
        } else {
            dropdown.classList.remove("show");
        }
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
                <div class="profile-badge" onclick="toggleProfileDropdown(event)">
                    <span>👤 ${escapeHTML(currentUser.name || 'User')}</span>
                    <span style="font-size: 0.7rem; color: #94a3b8;">▼</span>
                </div>
                
                <div class="profile-dropdown" id="profileDropdown">
                    <button onclick="openProfileSettings()">✏️ Edit Profile</button>
                    <button onclick="selectPlan('Pro Plan')">⚡ Upgrade Plan</button>
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
    alert("✏️ Edit profile feature coming soon!");
}

function escapeHTML(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
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