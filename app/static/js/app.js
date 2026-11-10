/**
 * Details of Panchayat Secretaries Working in Khammam District
 * Official Government Portal - Single Page Application Engine
 */

const APP_PATH_PREFIX = window.location.pathname.startsWith("/ps-data") ? "/ps-data" : (window.location.pathname.startsWith("/psdata") ? "/psdata" : "");
const API_BASE = `${APP_PATH_PREFIX}/api`;
let authToken = localStorage.getItem("khammam_ps_token") || null;
let currentUser = JSON.parse(localStorage.getItem("khammam_ps_user") || "null");

let sessionTimerInterval = null;
let sessionSecondsRemaining = 15 * 60; // 15 minutes
let currentRoute = "dashboard";

// Cache for dropdowns
let cachedMandals = [];
let cachedPanchayats = [];
let centralizedPanchayats = [];

// ==========================================
// INITIALIZATION & AUTH STATE
// ==========================================
document.addEventListener("DOMContentLoaded", async () => {
  if (authToken && currentUser) {
    showAuthenticatedUI();
    startSessionTimer();
    initApp();
  } else {
    showLoginModal();
  }
});

function initApp() {
  lucide.createIcons();
  loadCommonData();
  
  // Hash routing
  window.addEventListener("hashchange", handleHashChange);
  const initialHash = window.location.hash.replace("#", "") || "dashboard";
  navigate(initialHash);
}

function handleHashChange() {
  const hash = window.location.hash.replace("#", "") || "dashboard";
  navigate(hash);
}

function navigate(route) {
  // Unified Stage 2 handles both Salary GP and Working Station Mapping
  if (route === "stage3-working-mapping") {
    route = "stage2-salary-mapping";
  }

  // Mandal Admin cannot access District Reports (A-Z)
  if (currentUser && currentUser.role === "MANDAL_ADMIN" && route === "reports") {
    route = "mandal-reports";
  }

  currentRoute = route;
  window.location.hash = route;
  
  // Highlight active nav item
  document.querySelectorAll(".nav-item").forEach(item => {
    item.classList.remove("bg-govblue-800", "text-white");
    if (item.getAttribute("href") === `#${route}`) {
      item.classList.add("bg-govblue-800", "text-white");
    }
  });

  // Hide all view panels
  document.querySelectorAll(".view-panel").forEach(p => p.classList.add("hidden"));
  
  // Show target panel
  const target = document.getElementById(`view-${route}`);
  if (target) {
    target.classList.remove("hidden");
    loadRouteView(route);
  } else {
    // Fallback to dashboard
    document.getElementById("view-dashboard").classList.remove("hidden");
    loadRouteView("dashboard");
  }
  
  lucide.createIcons();
}

async function loadCommonData() {
  try {
    const [mandalsRes, allGpsRes] = await Promise.all([
      fetchAPI("/panchayats/mandals"),
      fetchAPI("/panchayats/all-centralized")
    ]);
    cachedMandals = mandalsRes || [];
    centralizedPanchayats = allGpsRes || [];
    updateHeaderAndNavScope();
  } catch (e) {
    console.error("Failed to preload common data", e);
  }
}

// ==========================================
// SESSION INACTIVITY TIMER (15 MINUTES)
// ==========================================
function startSessionTimer() {
  sessionSecondsRemaining = 15 * 60;
  clearInterval(sessionTimerInterval);
  
  const timerPill = document.getElementById("session-timer-pill");
  const timerDisplay = document.getElementById("timer-display");
  if (timerPill) timerPill.classList.remove("hidden");
  
  sessionTimerInterval = setInterval(() => {
    sessionSecondsRemaining--;
    if (sessionSecondsRemaining <= 0) {
      clearInterval(sessionTimerInterval);
      alert("Your session has timed out due to 15 minutes of inactivity as per Government Security Policy. Please log in again.");
      handleLogout();
      return;
    }
    
    const minutes = Math.floor(sessionSecondsRemaining / 60);
    const seconds = sessionSecondsRemaining % 60;
    if (timerDisplay) {
      timerDisplay.textContent = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
      if (sessionSecondsRemaining < 120) {
        timerDisplay.classList.add("text-red-400", "animate-pulse");
      } else {
        timerDisplay.classList.remove("text-red-400", "animate-pulse");
      }
    }
  }, 1000);
}

function resetSessionTimer() {
  sessionSecondsRemaining = 15 * 60;
}

// Reset timer on user interactions
window.addEventListener("mousemove", resetSessionTimer, { passive: true });
window.addEventListener("keydown", resetSessionTimer, { passive: true });
window.addEventListener("click", resetSessionTimer, { passive: true });

// ==========================================
// AUTHENTICATION & LOGIN LOGIC
// ==========================================
async function handleLoginSubmit(event) {
  event.preventDefault();
  const username = document.getElementById("login-username").value.trim();
  const password = document.getElementById("login-password").value;
  
  const errorAlert = document.getElementById("login-error-alert");
  const conflictAlert = document.getElementById("login-session-conflict-alert");
  errorAlert.classList.add("hidden");
  conflictAlert.classList.add("hidden");
  
  const submitBtn = document.getElementById("btn-login-submit");
  submitBtn.disabled = true;
  submitBtn.innerHTML = `<span>Verifying credentials...</span>`;

  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username,
        password,
        device_info: navigator.userAgent
      })
    });

    const data = await res.json();

    if (!res.ok) {
      if (res.status === 409) {
        // MANDATORY SINGLE SESSION RESTRICTION CONFLICT
        conflictAlert.innerHTML = `
          <div class="flex items-start">
            <i data-lucide="shield-alert" class="w-5 h-5 mr-2 text-amber-700 flex-shrink-0 mt-0.5"></i>
            <div>
              <strong>CONCURRENT LOGIN REJECTED:</strong><br>
              ${data.detail || "This Mandal account is already logged in on another device. Please logout from the existing device before attempting a new login."}
            </div>
          </div>
        `;
        conflictAlert.classList.remove("hidden");
        lucide.createIcons();
      } else {
        errorAlert.textContent = data.detail || "Authentication failed. Please check credentials.";
        errorAlert.classList.remove("hidden");
      }
      submitBtn.disabled = false;
      submitBtn.innerHTML = `<span>Authenticate & Access Portal</span><i data-lucide="arrow-right" class="w-4 h-4 ml-1.5"></i>`;
      lucide.createIcons();
      return;
    }

    // Success
    authToken = data.access_token;
    currentUser = data;
    localStorage.setItem("khammam_ps_token", authToken);
    localStorage.setItem("khammam_ps_user", JSON.stringify(currentUser));

    document.getElementById("login-modal").classList.add("hidden");
    showAuthenticatedUI();
    startSessionTimer();
    initApp();

  } catch (err) {
    errorAlert.textContent = "Network error connecting to district server. Please ensure server is running.";
    errorAlert.classList.remove("hidden");
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<span>Authenticate & Access Portal</span><i data-lucide="arrow-right" class="w-4 h-4 ml-1.5"></i>`;
    lucide.createIcons();
  }
}

function showLoginModal() {
  document.getElementById("login-modal").classList.remove("hidden");
  document.getElementById("app-container").classList.add("hidden");
  document.getElementById("top-user-pill").classList.add("hidden");
  document.getElementById("session-timer-pill").classList.add("hidden");

  // Reset header back to district default
  const coverageSubtitle = document.getElementById("header-coverage-subtitle");
  if (coverageSubtitle) coverageSubtitle.textContent = "Covering all 571 Gram Panchayats & 20 Mandals";
  const badge1Label = document.getElementById("header-badge-1-label");
  if (badge1Label) badge1Label.textContent = "Gram Panchayats";
  const badge1Val = document.getElementById("header-badge-1-val");
  if (badge1Val) badge1Val.textContent = "571";
  const badge2Label = document.getElementById("header-badge-2-label");
  if (badge2Label) badge2Label.textContent = "Mandals";
  const badge2Val = document.getElementById("header-badge-2-val");
  if (badge2Val) badge2Val.textContent = "20";
  const discCount = document.getElementById("header-disc-count");
  if (discCount) discCount.textContent = "0";

  lucide.createIcons();
}

function showAuthenticatedUI() {
  document.getElementById("login-modal").classList.add("hidden");
  document.getElementById("app-container").classList.remove("hidden");
  
  const topPill = document.getElementById("top-user-pill");
  topPill.classList.remove("hidden");
  topPill.classList.add("flex");
  
  document.getElementById("top-username").textContent = currentUser.display_name || currentUser.username;
  document.getElementById("side-user-name").textContent = currentUser.display_name || currentUser.username;
  
  const roleBadge = document.getElementById("top-role-badge");
  const sideMandal = document.getElementById("side-user-mandal");
  
  if (currentUser.role === "SUPER_ADMIN") {
    roleBadge.textContent = "DISTRICT SUPER ADMIN";
    roleBadge.className = "px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500 text-slate-950";
    sideMandal.textContent = "District Super Admin (All 20 Mandals)";
    document.querySelectorAll(".admin-only-section").forEach(el => el.classList.remove("hidden"));
  } else if (currentUser.role === "MANDAL_ADMIN") {
    roleBadge.textContent = `MANDAL ADMIN (${currentUser.mandal_name || 'Assigned'})`;
    roleBadge.className = "px-2 py-0.5 rounded text-[10px] font-bold bg-teal-500 text-slate-950";
    sideMandal.textContent = `Mandal: ${currentUser.mandal_name} (LGD: ${currentUser.mandal_lgd})`;
    document.querySelectorAll(".admin-only-section").forEach(el => el.classList.add("hidden"));
  } else {
    roleBadge.textContent = "DISTRICT VIEWER";
    roleBadge.className = "px-2 py-0.5 rounded text-[10px] font-bold bg-slate-500 text-white";
    sideMandal.textContent = "District Collectorate / Viewer";
    document.querySelectorAll(".admin-only-section").forEach(el => el.classList.add("hidden"));
  }

  // Update header banners, badges, and navigation scope for Mandal vs District
  updateHeaderAndNavScope();
}

function updateHeaderAndNavScope(summary = null) {
  if (!currentUser) return;

  const coverageSubtitle = document.getElementById("header-coverage-subtitle");
  const badge1Label = document.getElementById("header-badge-1-label");
  const badge1Val = document.getElementById("header-badge-1-val");
  const badge2Label = document.getElementById("header-badge-2-label");
  const badge2Val = document.getElementById("header-badge-2-val");
  const navDistrictReports = document.getElementById("nav-district-reports");
  const navMandalReportsLabel = document.getElementById("nav-mandal-reports-label");
  const navGPMasterLabel = document.getElementById("nav-gp-master-label");

  if (currentUser.role === "MANDAL_ADMIN") {
    // Determine Mandal GP count
    let mandalGpsCount = 0;
    if (summary && summary.total_gram_panchayats) {
      mandalGpsCount = summary.total_gram_panchayats;
    } else if (cachedMandals && cachedMandals.length > 0) {
      const myM = cachedMandals.find(m => m.id === currentUser.mandal_id);
      if (myM) mandalGpsCount = myM.total_gps;
    }
    if (!mandalGpsCount && centralizedPanchayats && centralizedPanchayats.length > 0) {
      mandalGpsCount = centralizedPanchayats.filter(gp => gp.mandal_id === currentUser.mandal_id).length;
    }

    const countText = mandalGpsCount ? `${mandalGpsCount} Gram Panchayats` : "Mandal Gram Panchayats";

    if (coverageSubtitle) {
      coverageSubtitle.textContent = `${currentUser.mandal_name} Mandal (LGD: ${currentUser.mandal_lgd}) • ${countText}`;
    }
    if (badge1Label) badge1Label.textContent = "Mandal GPs";
    if (badge1Val) badge1Val.textContent = mandalGpsCount || "-";
    if (badge2Label) badge2Label.textContent = "Mandal LGD";
    if (badge2Val) badge2Val.textContent = currentUser.mandal_lgd || "-";

    // Nav adjustments: Strictly hide district report for mandal admin
    if (navDistrictReports) navDistrictReports.classList.add("hidden");
    if (navMandalReportsLabel) navMandalReportsLabel.textContent = `${currentUser.mandal_name} Mandal Position`;
    if (navGPMasterLabel) navGPMasterLabel.textContent = `${currentUser.mandal_name} GPs (${mandalGpsCount || '...' })`;

  } else {
    // SUPER ADMIN / VIEWER: Full District View
    if (coverageSubtitle) {
      coverageSubtitle.textContent = "Covering all 571 Gram Panchayats & 20 Mandals";
    }
    if (badge1Label) badge1Label.textContent = "Gram Panchayats";
    if (badge1Val) badge1Val.textContent = "571";
    if (badge2Label) badge2Label.textContent = "Mandals";
    if (badge2Val) badge2Val.textContent = "20";

    if (navDistrictReports) navDistrictReports.classList.remove("hidden");
    if (navMandalReportsLabel) navMandalReportsLabel.textContent = "Mandal-wise Position";
    if (navGPMasterLabel) navGPMasterLabel.textContent = "GP Master (571 GPs)";
  }
}

async function handleLogout(skipServerLogout = false) {
  if (!skipServerLogout && authToken) {
    try {
      await fetch(`${API_BASE}/auth/logout`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${authToken}` }
      });
    } catch (e) {
      // Continue local cleanup
    }
  }
  clearInterval(sessionTimerInterval);
  authToken = null;
  currentUser = null;
  localStorage.removeItem("khammam_ps_token");
  localStorage.removeItem("khammam_ps_user");
  showLoginModal();
}

// ==========================================
// API CLIENT HELPER
// ==========================================
async function fetchAPI(endpoint, options = {}) {
  resetSessionTimer();
  const headers = options.headers || {};
  if (authToken) {
    headers["Authorization"] = `Bearer ${authToken}`;
  }
  if (!options.isFormData && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers
  });

  if (res.status === 401) {
    // Token expired or force logged out
    const err = await res.json().catch(() => ({}));
    alert(err.detail || "Your session has ended. Please log in again.");
    handleLogout(true);
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const rawText = await res.text().catch(() => "");
    let errorData;
    try {
      errorData = JSON.parse(rawText);
    } catch {
      errorData = { detail: rawText || res.statusText || `HTTP Error ${res.status}` };
    }
    throw errorData;
  }

  return res.json();
}

// ==========================================
// VIEW ROUTER DISPATCHER
// ==========================================
function loadRouteView(route) {
  switch (route) {
    case "dashboard":
      renderDashboardView();
      break;
    case "gp-master":
      renderGPMasterView();
      break;
    case "stage1-employee-reg":
      renderStage1EmployeeRegView();
      break;
    case "stage2-salary-mapping":
      renderStage2SalaryMappingView();
      break;
    case "stage3-working-mapping":
      renderStage3WorkingMappingView();
      break;
    case "internal-reassignment":
      renderInternalReassignmentView();
      break;
    case "clear-vacancy-register":
      renderClearVacancyRegisterView();
      break;
    case "reconciliation-report":
      renderReconciliationReportView();
      break;
    case "employee-entry":
      renderEmployeeEntryView();
      break;
    case "employee-master":
      renderEmployeeMasterView();
      break;
    case "salary-claiming":
      renderSalaryClaimingView();
      break;
    case "employee-tracking":
      renderEmployeeTrackingView();
      break;
    case "deputation-chains":
      renderDeputationChainsView();
      break;
    case "verification-centre":
      renderVerificationCentreView();
      break;
    case "discrepancies":
      renderDiscrepanciesView();
      break;
    case "availability":
      renderAvailabilityView();
      break;
    case "reports":
      renderReportsView();
      break;
    case "mandal-reports":
      renderMandalReportsView();
      break;
    case "import-export":
      renderImportExportView();
      break;
    case "user-management":
      renderUserManagementView();
      break;
    case "sessions-history":
      renderSessionsHistoryView();
      break;
    case "audit-logs":
      renderAuditLogsView();
      break;
  }
}

// ==========================================
// 1. DASHBOARD VIEW
// ==========================================
async function renderDashboardView() {
  const isMandal = currentUser && currentUser.role === "MANDAL_ADMIN";
  const mandalName = currentUser?.mandal_name || "Mandal";
  const title = isMandal ? `${mandalName} Mandal Dashboard` : "District Executive Dashboard";
  const subtitle = isMandal
    ? `Panchayat Secretary Posting, Deputation and Availability Analytics for ${mandalName} Mandal`
    : "Panchayat Secretary Posting, Deputation and Availability Analytics across Khammam District";
  const gpCardLabel = isMandal ? "Mandal Gram Panchayats" : "Gram Panchayats";
  const gpCardSubtext = isMandal ? `Total GPs in ${mandalName}` : "Total Sanctioned Posts";

  const container = document.getElementById("view-dashboard");
  container.innerHTML = `
    <div class="flex flex-wrap justify-between items-center mb-6 gap-3">
      <div>
        <h2 class="text-xl font-bold text-slate-900">${title}</h2>
        <p class="text-xs text-slate-500">${subtitle}</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <button onclick="navigate('stage1-employee-reg')" class="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded text-xs font-semibold flex items-center shadow transition">
          <i data-lucide="user-plus" class="w-3.5 h-3.5 mr-1.5"></i> Stage 1: Register PS
        </button>
        <button onclick="navigate('stage2-salary-mapping')" class="px-3 py-1.5 bg-teal-700 hover:bg-teal-800 text-white rounded text-xs font-semibold flex items-center shadow transition">
          <i data-lucide="map-pin" class="w-3.5 h-3.5 mr-1.5"></i> Stage 2: Salary & Working Mapping
        </button>
        <button onclick="navigate('internal-reassignment')" class="px-3 py-1.5 bg-pink-700 hover:bg-pink-800 text-white rounded text-xs font-semibold flex items-center shadow transition">
          <i data-lucide="shuffle" class="w-3.5 h-3.5 mr-1.5"></i> Internal Reassign
        </button>
        <button onclick="triggerDiscrepancyScan()" class="px-3 py-1.5 bg-rose-700 hover:bg-rose-800 text-white rounded text-xs font-semibold flex items-center shadow transition">
          <i data-lucide="scan" class="w-3.5 h-3.5 mr-1.5"></i> Scan Discrepancies
        </button>
      </div>
    </div>

    <!-- 2-STAGE ARCHITECTURE PIPELINE PROGRESS -->
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-4 mb-6">
      <div class="flex justify-between items-center mb-3">
        <h3 class="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center">
          <i data-lucide="layers" class="w-4 h-4 mr-2 text-govblue-900"></i>
          Two-Stage Data Architecture & Reassignment Pipeline
        </h3>
        <span class="text-[10px] text-slate-500 font-medium">Unified Salary & Working Station Workflow</span>
      </div>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div class="p-3 rounded-lg bg-amber-50/70 border border-amber-200 cursor-pointer hover:bg-amber-100 transition" onclick="navigate('stage1-employee-reg')">
          <div class="flex justify-between items-start">
            <span class="text-[10px] font-bold text-amber-800 uppercase">Stage 1: Registered PS</span>
            <span class="p-1 rounded bg-amber-200 text-amber-900"><i data-lucide="user-check" class="w-3.5 h-3.5"></i></span>
          </div>
          <div id="stat-stage1" class="text-xl font-bold text-amber-900 font-mono mt-1">-</div>
          <div class="text-[10px] text-amber-700 mt-0.5">Global Master Directory</div>
        </div>
        <div class="p-3 rounded-lg bg-teal-50/70 border border-teal-200 cursor-pointer hover:bg-teal-100 transition" onclick="navigate('stage2-salary-mapping')">
          <div class="flex justify-between items-start">
            <span class="text-[10px] font-bold text-teal-800 uppercase">Stage 2: Salary Mapped</span>
            <span class="p-1 rounded bg-teal-200 text-teal-900"><i data-lucide="wallet" class="w-3.5 h-3.5"></i></span>
          </div>
          <div id="stat-stage2" class="text-xl font-bold text-teal-900 font-mono mt-1">-</div>
          <div class="text-[10px] text-teal-700 mt-0.5">Salary GP & Service Status</div>
        </div>
        <div class="p-3 rounded-lg bg-indigo-50/70 border border-indigo-200 cursor-pointer hover:bg-indigo-100 transition" onclick="navigate('stage2-salary-mapping')">
          <div class="flex justify-between items-start">
            <span class="text-[10px] font-bold text-indigo-800 uppercase">Stage 2: Working Mapped</span>
            <span class="p-1 rounded bg-indigo-200 text-indigo-900"><i data-lucide="map-pin" class="w-3.5 h-3.5"></i></span>
          </div>
          <div id="stat-stage3" class="text-xl font-bold text-indigo-900 font-mono mt-1">-</div>
          <div class="text-[10px] text-indigo-700 mt-0.5">Deputation & Station Verified</div>
        </div>
        <div class="p-3 rounded-lg bg-pink-50/70 border border-pink-200 cursor-pointer hover:bg-pink-100 transition" onclick="navigate('internal-reassignment')">
          <div class="flex justify-between items-start">
            <span class="text-[10px] font-bold text-pink-800 uppercase">Internal Reassignments</span>
            <span class="p-1 rounded bg-pink-200 text-pink-900"><i data-lucide="shuffle" class="w-3.5 h-3.5"></i></span>
          </div>
          <div id="stat-reassignments" class="text-xl font-bold text-pink-900 font-mono mt-1">-</div>
          <div class="text-[10px] text-pink-700 mt-0.5">GP-X to GP-Z Adjustments</div>
        </div>
      </div>
    </div>

    <!-- Summary Cards -->
    <div id="dashboard-cards" class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center space-x-3">
        <div class="p-3 bg-blue-50 text-blue-700 rounded-lg"><i data-lucide="landmark" class="w-6 h-6"></i></div>
        <div>
          <div class="text-[11px] font-bold text-slate-500 uppercase">${gpCardLabel}</div>
          <div id="stat-total-gps" class="text-2xl font-bold text-slate-900 font-mono">-</div>
          <div class="text-[10px] text-slate-400">${gpCardSubtext}</div>
        </div>
      </div>
      <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center space-x-3">
        <div class="p-3 bg-emerald-50 text-emerald-700 rounded-lg"><i data-lucide="user-check" class="w-6 h-6"></i></div>
        <div>
          <div class="text-[11px] font-bold text-slate-500 uppercase">Regular Working</div>
          <div id="stat-regular-working" class="text-2xl font-bold text-emerald-600 font-mono">-</div>
          <div class="text-[10px] text-emerald-600">Available on Regular Duty</div>
        </div>
      </div>
      <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center space-x-3">
        <div class="p-3 bg-amber-50 text-amber-700 rounded-lg"><i data-lucide="user-x" class="w-6 h-6"></i></div>
        <div>
          <div class="text-[11px] font-bold text-slate-500 uppercase">Staff Not Available</div>
          <div id="stat-unavailable" class="text-2xl font-bold text-amber-600 font-mono">-</div>
          <div class="text-[10px] text-slate-400">Suspension / Abscond / Leave</div>
        </div>
      </div>
      <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center space-x-3 cursor-pointer hover:border-rose-400 transition" onclick="navigate('clear-vacancy-register')">
        <div class="p-3 bg-rose-50 text-rose-700 rounded-lg"><i data-lucide="shield-alert" class="w-6 h-6"></i></div>
        <div>
          <div class="text-[11px] font-bold text-slate-500 uppercase">Clear Vacancies (Cat A)</div>
          <div id="stat-clear-vacancies" class="text-2xl font-bold text-rose-600 font-mono">-</div>
          <div class="text-[10px] text-rose-500">No Salary & No Working PS</div>
        </div>
      </div>
    </div>

    <!-- DYNAMIC GP POSITION CATEGORIES ROW -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <div class="bg-white p-3.5 rounded-lg border border-slate-200 hover:border-rose-400 cursor-pointer transition text-center" onclick="navigate('clear-vacancy-register')">
        <div class="text-[10px] font-bold text-rose-700 uppercase">Category A (Clear Vacancy)</div>
        <div id="stat-cat-a" class="text-xl font-bold text-rose-700 font-mono">-</div>
        <div class="text-[9px] text-slate-400">No Salary & No Deputed PS</div>
      </div>
      <div class="bg-white p-3.5 rounded-lg border border-slate-200 hover:border-teal-400 cursor-pointer transition text-center" onclick="navigate('reports')">
        <div class="text-[10px] font-bold text-teal-700 uppercase">Category B (Deputed in Vacancy)</div>
        <div id="stat-cat-b" class="text-xl font-bold text-teal-700 font-mono">-</div>
        <div class="text-[9px] text-slate-400">Vacant GP with Deputed PS</div>
      </div>
      <div class="bg-white p-3.5 rounded-lg border border-slate-200 hover:border-purple-400 cursor-pointer transition text-center" onclick="navigate('reports')">
        <div class="text-[10px] font-bold text-purple-700 uppercase">Category C (Deputed Out)</div>
        <div id="stat-cat-c" class="text-xl font-bold text-purple-700 font-mono">-</div>
        <div class="text-[9px] text-slate-400">Salary GP with PS Deputed</div>
      </div>
      <div class="bg-white p-3.5 rounded-lg border border-slate-200 hover:border-amber-400 cursor-pointer transition text-center" onclick="navigate('reports')">
        <div class="text-[10px] font-bold text-amber-700 uppercase">Category D (No Working PS)</div>
        <div id="stat-cat-d" class="text-xl font-bold text-amber-700 font-mono">-</div>
        <div class="text-[9px] text-slate-400">Salary GP Unattended</div>
      </div>
    </div>

    <!-- Secondary Deputation Metric Badges -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <div class="bg-white p-3.5 rounded-lg border border-slate-200 text-center">
        <div class="text-[10px] font-bold text-slate-500 uppercase">Working in Own GP</div>
        <div id="stat-own-gp" class="text-xl font-bold text-slate-800 font-mono">-</div>
      </div>
      <div class="bg-white p-3.5 rounded-lg border border-slate-200 text-center">
        <div class="text-[10px] font-bold text-slate-500 uppercase">Deputation in Mandal</div>
        <div id="stat-dep-same-mandal" class="text-xl font-bold text-purple-700 font-mono">-</div>
      </div>
      <div class="bg-white p-3.5 rounded-lg border border-slate-200 text-center">
        <div class="text-[10px] font-bold text-slate-500 uppercase">Cross-Mandal Deputation</div>
        <div id="stat-dep-other-mandal" class="text-xl font-bold text-indigo-700 font-mono">-</div>
      </div>
      <div class="bg-white p-3.5 rounded-lg border border-slate-200 text-center">
        <div class="text-[10px] font-bold text-slate-500 uppercase">Other Dist / Dept Dep</div>
        <div id="stat-dep-other-district" class="text-xl font-bold text-teal-700 font-mono">-</div>
      </div>
    </div>

    <!-- Charts Row -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
      <!-- Availability Classification Chart -->
      <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
        <h3 class="text-sm font-bold text-slate-800 mb-3 flex items-center">
          <i data-lucide="pie-chart" class="w-4 h-4 mr-2 text-govteal-700"></i>
          Employee Service Availability Breakdown
        </h3>
        <div class="h-64 relative">
          <canvas id="chart-availability"></canvas>
        </div>
      </div>

      <!-- Deputation Breakdown Chart -->
      <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
        <h3 class="text-sm font-bold text-slate-800 mb-3 flex items-center">
          <i data-lucide="bar-chart-2" class="w-4 h-4 mr-2 text-govblue-800"></i>
          ${isMandal ? mandalName + ' Mandal' : 'District'} Deputation & Posting Distribution
        </h3>
        <div class="h-64 relative">
          <canvas id="chart-deputations"></canvas>
        </div>
      </div>
    </div>
  `;
  lucide.createIcons();

  try {
    const summary = await fetchAPI("/analytics/district-summary");
    
    document.getElementById("stat-total-gps").textContent = summary.total_gram_panchayats;
    document.getElementById("stat-regular-working").textContent = summary.available_for_regular_work;
    document.getElementById("stat-unavailable").textContent = summary.not_available_for_regular_work;
    document.getElementById("stat-clear-vacancies").textContent = summary.total_clear_vacancies;
    document.getElementById("header-disc-count").textContent = summary.active_discrepancies;
    
    document.getElementById("stat-own-gp").textContent = summary.posting_breakdown.own_gp;
    document.getElementById("stat-dep-same-mandal").textContent = summary.posting_breakdown.within_same_mandal;
    document.getElementById("stat-dep-other-mandal").textContent = summary.posting_breakdown.another_mandal;
    document.getElementById("stat-dep-other-district").textContent = summary.posting_breakdown.other_district;

    // Stage Progress stats
    if (summary.stage_progress) {
      const elS1 = document.getElementById("stat-stage1");
      if (elS1) elS1.textContent = summary.stage_progress.stage1_registered;
      const elS2 = document.getElementById("stat-stage2");
      if (elS2) elS2.textContent = summary.stage_progress.stage2_salary_mapped;
      const elS3 = document.getElementById("stat-stage3");
      if (elS3) elS3.textContent = summary.stage_progress.stage3_working_mapped;
      const elIR = document.getElementById("stat-reassignments");
      if (elIR) elIR.textContent = summary.stage_progress.internal_reassignments;
    }

    // GP Position Categories stats
    if (summary.categories) {
      const elCatA = document.getElementById("stat-cat-a");
      if (elCatA) elCatA.textContent = summary.categories.category_a_clear_vacancies;
      const elCatB = document.getElementById("stat-cat-b");
      if (elCatB) elCatB.textContent = summary.categories.category_b_deputed_in_clear_vacancies;
      const elCatC = document.getElementById("stat-cat-c");
      if (elCatC) elCatC.textContent = summary.categories.category_c_deputed_out;
      const elCatD = document.getElementById("stat-cat-d");
      if (elCatD) elCatD.textContent = summary.categories.category_d_no_staff_working;
    }

    // Refresh header with exact counts from summary
    updateHeaderAndNavScope(summary);

    // Render Availability Doughnut Chart
    const ctxAvail = document.getElementById("chart-availability").getContext("2d");
    const sbd = summary.service_status_breakdown;
    new Chart(ctxAvail, {
      type: "doughnut",
      data: {
        labels: ["Working (Available)", "Suspended", "Absconding", "Long Leave", "Medical Leave", "Maternity / CCL", "Other Leave"],
        datasets: [{
          data: [
            sbd.working,
            sbd.suspended,
            sbd.absconding,
            sbd.long_leave,
            sbd.medical_leave,
            sbd.maternity_and_ccl,
            sbd.other_leaves
          ],
          backgroundColor: [
            "#10b981", // Working - Green
            "#ef4444", // Suspended - Red
            "#451a03", // Absconding - Dark Brown
            "#f59e0b", // Long Leave - Amber
            "#06b6d4", // Medical - Cyan
            "#ec4899", // Maternity - Pink
            "#64748b"  // Other - Slate
          ]
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "right", labels: { boxWidth: 12, font: { size: 10 } } }
        }
      }
    });

    // Render Deputation Bar Chart
    const ctxDep = document.getElementById("chart-deputations").getContext("2d");
    const pbd = summary.posting_breakdown;
    new Chart(ctxDep, {
      type: "bar",
      data: {
        labels: ["Own Salary GP", "Same Mandal Dep", "Cross Mandal Dep", "Other District Dep"],
        datasets: [{
          label: "Number of Employees",
          data: [pbd.own_gp, pbd.within_same_mandal, pbd.another_mandal, pbd.other_district],
          backgroundColor: ["#1e3a8a", "#7c3aed", "#4f46e5", "#0f766e"]
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } }
      }
    });

  } catch (err) {
    console.error("Dashboard metrics load error", err);
  }
}

