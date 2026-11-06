(function () {
    const panel = document.getElementById('information_panel');
    const button = document.getElementById('menu_button_information');
    const otherMenus = ['menu_button_captures', 'menu_button_multi', 'menu_button_info', 'menu_button_players', 'menu_button_history', 'menu_button_settings'];
    function closeInformation() {
        panel.hidden = true;
        button.classList.remove('active');
        button.setAttribute('aria-expanded', 'false');
    }
    function toggleInformation() {
        if (!panel.hidden) { closeInformation(); return; }
        otherMenus.forEach(function(id) {
            const other = document.getElementById(id);
            if (other.classList.contains('active')) other.click();
        });
        panel.hidden = false;
        button.classList.add('active');
        button.setAttribute('aria-expanded', 'true');
    }
    button.setAttribute('aria-controls', 'information_panel');
    button.setAttribute('aria-expanded', 'false');
    button.addEventListener('click', toggleInformation);
    button.addEventListener('keydown', function(event) {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); button.click(); }
    });
    otherMenus.concat('start').forEach(function(id) {
        document.getElementById(id).addEventListener('click', closeInformation);
    });
})();
