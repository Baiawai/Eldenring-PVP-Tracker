(function () {
    const selector = document.getElementById('capture_speed');
    const status = document.getElementById('capture_speed_status');
    if (!selector) return;
    let current = '0';
    function errorText() { return window.uiT ? window.uiT('capture_interval_error', 'Impossible d’enregistrer le réglage.') : 'Impossible d’enregistrer le réglage.'; }
    async function init() {
        try {
            const response = await fetch('/capture-speed', {cache:'no-store'});
            if (!response.ok) throw new Error('request');
            const data = await response.json();
            current = String(data.interval);
            selector.value = current;
            selector.disabled = false;
        } catch (error) { status.textContent = errorText(); status.classList.add('error'); }
    }
    selector.addEventListener('change', async function() {
        const next = selector.value;
        selector.disabled = true;
        status.textContent = '';
        status.classList.remove('error');
        try {
            const response = await fetch('/capture-speed', {method:'POST', body:new URLSearchParams({interval:next})});
            if (!response.ok) throw new Error('request');
            const data = await response.json();
            current = String(data.interval);
            selector.value = current;
        } catch (error) { selector.value = current; status.textContent = errorText(); status.classList.add('error'); }
        finally { selector.disabled = false; }
    });
    init();
})();