// ==========================================
// 2. GP MASTER (ALL 571 GRAM PANCHAYATS)
// ==========================================
let gpMasterSearch = "";
let gpMasterMandalFilter = "";
let gpMasterPage = 0;
const gpMasterPageSize = 25;

async function renderGPMasterView() {
  const isMandal = currentUser && currentUser.role === "MANDAL_ADMIN";
  const mandalName = currentUser?.mandal_name || "Mandal";
  const title = isMandal ? `${mandalName} Mandal Gram Panchayats` : "Gram Panchayat Master Database";
  const subtitle = isMandal
    ? `Directory of Gram Panchayats under ${mandalName} Mandal (LGD: ${currentUser?.mandal_lgd})`
    : "Centralized directory of all 571 Gram Panchayats across Khammam District";

  if (isMandal) {
    gpMasterMandalFilter = currentUser.mandal_id;
  }

  const container = document.getElementById("view-gp-master");
  
  // Mandal filter options
  let mandalOptions = `<option value="">All 20 Mandals (District View)</option>`;
  if (isMandal) {
    mandalOptions = `<option value="${currentUser.mandal_id}" selected>${mandalName} (LGD: ${currentUser.mandal_lgd})</option>`;
  } else {
    cachedMandals.forEach(m => {
      const isSelected = gpMasterMandalFilter == m.id ? "selected" : "";
      mandalOptions += `<option value="${m.id}" ${isSelected}>${m.mandal_name} (LGD: ${m.mandal_lgd})</option>`;
    });
  }

  const disableMandalSelect = isMandal ? "disabled" : "";

  let badgeCountText = "571 Preloaded Gram Panchayats";
  if (isMandal) {
    const myM = cachedMandals.find(m => m.id === currentUser.mandal_id);
    const count = myM ? myM.total_gps : (centralizedPanchayats.filter(gp => gp.mandal_id === currentUser.mandal_id).length || "");
    badgeCountText = `${count} ${mandalName} Gram Panchayats`;
  }

  container.innerHTML = `
    <div class="flex flex-wrap justify-between items-center mb-5 gap-3">
      <div>
        <h2 class="text-xl font-bold text-slate-900">${title}</h2>
        <p class="text-xs text-slate-500">${subtitle}</p>
      </div>
      <div class="flex items-center space-x-2">
        <span class="text-xs bg-govblue-100 text-govblue-900 font-bold px-3 py-1 rounded-full border border-govblue-200">
          ${badgeCountText}
        </span>
      </div>
    </div>

    <!-- Filter Bar -->
    <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm mb-5 flex flex-wrap gap-3 items-center">
      <div class="flex-1 min-w-[200px]">
        <label class="block text-[10px] font-bold text-slate-500 uppercase mb-1">Search GP Name or LGD Code</label>
        <div class="relative">
          <input type="text" id="gp-search-input" value="${gpMasterSearch}" placeholder="Type GP name or LGD code..." oninput="handleGPSearchChange(event)" class="w-full pl-8 pr-3 py-1.5 text-xs border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800 outline-none">
          <i data-lucide="search" class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5"></i>
        </div>
      </div>
      <div class="w-64">
        <label class="block text-[10px] font-bold text-slate-500 uppercase mb-1">Mandal Filter</label>
        <select id="gp-mandal-select" onchange="handleGPMandalChange(event)" ${disableMandalSelect} class="w-full py-1.5 px-2 text-xs border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800 outline-none bg-white">
          ${mandalOptions}
        </select>
      </div>
      <div class="pt-4">
        <button onclick="loadGPMasterData()" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-900 text-white rounded text-xs font-semibold flex items-center">
          <i data-lucide="refresh-cw" class="w-3.5 h-3.5 mr-1"></i> Refresh
        </button>
      </div>
    </div>

    <!-- Table Container -->
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs text-slate-700">
          <thead class="bg-slate-50 border-b border-slate-200 text-[11px] font-bold text-slate-600 uppercase tracking-wider">
            <tr>
              <th class="px-3.5 py-3">#</th>
              <th class="px-3.5 py-3">GP LGD Code</th>
              <th class="px-3.5 py-3">Gram Panchayat Name</th>
              <th class="px-3.5 py-3">Mandal Name</th>
              <th class="px-3.5 py-3 text-center">Salary Strength</th>
              <th class="px-3.5 py-3 text-center">Working Staff</th>
              <th class="px-3.5 py-3 text-center">Deputed Out</th>
              <th class="px-3.5 py-3 text-center">Deputed In</th>
              <th class="px-3.5 py-3 text-center">Vacancy Status</th>
              <th class="px-3.5 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody id="gp-master-tbody" class="divide-y divide-slate-100">
            <tr><td colspan="10" class="text-center py-8 text-slate-400">Loading Gram Panchayats...</td></tr>
          </tbody>
        </table>
      </div>
      <!-- Pagination -->
      <div class="p-3.5 bg-slate-50 border-t border-slate-200 flex justify-between items-center text-xs">
        <span id="gp-pagination-info" class="text-slate-500">Showing records...</span>
        <div class="flex space-x-1.5">
          <button id="gp-btn-prev" onclick="prevGPPage()" class="px-2.5 py-1 bg-white border border-slate-300 rounded hover:bg-slate-100 disabled:opacity-50">Previous</button>
          <button id="gp-btn-next" onclick="nextGPPage()" class="px-2.5 py-1 bg-white border border-slate-300 rounded hover:bg-slate-100 disabled:opacity-50">Next</button>
        </div>
      </div>
    </div>
  `;
  lucide.createIcons();

  if (currentUser.role === "MANDAL_ADMIN") {
    gpMasterMandalFilter = currentUser.mandal_id;
  }

  loadGPMasterData();
}

function handleGPSearchChange(e) {
  gpMasterSearch = e.target.value;
  gpMasterPage = 0;
  loadGPMasterData();
}

function handleGPMandalChange(e) {
  gpMasterMandalFilter = e.target.value;
  gpMasterPage = 0;
  loadGPMasterData();
}

function prevGPPage() {
  if (gpMasterPage > 0) {
    gpMasterPage--;
    loadGPMasterData();
  }
}

function nextGPPage() {
  gpMasterPage++;
  loadGPMasterData();
}

async function loadGPMasterData() {
  const tbody = document.getElementById("gp-master-tbody");
  if (!tbody) return;

  const skip = gpMasterPage * gpMasterPageSize;
  let url = `/analytics/gp-positions?skip=${skip}&limit=${gpMasterPageSize}`;
  if (gpMasterSearch) url += `&search=${encodeURIComponent(gpMasterSearch)}`;
  if (gpMasterMandalFilter) url += `&mandal_id=${gpMasterMandalFilter}`;

  try {
    const data = await fetchAPI(url);
    const items = data.items || [];
    const total = data.total || 0;

    document.getElementById("gp-pagination-info").textContent = `Showing ${items.length > 0 ? skip + 1 : 0} to ${skip + items.length} of ${total} Gram Panchayats`;
    document.getElementById("gp-btn-prev").disabled = gpMasterPage === 0;
    document.getElementById("gp-btn-next").disabled = (skip + items.length) >= total;

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" class="text-center py-8 text-slate-400">No Gram Panchayats match your search filter.</td></tr>`;
      return;
    }

    let rowsHtml = "";
    items.forEach((gp, idx) => {
      const vacancyBadge = gp.is_clear_vacancy
        ? `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-200">CLEAR VACANCY</span>`
        : `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800">ATTACHED</span>`;

      rowsHtml += `
        <tr class="table-hover-row">
          <td class="px-3.5 py-2.5 text-slate-400 font-mono text-[11px]">${skip + idx + 1}</td>
          <td class="px-3.5 py-2.5 font-bold font-mono text-slate-900">${gp.lgd_code}</td>
          <td class="px-3.5 py-2.5 font-semibold text-slate-800">${gp.gp_name}</td>
          <td class="px-3.5 py-2.5 text-slate-600">${gp.mandal_name}</td>
          <td class="px-3.5 py-2.5 text-center font-mono font-bold">${gp.salary_claiming_strength}</td>
          <td class="px-3.5 py-2.5 text-center font-mono font-bold text-emerald-600">${gp.actual_working_strength}</td>
          <td class="px-3.5 py-2.5 text-center font-mono ${gp.deputation_out > 0 ? 'text-amber-600 font-bold' : 'text-slate-400'}">${gp.deputation_out}</td>
          <td class="px-3.5 py-2.5 text-center font-mono ${gp.deputation_in > 0 ? 'text-purple-600 font-bold' : 'text-slate-400'}">${gp.deputation_in}</td>
          <td class="px-3.5 py-2.5 text-center">${vacancyBadge}</td>
          <td class="px-3.5 py-2.5 text-right space-x-1.5">
            <button onclick="viewGPDetails(${gp.lgd_code})" class="px-2 py-1 bg-govblue-50 text-govblue-900 hover:bg-govblue-100 rounded text-[11px] font-semibold">View Staff</button>
            <button onclick="openVacancyModal(${gp.lgd_code}, '${gp.gp_name}', ${gp.is_clear_vacancy})" class="px-2 py-1 bg-slate-100 text-slate-700 hover:bg-slate-200 rounded text-[11px]">Vacancy</button>
          </td>
        </tr>
      `;
    });
    tbody.innerHTML = rowsHtml;
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="10" class="text-center py-6 text-red-500">Failed to load Gram Panchayats: ${e.detail || e.message}</td></tr>`;
  }
}

async function viewGPDetails(lgdCode) {
  try {
    const res = await fetchAPI(`/panchayats/${lgdCode}`);
    const gp = res.gp;
    const salaryStaff = res.salary_claiming_employees || [];
    const workingStaff = res.actually_working_employees || [];

    let salaryRows = "";
    if (salaryStaff.length === 0) {
      salaryRows = `<tr><td colspan="5" class="py-3 text-center text-slate-400">No employees drawing salary from this GP.</td></tr>`;
    } else {
      salaryStaff.forEach(s => {
        salaryRows += `
          <tr>
            <td class="py-2 font-mono font-bold text-slate-900">${s.employee_id}</td>
            <td class="py-2 font-medium">${s.name_ifmis}</td>
            <td class="py-2">${s.actual_working_gp_name} (${s.actual_working_mandal})</td>
            <td class="py-2"><span class="px-2 py-0.5 rounded text-[10px] font-bold ${s.service_status === 'WORKING' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}">${s.service_status}</span></td>
            <td class="py-2"><span class="px-1.5 py-0.5 rounded text-[10px] ${s.verification_status === 'VERIFIED_BOTH' ? 'bg-green-100 text-green-800' : 'bg-slate-100'}">${s.verification_status}</span></td>
          </tr>
        `;
      });
    }

    let workingRows = "";
    if (workingStaff.length === 0) {
      workingRows = `<tr><td colspan="5" class="py-3 text-center text-slate-400">No employees actually working in this GP.</td></tr>`;
    } else {
      workingStaff.forEach(w => {
        workingRows += `
          <tr>
            <td class="py-2 font-mono font-bold text-slate-900">${w.employee_id}</td>
            <td class="py-2 font-medium">${w.name_ifmis}</td>
            <td class="py-2">${w.salary_gp_name} (${w.salary_mandal_name})</td>
            <td class="py-2"><span class="px-2 py-0.5 rounded text-[10px] font-bold ${w.service_status === 'WORKING' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}">${w.service_status}</span></td>
            <td class="py-2"><span class="px-1.5 py-0.5 rounded text-[10px] ${w.verification_status === 'VERIFIED_BOTH' ? 'bg-green-100 text-green-800' : 'bg-slate-100'}">${w.verification_status}</span></td>
          </tr>
        `;
      });
    }

    const bodyHtml = `
      <div class="mb-5 bg-slate-50 p-4 rounded-lg border border-slate-200 flex justify-between items-center">
        <div>
          <div class="text-xs text-slate-500 font-bold uppercase">Gram Panchayat</div>
          <div class="text-lg font-bold text-slate-900">${gp.gp_name} (LGD: ${gp.lgd_code})</div>
          <div class="text-xs text-slate-600">Mandal: <strong>${gp.mandal_name}</strong> | District: <strong>Khammam</strong></div>
        </div>
        <div class="text-right">
          <div class="text-xs text-slate-500 font-bold uppercase">Clear Vacancy?</div>
          <div class="text-sm font-bold ${gp.is_clear_vacancy ? 'text-rose-600' : 'text-emerald-600'}">${gp.is_clear_vacancy ? 'YES (CLEAR VACANCY)' : 'NO (ATTACHED)'}</div>
          ${gp.vacancy_remarks ? `<div class="text-[11px] text-slate-500 italic max-w-xs">${gp.vacancy_remarks}</div>` : ''}
        </div>
      </div>

      <div class="mb-6">
        <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2 flex items-center">
          <i data-lucide="wallet" class="w-4 h-4 mr-1.5 text-teal-600"></i> Employees Drawing Salary from this GP (${salaryStaff.length})
        </h4>
        <table class="w-full text-xs text-left">
          <thead class="border-b text-slate-500">
            <tr>
              <th class="py-1.5">Emp ID</th>
              <th class="py-1.5">Employee Name</th>
              <th class="py-1.5">Actual Working At</th>
              <th class="py-1.5">Service Status</th>
              <th class="py-1.5">Verification</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">${salaryRows}</tbody>
        </table>
      </div>

      <div>
        <h4 class="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2 flex items-center">
          <i data-lucide="briefcase" class="w-4 h-4 mr-1.5 text-govblue-800"></i> Employees Actually Working in this GP (${workingStaff.length})
        </h4>
        <table class="w-full text-xs text-left">
          <thead class="border-b text-slate-500">
            <tr>
              <th class="py-1.5">Emp ID</th>
              <th class="py-1.5">Employee Name</th>
              <th class="py-1.5">Salary Drawing GP</th>
              <th class="py-1.5">Service Status</th>
              <th class="py-1.5">Verification</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">${workingRows}</tbody>
        </table>
      </div>
    `;

    openModal(`Gram Panchayat Staff Position: ${gp.gp_name}`, bodyHtml);
  } catch (err) {
    alert("Failed to load GP details: " + (err.detail || err.message));
  }
}

function openVacancyModal(lgdCode, gpName, currentStatus) {
  const bodyHtml = `
    <form onsubmit="handleSaveVacancy(event, ${lgdCode})" class="space-y-4 text-xs">
      <div>
        <p class="text-slate-600 mb-2">Configure Clear Vacancy status for <strong>${gpName}</strong> (LGD: ${lgdCode}):</p>
      </div>

      <div>
        <label class="block font-bold text-slate-700 uppercase mb-1">Clear Vacancy Status</label>
        <select id="modal-vacancy-status" class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800 bg-white">
          <option value="false" ${!currentStatus ? 'selected' : ''}>NO - Attached / Regular Post</option>
          <option value="true" ${currentStatus ? 'selected' : ''}>YES - Clear Vacancy (No PS allocated)</option>
        </select>
      </div>

      <div>
        <label class="block font-bold text-slate-700 uppercase mb-1">Vacancy Remarks / Reason</label>
        <textarea id="modal-vacancy-remarks" rows="3" placeholder="Provide detailed official reasons (e.g. Retirement, transfer without substitute, pending notification)..." class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800"></textarea>
      </div>

      <div class="bg-amber-50 p-2.5 rounded border border-amber-200 text-amber-900 leading-tight">
        <strong>Important Rule (Section 6 & 10):</strong> A GP with an employee on suspension, absconding or leave must NOT automatically be classified as a clear vacancy.
      </div>

      <div class="flex justify-end space-x-2 pt-2">
        <button type="button" onclick="closeModal()" class="px-3 py-1.5 bg-slate-200 text-slate-800 rounded">Cancel</button>
        <button type="submit" class="px-4 py-1.5 bg-govblue-900 text-white font-semibold rounded shadow">Save Vacancy Status</button>
      </div>
    </form>
  `;
  openModal(`Manage Clear Vacancy: ${gpName}`, bodyHtml);
}

async function handleSaveVacancy(e, lgdCode) {
  e.preventDefault();
  const isVacancy = document.getElementById("modal-vacancy-status").value === "true";
  const remarks = document.getElementById("modal-vacancy-remarks").value;

  try {
    await fetchAPI(`/panchayats/${lgdCode}/vacancy`, {
      method: "POST",
      body: JSON.stringify({
        gp_lgd: lgdCode,
        is_clear_vacancy: isVacancy,
        vacancy_remarks: remarks
      })
    });
    closeModal();
    alert("Vacancy status updated successfully");
    loadGPMasterData();
  } catch (err) {
    alert("Failed to update vacancy: " + (err.detail || err.message));
  }
}

// ==========================================
// 2A. STAGE 1: EMPLOYEE MASTER REGISTRATION
// ==========================================
let stage1IdDebounce = null;
let cachedStage1Employees = [];

async function renderStage1EmployeeRegView() {
  const container = document.getElementById("view-stage1-employee-reg");
  if (!container) return;

  const isMandal = currentUser && currentUser.role === "MANDAL_ADMIN";
  const myMandalId = currentUser ? currentUser.mandal_id : null;
  const myMandalName = currentUser ? (currentUser.mandal_name || "Mandal") : "";

  let mandalOptions = "";
  if (isMandal) {
    mandalOptions = `<option value="${myMandalId}" selected>${myMandalName} (Authorized Mandal)</option>`;
  } else {
    mandalOptions = `<option value="">-- Select Registration Mandal --</option>`;
    cachedMandals.forEach(m => {
      mandalOptions += `<option value="${m.id}">${m.mandal_name} (LGD: ${m.mandal_lgd})</option>`;
    });
  }

  container.innerHTML = `
    <div class="max-w-6xl mx-auto space-y-6">
      
      <!-- Stage 1 Header with Architecture Progress Bar -->
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-5 border-t-4 border-amber-500">
        <div class="flex flex-wrap justify-between items-center gap-3">
          <div>
            <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-100 text-amber-900 border border-amber-300 mb-1">
              <i data-lucide="layers" class="w-3.5 h-3.5 mr-1"></i> STAGE 1 OF 2 • ARCHITECTURAL WORKFLOW
            </span>
            <h2 class="text-xl font-bold text-slate-900">Stage 1: Employee Master Registration</h2>
            <p class="text-xs text-slate-500">Register Panchayat Secretary employee records with global uniqueness validation across all 20 Mandals. No GP mapping required at this stage.</p>
          </div>
          <div class="flex items-center space-x-2">
            <button onclick="navigate('stage2-salary-mapping')" class="px-3 py-1.5 bg-teal-700 hover:bg-teal-800 text-white rounded text-xs font-semibold flex items-center shadow transition">
              <span>Go to Stage 2: Salary & Working Mapping</span>
              <i data-lucide="arrow-right" class="w-3.5 h-3.5 ml-1"></i>
            </button>
          </div>
        </div>

        <!-- Progress Steps -->
        <div class="mt-4 pt-4 border-t border-slate-200 grid grid-cols-2 gap-2 text-center text-xs">
          <div class="p-2.5 rounded-lg bg-amber-50 border border-amber-300 font-bold text-amber-900 flex items-center justify-center">
            <span class="w-5 h-5 rounded-full bg-amber-600 text-white flex items-center justify-center text-[10px] mr-2">1</span>
            Stage 1: Employee Registration (Active)
          </div>
          <div class="p-2.5 rounded-lg bg-slate-50 border border-slate-200 text-slate-500 flex items-center justify-center cursor-pointer hover:bg-slate-100" onclick="navigate('stage2-salary-mapping')">
            <span class="w-5 h-5 rounded-full bg-slate-300 text-slate-700 flex items-center justify-center text-[10px] mr-2">2</span>
            Stage 2: Salary GP & Working Station Mapping
          </div>
        </div>
      </div>

      <!-- Registration Form -->
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <h3 class="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4 flex items-center">
          <i data-lucide="user-plus" class="w-4 h-4 mr-2 text-amber-600"></i>
          Panchayat Secretary Employee Information
        </h3>

        <form id="stage1-reg-form" onsubmit="handleStage1RegisterSubmit(event)" class="space-y-4 text-xs text-slate-700">
          
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <!-- Employee ID with real-time validation -->
            <div>
              <label class="block font-bold text-slate-800 uppercase mb-1">
                Employee ID <span class="text-rose-600">*</span>
              </label>
              <div class="relative">
                <input type="text" id="stage1-emp-id" required placeholder="e.g. 1029384" oninput="handleStage1IdInput(event)" class="w-full p-2 border border-slate-300 rounded font-mono font-bold text-slate-900 focus:ring-1 focus:ring-govblue-800 outline-none uppercase">
                <span id="stage1-id-icon" class="absolute right-2.5 top-2.5 hidden"></span>
              </div>
              <div id="stage1-id-feedback" class="text-[11px] mt-1 font-medium hidden"></div>
            </div>

            <!-- Employee Name -->
            <div>
              <label class="block font-bold text-slate-800 uppercase mb-1">
                Employee Name (As per Service Record) <span class="text-rose-600">*</span>
              </label>
              <input type="text" id="stage1-emp-name" required placeholder="Full Name as per official records" class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800 outline-none">
            </div>

            <!-- Mobile Number -->
            <div>
              <label class="block font-bold text-slate-800 uppercase mb-1">
                Mobile Number
              </label>
              <input type="tel" id="stage1-mobile" maxlength="10" oninput="this.value = this.value.replace(/[^0-9]/g, '').slice(0, 10)" placeholder="10-digit mobile number" class="w-full p-2 border border-slate-300 rounded font-mono focus:ring-1 focus:ring-govblue-800 outline-none">
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <!-- Designation -->
            <div>
              <label class="block font-bold text-slate-800 uppercase mb-1">
                Designation <span class="text-rose-600">*</span>
              </label>
              <select id="stage1-designation" required class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800 bg-white outline-none">
                <option value="Panchayat Secretary Grade-IV" selected>Panchayat Secretary Grade-IV</option>
                <option value="Panchayat Secretary Grade-III">Panchayat Secretary Grade-III</option>
                <option value="Panchayat Secretary Grade-II">Panchayat Secretary Grade-II</option>
                <option value="Panchayat Secretary Grade-I">Panchayat Secretary Grade-I</option>
                <option value="Junior Panchayat Secretary (JPS)">Junior Panchayat Secretary (JPS)</option>
                <option value="OPS (Out Sourcing Panchayat Secretary)">OPS (Out Sourcing Panchayat Secretary)</option>
                <option value="Temporary / Incharge Panchayat Secretary">Temporary / Incharge Panchayat Secretary</option>
              </select>
            </div>

            <!-- Date of Birth -->
            <div>
              <label class="block font-bold text-slate-800 uppercase mb-1">
                Date of Birth (Optional)
              </label>
              <input type="date" id="stage1-dob" class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800 outline-none bg-white">
            </div>

            <!-- Registration Mandal -->
            <div>
              <label class="block font-bold text-slate-800 uppercase mb-1">
                Registration Mandal <span class="text-rose-600">*</span>
              </label>
              <select id="stage1-mandal" required ${isMandal ? 'disabled' : ''} class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800 bg-white outline-none">
                ${mandalOptions}
              </select>
            </div>
          </div>

          <!-- Submit Buttons -->
          <div class="pt-3 border-t border-slate-200 flex justify-end space-x-3">
            <button type="reset" class="px-4 py-2 border border-slate-300 rounded text-slate-600 hover:bg-slate-50 font-semibold">
              Clear Form
            </button>
            <button type="submit" id="stage1-submit-btn" class="px-5 py-2 bg-govblue-900 hover:bg-govblue-800 text-white font-bold rounded shadow transition flex items-center">
              <i data-lucide="check" class="w-4 h-4 mr-1.5"></i> Register Employee (Stage 1)
            </button>
          </div>

        </form>
      </div>

      <!-- Live Table of Stage 1 Employees -->
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="p-4 bg-slate-50 border-b border-slate-200 flex flex-wrap justify-between items-center gap-3">
          <div>
            <h3 class="font-bold text-slate-800 text-sm">Registered Panchayat Secretaries</h3>
            <p class="text-[11px] text-slate-500">Live list of registered employees and their Salary GP & Working Station completion status.</p>
          </div>
          <div class="flex items-center space-x-2">
            <button onclick="loadStage1EmployeesList()" class="px-3 py-1 bg-white border border-slate-300 rounded text-xs font-semibold hover:bg-slate-100 flex items-center">
              <i data-lucide="refresh-cw" class="w-3.5 h-3.5 mr-1 text-slate-600"></i> Refresh
            </button>
          </div>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs text-slate-700">
            <thead class="bg-slate-100 border-b border-slate-200 text-[11px] font-bold text-slate-600 uppercase tracking-wider">
              <tr>
                <th class="px-3.5 py-3">#</th>
                <th class="px-3.5 py-3">Employee ID</th>
                <th class="px-3.5 py-3">Employee Name</th>
                <th class="px-3.5 py-3">Mobile No</th>
                <th class="px-3.5 py-3">Designation</th>
                <th class="px-3.5 py-3">Reg. Mandal</th>
                <th class="px-3.5 py-3 text-center">Salary GP</th>
                <th class="px-3.5 py-3 text-center">Working Station</th>
                <th class="px-3.5 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody id="stage1-tbody" class="divide-y divide-slate-100">
              <tr><td colspan="9" class="text-center py-8 text-slate-400">Loading registered employees...</td></tr>
            </tbody>
          </table>
        </div>
      </div>

    </div>
  `;
  lucide.createIcons();
  loadStage1EmployeesList();
}

function handleStage1IdInput(e) {
  const empId = e.target.value.trim();
  const feedback = document.getElementById("stage1-id-feedback");
  const icon = document.getElementById("stage1-id-icon");
  const submitBtn = document.getElementById("stage1-submit-btn");

  if (!feedback || !icon) return;
  clearTimeout(stage1IdDebounce);

  if (!empId) {
    feedback.className = "text-[11px] mt-1 font-medium hidden";
    icon.className = "absolute right-2.5 top-2.5 hidden";
    if (submitBtn) submitBtn.disabled = false;
    return;
  }

  stage1IdDebounce = setTimeout(async () => {
    try {
      const res = await fetchAPI(`/employees/check-id?employee_id=${encodeURIComponent(empId)}`);
      if (res.exists) {
        icon.className = "absolute right-2.5 top-2.5 block text-rose-600";
        icon.innerHTML = `<i data-lucide="alert-circle" class="w-4 h-4"></i>`;
        feedback.className = "text-[11px] mt-1 font-medium text-rose-700 bg-rose-50 p-2 rounded border border-rose-200 block";
        feedback.innerHTML = `<strong>DUPLICATE DETECTED:</strong> Employee ID <strong>${empId}</strong> is already registered under <strong>${res.employee.name}</strong> (${res.employee.mandal || 'Khammam'}). Duplicate employee creation is blocked.`;
        if (submitBtn) submitBtn.disabled = true;
      } else {
        icon.className = "absolute right-2.5 top-2.5 block text-emerald-600";
        icon.innerHTML = `<i data-lucide="check-circle" class="w-4 h-4"></i>`;
        feedback.className = "text-[11px] mt-1 font-medium text-emerald-700 bg-emerald-50 p-1.5 rounded border border-emerald-200 block";
        feedback.innerHTML = `✓ Employee ID <strong>${empId}</strong> is available and unique across Khammam District.`;
        if (submitBtn) submitBtn.disabled = false;
      }
      lucide.createIcons();
    } catch (err) {
      console.error("ID check error", err);
    }
  }, 350);
}

async function handleStage1RegisterSubmit(e) {
  e.preventDefault();
  const submitBtn = document.getElementById("stage1-submit-btn");
  submitBtn.disabled = true;
  submitBtn.innerHTML = `<i data-lucide="loader" class="w-4 h-4 mr-1.5 animate-spin"></i> Registering...`;
  lucide.createIcons();

  const isMandal = currentUser && currentUser.role === "MANDAL_ADMIN";
  const mandalId = isMandal ? currentUser.mandal_id : (parseInt(document.getElementById("stage1-mandal").value) || null);

  const payload = {
    employee_id: document.getElementById("stage1-emp-id").value.trim().toUpperCase(),
    name_ifmis: document.getElementById("stage1-emp-name").value.trim(),
    mobile_number: document.getElementById("stage1-mobile").value.trim() || null,
    designation: document.getElementById("stage1-designation").value,
    dob: document.getElementById("stage1-dob").value.trim() || null,
    registration_mandal_id: mandalId
  };

  try {
    const res = await fetchAPI("/employees/stage1-register", {
      method: "POST",
      body: JSON.stringify(payload)
    });

    alert(`Stage 1 Registration Successful!\nEmployee ID: ${res.employee_id}\nName: ${res.name_ifmis}\nYou can now proceed to Stage 2: Salary GP & Working Station Mapping.`);
    document.getElementById("stage1-reg-form").reset();
    document.getElementById("stage1-id-feedback").classList.add("hidden");
    document.getElementById("stage1-id-icon").classList.add("hidden");
    loadStage1EmployeesList();

    // Offer instant jump to Stage 2 Combined Mapping
    if (confirm(`Do you want to map Salary GP & Working Station for ${res.name_ifmis} (${res.employee_id}) right now?`)) {
      proceedToStage2(res.employee_id);
    }

  } catch (err) {
    alert("Registration Failed: " + (err.detail || JSON.stringify(err)));
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<i data-lucide="check" class="w-4 h-4 mr-1.5"></i> Register Employee (Stage 1)`;
    lucide.createIcons();
  }
}

