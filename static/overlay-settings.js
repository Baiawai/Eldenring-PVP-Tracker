(function () {
    'use strict';
    const setting = document.getElementById('game_overlay_enabled');
    const status = document.getElementById('game_overlay_status');
    if (!setting || !status) return;
    let changing = false;

    // Construct these rows in JavaScript as well as for an older HTML template
    // still cached by a running tracker process.
    const section = setting.closest('.contente_settings');
    const controls = {};
    const definitions = [
        ['visibility_mode', 'overlay_visibility_mode', 'Affichage de l’overlay', 'visibility', 'visibility'],
        ['background_opacity', 'overlay_custom_transparency', 'Transparence du fond', 'range', 'appearance'],
        ['background_color', 'overlay_custom_background_color', 'Couleur du fond', 'color', 'appearance'],
        ['show_overlay_border', 'overlay_show_border', 'Afficher la bordure de l’overlay', 'checkbox', 'appearance'],
        ['border_color', 'overlay_border_color', 'Couleur des bordures', 'color', 'appearance'],
        ['border_radius', 'overlay_border_radius', 'Arrondi des coins', 'size', 'appearance', 0, 30],
        ['text_color', 'overlay_custom_text_color', 'Couleur du texte', 'color', 'appearance'],
        ['text_opacity', 'overlay_text_transparency', 'Transparence du texte', 'range', 'appearance'],
        ['font_size', 'overlay_custom_text_size', 'Taille du texte', 'size', 'appearance', 12, 32],
        ['width_percent', 'overlay_width_percent', 'Largeur de l’overlay', 'range', 'appearance', 60, 100],
        ['position', 'overlay_position', 'Position de l’overlay', 'position', 'appearance'],
        ['show_status', 'overlay_custom_show_status', 'Afficher l’état du suivi', 'checkbox', 'content'],
        ['show_mode', 'overlay_custom_show_mode', 'Afficher le mode', 'checkbox', 'content'],
        ['show_peers', 'overlay_custom_show_peers', 'Afficher les joueurs et pings', 'checkbox', 'content'],
        ['show_event', 'overlay_custom_show_event', 'Afficher le dernier événement', 'checkbox', 'content'],
        ['show_player_count', 'overlay_player_count', 'Nombre de joueurs connectés', 'checkbox', 'content'],
        ['show_avatars', 'overlay_avatar_label', 'Avatars Steam', 'checkbox', 'players'],
        ['show_player_name', 'player_name', 'Nom du joueur', 'checkbox', 'players'],
        ['show_role', 'overlay_show_role', 'Rôle du joueur', 'checkbox', 'players'],
        ['show_steam_id', 'overlay_steam_id', 'SteamID', 'checkbox', 'players'],
        ['show_country', 'steam_show_country', 'Afficher le pays', 'checkbox', 'players'],
        ['show_ping', 'steam_ping_label', 'Ping Steam', 'checkbox', 'players'],
        ['show_ping_average', 'steam_peer_ping_average', 'Ping moyen', 'checkbox', 'players'],
        ['show_jitter', 'steam_peer_jitter', 'Jitter', 'checkbox', 'players'],
        ['show_quality', 'steam_peer_connection_quality', 'Qualité de connexion', 'checkbox', 'players'],
        ['show_duration', 'steam_peer_duration', 'Durée de connexion', 'checkbox', 'players'],
        ['show_player_stats', 'overlay_encounter_count', 'Nombre de rencontres', 'checkbox', 'players'],
        ['avatar_size', 'overlay_avatar_size', 'Taille des avatars', 'size', 'cards', 24, 96],
        ['card_size', 'overlay_card_size', 'Taille des cartes', 'size', 'cards', 48, 160],
        ['card_spacing', 'overlay_card_spacing', 'Espacement des cartes', 'size', 'cards', 0, 24],
        ['ping_good_color', 'overlay_ping_good_color', 'Couleur du ping faible', 'color', 'colors'],
        ['ping_medium_color', 'overlay_ping_medium_color', 'Couleur du ping moyen', 'color', 'colors'],
        ['ping_bad_color', 'overlay_ping_bad_color', 'Couleur du ping élevé', 'color', 'colors']
    ];
    const groups = {};
    [
        ['appearance', 'overlay_group_appearance', 'Apparence'],
        ['content', 'overlay_group_content', 'Informations générales'],
        ['players', 'overlay_group_players', 'Informations des joueurs'],
        ['cards', 'overlay_group_cards', 'Cartes des joueurs'],
        ['colors', 'overlay_group_ping_colors', 'Couleurs du ping']
    ].forEach(function ([id, key, fallback], index) {
        const group = document.createElement('details');
        group.className = 'overlay-custom-group';
        group.open = index === 0;
        const title = document.createElement('summary');
        title.dataset.i18n = key;
        title.dataset.i18nFr = fallback;
        title.textContent = window.uiT(key, fallback);
        group.appendChild(title);
        if (id === 'players') {
            const note = document.createElement('p');
            note.className = 'overlay-custom-note';
            note.dataset.i18n = 'overlay_player_data_availability';
            note.dataset.i18nFr = 'Certaines informations ne s’affichent que lorsqu’elles sont disponibles.';
            note.textContent = window.uiT(note.dataset.i18n, note.dataset.i18nFr);
            group.appendChild(note);
        }
        section.appendChild(group);
        groups[id] = group;
    });
    const optionStatus = document.createElement('div');
    optionStatus.className = 'overlay-custom-status';
    optionStatus.setAttribute('role', 'status');
    optionStatus.setAttribute('aria-live', 'polite');
    definitions.forEach(function ([name, key, fallback, type, group, minimum, maximum]) {
        const row = document.createElement('div');
        row.className = 'form_single overlay-custom-row';
        if (name === 'visibility_mode') row.classList.add('overlay-visibility-setting');
        const label = document.createElement('label');
        const id = 'overlay_custom_' + name;
        label.className = 'form_single_left';
        label.htmlFor = id;
        label.dataset.i18n = key;
        label.dataset.i18nFr = fallback;
        label.textContent = window.uiT(key, fallback);
        const area = document.createElement('div');
        area.className = 'form_single_right';
        const input = document.createElement(type === 'size' || type === 'position' || type === 'visibility' ? 'select' : 'input');
        input.id = id;
        input.disabled = true;
        if (type === 'size') {
            for (let px = minimum; px <= maximum; px++) {
                const option = document.createElement('option');
                option.value = String(px);
                option.textContent = px + ' px';
                input.appendChild(option);
            }
        } else if (type === 'position') {
            [
                ['top_left', 'overlay_position_top_left', 'En haut à gauche'],
                ['top_right', 'overlay_position_top_right', 'En haut à droite'],
                ['bottom_left', 'overlay_position_bottom_left', 'En bas à gauche'],
                ['bottom_right', 'overlay_position_bottom_right', 'En bas à droite']
            ].forEach(function ([value, key, fallback]) {
                const option = document.createElement('option');
                option.value = value; option.dataset.i18n = key; option.dataset.i18nFr = fallback;
                option.textContent = window.uiT(key, fallback); input.appendChild(option);
            });
        } else if (type === 'visibility') {
            [
                ['capture', 'overlay_visibility_capture', 'Pendant la capture'],
                ['game_visible', 'overlay_visibility_game_visible', 'Quand le jeu n’est pas réduit'],
                ['always', 'overlay_visibility_always', 'Tant que le tracker est ouvert']
            ].forEach(function ([value, key, fallback]) {
                const option = document.createElement('option');
                option.value = value; option.dataset.i18n = key; option.dataset.i18nFr = fallback;
                option.textContent = window.uiT(key, fallback); input.appendChild(option);
            });
        } else {
            input.type = type;
            if (type === 'range') {
                input.min = String(minimum === undefined ? 0 : minimum);
                input.max = String(maximum === undefined ? 100 : maximum);
                input.step = '1';
                const output = document.createElement('output');
                output.id = id + '_value';
                output.htmlFor = id;
                input.setAttribute('aria-describedby', output.id);
                controls[name + '_output'] = output;
            }
        }
        area.appendChild(input);
        if (controls[name + '_output']) area.appendChild(controls[name + '_output']);
        if (name === 'visibility_mode') {
            const selected = document.createElement('output');
            selected.id = id + '_selected';
            selected.className = 'overlay-visibility-value';
            selected.hidden = true;
            input.setAttribute('aria-describedby', selected.id);
            controls.visibility_mode_output = selected;
            area.appendChild(selected);
        }
        row.append(label, area);
        if (group === 'visibility') {
            section.insertBefore(row, groups.appearance);
            if (window.attachSettingsInfo) {
                const help = document.createElement('p');
                help.dataset.i18n = 'overlay_visibility_help';
                help.dataset.i18nFr = 'Le mode jeu non réduit reste visible même si le jeu n’est pas au premier plan. Le mode permanent reste visible même si le jeu est fermé.';
                help.textContent = window.uiT(help.dataset.i18n, help.dataset.i18nFr);
                window.attachSettingsInfo(row, [help], 'settings_info_overlay_visibility');
            }
        } else groups[group].appendChild(row);
        controls[name] = input;
    });
    section.appendChild(optionStatus);
    if (window.initSettingsYesNo) window.initSettingsYesNo(section);

    let savedOptions = {};
    let pendingOptions = {};
    let inFlightOptions = {};
    let saveTimer = null;
    let saving = false;

    function publishOptions() {
        const values = Object.assign({}, savedOptions, inFlightOptions, pendingOptions);
        window.trackerOverlayOptions = values;
        document.dispatchEvent(new CustomEvent('tracker-overlay-options-change', {detail:values}));
    }

    function updateVisibilityLabel() {
        const input = controls.visibility_mode;
        const output = controls.visibility_mode_output;
        if (!input || !output || !input.selectedOptions.length) return;
        const selected = input.selectedOptions[0].textContent;
        output.textContent = selected;
        if (!input.clientWidth) { output.hidden = true; return; }
        const style = getComputedStyle(input);
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');
        if (!context) { output.hidden = false; return; }
        context.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
        const available = input.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
        output.hidden = context.measureText(selected).width <= available;
    }
    if (window.ResizeObserver) new ResizeObserver(updateVisibilityLabel).observe(controls.visibility_mode);
    window.addEventListener('resize', updateVisibilityLabel);
    document.addEventListener('ui-language-change', updateVisibilityLabel);

    function renderOption(name, value) {
        const input = controls[name];
        if (!input) return;
        if (input.type === 'checkbox') {
            input.checked = value === true;
            input.dispatchEvent(new Event('tracker-setting-render'));
        } else if (name === 'background_opacity' || name === 'text_opacity') {
            input.value = String(100 - Number(value));
            controls[name + '_output'].textContent = input.value + ' %';
        } else if (name === 'width_percent') {
            input.value = String(value);
            controls.width_percent_output.textContent = input.value + ' %';
        } else {
            input.value = String(value);
        }
        if (name === 'visibility_mode') updateVisibilityLabel();
    }

    function readOption(name) {
        const input = controls[name];
        if (input.type === 'checkbox') return input.checked;
        if (name === 'background_opacity' || name === 'text_opacity') return 100 - Number(input.value);
        if (name === 'width_percent') return Number(input.value);
        if (name === 'position' || name === 'visibility_mode') return input.value;
        if (input.tagName === 'SELECT') return Number(input.value);
        return input.value;
    }

    async function flushOptions() {
        if (saving || !Object.keys(pendingOptions).length) return;
        const updates = pendingOptions;
        pendingOptions = {};
        inFlightOptions = updates;
        saving = true;
        try {
            const response = await fetch('/overlay-settings', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({options:updates})
            });
            if (!response.ok) throw new Error('request');
            const data = await response.json();
            Object.assign(savedOptions, data.options || updates);
            window.uiSetStatus(optionStatus);
        } catch (_) {
            Object.keys(updates).forEach(function (name) {
                if (!Object.prototype.hasOwnProperty.call(pendingOptions, name) && name in savedOptions) {
                    renderOption(name, savedOptions[name]);
                }
            });
            window.uiSetStatus(optionStatus, 'overlay_custom_error', 'Impossible d’enregistrer ce réglage.');
        } finally {
            saving = false;
            inFlightOptions = {};
            publishOptions();
            if (Object.keys(pendingOptions).length) flushOptions();
        }
    }

    definitions.forEach(function ([name, , , type]) {
        controls[name].addEventListener(type === 'range' || type === 'color' ? 'input' : 'change', function () {
            const value = readOption(name);
            if (name === 'visibility_mode') updateVisibilityLabel();
            if (name === 'background_opacity' || name === 'text_opacity') controls[name + '_output'].textContent = controls[name].value + ' %';
            if (name === 'width_percent') controls.width_percent_output.textContent = controls.width_percent.value + ' %';
            pendingOptions[name] = value;
            publishOptions();
            clearTimeout(saveTimer);
            saveTimer = setTimeout(flushOptions, type === 'range' || type === 'color' ? 150 : 0);
        });
    });

    function showAvailability(data) {
        if (!setting.checked) return window.uiSetStatus(status);
        if (data.status === 'capture_exclusion_unavailable') {
            window.uiSetStatus(status, 'game_overlay_capture_error', 'Overlay masqué : impossible de l’exclure des captures.');
        } else if (data.status === 'window_error') {
            window.uiSetStatus(status, 'game_overlay_window_error', 'Impossible d’afficher l’overlay.');
        } else {
            window.uiSetStatus(status);
        }
    }

    async function refreshAvailability() {
        if (!setting.checked || changing) return;
        try {
            const response = await fetch('/overlay-settings', {cache:'no-store'});
            if (!response.ok) return;
            const data = await response.json();
            if (setting.checked && !changing) showAvailability(data);
        } catch (_) { /* Keep the last known status if the tracker is unreachable. */ }
    }

    if (window.attachSettingsInfo) {
        const description = document.createElement('p');
        description.dataset.i18n = 'game_overlay_help';
        description.dataset.i18nFr = 'Affiche les informations du tracker par-dessus le jeu. Utilise le mode fenêtré ou sans bordure.';
        description.textContent = window.uiT(description.dataset.i18n, description.dataset.i18nFr);
        window.attachSettingsInfo(setting.closest('.form_single'), [description], 'settings_info_game_overlay');
    }

    async function load() {
        try {
            const response = await fetch('/overlay-settings', {cache:'no-store'});
            if (!response.ok) throw new Error('request');
            const data = await response.json();
            setting.checked = data.enabled;
            setting.disabled = false;
            if (!data.options || typeof data.options !== 'object') throw new Error('options');
            savedOptions = Object.assign({}, data.options);
            publishOptions();
            definitions.forEach(function ([name]) {
                if (Object.prototype.hasOwnProperty.call(savedOptions, name)) {
                    renderOption(name, savedOptions[name]);
                    controls[name].disabled = false;
                }
            });
            showAvailability(data);
            setting.dispatchEvent(new Event('tracker-setting-render'));
        } catch (_) {
            window.uiSetStatus(status, 'auto_game_start_error', 'Impossible de charger ce réglage.');
            window.uiSetStatus(optionStatus, 'overlay_custom_load_error', 'Impossible de charger ces réglages.');
        }
    }
    setting.addEventListener('change', async function () {
        const requested = setting.checked;
        changing = true;
        setting.disabled = true;
        window.uiSetStatus(status);
        try {
            const response = await fetch('/overlay-settings', {method:'POST', body:new URLSearchParams({enabled:String(requested)})});
            if (!response.ok) throw new Error('request');
            const data = await response.json();
            setting.checked = data.enabled;
            showAvailability(data);
        } catch (_) {
            setting.checked = !requested;
            window.uiSetStatus(status, 'auto_game_start_error', 'Impossible d’enregistrer ce réglage.');
        } finally {
            changing = false;
            setting.disabled = false;
            setting.dispatchEvent(new Event('tracker-setting-render'));
        }
    });
    load();
    setInterval(refreshAvailability, 5000);
})();
