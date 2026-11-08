(function () {
    'use strict';
    const setting = document.getElementById('auto_game_start');
    const status = document.getElementById('auto_game_start_status');
    if (!setting || !status) return;
    const tr = (key, fallback) => window.uiT ? window.uiT(key, fallback) : fallback;
    fetch('/auto-game-start', {cache:'no-store'}).then(response => {
        if (!response.ok) throw new Error('request');
        return response.json();
    }).then(data => { setting.checked = data.enabled; setting.disabled = false; setting.dispatchEvent(new Event('tracker-setting-render')); })
      .catch(() => { status.textContent = tr('auto_game_start_error', 'Impossible de charger ce réglage.'); });
    setting.addEventListener('change', async function () {
        const requested = setting.checked;
        setting.disabled = true;
        try {
            const response = await fetch('/auto-game-start', {method:'POST', body:new URLSearchParams({enabled:String(requested)})});
            if (!response.ok) throw new Error('request');
            setting.checked = (await response.json()).enabled;
            status.textContent = '';
        } catch (_) { setting.checked = !requested; status.textContent = tr('auto_game_start_error', 'Impossible d’enregistrer ce réglage.'); }
        finally { setting.disabled = false; setting.dispatchEvent(new Event('tracker-setting-render')); }
    });
})();