async function loadStage1EmployeesList() {
  const tbody = document.getElementById("stage1-tbody");
  if (!tbody) return;

  try {
    const list = await fetchAPI("/employees/stage1-list");
    cachedStage1Employees = list || [];

    if (cachedStage1Employees.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" class="text-center py-8 text-slate-400">No Panchayat Secretaries registered yet. Fill the form above to add an employee.</td></tr>`;
      return;
    }

    let rowsHtml = "";
    cachedStage1Employees.forEach((emp, idx) => {
      const s2Badge = emp.salary_mapped
        ? `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-teal-100 text-teal-800">Mapped: ${emp.salary_gp_name || ''}</span>`
        : `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800">Pending</span>`;

      const s3Badge = emp.working_mapped
        ? `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-100 text-indigo-800">Confirmed: ${emp.working_gp_name || ''}</span>`
        : `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-600">Pending</span>`;

      rowsHtml += `
        <tr class="hover:bg-slate-50">
          <td class="px-3.5 py-2.5 font-mono text-[11px] text-slate-400">${idx + 1}</td>
          <td class="px-3.5 py-2.5 font-mono font-bold text-slate-900">${emp.employee_id}</td>
          <td class="px-3.5 py-2.5 font-semibold text-slate-800">${emp.name_ifmis}</td>
          <td class="px-3.5 py-2.5 font-mono text-slate-600">${emp.mobile_number || 'N/A'}</td>
          <td class="px-3.5 py-2.5 text-slate-600">${emp.designation || 'PS'}</td>
          <td class="px-3.5 py-2.5 text-slate-600">${emp.registration_mandal_name || 'N/A'}</td>
          <td class="px-3.5 py-2.5 text-center">${s2Badge}</td>
          <td class="px-3.5 py-2.5 text-center">${s3Badge}</td>
          <td class="px-3.5 py-2.5 text-right space-x-1">
            <button onclick="proceedToStage2('${emp.employee_id}')" class="px-2.5 py-1 bg-teal-700 hover:bg-teal-800 text-white rounded text-[11px] font-semibold transition" title="Map Salary GP & Working Station">
              Map Salary & Station →
            </button>
          </td>
        </tr>
      `;
    });
    tbody.innerHTML = rowsHtml;

  } catch (err) {
    console.error("Failed loading stage 1 employees", err);
    tbody.innerHTML = `<tr><td colspan="9" class="text-center py-6 text-red-500">Error loading registered employees.</td></tr>`;
  }
}

let pendingStage2EmpId = null;

function proceedToStage2(empId) {
  pendingStage2EmpId = empId;
  navigate("stage2-salary-mapping");
}

// ==========================================
// 2B. STAGE 2 (COMBINED): SALARY GP, STATUS & WORKING STATION MAPPING
// ==========================================
async function renderStage2SalaryMappingView(preselectedEmpId = null) {
  const container = document.getElementById("view-stage2-salary-mapping");
  if (!container) return;

  const targetEmpId = preselectedEmpId || pendingStage2EmpId;
  pendingStage2EmpId = null;

  let employees = [];
  let mandalGps = [];
  try {
    const [empRes, gpRes] = await Promise.all([
      fetchAPI("/employees/dropdown-list"),
      fetchAPI("/panchayats?for_salary_entry=true")
    ]);
    employees = empRes || [];
    mandalGps = gpRes || [];
  } catch (err) {
    console.error("Error loading stage 2 options", err);
  }

  let empOptions = `<option value="">-- Select Registered Panchayat Secretary --</option>`;
  employees.forEach(e => {
    const empId = e.employee_id || e.id;
    const empName = e.name_ifmis || e.name || '';
    const empMobile = e.mobile_number || e.mobile || '';
    const isSel = (targetEmpId && empId === targetEmpId) ? "selected" : "";
    empOptions += `<option value="${empId}" data-name="${empName}" data-mobile="${empMobile}" ${isSel}>${e.display_label || (empName + ' - ' + empId)}</option>`;
  });

  let gpOptions = `<option value="">-- Select Authorized Salary GP --</option>`;
  mandalGps.forEach(g => {
    gpOptions += `<option value="${g.lgd_code}" data-name="${g.gp_name}" data-mandal="${g.mandal_name}" data-mandal-id="${g.mandal_id}">${g.gp_name} (LGD: ${g.lgd_code})</option>`;
  });

  let otherMandalOptions = `<option value="">-- Select Destination Mandal --</option>`;
  cachedMandals.forEach(m => {
    otherMandalOptions += `<option value="${m.id}">${m.mandal_name} (LGD: ${m.mandal_lgd})</option>`;
  });

  container.innerHTML = `
    <div class="max-w-4xl mx-auto space-y-6">
      
      <!-- Stage 2 Header with Progress -->
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-5 border-t-4 border-teal-600">
        <div class="flex flex-wrap justify-between items-center gap-3">
          <div>
            <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-teal-100 text-teal-900 border border-teal-300 mb-1">
              <i data-lucide="layers" class="w-3.5 h-3.5 mr-1"></i> STAGE 2 OF 2 • COMBINED MAPPING WORKFLOW
            </span>
            <h2 class="text-xl font-bold text-slate-900">Stage 2: Salary GP, Status & Working Station Mapping</h2>
            <p class="text-xs text-slate-500">Map salary-claiming Gram Panchayat, service status, and working station / deputation details in one unified step.</p>
          </div>
          <div class="flex items-center space-x-2">
            <button onclick="navigate('stage1-employee-reg')" class="px-3 py-1.5 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded text-xs font-semibold flex items-center transition">
              <i data-lucide="arrow-left" class="w-3.5 h-3.5 mr-1"></i> Back to Stage 1
            </button>
            <button onclick="navigate('reconciliation-report')" class="px-3 py-1.5 bg-govblue-900 hover:bg-govblue-800 text-white rounded text-xs font-semibold flex items-center shadow transition">
              <span>View 22-Col Master Report</span>
              <i data-lucide="arrow-right" class="w-3.5 h-3.5 ml-1"></i>
            </button>
          </div>
        </div>

        <!-- Progress Steps -->
        <div class="mt-4 pt-4 border-t border-slate-200 grid grid-cols-2 gap-2 text-center text-xs">
          <div class="p-2.5 rounded-lg bg-emerald-50 border border-emerald-300 text-emerald-900 font-semibold flex items-center justify-center cursor-pointer" onclick="navigate('stage1-employee-reg')">
            <span class="w-5 h-5 rounded-full bg-emerald-600 text-white flex items-center justify-center text-[10px] mr-2">✓</span>
            Stage 1: Employee Registration (Done)
          </div>
          <div class="p-2.5 rounded-lg bg-teal-50 border border-teal-400 font-bold text-teal-900 flex items-center justify-center">
            <span class="w-5 h-5 rounded-full bg-teal-700 text-white flex items-center justify-center text-[10px] mr-2">2</span>
            Stage 2: Salary & Working Mapping (Active)
          </div>
        </div>
      </div>

      <!-- Quick Option: Mark GP as Clear Vacant -->
      <div class="bg-amber-50 rounded-xl border border-amber-200 p-4 flex flex-wrap justify-between items-center gap-3">
        <div class="flex items-center space-x-3">
          <div class="p-2 bg-amber-200 text-amber-900 rounded-lg">
            <i data-lucide="shield-alert" class="w-5 h-5"></i>
          </div>
          <div>
            <h4 class="font-bold text-amber-950 text-xs">Is a Gram Panchayat Clear Vacant with No Salary Claimant?</h4>
            <p class="text-[11px] text-amber-800">If no employee is drawing salary from a GP, directly record it in the Clear Vacancy Register.</p>
          </div>
        </div>
        <button onclick="navigate('clear-vacancy-register')" class="px-3.5 py-1.5 bg-amber-800 hover:bg-amber-900 text-white rounded text-xs font-bold shadow flex items-center">
          <i data-lucide="file-text" class="w-3.5 h-3.5 mr-1.5"></i> Open Clear Vacancy Register
        </button>
      </div>

      <!-- Mapping Form -->
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <form id="stage2-form" onsubmit="handleStage2SalarySubmit(event)" class="space-y-5 text-xs text-slate-700">
          
          <!-- Employee Selector -->
          <div class="p-4 bg-slate-50 rounded-lg border border-slate-200">
            <label class="block font-bold text-slate-800 uppercase mb-1">
              Select Registered Panchayat Secretary <span class="text-rose-600">*</span>
            </label>
            <select id="stage2-emp-select" required onchange="handleStage2EmpSelect(event)" class="w-full p-2.5 border border-slate-300 rounded focus:ring-1 focus:ring-teal-700 font-semibold text-slate-800 bg-white outline-none">
              ${empOptions}
            </select>

            <!-- Auto-populated Info Card -->
            <div id="stage2-emp-card" class="hidden mt-3 p-3 bg-white rounded border border-slate-200 grid grid-cols-2 md:grid-cols-4 gap-2">
              <div>
                <span class="text-[10px] text-slate-400 uppercase font-bold block">Employee Name</span>
                <span id="stage2-card-name" class="font-bold text-slate-800">-</span>
              </div>
              <div>
                <span class="text-[10px] text-slate-400 uppercase font-bold block">Mobile Number</span>
                <span id="stage2-card-mobile" class="font-mono text-slate-700">-</span>
              </div>
              <div>
                <span class="text-[10px] text-slate-400 uppercase font-bold block">Employee ID</span>
                <span id="stage2-card-id" class="font-mono font-bold text-govblue-900">-</span>
              </div>
              <div>
                <span class="text-[10px] text-slate-400 uppercase font-bold block">Status</span>
                <span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800">Stage 1 Verified</span>
              </div>
            </div>
          </div>

          <!-- Salary Claiming GP -->
          <div class="p-4 bg-slate-50 rounded-lg border border-slate-200">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div class="md:col-span-2">
                <label class="block font-bold text-slate-800 uppercase mb-1">
                  Salary-Claiming Gram Panchayat (Preloaded Master) <span class="text-rose-600">*</span>
                </label>
                <select id="stage2-salary-gp" required onchange="handleStage2SalaryGPChange(event)" class="w-full p-2.5 border border-slate-300 rounded focus:ring-1 focus:ring-teal-700 bg-white outline-none">
                  ${gpOptions}
                </select>
                <p class="text-[10px] text-slate-500 mt-1">GPs are strictly filtered to your authorized Mandal.</p>
              </div>
              <div class="bg-white p-3 rounded border border-slate-200">
                <div class="text-[10px] text-slate-400 uppercase font-bold">Auto-Identified Mandal</div>
                <div id="stage2-mandal-display" class="font-bold text-teal-800 text-xs truncate">Select GP above</div>
                <div id="stage2-lgd-display" class="text-[10px] text-slate-500 font-mono mt-0.5">LGD Code: -</div>
              </div>
            </div>
          </div>

          <!-- Salary Claiming Status & Working From Date -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="block font-bold text-slate-800 uppercase mb-1">
                Salary Claiming Status <span class="text-rose-600">*</span>
              </label>
              <select id="stage2-salary-status" required class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-teal-700 bg-white outline-none">
                <option value="YES" selected>YES (Salary Claimed from this GP)</option>
                <option value="NO">NO (Salary Not Claimed here)</option>
              </select>
            </div>
            <div>
              <label class="block font-bold text-slate-800 uppercase mb-1">
                Date Of Joining
              </label>
              <input type="date" id="stage2-effective-date" class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-teal-700 bg-white outline-none">
            </div>
          </div>

          <!-- Service & Working Status -->
          <div class="p-4 bg-slate-50 rounded-lg border border-slate-200 space-y-3">
            <div>
              <label class="block font-bold text-slate-800 uppercase mb-1">
                Employee Service & Working Status <span class="text-rose-600">*</span>
              </label>
              <select id="stage2-service-status" required onchange="handleStage2ServiceStatusChange(event)" class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-teal-700 bg-white outline-none font-semibold text-slate-800">
                <option value="WORKING" selected>Working</option>
                <option value="SUSPENDED">Suspended</option>
                <option value="ABSCONDING">Absconding</option>
                <option value="LONG_LEAVE">Long Leave</option>
                <option value="MEDICAL_LEAVE">Medical Leave</option>
                <option value="MATERNITY_LEAVE">Maternity Leave</option>
                <option value="CHILD_CARE_LEAVE">Child Care Leave (CCL)</option>
                <option value="EARNED_LEAVE">Earned Leave</option>
                <option value="EXTRAORDINARY_LEAVE">Extraordinary Leave / Leave Without Pay (EOL)</option>
                <option value="OTHER_APPROVED_LEAVE">Other Approved Leave</option>
              </select>
            </div>

            <!-- Conditional Fields for Non-Working Statuses -->
            <div id="stage2-status-details" class="hidden p-3 bg-white rounded border border-slate-200 grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label id="stage2-order-label" class="block font-bold text-slate-700 uppercase mb-1 text-[10px]">Proceedings / Order Number</label>
                <input type="text" id="stage2-order-no" placeholder="Order / Proceedings No..." class="w-full p-1.5 border border-slate-300 rounded outline-none">
              </div>
              <div>
                <label id="stage2-date-label" class="block font-bold text-slate-700 uppercase mb-1 text-[10px]">Date from which Proceeded on Leave / Suspended / Absconding <span class="text-rose-600">*</span></label>
                <input type="date" id="stage2-order-date" class="w-full p-1.5 border border-slate-300 rounded outline-none bg-white">
              </div>
            </div>

            <div>
              <label class="block font-bold text-slate-700 uppercase mb-1 text-[10px]">Salary / Status Remarks</label>
              <input type="text" id="stage2-remarks" placeholder="Optional remarks regarding salary claiming mapping..." class="w-full p-1.5 border border-slate-300 rounded outline-none">
            </div>
          </div>

          <!-- PART B: WORKING STATION & DEPUTATION MAPPING -->
          <div class="p-4 bg-indigo-50/40 rounded-lg border border-indigo-200 space-y-4">
            <div class="flex items-center justify-between border-b border-indigo-200 pb-2">
              <h4 class="font-bold text-indigo-950 text-xs uppercase tracking-wider flex items-center">
                <i data-lucide="map-pin" class="w-4 h-4 mr-1.5 text-indigo-700"></i>
                Present Working Station & Deputation Details
              </h4>
              <span class="text-[10px] font-semibold text-indigo-700">Combined into Stage 2</span>
            </div>

            <div>
              <label class="block font-bold text-slate-800 uppercase mb-2 text-xs">
                Is Employee Presently Working in their Salary-Claiming GP? <span class="text-rose-600">*</span>
              </label>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <label class="flex items-center p-3 bg-white rounded border border-slate-200 cursor-pointer hover:border-indigo-400 transition">
                  <input type="radio" name="stage2-working-same" value="YES" checked onchange="handleStage2WorkingSameChange(event)" class="w-4 h-4 text-indigo-600">
                  <div class="ml-2.5">
                    <div class="font-bold text-slate-800">YES — Working in Salary GP</div>
                    <div class="text-[11px] text-slate-500">Regular active duty in their own salary-claiming Gram Panchayat.</div>
                  </div>
                </label>
                <label class="flex items-center p-3 bg-white rounded border border-slate-200 cursor-pointer hover:border-indigo-400 transition">
                  <input type="radio" name="stage2-working-same" value="NO" onchange="handleStage2WorkingSameChange(event)" class="w-4 h-4 text-indigo-600">
                  <div class="ml-2.5">
                    <div class="font-bold text-slate-800">NO — Deputed Elsewhere</div>
                    <div class="text-[11px] text-slate-500">Working in another GP, other Mandal, District, or Department.</div>
                  </div>
                </label>
              </div>
            </div>

            <!-- Deputation Details Section (Shown when Working Same == NO) -->
            <div id="stage2-deputation-panel" class="hidden p-4 bg-amber-50/70 rounded-lg border border-amber-300 space-y-4">
              <h4 class="font-bold text-amber-950 text-xs uppercase tracking-wider flex items-center">
                <i data-lucide="git-branch" class="w-4 h-4 mr-1.5 text-amber-700"></i>
                Official Deputation Assignment & Proceedings Details
              </h4>

              <div>
                <label class="block font-bold text-slate-800 uppercase mb-1">
                  Deputation Location Type <span class="text-rose-600">*</span>
                </label>
                <select id="stage2-posting-type" onchange="handleStage2PostingTypeChange(event)" class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-indigo-700 bg-white outline-none font-semibold text-slate-800">
                  <option value="WITHIN_MANDAL">Deputation Within Same Mandal</option>
                  <option value="ANOTHER_MANDAL">Deputation to Another Mandal in Khammam</option>
                  <option value="OTHER_DISTRICT">Deputation to Other District</option>
                  <option value="OTHER_DEPARTMENT">Deputation to Other Department</option>
                </select>
              </div>

              <!-- Destination: Within Same Mandal -->
              <div id="stage2-dest-same-mandal" class="space-y-1">
                <label class="block font-bold text-slate-800 uppercase mb-1">
                  Destination Gram Panchayat (Same Mandal) <span class="text-rose-600">*</span>
                </label>
                <select id="stage2-same-mandal-gp" class="w-full p-2 border border-slate-300 rounded bg-white outline-none">
                  <option value="">-- Select Salary GP First to Load Mandal GPs --</option>
                </select>
              </div>

              <!-- Destination: Another Mandal -->
              <div id="stage2-dest-another-mandal" class="hidden grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label class="block font-bold text-slate-800 uppercase mb-1">
                    Destination Mandal <span class="text-rose-600">*</span>
                  </label>
                  <select id="stage2-another-mandal-select" onchange="handleStage2DestMandalChange(event)" class="w-full p-2 border border-slate-300 rounded bg-white outline-none">
                    ${otherMandalOptions}
                  </select>
                </div>
                <div>
                  <label class="block font-bold text-slate-800 uppercase mb-1">
                    Destination Gram Panchayat <span class="text-rose-600">*</span>
                  </label>
                  <select id="stage2-another-mandal-gp" class="w-full p-2 border border-slate-300 rounded bg-white outline-none">
                    <option value="">-- Select Mandal First --</option>
                  </select>
                </div>
              </div>

              <!-- Destination: Other District -->
              <div id="stage2-dest-other-dist" class="hidden grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label class="block font-bold text-slate-800 uppercase mb-1">
                    External District Name <span class="text-rose-600">*</span>
                  </label>
                  <input type="text" id="stage2-other-dist-name" placeholder="e.g. Bhadradri Kothagudem, Warangal..." class="w-full p-2 border border-slate-300 rounded outline-none">
                </div>
                <div>
                  <label class="block font-bold text-slate-800 uppercase mb-1">
                    Destination Office / Gram Panchayat
                  </label>
                  <input type="text" id="stage2-other-dist-office" placeholder="Office / Gram Panchayat Name..." class="w-full p-2 border border-slate-300 rounded outline-none">
                </div>
              </div>

              <!-- Destination: Other Department -->
              <div id="stage2-dest-other-dept" class="hidden grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label class="block font-bold text-slate-800 uppercase mb-1">
                    Department Name <span class="text-rose-600">*</span>
                  </label>
                  <input type="text" id="stage2-other-dept-name" placeholder="e.g. Collectorate, DRDO, Zilla Praja Parishad..." class="w-full p-2 border border-slate-300 rounded outline-none">
                </div>
                <div>
                  <label class="block font-bold text-slate-800 uppercase mb-1">
                    Designation / Assigned Office
                  </label>
                  <input type="text" id="stage2-other-dept-office" placeholder="Office Name / Position..." class="w-full p-2 border border-slate-300 rounded outline-none">
                </div>
              </div>

              <!-- Order / Proceedings Information -->
              <div class="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2 border-t border-amber-200">
                <div>
                  <label class="block font-bold text-slate-800 uppercase mb-1">Deputation Order Number</label>
                  <input type="text" id="stage2-dep-order-no" placeholder="Proceedings Order No..." class="w-full p-1.5 border border-slate-300 rounded outline-none">
                </div>
                <div>
                  <label class="block font-bold text-slate-800 uppercase mb-1">Deputation Order Date</label>
                  <input type="date" id="stage2-dep-order-date" class="w-full p-1.5 border border-slate-300 rounded outline-none bg-white">
                </div>
                <div>
                  <label class="block font-bold text-slate-800 uppercase mb-1">Deputation Effective From</label>
                  <input type="date" id="stage2-dep-effective-date" class="w-full p-1.5 border border-slate-300 rounded outline-none bg-white">
                </div>
              </div>

              <div>
                <label class="block font-bold text-slate-700 uppercase mb-1">Deputation Remarks</label>
                <input type="text" id="stage2-dep-remarks" placeholder="Provide any additional order notes or remarks..." class="w-full p-1.5 border border-slate-300 rounded outline-none">
              </div>
            </div>
          </div>

          <!-- Submit Buttons -->
          <div class="pt-3 border-t border-slate-200 flex justify-end space-x-3">
            <button type="submit" id="stage2-submit-btn" class="px-5 py-2.5 bg-teal-800 hover:bg-teal-900 text-white font-bold rounded shadow transition flex items-center">
              <i data-lucide="check" class="w-4 h-4 mr-1.5"></i> Save Salary & Working Mapping (Stage 2)
            </button>
          </div>

        </form>
      </div>

    </div>
  `;
  lucide.createIcons();

  // Populate Same Mandal GPs immediately for default Mandal if logged in as Mandal Admin
  if (currentUser && currentUser.mandal_id) {
    populateStage2SameMandalGPs(currentUser.mandal_id, currentUser.mandal_name || "Mandal");
  }

  if (targetEmpId) {
    const sel = document.getElementById("stage2-emp-select");
    if (sel) {
      sel.value = targetEmpId;
      handleStage2EmpSelect({ target: sel });
    }
  }
}

function populateStage2SameMandalGPs(mandalId, mandalName = "") {
  const gpSelect = document.getElementById("stage2-same-mandal-gp");
  if (!gpSelect || !mandalId) return;
  const mandalGps = centralizedPanchayats.filter(gp => gp.mandal_id === parseInt(mandalId));
  let sameOptions = `<option value="">-- Select Destination GP in ${mandalName || 'Mandal'} --</option>`;
  mandalGps.forEach(g => {
    sameOptions += `<option value="${g.lgd_code}">${g.gp_name} (LGD: ${g.lgd_code})</option>`;
  });
  gpSelect.innerHTML = sameOptions;
}

function resetStage2MappingFields() {
  const salGpSel = document.getElementById("stage2-salary-gp");
  if (salGpSel) {
    salGpSel.value = "";
    handleStage2SalaryGPChange({ target: salGpSel });
  }
  const salStatus = document.getElementById("stage2-salary-status");
  if (salStatus) salStatus.value = "YES";
  const effDate = document.getElementById("stage2-effective-date");
  if (effDate) effDate.value = "";

  const statusSel = document.getElementById("stage2-service-status");
  if (statusSel) {
    statusSel.value = "WORKING";
    handleStage2ServiceStatusChange({ target: statusSel });
  }
  const orderNo = document.getElementById("stage2-order-no");
  if (orderNo) orderNo.value = "";
  const orderDate = document.getElementById("stage2-order-date");
  if (orderDate) orderDate.value = "";
  const remarks = document.getElementById("stage2-remarks");
  if (remarks) remarks.value = "";

  const yesRadio = document.querySelector('input[name="stage2-working-same"][value="YES"]');
  if (yesRadio) {
    yesRadio.checked = true;
    handleStage2WorkingSameChange({ target: yesRadio });
  }
  const pTypeSel = document.getElementById("stage2-posting-type");
  if (pTypeSel) {
    pTypeSel.value = "WITHIN_MANDAL";
    handleStage2PostingTypeChange({ target: pTypeSel });
  }
  const sameMandalGp = document.getElementById("stage2-same-mandal-gp");
  if (sameMandalGp) sameMandalGp.value = "";
  const anotherMandalSel = document.getElementById("stage2-another-mandal-select");
  if (anotherMandalSel) anotherMandalSel.value = "";
  const anotherMandalGp = document.getElementById("stage2-another-mandal-gp");
  if (anotherMandalGp) anotherMandalGp.innerHTML = `<option value="">-- Select Mandal First --</option>`;

  ["stage2-other-dist-name", "stage2-other-dist-office", "stage2-other-dept-name", "stage2-other-dept-office", "stage2-dep-order-no", "stage2-dep-order-date", "stage2-dep-effective-date", "stage2-dep-remarks"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = "";
  });
}

async function handleStage2EmpSelect(e) {
  const sel = e.target;
  const opt = sel.options[sel.selectedIndex];
  const card = document.getElementById("stage2-emp-card");
  resetStage2MappingFields();

  if (!sel.value || !opt) {
    if (card) card.classList.add("hidden");
    return;
  }
  document.getElementById("stage2-card-name").textContent = opt.getAttribute("data-name") || "-";
  document.getElementById("stage2-card-mobile").textContent = opt.getAttribute("data-mobile") || "N/A";
  document.getElementById("stage2-card-id").textContent = sel.value;
  card.classList.remove("hidden");

  // Fetch existing Stage 2 + Working Station data to pre-fill form if already mapped
  try {
    const info = await fetchAPI(`/employees/stage3-employee-info/${encodeURIComponent(sel.value)}`);
    if (info) {
      if (info.name_ifmis) document.getElementById("stage2-card-name").textContent = info.name_ifmis;
      if (info.mobile_number) document.getElementById("stage2-card-mobile").textContent = info.mobile_number;

      const salGpSel = document.getElementById("stage2-salary-gp");
      if (info.salary_gp_lgd && salGpSel) {
        salGpSel.value = String(info.salary_gp_lgd);
        handleStage2SalaryGPChange({ target: salGpSel });
      }
      if (info.salary_claiming_status) {
        document.getElementById("stage2-salary-status").value = info.salary_claiming_status;
      }
      document.getElementById("stage2-effective-date").value = info.working_from_date || "";

      const statusSel = document.getElementById("stage2-service-status");
      if (info.service_status && statusSel) {
        statusSel.value = info.service_status;
        handleStage2ServiceStatusChange({ target: statusSel });
      }
      document.getElementById("stage2-order-no").value = info.status_order_no || "";
      document.getElementById("stage2-order-date").value = info.status_order_date || "";
      document.getElementById("stage2-remarks").value = info.status_remarks || "";

      if (info.current_posting) {
        const cp = info.current_posting;
        const radioVal = cp.is_working_in_salary_gp ? "YES" : "NO";
        const radioEl = document.querySelector(`input[name="stage2-working-same"][value="${radioVal}"]`);
        if (radioEl) {
          radioEl.checked = true;
          handleStage2WorkingSameChange({ target: radioEl });
        }

        if (!cp.is_working_in_salary_gp) {
          const pTypeSel = document.getElementById("stage2-posting-type");
          const resolvedType = (cp.posting_type && cp.posting_type !== "OWN_GP") ? cp.posting_type : "WITHIN_MANDAL";
          pTypeSel.value = resolvedType;
          handleStage2PostingTypeChange({ target: pTypeSel });

          if (resolvedType === "WITHIN_MANDAL") {
            if (info.salary_mandal_id) {
              populateStage2SameMandalGPs(info.salary_mandal_id, info.salary_mandal_name || "Mandal");
            }
            if (cp.actual_working_gp_lgd) {
              document.getElementById("stage2-same-mandal-gp").value = String(cp.actual_working_gp_lgd);
            }
          } else if (resolvedType === "ANOTHER_MANDAL" && cp.actual_working_mandal_id) {
            const mSel = document.getElementById("stage2-another-mandal-select");
            mSel.value = String(cp.actual_working_mandal_id);
            handleStage2DestMandalChange({ target: mSel });
            if (cp.actual_working_gp_lgd) {
              document.getElementById("stage2-another-mandal-gp").value = String(cp.actual_working_gp_lgd);
            }
          } else if (resolvedType === "OTHER_DISTRICT") {
            document.getElementById("stage2-other-dist-name").value = cp.external_district_name || "";
            document.getElementById("stage2-other-dist-office").value = cp.external_gp_or_office_name || "";
          } else if (resolvedType === "OTHER_DEPARTMENT") {
            document.getElementById("stage2-other-dept-name").value = cp.external_department_name || "";
            document.getElementById("stage2-other-dept-office").value = cp.external_gp_or_office_name || "";
          }

          document.getElementById("stage2-dep-order-no").value = cp.deputation_order_no || "";
          document.getElementById("stage2-dep-order-date").value = cp.deputation_order_date || "";
          document.getElementById("stage2-dep-effective-date").value = cp.deputation_effective_from || "";
          document.getElementById("stage2-dep-remarks").value = cp.remarks || "";
        }
      }
    }
  } catch (err) {
    console.warn("Could not prefill Stage 2 existing mapping info", err);
  }
}

function handleStage2SalaryGPChange(e) {
  const sel = e.target;
  const opt = sel.options[sel.selectedIndex];
  const mandalDisp = document.getElementById("stage2-mandal-display");
  const lgdDisp = document.getElementById("stage2-lgd-display");

  if (!sel.value || !opt) {
    mandalDisp.textContent = "Select GP above";
    lgdDisp.textContent = "LGD Code: -";
    return;
  }
  const mName = opt.getAttribute("data-mandal") || "-";
  const mId = opt.getAttribute("data-mandal-id");
  mandalDisp.textContent = mName;
  lgdDisp.textContent = `LGD Code: ${sel.value}`;
  if (mId) {
    populateStage2SameMandalGPs(mId, mName);
  }
}

function handleStage2ServiceStatusChange(e) {
  const status = e.target.value;
  const detailsWrap = document.getElementById("stage2-status-details");
  const orderLabel = document.getElementById("stage2-order-label");
  const dateLabel = document.getElementById("stage2-date-label");

  if (status === "WORKING") {
    detailsWrap.classList.add("hidden");
  } else {
    detailsWrap.classList.remove("hidden");
    if (status === "SUSPENDED") {
      orderLabel.innerHTML = 'Suspension Order / Proceedings Number <span class="text-rose-600">*</span>';
      dateLabel.innerHTML = 'Date from which Suspended <span class="text-rose-600">*</span>';
    } else if (status === "ABSCONDING") {
      orderLabel.innerHTML = 'Disciplinary Notice / Memo Reference (if any)';
      dateLabel.innerHTML = 'Date from which Absconding <span class="text-rose-600">*</span>';
    } else if (status === "MEDICAL_LEAVE") {
      orderLabel.innerHTML = 'Medical Leave Sanction Proceedings No';
      dateLabel.innerHTML = 'Date from which Proceeded on Medical Leave <span class="text-rose-600">*</span>';
    } else if (status === "MATERNITY_LEAVE") {
      orderLabel.innerHTML = 'Maternity Leave Sanction Proceedings No';
      dateLabel.innerHTML = 'Date from which Proceeded on Maternity Leave <span class="text-rose-600">*</span>';
    } else if (status === "CHILD_CARE_LEAVE") {
      orderLabel.innerHTML = 'Child Care Leave Sanction Proceedings No';
      dateLabel.innerHTML = 'Date from which Proceeded on Child Care Leave <span class="text-rose-600">*</span>';
    } else if (status === "LONG_LEAVE") {
      orderLabel.innerHTML = 'Long Leave Sanction Proceedings No';
      dateLabel.innerHTML = 'Date from which Proceeded on Long Leave <span class="text-rose-600">*</span>';
    } else if (status === "EARNED_LEAVE") {
      orderLabel.innerHTML = 'Earned Leave Sanction Proceedings No';
      dateLabel.innerHTML = 'Date from which Proceeded on Earned Leave <span class="text-rose-600">*</span>';
    } else if (status === "EXTRAORDINARY_LEAVE") {
      orderLabel.innerHTML = 'EOL Sanction Proceedings No';
      dateLabel.innerHTML = 'Date from which Proceeded on Leave Without Pay (EOL) <span class="text-rose-600">*</span>';
    } else {
      orderLabel.innerHTML = 'Leave Sanction Proceedings No';
      dateLabel.innerHTML = 'Date from which Proceeded on Leave <span class="text-rose-600">*</span>';
    }
  }
}

