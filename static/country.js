// Country names follow the selected interface language; flags are bundled locally.
window.appendIpCountry = function(container, code) {
    if (typeof code !== 'string' || !/^[A-Z]{2}$/.test(code)) return;
    let name = code;
    try { name = new Intl.DisplayNames([document.documentElement.lang || 'fr'], {type:'region'}).of(code) || code; } catch (_) {}
    const span = document.createElement('span');
    span.className = 'ip-country';
    const flag = document.createElement('img');
    flag.src = '/static/flags/' + code.toLowerCase() + '.svg';
    flag.alt = '';
    flag.addEventListener('error', function() { flag.hidden = true; });
    span.append(flag, document.createTextNode(name));
    container.append(document.createTextNode(' · '), span);
};
