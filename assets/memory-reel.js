/* Locally rendered samples and server-supplied screenings never share storage. */
const renderMemory = (() => {
  const section=document.getElementById('together'), stage=section.querySelector('.memory-stage');
  const windowEl=section.querySelector('.memory-window'), list=document.getElementById('memoryList');
  const cues=stage.querySelectorAll('.film-cue');
  const samples=['你的名字。','天气之子','千与千寻','海街日记','心灵奇旅','龙猫','星际穿越','小森林','寻梦环游记','侧耳倾听'].map((title,i)=>({title,exampleDate:'2025.08.'+String(29-i*3).padStart(2,'0')}));
  const dates=new Intl.DateTimeFormat('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit'});
  const reduce=matchMedia('(prefers-reduced-motion: reduce)');
  let history=[], frame=0, visible=false, current=-1;
  function paint(){
    frame=0;
    const count=list.children.length,travel=section.offsetHeight-stage.offsetHeight;
    if(!count||!stage.offsetHeight)return;
    const progress=travel>0?Math.min(1,Math.max(0,-section.getBoundingClientRect().top/travel)):0;
    const floating=progress*(count-1),next=Math.round(floating),position=reduce.matches?next:floating;
    const fraction=count>1?position/(count-1):0;
    stage.style.setProperty('--film-position',(fraction*100)+'%');
    // Absolute offset (not accumulated deltas): reversing the scroll retraces the film.
    stage.style.setProperty('--perforation-offset',(reduce.matches?0:-floating*14)+'px');
    const radius=windowEl.clientHeight*.49;
    // Dates span one third of a circle, sharing each title's vertical position.
    const dateRadius=radius/Math.sin(Math.PI/3);
    for(let i=0;i<count;i++){
      const row=list.children[i],angle=(i-position)*.54;
      if(Math.abs(angle)>=Math.PI/2){row.style.visibility='hidden';row.removeAttribute('aria-current');continue}
      row.classList.toggle('is-past',i<next);row.style.visibility='visible';
      // Each glyph face is tangent to the drum; it turns edge-on before culling.
      row.style.setProperty('--tilt',(reduce.matches?0:-angle)+'rad');
      const y=radius*Math.sin(angle);
      row.style.setProperty('--y',y+'px');
      row.style.setProperty('--arc-inset',(dateRadius-Math.sqrt(dateRadius*dateRadius-y*y))+'px');
      if(i===next)row.setAttribute('aria-current','true');else row.removeAttribute('aria-current');
    }
    if(current!==next){current=next;for(const cue of cues)cue.textContent=String(next+1).padStart(2,'0');document.getElementById('memoryCount').textContent=String(next+1).padStart(2,'0')+' / '+String(count).padStart(2,'0')}
  }
  function requestPaint(){if(!frame)frame=requestAnimationFrame(paint)}
  function scrollPaint(){if(visible)requestPaint()}
  if('IntersectionObserver' in window)new IntersectionObserver(([entry])=>{visible=entry.isIntersecting;if(visible)requestPaint()}).observe(section);
  else visible=true;
  addEventListener('scroll',scrollPaint,{passive:true});addEventListener('resize',requestPaint);reduce.addEventListener('change',requestPaint);
  windowEl.addEventListener('keydown',e=>{
    const n=list.children.length;if(n<2||!['ArrowUp','ArrowDown','Home','End'].includes(e.key))return;
    const i=e.key==='Home'?0:e.key==='End'?n-1:current+(e.key==='ArrowDown'?1:-1);
    if(i<0||i>=n)return;
    e.preventDefault();const top=scrollY+section.getBoundingClientRect().top;
    scrollTo({top:top+(section.offsetHeight-stage.offsetHeight)*i/(n-1),behavior:'instant'});
  });
  function draw(rows,append=false){
    history=append?[...rows.filter(r=>!history.some(h=>h.id===r.id)),...history].slice(0,60):rows.slice(0,60);
    const demo=!history.length, items=demo?samples:history;
    section.dataset.mode=demo?'sample':'history';section.style.setProperty('--steps',items.length-1);
    document.getElementById('memoryMode').textContent=demo?'片名示例 · 非观看记录':'本房间 · 真实放映记录';
    document.getElementById('memoryCaption').textContent=demo?'这里的片名和日期仅作示例。播放第一部影片后，就换成你们自己的放映记录。':'把一起看过的日子，一场一场留下来。';
    document.getElementById('memoryScrollHint').textContent=items.length>1?'滚动页面 · 翻阅片名':'继续下滑 ↓';
    list.replaceChildren(...items.map(r=>{
      const li=document.createElement('li'),label=document.createElement(demo?'small':'time'),name=document.createElement('b');
      if(demo)label.textContent=r.exampleDate;
      else{const date=new Date(r.started*1000);label.dateTime=date.toISOString();label.textContent=dates.format(date)}
      name.textContent=r.title;li.append(name,label);return li;
    }));current=-1;paint();requestPaint();
  }
  draw([]);return draw;
})();