function handleStage2WorkingSameChange(e) {
  const isSame = e.target.value === "YES";
  const depPanel = document.getElementById("stage2-deputation-panel");
  if (depPanel) {
    depPanel.classList.toggle("hidden", isSame);
  }
}

function handleStage2PostingTypeChange(e) {
  const type = e.target.value;
  document.getElementById("stage2-dest-same-mandal").classList.toggle("hidden", type !== "WITHIN_MANDAL");
  document.getElementById("stage2-dest-another-mandal").classList.toggle("hidden", type !== "ANOTHER_MANDAL");
  document.getElementById("stage2-dest-other-dist").classList.toggle("hidden", type !== "OTHER_DISTRICT");
  document.getElementById("stage2-dest-other-dept").classList.toggle("hidden", type !== "OTHER_DEPARTMENT");
}

function handleStage2DestMandalChange(e) {
  const mId = parseInt(e.target.value);
  const gpSelect = document.getElementById("stage2-another-mandal-gp");
  if (!mId) {
    gpSelect.innerHTML = `<option value="">-- Select Mandal First --</option>`;
    return;
  }
  const destGps = centralizedPanchayats.filter(g => g.mandal_id === mId);
  let optHtml = `<option value="">-- Select Destination GP --</option>`;
  destGps.forEach(g => {
    optHtml += `<option value="${g.lgd_code}">${g.gp_name} (LGD: ${g.lgd_code})</option>`;
  });
  gpSelect.innerHTML = optHtml;
}

async function handleStage2SalarySubmit(e) {
  e.preventDefault();
  const empId = document.getElementById("stage2-emp-select").value;
  const gpLgd = parseInt(document.getElementById("stage2-salary-gp").value);
  if (!empId || !gpLgd) {
    alert("Please select both Employee and Salary-Claiming Gram Panchayat.");
    return;
  }

  const isWorkingSame = document.querySelector('input[name="stage2-working-same"]:checked').value === "YES";
  const postingType = isWorkingSame ? "OWN_GP" : document.getElementById("stage2-posting-type").value;

  let actualWorkingLgd = null;
  let extDist = null;
  let extMandal = null;
  let extOffice = null;
  let extDept = null;

  if (isWorkingSame) {
    actualWorkingLgd = gpLgd;
  } else if (postingType === "WITHIN_MANDAL") {
    actualWorkingLgd = parseInt(document.getElementById("stage2-same-mandal-gp").value);
    if (!actualWorkingLgd) {
      alert("Please select the Destination Gram Panchayat in the same Mandal.");
      return;
    }
  } else if (postingType === "ANOTHER_MANDAL") {
    actualWorkingLgd = parseInt(document.getElementById("stage2-another-mandal-gp").value);
    if (!actualWorkingLgd) {
      alert("Please select the Destination Gram Panchayat in the destination Mandal.");
      return;
    }
  } else if (postingType === "OTHER_DISTRICT") {
    extDist = document.getElementById("stage2-other-dist-name").value.trim();
    extOffice = document.getElementById("stage2-other-dist-office").value.trim();
    if (!extDist) {
      alert("Please provide the External District Name.");
      return;
    }
  } else if (postingType === "OTHER_DEPARTMENT") {
    extDept = document.getElementById("stage2-other-dept-name").value.trim();
    extOffice = document.getElementById("stage2-other-dept-office").value.trim();
    if (!extDept) {
      alert("Please provide the External Department Name.");
      return;
    }
  }

  const submitBtn = document.getElementById("stage2-submit-btn");
  submitBtn.disabled = true;
  submitBtn.innerHTML = `<i data-lucide="loader" class="w-4 h-4 mr-1.5 animate-spin"></i> Saving Mapping...`;
  lucide.createIcons();

  const payload = {
    employee_id: empId,
    salary_gp_lgd: gpLgd,
    salary_claiming_status: document.getElementById("stage2-salary-status").value,
    working_from_date: document.getElementById("stage2-effective-date").value || null,
    service_status: document.getElementById("stage2-service-status").value,
    status_order_no: document.getElementById("stage2-order-no").value || null,
    status_order_date: document.getElementById("stage2-order-date").value || null,
    remarks: document.getElementById("stage2-remarks").value || null,
    is_working_in_salary_gp: isWorkingSame,
    posting_type: postingType,
    actual_working_gp_lgd: actualWorkingLgd,
    external_district_name: extDist,
    external_mandal_name: extMandal,
    external_gp_or_office_name: extOffice,
    external_department_name: extDept,
    deputation_order_no: document.getElementById("stage2-dep-order-no")?.value || null,
    deputation_order_date: document.getElementById("stage2-dep-order-date")?.value || null,
    deputation_effective_from: document.getElementById("stage2-dep-effective-date")?.value || null,
    deputation_remarks: document.getElementById("stage2-dep-remarks")?.value || null
  };

  try {
    const res = await fetchAPI("/employees/stage2-combined-mapping", {
      method: "POST",
      body: JSON.stringify(payload)
    });

    alert(
      `Stage 2 Mapping Saved Successfully!\n` +
      `Employee: ${empId}\n` +
      `Salary GP: ${res.salary_gp_name} (${res.salary_mandal_name})\n` +
      `Working Station: ${res.actual_working_gp_name || 'External Office'} (${res.posting_type})`
    );

    if (confirm("View this record in the 22-Column Master Reconciliation Report?")) {
      navigate("reconciliation-report");
    } else {
      renderStage2SalaryMappingView();
    }

  } catch (err) {
    alert("Mapping Failed: " + (err.detail || JSON.stringify(err)));
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<i data-lucide="check" class="w-4 h-4 mr-1.5"></i> Save Salary & Working Mapping (Stage 2)`;
    lucide.createIcons();
  }
}

// ==========================================
// 2C. STAGE 3 COMPATIBILITY REDIRECT (COMBINED INTO STAGE 2)
// ==========================================
function renderStage3WorkingMappingView(preselectedEmpId = null) {
  if (preselectedEmpId) pendingStage2EmpId = preselectedEmpId;
  navigate("stage2-salary-mapping");
}

// ==========================================
// 2D. INTERNAL REASSIGNMENT MODULE
// ==========================================
async function renderInternalReassignmentView() {
  const container = document.getElementById("view-internal-reassignment");
  if (!container) return;

  const isMandal = currentUser && currentUser.role === "MANDAL_ADMIN";
  const myMandalId = currentUser ? currentUser.mandal_id : null;
  const myMandalName = currentUser ? (currentUser.mandal_name || "Mandal") : "";

  // Available GPs in this receiving Mandal for reassigning to
  const mandalGps = isMandal
    ? centralizedPanchayats.filter(gp => gp.mandal_id === myMandalId)
    : centralizedPanchayats;

  let reassignGpOptions = `<option value="">-- Select Reassigned Working GP (GP-Z) --</option>`;
  mandalGps.forEach(g => {
    reassignGpOptions += `<option value="${g.lgd_code}">${g.gp_name} (LGD: ${g.lgd_code}) - ${g.mandal_name}</option>`;
  });

  // Deputed employees list
  let deputedEmployees = [];
  try {
    const dropdownList = await fetchAPI("/employees/dropdown-list");
    deputedEmployees = dropdownList || [];
  } catch (err) {
    console.error("Error fetching deputed list", err);
  }

  let empOptions = `<option value="">-- Select Deputed Panchayat Secretary --</option>`;
  deputedEmployees.forEach(e => {
    const empId = e.employee_id || e.id;
    empOptions += `<option value="${empId}">${e.display_label || (e.name_ifmis + ' - ' + empId)}</option>`;
  });

  container.innerHTML = `
    <div class="max-w-5xl mx-auto space-y-6">
      
      <!-- Module Header with Clear Government Logic Explanation -->
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-5 border-t-4 border-pink-600">
        <div class="flex flex-wrap justify-between items-center gap-3">
          <div>
            <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-pink-100 text-pink-900 border border-pink-300 mb-1">
              <i data-lucide="shuffle" class="w-3.5 h-3.5 mr-1"></i> RECEIVING MANDAL REASSIGNMENT ENGINE
            </span>
            <h2 class="text-xl font-bold text-slate-900">Internal Reassignment Module (GP-X to GP-Z)</h2>
            <p class="text-xs text-slate-500">Record when a receiving Mandal reassigns an officially deputed secretary to another GP (e.g. from GP-X to GP-Z) without modifying the original deputation order.</p>
          </div>
          <button onclick="navigate('reconciliation-report')" class="px-3.5 py-1.5 bg-govblue-900 hover:bg-govblue-800 text-white rounded text-xs font-semibold flex items-center shadow transition">
            <i data-lucide="file-text" class="w-3.5 h-3.5 mr-1.5"></i> Open Master Reconciliation Report
          </button>
        </div>

        <div class="mt-4 p-3 bg-pink-50/70 rounded-lg border border-pink-200 text-xs text-pink-950 flex items-start space-x-2">
          <i data-lucide="info" class="w-4 h-4 text-pink-700 flex-shrink-0 mt-0.5"></i>
          <div>
            <strong>Architectural Guarantee:</strong> The original official deputation Gram Panchayat (GP-X) is permanently preserved in the database. Recording an internal reassignment updates the presently working station (GP-Z) and adds a permanent movement audit trail.
          </div>
        </div>
      </div>

      <!-- Reassignment Action Form -->
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <h3 class="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4 flex items-center">
          <i data-lucide="edit-3" class="w-4 h-4 mr-2 text-pink-600"></i>
          Record Internal Reassignment for Deputed Secretary
        </h3>

        <form id="reassign-form" onsubmit="handleInternalReassignmentSubmit(event)" class="space-y-5 text-xs text-slate-700">
          
          <!-- Select Deputed Employee -->
          <div class="p-4 bg-slate-50 rounded-lg border border-slate-200">
            <label class="block font-bold text-slate-800 uppercase mb-1">
              Select Deputed Panchayat Secretary <span class="text-rose-600">*</span>
            </label>
            <select id="reassign-emp-select" required onchange="handleReassignEmpSelect(event)" class="w-full p-2.5 border border-slate-300 rounded focus:ring-1 focus:ring-pink-700 font-semibold text-slate-800 bg-white outline-none">
              ${empOptions}
            </select>

            <!-- Auto-Populated Deputation Context Card -->
            <div id="reassign-context-card" class="hidden mt-3 p-3.5 bg-white rounded border border-slate-200 grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                <span class="text-[10px] text-slate-400 uppercase font-bold block">Salary GP & Mandal</span>
                <span id="reassign-sal-gp" class="font-bold text-slate-800">-</span>
              </div>
              <div>
                <span class="text-[10px] text-slate-400 uppercase font-bold block">Official Deputation GP (GP-X)</span>
                <span id="reassign-off-gp" class="font-bold text-amber-700 font-mono">-</span>
              </div>
              <div>
                <span class="text-[10px] text-slate-400 uppercase font-bold block">Deputation Order No & Date</span>
                <span id="reassign-order-info" class="font-mono text-slate-700">-</span>
              </div>
              <div>
                <span class="text-[10px] text-slate-400 uppercase font-bold block">Presently Working Station</span>
                <span id="reassign-current-working" class="font-bold text-indigo-700">-</span>
              </div>
            </div>
          </div>

          <!-- Reassignment Destination (GP-Z) & Date -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="block font-bold text-slate-800 uppercase mb-1">
                Reassigned Working Gram Panchayat (GP-Z) <span class="text-rose-600">*</span>
              </label>
              <select id="reassign-target-gp" required class="w-full p-2.5 border border-slate-300 rounded focus:ring-1 focus:ring-pink-700 bg-white outline-none font-semibold text-slate-800">
                ${reassignGpOptions}
              </select>
            </div>
            <div>
              <label class="block font-bold text-slate-800 uppercase mb-1">
                Reassignment Date <span class="text-rose-600">*</span>
              </label>
              <input type="date" id="reassign-date" required class="w-full p-2.5 border border-slate-300 rounded focus:ring-1 focus:ring-pink-700 bg-white outline-none">
            </div>
          </div>

          <!-- Written Proceedings Available Toggle -->
          <div class="p-4 bg-slate-50 rounded-lg border border-slate-200 space-y-3">
            <div class="flex items-center justify-between">
              <label class="font-bold text-slate-800 uppercase text-xs">
                Are Written Proceedings / Office Orders Available for this Reassignment?
              </label>
              <label class="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" id="reassign-has-proceedings" onchange="handleProceedingsToggle(event)" class="sr-only peer">
                <div class="w-11 h-6 bg-slate-300 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-pink-600"></div>
                <span id="reassign-proceedings-label" class="ml-2 font-semibold text-slate-700">No (Internal Arrangement)</span>
              </label>
            </div>

            <!-- Warning Banner When NO Written Proceedings -->
            <div id="reassign-internal-notice" class="p-3 bg-amber-50 rounded border border-amber-300 text-amber-900 font-semibold flex items-center">
              <i data-lucide="alert-triangle" class="w-4 h-4 mr-2 text-amber-600 flex-shrink-0"></i>
              <span>INTERNAL ARRANGEMENT – WRITTEN PROCEEDINGS NOT AVAILABLE. Detailed administrative justification remarks are mandatory below.</span>
            </div>

            <!-- Proceedings Fields (When Available) -->
            <div id="reassign-order-inputs" class="hidden grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
              <div>
                <label class="block font-bold text-slate-700 uppercase mb-1 text-[10px]">Proceedings / Order Number</label>
                <input type="text" id="reassign-proceedings-no" placeholder="e.g. Rc.No.123/2026/A1..." class="w-full p-2 border border-slate-300 rounded outline-none">
              </div>
              <div>
                <label class="block font-bold text-slate-700 uppercase mb-1 text-[10px]">Order Date</label>
                <input type="date" id="reassign-proceedings-date" class="w-full p-2 border border-slate-300 rounded outline-none bg-white">
              </div>
            </div>

            <!-- Mandatory Administrative Remarks -->
            <div>
              <label class="block font-bold text-slate-800 uppercase mb-1">
                Reason / Administrative Justification Remarks <span class="text-rose-600">*</span>
              </label>
              <textarea id="reassign-remarks" required rows="2" placeholder="Explain reasons for internal reassignment to GP-Z (e.g. GP-Z has clear vacancy / urgent public administration duty)..." class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-pink-700 outline-none"></textarea>
            </div>
          </div>

          <!-- Submit Buttons -->
          <div class="pt-3 border-t border-slate-200 flex justify-end space-x-3">
            <button type="submit" id="reassign-submit-btn" class="px-5 py-2.5 bg-pink-800 hover:bg-pink-900 text-white font-bold rounded shadow transition flex items-center">
              <i data-lucide="shuffle" class="w-4 h-4 mr-1.5"></i> Confirm Internal Reassignment (to GP-Z)
            </button>
          </div>

        </form>
      </div>

    </div>
  `;
  lucide.createIcons();
}

async function handleReassignEmpSelect(e) {
  const empId = e.target.value;
  const card = document.getElementById("reassign-context-card");
  if (!empId) {
    card.classList.add("hidden");
    return;
  }

  try {
    const info = await fetchAPI(`/employees/stage3-employee-info/${encodeURIComponent(empId)}`);
    document.getElementById("reassign-sal-gp").textContent = `${info.salary_gp_name || 'N/A'} (${info.salary_mandal_name || ''})`;
    document.getElementById("reassign-off-gp").textContent = info.official_deputation_gp_name || info.working_gp_name || "GP-X";
    document.getElementById("reassign-order-info").textContent = `${info.deputation_order_no || 'N/A'} (${info.deputation_order_date || 'N/A'})`;
    document.getElementById("reassign-current-working").textContent = info.working_gp_name || info.salary_gp_name || "N/A";
    card.classList.remove("hidden");
  } catch (err) {
    console.error("Error loading reassignment employee info", err);
  }
}

function handleProceedingsToggle(e) {
  const isChecked = e.target.checked;
  const label = document.getElementById("reassign-proceedings-label");
  const notice = document.getElementById("reassign-internal-notice");
  const inputs = document.getElementById("reassign-order-inputs");

  if (isChecked) {
    label.textContent = "Yes (Written Order Available)";
    notice.classList.add("hidden");
    inputs.classList.remove("hidden");
  } else {
    label.textContent = "No (Internal Arrangement)";
    notice.classList.remove("hidden");
    inputs.classList.add("hidden");
  }
}

async function handleInternalReassignmentSubmit(e) {
  e.preventDefault();
  const empId = document.getElementById("reassign-emp-select").value;
  const targetLgd = parseInt(document.getElementById("reassign-target-gp").value);
  const reassignDate = document.getElementById("reassign-date").value;
  const remarks = document.getElementById("reassign-remarks").value.trim();
  const hasProceedings = document.getElementById("reassign-has-proceedings").checked;

  if (!empId || !targetLgd || !reassignDate || !remarks) {
    alert("Please fill all mandatory fields including administrative remarks.");
    return;
  }

  const submitBtn = document.getElementById("reassign-submit-btn");
  submitBtn.disabled = true;
  submitBtn.innerHTML = `<i data-lucide="loader" class="w-4 h-4 mr-1.5 animate-spin"></i> Recording Reassignment...`;
  lucide.createIcons();

  const payload = {
    employee_id: empId,
    reassigned_to_gp_lgd: targetLgd,
    reassignment_date: reassignDate,
    is_written_proceedings_available: hasProceedings,
    proceedings_order_no: hasProceedings ? (document.getElementById("reassign-proceedings-no")?.value || null) : null,
    reason_remarks: remarks
  };

  try {
    const res = await fetchAPI("/employees/internal-reassignment", {
      method: "POST",
      body: JSON.stringify(payload)
    });

    alert(`Internal Reassignment Recorded Successfully!\nOriginal Deputation GP: ${res.original_deputation_gp_lgd} (Permanently Retained)\nReassigned Presently Working GP: ${res.reassigned_to_gp_name} (GP-Z)\nProceedings Status: ${res.is_written_proceedings_available ? 'Written Order Available' : 'INTERNAL ARRANGEMENT'}`);

    if (confirm("View the updated 22-Column Master Reconciliation Report?")) {
      navigate("reconciliation-report");
    } else {
      renderInternalReassignmentView();
    }

  } catch (err) {
    alert("Reassignment Failed: " + (err.detail || JSON.stringify(err)));
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<i data-lucide="shuffle" class="w-4 h-4 mr-1.5"></i> Confirm Internal Reassignment (to GP-Z)`;
    lucide.createIcons();
  }
}

// ==========================================
// 2E. CLEAR VACANCY REGISTER (CATEGORY A ONLY)
// ==========================================
let clearVacancySearch = "";
let clearVacancyMandal = "";

async function renderClearVacancyRegisterView() {
  const container = document.getElementById("view-clear-vacancy-register");
  if (!container) return;

  const isMandal = currentUser && currentUser.role === "MANDAL_ADMIN";
  const myMandalId = currentUser ? currentUser.mandal_id : null;

  let mandalOptions = `<option value="">All Mandals</option>`;
  cachedMandals.forEach(m => {
    mandalOptions += `<option value="${m.id}">${m.mandal_name} (LGD: ${m.mandal_lgd})</option>`;
  });

  container.innerHTML = `
    <div class="space-y-5">
      
      <!-- Header -->
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-5 border-t-4 border-rose-600 flex flex-wrap justify-between items-center gap-3">
        <div>
          <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-rose-100 text-rose-900 border border-rose-300 mb-1">
            <i data-lucide="shield-alert" class="w-3.5 h-3.5 mr-1"></i> CATEGORY A • NO SALARY CLAIMANT & NO DEPUTED PS
          </span>
          <h2 class="text-xl font-bold text-slate-900">Clear Vacancy Register (Category A ONLY)</h2>
          <p class="text-xs text-slate-500">Dedicated register strictly displaying Gram Panchayats with zero salary claimants, zero deputed secretaries, and zero attending personnel.</p>
        </div>
        <div class="flex items-center space-x-2">
          <a href="${API_BASE}/reports/export/H?format=excel" download class="px-3.5 py-1.5 bg-emerald-700 hover:bg-emerald-800 text-white rounded text-xs font-semibold flex items-center shadow transition">
            <i data-lucide="file-spreadsheet" class="w-3.5 h-3.5 mr-1.5"></i> Download Category A Excel
          </a>
          <a href="${API_BASE}/reports/export/H?format=csv" download class="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-900 text-white rounded text-xs font-semibold flex items-center shadow transition">
            <i data-lucide="file-text" class="w-3.5 h-3.5 mr-1.5"></i> CSV
          </a>
        </div>
      </div>

      <!-- Filters & Counter -->
      <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-wrap justify-between items-center gap-3">
        <div class="flex flex-wrap gap-3 items-center flex-1">
          <div class="min-w-[200px]">
            <input type="text" id="clear-vac-search" placeholder="Search GP Name or LGD Code..." oninput="handleClearVacSearch(event)" class="w-full p-2 text-xs border border-slate-300 rounded outline-none focus:ring-1 focus:ring-rose-600">
          </div>
          <div class="w-56">
            <select id="clear-vac-mandal-select" ${isMandal ? 'disabled' : ''} onchange="handleClearVacMandalChange(event)" class="w-full p-2 text-xs border border-slate-300 rounded bg-white outline-none">
              ${mandalOptions}
            </select>
          </div>
          <button onclick="loadClearVacanciesData()" class="px-3 py-2 bg-slate-800 hover:bg-slate-900 text-white rounded text-xs font-semibold flex items-center">
            <i data-lucide="refresh-cw" class="w-3.5 h-3.5 mr-1"></i> Refresh
          </button>
        </div>
        <div class="bg-rose-50 px-3.5 py-2 rounded-lg border border-rose-200 flex items-center space-x-2">
          <i data-lucide="alert-circle" class="w-4 h-4 text-rose-600"></i>
          <span class="text-xs font-bold text-rose-900">Total Category A Clear Vacancies: <span id="clear-vac-total-badge" class="font-mono text-base">-</span></span>
        </div>
      </div>

      <!-- Table Container -->
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs text-slate-700">
            <thead class="bg-slate-50 border-b border-slate-200 text-[11px] font-bold text-slate-600 uppercase tracking-wider">
              <tr>
                <th class="px-3.5 py-3">#</th>
                <th class="px-3.5 py-3">Mandal Name</th>
                <th class="px-3.5 py-3">Gram Panchayat Name</th>
                <th class="px-3.5 py-3">GP LGD Code</th>
                <th class="px-3.5 py-3 text-center">Salary Strength</th>
                <th class="px-3.5 py-3 text-center">Deputed In</th>
                <th class="px-3.5 py-3 text-center">Actual Working</th>
                <th class="px-3.5 py-3 text-center">Position Status</th>
                <th class="px-3.5 py-3">Remarks</th>
                <th class="px-3.5 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody id="clear-vac-tbody" class="divide-y divide-slate-100">
              <tr><td colspan="10" class="text-center py-8 text-slate-400">Loading Category A Clear Vacancies...</td></tr>
            </tbody>
          </table>
        </div>
      </div>

    </div>
  `;
  lucide.createIcons();

  if (isMandal) {
    clearVacancyMandal = myMandalId;
    const sel = document.getElementById("clear-vac-mandal-select");
    if (sel) sel.value = myMandalId;
  }

  loadClearVacanciesData();
}

function handleClearVacSearch(e) {
  clearVacancySearch = e.target.value.toLowerCase();
  loadClearVacanciesData();
}

function handleClearVacMandalChange(e) {
  clearVacancyMandal = e.target.value;
  loadClearVacanciesData();
}

async function loadClearVacanciesData() {
  const tbody = document.getElementById("clear-vac-tbody");
  if (!tbody) return;

  try {
    let url = `/analytics/gp-positions?category=CATEGORY_A&limit=600`;
    if (clearVacancyMandal) url += `&mandal_id=${clearVacancyMandal}`;
    if (clearVacancySearch) url += `&search=${encodeURIComponent(clearVacancySearch)}`;

    const data = await fetchAPI(url);
    const items = data.items || [];

    const badge = document.getElementById("clear-vac-total-badge");
    if (badge) badge.textContent = data.total || items.length;

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" class="text-center py-8 text-slate-400">No Gram Panchayats match Category A criteria for the selected filters.</td></tr>`;
      return;
    }

    let rowsHtml = "";
    items.forEach((gp, idx) => {
      rowsHtml += `
        <tr class="hover:bg-rose-50/40">
          <td class="px-3.5 py-2.5 font-mono text-[11px] text-slate-400">${idx + 1}</td>
          <td class="px-3.5 py-2.5 font-semibold text-slate-800">${gp.mandal_name}</td>
          <td class="px-3.5 py-2.5 font-bold text-slate-900">${gp.gp_name}</td>
          <td class="px-3.5 py-2.5 font-mono text-slate-600">${gp.lgd_code}</td>
          <td class="px-3.5 py-2.5 text-center font-bold text-slate-400 font-mono">0</td>
          <td class="px-3.5 py-2.5 text-center font-bold text-slate-400 font-mono">0</td>
          <td class="px-3.5 py-2.5 text-center font-bold text-slate-400 font-mono">0</td>
          <td class="px-3.5 py-2.5 text-center">
            <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-200">CATEGORY A (CLEAR VACANT)</span>
          </td>
          <td class="px-3.5 py-2.5 text-slate-500 text-[11px] italic">${gp.vacancy_remarks || 'No secretary attached or working'}</td>
          <td class="px-3.5 py-2.5 text-right">
            <button onclick="navigate('stage2-salary-mapping')" class="px-2.5 py-1 bg-govblue-900 hover:bg-govblue-800 text-white rounded text-[11px] font-semibold transition" title="Depute Secretary">
              Depute Secretary →
            </button>
          </td>
        </tr>
      `;
    });
    tbody.innerHTML = rowsHtml;

  } catch (err) {
    console.error("Failed loading clear vacancies", err);
    tbody.innerHTML = `<tr><td colspan="10" class="text-center py-6 text-red-500">Error loading Category A Clear Vacancies.</td></tr>`;
  }
}

// ==========================================
// 2F. 22-COLUMN MASTER RECONCILIATION REPORT
// ==========================================
let cachedReportDRows = [];
let cachedReportDHeaders = [];

async function renderReconciliationReportView() {
  const container = document.getElementById("view-reconciliation-report");
  if (!container) return;

  const isMandal = currentUser && currentUser.role === "MANDAL_ADMIN";
  const myMandalId = currentUser ? currentUser.mandal_id : null;

  let mandalOptions = `<option value="">All Mandals</option>`;
  cachedMandals.forEach(m => {
    mandalOptions += `<option value="${m.mandal_name}">${m.mandal_name}</option>`;
  });

  container.innerHTML = `
    <div class="space-y-5">
      
      <!-- Report Header -->
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-5 border-t-4 border-amber-500 flex flex-wrap justify-between items-center gap-3">
        <div>
          <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-100 text-amber-900 border border-amber-300 mb-1">
            <i data-lucide="shield-check" class="w-3.5 h-3.5 mr-1"></i> STATUTORY AUDIT & RECONCILIATION
          </span>
          <h2 class="text-xl font-bold text-slate-900">District Panchayat Secretary Master & Working Station Reconciliation Report</h2>
          <p class="text-xs text-slate-500">Mandatory 22-column comprehensive reconciliation statement showing salary GP, official deputation GP, internal reassignment, presently working GP, and verification status.</p>
        </div>
        <div class="flex items-center space-x-2">
          <a href="${API_BASE}/reports/export/D?format=excel" download class="px-3.5 py-1.5 bg-emerald-700 hover:bg-emerald-800 text-white rounded text-xs font-semibold flex items-center shadow transition">
            <i data-lucide="file-spreadsheet" class="w-3.5 h-3.5 mr-1.5"></i> Export 22-Col Excel
          </a>
          <a href="${API_BASE}/reports/export/D?format=csv" download class="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-900 text-white rounded text-xs font-semibold flex items-center shadow transition">
            <i data-lucide="file-text" class="w-3.5 h-3.5 mr-1.5"></i> Export CSV
          </a>
          <button onclick="window.print()" class="px-3 py-1.5 bg-white border border-slate-300 hover:bg-slate-100 text-slate-700 rounded text-xs font-semibold flex items-center shadow-sm">
            <i data-lucide="printer" class="w-3.5 h-3.5 mr-1"></i> Print
          </button>
        </div>
      </div>

      <!-- Filters Row -->
      <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm grid grid-cols-1 md:grid-cols-5 gap-3 items-center">
        <div class="md:col-span-2">
          <label class="block text-[10px] font-bold text-slate-500 uppercase mb-1">Search Employee / Mobile / GP</label>
          <div class="relative">
            <input type="text" id="recon-search-input" placeholder="Type Employee Name, ID, Mobile, or GP..." oninput="filterReconciliationTable()" class="w-full pl-8 pr-3 py-1.5 text-xs border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800 outline-none">
            <i data-lucide="search" class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5"></i>
          </div>
        </div>

        <div>
          <label class="block text-[10px] font-bold text-slate-500 uppercase mb-1">Mandal Filter</label>
          <select id="recon-mandal-filter" onchange="filterReconciliationTable()" class="w-full p-1.5 text-xs border border-slate-300 rounded bg-white outline-none">
            ${mandalOptions}
          </select>
        </div>

        <div>
          <label class="block text-[10px] font-bold text-slate-500 uppercase mb-1">Deputation Type</label>
          <select id="recon-type-filter" onchange="filterReconciliationTable()" class="w-full p-1.5 text-xs border border-slate-300 rounded bg-white outline-none">
            <option value="">All Types</option>
            <option value="REGULAR">Regular (Own GP)</option>
            <option value="WITHIN_MANDAL">Within Same Mandal</option>
            <option value="ANOTHER_MANDAL">Another Mandal</option>
            <option value="OTHER_DISTRICT">Other District</option>
            <option value="OTHER_DEPARTMENT">Other Department</option>
          </select>
        </div>

        <div>
          <label class="block text-[10px] font-bold text-slate-500 uppercase mb-1">Service Status</label>
          <select id="recon-status-filter" onchange="filterReconciliationTable()" class="w-full p-1.5 text-xs border border-slate-300 rounded bg-white outline-none">
            <option value="">All Statuses</option>
            <option value="WORKING">Working (Regular)</option>
            <option value="SUSPENDED">Suspended</option>
            <option value="ABSCONDING">Absconding</option>
            <option value="LONG_LEAVE">Long Leave</option>
            <option value="MEDICAL_LEAVE">Medical Leave</option>
          </select>
        </div>
      </div>

      <!-- Counter Bar -->
      <div class="flex justify-between items-center text-xs text-slate-500 px-1">
        <div>Showing <strong id="recon-count-display" class="text-slate-900 font-mono">0</strong> records matching active filters</div>
        <button onclick="loadReconciliationReportData()" class="text-govblue-800 font-semibold hover:underline flex items-center">
          <i data-lucide="refresh-cw" class="w-3 h-3 mr-1"></i> Reload from Database
        </button>
      </div>

      <!-- 22-Column Full Width Table Container -->
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="overflow-x-auto max-h-[650px] relative">
          <table class="w-full text-left text-[11px] text-slate-700 whitespace-nowrap">
            <thead class="bg-slate-800 text-white font-bold text-[10px] uppercase tracking-wider sticky top-0 z-10">
              <tr id="recon-table-headers">
                <th class="px-2.5 py-3 border-r border-slate-700">#</th>
                <th class="px-2.5 py-3 border-r border-slate-700">Employee Name</th>
                <th class="px-2.5 py-3 border-r border-slate-700">Employee ID</th>
                <th class="px-2.5 py-3 border-r border-slate-700">Mobile No</th>
                <th class="px-2.5 py-3 border-r border-slate-700">Reg. Mandal</th>
                <th class="px-2.5 py-3 border-r border-slate-700">Salary GP</th>
                <th class="px-2.5 py-3 border-r border-slate-700">Salary Mandal</th>
                <th class="px-2.5 py-3 border-r border-slate-700">Official Deputation GP</th>
                <th class="px-2.5 py-3 border-r border-slate-700">Official Deputation Mandal</th>
                <th class="px-2.5 py-3 border-r border-slate-700">Order No</th>
                <th class="px-2.5 py-3 border-r border-slate-700">Order Date</th>
                <th class="px-2.5 py-3 border-r border-slate-700">Effective Date</th>
                <th class="px-2.5 py-3 border-r border-slate-700">Reassigned From</th>
                <th class="px-2.5 py-3 border-r border-slate-700">Reassigned To (GP-Z)</th>
                <th class="px-2.5 py-3 border-r border-slate-700">Reassignment Date</th>
                <th class="px-2.5 py-3 border-r border-slate-700">Presently Working GP</th>
                <th class="px-2.5 py-3 border-r border-slate-700">Presently Working Mandal</th>
                <th class="px-2.5 py-3 border-r border-slate-700">Service Status</th>
                <th class="px-2.5 py-3 border-r border-slate-700">Deputation Type</th>
                <th class="px-2.5 py-3 border-r border-slate-700">Receiving Mandal Conf</th>
                <th class="px-2.5 py-3 border-r border-slate-700">Verification</th>
                <th class="px-2.5 py-3">Remarks</th>
              </tr>
            </thead>
            <tbody id="recon-tbody" class="divide-y divide-slate-100">
              <tr><td colspan="22" class="text-center py-12 text-slate-400">Loading Report D (22 Columns)...</td></tr>
            </tbody>
          </table>
        </div>
      </div>

    </div>
  `;
  lucide.createIcons();
  loadReconciliationReportData();
}

