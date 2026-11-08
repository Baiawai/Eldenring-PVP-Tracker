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
    let lockSettings = document.getElementById('notification_lock_settings');
    if (!lockSettings) {
        lockSettings = document.createElement('div');
        lockSettings.id = 'notification_lock_settings';
        lockSettings.hidden = true;
        lockSettings.innerHTML = '<div class="form_single"><label class="form_single_left" for="notification_lock" data-i18n="notification_lock">Verrouiller la zone détectée</label><div class="form_single_right"><input type="checkbox" id="notification_lock" disabled></div></div>' +
            '<p id="notification_lock_help" class="notification-region-intro" data-i18n="notification_lock_help">Lorsque l’aperçu montre la bonne zone de notification, verrouille ses limites pour éviter qu’une détection incorrecte les modifie. Déverrouille-la pour reprendre la détection automatique, notamment si l’affichage du jeu ou la position des notifications change.</p>' +
            '<p id="notification_lock_active" class="notification-region-intro" data-i18n="notification_lock_active" hidden>La zone est verrouillée : ses limites restent fixes jusqu’au déverrouillage.</p>' +
            '<p id="notification_lock_unavailable" class="notification-region-intro" data-i18n="notification_lock_unavailable" hidden>Attends qu’une zone soit détectée sur l’aperçu avant de la verrouiller.</p>';
    }
    lockSettings.querySelectorAll('[data-i18n]').forEach(function (node) {
        if (!node.dataset.i18nFr) node.dataset.i18nFr = node.textContent;
        if (window.uiT) node.textContent = window.uiT(node.dataset.i18n, node.dataset.i18nFr);
    });
    const actions = testButton.closest('.notification-actions');
    const resetActions = reset.closest('.notification-actions');
    if (actions !== resetActions) { actions.prepend(reset); resetActions.remove(); }
    purpose.after(sample); sample.after(manualRow); manualRow.after(manualIntro);
    manualIntro.after(autoIntro); autoIntro.after(controls); controls.after(lockSettings);
    lockSettings.after(status); status.after(actions); actions.after(testStatus); testStatus.after(testResult);
    if (window.initSettingsYesNo) window.initSettingsYesNo(document);
    const lock = document.getElementById('notification_lock');
    const lockUnavailable = document.getElementById('notification_lock_unavailable');
    const lockHelp = document.getElementById('notification_lock_help');
    const lockActive = document.getElementById('notification_lock_active');
    lockHelp.dataset.i18nFr = 'Lorsque l’aperçu montre la bonne zone de notification, verrouille ses limites pour éviter qu’une détection incorrecte les modifie. Déverrouille-la pour reprendre la détection automatique, notamment si l’affichage du jeu ou la position des notifications change.';
    lockHelp.textContent = window.uiT ? window.uiT('notification_lock_help', lockHelp.dataset.i18nFr) : lockHelp.dataset.i18nFr;
    const attachInfo = window.attachSettingsInfo;
    let autoLockedIntro = document.getElementById('notification_auto_locked_intro');
    if (!autoLockedIntro) {
        autoLockedIntro = document.createElement('p');
        autoLockedIntro.id = 'notification_auto_locked_intro';
        autoLockedIntro.className = 'notification-region-intro';
        autoLockedIntro.dataset.i18n = 'notification_auto_locked_intro';
        autoLockedIntro.dataset.i18nFr = 'La détection automatique est active. La zone reste fixe tant que son verrouillage est activé.';
        autoLockedIntro.textContent = window.uiT ? window.uiT('notification_auto_locked_intro', autoLockedIntro.dataset.i18nFr) : autoLockedIntro.dataset.i18nFr;
        autoLockedIntro.hidden = true;
    }
    attachInfo(manualRow, [manualIntro, autoIntro, autoLockedIntro], 'notification_mode_info');
    attachInfo(lock.closest('.form_single'), [lockHelp, lockActive, lockUnavailable], 'notification_lock_info');
    const retentionHelp = section.querySelector('[data-i18n="retention_captures_help"]');
    if (retentionHelp) attachInfo(retentionHelp.closest('.form_single'), [retentionHelp], 'notification_retention_info');
    const tr = (key, fallback) => window.uiT ? window.uiT(key, fallback) : fallback;
    let saved = [40, 100], previewId = null, testing = false, loading = false, editing = false, modeUpdating = false, modeEpoch = 0;
    function display() {
        const a = Number(top.value), b = Number(bottom.value);
        document.getElementById('notification_top_value').textContent = a + ' %';
        document.getElementById('notification_bottom_value').textContent = b + ' %';
        area.style.top = a + '%'; area.style.height = (b - a) + '%';
    }
    function setValues(a, b) { top.value = a; bottom.value = b; display(); }
    function clearResult() { testResult.hidden = true; testStatus.textContent = ''; }
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
        autoLockedIntro.hidden = isManual || data.locked !== true;
        const supportsLock = typeof data.locked === 'boolean';
        lockSettings.hidden = isManual || !supportsLock;
        lock.checked = data.locked === true;
        lock.disabled = isManual || !supportsLock || !(data.locked || data.can_lock);
        lockUnavailable.hidden = !!(data.locked || data.can_lock);
        lockHelp.hidden = false;
        lockActive.hidden = data.locked !== true;
        lock.dispatchEvent(new Event('tracker-setting-render'));
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
            renderMode(data, true); showSample(data); clearResult(); status.textContent = '';
        } catch (_) {
            manual.checked = !selected; manual.disabled = false;
            manual.dispatchEvent(new Event('tracker-setting-render'));
            status.textContent = tr('notification_error', 'Impossible d’enregistrer la zone.');
        } finally { modeUpdating = false; testButton.disabled = previewId === null || testing || editing; }
    });
    lock.addEventListener('change', async function () {
        const selected = lock.checked;
        modeEpoch++;
        modeUpdating = true; lock.disabled = manual.disabled = true; testButton.disabled = true;
        lock.dispatchEvent(new Event('tracker-setting-render'));
        manual.dispatchEvent(new Event('tracker-setting-render'));
        try {
            const body = new URLSearchParams({locked:String(selected), preview_id:String(previewId ?? '')});
            const response = await fetch('/notification-region', {method:'POST', body});
            const data = await response.json();
            if (!response.ok) {
                if (data.reason === 'preview_changed') throw new Error('preview_changed');
                throw new Error('lock');
            }
            renderMode(data, true); showSample(data); clearResult(); status.textContent = '';
        } catch (error) {
            lock.checked = !selected; lock.disabled = manual.disabled = false;
            lock.dispatchEvent(new Event('tracker-setting-render'));
            manual.dispatchEvent(new Event('tracker-setting-render'));
            status.textContent = error.message === 'preview_changed' ?
                tr('notification_lock_changed', 'Un nouvel exemple est disponible. Vérifie-le avant de verrouiller.') :
                tr('notification_error', 'Impossible d’enregistrer la zone.');
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
            showSample(data); status.textContent = '';
        } catch (_) { status.textContent = tr('notification_error', 'Impossible d’enregistrer la zone.'); }
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
            saved = selected; status.textContent = ''; clearResult();
        } catch (_) { setValues(...saved); status.textContent = tr('notification_error', 'Impossible d’enregistrer la zone.'); }
        finally { editing = false; top.disabled = bottom.disabled = false; testButton.disabled = previewId === null || testing; }
    }
    top.addEventListener('change', save); bottom.addEventListener('change', save);
    reset.addEventListener('click', function () { setValues(40,100); save(); });
    testButton.addEventListener('click', async function () {
        if (previewId === null) return;
        const testedId = previewId, testedEpoch = modeEpoch;
        testing = true; testButton.disabled = true; testResult.hidden = true;
        testStatus.textContent = tr('notification_ocr_testing', 'Analyse en cours…');
        try {
            const response = await fetch('/notification-ocr-test', {method:'POST', body:new URLSearchParams({preview_id:String(testedId)})});
            const data = await response.json();
            if (!response.ok) {
                if (data.reason === 'preview_changed' || data.reason === 'no_preview') {
                    await fetchSettings(false);
                    testStatus.textContent = tr('notification_ocr_changed', 'Un nouvel exemple est disponible. Lance à nouveau le test.');
                    return;
                }
                throw new Error('ocr');
            }
            if (testedId !== previewId || testedEpoch !== modeEpoch) return;
            testStatus.textContent = data.matched ? tr('notification_ocr_matched', 'Message reconnu comme événement de suivi.') :
                tr('notification_ocr_unmatched', 'Aucun événement reconnu dans la zone sélectionnée.');
            if (data.text.trim()) { testResult.textContent = data.text; testResult.hidden = false; }
        } catch (_) { testStatus.textContent = tr('notification_ocr_error', 'Impossible de tester la reconnaissance.'); }
        finally { testing = false; testButton.disabled = previewId === null || editing; }
    });
})();
