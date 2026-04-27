/**
 * Chat page.
 */

let currentSessionId = null;
let lastFailedMessage = "";
let currentTonePreference = null;
let toneControlsCollapsed = true;
const TONE_CONTROLS_STATE_KEY = "chat_tone_controls_collapsed";
const TONE_INDICATOR_MINI_KEY = "chat_tone_indicator_mini";
let toneIndicatorMini = false;
let latestPreferenceUndoToken = 0;

function formatToneStyleLabel(style) {
  if (style === "direct") return "直接务实";
  if (style === "motivational") return "激励推进";
  return "温和耐心";
}

function formatToneSourceLabel(source) {
  if (source === "manual") return "手动设置";
  if (source === "auto") return "对话自动学习";
  return "系统默认";
}

function renderToneIndicator() {
  return `
    <div class="chat-tone-indicator" id="chat-tone-indicator">
      <button class="chat-tone-mini-toggle" id="chat-tone-mini-toggle" onclick="toggleToneIndicatorMini()" type="button" title="切换最小化显示">◐</button>
      <button class="chat-tone-summary" id="chat-tone-summary" onclick="openToneSettings()" type="button">正在加载伴学语气...</button>
      <button class="btn btn-outline btn-sm" id="chat-tone-toggle" type="button" onclick="toggleToneControls()">展开控制</button>
      <div class="chat-tone-controls chat-tone-controls-collapsed" id="chat-tone-controls">
        <select class="chat-tone-quick-select" id="chat-tone-quick-select" onchange="quickChangeToneStyle()">
          <option value="gentle">温和耐心</option>
          <option value="direct">直接务实</option>
          <option value="motivational">激励推进</option>
        </select>
        <label class="chat-tone-lock-toggle">
          <input type="checkbox" id="chat-tone-lock" onchange="quickToggleToneLock()">
          锁定
        </label>
      </div>
    </div>
  `;
}

function getToneIndicatorElements() {
  return {
    indicator: document.getElementById("chat-tone-indicator"),
    controls: document.getElementById("chat-tone-controls"),
    toggle: document.getElementById("chat-tone-toggle"),
    summary: document.getElementById("chat-tone-summary"),
    quickSelect: document.getElementById("chat-tone-quick-select"),
    lockToggle: document.getElementById("chat-tone-lock"),
    miniToggle: document.getElementById("chat-tone-mini-toggle"),
  };
}

function applyToneIndicatorUiState() {
  const { indicator, controls, toggle } = getToneIndicatorElements();
  if (!indicator || !controls || !toggle) return;
  indicator.classList.toggle("chat-tone-indicator-mini", toneIndicatorMini);
  controls.classList.toggle("chat-tone-controls-collapsed", toneControlsCollapsed);
  toggle.textContent = toneControlsCollapsed ? "展开控制" : "收起控制";
  toggle.setAttribute("aria-expanded", toneControlsCollapsed ? "false" : "true");
}

function renderChat() {
  const app = document.getElementById("app");
  app.innerHTML = `
    <div class="chat-layout">
      <aside class="chat-sidebar">
        <div class="sidebar-header">
          <button class="btn btn-primary btn-sm full-width" onclick="createSession()">+ 新对话</button>
          <p class="sidebar-tip">把一句自然语言拆成任务、计划和提醒，让系统陪你一步步推进。</p>
        </div>
        <div class="session-list" id="session-list">正在加载对话...</div>
      </aside>

      <section class="chat-main">
        ${renderToneIndicator()}
        <div class="chat-messages" id="chat-messages">
          <div class="chat-empty">
            <h3>从一句自然语言开始</h3>
            <p>比如：帮我做一个下周高数复习计划，并记录今天先做的第一项任务。</p>
          </div>
        </div>
        <div class="chat-input-bar">
          <input
            type="text"
            id="chat-input"
            placeholder="输入任务、学习安排或复习计划"
            onkeydown="if(event.key==='Enter'){sendMessage();}"
          >
          <button class="btn btn-primary" id="chat-send-button" onclick="sendMessage()">发送</button>
        </div>
      </section>
    </div>
  `;

  toneControlsCollapsed = localStorage.getItem(TONE_CONTROLS_STATE_KEY) !== "0";
  toneIndicatorMini = localStorage.getItem(TONE_INDICATOR_MINI_KEY) === "1";
  applyToneIndicatorUiState();

  currentSessionId = null;
  loadToneIndicator();
  loadSessions();
}

