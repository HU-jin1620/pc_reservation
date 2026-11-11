// 登录 / 注册
(function () {
  const REMEMBERED_USERNAME_KEY = 'booking.rememberedUsername';

  function readRememberedUsername() {
    try { return localStorage.getItem(REMEMBERED_USERNAME_KEY) || ''; }
    catch (err) { return ''; }
  }

  function saveRememberedUsername(username) {
    try {
      if (username) localStorage.setItem(REMEMBERED_USERNAME_KEY, username);
      else localStorage.removeItem(REMEMBERED_USERNAME_KEY);
    } catch (err) {
      // 浏览器禁用本地存储时仍可正常登录，只是不预填用户名。
    }
  }

  const loginForm = document.getElementById('loginForm');
  if (loginForm) {
    const usernameInput = loginForm.querySelector('input[name="username"]');
    const passwordInput = loginForm.querySelector('input[name="password"]');
    const rememberInput = document.getElementById('rememberMe');
    const rememberedUsername = readRememberedUsername();
    if (rememberedUsername) {
      usernameInput.value = rememberedUsername;
      rememberInput.checked = true;
      passwordInput.focus();
    }

    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(loginForm);
      const username = String(fd.get('username') || '').trim();
      const remember = rememberInput.checked;
      try {
        await api('/api/login', { method: 'POST', body: {
          username, password: fd.get('password'), remember,
        }});
        saveRememberedUsername(remember ? username : '');
        location.href = '/booking';
      } catch (err) { toast(err.message, 'error'); }
    });
  }

  const regForm = document.getElementById('registerForm');
  if (regForm) {
    regForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(regForm);
      const username = fd.get('username').trim();
      const password = fd.get('password');
      const password2 = fd.get('password2');
      if (password !== password2) { toast('两次密码不一致', 'error'); return; }
      try {
        await api('/api/register', { method: 'POST', body: { username, password } });
        toast('注册成功');
        location.href = '/booking';
      } catch (err) { toast(err.message, 'error'); }
    });
  }
})();
