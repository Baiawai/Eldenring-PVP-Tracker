(function () {
    let language = 'fra';
    const settingsPanel = document.querySelector('.settings-panel');
    // Upgrade the markup served by an already-running tracker with a cached template.
    const oldHeading = settingsPanel && settingsPanel.querySelector('.settings-page-heading');
    if (oldHeading) {
        oldHeading.classList.replace('settings-page-heading', 'page-heading');
        const oldIcon = oldHeading.querySelector('.settings-page-heading-icon');
        if (oldIcon) oldIcon.classList.replace('settings-page-heading-icon', 'page-heading-icon');
    }
    if (settingsPanel && !settingsPanel.querySelector('.page-heading')) {
        // Support a template cached by the running tracker after a page refresh.
        const heading = document.createElement('header');
        heading.className = 'page-heading';
        const frame = document.createElement('span');
        frame.className = 'page-heading-icon';
        const icon = document.createElement('img');
        icon.src = '/static/icon-settings-bronze.png'; icon.alt = '';
        const title = document.createElement('h1'); title.textContent = 'Configuration';
        frame.appendChild(icon); heading.append(frame, title); settingsPanel.prepend(heading);
    }
    const settingsHeadingIcon = settingsPanel && settingsPanel.querySelector('.page-heading-icon img');
    if (settingsHeadingIcon) settingsHeadingIcon.src = '/static/icon-settings-bronze.png';
    const headingPages = [
        ['.cadre_multi', 'menu_button_multi', 'ranking', 'Classement'],
        ['#stats_panel', 'menu_button_info', 'statistics', 'Statistiques'],
        ['#players_panel', 'menu_button_players', 'players', 'Joueurs'],
        ['#history_panel', 'menu_button_history', 'history', 'Historique'],
        ['#information_panel', 'menu_button_information', 'information', 'Informations']
    ];
    headingPages.forEach(function (entry) {
        const panel = document.querySelector(entry[0]);
        if (!panel || panel.querySelector(':scope > .page-heading')) return;
        const heading = document.createElement('header');
        heading.className = 'page-heading';
        const frame = document.createElement('span');
        frame.className = 'page-heading-icon';
        const icon = document.createElement('img');
        icon.src = '/static/page-icon-' + entry[2] + '.png'; icon.alt = '';
        const title = document.createElement('span');
        title.className = 'page-heading-title';
        const menu = entry[1] && document.getElementById(entry[1]);
        const updateTitle = () => { title.textContent = menu && menu.textContent.trim() || entry[3]; };
        if (menu) new MutationObserver(updateTitle).observe(menu, {childList:true, subtree:true, characterData:true});
        updateTitle();
        frame.appendChild(icon); heading.append(frame, title); panel.prepend(heading);
    });
    document.querySelectorAll('.page-heading').forEach(function(pageHeading) {
        const panel = pageHeading.parentElement;
        let sparks = pageHeading.querySelector('.page-heading-sparks');
        if (!sparks) {
            sparks = document.createElement('span');
            sparks.className = 'page-heading-sparks';
            sparks.setAttribute('aria-hidden', 'true');
            pageHeading.prepend(sparks);
        }
        function regenerateHeadingSparks() {
            const fragment = document.createDocumentFragment();
            for (let index = 0; index < 130; index++) {
                const spark = document.createElement('i');
                const x = Math.pow(Math.random(), 1.25) * 96;
                const y = 50 + (Math.random() + Math.random() + Math.random() - 1.5) * 18;
                const size = .5 + Math.random() * 1.3;
                spark.style.left = x + '%'; spark.style.top = y + '%';
                spark.style.width = size + 'px'; spark.style.height = size + 'px';
                spark.style.opacity = .18 + Math.random() * .48;
                fragment.appendChild(spark);
            }
            sparks.replaceChildren(fragment);
        }
        let wasVisible = getComputedStyle(panel).display !== 'none' && !panel.hidden;
        if (wasVisible) regenerateHeadingSparks();
        new MutationObserver(function () {
            const visible = getComputedStyle(panel).display !== 'none' && !panel.hidden;
            if (visible && !wasVisible) regenerateHeadingSparks();
            wasVisible = visible;
        }).observe(panel, {attributes:true, attributeFilter:['style', 'class', 'hidden']});
    });
    // Provide translated tooltips on the existing settings icons.
    const settingsTitles = {
        '0': ['settings_tab_general', 'Général'],
        '1': ['settings_tab_display', 'Graphismes'],
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
    function updateSettingsPageHeading() {
        const title = settingsPanel && settingsPanel.querySelector('.page-heading h1');
        const menu = document.getElementById('menu_button_settings');
        if (title && menu && menu.textContent.trim()) title.textContent = menu.textContent.trim();
    }
    document.addEventListener('ui-language-change', updateSettingsPageHeading);
    const settingsNav = document.querySelector('.contente_header_settings');
    const settingsTitle = settingsNav && settingsNav.querySelector('.settings-section-title');
    function updateSettingsTitle() {
        if (!settingsTitle) return;
        const active = settingsNav.querySelector('.btn_menu_settings.active_setting');
        const entry = active && settingsTitles[active.getAttribute('menu')];
        if (entry) settingsTitle.textContent = window.uiT(entry[0], entry[1]);
    }
    if (settingsNav && settingsTitle) {
        new MutationObserver(updateSettingsTitle).observe(settingsNav, {subtree:true, attributes:true, attributeFilter:['class']});
        document.addEventListener('ui-language-change', updateSettingsTitle);
        updateSettingsTitle();
    }
})();