function toggleToneControls() {
  toneControlsCollapsed = !toneControlsCollapsed;
  applyToneIndicatorUiState();
  localStorage.setItem(TONE_CONTROLS_STATE_KEY, toneControlsCollapsed ? "1" : "0");
}

function toggleToneIndicatorMini() {
  toneIndicatorMini = !toneIndicatorMini;
  applyToneIndicatorUiState();
  localStorage.setItem(TONE_INDICATOR_MINI_KEY, toneIndicatorMini ? "1" : "0");
}

function openToneSettings() {
  sessionStorage.setItem("focus_settings_tone", "1");
  window.location.hash = "#settings";
}

function pushPreferenceUndo({
  title,
  body,
  rollbackPayloadFactory,
  rollbackSuccessMessage,
}) {
  const undoToken = ++latestPreferenceUndoToken;
  showToast(title, body, "success", {
    actionLabel: "撤销",
    duration: 5000,
    action: async () => {
      if (undoToken !== latestPreferenceUndoToken) return;
      try {
        const rollbackPayload = rollbackPayloadFactory();
        currentTonePreference = await api.put("/auth/preferences", rollbackPayload);
        await loadToneIndicator();
        showToast("已恢复", rollbackSuccessMessage, "success");
      } catch (error) {
        showToast("撤销失败", error.message, "error");
      }
    },
  });
}

async function loadToneIndicator() {
  const { summary, quickSelect, lockToggle, miniToggle } = getToneIndicatorElements();
  if (!summary || !quickSelect || !lockToggle) return;
  try {
    const preferences = await api.get("/auth/preferences");
    currentTonePreference = preferences;
    const effectiveStyle = preferences.companion_tone_effective_style || preferences.companion_tone_style;
    const toneLabel = formatToneStyleLabel(effectiveStyle);
    const sourceLabel = formatToneSourceLabel(preferences.companion_tone_source);
    const lockLabel = preferences.companion_tone_locked ? "已锁定" : "未锁定";
    summary.textContent = `当前伴学语气：${toneLabel}（${sourceLabel}，${lockLabel}）`;
    if (miniToggle) {
      miniToggle.title = `当前语气：${toneLabel}（${sourceLabel}，${lockLabel}）`;
      miniToggle.setAttribute("aria-label", miniToggle.title);
    }
    quickSelect.value = preferences.companion_tone_manual_style || preferences.companion_tone_style || "gentle";
    lockToggle.checked = !!preferences.companion_tone_locked;
  } catch (error) {
    summary.textContent = `当前伴学语气加载失败：${error.message}`;
    if (miniToggle) {
      miniToggle.title = summary.textContent;
      miniToggle.setAttribute("aria-label", summary.textContent);
    }
  }
}

async function quickChangeToneStyle() {
  const quickSelect = document.getElementById("chat-tone-quick-select");
  const lockToggle = document.getElementById("chat-tone-lock");
  if (!quickSelect || !lockToggle) return;
  const nextStyle = quickSelect.value;
  const previousStyle = currentTonePreference?.companion_tone_style || "gentle";
  if (nextStyle === previousStyle) return;

  quickSelect.disabled = true;
  lockToggle.disabled = true;
  try {
    const payload = {
      companion_tone_style: nextStyle,
      companion_tone_locked: currentTonePreference?.companion_tone_locked || false,
    };
    currentTonePreference = await api.put("/auth/preferences", payload);
    await loadToneIndicator();
    pushPreferenceUndo({
      title: "语气已切换",
      body: `已切换为${formatToneStyleLabel(nextStyle)}。5秒内可撤销。`,
      rollbackPayloadFactory: () => ({
        companion_tone_style: previousStyle,
        companion_tone_locked: currentTonePreference?.companion_tone_locked || false,
      }),
      rollbackSuccessMessage: `已恢复为${formatToneStyleLabel(previousStyle)}。`,
    });
  } catch (error) {
    quickSelect.value = previousStyle;
    showToast("切换失败", error.message, "error");
  } finally {
    quickSelect.disabled = false;
    lockToggle.disabled = false;
  }
}

