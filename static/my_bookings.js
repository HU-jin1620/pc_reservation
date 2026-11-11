// 我的预定
(function () {
  const tbody = document.querySelector('#myTable tbody');
  const modal = document.getElementById('cancelBookingModal');
  const confirmBtn = document.getElementById('confirmCancelBooking');
  let myBookings = [];
  let pendingBooking = null;

  function esc(s) {
    return (s == null ? '' : String(s)).replace(/[&<>"']/g,
      c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function formatHours(hours) {
    if (!hours.length) return '';
    const parts = [];
    let start = hours[0], prev = hours[0];
    for (let i = 1; i < hours.length; i++) {
      if (hours[i] === prev + 1) { prev = hours[i]; continue; }
      parts.push(formatHourRange(start, prev));
      start = prev = hours[i];
    }
    parts.push(formatHourRange(start, prev));
    return parts.join('、');
  }

  function formatHourRange(start, end) {
    const fmt = h => String(h).padStart(2, '0') + ':00';
    return start === end ? fmt(start) : fmt(start) + '-' + fmt(end + 1);
  }

  async function load() {
    try {
      const data = await api('/api/my_bookings');
      myBookings = data.bookings;
      render();
      populateDevices();
    } catch (err) { toast(err.message, 'error'); }
  }

  function render() {
    if (!myBookings.length) {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#9ca3af">暂无预定</td></tr>';
      return;
    }
    tbody.innerHTML = myBookings.map((b, index) => `
      <tr class="booking-row" data-booking-index="${index}" tabindex="0" title="点击取消整个时间段">
        <td>${esc(b.device_name)}</td>
        <td>${esc(b.date)}</td>
        <td>${esc(formatHours(b.hours))}</td>
        <td><button type="button" class="link-btn danger cancel-one-btn">取消</button></td>
      </tr>`).join('');
  }

  function openCancelModal(index) {
    const booking = myBookings[index];
    if (!booking) return;
    pendingBooking = booking;
    document.getElementById('cancelDevice').textContent = booking.device_name;
    document.getElementById('cancelDate').textContent = booking.date;
    document.getElementById('cancelHours').textContent = formatHours(booking.hours);
    modal.hidden = false;
    document.getElementById('closeCancelModal').focus();
  }

  function closeCancelModal() {
    modal.hidden = true;
    pendingBooking = null;
    confirmBtn.disabled = false;
    confirmBtn.textContent = '确认取消';
  }

  function populateDevices() {
    const sel = document.getElementById('cDevice');
    const names = [...new Set(myBookings.map(b => b.device_name))].sort();
    sel.innerHTML = names.map(n => '<option value="' + esc(n) + '">' + esc(n) + '</option>').join('');
    const all = document.getElementById('cAllDevices');
    all.checked = true;
    sel.hidden = true;
  }

  function toDateStr(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return y + '-' + m + '-' + day;
  }

  (function initSelects() {
    const today = toDateStr(new Date());
    document.getElementById('cStart').value = today;
    document.getElementById('cEnd').value = today;
    const ss = document.getElementById('cHourStart');
    const se = document.getElementById('cHourEnd');
    for (let h = 0; h < 24; h++) ss.add(new Option(h + ' 点', h));
    for (let h = 1; h <= 24; h++) se.add(new Option(h + ' 点', h));
    ss.value = '0';
    se.value = '24';
  })();

  document.getElementById('cAllDevices').addEventListener('change', (e) => {
    document.getElementById('cDevice').hidden = e.target.checked;
  });

  tbody.addEventListener('click', (e) => {
    const row = e.target.closest('.booking-row');
    if (row) openCancelModal(Number(row.dataset.bookingIndex));
  });

  tbody.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const row = e.target.closest('.booking-row');
    if (!row) return;
    e.preventDefault();
    openCancelModal(Number(row.dataset.bookingIndex));
  });

  document.getElementById('closeCancelModal').addEventListener('click', closeCancelModal);
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeCancelModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal.hidden) closeCancelModal();
  });

  confirmBtn.addEventListener('click', async () => {
    if (!pendingBooking) return;
    const booking = pendingBooking;
    confirmBtn.disabled = true;
    confirmBtn.textContent = '取消中...';
    try {
      const r = await api('/api/bookings', {
        method: 'DELETE',
        body: {
          device_names: [booking.device_name],
          start_date: booking.date,
          end_date: booking.date,
          hours: booking.hours
        }
      });
      closeCancelModal();
      toast('已取消 ' + r.cancelled + ' 个时段', 'success');
      load();
    } catch (err) {
      confirmBtn.disabled = false;
      confirmBtn.textContent = '确认取消';
      toast(err.message, 'error');
    }
  });

  document.getElementById('bulkCancelBtn').addEventListener('click', async () => {
    const startDate = document.getElementById('cStart').value;
    const endDate = document.getElementById('cEnd').value;
    const startHour = parseInt(document.getElementById('cHourStart').value, 10);
    const endHour = parseInt(document.getElementById('cHourEnd').value, 10);
    if (!startDate || !endDate || startDate > endDate) { toast('日期范围不正确', 'error'); return; }
    if (endHour <= startHour) { toast('结束小时必须大于开始小时', 'error'); return; }
    let deviceNames;
    if (document.getElementById('cAllDevices').checked) {
      deviceNames = [...new Set(myBookings.map(b => b.device_name))];
    } else {
      deviceNames = [document.getElementById('cDevice').value];
    }
    if (!deviceNames.length) { toast('没有可取消的设备', 'error'); return; }
    const hours = [];
    for (let h = startHour; h < endHour; h++) hours.push(h);
    if (!confirm('确定取消所选时间范围内本人 ' + deviceNames.length + ' 台设备的预订？')) return;
    try {
      const r = await api('/api/bookings', { method: 'DELETE', body: { device_names: deviceNames, start_date: startDate, end_date: endDate, hours } });
      toast('已取消 ' + r.cancelled + ' 个时段', 'success');
      load();
    } catch (err) { toast(err.message, 'error'); }
  });

  document.getElementById('refreshBtn').addEventListener('click', load);
  load();
})();
