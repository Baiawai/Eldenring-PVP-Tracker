(function () {
    'use strict';
    const section = document.querySelector('.contente_settings[setting="1"]');
    if (!section) return;
    let row = document.getElementById('interface_mode_row');
    if (!row) {
        row = document.createElement('div');
        row.id = 'interface_mode_row'; row.className = 'form_single';
        row.innerHTML = '<label class="form_single_left" for="interface_mode" data-i18n="interface_mode">Mode d’ouverture</label><div class="form_single_right"><select id="interface_mode" disabled><option value="browser" data-i18n="interface_browser">Navigateur</option><option value="window" data-i18n="interface_window">Fenêtre dédiée</option></select><span id="interface_mode_status" role="status" aria-live="polite"></span></div>';
        row.querySelectorAll('[data-i18n]').forEach(node => { if (window.uiT) node.textContent = window.uiT(node.dataset.i18n, node.textContent); });
    }
    section.prepend(row);
    const select = row.querySelector('select'), status = row.querySelector('[role=status]');
    let saved = 'browser';
    fetch('/interface-mode', {cache:'no-store'}).then(response => { if (!response.ok) throw Error(); return response.json(); }).then(data => {
        saved = data.mode; select.value = saved; select.disabled = false;
    }).catch(() => window.uiSetStatus(status, 'interface_mode_error', 'Impossible d’ouvrir cette fenêtre.'));
    select.addEventListener('change', async () => {
        select.disabled = true;
        try {
            const response = await fetch('/interface-mode', {method:'POST', body:new URLSearchParams({mode:select.value})});
            if (!response.ok) throw Error();
            saved = (await response.json()).mode;
            window.uiSetStatus(status);
        } catch (_) { select.value = saved; window.uiSetStatus(status, 'interface_mode_error', 'Impossible d’ouvrir cette fenêtre.'); }
        finally { select.disabled = false; }
    });
})();
