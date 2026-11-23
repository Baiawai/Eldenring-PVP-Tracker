(function () {
    const selector = document.getElementById('game_language');
    const status = document.getElementById('game_language_status');
    if (!selector) return;
    const label = document.getElementById('game_language_label');
    label.dataset.i18n = 'game_language_label';
    label.dataset.i18nFr = 'Langue du jeu';
    let current = '';
    function updateLabel() { label.textContent = window.uiT('game_language_label', 'Langue du jeu'); }
    async function init() {
        updateLabel();
        try {
            const response = await fetch('/game-language', {cache:'no-store'});
            if (!response.ok) throw new Error('request');
            const data = await response.json();
            selector.replaceChildren();
            data.languages.forEach(function(language) {
                const option = document.createElement('option');
                option.value = language.id;
                option.textContent = language.name;
                selector.appendChild(option);
            });
            current = data.language;
            selector.value = current;
            selector.disabled = false;
        } catch (error) {
            status.classList.add('error');
            window.uiSetStatus(status, 'game_language_loading_error', 'Impossible de charger les langues.');
        }
    }
    selector.addEventListener('change', async function() {
        const next = selector.value;
        selector.disabled = true;
        window.uiSetStatus(status);
        status.classList.remove('error');
        try {
            const response = await fetch('/game-language', {method:'POST', body:new URLSearchParams({language:next})});
            const data = await response.json();
            if (!response.ok) {
                if (data.reason === 'combat_active') throw new Error('combat');
                throw new Error('request');
            }
            current = data.language;
            selector.value = current;
        } catch (error) {
            selector.value = current;
            status.classList.add('error');
            if (error.message === 'combat') window.uiSetStatus(status, 'game_language_combat_error', 'Termine la partie en cours avant de changer la langue.');
            else window.uiSetStatus(status, 'game_language_error', 'Impossible de changer la langue.');
        } finally { selector.disabled = false; }
    });
    document.addEventListener('ui-language-change', updateLabel);
    init();

    // Existing server processes can keep the old template in memory. Add the
    // new row to that template as well, without a backend restart.
    let interfaceSelector = document.getElementById('interface_language');
    if (!interfaceSelector) {
        const row = document.createElement('div');
        row.className = 'form_single game-language-setting interface-language-setting';
        const interfaceLabel = document.createElement('label');
        interfaceLabel.className = 'form_single_left';
        interfaceLabel.id = 'interface_language_label';
        interfaceLabel.htmlFor = 'interface_language';
        interfaceLabel.dataset.i18n = 'interface_language_label';
        interfaceLabel.dataset.i18nFr = 'Langue de l’interface';
        interfaceLabel.textContent = window.uiT('interface_language_label', 'Langue de l’interface');
        const control = document.createElement('div');
        control.className = 'form_single_right';
        interfaceSelector = document.createElement('select');
        interfaceSelector.id = 'interface_language';
        interfaceSelector.setAttribute('aria-labelledby', interfaceLabel.id);
        interfaceSelector.disabled = true;
        const message = document.createElement('span');
        message.id = 'interface_language_status';
        message.setAttribute('role', 'status');
        message.setAttribute('aria-live', 'polite');
        control.append(interfaceSelector, message);
        row.append(interfaceLabel, control);
        selector.closest('.form_single').after(row);
        if (window.attachSettingsInfo) {
            const help = document.createElement('p');
            help.dataset.i18n = 'help_interface_language';
            help.dataset.i18nFr = 'Choisit la langue de l’interface indépendamment de celle du jeu.';
            help.textContent = window.uiT(help.dataset.i18n, help.dataset.i18nFr);
            window.attachSettingsInfo(row, [help], 'settings_info_interface_language');
        }
    }
    const interfaceStatus = document.getElementById('interface_language_status');
    let interfaceCurrent = '';
    async function initInterface() {
        try {
            const response = await fetch('/interface-language', {cache:'no-store'});
            if (!response.ok) throw new Error('request');
            const data = await response.json();
            interfaceSelector.replaceChildren();
            data.languages.forEach(function(language) {
                const option = document.createElement('option');
                option.value = language.id;
                option.textContent = language.name;
                interfaceSelector.appendChild(option);
            });
            interfaceCurrent = data.language;
            window.selectedInterfaceLanguage = data.language;
            interfaceSelector.value = data.language;
            interfaceSelector.disabled = false;
            launchLanguages(data.language);
        } catch (_) {
            interfaceStatus.classList.add('error');
            window.uiSetStatus(interfaceStatus, 'interface_language_loading_error', 'Impossible de charger les langues.');
        }
    }
    interfaceSelector.addEventListener('change', async function() {
        const next = interfaceSelector.value;
        interfaceSelector.disabled = true;
        window.uiSetStatus(interfaceStatus);
        interfaceStatus.classList.remove('error');
        try {
            const response = await fetch('/interface-language', {method:'POST', body:new URLSearchParams({language:next})});
            if (!response.ok) throw new Error('request');
            const data = await response.json();
            interfaceCurrent = data.language;
            window.selectedInterfaceLanguage = data.language;
            interfaceSelector.value = data.language;
            launchLanguages(data.language);
            if (typeof launchChart === 'function' && typeof mode_chart !== 'undefined') launchChart(mode_chart, 1);
        } catch (_) {
            interfaceSelector.value = interfaceCurrent;
            interfaceStatus.classList.add('error');
            window.uiSetStatus(interfaceStatus, 'interface_language_error', 'Impossible de changer la langue.');
        } finally { interfaceSelector.disabled = false; }
    });
    initInterface();
})();
