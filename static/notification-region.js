(function () {
    'use strict';
    const top = document.getElementById('notification_top');
    const bottom = document.getElementById('notification_bottom');
    const area = document.getElementById('notification_preview_area');
    const preview = document.getElementById('notification_preview');
    const img = document.getElementById('notification_preview_image');
    const empty = document.getElementById('notification_preview_empty');
    const status = document.getElementById('notification_status');
    const testButton = document.getElementById('notification_ocr_test');
    const testStatus = document.getElementById('notification_ocr_status');
    const testResult = document.getElementById('notification_ocr_result');
    const section = document.querySelector('.contente_settings[setting="2"]');
    const manual = document.getElementById('notification_manual');
    const controls = document.getElementById('notification_manual_controls');
    const reset = document.getElementById('notification_reset');
    const manualIntro = document.getElementById('notification_manual_intro');
    const autoIntro = document.getElementById('notification_auto_intro');
    if (!top || !bottom || !section) return;

    // Refresh the French fallback even when the running server cached an older template.
    autoIntro.dataset.i18nFr = 'Lorsque cette option est activée, le tracker repère le bandeau à partir des messages du jeu reconnus et ajuste la zone pour les notifications d’une ou deux lignes. Si sa position est incertaine, toute l’image est analysée. Choisis Non pour régler toi-même les limites supérieure et inférieure.';
    autoIntro.textContent = window.uiT ? window.uiT('notification_auto_intro', autoIntro.dataset.i18nFr) : autoIntro.dataset.i18nFr;

    // Update a page already served by the running tracker without resetting its session.
    const region = section.querySelector('.notification-region-settings');
    const heading = region.querySelector('.notification-region-title');
    const sample = region.querySelector('.notification-sample');
    const manualRow = manual.closest('.form_single');
    // Older cached pages used the inverse wording; only invert presentation,
    // keeping the stored manual preference and API unchanged.
    const modeLabel = manualRow.querySelector('.form_single_left label') || manualRow.querySelector('.form_single_left');
    modeLabel.dataset.i18n = 'notification_automatic';
    modeLabel.dataset.i18nFr = 'Détection automatique de la zone';
    modeLabel.textContent = window.uiT ? window.uiT('notification_automatic', modeLabel.dataset.i18nFr) : modeLabel.dataset.i18nFr;
    manual.checked = true;
    manual.dispatchEvent(new Event('tracker-setting-render'));
    let purpose = region.querySelector('.notification-purpose');
    if (!purpose) {
        purpose = document.createElement('p');
        purpose.className = 'notification-purpose';
        purpose.dataset.i18n = 'notification_purpose';
        purpose.dataset.i18nFr = 'Cette zone est essentielle au suivi : l’application lit les notifications à l’écran pour repérer les débuts de combat, les victoires et les noms des adversaires, sans modifier les fichiers du jeu.';
        purpose.textContent = window.uiT ? window.uiT('notification_purpose', purpose.dataset.i18nFr) : purpose.dataset.i18nFr;
        heading.after(purpose);
    }
    // Keep the preview, mode choice and manual sliders adjacent, including on
    // a page served from the previous cached template.
    const oldLockSettings = document.getElementById('notification_lock_settings');
    if (oldLockSettings) oldLockSettings.remove();
    const actions = testButton.closest('.notification-actions');
    const resetActions = reset.closest('.notification-actions');
    if (actions !== resetActions) { actions.prepend(reset); resetActions.remove(); }
    purpose.after(sample); sample.after(manualRow); manualRow.after(manualIntro);
    manualIntro.after(autoIntro); autoIntro.after(controls); controls.after(status); status.after(actions); actions.after(testStatus); testStatus.after(testResult);
    if (window.initSettingsYesNo) window.initSettingsYesNo(document);
    const attachInfo = window.attachSettingsInfo;
    attachInfo(manualRow, [manualIntro, autoIntro], 'notification_mode_info');
    const retentionHelp = section.querySelector('[data-i18n="retention_captures_help"]');
    if (retentionHelp) attachInfo(retentionHelp.closest('.form_single'), [retentionHelp], 'notification_retention_info');
    let saved = [40, 100], previewId = null, testing = false, loading = false, editing = false, modeUpdating = false, modeEpoch = 0;
    function display() {
        const a = Number(top.value), b = Number(bottom.value);
        document.getElementById('notification_top_value').textContent = a + ' %';
        document.getElementById('notification_bottom_value').textContent = b + ' %';
        area.style.top = a + '%'; area.style.height = (b - a) + '%';
    }
    function setValues(a, b) { top.value = a; bottom.value = b; display(); }
    function clearResult() { testResult.hidden = true; window.uiSetStatus(testStatus); }
    function showSample(data) {
        const nextId = data.preview && data.preview_id != null ? data.preview_id : null;
        if (nextId !== previewId) {
            previewId = nextId; clearResult();
            if (nextId !== null) img.src = 'data:image/jpeg;base64,' + data.preview;
            else img.removeAttribute('src');
        }
        preview.hidden = nextId === null; empty.hidden = nextId !== null;
        testButton.disabled = nextId === null || testing || editing;
    }
    function renderMode(data, initial) {
        const isManual = data.manual === true;
        manual.checked = !isManual;
        manual.disabled = false;
        manual.dispatchEvent(new Event('tracker-setting-render'));
        controls.hidden = !isManual; reset.hidden = !isManual;
        manualIntro.hidden = !isManual;
        autoIntro.hidden = false;
        if (initial || (!isManual && !editing)) {
            const bounds = [Math.round(data.top * 100), Math.round(data.bottom * 100)];
            if (isManual) saved = bounds;
            setValues(...bounds);
        }
    }
    manual.addEventListener('change', async function () {
        const selected = manual.checked;
        modeEpoch++;
        modeUpdating = true; manual.disabled = true; testButton.disabled = true;
        manual.dispatchEvent(new Event('tracker-setting-render'));
        try {
            const response = await fetch('/notification-region', {method:'POST', body:new URLSearchParams({manual:String(!selected)})});
            if (!response.ok) throw new Error('request');
            const data = await response.json();
            renderMode(data, true); showSample(data); clearResult(); window.uiSetStatus(status);
        } catch (_) {
            manual.checked = !selected; manual.disabled = false;
            manual.dispatchEvent(new Event('tracker-setting-render'));
            window.uiSetStatus(status, 'notification_error', 'Impossible d’enregistrer la zone.');
        } finally { modeUpdating = false; testButton.disabled = previewId === null || testing || editing; }
    });
    async function fetchSettings(initial) {
        if (loading || modeUpdating) return;
        loading = true;
        const epoch = modeEpoch;
        try {
            const response = await fetch('/notification-region', {cache:'no-store'});
            if (!response.ok) throw new Error('request');
            const data = await response.json();
            if (epoch !== modeEpoch) return;
            renderMode(data, initial);
            showSample(data); window.uiSetStatus(status);
        } catch (_) { window.uiSetStatus(status, 'notification_error', 'Impossible d’enregistrer la zone.'); }
        finally { loading = false; }
    }
    window.initNotificationRegion = function () { return fetchSettings(true); };
    setInterval(function () {
        const panel = document.querySelector('.settings-panel');
        if (!section.classList.contains('hide') && panel && getComputedStyle(panel).display !== 'none') fetchSettings(false);
    }, 3000);
    top.addEventListener('input', function () { if (+top.value > +bottom.value - 5) top.value = +bottom.value - 5; display(); clearResult(); editing = true; testButton.disabled = true; });
    bottom.addEventListener('input', function () { if (+bottom.value < +top.value + 5) bottom.value = +top.value + 5; display(); clearResult(); editing = true; testButton.disabled = true; });
    async function save() {
        const selected = [+top.value, +bottom.value];
        editing = true; testButton.disabled = true;
        top.disabled = bottom.disabled = true;
        try {
            const response = await fetch('/notification-region', {method:'POST', body:new URLSearchParams({top:selected[0]/100,bottom:selected[1]/100})});
            if (!response.ok) throw new Error('request');
            saved = selected; window.uiSetStatus(status); clearResult();
        } catch (_) { setValues(...saved); window.uiSetStatus(status, 'notification_error', 'Impossible d’enregistrer la zone.'); }
        finally { editing = false; top.disabled = bottom.disabled = false; testButton.disabled = previewId === null || testing; }
    }
    top.addEventListener('change', save); bottom.addEventListener('change', save);
    reset.addEventListener('click', function () { setValues(40,100); save(); });
    testButton.addEventListener('click', async function () {
        if (previewId === null) return;
        const testedId = previewId, testedEpoch = modeEpoch;
        testing = true; testButton.disabled = true; testResult.hidden = true;
        window.uiSetStatus(testStatus, 'notification_ocr_testing', 'Analyse en cours…');
        try {
            const response = await fetch('/notification-ocr-test', {method:'POST', body:new URLSearchParams({preview_id:String(testedId)})});
            const data = await response.json();
            if (!response.ok) {
                if (data.reason === 'preview_changed' || data.reason === 'no_preview') {
                    await fetchSettings(false);
                    window.uiSetStatus(testStatus, 'notification_ocr_changed', 'Un nouvel exemple est disponible. Lance à nouveau le test.');
                    return;
                }
                throw new Error('ocr');
            }
            if (testedId !== previewId || testedEpoch !== modeEpoch) return;
            if (data.matched) window.uiSetStatus(testStatus, 'notification_ocr_matched', 'Message reconnu comme événement de suivi.');
            else window.uiSetStatus(testStatus, 'notification_ocr_unmatched', 'Aucun événement reconnu dans la zone sélectionnée.');
            if (data.text.trim()) { testResult.textContent = data.text; testResult.hidden = false; }
        } catch (_) { window.uiSetStatus(testStatus, 'notification_ocr_error', 'Impossible de tester la reconnaissance.'); }
        finally { testing = false; testButton.disabled = previewId === null || editing; }
    });
})();