async function quickToggleToneLock() {
  const lockToggle = document.getElementById("chat-tone-lock");
  const quickSelect = document.getElementById("chat-tone-quick-select");
  if (!lockToggle || !quickSelect) return;
  const previousLocked = !!currentTonePreference?.companion_tone_locked;
  const nextLocked = lockToggle.checked;
  if (nextLocked === previousLocked) return;

  lockToggle.disabled = true;
  quickSelect.disabled = true;
  try {
    const payload = {
      companion_tone_style: currentTonePreference?.companion_tone_style || quickSelect.value || "gentle",
      companion_tone_locked: nextLocked,
    };
    currentTonePreference = await api.put("/auth/preferences", payload);
    await loadToneIndicator();
    pushPreferenceUndo({
      title: "锁定状态已更新",
      body: `${nextLocked ? "已开启手动优先锁定" : "已关闭手动优先锁定"}，5秒内可撤销。`,
      rollbackPayloadFactory: () => ({
        companion_tone_style: currentTonePreference?.companion_tone_style || quickSelect.value || "gentle",
        companion_tone_locked: previousLocked,
      }),
      rollbackSuccessMessage: previousLocked ? "已恢复为锁定状态。" : "已恢复为未锁定状态。",
    });
  } catch (error) {
    lockToggle.checked = previousLocked;
    showToast("更新失败", error.message, "error");
  } finally {
    lockToggle.disabled = false;
    quickSelect.disabled = false;
  }
}

async function loadSessions() {
  const list = document.getElementById("session-list");
  if (!list) return;

  try {
    const sessions = await api.get("/chat/sessions");
    if (!sessions.length) {
      list.innerHTML = '<div class="empty-state compact">还没有对话，先发一条消息试试。</div>';
      return;
    }

    list.innerHTML = sessions
      .map(
        (session) => `
        <div class="session-item ${session.id === currentSessionId ? "active" : ""}" onclick="switchSession(${session.id})">
          <span class="session-title">${escapeChatHtml(session.title || "新对话")}</span>
          <button class="del-btn" onclick="event.stopPropagation();deleteSession(${session.id})" title="删除对话">×</button>
        </div>
      `,
      )
      .join("");
  } catch (error) {
    list.innerHTML = `<div class="empty-state compact">${escapeChatHtml(error.message)}</div>`;
  }
}

function createSession() {
  currentSessionId = null;
  const container = document.getElementById("chat-messages");
  if (container) {
    container.innerHTML = `
      <div class="chat-empty">
        <h3>新对话已准备好</h3>
        <p>你可以继续输入任务、学习计划或提醒需求。</p>
      </div>
    `;
  }
  document.getElementById("chat-input")?.focus();
  loadSessions();
}

async function switchSession(sessionId) {
  currentSessionId = sessionId;
  await loadSessions();
  await loadMessages(sessionId);
}

async function loadMessages(sessionId) {
  const container = document.getElementById("chat-messages");
  if (!container) return;

  try {
    const messages = await api.get(`/chat/sessions/${sessionId}`);
    const visibleMessages = messages.filter((message) => message.role !== "system");

    if (!visibleMessages.length) {
      container.innerHTML = '<div class="empty-state compact">这段对话还没有消息。</div>';
      return;
    }

    container.innerHTML = visibleMessages.map((message) => renderMessageBubble(message)).join("");
    const proposalState = findProposalStatusFromHistory(visibleMessages, sessionId);
    renderProposalCommitDock(proposalState);
    container.scrollTop = container.scrollHeight;
  } catch (error) {
    container.innerHTML = `<div class="empty-state compact">${escapeChatHtml(error.message)}</div>`;
  }
}

const PROPOSAL_SCENARIO_LABELS = {
  exam_prep: "考试备考",
  course_exploration: "课程学习",
  skill_building: "技能提升",
  general_learning: "通用学习",
};

