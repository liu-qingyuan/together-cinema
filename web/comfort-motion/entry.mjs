// A single scroll measurement drives paused native animations, not the player.
import { animate } from 'motion/mini';
import { scroll } from 'motion';
export function mountChapter(section) {
  const tracks = [];
  let unsubscribe = () => {};
  function stop() {
    unsubscribe();
    for (const [player, node, props] of tracks) {
      player.cancel();
      for (const name of props) node.style.removeProperty(name);
    }
    tracks.length = 0;
  }
  function track(selector, frames) {
    const node = section.querySelector(selector);
    const player = animate(node, frames, {duration: 1, ease: 'linear'});
    player.pause();
    tracks.push([player, node, Object.keys(frames)]);
  }
  try {
    track('.comfort-photo', {transform: ['scale(1)', 'scale(1.09)']});
    track('.comfort-intro', {transform: ['translateY(0px)', 'translateY(-76px)'], opacity: [1, 0]});
    track('.opening-actions', {opacity:[1,0]});
    // Two arguments select Motion's element-tracking subscription.
    unsubscribe = scroll((_progress, info) => {
      for (const [player] of tracks) player.time = info.y.progress;
    }, {target: section.parentElement, offset: ['start start', 'center start']});
    return stop;
  } catch (err) { stop(); throw err; }
}
