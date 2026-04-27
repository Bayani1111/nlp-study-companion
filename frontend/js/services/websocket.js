/**
 * Reminder WebSocket client.
 * - Uses same-origin cookies for authentication.
 * - Reconnects automatically and keeps the connection alive with ping/pong.
 */

let _ws = null;
let _reconnectAttempts = 0;
let _heartbeatTimer = null;
let _reconnectTimer = null;
let _toastCounter = 0;

const MAX_RECONNECT_DELAY = 30000;
const toastActionRegistry = new Map();

function hasActiveSession() {
  return !!localStorage.getItem('user');
}

function connectReminderWS() {
  if (!hasActiveSession()) return;

  if (_ws) {
    _ws.onclose = null;
    _ws.close();
  }

  clearTimeout(_reconnectTimer);
  clearInterval(_heartbeatTimer);

  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${protocol}//${location.host}/ws/reminders`;

  _ws = new WebSocket(url);
  window.reminderWS = _ws;

  _ws.onopen = () => {
    _reconnectAttempts = 0;
    _heartbeatTimer = setInterval(() => {
      if (_ws && _ws.readyState === WebSocket.OPEN) {
        _ws.send('ping');
      }
    }, 30000);
  };

  _ws.onmessage = (event) => {
    if (event.data === 'pong') return;

    try {
      handleReminder(JSON.parse(event.data));
    } catch {
      // Ignore non-JSON payloads.
    }
  };

  _ws.onclose = () => {
    clearInterval(_heartbeatTimer);
    scheduleReconnect();
  };
}

function scheduleReconnect() {
  if (!hasActiveSession()) return;
  _reconnectAttempts += 1;
  const delay = Math.min(1000 * Math.pow(2, _reconnectAttempts - 1), MAX_RECONNECT_DELAY);
  _reconnectTimer = setTimeout(() => {
    connectReminderWS();
  }, delay);
}

function handleReminder(data) {
  const typeLabels = {
    approaching_deadline: "任务即将到期",
    overdue: "任务已经逾期",
    overdue_critical: "任务长时间逾期",
    phase_checkpoint: "阶段提醒",
  };
  const title = typeLabels[data.type] || "任务提醒";
  const body = data.type === "phase_checkpoint"
    ? `${data.plan_title || "当前计划"}的阶段“${data.phase_title || "未命名阶段"}”即将结束，还有 ${data.remaining_task_count || 0} 个任务待完成。`
    : data.task_title || "你有一条任务需要留意。";
  showToast(title, body, data.type === "overdue_critical" ? "error" : "warning", {
    actionLabel: "查看任务",
    action: () => {
      window.location.hash = "#tasks";
    },
  });
}

function showToast(title, body, variant = "info", options = {}) {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `toast toast-${variant}`;

  const actionId = options.action ? `toast-action-${_toastCounter++}` : null;
  if (actionId && options.action) {
    toastActionRegistry.set(actionId, options.action);
  }

  toast.innerHTML = `
    <div class="toast-head">
      <div class="toast-title">${escapeHtmlSafe(title)}</div>
      <button class="toast-close" type="button" aria-label="关闭提示">×</button>
    </div>
    <div class="toast-body">${escapeHtmlSafe(body)}</div>
    ${
      actionId && options.actionLabel
        ? `<button class="toast-action" type="button" data-toast-action="${actionId}">${escapeHtmlSafe(options.actionLabel)}</button>`
        : ""
    }
    <div class="toast-progress"><div class="toast-progress-bar"></div></div>
  `;

  const duration = options.duration ?? 4500;
  toast.style.setProperty("--toast-duration-ms", `${duration}ms`);
  let closed = false;
  const actionButton = toast.querySelector("[data-toast-action]");
  toast.tabIndex = 0;

  const closeToast = () => {
    if (closed) return;
    closed = true;
    window.removeEventListener("keydown", onKeydown);
    toast.style.opacity = "0";
    toast.style.transform = "translateY(-6px)";
    toast.style.transition = "opacity .25s ease, transform .25s ease";
    setTimeout(() => {
      if (actionId) {
        toastActionRegistry.delete(actionId);
      }
      toast.remove();
    }, 250);
  };

  toast.querySelector(".toast-close")?.addEventListener("click", closeToast);
  actionButton?.addEventListener("click", (event) => {
    const target = event.currentTarget;
    const handler = toastActionRegistry.get(target.dataset.toastAction);
    if (handler) {
      handler();
    }
    closeToast();
  });
  const onKeydown = (event) => {
    if (closed) return;
    if (!document.body.contains(toast)) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closeToast();
      return;
    }
    if (event.key === "Enter" && actionButton) {
      event.preventDefault();
      actionButton.click();
    }
  };
  window.addEventListener("keydown", onKeydown);

  container.appendChild(toast);
  toast.focus({ preventScroll: true });

  setTimeout(closeToast, duration);
}

function escapeHtmlSafe(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}