function findLatestScenarioFromHistory(messages) {
  if (!Array.isArray(messages)) return { scenario_type: "general_learning", scenario_label: "通用学习" };
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i];
    const entities = m?.entities || {};
    const gt = entities.goal_type;
    if (gt && PROPOSAL_SCENARIO_LABELS[gt]) {
      return { scenario_type: gt, scenario_label: PROPOSAL_SCENARIO_LABELS[gt] };
    }
  }
  return { scenario_type: "general_learning", scenario_label: "通用学习" };
}

function findProposalStatusFromHistory(messages, sessionId) {
  if (!Array.isArray(messages) || !messages.length) {
    return null;
  }
  let pending = null;
  for (let i = 0; i < messages.length; i += 1) {
    const m = messages[i];
    if (m.role !== "assistant") continue;
    if (m.intent !== "plan_proposal" || !m.entities) continue;
    const pack = m.entities.pending_action_proposal;
    if (pack && pack.proposal_id) {
      const st = m.entities.goal_type || (pack.entities && pack.entities.goal_type) || "general_learning";
      pending = {
        index: i,
        proposal_id: String(pack.proposal_id),
        scenario_type: st,
        scenario_label: PROPOSAL_SCENARIO_LABELS[st] || "通用学习",
        session_id: sessionId,
      };
    }
  }
  if (!pending) {
    return null;
  }
  let last = null; // { type: 'success' } | { type: 'failed' }
  for (let j = pending.index + 1; j < messages.length; j += 1) {
    const m = messages[j];
    if (m.role !== "assistant") continue;
    if (m.intent === "create_plan" || m.intent === "refine_plan") {
      last = { type: "success" };
    }
    if (m.intent === "action_failed") {
      const e = m.entities || {};
      const fp = e.failed_proposal_id;
      const legacyP = e.pending_action_proposal && e.pending_action_proposal.proposal_id;
      const pid = fp != null && fp !== "" ? String(fp) : legacyP ? String(legacyP) : null;
      if (pid && String(pid) !== String(pending.proposal_id)) {
        continue;
      }
      last = { type: "failed", proposal_id: String(pending.proposal_id) };
    }
  }
  if (last && last.type === "success") {
    return null;
  }
  if (last && last.type === "failed") {
    const scenario = findLatestScenarioFromHistory(messages);
    return {
      status: "failed",
      proposal_id: last.proposal_id,
      session_id: sessionId,
      scenario_type: scenario.scenario_type,
      scenario_label: scenario.scenario_label,
    };
  }
  return {
    status: "pending",
    proposal_id: pending.proposal_id,
    session_id: sessionId,
    scenario_type: pending.scenario_type,
    scenario_label: pending.scenario_label,
  };
}

function renderProposalCommitDock(state) {
  const container = document.getElementById("chat-messages");
  if (!container) return;
  container.querySelector("#chat-proposal-dock")?.remove();
  if (!state || !state.status) {
    return;
  }
  if (state.status === "failed" && !state.proposal_id) {
    return;
  }
  const sessionId = state.session_id;
  const proposalId = state.proposal_id || "";
  const nextHint =
    state.next_prompt ||
    (state.status === "failed"
      ? "网络或服务异常时会出现这种情况，可直接重试；也可以先发一句「先精简成一周3个关键任务」再试。"
      : "确认要执行再点下面按钮。尚未入库前，任务页不会出现对应项。");

  const scenarioLine =
    state.scenario_label
      ? `<div class="chat-scenario-line"><span class="chat-scenario-chip">当前场景：${escapeChatHtml(
          state.scenario_label,
        )}</span></div>`
      : "";
  const scenarioSwitch = renderScenarioSwitchButtons({
    scenario_type: state.scenario_type || "general_learning",
  });

  const title =
    state.status === "failed"
      ? "上次未能写入学习记录"
      : "这一版方案尚未成为「正式计划 / 任务」";
  const sub =
    state.status === "failed"
      ? "对话里的草案还在，可一键重试提交；与下方历史提示一致即可。"
      : "下方气泡只是草案说明。点「加入计划」后，才会在「计划 / 任务」里生成条目，任务树中也会出现对应任务。";

  const mainBtn =
    state.status === "failed"
      ? `<button class="btn btn-primary btn-sm" type="button" onclick="submitPlanProposal('${escapeChatAttr(
          proposalId,
        )}','${escapeChatAttr(String(sessionId))}')">重试加入计划</button>`
      : `<button class="btn btn-primary btn-sm" type="button" onclick="submitPlanProposal('${escapeChatAttr(
          proposalId,
        )}','${escapeChatAttr(String(sessionId))}')" ${proposalId ? "" : "disabled"}>加入计划</button>`;
  const secondary = `<button class="btn btn-outline btn-sm" type="button" onclick="window.location.hash='#tasks'">去任务/计划页</button>`;
  const modeClass = state.status === "failed" ? "chat-proposal-dock--failed" : "chat-proposal-dock--pending";

  container.insertAdjacentHTML(
    "beforeend",
    `
    <div id="chat-proposal-dock" class="chat-proposal-dock ${modeClass}" role="region" aria-label="学习方案落库">
      <div class="chat-proposal-dock-title">${escapeChatHtml(title)}</div>
      <p class="chat-proposal-dock-sub">${escapeChatHtml(sub)}</p>
      <p class="chat-proposal-dock-hint">${escapeChatHtml(nextHint)}</p>
      ${scenarioLine}
      ${scenarioSwitch}
      <div class="chat-proposal-dock-actions">
        ${mainBtn}
        ${secondary}
      </div>
    </div>
  `,
  );
  container.scrollTop = container.scrollHeight;
}

