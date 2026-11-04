(function () {
    const selector = document.getElementById('game_language');
    const status = document.getElementById('game_language_status');
    const label = document.getElementById('game_language_label');
    if (!selector) return;
    const uiCodes = {frafr:'fra', engus:'eng', deude:'deu', itait:'ita', spaes:'spaes', spaar:'spaar', porbr:'por', polpl:'pol', rusru:'rus', jpnjp:'jap', korkr:'kor', zhocn:'chi', zhotw:'zht', thath:'tha', araae:'ara'};
    const labels = {fra:'Langue',eng:'Language',deu:'Sprache',ita:'Lingua',spaes:'Idioma',spaar:'Idioma',por:'Idioma',pol:'Język',rus:'Язык',jap:'言語',kor:'언어',chi:'语言',zht:'語言',tha:'ภาษา',ara:'اللغة'};
    let current = '';
    function tr(key, french) { return window.uiT ? window.uiT(key, french) : french; }
    function updateLabel() { label.textContent = labels[window.uiCurrentLanguage ? window.uiCurrentLanguage() : 'fra'] || 'Langue'; }
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
            status.textContent = tr('game_language_loading_error', 'Impossible de charger les langues.');
        }
    }
    selector.addEventListener('change', async function() {
        const next = selector.value;
        selector.disabled = true;
        status.textContent = '';
        status.classList.remove('error');
        try {
            const response = await fetch('/languages', {method:'POST', body:new URLSearchParams({language:uiCodes[next]})});
            const data = await response.json();
            if (!response.ok) {
                if (data.reason === 'combat_active') throw new Error('combat');
                throw new Error('request');
            }
            current = data.game_language;
            selector.value = current;
            launchLanguages(data.language);
            if (typeof launchChart === 'function' && typeof mode_chart !== 'undefined') launchChart(mode_chart, 1);
        } catch (error) {
            selector.value = current;
            status.classList.add('error');
            status.textContent = error.message === 'combat' ?
                tr('game_language_combat_error', 'Termine la partie en cours avant de changer la langue.') :
                tr('game_language_error', 'Impossible de changer la langue.');
        } finally { selector.disabled = false; }
    });
    document.addEventListener('ui-language-change', updateLabel);
    init();
})();
