/* Local presentation only: never owns a room, socket, or media lifecycle. */
(() => {
  'use strict';
  const messages = globalThis.CinemaMessages;
  const storageKey = 'watchLanguage', supported = ['zh-CN', 'en'];
  let saved;
  try { saved = localStorage.getItem(storageKey); } catch {}
  let language = supported.includes(saved) ? saved :
    (navigator.languages || [navigator.language]).map(value => {
      const base = String(value).toLowerCase().split('-')[0];
      return base === 'zh' ? 'zh-CN' : base === 'en' ? 'en' : null;
    }).find(Boolean) || 'zh-CN';
  const bindings = new WeakMap();
  const message = (key, values = {}) => ({key, values});
  function render(value) {
    if (value && typeof value === 'object') {
      if ('date' in value) return new Intl.DateTimeFormat(language, value.options).format(new Date(value.date));
      if (value.key) return t(value.key, value.values);
    }
    return String(value ?? '');
  }
  function t(key, values = {}) {
    const template = messages[key]?.[language];
    if (template === undefined) throw Error('Missing translation: ' + key + '/' + language);
    return template.replace(/\{(\w+)\}/g, (_, name) => {
      if (!(name in values)) throw Error('Missing interpolation: ' + key + '/' + name);
      return render(values[name]);
    });
  }
  function text(element, value, attribute = null) {
    // Weak bindings let removed chat/library rows be collected normally.
    if (!attribute) {
      element.removeAttribute('data-i18n');
      element.removeAttribute('data-i18n-html');
    }
    const entries = bindings.get(element) || new Map();
    entries.set(attribute, value);
    bindings.set(element, entries);
    element.setAttribute('data-locale-bound', '');
    if (attribute) element.setAttribute(attribute, render(value));
    else element.textContent = render(value);
  }
  function apply() {
    const doc = globalThis.document;
    if (!doc) return;
    doc.documentElement.lang = language;
    for (const el of doc.querySelectorAll('[data-i18n]')) el.textContent = t(el.dataset.i18n);
    // Only trusted, bundled static copy may contain markup; user values use text().
    for (const el of doc.querySelectorAll('[data-i18n-html]')) el.innerHTML = t(el.dataset.i18nHtml);
    for (const attr of ['aria-label', 'title', 'placeholder']) {
      for (const el of doc.querySelectorAll('[data-i18n-' + attr + ']')) el.setAttribute(attr, t(el.getAttribute('data-i18n-' + attr)));
    }
    for (const el of doc.querySelectorAll('[data-locale-bound]')) {
      for (const [attribute, value] of bindings.get(el) || []) {
        if (attribute) el.setAttribute(attribute, render(value));
        else el.textContent = render(value);
      }
    }
    const select = doc.getElementById('interfaceLanguage');
    if (select) select.value = language;
  }
  function setLanguage(next) {
    if (!supported.includes(next)) throw Error('Unsupported language: ' + next);
    language = next;
    try { localStorage.setItem(storageKey, next); } catch {}
    apply();
    globalThis.document?.dispatchEvent(new Event('languagechange'));
  }
  function error(value) {
    if (value?.localeKey) return message(value.localeKey);
    const code = value?.code || (value?.name ? 'browser_' + value.name : null);
    return code && messages['error.' + code] ? message('error.' + code) : value?.message || String(value);
  }
  async function responseError(response) {
    const value = new Error(await response.text());
    value.code = response.headers.get('X-Cinema-Error');
    return value;
  }
  globalThis.CinemaLocale = {get language() { return language; }, t, message, text, setLanguage,
    error, responseError, date: (date, options) => ({date, options}),
    failure: key => Object.assign(new Error(t(key)), {localeKey: key})};
  globalThis.document?.addEventListener('DOMContentLoaded', () => {
    apply();
    const select = document.getElementById('interfaceLanguage');
    if (select) select.addEventListener('change', () => setLanguage(select.value));
  });
})();
