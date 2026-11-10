(function () {
    'use strict';
    function words() {
        const language = window.uiCurrentLanguage ? window.uiCurrentLanguage() : 'fra';
        const pack = window.ELDEN_UI_PACKS && window.ELDEN_UI_PACKS[language];
        return pack && pack.legacy ? [pack.legacy[44], pack.legacy[45]] : ['Non', 'Oui'];
    }
    function init(root) {
      root.querySelectorAll('.settings-panel input[type="checkbox"]').forEach(function (input) {
        if (input.dataset.yesNoReady === '1') return;
        const label = input.labels && input.labels[0];
        if (!label || !input.id) return;
        input.dataset.yesNoReady = '1';
        if (label.contains(input)) label.after(input);
        label.removeAttribute('for');
        if (!label.id) label.id = input.id + '_label';
        input.hidden = true;
        input.setAttribute('aria-hidden', 'true');
        input.tabIndex = -1;
        const group = document.createElement('div');
        group.className = 'yes-no-control';
        group.setAttribute('role', 'group');
        group.setAttribute('aria-labelledby', label.id);
        const no = document.createElement('button');
        const value = document.createElement('span');
        const yes = document.createElement('button');
        no.type = yes.type = 'button';
        no.textContent = '<'; yes.textContent = '>';
        value.setAttribute('aria-live', 'polite');
        group.append(no, value, yes);
        input.after(group);
        function render() {
            const [negative, positive] = words();
            value.textContent = input.checked ? positive : negative;
            const next = input.checked ? negative : positive;
            no.setAttribute('aria-label', label.textContent.trim() + ' : ' + next);
            yes.setAttribute('aria-label', label.textContent.trim() + ' : ' + next);
            no.disabled = yes.disabled = input.disabled;
        }
        function toggle() {
            if (input.disabled) return;
            input.checked = !input.checked;
            input.dispatchEvent(new Event('change', {bubbles:true}));
            render();
        }
        no.addEventListener('click', toggle);
        yes.addEventListener('click', toggle);
        input.addEventListener('change', render);
        input.addEventListener('tracker-setting-render', render);
        document.addEventListener('ui-language-change', render);
        new MutationObserver(render).observe(input, {attributes:true, attributeFilter:['disabled']});
        render();
      });
    }
    window.initSettingsYesNo = init;
    init(document);

    function repositionVisibleInfo() {
        document.querySelectorAll('.settings-panel .settings-info:is(:hover, :focus-within)').forEach(info => {
            if (info.placeTooltip) info.placeTooltip();
        });
    }
    document.addEventListener('scroll', repositionVisibleInfo, {capture:true, passive:true});
    window.addEventListener('resize', repositionVisibleInfo, {passive:true});

    function attachInfo(row, paragraphs, tooltipId) {
        if (!row) return;
        const section = row.closest('.contente_settings');
        if (!section) return;
        const existing = row.querySelector('.settings-info-tooltip');
        if (existing) {
            paragraphs.filter(Boolean).forEach(paragraph => existing.appendChild(paragraph));
            row.appendChild(existing.closest('.settings-info'));
            return;
        }
        if (!row.querySelector(':scope > .form_single_left') && !row.matches('.stat-detail-row, .environment-row, .form_btn')) return;
        const wrapper = document.createElement('div');
        wrapper.className = 'settings-info';
        const trigger = document.createElement('button');
        trigger.type = 'button'; trigger.className = 'settings-info-trigger'; trigger.textContent = 'i';
        trigger.dataset.i18nAria = 'information_title'; trigger.dataset.i18nAriaFr = 'Informations';
        trigger.setAttribute('aria-label', window.uiT ? window.uiT('information_title', 'Informations') : 'Informations');
        trigger.setAttribute('aria-describedby', tooltipId);
        const tooltip = document.createElement('div');
        tooltip.className = 'settings-info-tooltip'; tooltip.id = tooltipId; tooltip.setAttribute('role', 'tooltip');
        paragraphs.filter(Boolean).forEach(paragraph => tooltip.appendChild(paragraph));
        wrapper.append(trigger, tooltip); row.appendChild(wrapper);
        function placeTooltip() {
            const icon = trigger.getBoundingClientRect();
            const area = section.getBoundingClientRect();
            const box = tooltip.getBoundingClientRect();
            const margin = 8;
            const leftBound = Math.max(margin, area.left + margin);
            const rightBound = Math.min(window.innerWidth - margin, area.right - margin);
            const topBound = Math.max(margin, area.top + margin);
            const bottomBound = Math.min(window.innerHeight - margin, area.bottom - margin);
            const left = Math.max(leftBound, Math.min(icon.right - box.width, rightBound - box.width));
            const above = icon.top - box.height - margin;
            const below = icon.bottom + margin;
            let top = above >= topBound ? above : below;
            if (top + box.height > bottomBound) top = Math.max(topBound, bottomBound - box.height);
            // The application's display scale uses CSS zoom on the root element.
            const zoom = parseFloat(getComputedStyle(document.documentElement).zoom) || 1;
            tooltip.style.left = left / zoom + 'px';
            tooltip.style.top = top / zoom + 'px';
        }
        wrapper.placeTooltip = placeTooltip;
        wrapper.addEventListener('mouseenter', placeTooltip);
        trigger.addEventListener('focus', placeTooltip);
        new MutationObserver(() => {
            if (wrapper.matches(':hover, :focus-within')) placeTooltip();
        }).observe(tooltip, {subtree:true, childList:true, attributes:true, attributeFilter:['hidden']});
    }
    window.attachSettingsInfo = attachInfo;

    function helpText(key, fallback) {
        const p = document.createElement('p');
        p.dataset.i18n = key; p.dataset.i18nFr = fallback;
        p.textContent = window.uiT ? window.uiT(key, fallback) : fallback;
        return p;
    }
    function fieldInfo(selector, key, fallback, extras) {
        const control = document.querySelector('.settings-panel ' + selector);
        const row = control && control.closest('.form_single');
        if (!row || row.querySelector(':scope > .settings-info')) return;
        const description = helpText(key, fallback);
        attachInfo(row, [description].concat(extras || []), 'settings_info_' + selector.replace(/[^a-z0-9]+/gi, '_'));
    }
    fieldInfo('#game_language', 'help_language_specific', 'Choisit la langue de l’interface et celle utilisée pour reconnaître les messages du jeu. Cela ne change pas la langue du jeu.');
    fieldInfo('#capture_speed', 'help_capture_interval', 'Fixe le délai minimum entre deux analyses de l’écran. Un délai plus long réduit la fréquence de capture et peut manquer des notifications brèves.');
    fieldInfo('#auto_game_start', 'help_auto_game_specific', 'Lance le suivi lorsque la fenêtre du jeu apparaît. Le tracker ne lance pas le jeu.', [document.getElementById('auto_game_start_help')].filter(Boolean));
    fieldInfo('.auto_start', 'help_auto_tracker_specific', 'Démarre le suivi au chargement de l’interface du tracker, sans lancer le jeu.');
    const specificHelp = {
        '#notify_monitor_error':['help_notify_error', 'Affiche une notification Windows si une erreur interrompt la capture ou le suivi.'],
        '#notify_game_hidden':['help_notify_hidden', 'Prévient lorsque le jeu ne peut plus être capturé parce que sa fenêtre n’est plus visible.'],
        '#notify_monitor_stop':['help_notify_stop', 'Signale sur le bureau que le suivi a été arrêté.'],
        '.resolution':['help_resolution', 'Indique la résolution détectée de l’écran principal de Windows, en pixels. Cette valeur est informative.'],
        '.zoomWindow':['help_windows_scale', 'Indique le facteur de mise à l’échelle détecté dans Windows. Ce réglage se modifie dans Windows.'],
        '#display_scale':['help_display_scale', 'Agrandit ou réduit l’interface du tracker et ses textes dans ce navigateur, sans changer la taille du jeu.'],
        '#display_arabesques':['help_arabesques', 'Règle l’opacité des arabesques du panneau de profil : à 0 %, elles sont masquées.'],
        '#display_reduce_motion':['help_motion', 'Réduit les animations de l’interface pour limiter les mouvements à l’écran.'],
        '#display_legend':['help_show_legend', 'Affiche ou masque ta légende dans le panneau de profil sans supprimer son texte.'],
        '#steam_show_name':['help_steam_name', 'Affiche ou masque les noms des profils Steam détectés dans la liste des joueurs.'],
        '#steam_show_country':['help_steam_country', 'Affiche ou masque le pays associé à une adresse réseau lorsqu’il peut être déterminé.'],
        '#steam_show_ping':['help_steam_ping_display', 'Affiche ou masque le ping disponible dans la liste des joueurs Steam, sans modifier sa mesure.'],
        '#notification_top':['help_notification_top', 'Déplace la limite haute de la zone analysée en mode manuel. Place-la juste au-dessus du bandeau de notification.'],
        '#notification_bottom':['help_notification_bottom', 'Déplace la limite basse de la zone analysée en mode manuel. Laisse assez de place pour un bandeau de deux lignes.'],
        '#profile_capture_start':['help_profile_capture', 'Lit le pseudo, le niveau et l’image du personnage depuis l’écran « Quitter la partie » du jeu. Vérifie l’aperçu avant d’enregistrer.'],
        '#profile_legend':['help_profile_legend', 'Enregistre une courte phrase personnelle pour ton panneau de profil. Son affichage se règle séparément.']
    };
    Object.entries(specificHelp).forEach(([selector, description]) => fieldInfo(selector, ...description));

    const steamHelp = document.querySelector('.steam-peer-settings-inner > [data-i18n="steam_settings_help"]');
    fieldInfo('#steam_log_auto', 'steam_log_auto_help', 'Au démarrage du tracker ou de Steam, active le journal nécessaire à la détection des joueurs Steam. La détection P2P doit être activée. En cas d’échec, la configuration manuelle reste disponible.');
    const steamEnabled = document.getElementById('steam_peer_enabled');
    if (steamHelp && steamEnabled && steamEnabled.closest('.form_single')) {
        steamHelp.dataset.i18n = 'help_steam_detection';
        steamHelp.dataset.i18nFr = 'Active la détection des profils Steam connectés à ta session de jeu. Les profils Steam ne sont pas automatiquement associés aux personnages du jeu.';
        steamHelp.textContent = window.uiT ? window.uiT(steamHelp.dataset.i18n, steamHelp.dataset.i18nFr) : steamHelp.dataset.i18nFr;
        attachInfo(steamEnabled.closest('.form_single'), [steamHelp], 'settings_info_steam_enabled');
    } else {
        fieldInfo('#steam_peer_enabled', 'steam_settings_help', 'Lance le jeu puis laisse Steam ouvert. Les noms affichés sont les profils Steam ; les personnages et les rôles peuvent être différents. Le ping peut être indisponible.');
    }
    const pingHelp = document.getElementById('steam_ping_help');
    if (pingHelp) {
        const steamOnly = helpText('steam_ping_steam_only', 'Le ping Steam est affiché lorsqu’il est disponible.');
        const updatePingHelp = () => { steamOnly.hidden = !pingHelp.hidden; };
        updatePingHelp();
        new MutationObserver(updatePingHelp).observe(pingHelp, {attributes:true, attributeFilter:['hidden']});
        const row = pingHelp.closest('.form_single');
        if (row) attachInfo(row, [pingHelp, steamOnly], 'settings_info_steam_ping');
    }
    const steamRetention = document.querySelector('.steam-peer-settings [data-i18n="retention_steam_help"]');
    if (steamRetention) attachInfo(steamRetention.closest('.form_single'), [steamRetention], 'settings_info_retention_steam');
    const quitRow = document.querySelector('.settings-panel .contente_settings[setting="4"] .form_btn');
    if (quitRow) attachInfo(quitRow, [helpText('settings_help_quit', 'Fermer l’onglet laisse le tracker actif ; arrêter le programme ferme le tracker.')], 'settings_info_quit');

    const diagnostics = document.querySelector('.settings-panel .diagnostics-settings');
    let infoSequence = 0, pendingDiagnostics = false;
    const metricHelp = {
        diag_cpu:['help_diag_cpu', 'Part de la capacité totale du processeur utilisée par le processus du tracker, mesurée entre deux relevés.'],
        diag_ram:['help_diag_ram', 'Mémoire vive actuellement occupée par le processus du tracker.'],
        diag_ocr:['help_diag_ocr', 'Durée moyenne d’une lecture OCR depuis le lancement du tracker.'],
        diag_ocr_errors:['help_diag_ocr_errors', 'Nombre de lectures OCR et d’erreurs techniques. Une lecture incorrecte sans erreur technique n’est pas comptée comme erreur.'],
        diag_errors:['help_diag_errors', 'Nombre d’arrêts du suivi causés par une erreur depuis le lancement actuel.'],
        diag_ping:['help_diag_ping', 'Moyenne des pings disponibles des joueurs Steam actuellement détectés ; le nombre entre parenthèses indique les mesures utilisées.'],
        diag_sync:['help_diag_sync', 'Nombre de tentatives de synchronisation avec le classement réussies et échouées depuis le lancement.'],
        diag_sync_time:['help_diag_sync_time', 'Durée moyenne des tentatives de synchronisation avec le classement, réussies ou échouées.'],
        diag_version:['help_diag_version', 'Version de l’application actuellement en cours d’exécution.'],
        storage_database_total:['help_storage_total', 'Espace total occupé par les bases locales et leurs fichiers SQLite associés.'],
        storage_disk_free:['help_storage_free', 'Espace disponible sur le disque qui contient les données du tracker.'],
        usage_total:['help_usage_total', 'Temps cumulé pendant lequel le tracker est resté ouvert, y compris en attente.'],
        usage_sessions:['help_usage_sessions', 'Nombre de lancements du tracker comptabilisés dans les données locales.'],
        usage_average:['help_usage_average', 'Temps total d’utilisation divisé par le nombre de sessions enregistrées.'],
        usage_streak:['help_usage_streak', 'Nombre de jours consécutifs avec une utilisation, en partant d’aujourd’hui ou d’hier.']
    };
    const environmentHelp = {
        tracker:['help_env_tracker', 'Version de cette installation du tracker.'],
        python:['help_env_python', 'Version de Python qui exécute actuellement le tracker.'],
        tesseract:['help_env_tesseract', 'Version du moteur Tesseract utilisé pour lire le texte à l’écran, si elle est disponible.'],
        os:['help_env_os', 'Version du système d’exploitation détectée sur cet appareil.'],
        data_path:['help_env_path', 'Emplacement local des paramètres, statistiques, captures et historiques du tracker.']
    };
    function updateDiagnosticsInfo() {
        pendingDiagnostics = false;
        if (!diagnostics) return;
        diagnostics.querySelectorAll('.stat-detail-row, .environment-row').forEach(row => {
            if (row.querySelector(':scope > .settings-info')) return;
            const value = row.querySelector('strong');
            let description = value && (metricHelp[value.id] || environmentHelp[value.dataset.environment]);
            if (!description && row.closest('#storage_databases')) description = ['help_storage_database', 'Taille de cette base locale, y compris ses fichiers SQLite temporaires associés.'];
            if (!description && row.closest('#usage_recent_sessions')) description = ['help_usage_recent', 'Date de lancement et durée de cette session du tracker.'];
            if (!description && row.closest('#usage_features')) description = ['help_usage_feature', 'Nombre de fois où cette page a été ouverte dans le tracker.'];
            if (!description && row.closest('#usage_modes')) description = ['help_usage_mode', 'Nombre de combats enregistrés dans ce mode et sa part parmi les combats, lorsque les données sont disponibles.'];
            if (!description) description = ['settings_help_diagnostic', 'Mesure locale du tracker, calculée à partir des données disponibles.'];
            attachInfo(row, [helpText(...description)], 'settings_info_diagnostic_' + (++infoSequence));
        });
    }
    if (diagnostics) {
        new MutationObserver(() => {
            if (!pendingDiagnostics) { pendingDiagnostics = true; requestAnimationFrame(updateDiagnosticsInfo); }
        }).observe(diagnostics, {subtree:true, childList:true});
        updateDiagnosticsInfo();
    }
})();
