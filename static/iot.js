// 互联设备：通过小米电源（miiocli）查询并控制主机上下电。
(function () {
  const grid = document.getElementById('iotGrid');
  const summary = document.getElementById('iotSummary');
  const refreshBtn = document.getElementById('refreshBtn');
  let devices = [];
  let busy = false;
  let dryRun = true;

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (char) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[char]));
  }

  function stateInfo(device) {
    if (device.configured === false || device.state === 'unconfigured') {
      return { label: '未配置电源', className: 'unconfigured' };
    }
    if (device.state === 'on') {
      return { label: '已上电', className: 'on' };
    }
    if (device.state === 'off') {
      return { label: '已断电', className: 'off' };
    }
    if (device.state === 'error') {
      return { label: '状态读取失败', className: 'error' };
    }
    return { label: '状态待确认', className: 'unknown' };
  }

  function render() {
    if (!devices.length) {
      grid.innerHTML = '<div class="power-empty">暂无设备</div>';
      return;
    }
    grid.innerHTML = devices.map((device) => {
      const info = stateInfo(device);
      const unconfigured = device.configured === false || device.state === 'unconfigured';
      const onDisabled = unconfigured || device.state === 'on' ? ' disabled' : '';
      const offDisabled = unconfigured || device.state === 'off' ? ' disabled' : '';
      const modeText = unconfigured
        ? '尚未配置小米电源映射'
        : (dryRun ? '演练模式：不会真正上下电' : '真实控制已启用');
      const errorText = device.error
        ? `<div class="power-error">${esc(device.error)}</div>`
        : '';
      const updatedText = device.state_updated_at
        ? `上次状态 ${esc(device.state_updated_at)}`
        : '尚未读取到状态';
      return `
        <article class="power-card" data-device-id="${device.id}">
          <div class="power-card-head">
            <div class="power-identity">
              <div class="power-host">${esc(device.name)}</div>
              <div class="power-ip">${esc(device.ip)}</div>
            </div>
            <span class="power-badge ${info.className}">
              <span class="dot"></span>${esc(info.label)}
            </span>
          </div>
          <div class="power-meta">
            <span>控制方式</span>
            <strong>小米电源</strong>
          </div>
          <div class="power-meta">
            <span>当前模式</span>
            <strong>${modeText}</strong>
          </div>
          <div class="power-meta">
            <span>状态记录</span>
            <strong>${updatedText}</strong>
          </div>
          ${errorText}
          <div class="power-controls">
            <button class="power-btn power-on" type="button"
              data-action="on" data-device-id="${device.id}"${onDisabled}>
              上电
            </button>
            <button class="power-btn power-off" type="button"
              data-action="off" data-device-id="${device.id}"${offDisabled}>
              断电
            </button>
          </div>
        </article>`;
    }).join('');
  }

  async function loadDevices() {
    refreshBtn.disabled = true;
    refreshBtn.textContent = '刷新中...';
    try {
      const data = await api('/api/iot/devices');
      devices = data.devices || [];
      dryRun = !!data.dry_run;
      render();
      const counts = data.summary || {};
      const mode = dryRun ? '演练模式' : '真实控制已启用';
      const unconfiguredText = counts.unconfigured ? ` · 未配置 ${counts.unconfigured}` : '';
      summary.textContent = `主机 ${counts.total || devices.length} 台 · 已上电 ${counts.on || 0} · 已断电 ${counts.off || 0}${unconfiguredText} · ${mode}`;
    } catch (error) {
      summary.textContent = '状态读取失败';
      toast(error.message, 'error');
    } finally {
      refreshBtn.disabled = false;
      refreshBtn.textContent = '刷新状态';
    }
  }

  async function controlPower(deviceId, action, button) {
    if (!deviceId || busy) return;
    busy = true;
    const allButtons = grid.querySelectorAll('button');
    allButtons.forEach((item) => { item.disabled = true; });
    const originalText = button.textContent;
    button.textContent = action === 'on' ? '上电中...' : '断电中...';
    try {
      const result = await api(`/api/iot/${encodeURIComponent(deviceId)}/${action}`, {
        method: 'POST',
      });
      const hostName = result.device ? result.device.name : '设备';
      if (result.dry_run) {
        toast(result.message || `${hostName} 当前为演练模式，未真正上下电`, 'info');
      } else {
        toast(`${hostName} 已切换为${action === 'on' ? '已上电' : '已断电'}`, 'success');
      }
      await loadDevices();
    } catch (error) {
      button.textContent = originalText;
      toast(error.message, 'error');
      await loadDevices();
    } finally {
      busy = false;
    }
  }

  grid.addEventListener('click', (event) => {
    const button = event.target.closest('[data-action]');
    if (!button || button.disabled) return;
    controlPower(button.dataset.deviceId, button.dataset.action, button);
  });
  refreshBtn.addEventListener('click', loadDevices);
  loadDevices();
})();