function syncProposalCommitDockFromResponse(data) {
  if (!data) return;
  const sid = data.session_id || currentSessionId;
  if (data.intent === "plan_proposal" && data.proposal_id) {
    const st = data.scenario_type || "general_learning";
    renderProposalCommitDock({
      status: "pending",
      proposal_id: data.proposal_id,
      session_id: sid,
      next_prompt: data.next_prompt,
      scenario_type: st,
      scenario_label: data.scenario_label || PROPOSAL_SCENARIO_LABELS[st] || "通用学习",
    });
    return;
  }
  if (data.intent === "action_failed" && data.proposal_id) {
    const st = data.scenario_type || "general_learning";
    renderProposalCommitDock({
      status: "failed",
      proposal_id: data.proposal_id,
      session_id: sid,
      next_prompt: data.next_prompt,
      scenario_type: st,
      scenario_label: data.scenario_label || PROPOSAL_SCENARIO_LABELS[st] || "通用学习",
    });
    return;
  }
  if ((data.intent === "create_plan" || data.intent === "refine_plan") && Array.isArray(data.extracted_plans) && data.extracted_plans.length) {
    renderProposalCommitDock(null);
  }
}

function renderMessageBubble(message) {
  const content =
    message.role === "assistant"
      ? renderAssistantHtml(message.content)
      : escapeChatHtml(message.content).replace(/\n/g, "<br>");

  return `<div class="msg-bubble ${message.role}">${content}</div>`;
}

function setChatPendingState(isPending) {
  const input = document.getElementById("chat-input");
  const button = document.getElementById("chat-send-button");
  if (input) {
    input.disabled = isPending;
  }
  if (button) {
    button.disabled = isPending;
    button.textContent = isPending ? "整理中..." : "发送";
  }
}

function buildCreatedSummary(data) {
  if (data.sync_summary) {
    return data.sync_summary;
  }

  const createdTaskCount = Array.isArray(data.extracted_tasks) ? data.extracted_tasks.length : 0;
  const createdPlanCount = Array.isArray(data.extracted_plans) ? data.extracted_plans.length : 0;

  if (!createdTaskCount && !createdPlanCount) {
    return "";
  }

  const taskTitles = (data.extracted_tasks || [])
    .filter((task) => !task.parent_task_id)
    .map((task) => task.title)
    .slice(0, 2);
  const planTitle = data.extracted_plans?.[0]?.title || "";

  if (createdPlanCount && createdTaskCount) {
    return `已创建计划“${planTitle}”，并同步 ${createdTaskCount} 条任务到任务页。`;
  }
  if (createdPlanCount) {
    return `已创建计划“${planTitle}”，你可以去计划页继续细化。`;
  }
  return `已同步任务：${taskTitles.join("、") || "新的任务安排"}。`;
}

