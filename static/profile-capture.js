(function () {
    'use strict';
    const start = document.getElementById('profile_capture_start');
    const panel = document.getElementById('profile_capture_panel');
    const preview = document.getElementById('profile_capture_preview');
    const instructions = document.getElementById('profile_capture_instructions');
    const success = document.getElementById('profile_capture_success');
    const status = document.getElementById('profile_capture_status');
    const save = document.getElementById('profile_capture_save');
    let timer = null, token = '', generation = 0;
    const tr = (key, fallback) => window.uiT ? window.uiT(key, fallback) : fallback;
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
                status.textContent = ''; instructions.hidden = true; success.hidden = false; preview.hidden = false; save.disabled = false;
                return;
            }
        } catch (_) { status.textContent = tr('profile_capture_error', 'Lecture impossible. Réessaie.'); return; }
        timer = setTimeout(() => poll(current), 2000);
    }
    start.addEventListener('click', function () {
        clearTimeout(timer); generation++; token = ''; preview.hidden = true; instructions.hidden = false; success.hidden = true; panel.hidden = false;
        status.textContent = tr('profile_capture_wait', 'Laisse le jeu au premier plan sur cet écran pendant la lecture.');
        poll(generation);
    });
    document.getElementById('profile_capture_cancel').addEventListener('click', function () {
        generation++; clearTimeout(timer); token = ''; panel.hidden = true; preview.hidden = true; instructions.hidden = false; success.hidden = true;
    });
    save.addEventListener('click', async function () {
        save.disabled = true;
        try {
            const data = await request('save', token);
            document.querySelectorAll('.userName').forEach(e => { e.textContent = data.profile.name; });
            document.querySelectorAll('.userLvl_count').forEach(e => { e.textContent = data.profile.level; });
            document.querySelectorAll('.img_user').forEach(container => {
                let image = container.querySelector('.user_img_carde');
                if (!image) { image = document.createElement('img'); image.className = 'user_img_carde'; container.prepend(image); }
                image.src = 'data:image/jpeg;base64,' + data.profile.avatar;
            });
            document.querySelectorAll('.img_user .fakeImageuser').forEach(e => { e.style.display = 'none'; });
            document.querySelectorAll('.carde_info[info="profile"], .carde_info[info="pseudo"], .carde_info[info="avatar"], .carde_info[info="niveau"]').forEach(e => e.remove());
            preview.hidden = true; panel.hidden = true; token = '';
        } catch (_) { status.textContent = tr('profile_capture_error', 'Lecture impossible. Réessaie.'); save.disabled = false; }
    });
})();
