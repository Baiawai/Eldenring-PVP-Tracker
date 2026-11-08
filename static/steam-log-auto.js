(function () {
    'use strict';
    const input = document.getElementById('steam_log_auto');
    const status = document.getElementById('steam_log_auto_status');
    if (!input || !status) return;
    let saved = false;
    const render = () => input.dispatchEvent(new Event('tracker-setting-render'));
    const error = () => { status.textContent = window.uiT ? window.uiT('auto_game_start_error', 'Impossible d’enregistrer ce réglage.') : 'Impossible d’enregistrer ce réglage.'; };
    input.addEventListener('change', async () => {
        const desired = input.checked;
        input.disabled = true; render(); status.textContent = '';
        try {
            const response = await fetch('/steam-log-auto', {method:'POST', body:new URLSearchParams({enabled:String(desired)})});
            if (!response.ok) throw new Error('save');
            const data = await response.json();
            if (typeof data.enabled !== 'boolean') throw new Error('response');
            saved = data.enabled; input.checked = saved;
        } catch (_) { input.checked = saved; error(); }
        finally { input.disabled = false; render(); }
    });
    fetch('/steam-log-auto', {cache:'no-store'}).then(response => {
        if (!response.ok) throw new Error('load');
        return response.json();
    }).then(data => {
        if (typeof data.enabled !== 'boolean') throw new Error('response');
        saved = data.enabled; input.checked = saved; input.disabled = false; render();
    }).catch(() => { error(); render(); });
})();