async function loadReconciliationReportData() {
  const tbody = document.getElementById("recon-tbody");
  if (!tbody) return;

  try {
    const res = await fetchAPI("/reports/data/D");
    cachedReportDHeaders = res.headers || [];
    cachedReportDRows = res.rows || [];

    filterReconciliationTable();
  } catch (err) {
    console.error("Failed loading report D", err);
    tbody.innerHTML = `<tr><td colspan="22" class="text-center py-8 text-red-500">Error loading Reconciliation Report D.</td></tr>`;
  }
}

function filterReconciliationTable() {
  const tbody = document.getElementById("recon-tbody");
  if (!tbody) return;

  const search = (document.getElementById("recon-search-input")?.value || "").toLowerCase().trim();
  const mandalFilter = (document.getElementById("recon-mandal-filter")?.value || "").toLowerCase().trim();
  const typeFilter = (document.getElementById("recon-type-filter")?.value || "").toLowerCase().trim();
  const statusFilter = (document.getElementById("recon-status-filter")?.value || "").toLowerCase().trim();

  let filtered = cachedReportDRows.filter(row => {
    // Row indices:
    // 0: S.No, 1: Name, 2: ID, 3: Mobile, 4: RegMandal, 5: SalGP, 6: SalMandal,
    // 7: OffDepGP, 8: OffDepMandal, 9: OrderNo, 10: OrderDate, 11: EffDate,
    // 12: ReassignFrom, 13: ReassignTo, 14: ReassignDate,
    // 15: PresGP, 16: PresMandal, 17: ServiceStatus, 18: DepType,
    // 19: MandalConf, 20: VerifStatus, 21: Remarks
    const name = String(row[1] || "").toLowerCase();
    const id = String(row[2] || "").toLowerCase();
    const mobile = String(row[3] || "").toLowerCase();
    const salGp = String(row[5] || "").toLowerCase();
    const salMandal = String(row[6] || "").toLowerCase();
    const presGp = String(row[15] || "").toLowerCase();
    const presMandal = String(row[16] || "").toLowerCase();
    const srvStatus = String(row[17] || "").toLowerCase();
    const depType = String(row[18] || "").toLowerCase();

    if (search) {
      const matchSearch = name.includes(search) || id.includes(search) || mobile.includes(search) || salGp.includes(search) || presGp.includes(search);
      if (!matchSearch) return false;
    }

    if (mandalFilter) {
      const matchMandal = salMandal.includes(mandalFilter) || presMandal.includes(mandalFilter);
      if (!matchMandal) return false;
    }

    if (typeFilter) {
      if (!depType.includes(typeFilter)) return false;
    }

    if (statusFilter) {
      if (!srvStatus.includes(statusFilter)) return false;
    }

    return true;
  });

  const countBadge = document.getElementById("recon-count-display");
  if (countBadge) countBadge.textContent = filtered.length;

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="22" class="text-center py-8 text-slate-400">No records match the active search and filter criteria.</td></tr>`;
    return;
  }

  let rowsHtml = "";
  filtered.forEach((row, idx) => {
    // Highlight working in salary GP vs deputation
    const isOwnGp = String(row[18]).includes("OWN_GP") || String(row[18]).includes("REGULAR");
    const isInternallyReassigned = String(row[13]) !== "N/A";

    const depBadge = isOwnGp
      ? `<span class="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800">REGULAR</span>`
      : `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-900 border border-amber-300">${row[18]}</span>`;

    const statusBadge = row[17] === "WORKING"
      ? `<span class="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800">WORKING</span>`
      : `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-800">${row[17]}</span>`;

    const reassignCell = isInternallyReassigned
      ? `<span class="font-bold text-pink-700">${row[13]}</span>`
      : `<span class="text-slate-400">N/A</span>`;

    rowsHtml += `
      <tr class="hover:bg-slate-50/80">
        <td class="px-2.5 py-2 font-mono text-[10px] text-slate-400">${idx + 1}</td>
        <td class="px-2.5 py-2 font-bold text-slate-900">${row[1]}</td>
        <td class="px-2.5 py-2 font-mono font-bold text-govblue-900">${row[2]}</td>
        <td class="px-2.5 py-2 font-mono text-slate-600">${row[3]}</td>
        <td class="px-2.5 py-2 text-slate-600">${row[4]}</td>
        <td class="px-2.5 py-2 font-semibold text-teal-900">${row[5]}</td>
        <td class="px-2.5 py-2 text-slate-600">${row[6]}</td>
        <td class="px-2.5 py-2 text-slate-800">${row[7]}</td>
        <td class="px-2.5 py-2 text-slate-600">${row[8]}</td>
        <td class="px-2.5 py-2 font-mono text-slate-500">${row[9]}</td>
        <td class="px-2.5 py-2 font-mono text-slate-500">${row[10]}</td>
        <td class="px-2.5 py-2 font-mono text-slate-500">${row[11]}</td>
        <td class="px-2.5 py-2 text-slate-500">${row[12]}</td>
        <td class="px-2.5 py-2">${reassignCell}</td>
        <td class="px-2.5 py-2 font-mono text-slate-500">${row[14]}</td>
        <td class="px-2.5 py-2 font-bold text-indigo-900">${row[15]}</td>
        <td class="px-2.5 py-2 text-slate-600">${row[16]}</td>
        <td class="px-2.5 py-2 text-center">${statusBadge}</td>
        <td class="px-2.5 py-2 text-center">${depBadge}</td>
        <td class="px-2.5 py-2 text-slate-700">${row[19]}</td>
        <td class="px-2.5 py-2 text-slate-700">${row[20]}</td>
        <td class="px-2.5 py-2 text-slate-500 text-[10px] max-w-xs truncate" title="${row[21]}">${row[21]}</td>
      </tr>
    `;
  });
  tbody.innerHTML = rowsHtml;
}

// ==========================================
// 3. EMPLOYEE DATA ENTRY (PRIMARY MODULE - FIELDS 1 TO 8)
// ==========================================
let duplicateCheckTimeout = null;
let currentDuplicateStatus = false;

async function renderEmployeeEntryView() {
  const container = document.getElementById("view-employee-entry");

  // Load GPs of the logged-in Mandal
  let mandalGps = [];
  try {
    mandalGps = await fetchAPI("/panchayats?for_salary_entry=true");
  } catch (e) {
    console.error("Error fetching salary GPs", e);
  }

  let salaryGPOptions = `<option value="">-- Select Salary Claiming GP --</option>`;
  mandalGps.forEach(gp => {
    salaryGPOptions += `<option value="${gp.lgd_code}" data-name="${gp.gp_name}" data-mandal="${gp.mandal_name}" data-mandal-id="${gp.mandal_id}">${gp.gp_name} (LGD: ${gp.lgd_code})</option>`;
  });

  // GPs for same mandal destination
  let sameMandalGPOptions = `<option value="">-- Select Destination GP in Same Mandal --</option>`;
  mandalGps.forEach(gp => {
    sameMandalGPOptions += `<option value="${gp.lgd_code}">${gp.gp_name} (LGD: ${gp.lgd_code})</option>`;
  });

  // Other Mandals in Khammam District
  let otherMandalOptions = `<option value="">-- Select Destination Mandal --</option>`;
  cachedMandals.forEach(m => {
    otherMandalOptions += `<option value="${m.id}">${m.mandal_name} (LGD: ${m.mandal_lgd})</option>`;
  });

  container.innerHTML = `
    <div class="max-w-4xl mx-auto">
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden mb-6">
        
        <!-- Form Header -->
        <div class="bg-govblue-900 text-white p-5 border-b-4 border-amber-500">
          <div class="flex items-center space-x-3">
            <div class="p-2 bg-white/10 rounded-lg">
              <i data-lucide="file-signature" class="w-6 h-6 text-amber-400"></i>
            </div>
            <div>
              <h2 class="text-lg font-bold">Panchayat Secretary Data Entry & Deputation Mapping</h2>
              <p class="text-xs text-slate-300">Official Data Collection Form across Khammam District</p>
            </div>
          </div>
        </div>

        <form id="employee-entry-form" onsubmit="handleEmployeeEntrySubmit(event)" class="p-6 space-y-6 text-xs text-slate-700">

          <!-- DUPLICATE WARNING ALERT BANNER -->
          <div id="duplicate-warning-banner" class="hidden p-4 rounded-xl border-2 border-red-500 bg-red-50 text-red-900 shadow-md">
            <!-- Injected dynamically by real-time duplicate checker -->
          </div>

          <!-- FIELD 1: SALARY-CLAIMING GRAM PANCHAYAT -->
          <div class="p-4 bg-slate-50 rounded-lg border border-slate-200">
            <div class="flex items-center justify-between mb-2">
              <label class="font-bold text-slate-800 text-xs uppercase tracking-wider flex items-center">
                <span class="w-5 h-5 rounded-full bg-govblue-900 text-white flex items-center justify-center text-[10px] mr-1.5 font-mono">1</span>
                FIELD 1: Salary-Claiming Gram Panchayat (Preloaded Master)
              </label>
              <span class="text-[11px] text-rose-600 font-bold">Mandatory</span>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div class="md:col-span-2">
                <select id="entry-salary-gp" required onchange="handleSalaryGPChange(event)" class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800 bg-white">
                  ${salaryGPOptions}
                </select>
                <p class="text-[10px] text-slate-500 mt-1">Users cannot manually modify GP names, LGD codes or Mandal mappings.</p>
              </div>
              <div class="bg-white p-2.5 rounded border border-slate-200">
                <div class="text-[10px] text-slate-400 uppercase font-bold">Auto-Identified Mandal</div>
                <div id="entry-salary-mandal-display" class="font-bold text-govblue-900 text-xs truncate">Select GP first</div>
                <div id="entry-salary-lgd-display" class="text-[10px] text-slate-500 font-mono mt-0.5">LGD Code: -</div>
              </div>
            </div>
          </div>

          <!-- FIELD 2: PANCHAYAT SECRETARY WORKING STATUS -->
          <div class="p-4 bg-slate-50 rounded-lg border border-slate-200">
            <div class="flex items-center justify-between mb-2">
              <label class="font-bold text-slate-800 text-xs uppercase tracking-wider flex items-center">
                <span class="w-5 h-5 rounded-full bg-govblue-900 text-white flex items-center justify-center text-[10px] mr-1.5 font-mono">2</span>
                FIELD 2: Position Availability Status <span class="text-rose-600 ml-1">*</span>
              </label>
              <span class="text-[11px] text-rose-600 font-bold">Mandatory</span>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <select id="entry-gp-working-status" required onchange="handleGPWorkingStatusChange(event)" class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800 bg-white font-semibold text-slate-800">
                  <option value="">-- Select Position Availability Status --</option>
                  <option value="WORKING">Working (Employee Attached)</option>
                  <option value="CLEAR_VACANCY">Clear Vacancy (No Employee Attached)</option>
                </select>
              </div>
              <div id="entry-vacancy-remarks-wrap" class="hidden">
                <input type="text" id="entry-vacancy-remarks" placeholder="Provide vacancy remarks (e.g. Retirement on 31-12-2025, Clear Vacancy)..." class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800">
              </div>
            </div>
            <div id="field2-select-prompt" class="mt-3 p-3 bg-amber-50 rounded-lg border border-amber-200 text-amber-900 text-xs font-medium flex items-center">
              <i data-lucide="alert-circle" class="w-4 h-4 mr-2 text-amber-600 flex-shrink-0"></i>
              Please select Position Availability Status (Working or Clear Vacancy) above to proceed.
            </div>
          </div>

          <!-- EMPLOYEE SPECIFIC FIELDS WRAPPER -->
          <div id="employee-fields-wrapper" class="hidden space-y-6">

            <!-- FIELD 3: EMPLOYEE INFORMATION -->
            <div class="p-4 bg-slate-50 rounded-lg border border-slate-200">
              <div class="flex items-center justify-between mb-2">
                <label class="font-bold text-slate-800 text-xs uppercase tracking-wider flex items-center">
                  <span class="w-5 h-5 rounded-full bg-govblue-900 text-white flex items-center justify-center text-[10px] mr-1.5 font-mono">3</span>
                  FIELD 3: Employee Information (Unique ID & Contact)
                </label>
              </div>
              <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
                <div>
                  <label class="block font-semibold text-slate-700 mb-1">Employee ID <span class="text-rose-600">*</span></label>
                  <div class="relative">
                    <input type="text" id="entry-emp-id" required placeholder="e.g. TS-10029" oninput="handleEmpIdInput(event)" class="w-full p-2 uppercase font-mono font-bold border border-slate-300 rounded focus:ring-2 focus:ring-govblue-800 outline-none">
                    <span id="emp-id-check-spinner" class="hidden absolute right-2.5 top-2.5 text-slate-400">
                      <i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i>
                    </span>
                  </div>
                  <p class="text-[10px] text-slate-500 mt-1">Globally unique ID.</p>
                </div>
                <div>
                  <label class="block font-semibold text-slate-700 mb-1">Employee Name as per IFMIS/SR <span class="text-rose-600">*</span></label>
                  <input type="text" id="entry-emp-name" required placeholder="Full Name as per SR" class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800 outline-none">
                </div>
                <div>
                  <label class="block font-semibold text-slate-700 mb-1">Mobile Number <span class="text-rose-600">*</span></label>
                  <div class="relative">
                    <input type="tel" id="entry-emp-mobile" required pattern="[6-9][0-9]{9}" maxlength="10" placeholder="10-digit Mobile" class="w-full pl-8 p-2 font-mono font-bold border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800 outline-none">
                    <span class="absolute left-2 top-2 text-slate-400 font-bold text-[10px]">+91</span>
                  </div>
                  <p class="text-[10px] text-slate-500 mt-1">Official contact.</p>
                </div>
                <div>
                  <label class="block font-semibold text-slate-700 mb-1">Date of Birth <span class="text-rose-600">*</span></label>
                  <input type="date" id="entry-emp-dob" required class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800 outline-none">
                </div>
              </div>
            </div>

            <!-- FIELD 4: EMPLOYEE SERVICE STATUS & CONDITIONAL DETAILS -->
            <div class="p-4 bg-slate-50 rounded-lg border border-slate-200 space-y-4">
              <div class="flex items-center justify-between">
                <label class="font-bold text-slate-800 text-xs uppercase tracking-wider flex items-center">
                  <span class="w-5 h-5 rounded-full bg-govblue-900 text-white flex items-center justify-center text-[10px] mr-1.5 font-mono">4</span>
                  FIELD 4: Employee Service & Working Status
                </label>
              </div>
              
              <div>
                <label class="block font-semibold text-slate-700 mb-1">Service Status Category <span class="text-rose-600">*</span></label>
                <select id="entry-service-status" required onchange="handleServiceStatusChange(event)" class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800 bg-white font-semibold">
                  <option value="WORKING">Working</option>
                  <option value="SUSPENDED">Suspended</option>
                  <option value="ABSCONDING">Absconding (Unauthorized Absence)</option>
                  <option value="LONG_LEAVE">Long Leave</option>
                  <option value="MEDICAL_LEAVE">Medical Leave</option>
                  <option value="MATERNITY_LEAVE">Maternity Leave</option>
                  <option value="CHILD_CARE_LEAVE">Child Care Leave (CCL)</option>
                  <option value="EARNED_LEAVE">Earned Leave</option>
                  <option value="EXTRAORDINARY_LEAVE">Extraordinary Leave / Leave Without Pay (EOL)</option>
                  <option value="OTHER_APPROVED_LEAVE">Other Approved Leave</option>
                  <option value="OTHER">Other (Mandatory Remarks)</option>
                </select>
              </div>

              <!-- CONDITIONAL SERVICE FIELDS -->
              <div id="service-conditional-fields" class="hidden p-3 bg-white rounded border border-slate-200 space-y-3">
                <div class="font-bold text-govblue-900 text-xs border-b pb-1">Status Proceedings & Additional Details:</div>
                
                <!-- Common Dates & Orders -->
                <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div>
                    <label class="block font-semibold text-slate-700 mb-1">Effective From Date</label>
                    <input type="date" id="entry-status-from" class="w-full p-2 border border-slate-300 rounded">
                  </div>
                  <div>
                    <label id="entry-expected-join-label" class="block font-semibold text-slate-700 mb-1">Date from which Proceeded on Leave / Absconding / Suspended</label>
                    <input type="date" id="entry-expected-join-date" class="w-full p-2 border border-slate-300 rounded">
                  </div>
                  <div>
                    <label class="block font-semibold text-slate-700 mb-1">Proceedings / Order Number</label>
                    <input type="text" id="entry-proc-order-no" placeholder="e.g. ROC/PR/2025/112" class="w-full p-2 border border-slate-300 rounded">
                  </div>
                </div>

                <!-- Suspension Specific -->
                <div id="fields-suspended-specific" class="hidden grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 border-t">
                  <div>
                    <label class="block font-semibold text-slate-700 mb-1">Suspension Order Date</label>
                    <input type="date" id="entry-susp-date" class="w-full p-2 border border-slate-300 rounded">
                  </div>
                  <div>
                    <label class="block font-semibold text-slate-700 mb-1">Revocation Order Details (if any)</label>
                    <input type="text" id="entry-revocation-order" placeholder="Revocation order number if reinstated" class="w-full p-2 border border-slate-300 rounded">
                  </div>
                </div>

                <!-- Absconding Specific -->
                <div id="fields-absconding-specific" class="hidden grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 border-t">
                  <div>
                    <label class="block font-semibold text-slate-700 mb-1">Last Working Date / Date of Absence</label>
                    <input type="date" id="entry-absent-date" class="w-full p-2 border border-slate-300 rounded">
                  </div>
                  <div class="flex items-center pt-5">
                    <input type="checkbox" id="entry-disc-initiated" class="w-4 h-4 text-govblue-900 rounded border-slate-300 mr-2">
                    <label for="entry-disc-initiated" class="font-semibold text-slate-700">Disciplinary Proceedings Initiated?</label>
                  </div>
                </div>

                <div>
                  <label class="block font-semibold text-slate-700 mb-1">Reason / Remarks / Justification</label>
                  <textarea id="entry-status-remarks" rows="2" placeholder="Enter detailed remarks regarding this service status..." class="w-full p-2 border border-slate-300 rounded"></textarea>
                </div>
              </div>
            </div>

            <!-- FIELD 5: WORKING IN SALARY-CLAIMING GP? -->
            <div class="p-4 bg-slate-50 rounded-lg border border-slate-200">
              <div class="flex items-center justify-between mb-2">
                <label class="font-bold text-slate-800 text-xs uppercase tracking-wider flex items-center">
                  <span class="w-5 h-5 rounded-full bg-govblue-900 text-white flex items-center justify-center text-[10px] mr-1.5 font-mono">5</span>
                  FIELD 5: Working in Salary-Claiming GP? <span class="text-rose-600 ml-1">*</span>
                </label>
                <span class="text-[11px] text-rose-600 font-bold">Mandatory</span>
              </div>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-3 items-center">
                <div>
                  <select id="entry-is-own-gp" required onchange="handleIsOwnGPChange(event)" class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800 bg-white font-bold text-slate-800">
                    <option value="">-- Select Yes or No --</option>
                    <option value="YES">YES - Working in own Salary-Claiming GP</option>
                    <option value="NO">NO - Deputed to another GP / Mandal / District / Department</option>
                  </select>
                </div>
                <div class="text-[11px] text-slate-500">
                  If YES: Posting Type is automatically mapped to own GP. If NO: Deputation details below are mandatory.
                </div>
              </div>
            </div>

            <!-- FIELD 6: DEPUTATION DETAILS (Conditional when is_own_gp is NO) -->
            <div id="deputation-section" class="hidden p-4 bg-slate-50 rounded-lg border border-slate-200 space-y-4">
              <div class="flex items-center justify-between">
                <label class="font-bold text-slate-800 text-xs uppercase tracking-wider flex items-center">
                  <span class="w-5 h-5 rounded-full bg-govblue-900 text-white flex items-center justify-center text-[10px] mr-1.5 font-mono">6</span>
                  FIELD 6: Deputation Location Details <span class="text-rose-600 ml-1">*</span>
                </label>
                <span class="text-[11px] text-rose-600 font-bold">Mandatory when deputed</span>
              </div>

              <div>
                <label class="block font-semibold text-slate-700 mb-1">Deputation Scope / Type <span class="text-rose-600">*</span></label>
                <select id="entry-dep-type" onchange="handleDepTypeChange(event)" class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800 bg-white font-semibold text-slate-800">
                  <option value="WITHIN_MANDAL">1. Within the Same Mandal</option>
                  <option value="ANOTHER_MANDAL">2. Another Mandal within Khammam District</option>
                  <option value="OTHER_DISTRICT">3. Other District (Outside Khammam)</option>
                  <option value="OTHER_DEPARTMENT">4. Other Department</option>
                </select>
              </div>

              <!-- 1. Within Same Mandal -->
              <div id="dep-same-mandal-wrap" class="space-y-3 p-3 bg-white rounded border border-slate-200">
                <div class="font-bold text-govblue-900 text-xs border-b pb-1">Destination Gram Panchayat (Same Mandal):</div>
                <div>
                  <label class="block font-semibold text-slate-700 mb-1">Destination Gram Panchayat in Mandal <span class="text-rose-600">*</span></label>
                  <select id="entry-dest-gp-same-mandal" class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800 bg-white font-semibold">
                    ${sameMandalGPOptions}
                  </select>
                </div>
              </div>

              <!-- 2. Another Mandal within Khammam District -->
              <div id="dep-other-mandal-wrap" class="hidden space-y-3 p-3 bg-white rounded border border-slate-200">
                <div class="font-bold text-govblue-900 text-xs border-b pb-1">Destination in Another Mandal (Khammam District):</div>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label class="block font-semibold text-slate-700 mb-1">Destination Mandal Name <span class="text-rose-600">*</span></label>
                    <select id="entry-dest-other-mandal" onchange="handleDestOtherMandalChange(event)" class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800 bg-white font-semibold">
                      ${otherMandalOptions}
                    </select>
                  </div>
                  <div>
                    <label class="block font-semibold text-slate-700 mb-1">Destination Gram Panchayat <span class="text-rose-600">*</span></label>
                    <select id="entry-dest-gp-other-mandal" class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800 bg-white font-semibold">
                      <option value="">-- Select Destination Mandal First --</option>
                    </select>
                  </div>
                </div>
              </div>

              <!-- 3. Other District Deputation -->
              <div id="dep-other-district-wrap" class="hidden space-y-3 p-3 bg-white rounded border border-slate-200">
                <div class="font-bold text-govblue-900 text-xs border-b pb-1">External District Destination Details:</div>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label class="block font-semibold text-slate-700 mb-1">District Name <span class="text-rose-600">*</span></label>
                    <input type="text" id="entry-ext-district" placeholder="e.g. Suryapet, Nalgonda, Mahabubabad" class="w-full p-2 border border-slate-300 rounded font-semibold">
                  </div>
                  <div>
                    <label class="block font-semibold text-slate-700 mb-1">Mandal Name</label>
                    <input type="text" id="entry-ext-mandal" placeholder="e.g. Munagala" class="w-full p-2 border border-slate-300 rounded">
                  </div>
                  <div>
                    <label class="block font-semibold text-slate-700 mb-1">Destination GP / Office Name</label>
                    <input type="text" id="entry-ext-office" placeholder="e.g. Gram Panchayat Office / MPDO Office" class="w-full p-2 border border-slate-300 rounded">
                  </div>
                  <div>
                    <label class="block font-semibold text-slate-700 mb-1">External LGD Code (if available)</label>
                    <input type="text" id="entry-ext-lgd" placeholder="External LGD if known" class="w-full p-2 border border-slate-300 rounded font-mono">
                  </div>
                </div>
              </div>

              <!-- 4. Other Department Deputation -->
              <div id="dep-other-dept-wrap" class="hidden space-y-3 p-3 bg-white rounded border border-slate-200">
                <div class="font-bold text-govblue-900 text-xs border-b pb-1">Other Department Deputation Details:</div>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label class="block font-semibold text-slate-700 mb-1">Department Name <span class="text-rose-600">*</span></label>
                    <input type="text" id="entry-ext-department" placeholder="e.g. Revenue (Tahsildar Office), DRDO, Zilla Praja Parishad, Education, Health" class="w-full p-2 border border-slate-300 rounded font-semibold">
                  </div>
                  <div>
                    <label class="block font-semibold text-slate-700 mb-1">Designation / Post in Department</label>
                    <input type="text" id="entry-ext-dept-post" placeholder="e.g. Junior Assistant, Field Supervisor" class="w-full p-2 border border-slate-300 rounded">
                  </div>
                  <div class="md:col-span-2">
                    <label class="block font-semibold text-slate-700 mb-1">Office Name & Location / Address</label>
                    <input type="text" id="entry-ext-dept-location" placeholder="e.g. Collectorate Complex, Khammam / O/o Tahsildar Enkoor" class="w-full p-2 border border-slate-300 rounded">
                  </div>
                </div>
              </div>

            </div>

          </div>

          <!-- SUBMIT BUTTONS -->
          <div class="flex justify-end space-x-3 pt-3">
            <button type="button" onclick="navigate('dashboard')" class="px-4 py-2 border border-slate-300 text-slate-700 rounded font-semibold hover:bg-slate-50">Cancel</button>
            <button type="submit" id="btn-submit-employee" class="px-6 py-2 bg-govblue-900 hover:bg-govblue-800 text-white rounded font-bold shadow flex items-center">
              <i data-lucide="check-circle-2" class="w-4 h-4 mr-2"></i>
              <span>Final Submit Employee Record</span>
            </button>
          </div>

        </form>

      </div>
    </div>
  `;
  lucide.createIcons();
}

function handleSalaryGPChange(e) {
  const select = e.target;
  const opt = select.options[select.selectedIndex];
  const mandalDisplay = document.getElementById("entry-salary-mandal-display");
  const lgdDisplay = document.getElementById("entry-salary-lgd-display");
  
  if (opt && opt.value) {
    mandalDisplay.textContent = opt.getAttribute("data-mandal");
    lgdDisplay.textContent = `LGD Code: ${opt.value}`;
  } else {
    mandalDisplay.textContent = "Select GP first";
    lgdDisplay.textContent = "LGD Code: -";
  }
}

function handleGPWorkingStatusChange(e) {
  const status = e.target.value;
  const wrap = document.getElementById("entry-vacancy-remarks-wrap");
  const prompt = document.getElementById("field2-select-prompt");
  const empWrapper = document.getElementById("employee-fields-wrapper");
  const submitBtn = document.getElementById("btn-submit-employee");

  if (!status) {
    if (prompt) prompt.classList.remove("hidden");
    if (wrap) wrap.classList.add("hidden");
    if (empWrapper) empWrapper.classList.add("hidden");
    if (submitBtn) {
      submitBtn.innerHTML = `<i data-lucide="check-circle-2" class="w-4 h-4 mr-2"></i><span>Final Submit Employee Record</span>`;
      lucide.createIcons();
    }
  } else if (status === "CLEAR_VACANCY") {
    if (prompt) prompt.classList.add("hidden");
    if (wrap) wrap.classList.remove("hidden");
    if (empWrapper) empWrapper.classList.add("hidden");
    if (submitBtn) {
      submitBtn.innerHTML = `<i data-lucide="shield-alert" class="w-4 h-4 mr-2"></i><span>Record Clear Vacancy for GP</span>`;
      lucide.createIcons();
    }
  } else {
    // WORKING
    if (prompt) prompt.classList.add("hidden");
    if (wrap) wrap.classList.add("hidden");
    if (empWrapper) empWrapper.classList.remove("hidden");
    if (submitBtn) {
      submitBtn.innerHTML = `<i data-lucide="check-circle-2" class="w-4 h-4 mr-2"></i><span>Final Submit Employee Record</span>`;
      lucide.createIcons();
    }
  }
}

