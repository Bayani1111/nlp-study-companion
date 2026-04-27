/**
 * Tasks and study plans page.
 */

const taskPageState = {
  tasks: [],
  plans: [],
  templates: [],
  editingTaskId: null,
  editingPlanId: null,
  activePlanFilterId: null,
  activePlanFilterTitle: "",
  collapsedTaskIds: new Set(),
};

const focusState = {
  activeTaskId: null,
  startedAtMs: null,
  lastSyncedMinute: 0,
  timerId: null,
};

const FOCUS_STORAGE_KEY = "active_focus_session";

function sortTasksForDisplay(tasks = []) {
  return [...tasks].sort((left, right) => {
    const leftDate = left.scheduled_date || "";
    const rightDate = right.scheduled_date || "";
    if (leftDate !== rightDate) return leftDate.localeCompare(rightDate);
    return (left.sort_order || 0) - (right.sort_order || 0);
  });
}

function buildDayLabel(planId, scheduledDate) {
  if (!scheduledDate) return "未安排日期";
  const plan = taskPageState.plans.find((item) => item.id === planId);
  const dayIndex = plan?.day_schedule?.findIndex((item) => item.date === scheduledDate) ?? -1;
  if (dayIndex >= 0) {
    return `第${dayIndex + 1}天 · ${scheduledDate}`;
  }
  return scheduledDate;
}

function groupTasksByScheduledDate(tasks = [], planId = null) {
  const groups = new Map();

  sortTasksForDisplay(tasks).forEach((task) => {
    const key = task.scheduled_date || "unscheduled";
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        label: buildDayLabel(planId || task.plan_id, task.scheduled_date),
        scheduledDate: task.scheduled_date || null,
        tasks: [],
      });
    }
    groups.get(key).tasks.push(task);
  });

  return Array.from(groups.values());
}

