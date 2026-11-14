(function () {
    const selector = document.getElementById('capture_speed');
    const status = document.getElementById('capture_speed_status');
    if (!selector) return;
    let current = '0';
    function translateIntervals() {
        let formatter;
        try {
            formatter = new Intl.NumberFormat(document.documentElement.lang || 'fr', {style:'unit', unit:'second', unitDisplay:'short'});
        } catch (_) {
            formatter = new Intl.NumberFormat('fr', {style:'unit', unit:'second', unitDisplay:'short'});
        }
        Array.from(selector.options).forEach(function(option) {
            const seconds = Number(option.value);
            if (seconds > 0) option.textContent = formatter.format(seconds);
        });
    }
    document.addEventListener('ui-language-change', translateIntervals);
    translateIntervals();
    function showError() { window.uiSetStatus(status, 'capture_interval_error', 'Impossible d’enregistrer le réglage.'); }
    async function init() {
        try {
            const response = await fetch('/capture-speed', {cache:'no-store'});
            if (!response.ok) throw new Error('request');
            const data = await response.json();
            current = String(data.interval);
            selector.value = current;
            selector.disabled = false;
        } catch (error) { showError(); status.classList.add('error'); }
    }
    selector.addEventListener('change', async function() {
        const next = selector.value;
        selector.disabled = true;
        window.uiSetStatus(status);
        status.classList.remove('error');
        try {
            const response = await fetch('/capture-speed', {method:'POST', body:new URLSearchParams({interval:next})});
            if (!response.ok) throw new Error('request');
            const data = await response.json();
            current = String(data.interval);
            selector.value = current;
        } catch (error) { selector.value = current; showError(); status.classList.add('error'); }
        finally { selector.disabled = false; }
    });
    init();
})();
