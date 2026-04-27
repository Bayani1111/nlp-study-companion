/**
 * Study statistics page.
 */

function renderStats() {
  const today = new Date();
  const thirtyDaysAgo = new Date(today);
  thirtyDaysAgo.setDate(today.getDate() - 30);

  const app = document.getElementById("app");
  app.innerHTML = `
    <div class="stats-page">
      <section class="card stats-hero">
        <div>
          <p class="eyebrow">学习趋势</p>
          <h2>把任务推进、学习时长和提醒节奏放到同一块看板里</h2>
          <p class="section-note">这里会展示学习时长、连续学习、阶段达成率和任务完成节奏。任务页的专注计时会自动把学习时长同步到这里。</p>
        </div>
      </section>

      <section class="card date-range-picker">
        <label>统计区间</label>
        <input type="date" id="stats-start" value="${formatDateISO(thirtyDaysAgo)}">
        <span>至</span>
        <input type="date" id="stats-end" value="${formatDateISO(today)}">
        <button class="btn btn-outline btn-sm" onclick="refreshStats()">刷新统计</button>
      </section>

      <div class="stats-cards" id="stats-cards">正在加载...</div>

      <div class="stats-grid">
        <div class="chart-container">
          <h4>每日学习时长（分钟）</h4>
          <canvas id="bar-chart" height="220"></canvas>
        </div>
        <div class="chart-container">
          <h4>任务优先级分布</h4>
          <canvas id="pie-chart" height="220"></canvas>
        </div>
        <div class="chart-container">
          <h4>每周学习节奏</h4>
          <canvas id="weekday-chart" height="220"></canvas>
        </div>
        <div class="chart-container">
          <h4>任务完成时段</h4>
          <canvas id="rhythm-chart" height="220"></canvas>
        </div>
      </div>

      <div class="chart-container">
        <h4>任务与阶段达成概览</h4>
        <div id="task-stats-detail">正在加载...</div>
      </div>
    </div>
  `;
  refreshStats();
}

function formatDateISO(date) {
  return date.toISOString().split("T")[0];
}

async function refreshStats() {
  const start = document.getElementById("stats-start").value;
  const end = document.getElementById("stats-end").value;

  try {
    const [overview, taskStats, weeklyStats, todayStats] = await Promise.all([
      api.get(`/stats/overview?start=${start}&end=${end}`),
      api.get("/stats/tasks"),
      api.get("/stats/weekly"),
      api.get("/stats/daily"),
    ]);

    renderStatCards(overview, todayStats);
    drawBarChart(overview.daily_breakdown || {}, "bar-chart", "暂无学习时长");
    drawPieChart(overview.priority_distribution || taskStats.priority_distribution || {});
    drawBarChart(overview.weekday_distribution || {}, "weekday-chart", "暂无学习节奏");
    drawBarChart(overview.completion_rhythm || {}, "rhythm-chart", "暂无完成记录");

    document.getElementById("task-stats-detail").innerHTML = `
      <div class="stats-inline">
        <span>待处理 <b>${taskStats.pending_tasks}</b></span>
        <span>进行中 <b>${taskStats.in_progress_tasks}</b></span>
        <span>已完成 <b>${taskStats.completed_tasks}</b></span>
        <span>已逾期 <b>${taskStats.overdue_tasks}</b></span>
        <span>阶段达成率 <b>${((taskStats.phase_completion_rate || 0) * 100).toFixed(1)}%</b></span>
        <span>本周学习 <b>${weeklyStats.total_study_minutes}</b> 分钟</span>
      </div>
    `;
  } catch (error) {
    document.getElementById("stats-cards").innerHTML = `
      <div class="empty-state compact">${escapeStatsHtml(error.message)}</div>
    `;
  }
}

function renderStatCards(overview, todayStats) {
  const completionRate = overview.completion_rate != null ? `${(overview.completion_rate * 100).toFixed(1)}%` : "0%";
  const phaseRate = overview.phase_completion_rate != null ? `${(overview.phase_completion_rate * 100).toFixed(1)}%` : "0%";

  document.getElementById("stats-cards").innerHTML = `
    <div class="stat-card">
      <div class="stat-value">${overview.total_study_minutes}</div>
      <div class="stat-label">累计学习分钟</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${overview.total_sessions || 0}</div>
      <div class="stat-label">学习记录次数</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${overview.streak_days || 0}</div>
      <div class="stat-label">连续学习天数</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${completionRate}</div>
      <div class="stat-label">任务完成率</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${phaseRate}</div>
      <div class="stat-label">阶段达成率</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${todayStats.study_minutes}</div>
      <div class="stat-label">今日学习分钟</div>
    </div>
  `;
}

