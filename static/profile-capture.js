(function () {
    'use strict';
    const start = document.getElementById('profile_capture_start');
    const panel = document.getElementById('profile_capture_panel');
    const preview = document.getElementById('profile_capture_preview');
    let instructions = document.getElementById('profile_capture_instructions');
    const success = document.getElementById('profile_capture_success');
    const status = document.getElementById('profile_capture_status');
    const save = document.getElementById('profile_capture_save');
    const cancel = document.getElementById('profile_capture_cancel');
    // Older cached templates use a paragraph. Replace it with a semantic
    // container before adding the list, so the same guide works after refresh.
    if (instructions.tagName.toLowerCase() !== 'div') {
        const container = document.createElement('div');
        container.id = instructions.id;
        container.hidden = instructions.hidden;
        instructions.replaceWith(container);
        instructions = container;
    }
    instructions.classList.add('profile-capture-guide');
    instructions.removeAttribute('data-i18n');
    instructions.removeAttribute('data-i18n-fr');
    const guideCopy = [
        ['profile_guide_step_1', 'Lance Elden Ring et charge ton personnage dans le monde.'],
        ['profile_guide_step_2', 'Retourne dans le jeu, ouvre son menu, puis les paramètres du jeu.'],
        ['profile_guide_step_3', 'Va dans le dernier onglet à droite, celui qui permet de quitter. Cet écran affiche notamment le niveau et le temps de jeu de ton personnage. Ne confirme pas la sortie.'],
        ['profile_guide_step_4', 'Laisse cet écran au premier plan quelques secondes ; si la récupération n’est pas terminée, reviens sur le même écran du jeu. Les libellés dépendent de la langue du jeu.'],
        ['profile_guide_step_5', 'Reviens au tracker, vérifie le pseudo, le niveau et l’image, puis enregistre ou annule.']
    ];
    const guideTitle = document.createElement('h3');
    guideTitle.dataset.i18n = 'profile_guide_title';
    guideTitle.dataset.i18nFr = 'Récupérer son profil';
    const steps = document.createElement('ol');
    steps.className = 'profile-guide-steps';
    guideCopy.forEach(function ([key, fallback]) {
        const step = document.createElement('li');
        step.dataset.i18n = key;
        step.dataset.i18nFr = fallback;
        steps.appendChild(step);
    });
    // These language-neutral diagrams reproduce the relative layout of the two
    // game menus without revealing a player's profile information.
    const guideVisuals = [
        {
            key: 'profile_guide_menu_visual_label',
            fallback: '1. Dans le menu du jeu, sélectionne Configuration',
            className: 'profile-guide-menu-visual',
            svg: `<svg viewBox="0 0 320 434" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
                <defs>
                    <linearGradient id="profile-menu-bg" x1="0" y1="0" x2="1" y2="0"><stop stop-color="#24221a"/><stop offset="1" stop-color="#11100d"/></linearGradient>
                    <linearGradient id="profile-menu-selected" x1="0" y1="0" x2="1" y2="0"><stop stop-color="#998a62" stop-opacity=".3"/><stop offset=".6" stop-color="#b6a77c" stop-opacity=".13"/><stop offset="1" stop-color="#b6a77c" stop-opacity="0"/></linearGradient>
                </defs>
                <rect x="1" y="1" width="318" height="432" rx="3" fill="url(#profile-menu-bg)" stroke="#796641" stroke-width="2"/>
                <!-- The illustrations are schematic: the text bars are intentionally language neutral. -->
                <rect x="2" y="361" width="316" height="57" fill="url(#profile-menu-selected)"/>
                <!-- Pixels from the seven menu icons only; the source screenshot is not included. -->
                <defs>
                    <clipPath id="profile-menu-icon-0"><rect x="19" y="14" width="48" height="48"/></clipPath>
                    <clipPath id="profile-menu-icon-1"><rect x="19" y="71" width="48" height="48"/></clipPath>
                    <clipPath id="profile-menu-icon-2"><rect x="19" y="128" width="48" height="48"/></clipPath>
                    <clipPath id="profile-menu-icon-3"><rect x="19" y="185" width="48" height="48"/></clipPath>
                    <clipPath id="profile-menu-icon-4"><rect x="19" y="242" width="48" height="48"/></clipPath>
                    <clipPath id="profile-menu-icon-5"><rect x="19" y="299" width="48" height="48"/></clipPath>
                    <clipPath id="profile-menu-icon-6"><rect x="19" y="356" width="48" height="48"/></clipPath>
                </defs>
                <image href="/static/profile-guide-menu-icons.png" x="19" y="14" width="48" height="336" clip-path="url(#profile-menu-icon-0)"/>
                <image href="/static/profile-guide-menu-icons.png" x="19" y="23" width="48" height="336" clip-path="url(#profile-menu-icon-1)"/>
                <image href="/static/profile-guide-menu-icons.png" x="19" y="32" width="48" height="336" clip-path="url(#profile-menu-icon-2)"/>
                <image href="/static/profile-guide-menu-icons.png" x="19" y="41" width="48" height="336" clip-path="url(#profile-menu-icon-3)"/>
                <image href="/static/profile-guide-menu-icons.png" x="19" y="50" width="48" height="336" clip-path="url(#profile-menu-icon-4)"/>
                <image href="/static/profile-guide-menu-icons.png" x="19" y="59" width="48" height="336" clip-path="url(#profile-menu-icon-5)"/>
                <image href="/static/profile-guide-menu-icons.png" x="19" y="68" width="48" height="336" clip-path="url(#profile-menu-icon-6)"/>
                <g stroke="#c1b393" stroke-width="3" stroke-linecap="round" opacity=".8">
                    <path d="M78 38h71M78 95h106M78 152h62M78 209h45M78 266h60M78 323h82"/>
                </g>
                <path d="M78 380h86" stroke="#ead9ae" stroke-width="3.5" stroke-linecap="round"/>
                <path d="M193 380h-17m6-6-6 6 6 6" fill="none" stroke="#e2c17e" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>`
        },
        {
            key: 'profile_guide_profile_visual_label',
            fallback: '2. Ouvre le dernier onglet et reste sur cet écran',
            className: 'profile-guide-profile-visual',
            svg: `<svg viewBox="0 0 480 270" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
  <defs>
    <linearGradient id="profile-bg" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#161510"/><stop offset=".65" stop-color="#25241b"/><stop offset="1" stop-color="#484638"/></linearGradient>
    <linearGradient id="profile-heading" x1="0" y1="0" x2="1" y2="0"><stop stop-color="#665c41" stop-opacity=".6"/><stop offset="1" stop-color="#665c41" stop-opacity="0"/></linearGradient>
    <clipPath id="profile-guide-default-avatar"><rect x="246" y="91" width="119" height="64"/></clipPath>
  </defs>
  <rect x="1" y="1" width="478" height="268" rx="3" fill="url(#profile-bg)" stroke="#796641" stroke-width="2"/>
  <path d="M2 6H195v19H2z" fill="url(#profile-heading)"/>
  <rect x="12" y="7" width="16" height="16" fill="#554d37" stroke="#aa986d" stroke-width=".6"/>
  <g fill="none" stroke="#c0b08a" stroke-width="1"><circle cx="19" cy="14" r="4"/><circle cx="19" cy="14" r="1.5"/><circle cx="24" cy="19" r="2.5"/></g>
  <path d="M33 15h56" stroke="#baa784" stroke-width="3.5" stroke-linecap="round"/>
  <!-- Barre d’onglets issue de la capture : aucun élément du profil n’est inclus. -->
  <image href="/static/profile-guide-profile-tabs.png" x="16" y="31" width="400" height="34"/>
  <!-- La flèche désigne l’onglet de sortie, sans viser les boutons. -->
  <path d="M380 79V70m-4 4 4-4 4 4" fill="none" stroke="#e2c17e" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  <!-- Panneau : informations à gauche et portrait générique à droite. -->
  <rect x="100" y="84" width="280" height="83" fill="#0b0a08" fill-opacity=".78" stroke="#413c2f"/>
  <path d="M116 103h111M116 122h111M116 137h111" stroke="#706653" stroke-width=".7"/>
  <path d="M121 99h41M129 118h22m17 0h12m32 0h14M165 133h57" stroke="#b7ab90" stroke-width="2.2" stroke-linecap="round"/>
  <image href="/static/default-profile-silhouette.png" x="246" y="91" width="119" height="64" preserveAspectRatio="xMidYMid slice" clip-path="url(#profile-guide-default-avatar)"/>
  <rect x="146" y="184" width="77" height="11" fill="#27251e" stroke="#b1a88e" stroke-width="1"/>
  <rect x="257" y="184" width="77" height="11" fill="#1a1914" stroke="#9e9886" stroke-width=".8"/>
  <path d="M162 189.5h45M272 189.5h47" stroke="#b0a68c" stroke-width="1.7" stroke-linecap="round"/>
  <path d="M97 249h85M97 257h47" stroke="#b2a78a" stroke-width="1.7" stroke-linecap="round"/>
</svg>`
        }
    ];
    const illustrations = guideVisuals.map(function (visual) {
        const figure = document.createElement('figure');
        figure.className = 'profile-guide-visual ' + visual.className;
        figure.innerHTML = visual.svg;
        const caption = document.createElement('figcaption');
        caption.dataset.i18n = visual.key;
        caption.dataset.i18nFr = visual.fallback;
        figure.appendChild(caption);
        return figure;
    });
    instructions.replaceChildren(guideTitle, steps, ...illustrations);
    function translateGuide() {
        instructions.querySelectorAll('[data-i18n]').forEach(function (node) {
            node.textContent = window.uiT ? window.uiT(node.dataset.i18n, node.dataset.i18nFr) : node.dataset.i18nFr;
        });
    }
    document.addEventListener('ui-language-change', translateGuide);
    translateGuide();
    // Create the saved profile separately from the unconfirmed capture. This
    // also upgrades templates cached by an already-running tracker.
    let savedPreview = document.getElementById('saved_profile_preview');
    if (!savedPreview) {
        savedPreview = document.createElement('section');
        savedPreview.id = 'saved_profile_preview';
        savedPreview.className = 'profile-saved-preview';
        savedPreview.hidden = true;
        savedPreview.setAttribute('aria-labelledby', 'saved_profile_title');
        savedPreview.innerHTML = '<h3 id="saved_profile_title" data-i18n="profile_saved_preview" data-i18n-fr="Profil enregistré">Profil enregistré</h3>' +
            '<div class="profile-saved-content"><img id="saved_profile_avatar" alt="" hidden>' +
            '<div class="profile-saved-fields"><p><span data-i18n="online_name" data-i18n-fr="Pseudo">Pseudo</span> : <strong id="saved_profile_name"></strong></p>' +
            '<p><span data-i18n="leaderboard_level" data-i18n-fr="Niveau">Niveau</span> : <strong id="saved_profile_level"></strong></p></div></div>';
        panel.before(savedPreview);
        if (window.uiT) savedPreview.querySelectorAll('[data-i18n]').forEach(function (node) {
            node.textContent = window.uiT(node.dataset.i18n, node.dataset.i18nFr);
        });
    }
    window.updateSavedProfilePreview = function (profile) {
        if (!profile || typeof profile !== 'object') return;
        const name = typeof profile.name === 'string' ? profile.name : '';
        const level = Number(profile.level);
        const avatar = typeof profile.avatar === 'string' ? profile.avatar : '';
        const hasName = !!name.trim();
        const hasLevel = Number.isFinite(level) && level > 0;
        const hasAvatar = !!avatar.trim();
        savedPreview.hidden = !(hasName || hasLevel || hasAvatar);
        const nameNode = savedPreview.querySelector('#saved_profile_name');
        const levelNode = savedPreview.querySelector('#saved_profile_level');
        nameNode.textContent = hasName ? name : '';
        levelNode.textContent = hasLevel ? String(profile.level) : '';
        nameNode.closest('p').hidden = !hasName;
        levelNode.closest('p').hidden = !hasLevel;
        const image = savedPreview.querySelector('#saved_profile_avatar');
        image.hidden = !hasAvatar;
        if (hasAvatar) image.src = 'data:image/jpeg;base64,' + avatar;
        else image.removeAttribute('src');
    };
    if (window.savedProfileSnapshot) window.updateSavedProfilePreview(window.savedProfileSnapshot);
    // Bring older cached templates to the same compact review layout.
    if (!preview.querySelector('.profile-capture-content')) {
        const content = document.createElement('div');
        content.className = 'profile-capture-content';
        const fields = document.createElement('div');
        fields.className = 'profile-capture-fields';
        fields.append(document.getElementById('profile_capture_name').closest('p'),
                      document.getElementById('profile_capture_level').closest('p'));
        content.append(document.getElementById('profile_capture_avatar'), fields);
        preview.prepend(content);
    }
    let actions = panel.querySelector('.profile-capture-actions');
    if (!actions) {
        actions = document.createElement('div');
        actions.className = 'profile-capture-actions';
        panel.appendChild(actions);
    }
    actions.append(cancel, save);
    save.hidden = true;
    let timer = null, token = '', generation = 0;
    const setStatus = (key, fallback) => window.uiSetStatus(status, key, fallback);
    async function request(action, value) {
        const response = await fetch('/profile-capture', {method:'POST', body:new URLSearchParams({action, token:value || ''})});
        if (!response.ok) throw new Error('profile');
        return response.json();
    }
    async function poll(current) {
        if (current !== generation) return;
        try {
            const data = await request('read');
            if (current !== generation) return;
            if (data.request === 'success') {
                token = data.token;
                document.getElementById('profile_capture_name').textContent = data.profile.name;
                document.getElementById('profile_capture_level').textContent = data.profile.level;
                document.getElementById('profile_capture_avatar').src = 'data:image/jpeg;base64,' + data.profile.avatar;
                setStatus(); instructions.hidden = true; success.hidden = false; preview.hidden = false; save.hidden = false; save.disabled = false;
                return;
            }
        } catch (_) { setStatus('profile_capture_error', 'Lecture impossible. Réessaie.'); return; }
        timer = setTimeout(() => poll(current), 2000);
    }
    start.addEventListener('click', function () {
        clearTimeout(timer); generation++; token = ''; preview.hidden = true; save.hidden = true; instructions.hidden = false; success.hidden = true; panel.hidden = false;
        setStatus('profile_capture_wait', 'Laisse le jeu au premier plan sur cet écran pendant la lecture.');
        poll(generation);
    });
    cancel.addEventListener('click', function () {
        generation++; clearTimeout(timer); token = ''; panel.hidden = true; preview.hidden = true; save.hidden = true; instructions.hidden = false; success.hidden = true; setStatus();
    });
    save.addEventListener('click', async function () {
        save.disabled = true;
        try {
            const data = await request('save', token);
            window.savedProfileSnapshot = {name:data.profile.name, level:data.profile.level, avatar:data.profile.avatar};
            window.updateSavedProfilePreview(window.savedProfileSnapshot);
            document.querySelectorAll('.userName').forEach(e => { e.textContent = data.profile.name; });
            document.querySelectorAll('.userLvl_count').forEach(e => { e.textContent = data.profile.level; });
            if (window.updateSidebarProfile) window.updateSidebarProfile(data.profile.name, data.profile.level);
            document.querySelectorAll('.img_user').forEach(container => {
                let image = container.querySelector('.user_img_carde');
                if (!image) { image = document.createElement('img'); image.className = 'user_img_carde'; container.prepend(image); }
                image.src = 'data:image/jpeg;base64,' + data.profile.avatar;
            });
            document.querySelectorAll('.img_user .fakeImageuser').forEach(e => { e.style.display = 'none'; });
            document.querySelectorAll('.carde_info[info="profile"], .carde_info[info="pseudo"], .carde_info[info="avatar"], .carde_info[info="niveau"]').forEach(e => e.remove());
            preview.hidden = true; panel.hidden = true; token = '';
        } catch (_) { setStatus('profile_capture_error', 'Lecture impossible. Réessaie.'); save.disabled = false; }
    });
})();