function handleEmpIdInput(e) {
  const empId = e.target.value.trim();
  const spinner = document.getElementById("emp-id-check-spinner");
  const warningBanner = document.getElementById("duplicate-warning-banner");
  const submitBtn = document.getElementById("btn-submit-employee");

  clearTimeout(duplicateCheckTimeout);
  if (!empId) {
    warningBanner.classList.add("hidden");
    currentDuplicateStatus = false;
    submitBtn.disabled = false;
    return;
  }

  spinner.classList.remove("hidden");

  // SECTION 7: Real-time global employee check
  duplicateCheckTimeout = setTimeout(async () => {
    try {
      const res = await fetchAPI(`/employees/check-id?employee_id=${encodeURIComponent(empId)}`);
      spinner.classList.add("hidden");

      if (res.is_duplicate) {
        currentDuplicateStatus = true;
        submitBtn.disabled = true;
        const r = res.existing_record;
        
        warningBanner.innerHTML = `
          <div class="flex items-start">
            <i data-lucide="alert-octagon" class="w-6 h-6 mr-3 text-red-600 flex-shrink-0 mt-0.5"></i>
            <div class="flex-1">
              <h4 class="font-bold text-red-900 text-sm tracking-tight uppercase">EMPLOYEE ALREADY EXISTS!</h4>
              <p class="text-xs text-red-800 mt-0.5 leading-relaxed">
                This Employee ID is already registered in Details of Panchayat Secretaries Working in Khammam District. Duplicate employee registration is strictly prohibited.
              </p>
              
              <div class="mt-3 bg-white p-3 rounded-lg border border-red-300 text-slate-800 grid grid-cols-2 gap-2 text-[11px]">
                <div><strong>Employee Name:</strong> ${r.name_ifmis}</div>
                <div><strong>Employee ID:</strong> <span class="font-mono font-bold">${r.employee_id}</span></div>
                <div><strong>Salary Claiming GP:</strong> ${r.salary_gp_name}</div>
                <div><strong>Salary Claiming Mandal:</strong> ${r.salary_mandal_name}</div>
                <div><strong>Current Working GP:</strong> ${r.current_working_gp}</div>
                <div><strong>Current Working Mandal:</strong> ${r.current_working_mandal}</div>
                <div><strong>Service Status:</strong> <span class="font-bold text-red-700">${r.service_status}</span></div>
                <div><strong>Verification Status:</strong> ${r.verification_status}</div>
              </div>
            </div>
          </div>
        `;
        warningBanner.classList.remove("hidden");
        lucide.createIcons();
      } else {
        currentDuplicateStatus = false;
        submitBtn.disabled = false;
        warningBanner.classList.add("hidden");
      }
    } catch (err) {
      spinner.classList.add("hidden");
    }
  }, 400);
}

function handleIsOwnGPChange(e) {
  const isOwn = e.target.value === "NO";
  const depSection = document.getElementById("deputation-section");
  if (depSection) {
    if (isOwn) {
      depSection.classList.remove("hidden");
    } else {
      depSection.classList.add("hidden");
    }
  }
}

function handleServiceStatusChange(e) {
  const status = e.target.value;
  const condFields = document.getElementById("service-conditional-fields");
  const suspSpecific = document.getElementById("fields-suspended-specific");
  const absSpecific = document.getElementById("fields-absconding-specific");
  const dateLabel = document.getElementById("entry-expected-join-label");

  if (status === "WORKING") {
    condFields.classList.add("hidden");
  } else {
    condFields.classList.remove("hidden");
    if (status === "SUSPENDED") {
      suspSpecific.classList.remove("hidden");
      absSpecific.classList.add("hidden");
      if (dateLabel) dateLabel.textContent = "Date from which Suspended";
    } else if (status === "ABSCONDING") {
      suspSpecific.classList.add("hidden");
      absSpecific.classList.remove("hidden");
      if (dateLabel) dateLabel.textContent = "Date from which Absconding";
    } else if (status === "MEDICAL_LEAVE") {
      suspSpecific.classList.add("hidden");
      absSpecific.classList.add("hidden");
      if (dateLabel) dateLabel.textContent = "Date from which Proceeded on Medical Leave";
    } else if (status === "MATERNITY_LEAVE") {
      suspSpecific.classList.add("hidden");
      absSpecific.classList.add("hidden");
      if (dateLabel) dateLabel.textContent = "Date from which Proceeded on Maternity Leave";
    } else if (status === "CHILD_CARE_LEAVE") {
      suspSpecific.classList.add("hidden");
      absSpecific.classList.add("hidden");
      if (dateLabel) dateLabel.textContent = "Date from which Proceeded on Child Care Leave";
    } else if (status === "LONG_LEAVE") {
      suspSpecific.classList.add("hidden");
      absSpecific.classList.add("hidden");
      if (dateLabel) dateLabel.textContent = "Date from which Proceeded on Long Leave";
    } else if (status === "EARNED_LEAVE") {
      suspSpecific.classList.add("hidden");
      absSpecific.classList.add("hidden");
      if (dateLabel) dateLabel.textContent = "Date from which Proceeded on Earned Leave";
    } else if (status === "EXTRAORDINARY_LEAVE") {
      suspSpecific.classList.add("hidden");
      absSpecific.classList.add("hidden");
      if (dateLabel) dateLabel.textContent = "Date from which Proceeded on Leave Without Pay (EOL)";
    } else {
      suspSpecific.classList.add("hidden");
      absSpecific.classList.add("hidden");
      if (dateLabel) dateLabel.textContent = "Date from which Proceeded on Leave";
    }
  }
}

function handleDepTypeChange(e) {
  const type = e.target.value;
  const sameMandalWrap = document.getElementById("dep-same-mandal-wrap");
  const otherMandalWrap = document.getElementById("dep-other-mandal-wrap");
  const otherDistrictWrap = document.getElementById("dep-other-district-wrap");
  const otherDeptWrap = document.getElementById("dep-other-dept-wrap");

  if (sameMandalWrap) sameMandalWrap.classList.add("hidden");
  if (otherMandalWrap) otherMandalWrap.classList.add("hidden");
  if (otherDistrictWrap) otherDistrictWrap.classList.add("hidden");
  if (otherDeptWrap) otherDeptWrap.classList.add("hidden");

  if (type === "WITHIN_MANDAL") {
    if (sameMandalWrap) sameMandalWrap.classList.remove("hidden");
  } else if (type === "ANOTHER_MANDAL") {
    if (otherMandalWrap) otherMandalWrap.classList.remove("hidden");
  } else if (type === "OTHER_DISTRICT") {
    if (otherDistrictWrap) otherDistrictWrap.classList.remove("hidden");
  } else if (type === "OTHER_DEPARTMENT") {
    if (otherDeptWrap) otherDeptWrap.classList.remove("hidden");
  }
}

function handleDestOtherMandalChange(e) {
  const mandalId = parseInt(e.target.value);
  const gpSelect = document.getElementById("entry-dest-gp-other-mandal");
  if (!gpSelect) return;

  if (!mandalId) {
    gpSelect.innerHTML = `<option value="">-- Select Destination Mandal First --</option>`;
    return;
  }

  const matchingGPs = centralizedPanchayats.filter(gp => gp.mandal_id === mandalId);
  let opts = `<option value="">-- Select Destination GP (${matchingGPs.length} GPs in Mandal) --</option>`;
  matchingGPs.forEach(gp => {
    opts += `<option value="${gp.lgd_code}">${gp.gp_name} (LGD: ${gp.lgd_code})</option>`;
  });
  gpSelect.innerHTML = opts;
}