function drawBarChart(dataMap, canvasId, emptyLabel) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = Math.max(320, rect.width - 40);
  canvas.height = 220;

  const width = canvas.width;
  const height = canvas.height;
  const padding = { top: 10, right: 10, bottom: 40, left: 50 };

  ctx.clearRect(0, 0, width, height);

  const entries = Object.entries(dataMap).sort((a, b) => a[0].localeCompare(b[0]));
  if (!entries.length || entries.every((entry) => entry[1] === 0)) {
    ctx.fillStyle = "#8b94a7";
    ctx.font = "13px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(emptyLabel, width / 2, height / 2);
    return;
  }

  const values = entries.map((entry) => entry[1]);
  const maxVal = Math.max(...values, 1);
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const barWidth = Math.max(4, Math.min(28, chartWidth / entries.length - 4));

  ctx.strokeStyle = "#e4e7ee";
  ctx.fillStyle = "#8b94a7";
  ctx.font = "11px sans-serif";
  ctx.textAlign = "right";

  for (let i = 0; i <= 4; i += 1) {
    const y = padding.top + chartHeight - (chartHeight * i) / 4;
    const value = Math.round((maxVal * i) / 4);
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(width - padding.right, y);
    ctx.stroke();
    ctx.fillText(value, padding.left - 6, y + 4);
  }

  ctx.fillStyle = "#4a6cf7";
  const totalBarSpace = chartWidth / entries.length;
  entries.forEach(([label, value], index) => {
    const x = padding.left + index * totalBarSpace + (totalBarSpace - barWidth) / 2;
    const barHeight = (value / maxVal) * chartHeight;
    const y = padding.top + chartHeight - barHeight;
    ctx.fillRect(x, y, barWidth, barHeight);

    ctx.save();
    ctx.fillStyle = "#8b94a7";
    ctx.font = "10px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(formatAxisLabel(label), x + barWidth / 2, height - padding.bottom + 14);
    ctx.restore();
  });
}

function drawPieChart(distData) {
  const canvas = document.getElementById("pie-chart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = Math.max(320, rect.width - 40);
  canvas.height = 220;

  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);

  const entries = Object.entries(distData).filter(([, value]) => value > 0);
  const total = entries.reduce((sum, [, value]) => sum + value, 0);

  if (!total) {
    ctx.fillStyle = "#8b94a7";
    ctx.font = "13px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("暂无任务优先级数据", width / 2, height / 2);
    return;
  }

  const colors = { high: "#e5534b", medium: "#d29922", low: "#2da44e" };
  const labels = { high: "高优先级", medium: "中优先级", low: "低优先级" };
  const centerX = width / 2 - 60;
  const centerY = height / 2;
  const outerRadius = Math.min(centerX, centerY) - 10;
  const innerRadius = outerRadius * 0.55;

  let startAngle = -Math.PI / 2;
  entries.forEach(([key, value]) => {
    const sliceAngle = (value / total) * Math.PI * 2;
    ctx.beginPath();
    ctx.arc(centerX, centerY, outerRadius, startAngle, startAngle + sliceAngle);
    ctx.arc(centerX, centerY, innerRadius, startAngle + sliceAngle, startAngle, true);
    ctx.closePath();
    ctx.fillStyle = colors[key] || "#9aa4b2";
    ctx.fill();
    startAngle += sliceAngle;
  });

  let legendY = 40;
  ctx.font = "12px sans-serif";
  ctx.textAlign = "left";
  entries.forEach(([key, value]) => {
    const legendX = width / 2 + 40;
    ctx.fillStyle = colors[key] || "#9aa4b2";
    ctx.fillRect(legendX, legendY - 8, 12, 12);
    ctx.fillStyle = "#2a3140";
    ctx.fillText(`${labels[key] || key}: ${value} (${((value / total) * 100).toFixed(0)}%)`, legendX + 18, legendY + 2);
    legendY += 24;
  });
}

function formatAxisLabel(label) {
  if (/^\d{4}-\d{2}-\d{2}$/.test(label)) {
    return label.slice(5);
  }
  return label.replace(":00", "");
}

function escapeStatsHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}
