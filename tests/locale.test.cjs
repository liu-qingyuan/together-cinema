const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const assets = path.join(__dirname, '../web/assets');
function language(languages, saved, blocked = false) {
  const store = new Map(saved ? [['watchLanguage', saved]] : []);
  const context = vm.createContext({navigator: {languages}, Intl, Date,
    localStorage: {getItem(k) {if (blocked) throw Error('blocked'); return store.get(k);},
      setItem(k, v) {if (blocked) throw Error('blocked'); store.set(k, v);}}});
  for (const file of ['locale-messages.js', 'locale.js']) vm.runInContext(fs.readFileSync(path.join(assets, file), 'utf8'), context);
  return {locale: context.CinemaLocale, store};
}
test('local language resolves preferences and still switches when storage is unavailable', () => {
  assert.equal(language(['fr', 'en-GB']).locale.language, 'en');
  assert.equal(language(['zh-TW', 'en']).locale.language, 'zh-CN');
  assert.equal(language(['ja']).locale.language, 'zh-CN');
  assert.equal(language(['en'], 'zh-CN').locale.language, 'zh-CN');
  assert.equal(language(['en'], 'invalid').locale.language, 'en');
  const {locale, store} = language(['zh-CN']);
  locale.setLanguage('en');
  assert.equal(locale.language, 'en');
  assert.equal(store.get('watchLanguage'), 'en');
  const unavailable = language(['en'], null, true).locale;
  unavailable.setLanguage('zh-CN');
  assert.equal(unavailable.language, 'zh-CN');
});

test('stable error IDs localize while unknown and legacy responses remain readable', async () => {
  const {locale} = language(['en']);
  const known = await locale.responseError({text: async () => '旧中文错误', headers: {get: () => 'source_expired'}});
  assert.equal(locale.t(locale.error(known).key), 'Online source expired or released. Find the source again.');
  for (const code of [null, 'future_error']) {
    const legacy = await locale.responseError({text: async () => 'Readable legacy detail', headers: {get: () => code}});
    assert.equal(locale.error(legacy), 'Readable legacy detail');
  }
  assert.throws(() => locale.t('room.label'), /Missing interpolation/);
  assert.throws(() => locale.t('missing.key'), /Missing translation/);
  assert.equal(locale.t('network.filmTitle', {title: '<original> 中文', mode: locale.message('network.direct')}), '<original> 中文 · Direct');
});
