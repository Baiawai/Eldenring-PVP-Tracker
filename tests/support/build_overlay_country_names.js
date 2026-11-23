// Generate offline country names using the local ICU/CLDR data in Node.js.
// Only regions with bundled flag assets are included. The application's
// supported UI locales come from its existing translation catalog.
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..', '..');
const packFile = path.join(root, 'application', 'locales', 'ui_packs.json');
const flagDir = path.join(root, 'static', 'flags');
const output = path.join(root, 'application', 'locales', 'overlay_country_names.json');
const packs = JSON.parse(fs.readFileSync(packFile, 'utf8'));
const languages = {fra: 'fr'};
for (const [language, pack] of Object.entries(packs)) languages[language] = pack.html_lang;
const codes = fs.readdirSync(flagDir)
    .filter(name => /^[a-z]{2}\.svg$/.test(name))
    .map(name => name.slice(0, 2).toUpperCase()).sort();

const result = {};
for (const [language, locale] of Object.entries(languages)) {
    if (Intl.DisplayNames.supportedLocalesOf([locale]).length !== 1) {
        throw new Error(`Local ICU does not support ${locale}`);
    }
    const names = new Intl.DisplayNames([locale], {type: 'region', fallback: 'none'});
    result[language] = {};
    for (const code of codes) {
        const name = names.of(code);
        if (name && name !== code) result[language][code] = name;
    }
}
fs.writeFileSync(output, JSON.stringify(result, null, 2) + '\n', 'utf8');
console.log(`Wrote ${Object.keys(languages).length} locales, up to ${codes.length} regions each (ICU ${process.versions.icu}).`);
