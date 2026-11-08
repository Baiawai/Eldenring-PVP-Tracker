(function () {
    'use strict';
    const fields = {
        monitor_error:document.getElementById('notify_monitor_error'),
        game_hidden:document.getElementById('notify_game_hidden'),
        monitor_stop:document.getElementById('notify_monitor_stop')
    };
    const status = document.getElementById('tracking_notifications_status');
    if (!status || Object.values(fields).some(node => !node)) return;
    const tr = (key, fallback) => window.uiT ? window.uiT(key, fallback) : fallback;
    function busy(value) { Object.values(fields).forEach(node => { node.disabled = value; node.dispatchEvent(new Event('tracker-setting-render')); }); }
    function apply(settings) { Object.entries(fields).forEach(([kind, node]) => { node.checked = settings[kind] === true; node.dispatchEvent(new Event('tracker-setting-render')); }); }
    Object.entries(fields).forEach(([kind, node]) => {
        node.addEventListener('change', async function () {
            const requested = node.checked;
            busy(true);
            try {
                const response = await fetch('/tracking-notifications', {method:'POST', body:new URLSearchParams({kind, enabled:String(requested)})});
                if (!response.ok) throw new Error('request');
                apply((await response.json()).settings);
                status.textContent = '';
            } catch (_) { node.checked = !requested; status.textContent = tr('notification_settings_error', 'Impossible de modifier les notifications.'); }
            finally { busy(false); }
        });
    });
    fetch('/tracking-notifications', {cache:'no-store'}).then(response => {
        if (!response.ok) throw new Error('request');
        return response.json();
    }).then(data => { apply(data.settings); busy(false); })
      .catch(() => { status.textContent = tr('notification_settings_error', 'Impossible de modifier les notifications.'); });
})();