async function handleEmployeeEntrySubmit(e) {
  e.preventDefault();

  const salaryGPLgd = parseInt(document.getElementById("entry-salary-gp").value);
  if (!salaryGPLgd) {
    alert("Please select a Salary-Claiming Gram Panchayat.");
    document.getElementById("entry-salary-gp").focus();
    return;
  }

  const workingStatus = document.getElementById("entry-gp-working-status").value;
  if (!workingStatus) {
    alert("FIELD 2: Position Availability Status is mandatory. Please select whether this GP has an employee Working or is a Clear Vacancy.");
    document.getElementById("entry-gp-working-status").focus();
    return;
  }

  if (workingStatus === "CLEAR_VACANCY") {
    // Submit as Clear Vacancy
    try {
      await fetchAPI(`/panchayats/${salaryGPLgd}/vacancy`, {
        method: "POST",
        body: JSON.stringify({
          gp_lgd: salaryGPLgd,
          is_clear_vacancy: true,
          vacancy_remarks: document.getElementById("entry-vacancy-remarks").value || "Clear vacancy submitted by Mandal"
        })
      });
      alert("Clear Vacancy recorded successfully for the Gram Panchayat.");
      navigate("gp-master");
    } catch (err) {
      alert("Error: " + (err.detail || err.message));
    }
    return;
  }

  // Position Availability Status is WORKING
  if (currentDuplicateStatus) {
    alert("Cannot submit: Employee ID already registered in the district database.");
    return;
  }

  // Employee details validation
  const empId = document.getElementById("entry-emp-id").value.trim();
  const empName = document.getElementById("entry-emp-name").value.trim();
  const mobile = document.getElementById("entry-emp-mobile")?.value.trim() || null;
  const dob = document.getElementById("entry-emp-dob").value;

  if (!empId) {
    alert("Please enter Employee ID.");
    document.getElementById("entry-emp-id").focus();
    return;
  }
  if (!empName) {
    alert("Please enter Employee Name as per IFMIS/SR.");
    document.getElementById("entry-emp-name").focus();
    return;
  }
  if (!mobile || !/^[6-9]\d{9}$/.test(mobile)) {
    alert("Please enter a valid 10-digit Mobile Number starting with 6, 7, 8, or 9.");
    document.getElementById("entry-emp-mobile")?.focus();
    return;
  }
  if (!dob) {
    alert("Please select Employee Date of Birth.");
    document.getElementById("entry-emp-dob").focus();
    return;
  }

  // Field 4: Service status
  const serviceStatus = document.getElementById("entry-service-status").value;

  // Field 5: Working in salary GP?
  const isOwnGPVal = document.getElementById("entry-is-own-gp").value;
  if (!isOwnGPVal) {
    alert("FIELD 5: Please select whether the employee is working in their Salary-Claiming GP (YES or NO).");
    document.getElementById("entry-is-own-gp").focus();
    return;
  }

  const isOwnGP = (isOwnGPVal === "YES");

  let postingType = "OWN_GP";
  let destGPLgd = null;
  let extDist = null;
  let extMandal = null;
  let extOffice = null;
  let extDept = null;
  let extLgd = null;

  if (isOwnGP) {
    postingType = "OWN_GP";
    destGPLgd = salaryGPLgd;
  } else {
    // Deputation details are mandatory
    postingType = document.getElementById("entry-dep-type").value;
    if (!postingType) {
      alert("Please select a Deputation Type.");
      return;
    }

    if (postingType === "WITHIN_MANDAL") {
      const sameGPVal = document.getElementById("entry-dest-gp-same-mandal").value;
      if (!sameGPVal) {
        alert("Please select Destination Gram Panchayat within the Same Mandal.");
        document.getElementById("entry-dest-gp-same-mandal").focus();
        return;
      }
      destGPLgd = parseInt(sameGPVal);
    } else if (postingType === "ANOTHER_MANDAL") {
      const otherMandalVal = document.getElementById("entry-dest-other-mandal").value;
      if (!otherMandalVal) {
        alert("Please select Destination Mandal in Khammam District.");
        document.getElementById("entry-dest-other-mandal").focus();
        return;
      }
      const otherGPVal = document.getElementById("entry-dest-gp-other-mandal").value;
      if (!otherGPVal) {
        alert("Please select Destination Gram Panchayat in the selected Mandal.");
        document.getElementById("entry-dest-gp-other-mandal").focus();
        return;
      }
      destGPLgd = parseInt(otherGPVal);
    } else if (postingType === "OTHER_DISTRICT") {
      extDist = document.getElementById("entry-ext-district").value.trim();
      if (!extDist) {
        alert("District Name is mandatory for Other District deputation.");
        document.getElementById("entry-ext-district").focus();
        return;
      }
      extMandal = document.getElementById("entry-ext-mandal").value.trim() || null;
      extOffice = document.getElementById("entry-ext-office").value.trim() || null;
      extLgd = document.getElementById("entry-ext-lgd").value.trim() || null;
    } else if (postingType === "OTHER_DEPARTMENT") {
      extDept = document.getElementById("entry-ext-department").value.trim();
      if (!extDept) {
        alert("Department Name is mandatory for Other Department deputation.");
        document.getElementById("entry-ext-department").focus();
        return;
      }
      const postName = document.getElementById("entry-ext-dept-post").value.trim();
      const locName = document.getElementById("entry-ext-dept-location").value.trim();
      extOffice = [postName, locName].filter(Boolean).join(" - ") || null;
      extDist = "Telangana";
    }
  }

  const payload = {
    employee_id: empId,
    name_ifmis: empName,
    mobile_number: mobile,
    dob: dob,
    salary_gp_lgd: salaryGPLgd,
    is_working_in_salary_gp: isOwnGP,
    service_status: serviceStatus,
    status_effective_from: document.getElementById("entry-status-from")?.value || null,
    expected_joining_date: document.getElementById("entry-expected-join-date")?.value || null,
    proceedings_order_no: document.getElementById("entry-proc-order-no")?.value || null,
    suspension_order_no: document.getElementById("entry-proc-order-no")?.value || null,
    suspension_order_date: document.getElementById("entry-susp-date")?.value || null,
    revocation_order_no: document.getElementById("entry-revocation-order")?.value || null,
    last_working_date: document.getElementById("entry-absent-date")?.value || null,
    disciplinary_initiated: document.getElementById("entry-disc-initiated")?.checked || false,
    reason_remarks: document.getElementById("entry-status-remarks")?.value || null,
    posting_type: postingType,
    actual_working_gp_lgd: destGPLgd,
    external_district_name: extDist,
    external_mandal_name: extMandal,
    external_gp_or_office_name: extOffice,
    external_department_name: extDept,
    external_lgd_code: extLgd,
    declaration_agreed: true
  };

  try {
    const res = await fetchAPI("/employees", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    alert(`Success: ${res.message}`);
    navigate("employee-master");
  } catch (err) {
    alert("Submission error: " + (err.detail || err.message));
  }
}

// ==========================================
// 4. EMPLOYEE MASTER & SEARCH VIEW
// ==========================================
let empMasterSearch = "";
let empMasterMandal = "";
let empMasterStatus = "";
let empMasterPosting = "";
let empMasterPage = 0;

async function renderEmployeeMasterView() {
  const container = document.getElementById("view-employee-master");

  let mandalOptions = `<option value="">All Mandals</option>`;
  cachedMandals.forEach(m => {
    mandalOptions += `<option value="${m.id}">${m.mandal_name}</option>`;
  });

  container.innerHTML = `
    <div class="flex justify-between items-center mb-5">
      <div>
        <h2 class="text-xl font-bold text-slate-900">District Employee Master Directory</h2>
        <p class="text-xs text-slate-500">Master database of all registered Panchayat Secretaries in Khammam District</p>
      </div>
      <div>
        <button onclick="navigate('employee-entry')" class="px-3.5 py-1.5 bg-govblue-900 hover:bg-govblue-800 text-white rounded text-xs font-semibold flex items-center shadow">
          <i data-lucide="user-plus" class="w-3.5 h-3.5 mr-1.5"></i> Add New Employee
        </button>
      </div>
    </div>

    <!-- Filters -->
    <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm mb-5 grid grid-cols-1 md:grid-cols-4 gap-3 items-center">
      <div>
        <label class="block text-[10px] font-bold text-slate-500 uppercase mb-1">Search Employee / GP</label>
        <input type="text" id="emp-search-input" value="${empMasterSearch}" placeholder="Search ID, name, GP..." oninput="handleEmpSearchChange(event)" class="w-full p-1.5 text-xs border border-slate-300 rounded outline-none">
      </div>
      <div>
        <label class="block text-[10px] font-bold text-slate-500 uppercase mb-1">Mandal Filter</label>
        <select id="emp-mandal-select" onchange="handleEmpMandalChange(event)" class="w-full p-1.5 text-xs border border-slate-300 rounded outline-none bg-white">
          ${mandalOptions}
        </select>
      </div>
      <div>
        <label class="block text-[10px] font-bold text-slate-500 uppercase mb-1">Service Status</label>
        <select id="emp-status-select" onchange="handleEmpStatusFilterChange(event)" class="w-full p-1.5 text-xs border border-slate-300 rounded outline-none bg-white">
          <option value="">All Statuses</option>
          <option value="WORKING">Working (Regular)</option>
          <option value="SUSPENDED">Suspended</option>
          <option value="ABSCONDING">Absconding</option>
          <option value="LONG_LEAVE">Long Leave</option>
          <option value="MEDICAL_LEAVE">Medical Leave</option>
          <option value="MATERNITY_LEAVE">Maternity Leave</option>
        </select>
      </div>
      <div>
        <label class="block text-[10px] font-bold text-slate-500 uppercase mb-1">Posting Type</label>
        <select id="emp-posting-select" onchange="handleEmpPostingFilterChange(event)" class="w-full p-1.5 text-xs border border-slate-300 rounded outline-none bg-white">
          <option value="">All Postings</option>
          <option value="OWN_GP">Own Salary GP</option>
          <option value="WITHIN_MANDAL">Within Same Mandal</option>
          <option value="ANOTHER_MANDAL">Another Mandal</option>
          <option value="OTHER_DISTRICT">Other District</option>
        </select>
      </div>
    </div>

    <!-- Table -->
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs text-slate-700">
          <thead class="bg-slate-50 border-b border-slate-200 text-[11px] font-bold text-slate-600 uppercase tracking-wider">
            <tr>
              <th class="px-3.5 py-3">#</th>
              <th class="px-3.5 py-3">Employee ID</th>
              <th class="px-3.5 py-3">Employee Name</th>
              <th class="px-3.5 py-3">Mobile No</th>
              <th class="px-3.5 py-3">Salary Claiming GP</th>
              <th class="px-3.5 py-3">Salary Mandal</th>
              <th class="px-3.5 py-3">Actual Working Location</th>
              <th class="px-3.5 py-3">Posting Type</th>
              <th class="px-3.5 py-3">Service Status</th>
              <th class="px-3.5 py-3">Verification</th>
              <th class="px-3.5 py-3 text-right">Profile</th>
            </tr>
          </thead>
          <tbody id="emp-master-tbody" class="divide-y divide-slate-100">
            <tr><td colspan="10" class="text-center py-8 text-slate-400">Loading employees...</td></tr>
          </tbody>
        </table>
      </div>
      <div class="p-3.5 bg-slate-50 border-t border-slate-200 flex justify-between items-center text-xs">
        <span id="emp-pagination-info" class="text-slate-500">Showing records...</span>
        <div class="flex space-x-1.5">
          <button id="emp-btn-prev" onclick="prevEmpPage()" class="px-2.5 py-1 bg-white border border-slate-300 rounded hover:bg-slate-100 disabled:opacity-50">Previous</button>
          <button id="emp-btn-next" onclick="nextEmpPage()" class="px-2.5 py-1 bg-white border border-slate-300 rounded hover:bg-slate-100 disabled:opacity-50">Next</button>
        </div>
      </div>
    </div>
  `;
  lucide.createIcons();
  loadEmployeeMasterData();
}

function handleEmpSearchChange(e) {
  empMasterSearch = e.target.value;
  empMasterPage = 0;
  loadEmployeeMasterData();
}

function handleEmpMandalChange(e) {
  empMasterMandal = e.target.value;
  empMasterPage = 0;
  loadEmployeeMasterData();
}

function handleEmpStatusFilterChange(e) {
  empMasterStatus = e.target.value;
  empMasterPage = 0;
  loadEmployeeMasterData();
}

function handleEmpPostingFilterChange(e) {
  empMasterPosting = e.target.value;
  empMasterPage = 0;
  loadEmployeeMasterData();
}

function prevEmpPage() {
  if (empMasterPage > 0) {
    empMasterPage--;
    loadEmployeeMasterData();
  }
}

function nextEmpPage() {
  empMasterPage++;
  loadEmployeeMasterData();
}

async function loadEmployeeMasterData() {
  const tbody = document.getElementById("emp-master-tbody");
  if (!tbody) return;

  const skip = empMasterPage * 25;
  let url = `/employees?skip=${skip}&limit=25`;
  if (empMasterSearch) url += `&search=${encodeURIComponent(empMasterSearch)}`;
  if (empMasterMandal) url += `&mandal_id=${empMasterMandal}`;
  if (empMasterStatus) url += `&service_status=${empMasterStatus}`;
  if (empMasterPosting) url += `&posting_type=${empMasterPosting}`;

  try {
    const data = await fetchAPI(url);
    const items = data.items || [];
    const total = data.total || 0;

    document.getElementById("emp-pagination-info").textContent = `Showing ${items.length > 0 ? skip + 1 : 0} to ${skip + items.length} of ${total} employees`;
    document.getElementById("emp-btn-prev").disabled = empMasterPage === 0;
    document.getElementById("emp-btn-next").disabled = (skip + items.length) >= total;

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" class="text-center py-8 text-slate-400">No employee records found.</td></tr>`;
      return;
    }

    let rowsHtml = "";
    items.forEach((e, idx) => {
      let statusBadge = `<span class="px-2 py-0.5 rounded text-[10px] font-bold ${e.service_status === 'WORKING' ? 'badge-working' : (e.service_status === 'SUSPENDED' ? 'badge-suspended' : (e.service_status === 'ABSCONDING' ? 'badge-absconding' : 'badge-leave'))}">${e.service_status}</span>`;
      let verifBadge = `<span class="px-1.5 py-0.5 rounded text-[10px] font-medium ${e.verification_status === 'VERIFIED_BOTH' ? 'bg-green-100 text-green-800' : (e.verification_status === 'PENDING' ? 'bg-amber-100 text-amber-800' : 'bg-rose-100 text-rose-800')}">${e.verification_status}</span>`;

      rowsHtml += `
        <tr class="table-hover-row">
          <td class="px-3.5 py-2.5 text-slate-400 font-mono text-[11px]">${skip + idx + 1}</td>
          <td class="px-3.5 py-2.5 font-bold font-mono text-slate-900">${e.employee_id}</td>
          <td class="px-3.5 py-2.5 font-semibold text-slate-800">${e.name_ifmis}</td>
          <td class="px-3.5 py-2.5 font-mono text-slate-600">${e.mobile_number || 'N/A'}</td>
          <td class="px-3.5 py-2.5">${e.salary_gp_name}</td>
          <td class="px-3.5 py-2.5">${e.salary_mandal_name}</td>
          <td class="px-3.5 py-2.5 font-medium text-slate-900">${e.actual_working_gp_name} (${e.actual_working_mandal_name})</td>
          <td class="px-3.5 py-2.5 text-slate-600">${e.posting_type}</td>
          <td class="px-3.5 py-2.5">${statusBadge}</td>
          <td class="px-3.5 py-2.5">${verifBadge}</td>
          <td class="px-3.5 py-2.5 text-right">
            <button onclick="viewEmployeeProfile('${e.employee_id}')" class="px-2 py-1 bg-govblue-50 text-govblue-900 hover:bg-govblue-100 rounded text-[11px] font-semibold">Profile</button>
          </td>
        </tr>
      `;
    });
    tbody.innerHTML = rowsHtml;
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="10" class="text-center py-6 text-red-500">Failed to load employees: ${err.detail || err.message}</td></tr>`;
  }
}

async function viewEmployeeProfile(empId) {
  try {
    const p = await fetchAPI(`/employees/${empId}`);
    
    // Status badges
    const statusBadge = `<span class="px-2.5 py-1 rounded text-xs font-bold ${p.current_service_status.service_status === 'WORKING' ? 'badge-working' : 'badge-suspended'}">${p.current_service_status.service_status}</span>`;

    let postingHistHtml = "";
    p.posting_history.forEach(ph => {
      postingHistHtml += `
        <div class="p-3 bg-white rounded border border-slate-200 text-xs flex justify-between items-start mb-2">
          <div>
            <div class="font-bold text-slate-800">${ph.working_gp_name} (${ph.working_mandal_name || ph.external_district})</div>
            <div class="text-[11px] text-slate-500">Order: ${ph.order_no || 'N/A'} | Date: ${ph.order_date || 'N/A'}</div>
          </div>
          <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold ${ph.is_current ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-500'}">${ph.is_current ? 'CURRENT' : 'HISTORICAL'}</span>
        </div>
      `;
    });

    let statusHistHtml = "";
    p.status_history.forEach(sh => {
      statusHistHtml += `
        <div class="p-3 bg-white rounded border border-slate-200 text-xs flex justify-between items-start mb-2">
          <div>
            <div class="font-bold text-slate-800">${sh.service_status}</div>
            <div class="text-[11px] text-slate-500">Effective: ${sh.effective_from || 'N/A'} | Expected Join: ${sh.expected_joining_date || 'N/A'}</div>
            ${sh.reason_remarks ? `<div class="text-[11px] text-slate-600 mt-1 italic">${sh.reason_remarks}</div>` : ''}
          </div>
          <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold ${sh.is_current ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-500'}">${sh.is_current ? 'CURRENT' : 'HISTORICAL'}</span>
        </div>
      `;
    });

    const bodyHtml = `
      <!-- Prominent Header Banner as per Section 9 Specs -->
      <div class="bg-govblue-900 text-white p-4 rounded-xl shadow mb-5 space-y-2">
        <div class="flex justify-between items-start">
          <div>
            <div class="text-xs text-amber-300 font-bold uppercase tracking-wider">EMPLOYEE PROFILE</div>
            <div class="text-lg font-bold">${p.name_ifmis}</div>
            <div class="font-mono text-xs text-slate-300">Employee ID: <strong class="text-white">${p.employee_id}</strong> | Mobile: <a href="tel:${p.mobile_number}" class="text-amber-300 hover:underline font-bold">${p.mobile_number || 'N/A'}</a> | DOB: ${p.dob}</div>
          </div>
          <div>${statusBadge}</div>
        </div>
        
        <div class="grid grid-cols-2 gap-3 pt-3 border-t border-white/20 text-xs">
          <div class="bg-govblue-950/60 p-2.5 rounded border border-white/10">
            <div class="text-[10px] text-slate-400 font-bold uppercase">SALARY CLAIMED FROM:</div>
            <div class="text-sm font-bold text-amber-300">${p.salary_gp_name}</div>
            <div class="text-[10px] text-slate-300">Mandal: ${p.salary_mandal_name}</div>
          </div>
          <div class="bg-govblue-950/60 p-2.5 rounded border border-white/10">
            <div class="text-[10px] text-slate-400 font-bold uppercase">ACTUALLY WORKING AT:</div>
            <div class="text-sm font-bold text-emerald-300">${p.current_posting.actual_working_gp_name}</div>
            <div class="text-[10px] text-slate-300">Mandal / Dist: ${p.current_posting.actual_working_mandal_name || p.current_posting.external_district_name}</div>
          </div>
        </div>
      </div>

      <!-- Deputation & Verification Badges -->
      <div class="grid grid-cols-3 gap-3 mb-5 text-xs text-center">
        <div class="p-2.5 bg-slate-50 border rounded">
          <div class="text-[10px] text-slate-400 font-bold uppercase">Posting Type</div>
          <div class="font-bold text-slate-800">${p.current_posting.posting_type}</div>
        </div>
        <div class="p-2.5 bg-slate-50 border rounded">
          <div class="text-[10px] text-slate-400 font-bold uppercase">Verification Status</div>
          <div class="font-bold text-emerald-700">${p.current_posting.verification_status}</div>
        </div>
        <div class="p-2.5 bg-slate-50 border rounded">
          <div class="text-[10px] text-slate-400 font-bold uppercase">Deputation Order</div>
          <div class="font-bold text-slate-800">${p.current_posting.deputation_order_no || 'N/A'}</div>
        </div>
      </div>

      <!-- Tabs / Sections: Postings & Status Timeline -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <h4 class="font-bold text-xs text-slate-700 uppercase tracking-wider mb-2 flex items-center">
            <i data-lucide="history" class="w-3.5 h-3.5 mr-1.5 text-govblue-800"></i> Posting History Timeline
          </h4>
          <div class="max-h-60 overflow-y-auto">${postingHistHtml}</div>
        </div>
        <div>
          <h4 class="font-bold text-xs text-slate-700 uppercase tracking-wider mb-2 flex items-center">
            <i data-lucide="clock" class="w-3.5 h-3.5 mr-1.5 text-amber-600"></i> Service Status History
          </h4>
          <div class="max-h-60 overflow-y-auto">${statusHistHtml}</div>
        </div>
      </div>
    `;

    openModal(`Profile: ${p.name_ifmis} (${p.employee_id})`, bodyHtml);
  } catch (err) {
    alert("Failed to load profile: " + (err.detail || err.message));
  }
}

// ==========================================
// 5. SALARY CLAIMING DETAILS VIEW
// ==========================================
async function renderSalaryClaimingView() {
  const container = document.getElementById("view-salary-claiming");
  container.innerHTML = `
    <div class="flex justify-between items-center mb-5">
      <div>
        <h2 class="text-xl font-bold text-slate-900">Salary Claiming GP vs Actual Working GP Mapping</h2>
        <p class="text-xs text-slate-500">Cross-reference between employee salary claiming location and physical working posting</p>
      </div>
      <div>
        <button onclick="downloadReportExcel('D')" class="px-3.5 py-1.5 bg-emerald-700 hover:bg-emerald-800 text-white rounded text-xs font-semibold flex items-center shadow">
          <i data-lucide="download" class="w-3.5 h-3.5 mr-1.5"></i> Export Report (D)
        </button>
      </div>
    </div>
    
    <div id="salary-claiming-table-wrap" class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden p-4">
      <div class="text-center py-6 text-slate-400">Loading salary mapping details...</div>
    </div>
  `;
  lucide.createIcons();

  try {
    const res = await fetchAPI("/reports/data/D");
    const headers = res.headers || [];
    const rows = res.rows || [];

    let tableHtml = `
      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs text-slate-700">
          <thead class="bg-slate-50 border-b border-slate-200 text-[11px] font-bold text-slate-600 uppercase">
            <tr>
              ${headers.map(h => `<th class="px-3 py-2.5">${h}</th>`).join('')}
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            ${rows.map(r => `
              <tr class="table-hover-row">
                <td class="px-3 py-2 font-mono text-slate-400">${r[0]}</td>
                <td class="px-3 py-2 font-bold font-mono text-slate-900">${r[1]}</td>
                <td class="px-3 py-2 font-semibold text-slate-800">${r[2]}</td>
                <td class="px-3 py-2 font-mono text-slate-600">${r[3] || 'N/A'}</td>
                <td class="px-3 py-2 font-medium">${r[4]}</td>
                <td class="px-3 py-2 text-slate-600">${r[5]}</td>
                <td class="px-3 py-2 font-bold text-govblue-900">${r[6]}</td>
                <td class="px-3 py-2 text-slate-600">${r[7]}</td>
                <td class="px-3 py-2 text-slate-600">${r[8]}</td>
                <td class="px-3 py-2 font-semibold ${String(r[9]).includes('NO') ? 'text-amber-600' : 'text-emerald-600'}">${r[9]}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
    document.getElementById("salary-claiming-table-wrap").innerHTML = tableHtml;
  } catch (err) {
    document.getElementById("salary-claiming-table-wrap").innerHTML = `<div class="text-center text-red-500 py-4">Failed to load data: ${err.message}</div>`;
  }
}

// ==========================================
// 6. EMPLOYEE LIVE TRACKING
// ==========================================
async function renderEmployeeTrackingView() {
  const container = document.getElementById("view-employee-tracking");
  container.innerHTML = `
    <div class="max-w-4xl mx-auto space-y-6">
      <div>
        <h2 class="text-xl font-bold text-slate-900">Panchayat Secretary Live Tracking Portal</h2>
        <p class="text-xs text-slate-500">Instant lookup of any employee's verified location, salary GP and status</p>
      </div>

      <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex space-x-3 items-center">
        <div class="flex-1 relative">
          <input type="text" id="tracking-search-input" placeholder="Enter Employee ID (e.g. TS-1001) or Name..." onkeydown="if(event.key==='Enter') executeTrackingSearch()" class="w-full pl-9 pr-4 py-2.5 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-govblue-800 outline-none">
          <i data-lucide="search" class="w-4 h-4 text-slate-400 absolute left-3 top-3.5"></i>
        </div>
        <button onclick="executeTrackingSearch()" class="px-5 py-2.5 bg-govblue-900 hover:bg-govblue-800 text-white font-bold rounded-lg shadow text-xs">
          Search Profile
        </button>
      </div>

      <div id="tracking-result-container">
        <!-- Rendered search result -->
      </div>
    </div>
  `;
  lucide.createIcons();
}

async function executeTrackingSearch() {
  const query = document.getElementById("tracking-search-input").value.trim();
  const container = document.getElementById("tracking-result-container");
  if (!query) return;

  container.innerHTML = `<div class="p-8 text-center text-slate-400">Searching district records...</div>`;

  try {
    const data = await fetchAPI(`/employees?search=${encodeURIComponent(query)}&limit=5`);
    const items = data.items || [];
    if (items.length === 0) {
      container.innerHTML = `
        <div class="bg-white p-8 rounded-xl border border-slate-200 text-center">
          <i data-lucide="search-x" class="w-12 h-12 text-slate-300 mx-auto mb-2"></i>
          <h4 class="font-bold text-slate-800 text-sm">No Employee Records Found</h4>
          <p class="text-xs text-slate-500">No Panchayat Secretary matching "${query}" was found in Khammam District database.</p>
        </div>
      `;
      lucide.createIcons();
      return;
    }

    let cardsHtml = items.map(emp => `
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden mb-4">
        <div class="bg-govblue-900 text-white p-4 flex justify-between items-center">
          <div>
            <div class="text-xs text-amber-300 font-bold uppercase">EMPLOYEE RECORD FOUND</div>
            <div class="text-base font-bold">${emp.name_ifmis}</div>
            <div class="font-mono text-xs text-slate-300">ID: ${emp.employee_id} | Mobile: <strong class="text-amber-300">${emp.mobile_number || 'N/A'}</strong> | Mandal: ${emp.salary_mandal_name}</div>
          </div>
          <button onclick="viewEmployeeProfile('${emp.employee_id}')" class="px-3 py-1 bg-amber-500 hover:bg-amber-600 text-slate-950 font-bold rounded text-xs shadow">
            Full Dossier
          </button>
        </div>
        <div class="p-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-xs bg-slate-50 border-t">
          <div>
            <span class="text-slate-400 text-[10px] uppercase font-bold block">Salary Claiming GP</span>
            <strong class="text-slate-900">${emp.salary_gp_name}</strong>
          </div>
          <div>
            <span class="text-slate-400 text-[10px] uppercase font-bold block">Actual Working Location</span>
            <strong class="text-govblue-900">${emp.actual_working_gp_name}</strong>
          </div>
          <div>
            <span class="text-slate-400 text-[10px] uppercase font-bold block">Service Status</span>
            <span class="px-2 py-0.5 rounded text-[10px] font-bold ${emp.service_status === 'WORKING' ? 'badge-working' : 'badge-suspended'}">${emp.service_status}</span>
          </div>
          <div>
            <span class="text-slate-400 text-[10px] uppercase font-bold block">Posting Type</span>
            <span class="font-semibold text-slate-700">${emp.posting_type}</span>
          </div>
        </div>
      </div>
    `).join('');

    container.innerHTML = cardsHtml;
    lucide.createIcons();
  } catch (err) {
    container.innerHTML = `<div class="p-4 text-center text-red-500">Error: ${err.message}</div>`;
  }
}

// ==========================================
// 7. DEPUTATION CHAINS GRAPH & INTELLIGENCE
// ==========================================
async function renderDeputationChainsView() {
  const container = document.getElementById("view-deputation-chains");
  container.innerHTML = `
    <div class="flex justify-between items-center mb-5">
      <div>
        <h2 class="text-xl font-bold text-slate-900">Automatic Deputation Chain Tracking Engine</h2>
        <p class="text-xs text-slate-500">Interactive relationship diagram tracing multi-hop deputation chains and detecting circular links</p>
      </div>
      <div>
        <button onclick="downloadReportExcel('Q')" class="px-3.5 py-1.5 bg-purple-700 hover:bg-purple-800 text-white rounded text-xs font-semibold flex items-center shadow">
          <i data-lucide="download" class="w-3.5 h-3.5 mr-1.5"></i> Export Chain Report (Q)
        </button>
      </div>
    </div>

    <!-- Summary Notice -->
    <div class="p-3.5 bg-amber-50 rounded-xl border border-amber-200 text-amber-900 text-xs mb-5 flex items-center justify-between">
      <div class="flex items-center space-x-2">
        <i data-lucide="info" class="w-4 h-4 text-amber-600 flex-shrink-0"></i>
        <span><strong>Independent Verification Rule:</strong> Every employee has an independently recorded location. A chain of GP relationships does not automatically assume postings.</span>
      </div>
      <div id="chains-stat-badge" class="font-bold font-mono text-amber-900">Scanning chains...</div>
    </div>

    <!-- Canvas Diagram & Chain Cards -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      
      <!-- Left 2 Cols: Interactive Graph Canvas -->
      <div class="lg:col-span-2 bg-white rounded-xl border border-slate-200 shadow-sm p-4 flex flex-col">
        <div class="flex justify-between items-center mb-2">
          <h3 class="font-bold text-xs text-slate-700 uppercase tracking-wider flex items-center">
            <i data-lucide="git-merge" class="w-4 h-4 mr-1.5 text-purple-600"></i> Interactive Deputation Network Visualizer
          </h3>
          <span class="text-[10px] text-slate-400">Green = Working Staff | Red = Circular Warnings</span>
        </div>
        <div class="relative bg-slate-950 rounded-lg overflow-hidden h-[420px] flex items-center justify-center">
          <canvas id="deputation-canvas" class="w-full h-full"></canvas>
          <div id="canvas-overlay-tip" class="absolute bottom-2 left-2 text-[10px] text-slate-400 bg-black/60 px-2 py-1 rounded pointer-events-none">
            Interactive: Click nodes to view employee deputation details
          </div>
        </div>
      </div>

      <!-- Right 1 Col: Discovered Chains List -->
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-4 flex flex-col">
        <h3 class="font-bold text-xs text-slate-700 uppercase tracking-wider mb-3 flex items-center">
          <i data-lucide="list-ordered" class="w-4 h-4 mr-1.5 text-govblue-800"></i> Multi-Hop Chains Directory
        </h3>
        <div id="chains-list-container" class="space-y-3 overflow-y-auto max-h-[420px] text-xs">
          <div class="text-center py-8 text-slate-400">Loading chains...</div>
        </div>
      </div>

    </div>
  `;
  lucide.createIcons();

  try {
    const res = await fetchAPI("/deputations/chains");
    const chains = res.chains || [];
    const circularWarnings = res.circular_warnings || [];

    document.getElementById("chains-stat-badge").textContent = `Chains Found: ${chains.length} (Multi-Hop: ${res.multi_hop_chains_count})`;

    // Render Chains Cards in Right Column
    const chainsContainer = document.getElementById("chains-list-container");
    if (chains.length === 0) {
      chainsContainer.innerHTML = `<div class="text-center py-6 text-slate-400">No active deputation chains found.</div>`;
    } else {
      let cardsHtml = "";
      chains.forEach((c, idx) => {
        let hopSteps = "";
        c.employees.forEach((e, hIdx) => {
          hopSteps += `
            <div class="p-2 bg-slate-50 rounded border border-slate-200 mb-1.5 text-[11px]">
              <div class="font-bold text-slate-900">${hIdx + 1}. ${e.name_ifmis} (${e.employee_id})</div>
              <div class="text-slate-500">Draws Salary: <strong>${e.salary_gp_name}</strong></div>
              <div class="text-govblue-900">Works At: <strong>${e.actual_working_gp_name}</strong></div>
            </div>
          `;
        });

        cardsHtml += `
          <div class="p-3 bg-white rounded-lg border ${c.is_circular ? 'border-red-400 bg-red-50/20' : 'border-slate-200'} shadow-sm">
            <div class="flex justify-between items-center mb-1.5">
              <span class="font-bold font-mono text-purple-700 text-xs">${c.chain_id}</span>
              <span class="px-1.5 py-0.5 rounded text-[10px] font-bold ${c.is_multi_hop ? 'bg-purple-100 text-purple-800' : 'bg-slate-100 text-slate-600'}">${c.length} Hops</span>
            </div>
            ${c.is_circular ? `<div class="text-[10px] font-bold text-red-600 mb-1.5">⚠️ CIRCULAR REFERENCE DETECTED</div>` : ''}
            <div>${hopSteps}</div>
          </div>
        `;
      });
      chainsContainer.innerHTML = cardsHtml;
    }

    // Draw Graph onto HTML5 Canvas
    drawDeputationGraph(res.graph);

  } catch (err) {
    console.error("Deputation chain load error", err);
  }
}

function drawDeputationGraph(graph) {
  const canvas = document.getElementById("deputation-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  // High DPI scaling
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * 2;
  canvas.height = rect.height * 2;
  ctx.scale(2, 2);

  const width = rect.width;
  const height = rect.height;

  ctx.clearRect(0, 0, width, height);

  const nodes = graph.nodes || [];
  const edges = graph.edges || [];

  if (nodes.length === 0) {
    ctx.fillStyle = "#64748b";
    ctx.font = "12px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("No deputation links to render in current view", width / 2, height / 2);
    return;
  }

  // Layout nodes around circle or grid
  const nodePositions = {};
  const radius = Math.min(width, height) * 0.38;
  const centerX = width / 2;
  const centerY = height / 2;

  nodes.forEach((node, i) => {
    const angle = (i / nodes.length) * 2 * Math.PI - Math.PI / 2;
    nodePositions[node.id] = {
      x: centerX + radius * Math.cos(angle),
      y: centerY + radius * Math.sin(angle),
      label: node.label.split("\n")[0],
      mandal: node.mandal || ""
    };
  });

  // Draw Edges (Directed Arrows)
  edges.forEach(edge => {
    const fromPos = nodePositions[edge.from];
    const toPos = nodePositions[edge.to];
    if (fromPos && toPos) {
      ctx.beginPath();
      ctx.moveTo(fromPos.x, fromPos.y);
      ctx.lineTo(toPos.x, toPos.y);
      ctx.strokeStyle = edge.service_status === "WORKING" ? "#10b981" : "#f59e0b";
      ctx.lineWidth = 2;
      ctx.stroke();

      // Arrow head
      const angle = Math.atan2(toPos.y - fromPos.y, toPos.x - fromPos.x);
      const arrowLen = 10;
      const arrowX = toPos.x - 18 * Math.cos(angle);
      const arrowY = toPos.y - 18 * Math.sin(angle);

      ctx.beginPath();
      ctx.moveTo(arrowX, arrowY);
      ctx.lineTo(arrowX - arrowLen * Math.cos(angle - Math.PI / 6), arrowY - arrowLen * Math.sin(angle - Math.PI / 6));
      ctx.lineTo(arrowX - arrowLen * Math.cos(angle + Math.PI / 6), arrowY - arrowLen * Math.sin(angle + Math.PI / 6));
      ctx.fillStyle = edge.service_status === "WORKING" ? "#10b981" : "#f59e0b";
      ctx.fill();
    }
  });

  // Draw Nodes
  nodes.forEach(node => {
    const pos = nodePositions[node.id];
    if (pos) {
      // Circle
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, 16, 0, 2 * Math.PI);
      ctx.fillStyle = node.type === "GP" ? "#1e3a8a" : "#7c3aed";
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#ffffff";
      ctx.stroke();

      // Label
      ctx.fillStyle = "#e2e8f0";
      ctx.font = "bold 9px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(pos.label.substring(0, 14), pos.x, pos.y + 26);
    }
  });
}

// ==========================================
// 8. TWO-SIDE VERIFICATION CENTRE
// ==========================================
async function renderVerificationCentreView() {
  const container = document.getElementById("view-verification-centre");
  container.innerHTML = `
    <div class="flex justify-between items-center mb-5">
      <div>
        <h2 class="text-xl font-bold text-slate-900">Two-Side Deputation Verification Centre</h2>
        <p class="text-xs text-slate-500">Cross-verification of incoming and outgoing deputation assignments (Section 14)</p>
      </div>
      <div>
        <span class="text-xs bg-govteal-600 text-white font-bold px-3 py-1 rounded">Official Verification Module</span>
      </div>
    </div>

    <div class="p-4 bg-teal-50 rounded-xl border border-teal-200 text-teal-950 text-xs mb-5 flex items-center justify-between">
      <div>
        <strong>Two-Side Principle:</strong> When a salary-claiming GP marks an employee deputed to a receiving GP, the receiving Mandal must independently verify and confirm physical joining before status becomes <em>Verified by Both GPs</em>.
      </div>
    </div>

    <!-- Incoming Verifications Table -->
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden mb-6">
      <div class="bg-slate-50 p-4 border-b border-slate-200 flex justify-between items-center">
        <h3 class="font-bold text-slate-800 text-xs uppercase tracking-wider flex items-center">
          <i data-lucide="inbox" class="w-4 h-4 mr-2 text-govblue-900"></i> Incoming Deputations Requiring Your Verification
        </h3>
        <span id="incoming-verif-count" class="text-xs font-mono font-bold text-govblue-900">0 records</span>
      </div>
      <div id="incoming-verif-table-wrap" class="p-4 text-center text-slate-400">Loading incoming verification requests...</div>
    </div>

    <!-- Outgoing Verifications Table -->
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <div class="bg-slate-50 p-4 border-b border-slate-200 flex justify-between items-center">
        <h3 class="font-bold text-slate-800 text-xs uppercase tracking-wider flex items-center">
          <i data-lucide="send" class="w-4 h-4 mr-2 text-purple-700"></i> Outgoing Deputations Sent for Receiving Mandal Confirmation
        </h3>
        <span id="outgoing-verif-count" class="text-xs font-mono font-bold text-purple-700">0 records</span>
      </div>
      <div id="outgoing-verif-table-wrap" class="p-4 text-center text-slate-400">Loading outgoing verification requests...</div>
    </div>
  `;
  lucide.createIcons();

  try {
    const res = await fetchAPI("/verifications");
    const incoming = res.incoming_verifications || [];
    const outgoing = res.outgoing_verifications || [];

    document.getElementById("incoming-verif-count").textContent = `${incoming.length} records`;
    document.getElementById("outgoing-verif-count").textContent = `${outgoing.length} records`;

    // Incoming Table
    if (incoming.length === 0) {
      document.getElementById("incoming-verif-table-wrap").innerHTML = `<div class="py-6 text-slate-400">No pending incoming deputation verification requests.</div>`;
    } else {
      let inHtml = `
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs text-slate-700">
            <thead class="text-slate-500 border-b">
              <tr>
                <th class="py-2">Emp ID</th>
                <th class="py-2">Employee Name</th>
                <th class="py-2">Salary Claiming GP</th>
                <th class="py-2">Assigned To Working GP</th>
                <th class="py-2">Order No</th>
                <th class="py-2">Status</th>
                <th class="py-2 text-right">Verification Action</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              ${incoming.map(v => `
                <tr class="table-hover-row">
                  <td class="py-2.5 font-bold font-mono text-slate-900">${v.employee_id}</td>
                  <td class="py-2.5 font-semibold">${v.name_ifmis}</td>
                  <td class="py-2.5">${v.salary_gp_name} (${v.salary_mandal_name})</td>
                  <td class="py-2.5 font-bold text-govblue-900">${v.receiving_gp_name} (${v.receiving_mandal_name})</td>
                  <td class="py-2.5 text-slate-500">${v.deputation_order_no || 'N/A'}</td>
                  <td class="py-2.5"><span class="px-2 py-0.5 rounded text-[10px] font-bold ${v.status === 'CONFIRMED' ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'}">${v.status}</span></td>
                  <td class="py-2.5 text-right space-x-1">
                    <button onclick="openVerificationModal(${v.posting_id}, '${v.name_ifmis.replace(/'/g, "\\'")}', ${v.receiving_gp_lgd || 0}, '${(v.receiving_gp_name || '').replace(/'/g, "\\'")}', ${v.receiving_mandal_id})" class="px-3 py-1 bg-govblue-900 hover:bg-govblue-800 text-white rounded font-bold text-[11px] shadow">Verify / Re-assign</button>
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;
      document.getElementById("incoming-verif-table-wrap").innerHTML = inHtml;
    }

    // Outgoing Table
    if (outgoing.length === 0) {
      document.getElementById("outgoing-verif-table-wrap").innerHTML = `<div class="py-6 text-slate-400">No outgoing deputation records from this Mandal.</div>`;
    } else {
      let outHtml = `
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs text-slate-700">
            <thead class="text-slate-500 border-b">
              <tr>
                <th class="py-2">Emp ID</th>
                <th class="py-2">Employee Name</th>
                <th class="py-2">Salary Claiming GP</th>
                <th class="py-2">Deputed Destination GP</th>
                <th class="py-2">Two-Side Verification Status</th>
                <th class="py-2">Receiving Remarks</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              ${outgoing.map(v => `
                <tr class="table-hover-row">
                  <td class="py-2.5 font-bold font-mono text-slate-900">${v.employee_id}</td>
                  <td class="py-2.5 font-semibold">${v.name_ifmis}</td>
                  <td class="py-2.5">${v.salary_gp_name}</td>
                  <td class="py-2.5 font-bold text-govblue-900">${v.receiving_gp_name} (${v.receiving_mandal_name})</td>
                  <td class="py-2.5"><span class="px-2 py-0.5 rounded text-[10px] font-bold ${v.status === 'CONFIRMED' ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'}">${v.status}</span></td>
                  <td class="py-2.5 text-slate-500 italic">${v.receiving_remarks || 'Awaiting confirmation'}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;
      document.getElementById("outgoing-verif-table-wrap").innerHTML = outHtml;
    }

  } catch (err) {
    console.error("Verification centre error", err);
  }
}

function openVerificationModal(postingId, empName, currentGpLgd, currentGpName, mandalId) {
  // Filter GPs belonging to receiving mandal
  const mGps = centralizedPanchayats.filter(gp => gp.mandal_id === mandalId);
  let gpOptions = `<option value="${currentGpLgd}">Confirm at Designated GP: ${currentGpName} (LGD: ${currentGpLgd})</option>`;
  mGps.forEach(gp => {
    if (gp.lgd_code !== currentGpLgd) {
      gpOptions += `<option value="${gp.lgd_code}">Internally Re-assigned to: ${gp.gp_name} (LGD: ${gp.lgd_code})</option>`;
    }
  });

  const bodyHtml = `
    <div class="space-y-4 text-xs">
      <div class="p-3 bg-blue-50 border border-blue-200 rounded text-blue-950">
        <div class="font-bold text-sm text-govblue-950">${empName}</div>
        <div class="text-[11px] text-slate-600 mt-0.5">Designated Destination: <strong>${currentGpName} (LGD: ${currentGpLgd})</strong></div>
      </div>

      <div>
        <label class="block font-bold text-slate-700 uppercase tracking-wider mb-1">
          Actual Physical Working Gram Panchayat (Confirm or Re-assign Internally)
        </label>
        <select id="modal-verif-gp-select" class="w-full p-2 border border-slate-300 rounded font-semibold text-xs bg-white text-slate-900 outline-none">
          ${gpOptions}
        </select>
        <p class="text-[11px] text-slate-500 mt-1">
          <strong>Internal Re-allocation:</strong> If your Mandal internally re-assigned this secretary to a different GP (e.g. from GP X to GP Z), select the actual working GP above.
        </p>
      </div>

      <div>
        <label class="block font-bold text-slate-700 uppercase tracking-wider mb-1">Official Verification Remarks</label>
        <textarea id="modal-verif-remarks" rows="2" placeholder="e.g. Physically joined duty on internal assignment / Proceedings ref..." class="w-full p-2 border border-slate-300 rounded text-xs outline-none"></textarea>
      </div>

      <div class="pt-3 border-t border-slate-200 flex justify-end space-x-2">
        <button onclick="closeModal()" class="px-3 py-1.5 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded font-semibold text-xs">Cancel</button>
        <button onclick="submitVerificationAction(${postingId}, 'REJECT', ${currentGpLgd})" class="px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded font-bold text-xs">Reject (Not Joined)</button>
        <button onclick="submitVerificationAction(${postingId}, 'DISCREPANCY', ${currentGpLgd})" class="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded font-bold text-xs">Raise Discrepancy</button>
        <button onclick="submitVerificationAction(${postingId}, 'CONFIRM', ${currentGpLgd})" class="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded font-bold text-xs shadow">Confirm Joining</button>
      </div>
    </div>
  `;

  openModal(`Deputation Verification & Working GP Assignment: ${empName}`, bodyHtml);
}

async function submitVerificationAction(postingId, action, originalGpLgd) {
  const gpSelect = document.getElementById("modal-verif-gp-select");
  const remarksInput = document.getElementById("modal-verif-remarks");

  const selectedGpLgd = gpSelect ? parseInt(gpSelect.value) : originalGpLgd;
  const remarks = remarksInput ? remarksInput.value.trim() : "";

  const payload = {
    posting_id: postingId,
    action: action,
    remarks: remarks || (action === "CONFIRM" ? "Physical joining verified and confirmed by receiving Mandal." : "Verification action taken")
  };

  if (action === "CONFIRM" && selectedGpLgd && selectedGpLgd !== originalGpLgd) {
    payload.corrected_working_gp_lgd = selectedGpLgd;
  }

  try {
    const res = await fetchAPI("/verifications/action", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    alert(`Success: ${res.message}`);
    closeModal();
    renderVerificationCentreView();
  } catch (err) {
    alert("Error: " + (err.detail || err.message));
  }
}

// ==========================================
// 9. DISCREPANCY MANAGEMENT ENGINE
// ==========================================
async function renderDiscrepanciesView() {
  const container = document.getElementById("view-discrepancies");
  container.innerHTML = `
    <div class="flex justify-between items-center mb-5">
      <div>
        <h2 class="text-xl font-bold text-slate-900">District Discrepancy Detection & Resolution Centre</h2>
        <p class="text-xs text-slate-500">Automated 19-rule discrepancy detection engine across all 571 GPs (Section 15)</p>
      </div>
      <div>
        <button onclick="triggerDiscrepancyScan()" class="px-4 py-2 bg-rose-700 hover:bg-rose-800 text-white rounded text-xs font-bold flex items-center shadow">
          <i data-lucide="scan" class="w-4 h-4 mr-1.5"></i> Run Real-Time Scan Now
        </button>
      </div>
    </div>

    <!-- Discrepancy List Table -->
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <div class="p-4 bg-slate-50 border-b border-slate-200 flex justify-between items-center">
        <h3 class="font-bold text-slate-800 text-xs uppercase tracking-wider">Identified Issues & Resolution Status</h3>
        <span id="disc-count-badge" class="font-bold font-mono text-xs text-rose-600">Loading issues...</span>
      </div>
      <div id="discrepancy-table-wrap" class="p-4 text-center text-slate-400">Loading discrepancy records...</div>
    </div>
  `;
  lucide.createIcons();
  loadDiscrepanciesData();
}

async function triggerDiscrepancyScan() {
  try {
    const res = await fetchAPI("/discrepancies/scan");
    alert(`Scan completed: ${res.total_discrepancies_detected} issue(s) detected across Khammam District.`);
    loadDiscrepanciesData();
  } catch (err) {
    alert("Scan failed: " + (err.detail || err.message));
  }
}

async function loadDiscrepanciesData() {
  const wrap = document.getElementById("discrepancy-table-wrap");
  if (!wrap) return;

  try {
    const list = await fetchAPI("/discrepancies");
    document.getElementById("disc-count-badge").textContent = `${list.length} total issues`;

    if (list.length === 0) {
      wrap.innerHTML = `<div class="py-8 text-center text-emerald-600 font-bold">✨ No active discrepancies detected. All postings and statuses are fully verified!</div>`;
      return;
    }

    let rowsHtml = `
      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs text-slate-700">
          <thead class="text-slate-500 border-b">
            <tr>
              <th class="py-2">Severity</th>
              <th class="py-2">Issue Title</th>
              <th class="py-2">Description</th>
              <th class="py-2">Emp ID</th>
              <th class="py-2">Mandal</th>
              <th class="py-2">Status</th>
              <th class="py-2 text-right">Resolve</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            ${list.map(d => `
              <tr class="table-hover-row">
                <td class="py-2.5">
                  <span class="px-2 py-0.5 rounded text-[10px] font-bold ${d.severity === 'CRITICAL' ? 'bg-red-600 text-white' : (d.severity === 'HIGH' ? 'bg-rose-100 text-rose-800' : 'bg-amber-100 text-amber-800')}">${d.severity}</span>
                </td>
                <td class="py-2.5 font-bold text-slate-900">${d.title}</td>
                <td class="py-2.5 text-slate-600 max-w-xs leading-tight">${d.description}</td>
                <td class="py-2.5 font-mono font-bold">${d.employee_id || 'N/A'}</td>
                <td class="py-2.5 font-medium">${d.mandal_name || 'District'}</td>
                <td class="py-2.5">
                  <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold ${d.status === 'RESOLVED' ? 'bg-green-100 text-green-800' : 'bg-slate-100 text-slate-600'}">${d.status}</span>
                </td>
                <td class="py-2.5 text-right">
                  ${d.status !== 'RESOLVED' ? `<button onclick="openResolveDiscrepancyModal(${d.id}, '${d.title}')" class="px-2.5 py-1 bg-govblue-900 text-white rounded font-bold text-[11px]">Resolve</button>` : `<span class="text-slate-400 text-[11px]">Closed</span>`}
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
    wrap.innerHTML = rowsHtml;
  } catch (err) {
    wrap.innerHTML = `<div class="py-4 text-center text-red-500">Failed to load discrepancies: ${err.message}</div>`;
  }
}

function openResolveDiscrepancyModal(discId, title) {
  const bodyHtml = `
    <form onsubmit="handleResolveDiscrepancy(event, ${discId})" class="space-y-4 text-xs">
      <div>
        <label class="block font-bold text-slate-700 uppercase mb-1">Issue</label>
        <div class="p-2.5 bg-slate-50 rounded border text-slate-800 font-semibold">${title}</div>
      </div>
      <div>
        <label class="block font-bold text-slate-700 uppercase mb-1">Official Resolution Remarks</label>
        <textarea id="modal-resolution-remarks" required rows="3" placeholder="Explain the verification steps taken to resolve this discrepancy..." class="w-full p-2 border border-slate-300 rounded focus:ring-1 focus:ring-govblue-800"></textarea>
      </div>
      <div class="flex justify-end space-x-2 pt-2">
        <button type="button" onclick="closeModal()" class="px-3 py-1.5 bg-slate-200 text-slate-800 rounded">Cancel</button>
        <button type="submit" class="px-4 py-1.5 bg-emerald-700 text-white font-bold rounded shadow">Confirm Resolution</button>
      </div>
    </form>
  `;
  openModal("Resolve Discrepancy Record", bodyHtml);
}

async function handleResolveDiscrepancy(e, discId) {
  e.preventDefault();
  const remarks = document.getElementById("modal-resolution-remarks").value.trim();

  try {
    await fetchAPI(`/discrepancies/${discId}/resolve`, {
      method: "POST",
      body: JSON.stringify({
        resolution_remarks: remarks,
        new_status: "RESOLVED"
      })
    });
    closeModal();
    alert("Discrepancy resolved successfully.");
    loadDiscrepanciesData();
  } catch (err) {
    alert("Resolution error: " + (err.detail || err.message));
  }
}

// ==========================================
// 10. EMPLOYEE AVAILABILITY CLASSIFICATION
// ==========================================
async function renderAvailabilityView() {
  const container = document.getElementById("view-availability");
  container.innerHTML = `
    <div class="flex justify-between items-center mb-5">
      <div>
        <h2 class="text-xl font-bold text-slate-900">Actual Employee Availability Management</h2>
        <p class="text-xs text-slate-500">Classification of staff by physical availability for regular duty across Khammam District</p>
      </div>
      <div>
        <button onclick="downloadReportExcel('O')" class="px-3.5 py-1.5 bg-govblue-900 hover:bg-govblue-800 text-white rounded text-xs font-semibold flex items-center shadow">
          <i data-lucide="download" class="w-3.5 h-3.5 mr-1.5"></i> Export Unavailable Staff Report (O)
        </button>
      </div>
    </div>

    <!-- Availability Three Categories Card Grid -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-5 mb-6">
      
      <!-- Category A -->
      <div class="bg-white p-5 rounded-xl border-t-4 border-emerald-500 border-x border-b shadow-sm">
        <div class="flex justify-between items-center mb-2">
          <h3 class="font-bold text-xs text-slate-800 uppercase tracking-wider">CATEGORY A</h3>
          <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800">AVAILABLE</span>
        </div>
        <div class="text-lg font-bold text-emerald-700">Available for Regular Work</div>
        <p class="text-[11px] text-slate-500 mt-1">Panchayat Secretaries actively working on ground in Gram Panchayats.</p>
        <div class="mt-4 pt-3 border-t flex justify-between items-center">
          <span class="text-xs text-slate-600">Total Available:</span>
          <span id="avail-cat-a-count" class="text-xl font-bold text-emerald-600 font-mono">-</span>
        </div>
      </div>

      <!-- Category B -->
      <div class="bg-white p-5 rounded-xl border-t-4 border-amber-500 border-x border-b shadow-sm">
        <div class="flex justify-between items-center mb-2">
          <h3 class="font-bold text-xs text-slate-800 uppercase tracking-wider">CATEGORY B</h3>
          <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800">NOT AVAILABLE</span>
        </div>
        <div class="text-lg font-bold text-amber-700">Not Available for Regular Work</div>
        <p class="text-[11px] text-slate-500 mt-1">Suspended, Absconding, Medical Leave, Maternity/CCL, Long Leave, EOL.</p>
        <div class="mt-4 pt-3 border-t flex justify-between items-center">
          <span class="text-xs text-slate-600">Total Unavailable:</span>
          <span id="avail-cat-b-count" class="text-xl font-bold text-amber-600 font-mono">-</span>
        </div>
      </div>

      <!-- Category C -->
      <div class="bg-white p-5 rounded-xl border-t-4 border-slate-500 border-x border-b shadow-sm">
        <div class="flex justify-between items-center mb-2">
          <h3 class="font-bold text-xs text-slate-800 uppercase tracking-wider">CATEGORY C</h3>
          <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700">UNVERIFIED</span>
        </div>
        <div class="text-lg font-bold text-slate-700">Status Under Verification</div>
        <p class="text-[11px] text-slate-500 mt-1">Two-side deputations pending confirmation or expired return dates.</p>
        <div class="mt-4 pt-3 border-t flex justify-between items-center">
          <span class="text-xs text-slate-600">Pending Verification:</span>
          <span id="avail-cat-c-count" class="text-xl font-bold text-slate-700 font-mono">-</span>
        </div>
      </div>

    </div>

    <!-- Category B Detailed Breakdown -->
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
      <h3 class="font-bold text-sm text-slate-800 mb-3 flex items-center">
        <i data-lucide="user-x" class="w-4 h-4 mr-2 text-amber-600"></i> Unavailable Staff Detailed Roster (Category B)
      </h3>
      <div id="unavailable-roster-wrap" class="overflow-x-auto text-xs text-center py-4 text-slate-400">Loading unavailable staff roster...</div>
    </div>
  `;
  lucide.createIcons();

  try {
    const summary = await fetchAPI("/analytics/district-summary");
    document.getElementById("avail-cat-a-count").textContent = summary.available_for_regular_work;
    document.getElementById("avail-cat-b-count").textContent = summary.not_available_for_regular_work;
    document.getElementById("avail-cat-c-count").textContent = summary.pending_verifications;

    const repO = await fetchAPI("/reports/data/O");
    const headers = repO.headers || [];
    const rows = repO.rows || [];

    if (rows.length === 0) {
      document.getElementById("unavailable-roster-wrap").innerHTML = `<div class="py-4 text-center text-slate-400">No staff currently in unavailable categories.</div>`;
    } else {
      let tHtml = `
        <table class="w-full text-left text-xs text-slate-700">
          <thead class="bg-slate-50 border-b text-[11px] font-bold text-slate-600 uppercase">
            <tr>
              ${headers.map(h => `<th class="px-3 py-2.5">${h}</th>`).join('')}
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            ${rows.map(r => `
              <tr class="table-hover-row">
                <td class="px-3 py-2 font-mono text-slate-400">${r[0]}</td>
                <td class="px-3 py-2 font-bold font-mono text-slate-900">${r[1]}</td>
                <td class="px-3 py-2 font-semibold text-slate-800">${r[2]}</td>
                <td class="px-3 py-2">${r[3]}</td>
                <td class="px-3 py-2">${r[4]}</td>
                <td class="px-3 py-2 font-bold text-amber-700">${r[5]}</td>
                <td class="px-3 py-2 text-slate-500">${r[6]}</td>
                <td class="px-3 py-2 text-slate-500">${r[7]}</td>
                <td class="px-3 py-2 italic text-slate-600">${r[8]}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
      document.getElementById("unavailable-roster-wrap").innerHTML = tHtml;
    }
  } catch (err) {
    console.error("Availability load error", err);
  }
}

// ==========================================
// 11. DISTRICT REPORTS (ALL 26 REPORTS A-Z)
// ==========================================
let currentReportCode = "A";

async function renderReportsView() {
  if (currentUser && currentUser.role === "MANDAL_ADMIN") {
    navigate("mandal-reports");
    return;
  }

  const container = document.getElementById("view-reports");
  
  let reportList = [];
  try {
    reportList = await fetchAPI("/reports/list");
  } catch (e) {
    reportList = [];
  }

  let optionsHtml = "";
  reportList.forEach(r => {
    optionsHtml += `<option value="${r.code}">${r.code}. ${r.name}</option>`;
  });

  container.innerHTML = `
    <div class="flex flex-wrap justify-between items-center mb-5 gap-3">
      <div>
        <h2 class="text-xl font-bold text-slate-900">District Statutory Report Generator</h2>
        <p class="text-xs text-slate-500">26 Official Government Reports (A to Z) with Excel, CSV and Print exports</p>
      </div>
      <div class="flex space-x-2">
        <button onclick="downloadReportExcel(currentReportCode)" class="px-3.5 py-1.5 bg-emerald-700 hover:bg-emerald-800 text-white rounded text-xs font-semibold flex items-center shadow">
          <i data-lucide="file-spreadsheet" class="w-3.5 h-3.5 mr-1.5"></i> Export Excel (XLSX)
        </button>
        <button onclick="downloadReportCSV(currentReportCode)" class="px-3.5 py-1.5 bg-govblue-900 hover:bg-govblue-800 text-white rounded text-xs font-semibold flex items-center shadow">
          <i data-lucide="file-text" class="w-3.5 h-3.5 mr-1.5"></i> Export CSV
        </button>
        <button onclick="window.print()" class="px-3.5 py-1.5 bg-slate-700 hover:bg-slate-800 text-white rounded text-xs font-semibold flex items-center shadow">
          <i data-lucide="printer" class="w-3.5 h-3.5 mr-1.5"></i> Print Report
        </button>
      </div>
    </div>

    <!-- Report Selector Dropdown -->
    <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm mb-5 flex flex-wrap gap-3 items-center">
      <div class="flex-1 min-w-[300px]">
        <label class="block text-[10px] font-bold text-slate-500 uppercase mb-1">Select Official Report (A to Z)</label>
        <select id="report-code-select" onchange="handleReportSelectChange(event)" class="w-full p-2 border border-slate-300 rounded font-semibold text-xs bg-white text-slate-900">
          ${optionsHtml}
        </select>
      </div>
      <div class="pt-4">
        <button onclick="loadReportPreview()" class="px-4 py-2 bg-govblue-900 hover:bg-govblue-800 text-white rounded text-xs font-bold">
          Generate Preview
        </button>
      </div>
    </div>

    <!-- Report Preview Paper Format -->
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6 overflow-hidden">
      <!-- Printable Official Header -->
      <div class="text-center pb-4 mb-4 border-b-2 border-slate-800">
        <div class="text-xs font-bold text-slate-500 uppercase tracking-widest">GOVERNMENT OF TELANGANA</div>
        <h3 class="text-base font-bold text-govblue-950">DISTRICT PANCHAYAT OFFICE, KHAMMAM</h3>
        <h4 id="report-preview-title" class="text-sm font-bold text-amber-700 mt-1">District Employee Master Report</h4>
        <div class="text-[11px] text-slate-500 mt-1">Generated On: <span id="report-preview-timestamp">-</span> | Khammam District</div>
      </div>

      <div id="report-preview-table-wrap" class="overflow-x-auto text-xs">
        <div class="py-8 text-center text-slate-400">Loading report preview...</div>
      </div>
    </div>
  `;
  lucide.createIcons();

  loadReportPreview();
}

function handleReportSelectChange(e) {
  currentReportCode = e.target.value;
  loadReportPreview();
}

async function loadReportPreview() {
  const wrap = document.getElementById("report-preview-table-wrap");
  if (!wrap) return;

  wrap.innerHTML = `<div class="py-8 text-center text-slate-400">Generating report...</div>`;

  try {
    const res = await fetchAPI(`/reports/data/${currentReportCode}`);
    document.getElementById("report-preview-title").textContent = `Report ${res.report_code}: ${res.title}`;
    document.getElementById("report-preview-timestamp").textContent = res.generated_at;

    const headers = res.headers || [];
    const rows = res.rows || [];

    if (rows.length === 0) {
      wrap.innerHTML = `<div class="py-8 text-center text-slate-400">No records found for this report criteria.</div>`;
      return;
    }

    let tHtml = `
      <table class="w-full text-left text-xs text-slate-800 border-collapse">
        <thead class="bg-slate-100 border-b border-slate-300 text-[11px] font-bold text-slate-700 uppercase">
          <tr>
            ${headers.map(h => `<th class="px-3 py-2 border-r border-slate-200 last:border-r-0">${h}</th>`).join('')}
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-200">
          ${rows.map(r => `
            <tr class="table-hover-row">
              ${r.map(val => `<td class="px-3 py-2 border-r border-slate-100 last:border-r-0">${val !== null ? val : ''}</td>`).join('')}
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
    wrap.innerHTML = tHtml;
  } catch (err) {
    wrap.innerHTML = `<div class="py-4 text-center text-red-500">Error generating report: ${err.message}</div>`;
  }
}

function downloadReportExcel(code) {
  window.open(`${API_BASE}/reports/export/${code}?format=excel`, '_blank');
}

function downloadReportCSV(code) {
  window.open(`${API_BASE}/reports/export/${code}?format=csv`, '_blank');
}

// ==========================================
// 12. MANDAL-WISE POSITION STATEMENT
// ==========================================
async function renderMandalReportsView() {
  const isMandal = currentUser && currentUser.role === "MANDAL_ADMIN";
  const mandalName = currentUser?.mandal_name || "Mandal";
  const title = isMandal ? `${mandalName} Mandal Position Statement` : "Mandal-wise Comparative Position Statement";
  const subtitle = isMandal
    ? `Position statement and employee availability summary for ${mandalName} Mandal (LGD: ${currentUser?.mandal_lgd})`
    : "Summary metrics across all 20 Mandals of Khammam District";
  const exportLabel = isMandal ? `Export ${mandalName} Statement` : "Export Report (B)";

  const container = document.getElementById("view-mandal-reports");
  container.innerHTML = `
    <div class="flex justify-between items-center mb-5">
      <div>
        <h2 class="text-xl font-bold text-slate-900">${title}</h2>
        <p class="text-xs text-slate-500">${subtitle}</p>
      </div>
      <div>
        <button onclick="downloadReportExcel('B')" class="px-3.5 py-1.5 bg-govblue-900 text-white rounded text-xs font-semibold flex items-center shadow">
          <i data-lucide="download" class="w-3.5 h-3.5 mr-1.5"></i> ${exportLabel}
        </button>
      </div>
    </div>

    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden p-4">
      <div id="mandal-table-wrap" class="overflow-x-auto text-xs text-center py-6 text-slate-400">Loading mandal analytics...</div>
    </div>
  `;
  lucide.createIcons();

  try {
    const list = await fetchAPI("/analytics/mandal-breakdown");
    let rowsHtml = `
      <table class="w-full text-left text-xs text-slate-700">
        <thead class="bg-slate-50 border-b text-[11px] font-bold text-slate-600 uppercase">
          <tr>
            <th class="py-2.5 px-3">#</th>
            <th class="py-2.5 px-3">Mandal Name</th>
            <th class="py-2.5 px-3">Mandal LGD</th>
            <th class="py-2.5 px-3 text-center">Total GPs</th>
            <th class="py-2.5 px-3 text-center">Clear Vacancies</th>
            <th class="py-2.5 px-3 text-center">Salary Strength</th>
            <th class="py-2.5 px-3 text-center">Working Here</th>
            <th class="py-2.5 px-3 text-center">Deputed Out</th>
            <th class="py-2.5 px-3 text-center">Deputed In</th>
            <th class="py-2.5 px-3 text-center">Unavailable</th>
            <th class="py-2.5 px-3 text-center">Submission Status</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          ${list.map((m, idx) => `
            <tr class="table-hover-row">
              <td class="py-2 px-3 font-mono text-slate-400">${idx + 1}</td>
              <td class="py-2 px-3 font-bold text-slate-900">${m.mandal_name}</td>
              <td class="py-2 px-3 font-mono text-slate-500">${m.mandal_lgd}</td>
              <td class="py-2 px-3 text-center font-bold">${m.total_gps}</td>
              <td class="py-2 px-3 text-center font-bold ${m.clear_vacancies > 0 ? 'text-rose-600' : 'text-slate-400'}">${m.clear_vacancies}</td>
              <td class="py-2 px-3 text-center font-bold text-govblue-900">${m.salary_drawing_strength}</td>
              <td class="py-2 px-3 text-center font-bold text-emerald-600">${m.actually_working_strength}</td>
              <td class="py-2 px-3 text-center font-bold text-amber-600">${m.deputed_out}</td>
              <td class="py-2 px-3 text-center font-bold text-purple-600">${m.deputed_in}</td>
              <td class="py-2 px-3 text-center font-bold ${m.unavailable_strength > 0 ? 'text-red-600' : 'text-slate-400'}">${m.unavailable_strength}</td>
              <td class="py-2 px-3 text-center">
                <span class="px-2 py-0.5 rounded text-[10px] font-bold ${m.is_submitted ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'}">
                  ${m.is_submitted ? 'SUBMITTED' : 'PENDING'}
                </span>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
    document.getElementById("mandal-table-wrap").innerHTML = rowsHtml;
  } catch (err) {
    document.getElementById("mandal-table-wrap").innerHTML = `<div class="text-center text-red-500 py-4">Error loading breakdown: ${err.message}</div>`;
  }
}

// ==========================================
// 13. BULK EXCEL IMPORT & EXPORT
// ==========================================
async function renderImportExportView() {
  const container = document.getElementById("view-import-export");
  container.innerHTML = `
    <div class="max-w-4xl mx-auto space-y-6">
      <div>
        <h2 class="text-xl font-bold text-slate-900">Bulk Excel Data Import & Migration Engine</h2>
        <p class="text-xs text-slate-500">Section 18: Upload and validate master employee records with row-by-row error detection</p>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
        <!-- Step 1: Download Template -->
        <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div>
            <div class="w-10 h-10 rounded-lg bg-emerald-50 text-emerald-700 flex items-center justify-center mb-3">
              <i data-lucide="download" class="w-5 h-5"></i>
            </div>
            <h3 class="font-bold text-slate-800 text-sm mb-1">Step 1: Download Excel Template</h3>
            <p class="text-xs text-slate-500 leading-relaxed mb-4">
              Get the standardized Excel template containing all required column headers, LGD reference guidelines, and sample records.
            </p>
          </div>
          <button onclick="downloadExcelTemplate()" class="w-full py-2 bg-slate-800 hover:bg-slate-900 text-white rounded font-bold text-xs flex items-center justify-center">
            <i data-lucide="file-spreadsheet" class="w-4 h-4 mr-2"></i> Download Template (.xlsx)
          </button>
        </div>

        <!-- Step 2: Upload Excel File -->
        <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div>
            <div class="w-10 h-10 rounded-lg bg-govblue-50 text-govblue-900 flex items-center justify-center mb-3">
              <i data-lucide="upload" class="w-5 h-5"></i>
            </div>
            <h3 class="font-bold text-slate-800 text-sm mb-1">Step 2: Upload Completed File</h3>
            <p class="text-xs text-slate-500 leading-relaxed mb-4">
              Upload your Excel file. The system will perform instant global validation against 571 GPs and existing Employee IDs.
            </p>
          </div>
          <form onsubmit="handleUploadSubmit(event)" class="space-y-2">
            <input type="file" id="bulk-excel-file" accept=".xlsx, .xlsm" required class="w-full text-xs text-slate-500 file:mr-2 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-xs file:font-semibold file:bg-govblue-50 file:text-govblue-900 hover:file:bg-govblue-100">
            <button type="submit" id="btn-upload-excel" class="w-full py-2 bg-govblue-900 hover:bg-govblue-800 text-white rounded font-bold text-xs flex items-center justify-center">
              <i data-lucide="check" class="w-4 h-4 mr-2"></i> Validate & Import Data
            </button>
          </form>
        </div>
      </div>

      <!-- Import Validation Results -->
      <div id="import-results-container" class="hidden bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-4">
        <!-- Injected after upload -->
      </div>
    </div>
  `;
  lucide.createIcons();
}

function downloadExcelTemplate() {
  window.open(`${API_BASE}/import-export/template`, '_blank');
}

async function handleUploadSubmit(e) {
  e.preventDefault();
  const fileInput = document.getElementById("bulk-excel-file");
  if (!fileInput.files || fileInput.files.length === 0) return;

  const btn = document.getElementById("btn-upload-excel");
  btn.disabled = true;
  btn.innerHTML = `<span>Validating records...</span>`;

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  const container = document.getElementById("import-results-container");
  container.classList.remove("hidden");
  container.innerHTML = `<div class="p-6 text-center text-slate-400">Processing Excel rows and validating against master database...</div>`;

  try {
    const res = await fetchAPI("/import-export/upload-employees", {
      method: "POST",
      isFormData: true,
      body: formData
    });

    let errorsHtml = "";
    if (res.errors && res.errors.length > 0) {
      errorsHtml = `
        <div class="mt-4 border-t pt-4">
          <h4 class="font-bold text-xs text-rose-700 uppercase mb-2">Validation Errors Found (${res.errors.length})</h4>
          <div class="max-h-60 overflow-y-auto space-y-1 text-xs">
            ${res.errors.map(err => `
              <div class="p-2 bg-rose-50 text-rose-900 border border-rose-200 rounded text-[11px] flex justify-between">
                <span>Row ${err.row}: <strong>${err.employee_id}</strong> - ${err.error}</span>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }

    container.innerHTML = `
      <div class="border-b pb-3 flex justify-between items-center">
        <h3 class="font-bold text-slate-800 text-sm">Bulk Import Summary Report</h3>
        <span class="px-2.5 py-0.5 rounded text-xs font-bold ${res.total_errors > 0 ? 'bg-amber-100 text-amber-900' : 'bg-emerald-100 text-emerald-900'}">
          ${res.total_errors > 0 ? 'Completed with Warnings' : '100% Successful'}
        </span>
      </div>

      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs text-center">
        <div class="p-3 bg-slate-50 rounded border">
          <span class="text-slate-400 text-[10px] uppercase font-bold block">Total Rows</span>
          <strong class="text-base text-slate-800">${res.total_rows_processed}</strong>
        </div>
        <div class="p-3 bg-emerald-50 rounded border border-emerald-200">
          <span class="text-emerald-700 text-[10px] uppercase font-bold block">Successfully Imported</span>
          <strong class="text-base text-emerald-700 font-bold">${res.successfully_imported}</strong>
        </div>
        <div class="p-3 bg-amber-50 rounded border border-amber-200">
          <span class="text-amber-700 text-[10px] uppercase font-bold block">Duplicates Blocked</span>
          <strong class="text-base text-amber-700 font-bold">${res.duplicate_employee_ids}</strong>
        </div>
        <div class="p-3 bg-rose-50 rounded border border-rose-200">
          <span class="text-rose-700 text-[10px] uppercase font-bold block">Invalid GPs</span>
          <strong class="text-base text-rose-700 font-bold">${res.invalid_gp_codes}</strong>
        </div>
      </div>

      ${errorsHtml}
    `;

    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="check" class="w-4 h-4 mr-2"></i> Validate & Import Data`;
    lucide.createIcons();

  } catch (err) {
    container.innerHTML = `<div class="p-4 text-center text-red-600">Import failed: ${err.detail || err.message}</div>`;
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="check" class="w-4 h-4 mr-2"></i> Validate & Import Data`;
  }
}

// ==========================================
// 14. ADMIN CONTROLS: USERS, SESSIONS & AUDIT
// ==========================================
async function renderUserManagementView() {
  const container = document.getElementById("view-user-management");
  container.innerHTML = `
    <div class="flex justify-between items-center mb-5">
      <div>
        <h2 class="text-xl font-bold text-slate-900">User Account Administration</h2>
        <p class="text-xs text-slate-500">Manage Mandal official credentials, unlock locked accounts, and reset passwords</p>
      </div>
    </div>
    <div id="users-table-wrap" class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden p-4">
      <div class="text-center py-6 text-slate-400">Loading user accounts...</div>
    </div>
  `;
  lucide.createIcons();

  try {
    const users = await fetchAPI("/admin/users");
    let rowsHtml = `
      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs text-slate-700">
          <thead class="bg-slate-50 border-b text-[11px] font-bold text-slate-600 uppercase">
            <tr>
              <th class="py-2.5 px-3">#</th>
              <th class="py-2.5 px-3">Username</th>
              <th class="py-2.5 px-3">Display Name / Office</th>
              <th class="py-2.5 px-3">Assigned Mandal</th>
              <th class="py-2.5 px-3 text-center">Role</th>
              <th class="py-2.5 px-3 text-center">Status</th>
              <th class="py-2.5 px-3 text-center">Active Session</th>
              <th class="py-2.5 px-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            ${users.map((u, idx) => `
              <tr class="table-hover-row">
                <td class="py-2.5 px-3 font-mono text-slate-400">${idx + 1}</td>
                <td class="py-2.5 px-3 font-bold font-mono text-slate-900">${u.username}</td>
                <td class="py-2.5 px-3 font-medium">${u.display_name}</td>
                <td class="py-2.5 px-3">${u.mandal_name}</td>
                <td class="py-2.5 px-3 text-center">
                  <span class="px-2 py-0.5 rounded text-[10px] font-bold ${u.role === 'SUPER_ADMIN' ? 'bg-amber-500 text-slate-950' : 'bg-govblue-100 text-govblue-900'}">${u.role}</span>
                </td>
                <td class="py-2.5 px-3 text-center">
                  ${u.is_locked ? `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-600 text-white">LOCKED (5 Failed)</span>` : `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800">ACTIVE</span>`}
                </td>
                <td class="py-2.5 px-3 text-center">
                  ${u.has_active_session ? `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-green-100 text-green-800">${u.active_session_count > 1 ? `${u.active_session_count} SESSIONS` : 'LOGGED IN'}</span>` : `<span class="text-slate-400 text-[10px]">OFFLINE</span>`}
                </td>
                <td class="py-2.5 px-3 text-right space-x-1.5">
                  ${u.is_locked ? `<button onclick="handleUnlockUser(${u.id}, '${u.username}')" class="px-2 py-1 bg-rose-600 hover:bg-rose-700 text-white rounded text-[11px] font-bold">Unlock</button>` : ''}
                  <button onclick="handleAdminResetPassword(${u.id}, '${u.username}')" class="px-2 py-1 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded text-[11px]">Reset Pwd</button>
                  ${u.has_active_session ? `<button onclick="handleAdminForceLogout('${u.username}')" class="px-2 py-1 bg-amber-50 text-amber-900 hover:bg-amber-100 rounded text-[11px] font-bold">Terminate Session(s)</button>` : ''}
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
    document.getElementById("users-table-wrap").innerHTML = rowsHtml;
  } catch (err) {
    document.getElementById("users-table-wrap").innerHTML = `<div class="py-4 text-center text-red-500">${err.message}</div>`;
  }
}

async function handleUnlockUser(userId, username) {
  try {
    const res = await fetchAPI(`/admin/users/${userId}/unlock`, { method: "POST" });
    alert(res.message);
    renderUserManagementView();
  } catch (err) {
    alert("Unlock failed: " + (err.detail || err.message));
  }
}

async function handleAdminResetPassword(userId, username) {
  const newPwd = prompt(`Enter new password for ${username} (min 6 chars):`, "Mandal@2026");
  if (!newPwd) return;

  try {
    const res = await fetchAPI(`/admin/users/${userId}/reset-password?new_password=${encodeURIComponent(newPwd)}`, { method: "POST" });
    alert(res.message);
  } catch (err) {
    alert("Reset failed: " + (err.detail || err.message));
  }
}

async function handleAdminForceLogout(username) {
  if (!confirm(`Are you sure you want to force logout user ${username}?`)) return;
  try {
    const res = await fetchAPI("/auth/force-logout", {
      method: "POST",
      body: JSON.stringify({ username: username })
    });
    alert(res.message);
    renderUserManagementView();
  } catch (err) {
    alert("Force logout error: " + (err.detail || err.message));
  }
}

async function renderSessionsHistoryView() {
  const container = document.getElementById("view-sessions-history");
  container.innerHTML = `
    <div class="flex justify-between items-center mb-5">
      <div>
        <h2 class="text-xl font-bold text-slate-900">Active Sessions & Security Login History</h2>
        <p class="text-xs text-slate-500">Multi-user concurrent session tracking, IP logging, and independent device auditing</p>
      </div>
    </div>

    <!-- Active Sessions -->
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden mb-6">
      <div class="p-4 bg-slate-50 border-b flex justify-between items-center">
        <h3 class="font-bold text-xs text-slate-800 uppercase tracking-wider flex items-center">
          <i data-lucide="radio" class="w-4 h-4 mr-2 text-emerald-600 animate-pulse"></i> Live Active User Sessions (Multi-User Concurrent Enabled)
        </h3>
        <button onclick="renderSessionsHistoryView()" class="text-xs text-slate-600 hover:text-slate-900 flex items-center">
          <i data-lucide="refresh-cw" class="w-3.5 h-3.5 mr-1"></i> Refresh
        </button>
      </div>
      <div id="active-sessions-table-wrap" class="p-4 text-center text-slate-400">Loading active sessions...</div>
    </div>

    <!-- Login History -->
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <div class="p-4 bg-slate-50 border-b">
        <h3 class="font-bold text-xs text-slate-800 uppercase tracking-wider flex items-center">
          <i data-lucide="shield" class="w-4 h-4 mr-2 text-govblue-900"></i> Authentication & Access Attempt Logs
        </h3>
      </div>
      <div id="login-history-table-wrap" class="p-4 text-center text-slate-400">Loading login history...</div>
    </div>
  `;
  lucide.createIcons();

  try {
    const [sessions, history] = await Promise.all([
      fetchAPI("/auth/active-sessions"),
      fetchAPI("/auth/login-history?limit=100")
    ]);

    // Render active sessions
    let sessHtml = `
      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs text-slate-700">
          <thead class="text-slate-500 border-b">
            <tr>
              <th class="py-2">User / Role</th>
              <th class="py-2">Mandal</th>
              <th class="py-2">IP Address</th>
              <th class="py-2">Device Information</th>
              <th class="py-2">Login Time</th>
              <th class="py-2">Last Activity</th>
              <th class="py-2 text-right">Action</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            ${sessions.map(s => `
              <tr class="table-hover-row">
                <td class="py-2.5 font-bold text-slate-900">${s.username} (${s.role})</td>
                <td class="py-2.5">${s.mandal_name}</td>
                <td class="py-2.5 font-mono">${s.ip_address}</td>
                <td class="py-2.5 text-[11px] text-slate-500 max-w-xs truncate">${s.device_info}</td>
                <td class="py-2.5 text-slate-600">${s.login_datetime}</td>
                <td class="py-2.5 font-mono text-emerald-700 font-bold">${s.last_activity}</td>
                <td class="py-2.5 text-right">
                  <button onclick="handleForceLogoutSession('${s.session_id}')" class="px-2.5 py-1 bg-rose-600 hover:bg-rose-700 text-white rounded font-bold text-[11px]">Force Logout</button>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
    document.getElementById("active-sessions-table-wrap").innerHTML = sessHtml;

    // Render login history
    let histHtml = `
      <div class="overflow-x-auto max-h-96">
        <table class="w-full text-left text-xs text-slate-700">
          <thead class="text-slate-500 border-b sticky top-0 bg-white">
            <tr>
              <th class="py-2">Timestamp</th>
              <th class="py-2">Username Attempted</th>
              <th class="py-2">IP Address</th>
              <th class="py-2">Status</th>
              <th class="py-2">Reason / Details</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            ${history.map(h => `
              <tr class="table-hover-row">
                <td class="py-2 text-slate-500 font-mono text-[11px]">${h.created_at}</td>
                <td class="py-2 font-bold font-mono">${h.username_attempted}</td>
                <td class="py-2 font-mono text-slate-600">${h.ip_address}</td>
                <td class="py-2">
                  <span class="px-2 py-0.5 rounded text-[10px] font-bold ${h.status === 'SUCCESS' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}">${h.status}</span>
                </td>
                <td class="py-2 text-slate-600">${h.reason || '-'}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
    document.getElementById("login-history-table-wrap").innerHTML = histHtml;

  } catch (err) {
    console.error("Sessions load error", err);
  }
}

async function handleForceLogoutSession(sessionId) {
  if (!confirm("Are you sure you want to terminate this active session?")) return;
  try {
    const res = await fetchAPI("/auth/force-logout", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId })
    });
    alert(res.message);
    renderSessionsHistoryView();
  } catch (err) {
    alert("Force logout error: " + (err.detail || err.message));
  }
}

async function renderAuditLogsView() {
  const container = document.getElementById("view-audit-logs");
  container.innerHTML = `
    <div class="flex justify-between items-center mb-5">
      <div>
        <h2 class="text-xl font-bold text-slate-900">System Audit Trail</h2>
        <p class="text-xs text-slate-500">Permanent tamper-resistant log of all administrative actions and employee modifications</p>
      </div>
    </div>
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden p-4">
      <div id="audit-table-wrap" class="overflow-x-auto text-xs text-center py-6 text-slate-400">Loading audit trail...</div>
    </div>
  `;
  lucide.createIcons();

  try {
    const logs = await fetchAPI("/admin/audit-logs?limit=150");
    let rowsHtml = `
      <table class="w-full text-left text-xs text-slate-700">
        <thead class="bg-slate-50 border-b text-[11px] font-bold text-slate-600 uppercase">
          <tr>
            <th class="py-2.5 px-3">Timestamp</th>
            <th class="py-2.5 px-3">Official User</th>
            <th class="py-2.5 px-3">Action Type</th>
            <th class="py-2.5 px-3">Entity Type</th>
            <th class="py-2.5 px-3">Entity ID</th>
            <th class="py-2.5 px-3">Action Description</th>
            <th class="py-2.5 px-3">IP Address</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          ${logs.map(l => `
            <tr class="table-hover-row">
              <td class="py-2 px-3 text-slate-500 font-mono text-[11px]">${l.timestamp}</td>
              <td class="py-2 px-3 font-bold font-mono text-slate-900">${l.username}</td>
              <td class="py-2 px-3 font-semibold text-govblue-900">${l.action}</td>
              <td class="py-2 px-3 font-mono text-slate-600">${l.entity_type}</td>
              <td class="py-2 px-3 font-mono font-bold">${l.entity_id || '-'}</td>
              <td class="py-2 px-3 text-slate-700 max-w-sm truncate">${l.details || '-'}</td>
              <td class="py-2 px-3 font-mono text-slate-500">${l.ip_address}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
    document.getElementById("audit-table-wrap").innerHTML = rowsHtml;
  } catch (err) {
    document.getElementById("audit-table-wrap").innerHTML = `<div class="py-4 text-center text-red-500">${err.message}</div>`;
  }
}

// ==========================================
// MODAL CONTROLLER
// ==========================================
function openModal(title, bodyHtml) {
  document.getElementById("modal-title").textContent = title;
  document.getElementById("modal-body").innerHTML = bodyHtml;
  document.getElementById("app-modal").classList.remove("hidden");
  lucide.createIcons();
}

function closeModal() {
  document.getElementById("app-modal").classList.add("hidden");
  document.getElementById("modal-body").innerHTML = "";
}
