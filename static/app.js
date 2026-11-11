// 公共工具：fetch 封装、toast、退出登录
async function api(path, options = {}) {
  const opts = Object.assign({ headers: {} }, options);
  if (opts.body && typeof opts.body !== 'string') {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(opts.body);
  }
  const resp = await fetch(path, opts);
  let data = null;
  try { data = await resp.json(); } catch (e) { /* ignore */ }
  if (!resp.ok) {
    const msg = (data && data.error) || ('请求失败 ' + resp.status);
    throw new Error(msg);
  }
  return data;
}

function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

document.addEventListener('click', (e) => {
  if (e.target && e.target.id === 'logoutBtn') {
    api('/api/logout', { method: 'POST' })
      .then(() => { location.href = '/login'; })
      .catch(() => { location.href = '/login'; });
  }
});

document.addEventListener('DOMContentLoaded', () => {
  const modal = document.getElementById('accountModal');
  const openBtn = document.getElementById('accountBtn');
  const closeBtn = document.getElementById('closeAccountModal');
  const cancelBtn = document.getElementById('cancelAccountBtn');
  const form = document.getElementById('changePasswordForm');
  if (!modal || !openBtn || !form) return;

  const submitBtn = document.getElementById('changePasswordBtn');

  function closeAccountModal() {
    modal.hidden = true;
    form.reset();
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = '修改密码';
    }
  }

  function openAccountModal() {
    modal.hidden = false;
    const input = form.querySelector('input[name="current_password"]');
    if (input) input.focus();
  }

  openBtn.addEventListener('click', openAccountModal);
  if (closeBtn) closeBtn.addEventListener('click', closeAccountModal);
  if (cancelBtn) cancelBtn.addEventListener('click', closeAccountModal);
  modal.addEventListener('click', (event) => {
    if (event.target === modal) closeAccountModal();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !modal.hidden) closeAccountModal();
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    const newPassword = formData.get('new_password') || '';
    const confirmPassword = formData.get('confirm_password') || '';
    if (newPassword !== confirmPassword) {
      toast('两次输入的新密码不一致', 'error');
      return;
    }
    submitBtn.disabled = true;
    submitBtn.textContent = '修改中...';
    try {
      await api('/api/change_password', {
        method: 'POST',
        body: {
          current_password: formData.get('current_password') || '',
          new_password: newPassword,
          confirm_password: confirmPassword,
        },
      });
      closeAccountModal();
      toast('密码已修改', 'success');
    } catch (error) {
      submitBtn.disabled = false;
      submitBtn.textContent = '修改密码';
      toast(error.message, 'error');
    }
  });
});