function applyNextPromptOptionFromButton(event) {
  const target = event.currentTarget;
  const option = target?.dataset?.option || "";
  const input = document.getElementById("chat-input");
  if (!option || !input) return;
  input.value = option;
  sendMessage();
}

function appendAssistantFeedback(data) {
  const container = document.getElementById("chat-messages");
  if (!container) return;

  if (data.intent === "plan_proposal") {
    return;
  }
  if (data.intent === "action_failed" && data.proposal_id) {
    return;
  }

  if (data.intent === "clarify_plan") {
    if (!data.next_prompt) return;
    const options = Array.isArray(data.next_prompt_options) ? data.next_prompt_options.filter(Boolean).slice(0, 2) : [];
    const optionsHtml = options.length
      ? `<div class="chat-guidance-options">
          ${options
            .map(
              (option) =>
                `<button class="btn btn-outline btn-sm" type="button" data-option="${escapeChatHtml(option)}" onclick="applyNextPromptOptionFromButton(event)">${escapeChatHtml(option)}</button>`,
            )
            .join("")}
        </div>`
      : "";

    container.insertAdjacentHTML(
      "beforeend",
      `
        <div class="chat-guidance-card">
          <div class="chat-guidance-label">继续聊这一点</div>
          <p>${escapeChatHtml(data.next_prompt)}</p>
          ${renderScenarioContext(data)}
          ${optionsHtml}
          ${renderScenarioSwitchButtons(data)}
        </div>
      `,
    );
    container.scrollTop = container.scrollHeight;
    return;
  }

  const summary = buildCreatedSummary(data);
  const nextPrompt = data.next_prompt || "";
  const nextOptions = Array.isArray(data.next_prompt_options) ? data.next_prompt_options.filter(Boolean).slice(0, 2) : [];
  if (!summary && !nextPrompt) return;

  container.insertAdjacentHTML(
    "beforeend",
    `
      <div class="chat-action-summary">
        <div class="chat-action-copy">
          ${summary ? `<strong>已同步到任务系统</strong><p>${escapeChatHtml(summary)}</p>` : ""}
          ${
            nextPrompt
              ? `<div class="chat-next-step"><span>接下来建议</span><p>${escapeChatHtml(nextPrompt)}</p>${
                  nextOptions.length
                    ? `<div class="chat-next-options">
                        ${nextOptions
                          .map(
                            (option) =>
                              `<button class="btn btn-outline btn-sm" type="button" data-option="${escapeChatHtml(option)}" onclick="applyNextPromptOptionFromButton(event)">${escapeChatHtml(option)}</button>`,
                          )
                          .join("")}
                      </div>`
                    : ""
                }</div>`
              : ""
          }
          ${renderScenarioContext(data)}
        </div>
        <div class="chat-action-links">
          <button class="btn btn-outline btn-sm" onclick="window.location.hash='#tasks'">查看任务页</button>
          ${
            Array.isArray(data.extracted_plans) && data.extracted_plans.length
              ? '<button class="btn btn-outline btn-sm" onclick="window.location.hash=\'#tasks\'">查看计划</button>'
              : ""
          }
        </div>
      </div>
    `,
  );
  container.scrollTop = container.scrollHeight;
}

function renderScenarioContext(data) {
  if (!data?.scenario_label) return "";
  return `<div class="chat-scenario-line"><span class="chat-scenario-chip">当前场景：${escapeChatHtml(data.scenario_label)}</span></div>`;
}

function renderScenarioSwitchButtons(data) {
  const current = data?.scenario_type || "";
  const options = [
    { type: "exam_prep", label: "切换到考试备考" },
    { type: "course_exploration", label: "切换到课程学习" },
    { type: "skill_building", label: "切换到技能提升" },
    { type: "general_learning", label: "切换到通用学习" },
  ].filter((item) => item.type !== current);
  if (!options.length) return "";
  return `
    <div class="chat-scenario-switch">
      ${options
        .map(
          (item) =>
            `<button class="btn btn-outline btn-sm" type="button" onclick="switchPlanningScenario('${item.type}')">${item.label}</button>`,
        )
        .join("")}
    </div>
  `;
}

