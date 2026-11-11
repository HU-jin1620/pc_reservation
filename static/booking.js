// 预定列表
(function () {
  const datePicker = document.getElementById('datePicker');
  const dateLabel = document.getElementById('dateLabel');
  const grid = document.getElementById('grid');
  const bulkDeviceMap = new Map();

  function toDateStr(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return y + '-' + m + '-' + day;
  }
  function parseDate(s) {
    const p = s.split('-').map(Number);
    return new Date(p[0], p[1] - 1, p[2]);
  }
  function isPastSlot(dateStr, hour) {
    const now = new Date();
    const today = toDateStr(now);
    if (dateStr < today) return true;
    if (dateStr === today && hour <= now.getHours()) return true;
    return false;
  }

  function currentDate() { return datePicker.value; }
  function setDate(s) { datePicker.value = s; dateLabel.textContent = s; }

  function shiftDay(delta) {
    const d = parseDate(currentDate());
    d.setDate(d.getDate() + delta);
    setDate(toDateStr(d));
    loadGrid();
  }

  async function loadGrid() {
    try {
      const data = await api('/api/bookings?date=' + currentDate());
      renderGrid(data);
    } catch (err) { toast(err.message, 'error'); }
  }

  function renderGrid(data) {
    let html = '<table class="grid-table"><thead><tr><th class="dev-col">设备</th>';
    for (let h = 0; h < 24; h++) html += '<th>' + String(h).padStart(2, '0') + '</th>';
    html += '</tr></thead><tbody>';
    for (const dev of data.devices) {
      html += '<tr><td class="dev-col" title="' + dev.name + '">' + dev.name + '</td>';
      for (let h = 0; h < 24; h++) {
        const u = dev.slots[String(h)];
        let state, label;
        if (u) {
          label = u;
          state = (u === data.current_user) ? 'mine' : 'other';
        } else {
          label = '';
          state = isPastSlot(data.date, h) ? 'past' : 'free';
        }
        html += '<td class="cell ' + state + '" data-device="' + dev.name + '" data-hour="' + h +
          '" data-user="' + (u || '') + '">' + label + '</td>';
      }
      html += '</tr>';
    }
    html += '</tbody></table>';
    grid.innerHTML = html;
  }

  grid.addEventListener('click', async (e) => {
    const cell = e.target.closest('.cell');
    if (!cell) return;
    const device = cell.dataset.device;
    const hour = parseInt(cell.dataset.hour, 10);
    const user = cell.dataset.user;
    const date = currentDate();

    if (user && user !== window.CURRENT_USER) {
      toast('已被 ' + user + ' 预定', 'error');
      return;
    }
    if (!user && isPastSlot(date, hour)) {
      toast('过去时段不可预定', 'error');
      return;
    }
    const payload = { device_names: [device], start_date: date, end_date: date, hours: [hour] };
    try {
      if (user) { // 本人 → 取消
        if (isPastSlot(date, hour)) { toast('过去时段不可取消', 'error'); return; }
        const r = await api('/api/bookings', { method: 'DELETE', body: payload });
        toast(r.cancelled ? '已取消' : '未找到可取消的预订');
      } else { // 空闲 → 预定
        const r = await api('/api/bookings', { method: 'POST', body: payload });
        toast(r.booked ? '已预定' : '该时段已被占用', r.booked ? 'success' : 'error');
      }
      loadGrid();
    } catch (err) { toast(err.message, 'error'); }
  });

  document.getElementById('prevDay').addEventListener('click', () => shiftDay(-1));
  document.getElementById('nextDay').addEventListener('click', () => shiftDay(1));
  document.getElementById('todayBtn').addEventListener('click', () => { setDate(toDateStr(new Date())); loadGrid(); });
  datePicker.addEventListener('change', loadGrid);

  // ---- 批量预定 ----
  function appendConfigCell(row, value) {
    const cell = document.createElement('td');
    const text = value || '';
    cell.textContent = text || '—';
    cell.title = text;
    if (!text) cell.classList.add('bulk-config-missing');
    row.appendChild(cell);
  }

  function renderBulkConfig() {
    const body = document.getElementById('bulkConfigBody');
    const count = document.getElementById('bulkConfigCount');
    const selectedNames = [...document.querySelectorAll('.bulk-dev:checked')].map(cb => cb.value);
    body.replaceChildren();
    count.textContent = selectedNames.length ? '已选 ' + selectedNames.length + ' 台' : '未选择';

    if (!selectedNames.length) {
      const row = document.createElement('tr');
      row.className = 'bulk-config-empty';
      const cell = document.createElement('td');
      cell.colSpan = 6;
      cell.textContent = '勾选左侧设备后显示配置';
      row.appendChild(cell);
      body.appendChild(row);
      return;
    }

    for (const name of selectedNames) {
      const device = bulkDeviceMap.get(name) || {};
      const row = document.createElement('tr');
      appendConfigCell(row, name);
      appendConfigCell(row, device.os);
      appendConfigCell(row, device.cpu);
      appendConfigCell(row, device.motherboard);
      appendConfigCell(row, device.motherboard_vendor);
      appendConfigCell(row, device.memory);
      body.appendChild(row);
    }
  }

  async function initBulk() {
    const startSel = document.getElementById('bkHourStart');
    const endSel = document.getElementById('bkHourEnd');
    for (let h = 0; h < 24; h++) startSel.add(new Option(h + ' 点', h));
    for (let h = 1; h <= 24; h++) endSel.add(new Option(h + ' 点', h));
    startSel.value = '9';
    endSel.value = '18';

    const today = toDateStr(new Date());
    document.getElementById('bkStart').value = today;
    document.getElementById('bkEnd').value = today;

    try {
      const data = await api('/api/devices');
      const box = document.getElementById('bulkDevices');
      for (const d of data.devices) {
        bulkDeviceMap.set(d.name, d);
        const lab = document.createElement('label');
        lab.className = 'check-item';
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'bulk-dev';
        checkbox.value = d.name;
        checkbox.checked = true;
        lab.appendChild(checkbox);
        lab.appendChild(document.createTextNode(' ' + d.name));
        box.appendChild(lab);
      }
      renderBulkConfig();
    } catch (err) {
      document.getElementById('bulkConfigCount').textContent = '加载失败';
      toast(err.message, 'error');
    }
  }

  document.getElementById('bulkAll').addEventListener('change', (e) => {
    document.querySelectorAll('.bulk-dev').forEach(cb => { cb.checked = e.target.checked; });
    e.target.indeterminate = false;
    renderBulkConfig();
  });

  document.getElementById('bulkDevices').addEventListener('change', (e) => {
    if (!e.target.matches('.bulk-dev')) return;
    const boxes = [...document.querySelectorAll('.bulk-dev')];
    const checked = boxes.filter(cb => cb.checked).length;
    const all = document.getElementById('bulkAll');
    all.checked = boxes.length > 0 && checked === boxes.length;
    all.indeterminate = checked > 0 && checked < boxes.length;
    renderBulkConfig();
  });

  document.getElementById('bulkBookBtn').addEventListener('click', async () => {
    const deviceNames = [...document.querySelectorAll('.bulk-dev:checked')].map(cb => cb.value);
    const startDate = document.getElementById('bkStart').value;
    const endDate = document.getElementById('bkEnd').value;
    const startHour = parseInt(document.getElementById('bkHourStart').value, 10);
    const endHour = parseInt(document.getElementById('bkHourEnd').value, 10);
    if (!deviceNames.length) { toast('请选择设备', 'error'); return; }
    if (!startDate || !endDate || startDate > endDate) { toast('日期范围不正确', 'error'); return; }
    if (endHour <= startHour) { toast('结束小时必须大于开始小时', 'error'); return; }
    const hours = [];
    for (let h = startHour; h < endHour; h++) hours.push(h);
    try {
      const r = await api('/api/bookings', { method: 'POST', body: { device_names: deviceNames, start_date: startDate, end_date: endDate, hours } });
      toast('已预定 ' + r.booked + ' 个时段，跳过 ' + r.skipped + ' 个', 'success');
      loadGrid();
    } catch (err) { toast(err.message, 'error'); }
  });

  // 初始化
  setDate(toDateStr(new Date()));
  initBulk();
  loadGrid();
})();
