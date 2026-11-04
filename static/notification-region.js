(function() {
    const top = document.getElementById('notification_top');
    const bottom = document.getElementById('notification_bottom');
    const area = document.getElementById('notification_preview_area');
    const preview = document.getElementById('notification_preview');
    const img = document.getElementById('notification_preview_image');
    const empty = document.getElementById('notification_preview_empty');
    const status = document.getElementById('notification_status');
    if (!top || !bottom) return;
    let saved = [40, 100];
    function display() {
        const a = Number(top.value), b = Number(bottom.value);
        document.getElementById('notification_top_value').textContent = a + ' %';
        document.getElementById('notification_bottom_value').textContent = b + ' %';
        area.style.top = a + '%';
        area.style.height = (b - a) + '%';
    }
    function setValues(a, b) { top.value = a; bottom.value = b; display(); }
    function errorText() { return window.uiT ? window.uiT('notification_error', 'Impossible d’enregistrer la zone.') : 'Impossible d’enregistrer la zone.'; }
    window.initNotificationRegion = async function() {
        try {
            const response = await fetch('/notification-region', {cache:'no-store'});
            if (!response.ok) throw new Error('request');
            const data = await response.json();
            saved = [Math.round(data.top * 100), Math.round(data.bottom * 100)];
            setValues(...saved);
            if (data.preview) { img.src = 'data:image/jpeg;base64,' + data.preview; preview.hidden = false; empty.hidden = true; }
            else { preview.hidden = true; empty.hidden = false; }
            status.textContent = '';
        } catch (_) { status.textContent = errorText(); }
    };
    top.addEventListener('input', function() { if (+top.value > +bottom.value - 5) top.value = +bottom.value - 5; display(); });
    bottom.addEventListener('input', function() { if (+bottom.value < +top.value + 5) bottom.value = +top.value + 5; display(); });
    async function save() {
        const selected = [+top.value, +bottom.value];
        top.disabled = bottom.disabled = true;
        try {
            const response = await fetch('/notification-region', {method:'POST', body:new URLSearchParams({top:selected[0]/100,bottom:selected[1]/100})});
            if (!response.ok) throw new Error('request');
            saved = selected; status.textContent = '';
        } catch (_) { setValues(...saved); status.textContent = errorText(); }
        finally { top.disabled = bottom.disabled = false; }
    }
    top.addEventListener('change', save);
    bottom.addEventListener('change', save);
    document.getElementById('notification_reset').addEventListener('click', function() { setValues(40,100); save(); });
})();
