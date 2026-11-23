// A personal preference: never part of the room or media state.
(() => {
  const key = 'together-cinema.appearance';
  const valid = value => ['day', 'night'].includes(value) ? value : 'auto';
  const read = () => { try { return valid(localStorage.getItem(key)); } catch { return 'auto'; } };
  let mode = read(), timer;
  function apply() {
    clearTimeout(timer);
    const now = new Date(), hour = now.getHours();
    const theme = mode === 'auto' ? (hour >= 7 && hour < 19 ? 'day' : 'night') : mode;
    document.documentElement.dataset.appearance = theme;
    document.querySelector('meta[name="theme-color"]').content = theme === 'night' ? '#191b1f' : '#f8f9f7';
    const menu = document.getElementById('appearanceMode');
    if (menu) menu.value = mode;
    if (mode === 'auto') {
      const next = new Date(now);
      if (hour >= 19) next.setDate(next.getDate() + 1);
      next.setHours(hour < 7 || hour >= 19 ? 7 : 19, 0, 0, 0);
      timer = setTimeout(apply, next - now);
    }
  }
  apply(); // Set the palette before first paint, including on a restored manual choice.
  document.addEventListener('DOMContentLoaded', () => {
    apply();
    document.getElementById('appearanceMode').addEventListener('change', event => {
      mode = valid(event.target.value);
      try { localStorage.setItem(key, mode); } catch { /* still works for this visit */ }
      apply();
    });
  }, {once:true});
  window.addEventListener('storage', event => {
    if (event.key === key || event.key === null) { mode = read(); apply(); }
  });
  window.addEventListener('pageshow', apply);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) apply(); });
})();
