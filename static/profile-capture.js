(function () {
    'use strict';
    const start = document.getElementById('profile_capture_start');
    const panel = document.getElementById('profile_capture_panel');
    const preview = document.getElementById('profile_capture_preview');
    const instructions = document.getElementById('profile_capture_instructions');
    const success = document.getElementById('profile_capture_success');
    const status = document.getElementById('profile_capture_status');
    const save = document.getElementById('profile_capture_save');
    const cancel = document.getElementById('profile_capture_cancel');
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
