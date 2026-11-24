/* Personal room appearance: no room messages, player commands, or shared writes. */
(() => {
  const byId = id => document.getElementById(id);
  const body = document.body, world = byId('atmosphere'), media = byId('video');
  const art = world.querySelector('.atlas-art'), plate = world.querySelector('.atlas-plate');
  const grid = world.querySelector('.scene-grid'), controls = [], works = new Map();
  let catalog;
  const artUrl = (work, size) => '/room-art/' + work.key + '-' + size + '.webp' +
    (work.revision ? '?v=' + encodeURIComponent(work.revision) : '');
  function loadCatalog() {
    if (catalog) return catalog;
    catalog = fetch('/scenes/sources.json?room-art=7').then(r => {
      if (!r.ok) throw Error('catalog'); return r.json();
    }).then(rows => {
      const entries = rows.filter(r => r.collection === 'room');
      if (!entries.length) throw Error('Empty scene catalog');
      for (const [i, work] of entries.entries()) {
        const button = document.createElement('button'), thumb = new Image();
        const index = document.createElement('span'), label = document.createElement('span'), name = document.createElement('b'), category = document.createElement('small'), dot = document.createElement('i');
        button.type='button'; button.className='scene-choice'; button.dataset.sceneChoice=work.key; button.setAttribute('aria-pressed','false');
        index.className='atlas-index';index.textContent=String(i+1).padStart(2,'0');
        thumb.src=artUrl(work,'thumb');thumb.alt='';thumb.loading='lazy';thumb.width=72;thumb.height=43;thumb.style.objectPosition='center '+(work.focus*100)+'%';
        label.className='atlas-label';name.textContent=work.title;category.textContent=work.genre+' / '+index.textContent;label.append(name,category);
        dot.className='atlas-dot';dot.setAttribute('aria-hidden','true');
        button.append(index,thumb,label,dot);button.addEventListener('click',()=>choose(button,true));
        works.set(work.key,work);controls.push(button);grid.append(button);
      }
    }).catch(e=>{catalog=null;throw e});
    return catalog;
  }
  const toggle = byId('sceneMotion'), reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const read = (k, d) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } };
  const save = (k, v) => { try { localStorage.setItem(k, v); } catch {} };
  let generation = 0, active = '', visible = false, frame = 0, transition = null, bookOpen = false;
  toggle.checked = read('watchSceneMotion', '1') === '1';
  const canMove = () => body.dataset.view === 'room' && toggle.checked && !reduced.matches &&
    !document.hidden && media.paused && !document.fullscreenElement && !body.classList.contains('player-fullscreen');
  function scrollScene() {
    if (frame || !visible || !canMove()) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      const box = plate.getBoundingClientRect();
      const progress = Math.max(-1, Math.min(1, (innerHeight / 2 - box.top - box.height / 2) / ((innerHeight + box.height) / 2)));
      plate.style.setProperty('--atlas-y', (progress * Math.min(24, box.height * .06)).toFixed(1) + 'px');
    });
  }
  // Keep the ordinary document layout if the optional module is unavailable.
  const chapter = byId('roomOpening');
  let inChapter = false, chapterModule, loadAttempted = false, stopChapter;
  const film = byId('openingFilm'), lowData = matchMedia('(prefers-reduced-data: reduce)');
  let filmWanted = false;
  function syncFilm() {
    const wanted = inChapter && active === 'anime' && canMove() && !lowData.matches && !navigator.connection?.saveData;
    if (wanted === filmWanted) return;
    filmWanted = wanted;
    if (!wanted) { film.pause(); film.removeAttribute('data-ready'); return; }
    if (!film.hasAttribute('src')) film.src = '/room-art/anime-opening-v1.mp4';
    film.play().then(()=>{if (filmWanted && !film.paused) film.setAttribute('data-ready','')}).catch(()=>{});
  }
  lowData.addEventListener('change',syncFilm);
  function syncChapter() {
    syncFilm();
    if (!inChapter || !canMove()) {
      stopChapter?.(); stopChapter = null; return;
    }
    if (stopChapter) return;
    if (chapterModule) {
      try { stopChapter = chapterModule.mountChapter(chapter); }
      catch { chapterModule = null; }
    } else if (!loadAttempted) {
      loadAttempted = true;
      import('/assets/comfort-motion-1.js?v=3').then(module => {
        chapterModule = module; syncChapter();
      }).catch(() => {}); // Static settings remain functional.
    }
  }
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(([entry]) => {
      inChapter = entry.isIntersecting; syncChapter();
    }).observe(document.querySelector('.opening-window'));
  }
  function syncMotion() {
    body.toggleAttribute('data-room-motion', canMove());
    syncChapter();
    if (canMove()) return scrollScene();
    cancelAnimationFrame(frame); frame = 0;
    transition?.cancel(); plate.style.removeProperty('--atlas-y');
  }
  async function choose(button, reveal) {
    const version = ++generation, key = button.dataset.sceneChoice;
    const work = works.get(key);
    const compact = matchMedia('(max-width:760px)').matches;
    const url = artUrl(work, compact ? 'compact' : 'wide');
    const img = new Image(); img.src = url;
    try { await img.decode(); } catch {
      if (version === generation) byId('sceneStatus').textContent = '图片未能加载，已保留当前风景。请重试。';
      return;
    }
    if (version !== generation || body.dataset.view !== 'room') return;
    const name = button.querySelector('b').textContent;
    body.dataset.scene = key;plate.toggleAttribute('data-portrait',work.portrait);
    body.style.setProperty('--atlas-focus', (work.focus*100)+'%');
    document.documentElement.style.setProperty('--scene-image', 'url("' + url + '")');
    for (const c of controls) c.setAttribute('aria-pressed', String(c === button));
    byId('atlasName').textContent = name; byId('atlasEnglish').textContent = work.english;
    const credit=byId('atlasCredit');credit.href=work.source;
    credit.textContent=work.author+' · 原作 ↗';
    byId('atlasNumber').textContent = button.querySelector('.atlas-index').textContent + ' / ' + String(controls.length).padStart(2,'0');
    byId('sceneStatus').textContent = '当前 · ' + name + '（仅自己可见）';
    if (active !== key && reveal && canMove() && typeof art.animate === 'function') {
      transition?.cancel();
      transition = art.animate([{clipPath:'inset(0 0 0 35%)',opacity:.32},{clipPath:'inset(0 0 0 0%)',opacity:1}],{duration:480,easing:'cubic-bezier(.16,1,.3,1)'});
    }
    active = key; save('watchScene',key); syncFilm();
  }
  async function onView() {
    syncMotion();
    if (body.dataset.view !== 'room') { bookOpen = false; generation++; return; }
    if (bookOpen) return;
    bookOpen = true;
    try { await loadCatalog(); } catch { bookOpen=false;byId('sceneStatus').textContent='壁纸目录未能加载，请刷新重试。';return; }
    if (body.dataset.view !== 'room') return;
    choose(controls.find(c => c.dataset.sceneChoice === read('watchScene','anime')) || controls[0], false);
    const entry = {'#together':byId('together'), '#player': byId('player'), '#atmosphere': world, '#advancedControls': byId('advancedControls'), '#comfortSettings': byId('comfortSettings')}[location.hash];
    if (entry) requestAnimationFrame(() => entry.scrollIntoView({block:'start',behavior:'instant'}));
  }
  toggle.addEventListener('change', () => {save('watchSceneMotion', toggle.checked?'1':'0');syncMotion();});
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(([e]) => {visible = e.isIntersecting;scrollScene();});
    observer.observe(plate);
  }
  addEventListener('scroll',scrollScene,{passive:true});
  for (const event of ['play','pause','ended','emptied']) media.addEventListener(event,syncMotion);
  for (const event of ['visibilitychange','fullscreenchange','webkitfullscreenchange','viewportchange']) document.addEventListener(event,syncMotion);
  document.addEventListener('viewchange',onView); reduced.addEventListener('change',syncMotion);
  onView();
})();
