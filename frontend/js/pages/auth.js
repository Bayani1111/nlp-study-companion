/**
 * Authentication pages.
 */

function renderLogin() {
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="auth-container card">
      <h2>登录</h2>
      <p class="section-note">登录后可以继续管理任务、计划和提醒。</p>
      <div id="auth-error" class="form-error" style="display:none;"></div>
      <div class="form-group">
        <label>用户名</label>
        <input class="form-control" type="text" id="login-username" placeholder="请输入用户名">
      </div>
      <div class="form-group">
        <label>密码</label>
        <input class="form-control" type="password" id="login-password" placeholder="请输入密码">
      </div>
      <button class="btn btn-primary auth-submit" onclick="handleLogin()">登录</button>
      <div class="switch-link">
        还没有账号？<a href="#register">立即注册</a>
      </div>
    </div>
  `;

  setTimeout(() => {
    const pwdInput = document.getElementById('login-password');
    if (pwdInput) {
      pwdInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') handleLogin();
      });
    }
  }, 0);
}

async function handleLogin() {
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;
  const errEl = document.getElementById('auth-error');

  if (!username || !password) {
    errEl.textContent = '请填写用户名和密码。';
    errEl.style.display = 'block';
    return;
  }

  try {
    const data = await api.post('/auth/login', { username, password });
    localStorage.setItem('user', JSON.stringify(data.user));
    connectReminderWS();
    window.location.hash = '#chat';
  } catch (error) {
    errEl.textContent = error.message;
    errEl.style.display = 'block';
  }
}

function renderRegister() {
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="auth-container card">
      <h2>注册</h2>
      <p class="section-note">创建账号后，你的任务、计划和提醒会和当前账号绑定。</p>
      <div id="auth-error" class="form-error" style="display:none;"></div>
      <div class="form-group">
        <label>用户名</label>
        <input class="form-control" type="text" id="reg-username" placeholder="3-50 位字母、数字或下划线">
      </div>
      <div class="form-group">
        <label>邮箱</label>
        <input class="form-control" type="email" id="reg-email" placeholder="请输入邮箱">
      </div>
      <div class="form-group">
        <label>密码</label>
        <input class="form-control" type="password" id="reg-password" placeholder="至少 8 位，包含字母和数字">
      </div>
      <button class="btn btn-primary auth-submit" onclick="handleRegister()">注册</button>
      <div class="switch-link">
        已有账号？<a href="#login">去登录</a>
      </div>
    </div>
  `;
}

async function handleRegister() {
  const username = document.getElementById('reg-username').value.trim();
  const email = document.getElementById('reg-email').value.trim();
  const password = document.getElementById('reg-password').value;
  const errEl = document.getElementById('auth-error');

  if (!username || !email || !password) {
    errEl.textContent = '请填写所有字段。';
    errEl.style.display = 'block';
    return;
  }

  try {
    const data = await api.post('/auth/register', { username, email, password });
    localStorage.setItem('user', JSON.stringify(data.user));
    connectReminderWS();
    window.location.hash = '#chat';
  } catch (error) {
    errEl.textContent = error.message;
    errEl.style.display = 'block';
  }
}
