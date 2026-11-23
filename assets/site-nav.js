/* Room/gallery navigation. No player commands, continuous scroll loop or network requests. */
(() => {
  const nav = document.getElementById('siteNav'), trigger = nav.querySelector('.nav-toggle');
  const links = [...nav.querySelectorAll('.nav-links a')];
  const small = matchMedia('(max-width:1140px)'), media = document.getElementById('video');
  const stage = document.getElementById('videoStage');
  let stageVisible = false, mode = 'idle', closeTimer;
  const inRoom = () => document.body.dataset.view === 'room';
  const visibleLinks = () => links.filter(a => a.dataset.area === (inRoom() ? 'room' : 'gallery'));
  function setMode(next, restore = false) {
    clearTimeout(closeTimer);
    mode = next;
    const wide = next === 'hover' && !small.matches;
    nav.toggleAttribute('data-compact', !wide);
    nav.toggleAttribute('data-open', !wide && next !== 'idle');
    trigger.setAttribute('aria-expanded', String(next !== 'idle'));
    if (restore) trigger.focus({preventScroll:true});
  }
  nav.addEventListener('pointerenter', e => {
    clearTimeout(closeTimer);
    if (e.pointerType !== 'mouse' || mode !== 'idle') return;
    if (!small.matches && document.activeElement === trigger) nav.querySelector('.nav-home').focus({preventScroll:true});
    setMode('hover');
  });
  nav.addEventListener('pointerleave', e => {
    if (e.pointerType !== 'mouse' || mode !== 'hover' || links.includes(document.activeElement)) return;
    // Keep the list painted until its exit stroke finishes; re-entry cancels closure.
    const ms = parseFloat(getComputedStyle(nav).getPropertyValue('--underline-exit')) || 0;
    if (ms) closeTimer = setTimeout(() => { if (!links.includes(document.activeElement)) setMode('idle'); }, ms);
    else setMode('idle');
  });
  function highlight() {
    const group = visibleLinks(), line = Math.max(90, innerHeight * .22);
    const current = group.filter(a => document.getElementById(a.hash.slice(1)).getBoundingClientRect().top <= line).pop() || group[0];
    for (const a of links) {
      if (a === current) a.setAttribute('aria-current','location'); else a.removeAttribute('aria-current');
    }
    nav.querySelector('.nav-current').textContent = current.textContent;
    trigger.setAttribute('aria-label','导航菜单，当前：'+current.textContent);
  }
  function keepVideoClear() {
    const hide = inRoom() && stageVisible && !media.paused;
    nav.toggleAttribute('data-video-clear', hide);
    if (hide || document.fullscreenElement || document.body.classList.contains('player-fullscreen')) setMode('idle');
  }
  trigger.addEventListener('click', () => setMode(mode === 'menu' ? 'idle' : 'menu'));
  nav.addEventListener('keydown', e => {if(e.key==='Escape' && mode !== 'idle'){e.preventDefault();setMode('idle',true);}});
  nav.addEventListener('focusout', e => {if (!nav.contains(e.relatedTarget)) setMode('idle');});
  document.addEventListener('pointerdown', e => {if (!nav.contains(e.target) && mode !== 'idle') setMode('idle');});
  nav.addEventListener('click', e => {
    const a=e.target.closest('a'); if(!a)return;
    const dest=document.getElementById(a.hash.slice(1));
    if(dest){dest.setAttribute('tabindex','-1');dest.focus({preventScroll:true});}
    setMode('idle');
  });
  document.addEventListener('viewchange',()=>{setMode('idle');highlight();keepVideoClear();});
  small.addEventListener('change',()=>setMode('idle',links.includes(document.activeElement)));
  for (const event of ['play','pause','ended','emptied']) media.addEventListener(event,keepVideoClear);
  for (const event of ['fullscreenchange','webkitfullscreenchange','viewportchange']) document.addEventListener(event,keepVideoClear);
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(([e])=>{stageVisible=e.isIntersecting;keepVideoClear();}).observe(stage);
    let spy;
    const measure = () => {
      spy?.disconnect();
      const line=Math.max(90,innerHeight*.22);
      spy=new IntersectionObserver(highlight,{rootMargin:`-${line}px 0px -${Math.max(0,innerHeight-line-2)}px 0px`});
      links.forEach(a => spy.observe(document.getElementById(a.hash.slice(1))));
      highlight();
    };
    measure();window.addEventListener('resize',measure);
  }
  highlight();
})();
