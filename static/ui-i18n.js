(function () {
    let language = 'fra';
    // Provide translated tooltips on the existing settings icons.
    const settingsTitles = {
        '0': ['settings_tab_general', 'Général'],
        '1': ['settings_tab_display', 'Écran'],
        '2': ['settings_tab_capture', 'Capture'],
        '3': ['settings_tab_profile', 'Profil'],
        '5': ['settings_tab_p2p', 'P2P'],
        '6': ['settings_tab_diagnostics', 'Diagnostic'],
        '4': ['settings_tab_exit', 'Quitter']
    };
    document.querySelectorAll('.contente_header_settings .btn_menu_settings[menu]').forEach(function(tab) {
        const entry = settingsTitles[tab.getAttribute('menu')];
        if (!entry) return;
        tab.dataset.i18nTitle = entry[0];
        tab.dataset.i18nTitleFr = entry[1];
        tab.title = entry[1];
        if (tab.hasAttribute('data-i18n-aria')) {
            tab.dataset.i18nAria = entry[0];
            tab.setAttribute('aria-label', entry[1]);
        }
    });
    window.uiT = function(key, french) {
        const pack = window.ELDEN_UI_PACKS && window.ELDEN_UI_PACKS[language];
        return pack && pack.modern && pack.modern[key] ? pack.modern[key] : french;
    };
    window.uiApplyLanguage = function(next) {
        language = next || 'fra';
        const pack = window.ELDEN_UI_PACKS && window.ELDEN_UI_PACKS[language];
        document.documentElement.lang = pack ? pack.html_lang : 'fr';
        document.querySelectorAll('[data-i18n]').forEach(function(node) {
            if (!Object.prototype.hasOwnProperty.call(node.dataset, 'i18nFr')) node.dataset.i18nFr = node.textContent;
            if (node.dataset.i18n === 'invasion') node.dataset.i18nFr = 'Invasions';
            if (node.dataset.i18n === 'arena') node.dataset.i18nFr = 'Arène 1v1';
            node.textContent = window.uiT(node.dataset.i18n, node.dataset.i18nFr);
        });
        document.querySelectorAll('[data-i18n-title]').forEach(function(node) {
            if (!Object.prototype.hasOwnProperty.call(node.dataset, 'i18nTitleFr')) node.dataset.i18nTitleFr = node.title || '';
            node.title = window.uiT(node.dataset.i18nTitle, node.dataset.i18nTitleFr);
        });
        document.querySelectorAll('[data-i18n-placeholder]').forEach(function(node) {
            if (!Object.prototype.hasOwnProperty.call(node.dataset, 'i18nPlaceholderFr')) node.dataset.i18nPlaceholderFr = node.getAttribute('placeholder') || '';
            node.setAttribute('placeholder', window.uiT(node.dataset.i18nPlaceholder, node.dataset.i18nPlaceholderFr));
        });
        document.querySelectorAll('[data-i18n-aria]').forEach(function(node) {
            if (!Object.prototype.hasOwnProperty.call(node.dataset, 'i18nAriaFr')) node.dataset.i18nAriaFr = node.getAttribute('aria-label') || '';
            node.setAttribute('aria-label', window.uiT(node.dataset.i18nAria, node.dataset.i18nAriaFr));
        });
        document.dispatchEvent(new CustomEvent('ui-language-change', {detail:{language:language}}));
    };
    window.uiCurrentLanguage = function() { return language; };
})();