function renderDayTaskGroups(tasks = [], planId = null, options = {}) {
  const { compact = false, detail = false } = options;
  const groups = groupTasksByScheduledDate(tasks, planId);
  if (!groups.length) return "";

  return `
    <div class="${detail ? "detail-day-groups" : "task-day-groups"}">
      ${groups
        .map(
          (group) => `
            <section class="${detail ? "detail-day-group" : "task-day-group"}">
              <div class="${detail ? "detail-day-group-header" : "task-day-group-header"}">
                <strong>📅 ${escapeTaskHtml(group.label)}</strong>
                <span>${group.tasks.length} 项安排</span>
              </div>
              <div class="${detail ? "detail-day-group-body" : "task-day-group-body"}">
                ${group.tasks
                  .map((task) =>
                    detail
                      ? renderPlanDetailTask(task, 1)
                      : renderTaskCard(task, compact ? 1 : 1, { inDayGroup: true }),
                  )
                  .join("")}
              </div>
            </section>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderTasks() {
  const app = document.getElementById("app");
  app.innerHTML = `
    <div class="tasks-page">
      <section class="tasks-hero card">
        <div class="hero-copy">
          <p class="eyebrow">计划推进</p>
          <h2>让计划、任务和执行反馈在一个页面里闭环</h2>
          <p>
            这里会集中呈现聊天里生成的任务、你手动整理的待办，以及学习计划的阶段推进。
            记录、排序、执行、复盘，都应该在这里变得顺手。
          </p>
        </div>
        <div class="hero-actions">
          <button class="btn btn-primary" onclick="showCreateTaskModal()">+ 新建任务</button>
          <button class="btn btn-outline" onclick="showCreatePlanModal()">+ 新建计划</button>
        </div>
      </section>

      <section class="task-toolbar card">
        <div class="filters">
          <select id="filter-status" onchange="loadTaskList()">
            <option value="">全部状态</option>
            <option value="pending">待处理</option>
            <option value="in_progress">进行中</option>
            <option value="completed">已完成</option>
            <option value="overdue">已逾期</option>
          </select>
          <select id="filter-priority" onchange="loadTaskList()">
            <option value="">全部优先级</option>
            <option value="high">高优先级</option>
            <option value="medium">中优先级</option>
            <option value="low">低优先级</option>
          </select>
        </div>
        <div class="toolbar-actions">
          <button class="btn btn-outline btn-sm" onclick="previewAdvisoryCleanup()">预览清理建议型子任务</button>
          <button class="btn btn-danger btn-sm" onclick="applyAdvisoryCleanup()">确认清理建议型子任务</button>
        </div>
        <div class="section-note">任务会优先按计划内顺序和安排日期展示，方便你按阶段推进。</div>
      </section>

      <div id="focus-banner"></div>
      <div id="task-filter-banner"></div>
      <section class="plan-template-strip card" id="plan-template-strip">正在加载计划模板...</section>

      <div class="tasks-grid">
        <section class="task-panel card">
          <div class="panel-header">
            <div>
              <h3>任务树</h3>
              <p class="panel-count" id="task-summary">正在加载...</p>
            </div>
          </div>
          <div id="task-list" class="task-list">正在加载...</div>
        </section>

        <section class="plan-panel card">
          <div class="panel-header">
            <div>
              <h3>学习计划</h3>
              <p class="panel-count" id="plan-summary">正在加载...</p>
            </div>
          </div>
          <div id="plan-list" class="plan-list">正在加载...</div>
        </section>
      </div>
    </div>
  `;

  restoreFocusSession();
  renderFocusBanner();
  loadTaskPageData();
}

async function loadTaskPageData() {
  await Promise.all([loadTaskList(), loadPlanList(), loadPlanTemplates()]);
}

async function loadPlanTemplates() {
  const container = document.getElementById("plan-template-strip");
  if (!container) return;

  try {
    const templates = await api.get("/plans/templates");
    taskPageState.templates = templates;

    if (!templates.length) {
      container.innerHTML = '<div class="empty-state compact">暂时没有可用模板。</div>';
      return;
    }

    container.innerHTML = `
      <div class="template-strip-header">
        <div>
          <p class="eyebrow">快速起步</p>
          <h3>先用模板搭一个骨架，再慢慢细化阶段和任务</h3>
        </div>
      </div>
      <div class="template-strip-list">
        ${templates.map(renderTemplateCard).join("")}
      </div>
    `;
  } catch (error) {
    container.innerHTML = `<div class="empty-state compact">${escapeTaskHtml(error.message)}</div>`;
  }
}

function renderTemplateCard(template) {
  return `
    <article class="template-card">
      <div class="template-card-top">
        <strong>${escapeTaskHtml(template.title)}</strong>
        <span>${template.duration_days} 天</span>
      </div>
      <p>${escapeTaskHtml(template.description)}</p>
      <div class="template-phase-preview">
        ${(template.phases || [])
          .slice(0, 3)
          .map((phase) => `<span>${escapeTaskHtml(phase.title)}</span>`)
          .join("")}
      </div>
      <button class="btn btn-outline btn-sm" onclick="showQuickCreatePlanModal('${escapeAttr(template.key)}')">
        使用这个模板
      </button>
    </article>
  `;
}

function saveFocusSession() {
  if (!focusState.activeTaskId || !focusState.startedAtMs) {
    localStorage.removeItem(FOCUS_STORAGE_KEY);
    return;
  }
  localStorage.setItem(
    FOCUS_STORAGE_KEY,
    JSON.stringify({
      activeTaskId: focusState.activeTaskId,
      startedAtMs: focusState.startedAtMs,
      lastSyncedMinute: focusState.lastSyncedMinute,
    }),
  );
}

function restoreFocusSession() {
  if (focusState.timerId) {
    clearInterval(focusState.timerId);
    focusState.timerId = null;
  }

  try {
    const raw = localStorage.getItem(FOCUS_STORAGE_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (!parsed.activeTaskId || !parsed.startedAtMs) return;
    focusState.activeTaskId = parsed.activeTaskId;
    focusState.startedAtMs = parsed.startedAtMs;
    focusState.lastSyncedMinute = parsed.lastSyncedMinute || 0;
    startFocusTicker();
  } catch {
    localStorage.removeItem(FOCUS_STORAGE_KEY);
  }
}

function startFocusTicker() {
  if (focusState.timerId) {
    clearInterval(focusState.timerId);
  }
  focusState.timerId = setInterval(() => {
    renderFocusBanner();
    syncFocusMinutes();
  }, 1000);
}

function getActiveFocusTask() {
  return focusState.activeTaskId ? findTaskById(focusState.activeTaskId) : null;
}

function getFocusElapsedMinutes() {
  if (!focusState.startedAtMs) return 0;
  return Math.floor((Date.now() - focusState.startedAtMs) / 60000);
}

function getFocusElapsedLabel() {
  if (!focusState.startedAtMs) return "00:00";
  const totalSeconds = Math.max(0, Math.floor((Date.now() - focusState.startedAtMs) / 1000));
  const hours = String(Math.floor(totalSeconds / 3600)).padStart(2, "0");
  const minutes = String(Math.floor((totalSeconds % 3600) / 60)).padStart(2, "0");
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${hours}:${minutes}:${seconds}`;
}

function renderFocusBanner() {
  const banner = document.getElementById("focus-banner");
  if (!banner) return;

  const activeTask = getActiveFocusTask();
  if (!activeTask) {
    banner.innerHTML = "";
    return;
  }

  banner.innerHTML = `
    <div class="focus-banner card">
      <div>
        <strong>正在学习：${escapeTaskHtml(activeTask.title)}</strong>
        <p>已累计 ${getFocusElapsedLabel()}，系统会自动按分钟记录学习时长。</p>
      </div>
      <div class="focus-banner-actions">
        <button class="btn btn-outline btn-sm" onclick="window.location.hash='#stats'">查看统计</button>
        <button class="btn btn-primary btn-sm" onclick="stopFocusSession()">结束本次学习</button>
      </div>
    </div>
  `;
}

async function startFocusSession(taskId) {
  const task = findTaskById(taskId);
  if (!task) {
    showToast("任务不存在", "请刷新页面后再试。", "error");
    return;
  }

  if (focusState.activeTaskId && focusState.activeTaskId !== taskId) {
    await stopFocusSession({ silentToast: true });
  }

  focusState.activeTaskId = taskId;
  focusState.startedAtMs = Date.now();
  focusState.lastSyncedMinute = 0;
  saveFocusSession();
  startFocusTicker();
  renderFocusBanner();

  if (task.status === "pending") {
    try {
      await api.put(`/tasks/${taskId}`, { status: "in_progress" });
    } catch {
      // best effort
    }
  }

  showToast("学习已开始", `正在记录“${task.title}”的学习时长。`, "success");
  await loadTaskPageData();
}

async function syncFocusMinutes(force = false) {
  if (!focusState.activeTaskId || !focusState.startedAtMs) return;
  const elapsedMinutes = getFocusElapsedMinutes();
  let unsyncedMinutes = elapsedMinutes - focusState.lastSyncedMinute;

  if (!force && unsyncedMinutes < 1) {
    return;
  }

  if (force && unsyncedMinutes <= 0) {
    const totalSeconds = Math.max(0, Math.floor((Date.now() - focusState.startedAtMs) / 1000));
    unsyncedMinutes = totalSeconds >= 30 ? 1 : 0;
  }

  if (unsyncedMinutes <= 0) return;

  try {
    await api.post("/stats/study-session", {
      task_id: focusState.activeTaskId,
      duration_minutes: unsyncedMinutes,
      source: "focus_timer",
    });
    focusState.lastSyncedMinute += unsyncedMinutes;
    saveFocusSession();
  } catch {
    // keep local state and try again later
  }
}

async function stopFocusSession(options = {}) {
  if (!focusState.activeTaskId) return;
  await syncFocusMinutes(true);
  const activeTask = getActiveFocusTask();
  if (focusState.timerId) {
    clearInterval(focusState.timerId);
  }
  focusState.activeTaskId = null;
  focusState.startedAtMs = null;
  focusState.lastSyncedMinute = 0;
  focusState.timerId = null;
  saveFocusSession();
  renderFocusBanner();

  if (!options.silentToast) {
    showToast("学习已结束", activeTask ? `已保存“${activeTask.title}”的学习时长。` : "本次学习时长已保存。", "success");
  }
}

async function loadTaskList() {
  const taskListEl = document.getElementById("task-list");
  if (!taskListEl) return;

  const params = new URLSearchParams();
  const status = document.getElementById("filter-status")?.value || "";
  const priority = document.getElementById("filter-priority")?.value || "";

  if (status) params.set("status", status);
  if (priority) params.set("priority", priority);

  const suffix = params.toString() ? `?${params.toString()}` : "";

  try {
    const tasks = await api.get(`/tasks${suffix}`);
    taskPageState.tasks = tasks;

    const filteredTasks = taskPageState.activePlanFilterId
      ? tasks.filter((task) => task.plan_id === taskPageState.activePlanFilterId)
      : tasks;

    renderTaskFilterBanner();
    updateTaskSummary(filteredTasks);

    if (!filteredTasks.length) {
      taskListEl.innerHTML = renderTaskEmptyState();
      return;
    }

    taskListEl.innerHTML = filteredTasks.map((task) => renderTaskCard(task)).join("");
  } catch (error) {
    taskListEl.innerHTML = `
      <div class="empty-state empty-state-error">
        <h4>任务加载失败</h4>
        <p>${escapeTaskHtml(error.message)}</p>
        <button class="btn btn-outline btn-sm" onclick="loadTaskList()">重新加载</button>
      </div>
    `;
  }
}

function updateTaskSummary(filteredTasks) {
  const summary = document.getElementById("task-summary");
  if (!summary) return;

  if (taskPageState.activePlanFilterId) {
    summary.textContent = `当前显示“${taskPageState.activePlanFilterTitle}”下的 ${filteredTasks.length} 个主任务`;
    return;
  }

  if (!filteredTasks.length) {
    summary.textContent = "还没有任务";
    return;
  }

  const completedCount = filteredTasks.filter((task) => task.status === "completed").length;
  summary.textContent = `共 ${filteredTasks.length} 个主任务，已完成 ${completedCount} 个`;
}

function renderTaskEmptyState() {
  if (taskPageState.activePlanFilterId) {
    return `
      <div class="empty-state">
        <h4>这个计划下还没有任务</h4>
        <p>你可以先给这个计划新增主任务，或者取消筛选查看全部任务。</p>
        <div class="empty-state-actions">
          <button class="btn btn-primary btn-sm" onclick="showCreateTaskModal()">给计划添加任务</button>
          <button class="btn btn-outline btn-sm" onclick="clearPlanTaskFilter()">查看全部任务</button>
        </div>
      </div>
    `;
  }

  return `
    <div class="empty-state">
      <h4>还没有任务</h4>
      <p>你可以先在聊天里说一句自然语言，或者直接手动创建一个主任务。</p>
      <div class="empty-state-actions">
        <button class="btn btn-primary btn-sm" onclick="window.location.hash='#chat'">去聊天页生成</button>
        <button class="btn btn-outline btn-sm" onclick="showCreateTaskModal()">手动新建任务</button>
      </div>
    </div>
  `;
}

function renderTaskFilterBanner() {
  const banner = document.getElementById("task-filter-banner");
  if (!banner) return;

  if (!taskPageState.activePlanFilterId) {
    banner.innerHTML = "";
    return;
  }

  const plan = taskPageState.plans.find((item) => item.id === taskPageState.activePlanFilterId);
  banner.innerHTML = `
    <div class="task-filter-banner card">
      <div>
        <strong>当前正在查看计划任务</strong>
        <span>${escapeTaskHtml(taskPageState.activePlanFilterTitle)}</span>
        ${
          plan
            ? `<small>阶段 ${plan.phases?.length || 0} 个，按天安排 ${plan.day_schedule?.length || 0} 天</small>`
            : ""
        }
      </div>
      <button class="btn btn-outline btn-sm" onclick="clearPlanTaskFilter()">查看全部任务</button>
    </div>
  `;
}

function renderTaskCard(task, depth = 0, options = {}) {
  const { inDayGroup = false } = options;
  const hasChildren = Array.isArray(task.children) && task.children.length > 0;
  const isCollapsed = taskPageState.collapsedTaskIds.has(task.id);
  const dueLabel = task.due_date ? `截止：${formatTaskDate(task.due_date)}` : "未设置截止时间";
  const scheduleLabel = task.scheduled_date ? `安排：${task.scheduled_date}` : "未设置安排日期";
  const estimateLabel = task.estimated_minutes ? `预计 ${task.estimated_minutes} 分钟` : "未填写预计时长";
  const planLabel = task.plan_id
    ? `计划：<button class="plan-link-button" onclick="filterTasksByPlan(${task.plan_id})">${escapeTaskHtml(resolvePlanTitle(task.plan_id))}</button>`
    : "未绑定计划";
  const phaseLabel = task.phase_id ? `阶段：${escapeTaskHtml(resolvePhaseTitle(task.plan_id, task.phase_id))}` : "未绑定阶段";

  const parentSummary =
    task.subtask_count > 0
      ? `
        <div class="subtask-progress">
          <div class="plan-progress-top">
            <span>子任务进度 ${task.completed_subtask_count}/${task.subtask_count}</span>
            <strong>${task.subtask_count ? Math.round((task.completed_subtask_count / task.subtask_count) * 100) : 0}%</strong>
          </div>
          <div class="progress-track">
            <div class="progress-fill" style="width:${task.subtask_count ? (task.completed_subtask_count / task.subtask_count) * 100 : 0}%"></div>
          </div>
        </div>
      `
      : "";

  const statusAction =
    task.status === "completed"
      ? `<button class="btn btn-outline btn-sm" onclick="toggleTaskStatus(${task.id}, 'pending')">重新打开</button>`
      : `<button class="btn btn-primary btn-sm" onclick="toggleTaskStatus(${task.id}, 'completed')">标记完成</button>`;

  const addSubtaskAction =
    depth === 0
      ? `<button class="btn btn-outline btn-sm" onclick="showCreateSubtaskModal(${task.id})">添加子任务</button>`
      : "";
  const focusAction =
    depth === 0
      ? focusState.activeTaskId === task.id
        ? `<button class="btn btn-outline btn-sm" onclick="stopFocusSession()">结束学习</button>`
        : `<button class="btn btn-outline btn-sm" onclick="startFocusSession(${task.id})">开始学习</button>`
      : "";

  const collapseAction = hasChildren
    ? `<button class="btn btn-outline btn-sm" onclick="toggleTaskCollapse(${task.id})">${isCollapsed ? "展开子任务" : "收起子任务"}</button>`
    : "";

  const childHtml =
    hasChildren && !isCollapsed
      ? `<div class="subtask-list">${
          depth === 0
            ? renderDayTaskGroups(task.children, task.plan_id)
            : task.children.map((child) => renderTaskCard(child, depth + 1)).join("")
        }</div>`
      : "";

  return `
    <article class="task-card ${depth > 0 ? "task-card-child" : "task-card-parent"} ${inDayGroup ? "task-card-in-day-group" : ""}">
      <div class="task-main">
        <div class="task-card-header">
          <div>
            <div class="task-title-row">
              ${depth > 0 ? '<span class="task-tree-marker">↳</span>' : ""}
              <div class="task-title">${escapeTaskHtml(task.title)}</div>
            </div>
            <div class="task-subline">
              ${depth > 0 ? '<span class="tree-badge">子任务</span>' : '<span class="tree-badge">主任务</span>'}
              ${hasChildren ? `<span class="tree-hint">${task.subtask_count} 个子任务</span>` : ""}
            </div>
          </div>
          <div class="task-badges">
            <span class="badge badge-${task.priority}">${priorityLabel(task.priority)}</span>
            <span class="badge badge-${task.status}">${statusLabel(task.status)}</span>
          </div>
        </div>
        ${task.description ? `<p class="task-desc">${escapeTaskHtml(task.description)}</p>` : ""}
        ${parentSummary}
        <div class="task-meta">
          <span>${scheduleLabel}</span>
          <span>${dueLabel}</span>
          <span>${estimateLabel}</span>
          <span>${phaseLabel}</span>
          <span>${planLabel}</span>
          <span>顺序：${task.sort_order || 0}</span>
        </div>
        ${childHtml}
      </div>
      <div class="task-actions">
        ${statusAction}
        ${focusAction}
        ${collapseAction}
        ${addSubtaskAction}
        <button class="btn btn-outline btn-sm" onclick="showEditTaskModal(${task.id})">编辑</button>
        <button class="btn btn-danger btn-sm" onclick="deleteTask(${task.id})">删除</button>
      </div>
    </article>
  `;
}

function toggleTaskCollapse(taskId) {
  if (taskPageState.collapsedTaskIds.has(taskId)) {
    taskPageState.collapsedTaskIds.delete(taskId);
  } else {
    taskPageState.collapsedTaskIds.add(taskId);
  }
  loadTaskList();
}

async function loadPlanList() {
  const planListEl = document.getElementById("plan-list");
  if (!planListEl) return;

  try {
    const plans = await api.get("/plans");
    taskPageState.plans = plans;

    if (
      taskPageState.activePlanFilterId &&
      !plans.some((plan) => plan.id === taskPageState.activePlanFilterId)
    ) {
      clearPlanTaskFilter({ silent: true });
    }

    updatePlanSummary(plans);

    if (!plans.length) {
      planListEl.innerHTML = `
        <div class="empty-state">
          <h4>还没有学习计划</h4>
          <p>如果你的目标需要分阶段推进，可以先创建一个计划，再往计划里挂任务。</p>
          <div class="empty-state-actions">
            <button class="btn btn-primary btn-sm" onclick="showCreatePlanModal()">手动新建计划</button>
          </div>
        </div>
      `;
      return;
    }

    planListEl.innerHTML = plans.map(renderPlanCard).join("");
    if (taskPageState.tasks.length) {
      await loadTaskList();
    }
  } catch (error) {
    planListEl.innerHTML = `
      <div class="empty-state empty-state-error">
        <h4>计划加载失败</h4>
        <p>${escapeTaskHtml(error.message)}</p>
        <button class="btn btn-outline btn-sm" onclick="loadPlanList()">重新加载</button>
      </div>
    `;
  }
}

function updatePlanSummary(plans) {
  const summary = document.getElementById("plan-summary");
  if (!summary) return;

  if (!plans.length) {
    summary.textContent = "还没有学习计划";
    return;
  }

  const activeCount = plans.filter((plan) => plan.status === "active").length;
  summary.textContent = `共 ${plans.length} 个计划，正在推进 ${activeCount} 个`;
}

function renderPlanCard(plan) {
  const progressWidth = Math.max(0, Math.min(100, plan.progress_percent || 0));
  const isActiveFilter = taskPageState.activePlanFilterId === plan.id;

  return `
    <article class="plan-card ${isActiveFilter ? "plan-card-active" : ""}">
      <div class="plan-card-header">
        <div>
          <div class="plan-title">${escapeTaskHtml(plan.title)}</div>
          <div class="plan-dates">${plan.start_date} 至 ${plan.end_date}</div>
        </div>
        <span class="badge badge-${plan.status}">${planStatusLabel(plan.status)}</span>
      </div>
      ${plan.description ? `<p class="task-desc">${escapeTaskHtml(plan.description)}</p>` : ""}
      <div class="plan-progress">
        <div class="plan-progress-top">
          <span>${plan.completed_task_count || 0}/${plan.task_count || 0} 个主任务已完成</span>
          <strong>${progressWidth.toFixed(0)}%</strong>
        </div>
        <div class="progress-track">
          <div class="progress-fill" style="width:${progressWidth}%"></div>
        </div>
      </div>
      <div class="plan-detail-metrics">
        <span>阶段 ${plan.phases?.length || 0}</span>
        <span>子任务 ${plan.completed_subtask_count || 0}/${plan.subtask_count || 0}</span>
        <span>按天安排 ${plan.day_schedule?.length || 0} 天</span>
      </div>
      <div class="plan-actions">
        <button class="btn ${isActiveFilter ? "btn-primary" : "btn-outline"} btn-sm" onclick="filterTasksByPlan(${plan.id})">
          ${isActiveFilter ? "正在查看任务" : "查看计划任务"}
        </button>
        <button class="btn btn-outline btn-sm" onclick="showPlanDetail(${plan.id})">详情</button>
        <button class="btn btn-outline btn-sm" onclick="showEditPlanModal(${plan.id})">编辑</button>
        <button class="btn btn-danger btn-sm" onclick="deletePlan(${plan.id})">删除</button>
      </div>
    </article>
  `;
}

function filterTasksByPlan(planId) {
  const plan = taskPageState.plans.find((item) => item.id === planId);
  if (!plan) {
    showToast("计划不存在", "请刷新页面后重试。", "error");
    return;
  }

  taskPageState.activePlanFilterId = plan.id;
  taskPageState.activePlanFilterTitle = plan.title;
  loadTaskList();
  loadPlanList();
}

function clearPlanTaskFilter(options = {}) {
  taskPageState.activePlanFilterId = null;
  taskPageState.activePlanFilterTitle = "";
  if (!options.silent) {
    showToast("已清除筛选", "现在正在显示全部任务。", "success");
  }
  loadTaskList();
  loadPlanList();
}

function showCreateTaskModal() {
  taskPageState.editingTaskId = null;
  openTaskModal("新建任务", {
    title: "",
    description: "",
    priority: "medium",
    status: "pending",
    due_date: "",
    scheduled_date: "",
    estimated_minutes: "",
    actual_minutes: "",
    plan_id: taskPageState.activePlanFilterId || "",
    phase_id: "",
    parent_task_id: "",
    sort_order: 0,
  });
}

function showCreateSubtaskModal(parentId) {
  const parentTask = findTaskById(parentId);
  if (!parentTask) {
    showToast("父任务不存在", "请刷新页面后再试。", "error");
    return;
  }

  taskPageState.editingTaskId = null;
  openTaskModal(`给“${parentTask.title}”添加子任务`, {
    title: "",
    description: "",
    priority: parentTask.priority || "medium",
    status: "pending",
    due_date: parentTask.due_date ? toDateTimeLocalValue(parentTask.due_date) : "",
    scheduled_date: parentTask.scheduled_date || "",
    estimated_minutes: "",
    actual_minutes: "",
    plan_id: parentTask.plan_id || "",
    phase_id: parentTask.phase_id || "",
    parent_task_id: parentTask.id,
    sort_order: 0,
  });
}

function showEditTaskModal(taskId) {
  const task = findTaskById(taskId);
  if (!task) {
    showToast("任务不存在", "请刷新页面后再试。", "error");
    return;
  }

  taskPageState.editingTaskId = taskId;
  openTaskModal("编辑任务", {
    ...task,
    due_date: task.due_date ? toDateTimeLocalValue(task.due_date) : "",
    scheduled_date: task.scheduled_date || "",
    estimated_minutes: task.estimated_minutes || "",
    actual_minutes: task.actual_minutes || "",
    plan_id: task.plan_id || "",
    phase_id: task.phase_id || "",
    parent_task_id: task.parent_task_id || "",
    sort_order: task.sort_order || 0,
  });
}

function openTaskModal(title, task) {
  const availablePlans = taskPageState.plans;
  const activePlan = availablePlans.find((plan) => String(plan.id) === String(task.plan_id));
  const planOptions = ['<option value="">不绑定计划</option>']
    .concat(
      availablePlans.map(
        (plan) =>
          `<option value="${plan.id}" ${String(task.plan_id) === String(plan.id) ? "selected" : ""}>${escapeTaskHtml(plan.title)}</option>`,
      ),
    )
    .join("");

  const phaseOptions = ['<option value="">不绑定阶段</option>']
    .concat(
      (activePlan?.phases || []).map(
        (phase) =>
          `<option value="${phase.id}" ${String(task.phase_id) === String(phase.id) ? "selected" : ""}>${escapeTaskHtml(phase.title)}</option>`,
      ),
    )
    .join("");

  const parentOptions = ['<option value="">作为主任务</option>']
    .concat(
      taskPageState.tasks
        .filter((item) => item.id !== taskPageState.editingTaskId)
        .map(
          (item) =>
            `<option value="${item.id}" ${String(task.parent_task_id) === String(item.id) ? "selected" : ""}>${escapeTaskHtml(item.title)}</option>`,
        ),
    )
    .join("");

  openModal(
    "task-modal",
    `
      <div class="modal">
        <h3>${escapeTaskHtml(title)}</h3>
        <div class="modal-grid">
          <div class="form-group">
            <label>任务标题</label>
            <input class="form-control" id="task-title" value="${escapeAttr(task.title)}" placeholder="比如：完成高数第一章复习">
          </div>
          <div class="form-group">
            <label>父任务</label>
            <select class="form-control" id="task-parent-id">${parentOptions}</select>
          </div>
          <div class="form-group">
            <label>绑定计划</label>
            <select class="form-control" id="task-plan-id">${planOptions}</select>
          </div>
          <div class="form-group">
            <label>绑定阶段</label>
            <select class="form-control" id="task-phase-id">${phaseOptions}</select>
          </div>
          <div class="form-group">
            <label>优先级</label>
            <select class="form-control" id="task-priority">
              <option value="high" ${task.priority === "high" ? "selected" : ""}>高优先级</option>
              <option value="medium" ${task.priority === "medium" ? "selected" : ""}>中优先级</option>
              <option value="low" ${task.priority === "low" ? "selected" : ""}>低优先级</option>
            </select>
          </div>
          <div class="form-group full-span">
            <label>任务描述</label>
            <textarea class="form-control" id="task-description" rows="4" placeholder="写下具体要求、拆解步骤或注意事项">${escapeTaskHtml(task.description || "")}</textarea>
          </div>
          <div class="form-group">
            <label>状态</label>
            <select class="form-control" id="task-status">
              <option value="pending" ${task.status === "pending" ? "selected" : ""}>待处理</option>
              <option value="in_progress" ${task.status === "in_progress" ? "selected" : ""}>进行中</option>
              <option value="completed" ${task.status === "completed" ? "selected" : ""}>已完成</option>
              <option value="overdue" ${task.status === "overdue" ? "selected" : ""}>已逾期</option>
            </select>
          </div>
          <div class="form-group">
            <label>安排日期</label>
            <input class="form-control" type="date" id="task-scheduled-date" value="${task.scheduled_date || ""}">
          </div>
          <div class="form-group">
            <label>截止时间</label>
            <input class="form-control" type="datetime-local" id="task-due-date" value="${task.due_date || ""}">
          </div>
          <div class="form-group">
            <label>计划内顺序</label>
            <input class="form-control" type="number" min="0" id="task-sort-order" value="${task.sort_order || 0}">
          </div>
          <div class="form-group">
            <label>预计时长（分钟）</label>
            <input class="form-control" type="number" min="0" id="task-estimated-minutes" value="${task.estimated_minutes || ""}">
          </div>
          <div class="form-group">
            <label>实际时长（分钟）</label>
            <input class="form-control" type="number" min="0" id="task-actual-minutes" value="${task.actual_minutes || ""}">
          </div>
        </div>
        <div class="modal-tip">计划、阶段、安排日期和顺序一起使用时，任务树会更清晰。</div>
        <div class="modal-actions">
          <button class="btn btn-outline" onclick="closeModal('task-modal')">取消</button>
          <button class="btn btn-primary" onclick="submitTaskModal()">保存</button>
        </div>
      </div>
    `,
  );
}

async function submitTaskModal() {
  const payload = collectTaskFormData();
  if (!payload.title) {
    showToast("缺少标题", "任务标题不能为空。", "error");
    return;
  }

  try {
    if (taskPageState.editingTaskId) {
      await api.put(`/tasks/${taskPageState.editingTaskId}`, payload);
      showToast("任务已更新", "任务内容已经保存。", "success");
    } else {
      await api.post("/tasks", payload);
      showToast("任务已创建", payload.parent_task_id ? "子任务已经加入主任务。" : "新任务已经加入列表。", "success");
    }
    closeModal("task-modal");
    await loadTaskPageData();
  } catch (error) {
    showToast("保存失败", error.message, "error");
  }
}

function collectTaskFormData() {
  const payload = {
    title: document.getElementById("task-title").value.trim(),
    description: document.getElementById("task-description").value.trim() || null,
    priority: document.getElementById("task-priority").value,
    status: document.getElementById("task-status").value,
    due_date: document.getElementById("task-due-date").value || null,
    scheduled_date: document.getElementById("task-scheduled-date").value || null,
    estimated_minutes: parseOptionalInt(document.getElementById("task-estimated-minutes").value),
    actual_minutes: parseOptionalInt(document.getElementById("task-actual-minutes").value),
    sort_order: parseOptionalInt(document.getElementById("task-sort-order").value) || 0,
    plan_id: parseOptionalInt(document.getElementById("task-plan-id").value),
    phase_id: parseOptionalInt(document.getElementById("task-phase-id").value),
    parent_task_id: parseOptionalInt(document.getElementById("task-parent-id").value),
  };

  if (payload.due_date) {
    payload.due_date = new Date(payload.due_date).toISOString();
  }

  return payload;
}

async function toggleTaskStatus(taskId, nextStatus) {
  const task = findTaskById(taskId);
  if (!task) return;

  try {
    await api.put(`/tasks/${taskId}`, { status: nextStatus });
    showToast("任务状态已更新", `${task.title} 现在是${statusLabel(nextStatus)}。`, "success");
    await loadTaskPageData();
  } catch (error) {
    showToast("更新失败", error.message, "error");
  }
}

async function deleteTask(taskId) {
  const task = findTaskById(taskId);
  if (!task) return;
  if (!confirm(`确定删除任务“${task.title}”吗？如果它下面还有子任务，也会一起删除。`)) return;

  try {
    await api.del(`/tasks/${taskId}`);
    showToast("任务已删除", "任务已经从列表中移除。", "success");
    await loadTaskPageData();
  } catch (error) {
    showToast("删除失败", error.message, "error");
  }
}

async function previewAdvisoryCleanup() {
  try {
    const payload = await api.post("/tasks/cleanup/advisory?dry_run=true", null);
    if (!payload.matched_count) {
      showToast("未发现脏子任务", `已扫描 ${payload.scanned_subtasks} 条子任务，当前无需清理。`, "success");
      return;
    }
    renderCleanupCandidatesModal(payload, "preview");
  } catch (error) {
    showToast("预览失败", error.message, "error");
  }
}

async function applyAdvisoryCleanup() {
  if (!confirm("将清理历史里的“建议型子任务”，该操作会删除命中子任务，是否继续？")) return;
  try {
    const payload = await api.post("/tasks/cleanup/advisory?dry_run=false", null);
    showToast(
      "清理完成",
      `扫描 ${payload.scanned_subtasks} 条，命中 ${payload.matched_count} 条，已删除 ${payload.deleted_count} 条。`,
      "success",
    );
    renderCleanupCandidatesModal(payload, "apply");
    await loadTaskPageData();
  } catch (error) {
    showToast("清理失败", error.message, "error");
  }
}

function renderCleanupCandidatesModal(payload, mode = "preview") {
  const title = mode === "preview" ? "建议型子任务清理预览" : "建议型子任务清理结果";
  const summary = `扫描 ${payload.scanned_subtasks} 条子任务，命中 ${payload.matched_count} 条，已删除 ${payload.deleted_count} 条。`;
  const rows = (payload.candidates || [])
    .slice(0, 80)
    .map(
      (item) => `
        <tr>
          <td>#${item.id}</td>
          <td>${escapeTaskHtml(item.title)}</td>
          <td>${escapeTaskHtml(item.reason || "-")}</td>
        </tr>
      `,
    )
    .join("");

  openModal(
    "cleanup-advisory-modal",
    `
      <div class="modal">
        <h3>${title}</h3>
        <p>${summary}</p>
        ${
          payload.candidates?.length
            ? `
              <div class="cleanup-preview-table-wrap">
                <table class="cleanup-preview-table">
                  <thead>
                    <tr>
                      <th>任务ID</th>
                      <th>标题</th>
                      <th>命中原因</th>
                    </tr>
                  </thead>
                  <tbody>${rows}</tbody>
                </table>
              </div>
              ${
                payload.candidates.length > 80
                  ? `<p class="modal-tip">仅展示前 80 条，完整数量见上方统计。</p>`
                  : ""
              }
            `
            : '<p class="modal-tip">未命中可清理子任务。</p>'
        }
        <div class="modal-actions">
          <button class="btn btn-outline" onclick="closeModal('cleanup-advisory-modal')">关闭</button>
          ${
            mode === "preview" && payload.matched_count
              ? '<button class="btn btn-danger" onclick="closeModal(\'cleanup-advisory-modal\'); applyAdvisoryCleanup();">执行清理</button>'
              : ""
          }
        </div>
      </div>
    `,
  );
}

function showCreatePlanModal() {
  taskPageState.editingPlanId = null;
  openPlanModal("新建学习计划", {
    title: "",
    description: "",
    template_key: "",
    start_date: "",
    end_date: "",
    status: "active",
    phases: [],
  });
}

function showQuickCreatePlanModal(templateKey) {
  const template = taskPageState.templates.find((item) => item.key === templateKey);
  if (!template) return;

  openModal(
    "plan-quick-create-modal",
    `
      <div class="modal">
        <h3>使用模板快速生成</h3>
        <div class="form-group">
          <label>模板</label>
          <input class="form-control" value="${escapeAttr(template.title)}" disabled>
        </div>
        <div class="form-group">
          <label>计划标题</label>
          <input class="form-control" id="quick-plan-title" value="${escapeAttr(template.title)}">
        </div>
        <div class="form-group">
          <label>开始日期</label>
          <input class="form-control" type="date" id="quick-plan-start-date" value="${new Date().toISOString().slice(0, 10)}">
        </div>
        <div class="form-group">
          <label>补充说明</label>
          <textarea class="form-control" id="quick-plan-description" rows="3" placeholder="可以写上这次计划的目标">${escapeTaskHtml(template.description || "")}</textarea>
        </div>
        <div class="modal-actions">
          <button class="btn btn-outline" onclick="closeModal('plan-quick-create-modal')">取消</button>
          <button class="btn btn-primary" onclick="submitQuickCreatePlan('${escapeAttr(template.key)}')">生成计划</button>
        </div>
      </div>
    `,
  );
}

async function submitQuickCreatePlan(templateKey) {
  try {
    const created = await api.post("/plans/quick-create", {
      template_key: templateKey,
      title: document.getElementById("quick-plan-title").value.trim() || null,
      description: document.getElementById("quick-plan-description").value.trim() || null,
      start_date: document.getElementById("quick-plan-start-date").value,
    });
    closeModal("plan-quick-create-modal");
    showToast("计划已生成", "模板阶段和基础任务已经创建完成。", "success", {
      actionLabel: "查看详情",
      action: () => {
        window.location.hash = "#tasks";
        setTimeout(() => showPlanDetail(created.id), 200);
      },
    });
    await loadTaskPageData();
  } catch (error) {
    showToast("生成失败", error.message, "error");
  }
}

function showEditPlanModal(planId) {
  const plan = taskPageState.plans.find((item) => item.id === planId);
  if (!plan) {
    showToast("计划不存在", "请刷新页面后再试。", "error");
    return;
  }

  taskPageState.editingPlanId = planId;
  openPlanModal("编辑学习计划", plan);
}

function openPlanModal(title, plan) {
  const phases = plan.phases?.length
    ? plan.phases
    : [{ title: "", description: "", start_date: "", end_date: "", sequence: 0 }];

  openModal(
    "plan-modal",
    `
      <div class="modal">
        <h3>${escapeTaskHtml(title)}</h3>
        <div class="modal-grid">
          <div class="form-group full-span">
            <label>计划标题</label>
            <input class="form-control" id="plan-title" value="${escapeAttr(plan.title)}" placeholder="比如：下周高数复习计划">
          </div>
          <div class="form-group full-span">
            <label>计划描述</label>
            <textarea class="form-control" id="plan-description" rows="4" placeholder="写下目标、阶段安排和提醒点">${escapeTaskHtml(plan.description || "")}</textarea>
          </div>
          <div class="form-group">
            <label>模板标识</label>
            <input class="form-control" id="plan-template-key" value="${escapeAttr(plan.template_key || "")}" placeholder="可留空">
          </div>
          <div class="form-group">
            <label>计划状态</label>
            <select class="form-control" id="plan-status">
              <option value="active" ${plan.status === "active" ? "selected" : ""}>进行中</option>
              <option value="completed" ${plan.status === "completed" ? "selected" : ""}>已完成</option>
              <option value="archived" ${plan.status === "archived" ? "selected" : ""}>已归档</option>
            </select>
          </div>
          <div class="form-group">
            <label>开始日期</label>
            <input class="form-control" type="date" id="plan-start-date" value="${plan.start_date || ""}">
          </div>
          <div class="form-group">
            <label>结束日期</label>
            <input class="form-control" type="date" id="plan-end-date" value="${plan.end_date || ""}">
          </div>
        </div>
        <div class="phase-editor">
          <div class="phase-editor-header">
            <strong>计划阶段</strong>
            <button class="btn btn-outline btn-sm" onclick="addPhaseRow()">添加阶段</button>
          </div>
          <div id="phase-editor-list">
            ${phases.map((phase, index) => renderPhaseEditorRow(phase, index)).join("")}
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn btn-outline" onclick="closeModal('plan-modal')">取消</button>
          <button class="btn btn-primary" onclick="submitPlanModal()">保存</button>
        </div>
      </div>
    `,
  );
}

function renderPhaseEditorRow(phase, index) {
  return `
    <div class="phase-editor-row" data-phase-index="${index}">
      <input class="form-control" data-phase-field="title" value="${escapeAttr(phase.title || "")}" placeholder="阶段标题">
      <input class="form-control" data-phase-field="description" value="${escapeAttr(phase.description || "")}" placeholder="阶段说明">
      <input class="form-control" type="date" data-phase-field="start_date" value="${phase.start_date || ""}">
      <input class="form-control" type="date" data-phase-field="end_date" value="${phase.end_date || ""}">
      <input class="form-control" type="number" min="0" data-phase-field="sequence" value="${phase.sequence ?? index}">
      <button class="btn btn-danger btn-sm" onclick="removePhaseRow(${index})">删除</button>
    </div>
  `;
}

function addPhaseRow() {
  const list = document.getElementById("phase-editor-list");
  if (!list) return;
  const index = list.children.length;
  list.insertAdjacentHTML("beforeend", renderPhaseEditorRow({}, index));
}

function removePhaseRow(index) {
  document.querySelector(`.phase-editor-row[data-phase-index="${index}"]`)?.remove();
}

function collectPlanPhases() {
  return Array.from(document.querySelectorAll(".phase-editor-row"))
    .map((row) => ({
      title: row.querySelector("[data-phase-field='title']").value.trim(),
      description: row.querySelector("[data-phase-field='description']").value.trim() || null,
      start_date: row.querySelector("[data-phase-field='start_date']").value || null,
      end_date: row.querySelector("[data-phase-field='end_date']").value || null,
      sequence: parseOptionalInt(row.querySelector("[data-phase-field='sequence']").value) || 0,
    }))
    .filter((phase) => phase.title);
}

async function submitPlanModal() {
  const payload = {
    title: document.getElementById("plan-title").value.trim(),
    description: document.getElementById("plan-description").value.trim() || null,
    template_key: document.getElementById("plan-template-key").value.trim() || null,
    start_date: document.getElementById("plan-start-date").value,
    end_date: document.getElementById("plan-end-date").value,
    phases: collectPlanPhases(),
  };
  const status = document.getElementById("plan-status").value;

  if (!payload.title || !payload.start_date || !payload.end_date) {
    showToast("信息不完整", "计划标题、开始日期和结束日期不能为空。", "error");
    return;
  }

  try {
    if (taskPageState.editingPlanId) {
      await api.put(`/plans/${taskPageState.editingPlanId}`, payload);
      await api.put(`/plans/${taskPageState.editingPlanId}/status`, { status });
      showToast("计划已更新", "学习计划内容已经保存。", "success");
    } else {
      await api.post("/plans", payload);
      showToast("计划已创建", "现在可以继续往各阶段挂任务了。", "success");
    }
    closeModal("plan-modal");
    await loadTaskPageData();
  } catch (error) {
    showToast("保存失败", error.message, "error");
  }
}

async function deletePlan(planId) {
  const plan = taskPageState.plans.find((item) => item.id === planId);
  if (!plan) return;
  if (!confirm(`确定删除计划“${plan.title}”吗？`)) return;

  try {
    await api.del(`/plans/${planId}`);
    if (taskPageState.activePlanFilterId === planId) {
      taskPageState.activePlanFilterId = null;
      taskPageState.activePlanFilterTitle = "";
    }
    showToast("计划已删除", "学习计划已经从列表中移除。", "success");
    await loadTaskPageData();
  } catch (error) {
    showToast("删除失败", error.message, "error");
  }
}

async function showPlanDetail(planId) {
  try {
    const [plan, tasks] = await Promise.all([api.get(`/plans/${planId}`), api.get("/tasks")]);
    const planTasks = tasks.filter((task) => task.plan_id === planId);

    openModal(
      "plan-detail-modal",
      `
        <div class="modal plan-detail-modal">
          <h3>计划详情</h3>
          <div class="plan-detail-summary-grid">
            <article class="plan-summary-card">
              <span>计划标题</span>
              <strong>${escapeTaskHtml(plan.title)}</strong>
              <small>${plan.start_date} 至 ${plan.end_date}</small>
            </article>
            <article class="plan-summary-card">
              <span>当前状态</span>
              <strong>${planStatusLabel(plan.status)}</strong>
              <small>${plan.phases?.length || 0} 个阶段</small>
            </article>
            <article class="plan-summary-card">
              <span>主任务进度</span>
              <strong>${plan.completed_task_count || 0}/${plan.task_count || 0}</strong>
              <small>${(plan.progress_percent || 0).toFixed(0)}%</small>
            </article>
            <article class="plan-summary-card">
              <span>子任务进度</span>
              <strong>${plan.completed_subtask_count || 0}/${plan.subtask_count || 0}</strong>
              <small>按天安排 ${plan.day_schedule?.length || 0} 天</small>
            </article>
          </div>

          <div class="detail-block detail-block-lead">
            <span>计划说明</span>
            <p>${escapeTaskHtml(plan.description || "暂无计划说明")}</p>
          </div>

          <div class="plan-detail-sections">
            ${renderPhaseDetail(plan.phases || [])}
            ${renderDaySchedule(plan.day_schedule || [])}
            ${renderWeekSchedule(plan.week_schedule || [])}
            ${renderPlanTaskTree(planTasks)}
          </div>
          <div class="modal-actions">
            <button class="btn btn-outline" onclick="closeModal('plan-detail-modal')">关闭</button>
          </div>
        </div>
      `,
    );
  } catch (error) {
    showToast("加载失败", error.message, "error");
  }
}

function renderPhaseDetail(phases) {
  if (!phases.length) {
    return `
      <div class="detail-block">
        <span>阶段视图</span>
        <p>这个计划还没有阶段。你可以在编辑计划时补上阶段安排。</p>
      </div>
    `;
  }

  return `
    <div class="detail-block">
      <span>阶段视图</span>
      <div class="phase-detail-list">
        ${phases
          .map(
            (phase) => `
          <article class="phase-detail-card">
            <div class="phase-detail-top">
              <strong>${escapeTaskHtml(phase.title)}</strong>
              <span>${Number(phase.progress_percent || 0).toFixed(0)}%</span>
            </div>
            ${phase.description ? `<p>${escapeTaskHtml(phase.description)}</p>` : ""}
            <small>${phase.start_date || "未设开始"} 至 ${phase.end_date || "未设结束"}</small>
            <div class="progress-track"><div class="progress-fill" style="width:${phase.progress_percent || 0}%"></div></div>
            <small>${phase.completed_task_count || 0}/${phase.task_count || 0} 个主任务</small>
          </article>
        `,
          )
          .join("")}
      </div>
    </div>
  `;
}

function renderDaySchedule(daySchedule) {
  if (!daySchedule.length) {
    return `
      <div class="detail-block">
        <span>按天安排</span>
        <p>当前还没有按天安排的任务。给任务设置安排日期后，这里会自动生成。</p>
      </div>
    `;
  }

  return `
    <div class="detail-block">
      <span>按天安排</span>
      <div class="schedule-list">
        ${daySchedule
          .map(
            (item) => `
          <div class="schedule-card">
            <strong>${escapeTaskHtml(item.label)}</strong>
            <small>${item.completed_task_count}/${item.task_count} 个主任务已完成</small>
            <p>${(item.task_titles || []).length ? escapeTaskHtml(item.task_titles.join("、")) : "暂无任务标题"}</p>
          </div>
        `,
          )
          .join("")}
      </div>
    </div>
  `;
}

function renderWeekSchedule(weekSchedule) {
  if (!weekSchedule.length) {
    return `
      <div class="detail-block">
        <span>按周安排</span>
        <p>当前还没有可以按周聚合的安排。</p>
      </div>
    `;
  }

  return `
    <div class="detail-block">
      <span>按周安排</span>
      <div class="schedule-list">
        ${weekSchedule
          .map(
            (item) => `
          <div class="schedule-card">
            <strong>${escapeTaskHtml(item.week_label)}</strong>
            <small>${item.completed_task_count}/${item.task_count} 个主任务已完成</small>
            <p>${escapeTaskHtml((item.dates || []).join(" / "))}</p>
          </div>
        `,
          )
          .join("")}
      </div>
    </div>
  `;
}

function renderPlanTaskTree(tasks) {
  if (!tasks.length) {
    return `
      <div class="detail-block">
        <span>任务树</span>
        <p>这个计划下还没有任务。你可以先新增一个主任务，再在主任务下面拆分子任务。</p>
      </div>
    `;
  }

  return `
    <div class="detail-block">
      <span>任务树</span>
      <div class="detail-task-tree">
        ${tasks.map((task) => renderPlanDetailTask(task)).join("")}
      </div>
    </div>
  `;
}

function renderPlanDetailTask(task, depth = 0) {
  const children = task.children || [];
  const phaseName = task.phase_id ? resolvePhaseTitle(task.plan_id, task.phase_id) : null;
  const groupedChildren = depth === 0 ? renderDayTaskGroups(children, task.plan_id, { detail: true }) : "";

  return `
    <div class="detail-task-node ${depth > 0 ? "detail-task-node-child" : ""}">
      <div class="detail-task-item">
        <div class="detail-task-main">
          <strong>${depth > 0 ? "↳ " : ""}${escapeTaskHtml(task.title)}</strong>
          ${task.description ? `<p>${escapeTaskHtml(task.description)}</p>` : ""}
          <p class="detail-subtask-summary">
            ${phaseName ? `阶段：${escapeTaskHtml(phaseName)} / ` : ""}
            顺序 ${task.sort_order || 0}
            ${task.scheduled_date ? ` / 安排 ${task.scheduled_date}` : ""}
          </p>
          ${task.subtask_count > 0 ? `<p class="detail-subtask-summary">子任务进度：${task.completed_subtask_count}/${task.subtask_count}</p>` : ""}
        </div>
        <div class="detail-task-side">
          <span class="badge badge-${task.status}">${statusLabel(task.status)}</span>
          <small>${task.due_date ? `截止：${formatTaskDate(task.due_date)}` : "未设置截止时间"}</small>
          <div class="detail-task-actions">
            ${
              depth === 0
                ? focusState.activeTaskId === task.id
                  ? `<button class="btn btn-outline btn-sm" onclick="stopFocusSession()">结束学习</button>`
                  : `<button class="btn btn-outline btn-sm" onclick="startFocusSession(${task.id})">开始学习</button>`
                : ""
            }
            <button class="btn btn-outline btn-sm" onclick="openTaskFromPlanDetail(${task.id})">编辑</button>
            <button class="btn btn-primary btn-sm" onclick="toggleTaskStatusFromPlanDetail(${task.id}, '${task.status === "completed" ? "pending" : "completed"}')">
              ${task.status === "completed" ? "重开" : "完成"}
            </button>
          </div>
        </div>
      </div>
      ${
        children.length
          ? `<div class="detail-task-children">${
              depth === 0 ? groupedChildren : children.map((child) => renderPlanDetailTask(child, depth + 1)).join("")
            }</div>`
          : ""
      }
    </div>
  `;
}

function openModal(id, innerHtml) {
  closeModal(id);
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.id = id;
  overlay.innerHTML = innerHtml;
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) {
      closeModal(id);
    }
  });
  document.body.appendChild(overlay);
}

function closeModal(id) {
  document.getElementById(id)?.remove();
}

function openTaskFromPlanDetail(taskId) {
  closeModal("plan-detail-modal");
  showEditTaskModal(taskId);
}

async function toggleTaskStatusFromPlanDetail(taskId, nextStatus) {
  const currentFilterPlanId = taskPageState.activePlanFilterId;
  await toggleTaskStatus(taskId, nextStatus);
  const targetPlanId = currentFilterPlanId || findTaskById(taskId)?.plan_id;
  if (targetPlanId) {
    await showPlanDetail(targetPlanId);
  }
}

function findTaskById(taskId, tasks = taskPageState.tasks) {
  for (const task of tasks) {
    if (task.id === taskId) return task;
    if (task.children?.length) {
      const child = findTaskById(taskId, task.children);
      if (child) return child;
    }
  }
  return null;
}

function parseOptionalInt(value) {
  if (value === "" || value == null) return null;
  const parsed = parseInt(value, 10);
  return Number.isNaN(parsed) ? null : parsed;
}

function toDateTimeLocalValue(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (part) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatTaskDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间格式错误";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function resolvePlanTitle(planId) {
  if (!planId) return "未绑定计划";
  return taskPageState.plans.find((plan) => plan.id === planId)?.title || `计划 #${planId}`;
}

function resolvePhaseTitle(planId, phaseId) {
  if (!planId || !phaseId) return "未绑定阶段";
  const plan = taskPageState.plans.find((item) => item.id === planId);
  return plan?.phases?.find((phase) => phase.id === phaseId)?.title || `阶段 #${phaseId}`;
}

function priorityLabel(priority) {
  return {
    high: "高优先级",
    medium: "中优先级",
    low: "低优先级",
  }[priority] || priority;
}

function statusLabel(status) {
  return {
    pending: "待处理",
    in_progress: "进行中",
    completed: "已完成",
    overdue: "已逾期",
  }[status] || status;
}

function planStatusLabel(status) {
  return {
    active: "进行中",
    completed: "已完成",
    archived: "已归档",
  }[status] || status;
}

function escapeTaskHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}

function escapeAttr(value) {
  return escapeTaskHtml(value).replace(/"/g, "&quot;");
}

window.addEventListener("beforeunload", () => {
  if (focusState.activeTaskId) {
    syncFocusMinutes(true);
  }
});

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden" && focusState.activeTaskId) {
    syncFocusMinutes(true);
  }
});
