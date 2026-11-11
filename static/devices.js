// 设备管理
(function () {
  const tbody = document.querySelector('#devTable tbody');
  const modal = document.getElementById('modal');
  const form = document.getElementById('devForm');
  const modalTitle = document.getElementById('modalTitle');
  const searchInput = document.getElementById('searchInput');
  let allDevices = [];

  function esc(s) {
    return (s == null ? '' : String(s)).replace(/[&<>"']/g,
      c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  async function load() {
    try {
      const data = await api('/api/devices');
      allDevices = data.devices;
      render();
    } catch (err) { toast(err.message, 'error'); }
  }

  function render() {
    const kw = searchInput.value.trim().toLowerCase();
    const list = allDevices.filter(d =>
      !kw || d.name.toLowerCase().includes(kw) || d.ip.includes(kw));
    tbody.innerHTML = list.map(d => `
      <tr>
        <td>${esc(d.name)}</td><td>${esc(d.ip)}</td><td>${esc(d.location)}</td>
        <td>${esc(d.os)}</td><td>${esc(d.cpu)}</td><td>${esc(d.motherboard)}</td>
        <td>${esc(d.motherboard_vendor)}</td><td>${esc(d.memory)}</td>
        <td class="actions">
          <button class="link-btn" data-act="edit" data-id="${d.id}">编辑</button>
          <button class="link-btn danger" data-act="del" data-id="${d.id}">删除</button>
        </td>
      </tr>`).join('');
  }

  function openModal(device) {
    form.reset();
    modalTitle.textContent = device ? '编辑设备' : '新增设备';
    form.id.value = device ? device.id : '';
    for (const k of ['name', 'ip', 'location', 'os', 'cpu', 'motherboard', 'motherboard_vendor', 'memory']) {
      form[k].value = device ? (device[k] || '') : (k === 'location' ? '深圳' : '');
    }
    modal.hidden = false;
  }
  function closeModal() { modal.hidden = true; }

  tbody.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-act]');
    if (!btn) return;
    const id = btn.dataset.id;
    const device = allDevices.find(d => String(d.id) === id);
    if (btn.dataset.act === 'edit') openModal(device);
    else if (btn.dataset.act === 'del') {
      if (!confirm('确定删除设备 ' + (device ? device.name : '') + ' ？其关联预订也会删除。')) return;
      api('/api/devices/' + id, { method: 'DELETE' })
        .then(() => { toast('已删除', 'success'); load(); })
        .catch(err => toast(err.message, 'error'));
    }
  });

  document.getElementById('addBtn').addEventListener('click', () => openModal(null));
  document.getElementById('cancelBtn').addEventListener('click', closeModal);
  modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
  searchInput.addEventListener('input', render);

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const payload = {};
    for (const k of ['name', 'ip', 'location', 'os', 'cpu', 'motherboard', 'motherboard_vendor', 'memory']) {
      payload[k] = (fd.get(k) || '').trim();
    }
    const id = fd.get('id');
    try {
      if (id) await api('/api/devices/' + id, { method: 'PUT', body: payload });
      else await api('/api/devices', { method: 'POST', body: payload });
      toast('已保存', 'success');
      closeModal();
      load();
    } catch (err) { toast(err.message, 'error'); }
  });

  load();
})();
