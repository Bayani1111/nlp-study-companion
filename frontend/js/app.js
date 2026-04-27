/**
 * Hash-based SPA router.
 */

const routes = {
  "#login": () => renderLogin(),
  "#register": () => renderRegister(),
  "#chat": () => renderChat(),
  "#tasks": () => renderTasks(),
  "#plans": () => renderTasks(),
  "#stats": () => renderStats(),
  "#settings": () => renderSettings(),
};

const protectedRoutes = ["#chat", "#tasks", "#plans", "#stats", "#settings"];

function isLoggedIn() {
  return !!localStorage.getItem("user");
}

async function restoreUserFromSession() {
  if (isLoggedIn()) return;

  try {
    const user = await api.get("/auth/profile");
    localStorage.setItem("user", JSON.stringify(user));
  } catch {
    api.clearClientSession();
  }
}

function updateNavbar(hash) {
  document.querySelectorAll(".nav-links a").forEach((link) => {
    link.classList.toggle("active", link.getAttribute("href") === hash);
  });

  const navbar = document.getElementById("navbar");
  if (!navbar) return;

  navbar.style.display = isLoggedIn() ? "flex" : "none";
  if (!isLoggedIn()) return;

  try {
    const user = JSON.parse(localStorage.getItem("user") || "{}");
    const nameEl = document.getElementById("nav-username");
    if (nameEl) {
      nameEl.textContent = user.nickname || user.username || "";
    }
  } catch {
    // Ignore cache parsing issues.
  }
}

function navigate() {
  const hash = window.location.hash || "#login";

  if (protectedRoutes.includes(hash) && !isLoggedIn()) {
    window.location.hash = "#login";
    return;
  }

  if ((hash === "#login" || hash === "#register") && isLoggedIn()) {
    window.location.hash = "#chat";
    return;
  }

  updateNavbar(hash);

  const handler = routes[hash];
  if (handler) {
    handler();
  } else {
    window.location.hash = isLoggedIn() ? "#chat" : "#login";
  }
}

async function logout() {
  try {
    await api.post("/auth/logout");
  } catch {
    // Cookie cleanup is best effort.
  }

  api.clearClientSession();
  window.location.hash = "#login";
}

function renderSettings() {
  const app = document.getElementById("app");
  app.innerHTML = `
    <div class="settings-container card">
      <h2>提醒设置</h2>
      <p class="section-note">这些设置会影响即将到期和逾期任务的提醒节奏。</p>
      <div id="settings-form">正在加载...</div>
    </div>
  `;
  loadSettings();
}

function maybeFocusToneSettings() {
  if (sessionStorage.getItem("focus_settings_tone") !== "1") return;
  sessionStorage.removeItem("focus_settings_tone");
  const toneSelect = document.getElementById("s-tone-style");
  if (!toneSelect) return;
  toneSelect.focus();
  toneSelect.scrollIntoView({ behavior: "smooth", block: "center" });
}

function formatToneSource(source) {
  if (source === "manual") return "当前来源：手动设置";
  if (source === "auto") return "当前来源：对话自动学习";
  return "当前来源：系统默认";
}

function formatToneStyle(style) {
  if (style === "direct") return "直接务实";
  if (style === "motivational") return "激励推进";
  return "温和耐心";
}

async function loadSettings() {
  const container = document.getElementById("settings-form");

  try {
    const [settings, preferences] = await Promise.all([
      api.get("/reminders/settings"),
      api.get("/auth/preferences"),
    ]);
    container.innerHTML = `
      <h3>伴学风格</h3>
      <div class="form-group" id="tone-settings-group">
        <label>回复语气</label>
        <select class="form-control" id="s-tone-style">
          <option value="gentle" ${preferences.companion_tone_style === "gentle" ? "selected" : ""}>温和耐心（默认）</option>
          <option value="direct" ${preferences.companion_tone_style === "direct" ? "selected" : ""}>直接务实</option>
          <option value="motivational" ${preferences.companion_tone_style === "motivational" ? "selected" : ""}>激励推进</option>
        </select>
        <p class="section-note">${formatToneSource(preferences.companion_tone_source)}</p>
        <p class="section-note">当前生效语气：${formatToneStyle(preferences.companion_tone_effective_style)}</p>
        <p class="section-note">手动语气：${preferences.companion_tone_manual_style ? formatToneStyle(preferences.companion_tone_manual_style) : "未设置"}</p>
      </div>
      <div class="form-group">
        <label>
          <input type="checkbox" id="s-tone-locked" ${preferences.companion_tone_locked ? "checked" : ""}>
          手动优先锁定（开启后不被自动学习覆盖）
        </label>
      </div>
      <h3>提醒设置</h3>
      <div class="form-group">
        <label>提前提醒（分钟）</label>
        <input class="form-control" type="number" id="s-before-due" value="${settings.before_due_minutes}" min="0" max="1440">
      </div>
      <div class="form-group">
        <label>逾期提醒</label>
        <select class="form-control" id="s-overdue">
          <option value="true" ${settings.overdue_enabled ? "selected" : ""}>开启</option>
          <option value="false" ${!settings.overdue_enabled ? "selected" : ""}>关闭</option>
        </select>
      </div>
      <div class="form-group">
        <label>静默开始时间（0-23）</label>
        <input class="form-control" type="number" id="s-quiet-start" value="${settings.quiet_start_hour}" min="0" max="23">
      </div>
      <div class="form-group">
        <label>静默结束时间（0-23）</label>
        <input class="form-control" type="number" id="s-quiet-end" value="${settings.quiet_end_hour}" min="0" max="23">
      </div>
      <button class="btn btn-primary" onclick="saveSettings()">保存设置</button>
    `;
    maybeFocusToneSettings();
  } catch (error) {
    container.innerHTML = `<div class="empty-state compact">${escapeHtml(error.message)}</div>`;
  }
}

async function saveSettings() {
  try {
    await Promise.all([
      api.put("/reminders/settings", {
        before_due_minutes: parseInt(document.getElementById("s-before-due").value, 10),
        overdue_enabled: document.getElementById("s-overdue").value === "true",
        quiet_start_hour: parseInt(document.getElementById("s-quiet-start").value, 10),
        quiet_end_hour: parseInt(document.getElementById("s-quiet-end").value, 10),
      }),
      api.put("/auth/preferences", {
        companion_tone_style: document.getElementById("s-tone-style").value,
        companion_tone_locked: document.getElementById("s-tone-locked").checked,
      }),
    ]);
    showToast("设置已保存", "提醒策略与伴学风格（含锁定开关）已更新。", "success");
  } catch (error) {
    showToast("保存失败", error.message, "error");
  }
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}

window.addEventListener("hashchange", navigate);
window.addEventListener("DOMContentLoaded", async () => {
  await restoreUserFromSession();
  navigate();
  if (isLoggedIn()) {
    connectReminderWS();
  }
});
