(function () {
    'use strict';
    const fields = {
        captures:{select:document.getElementById('retention_captures'), status:document.getElementById('retention_captures_status')},
        steam:{select:document.getElementById('retention_steam'), status:document.getElementById('retention_steam_status')}
    };
    if (Object.values(fields).some(field => !field.select || !field.status)) return;
    const tr = (key, fallback) => window.uiT ? window.uiT(key, fallback) : fallback;
    let saved = {captures:0, steam:0};
    const busy = value => Object.values(fields).forEach(field => { field.select.disabled = value; });
    function render() { Object.entries(fields).forEach(([kind, field]) => { field.select.value = String(saved[kind]); }); }
    function translateDurations() {
        let formatter;
        try { formatter = new Intl.NumberFormat(document.documentElement.lang || 'fr', {style:'unit', unit:'day', unitDisplay:'long'}); }
        catch (_) { formatter = new Intl.NumberFormat('fr', {style:'unit', unit:'day', unitDisplay:'long'}); }
        Object.values(fields).forEach(field => {
            Array.from(field.select.options).filter(option => Number(option.value) > 0).forEach(option => { option.textContent = formatter.format(Number(option.value)); });
        });
    }
    document.addEventListener('ui-language-change', translateDurations);
    translateDurations();
    Object.entries(fields).forEach(([kind, field]) => {
        field.select.addEventListener('change', async function () {
            const days = Number(field.select.value);
            if (days && !window.confirm(tr('retention_confirm', 'Les données plus anciennes seront supprimées au prochain démarrage. Continuer ?'))) { render(); return; }
            busy(true);
            try {
                const response = await fetch('/retention-settings', {method:'POST', body:new URLSearchParams({kind, days:String(days)})});
                const data = await response.json();
                if (!response.ok) {
                    if (data.reason === 'monitor_active') { field.status.textContent = tr('retention_stop', 'Arrêtez le suivi avant de modifier la conservation.'); render(); return; }
                    throw new Error('request');
                }
                saved = data.settings; render();
                field.status.textContent = tr('retention_saved', 'Réglage enregistré.');
            } catch (_) { render(); field.status.textContent = tr('retention_error', 'Impossible de modifier la conservation.'); }
            finally { busy(false); }
        });
    });
    busy(true);
    fetch('/retention-settings', {cache:'no-store'}).then(response => {
        if (!response.ok) throw new Error('request');
        return response.json();
    }).then(data => { saved = data.settings; render(); busy(false); })
      .catch(() => { Object.values(fields).forEach(field => { field.status.textContent = tr('retention_error', 'Impossible de modifier la conservation.'); }); });
})();
