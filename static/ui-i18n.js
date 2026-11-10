(function () {
    let language = 'fra';
    // Keep the FAQ current when Flask serves a template cached before this update.
    const faqFrench = {"faq_a_01": "Lance le tracker et Elden Ring, puis sélectionne dans Configuration la langue utilisée en jeu. Clique sur Start pour commencer et sur Stop pour arrêter le suivi. Un nouveau suivi remet la session en mémoire à zéro.", "faq_a_04": "Le tracker lit les notifications à l’écran par reconnaissance de texte (OCR). Un message masqué, manqué ou mal lu peut laisser un résultat inconnu. Vérifie la langue du jeu et la zone dans Configuration → Capture, puis teste-la avec un exemple reconnu sur deux lignes.", "faq_a_05": "Dans Configuration, sélectionne la langue utilisée dans le jeu. Elle règle l’interface et la reconnaissance des messages, sans changer la langue du jeu. Au premier lancement, la langue du navigateur est utilisée si elle est prise en charge, sinon l’anglais ; ton choix enregistré est conservé.", "faq_a_06": "Dans Configuration → Capture, la détection automatique cherche la zone des notifications et prévoit les messages sur deux lignes. Vérifie l’aperçu avec un exemple reconnu, puis verrouille la zone si elle est correcte ; déverrouille-la si l’affichage change. Tu peux aussi désactiver le mode automatique et régler les limites manuellement. Un intervalle plus long réduit la fréquence des lectures et peut manquer des messages courts.", "faq_a_07": "Choisis un mode : le taux de victoire divise les victoires par les victoires, défaites et égalités enregistrées. Les égalités ne concernent que l’arène. Le graphique utilise les captures de résultats conservées ; il peut donc différer des statistiques cumulées.", "faq_a_09": "Les informations Steam et le ping apparaissent lorsqu’ils sont disponibles. Une adresse peut être celle d’un relais et sa localisation reste indicative. En développement, la mesure avancée du ping peut demander une autorisation administrateur ; la version Store utilise le ping Steam disponible sans élévation.", "faq_a_12": "La version Store comprend les composants nécessaires. Pour lancer le projet depuis ses sources, installe Python et prépare la distribution locale de Tesseract ou utilise une installation existante ; consulte le README du projet.", "faq_a_13": "Fermer l’onglet laisse le tracker actif. Stop arrête le suivi ; Configuration → Quitter ferme le programme. Redémarrer le suivi remet la session en mémoire à zéro, mais conserve les statistiques enregistrées.", "faq_q_15": "Comment récupérer mon profil de personnage ?", "faq_a_15": "Dans Configuration → Profil, lance la capture. En jeu, ouvre Configuration → Quitter la partie sans confirmer la sortie et garde le jeu visible. Le tracker récupère ensemble pseudo, niveau et image : vérifie-les avant d’enregistrer ou annule si nécessaire.", "faq_q_16": "Comment fonctionnent l’archivage et la purge de l’historique ?", "faq_a_16": "Arrête le suivi avant d’archiver ou de purger l’historique actif. L’archivage retire les événements de la liste, y compris les rencontres Steam, et les conserve chiffrés localement. La restauration ajoute les événements absents sans doublons et conserve l’archive. La purge retire l’historique actif mais conserve les archives, les captures et les statistiques cumulées.", "faq_q_17": "Comment activer la détection Steam ?", "faq_a_17": "Dans Configuration → P2P, active la détection des joueurs. L’activation automatique du journal Steam est proposée par défaut : elle demande à Steam d’activer le journal nécessaire au démarrage du tracker ou de Steam. Si elle échoue, la commande manuelle reste disponible. Les profils observés ne sont pas automatiquement associés aux personnages en jeu."};
    faqFrench.faq_a_11 = 'La consultation du classement contacte le serveur configuré, par défaut eldenringpvp.com. La participation est facultative et nécessite de connecter un compte Steam.';
    faqFrench.faq_q_18 = 'Comment connecter Steam et participer au classement ?';
    faqFrench.faq_a_18 = 'Dans Configuration → Classement en ligne, active la participation et accepte les conditions. Connecte-toi à Steam dans la fenêtre ouverte, puis saisis dans le tracker le code temporaire affiché par le site ; ne partage pas ce code. La publication d’un lien vers ton profil Steam est facultative.';
    const faqList = document.querySelector(".faq-list");
    if (faqList) {
        Object.keys(faqFrench).forEach(function (key) {
            let node = faqList.querySelector('[data-i18n="' + key + '"]');
            if (!node && /^faq_q_1[5-8]$/.test(key)) {
                const item = document.createElement("details"); item.className = "faq-item";
                node = document.createElement("summary"); node.dataset.i18n = key;
                const answer = document.createElement("p"); answer.dataset.i18n = key.replace("faq_q_", "faq_a_");
                item.append(node, answer); faqList.appendChild(item);
            }
            if (node) { node.textContent = faqFrench[key]; node.dataset.i18nFr = faqFrench[key]; }
        });
    }
    // Keep the community link available when an existing server has cached its template.
    const informationShell = document.querySelector('#information_panel .information-shell');
    if (informationShell && !informationShell.querySelector('.information-discord-panel')) {
        informationShell.querySelectorAll('.information-discord').forEach(node => node.remove());
        const panel = document.createElement('section');
        panel.className = 'information-discord-panel';
        panel.setAttribute('aria-labelledby', 'information_discord_title');
        panel.innerHTML = '<img class="information-discord-icon" src="/static/icon-discord-bronze.png" alt=""><div class="information-discord-content"><h2 id="information_discord_title" data-i18n="information_discord_title">Aide et assistance</h2><p data-i18n="information_discord_help">Pour toute aide ou demande de support, rejoins notre serveur Discord.</p><a class="information-discord" href="https://discord.gg/y79z83D2Ua" target="_blank" rel="noopener noreferrer" data-i18n="information_discord">Rejoindre le serveur Discord</a></div>';
        informationShell.prepend(panel);
    }
    const rankingPanel = document.querySelector('.cadre_multi');
    if (rankingPanel) {
        // Restore the original layout even when Flask has cached the disabled-page template.
        const header = rankingPanel.querySelector('.leaderboard-header');
        if (header && !header.querySelector('.leaderboard-intro')) {
            const intro = document.createElement('p');
            intro.className = 'leaderboard-intro'; intro.dataset.i18n = 'leaderboard_intro';
            intro.textContent = 'Retrouve les résultats des combattants de l’arène.';
            header.querySelector('div').appendChild(intro);
        }
        if (header && !header.querySelector('#leaderboard_refresh')) {
            const refresh = document.createElement('button');
            refresh.type = 'button'; refresh.id = 'leaderboard_refresh'; refresh.dataset.i18n = 'leaderboard_refresh';
            refresh.textContent = 'Actualiser'; header.appendChild(refresh);
        }
        rankingPanel.querySelectorAll('.leaderboard-intro, #leaderboard_refresh').forEach(node => { node.hidden = false; });
        const rankingContent = rankingPanel.querySelector('.panel_multi_body');
        if (rankingContent) { rankingContent.id = 'leaderboard_content'; rankingContent.hidden = true; }
        if (header && !rankingPanel.querySelector('.leaderboard-content-options')) {
            const options = document.createElement('section'); options.className = 'leaderboard-content-options';
            options.innerHTML = '<p data-i18n="leaderboard_content_rules">Le classement est modéré par l’administrateur. La nudité et la violence explicite sont interdites.</p><p data-i18n="leaderboard_content_filter_explain">Les pseudonymes et avatars sont fournis par les joueurs et modérés manuellement. Choisis de les afficher pour consulter le classement.</p><button type="button" id="leaderboard_content_toggle" aria-pressed="false" aria-controls="leaderboard_content" data-i18n="leaderboard_content_show">Afficher le contenu des joueurs</button><p data-i18n="leaderboard_report_help">Un e-mail s’ouvre : indique le pseudo concerné, sans inclure d’informations sensibles.</p><a class="leaderboard-report" data-i18n="leaderboard_report_button" href="mailto:gael.pitras@gmail.com?subject=Signalement%20de%20contenu%20du%20classement&amp;body=Pseudo%20concern%C3%A9%20%3A%0ADescription%20%3A%0A%0AN%E2%80%99inclus%20aucune%20information%20sensible.">Signaler un contenu</a>';
            header.after(options);
        }
        const status = rankingPanel.querySelector('#leaderboard_status');
        if (status) {
            status.hidden = true; status.removeAttribute('data-i18n'); status.textContent = '';
        }
    }
    // Older cached templates do not contain the report action on the player card.
    const playerHeading = document.querySelector('#leaderboard_player_dialog .leaderboard-player-heading');
    if (playerHeading && !playerHeading.querySelector('.leaderboard-player-report')) {
        const link = document.createElement('a'); link.className = 'leaderboard-player-report';
        link.dataset.i18n = 'leaderboard_report_button'; link.textContent = 'Signaler un contenu';
        link.href = 'mailto:gael.pitras@gmail.com?subject=Signalement%20de%20contenu%20du%20classement';
        playerHeading.appendChild(link);
    }
    if (playerHeading && !playerHeading.querySelector('.leaderboard-player-report-help')) {
        const help = document.createElement('p'); help.className = 'leaderboard-player-report-help';
        help.dataset.i18n = 'leaderboard_report_help'; help.textContent = 'Un e-mail s’ouvre : indique le pseudo concerné, sans inclure d’informations sensibles.';
        playerHeading.appendChild(help);
    }
    // Refresh the favicon even when the running server has cached an older template.
    document.querySelectorAll('link[rel~="icon"]').forEach(link => { link.href = '/static/tracker-eye-ornament.ico'; });
    const profileInstructions = document.getElementById('profile_capture_instructions');
    if (profileInstructions) profileInstructions.textContent = 'Lance Elden Ring et charge ta partie. Une fois dans le monde du jeu, ouvre le menu principal, puis Configuration. Va dans l’onglet tout à droite, « Quitter la partie », sans quitter la partie. L’application y récupérera automatiquement ton pseudo, ton niveau et ton image. Attends quelques secondes (environ 2 à 5 secondes), puis reviens ici pour vérifier les informations récupérées et les enregistrer.';
    // Upgrade the guidance in templates cached by an already-running tracker.
    const legacyProfile = document.querySelector('.carde_info[info="pseudo"]');
    if (legacyProfile) {
        legacyProfile.setAttribute('info', 'profile');
        const title = legacyProfile.querySelector('h5');
        const description = legacyProfile.querySelector('p');
        if (title) { title.classList.remove('btr_3'); title.dataset.i18n = 'profile_capture_start'; title.textContent = 'Récupérer mon profil'; }
        if (description) description.classList.remove('btr_4');
        document.querySelectorAll('.carde_info[info="avatar"], .carde_info[info="niveau"]').forEach(node => node.remove());
    }
    const profileGuidance = document.querySelector('.carde_info[info="profile"] p');
    if (profileGuidance) {
        profileGuidance.dataset.i18n = 'sidebar_profile_guidance';
        profileGuidance.textContent = 'Lance Elden Ring et charge ta partie, puis ouvre l’onglet « Quitter la partie » sans quitter. L’application récupérera ton pseudo, ton niveau et ton image.';
        if (!profileGuidance.parentElement.querySelector('.sidebar-guidance-action')) {
            const action = document.createElement('p');
            action.className = 'sidebar-guidance-action';
            action.dataset.i18n = 'sidebar_profile_open';
            action.textContent = 'Clique ici pour ouvrir la configuration du profil.';
            profileGuidance.after(action);
        }
    }
    document.querySelectorAll('.carde_info[info="captures"]').forEach(node => node.remove());
    [['languages', 'icon-settings-bronze.png'], ['profile', 'icon-edit-profile-bronze.png']].forEach(function (entry) {
        const icon = document.querySelector('.carde_info[info="' + entry[0] + '"] img');
        if (icon) { icon.src = '/static/' + entry[1]; icon.alt = ''; }
    });
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
    // Add accessible translations to templates already cached by the running server.
    [['.players-overview', 'players_recognized', 'Joueurs identifiés'],
     ['#capture_mode', 'captures_mode_label', 'Mode des captures']].forEach(function(entry) {
        const node = document.querySelector(entry[0]);
        if (node) { node.dataset.i18nAria = entry[1]; node.dataset.i18nAriaFr = entry[2]; }
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