function switchPlanningScenario(scenarioType) {
  const mapping = {
    exam_prep: "我想按考试备考场景来规划",
    course_exploration: "我想按课程学习场景来规划",
    skill_building: "我想按技能提升场景来规划",
    general_learning: "我想按通用学习场景来规划",
  };
  const input = document.getElementById("chat-input");
  if (!input) return;
  input.value = mapping[scenarioType] || "我想按通用学习场景来规划";
  sendMessage();
}

async function submitPlanProposal(proposalId, proposalSessionId) {
  if (!proposalId) {
    showToast("草案失效", "当前草案缺少标识，请先重新生成。", "error");
    return;
  }
  const targetSessionId = Number(proposalSessionId) || currentSessionId || null;
  const container = document.getElementById("chat-messages");
  if (!container) return;
  const loadingId = `proposal-loading-${Date.now()}`;
  container.insertAdjacentHTML(
    "beforeend",
    `<div class="msg-bubble assistant msg-bubble-loading" id="${loadingId}">正在把这版草案加入计划并生成任务...</div>`,
  );
  container.scrollTop = container.scrollHeight;

  try {
    const data = await api.post("/chat", {
      message: "加入计划",
      session_id: targetSessionId,
      proposal_id: proposalId,
    });
    document.getElementById(loadingId)?.remove();
    container.insertAdjacentHTML(
      "beforeend",
      `<div class="msg-bubble assistant">${renderAssistantHtml(data.reply)}</div>`,
    );
    appendAssistantFeedback(data);
    syncProposalCommitDockFromResponse(data);
    container.scrollTop = container.scrollHeight;
    if (!currentSessionId) currentSessionId = data.session_id;
    await loadSessions();
  } catch (error) {
    document.getElementById(loadingId)?.remove();
    showToast("加入计划失败", error.message, "error");
  }
}

async function sendMessage() {
  const input = document.getElementById("chat-input");
  const container = document.getElementById("chat-messages");
  if (!input || !container) return;

  const text = input.value.trim();
  if (!text) return;

  lastFailedMessage = "";
  setChatPendingState(true);

  if (container.querySelector(".chat-empty")) {
    container.innerHTML = "";
  }

  container.insertAdjacentHTML("beforeend", `<div class="msg-bubble user">${escapeChatHtml(text)}</div>`);
  input.value = "";
  container.scrollTop = container.scrollHeight;

  const loadingId = `loading-${Date.now()}`;
  container.insertAdjacentHTML(
    "beforeend",
    `<div class="msg-bubble assistant msg-bubble-loading" id="${loadingId}">我先帮你整理目标、同步任务，再给你一个更清晰的下一步建议...</div>`,
  );
  container.scrollTop = container.scrollHeight;

  try {
    const data = await api.post("/chat", {
      message: text,
      session_id: currentSessionId,
    });

    document.getElementById(loadingId)?.remove();
    container.insertAdjacentHTML(
      "beforeend",
      `<div class="msg-bubble assistant">${renderAssistantHtml(data.reply)}</div>`,
    );
    appendAssistantFeedback(data);
    syncProposalCommitDockFromResponse(data);
    container.scrollTop = container.scrollHeight;

    if (!currentSessionId) {
      currentSessionId = data.session_id;
    }
    await loadSessions();

    if (data.intent === "create_task" && Array.isArray(data.extracted_tasks) && data.extracted_tasks.length) {
      const parentTask = data.extracted_tasks.find((task) => !task.parent_task_id);
      const subtaskCount = data.extracted_tasks.filter((task) => task.parent_task_id).length;
      if (parentTask && subtaskCount) {
        showToast(
          "任务已记录",
          `已创建主任务“${parentTask.title}”，并拆成 ${subtaskCount} 个子任务。`,
          "success",
          {
            actionLabel: "打开任务页",
            action: () => {
              window.location.hash = "#tasks";
            },
          },
        );
      } else {
        const titles = data.extracted_tasks
          .map((task) => task.title)
          .filter(Boolean)
          .slice(0, 2)
          .join("、");
        showToast(
          "任务已记录",
          titles ? `已经同步到任务页：${titles}` : "聊天里提到的任务已经同步到任务页。",
          "success",
          {
            actionLabel: "打开任务页",
            action: () => {
              window.location.hash = "#tasks";
            },
          },
        );
      }
    }

    if (data.intent === "create_plan" && Array.isArray(data.extracted_plans) && data.extracted_plans.length) {
      const planTitle = data.extracted_plans[0].title;
      if (Array.isArray(data.extracted_tasks) && data.extracted_tasks.length) {
        const subtaskCount = data.extracted_tasks.filter((task) => task.parent_task_id).length;
        const detail = subtaskCount
          ? `计划“${planTitle}”已创建，并自动拆成 ${subtaskCount} 个子任务。`
          : `计划“${planTitle}”已创建，并绑定了对应任务。`;
        showToast("计划已创建", detail, "success", {
          actionLabel: "查看计划",
          action: () => {
            window.location.hash = "#tasks";
          },
        });
      } else {
        showToast("计划已创建", `学习计划“${planTitle}”已经同步到计划页。`, "success", {
          actionLabel: "查看计划",
          action: () => {
            window.location.hash = "#tasks";
          },
        });
      }
    }
  } catch (error) {
    lastFailedMessage = text;
    const loadingEl = document.getElementById(loadingId);
    if (loadingEl) {
      loadingEl.classList.remove("msg-bubble-loading");
      loadingEl.classList.add("msg-bubble-error");
      loadingEl.innerHTML = `
        <strong>发送失败</strong>
        <p>${escapeChatHtml(error.message)}</p>
        <button class="btn btn-outline btn-sm" onclick="retryLastFailedMessage()">重试刚才这条</button>
      `;
    }
    showToast("发送失败", error.message, "error");
  } finally {
    setChatPendingState(false);
  }
}

function retryLastFailedMessage() {
  if (!lastFailedMessage) return;
  const input = document.getElementById("chat-input");
  if (!input) return;
  input.value = lastFailedMessage;
  input.focus();
}

async function deleteSession(sessionId) {
  if (!confirm("确定删除这段对话吗？")) return;

  try {
    await api.del(`/chat/sessions/${sessionId}`);
    if (currentSessionId === sessionId) {
      currentSessionId = null;
      const container = document.getElementById("chat-messages");
      if (container) {
        container.innerHTML = `
          <div class="chat-empty">
            <h3>对话已删除</h3>
            <p>你可以马上开始一段新的任务整理对话。</p>
          </div>
        `;
      }
    }
    await loadSessions();
    showToast("对话已删除", "这段历史记录已经清理完成。", "success");
  } catch (error) {
    showToast("删除失败", error.message, "error");
  }
}

function renderAssistantHtml(content) {
  const escaped = escapeChatHtml(content ?? "");
  const normalized = escaped.replace(/\r\n/g, "\n");
  const blocks = normalized.split(/\n{2,}/).filter(Boolean);

  const renderedBlocks = blocks.map((block) => {
    const trimmed = block.trim();

    if (/^---+$/.test(trimmed)) {
      return "<hr>";
    }

    if (/^###\s+/.test(trimmed)) {
      return `<h4>${renderInlineMarkdown(trimmed.replace(/^###\s+/, ""))}</h4>`;
    }

    if (/^##\s+/.test(trimmed)) {
      return `<h3>${renderInlineMarkdown(trimmed.replace(/^##\s+/, ""))}</h3>`;
    }

    if (/^#\s+/.test(trimmed)) {
      return `<h2>${renderInlineMarkdown(trimmed.replace(/^#\s+/, ""))}</h2>`;
    }

    if (/^[-*]\s+/m.test(trimmed)) {
      const items = trimmed
        .split("\n")
        .filter((line) => /^[-*]\s+/.test(line.trim()))
        .map((line) => `<li>${renderInlineMarkdown(line.trim().replace(/^[-*]\s+/, ""))}</li>`)
        .join("");
      return `<ul>${items}</ul>`;
    }

    return `<p>${renderInlineMarkdown(trimmed).replace(/\n/g, "<br>")}</p>`;
  });

  return `<div class="assistant-rich-text">${renderedBlocks.join("")}</div>`;
}

function renderInlineMarkdown(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
}

function escapeChatHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}

function escapeChatAttr(value) {
  return escapeChatHtml(value).replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
