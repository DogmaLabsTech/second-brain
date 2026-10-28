// 05 Timeline (brief 10): one bar per day (notes changed that day), oldest left, today right. Hover a bar = its date and count,
// click = jump there, drag across the bars or the track = scrub. ▶ replays the brain day by day (notes fade in as their day
// arrives), NOW goes back to live. The panel owns its markup and state; the Deck only hears onChange(cut) and asks alpha(age).
// cut = how many days back we stand (0 = live, float while replaying); a note of age a is shown fully when a >= cut.
const fmt = t => new Date(t).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' });
export function makeTimeline(el, { ages, NOW, max = 38, count, onChange }) {
  const bins = Array.from({ length: max + 1 }, (_, a) => ages.filter(x => x === a).length), top = Math.max(1, ...bins.slice(0, max));
  const dayOf = a => NOW - a * 864e5, label = a => a >= max ? `${max}+ days ago` : a === 0 ? 'Today' : a === 1 ? 'Yesterday' : fmt(dayOf(a));
  const frac = c => (max - c + .5) / (max + 1);   // the playhead sits on the middle of the bar of day c
  el.innerHTML = `<div class="h"><span><i class="num">05</i>Timeline</span><b><span class="tl-now" data-r="dl">LIVE</span></b></div>
    <div class="tl-plot" data-r="plot" role="slider" tabindex="0" aria-label="day" aria-valuemin="0" aria-valuemax="${max}">
      <div class="tl-bars">${bins.map((_, k) => { const a = max - k; return `<i data-a="${a}" class="${a === 0 ? 'today' : a >= max ? 'old' : ''}${a && a % 7 === 0 ? ' wk' : ''}" style="--h:${Math.max(5, bins[a] / top * 100)}%"></i>`; }).join('')}</div>
      <div class="tl-track"><u data-r="fill"></u><em data-r="thumb"></em></div><div class="tl-head" data-r="head"></div><div class="tl-tip" data-r="tip"></div></div>
    <div class="tl-axis"><span class="l">${max}+ DAYS</span>${[28, 21, 14, 7].map(a => `<span style="--x:${frac(a) * 100}%">${fmt(dayOf(a)).replace(/^\w+ /, '').toUpperCase()}</span>`).join('')}<span class="r">TODAY</span></div>
    <div class="tl-ctl"><button class="chip2 tl-play" data-r="play" title="replay the brain day by day"><i></i><span>REPLAY</span></button><button class="chip2" data-r="now" title="back to today">NOW</button><span class="tl-sum" data-r="sum"></span></div>`;
  const R = n => el.querySelector(`[data-r=${n}]`), plot = R('plot'), barEls = [...el.querySelectorAll('.tl-bars i')].reverse();   // barEls[a] = day a
  let cut = 0, playing = false, scrub = null;
  function set(c, quiet) { cut = Math.max(0, Math.min(max, c)); const d = Math.round(cut), f = frac(cut);
    plot.style.setProperty('--f', (f * 100).toFixed(2) + '%'); plot.setAttribute('aria-valuenow', max - d); plot.setAttribute('aria-valuetext', label(d));
    R('dl').textContent = d === 0 ? 'LIVE' : label(d).toUpperCase(); R('dl').classList.toggle('past', d > 0);
    barEls.forEach((b, a) => { b.classList.toggle('off', a < cut - .5); b.classList.toggle('cur', a === d && d > 0); });
    R('sum').innerHTML = `<b>${count(d).toLocaleString()}</b> notes ${d === 0 ? 'now' : 'by then'}<span> · ${bins[Math.min(d, max)]} changed ${d === 0 ? 'today' : d >= max ? 'earlier' : 'that day'}</span>`;
    if (!quiet) onChange(cut); }
  function play(on) { playing = on; el.classList.toggle('playing', on); R('play').querySelector('span').textContent = on ? 'PAUSE' : 'REPLAY'; if (on && cut < .5) set(max); }
  // the plot: hover shows the day, click jumps to it, a drag scrubs smoothly
  const at = e => { const r = plot.getBoundingClientRect(), x = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)); return max + .5 - x * (max + 1); };
  function tip(e) { const a = Math.max(0, Math.min(max, Math.round(at(e)))), b = barEls[a], t = R('tip');
    t.innerHTML = `<b>${label(a)}</b>${bins[a]} note${bins[a] === 1 ? '' : 's'} changed${a < max ? '' : ' (and older)'}`; t.style.setProperty('--x', frac(a) * 100 + '%'); t.classList.add('on');
    barEls.forEach(x => x.classList.toggle('hov', x === b)); }
  plot.addEventListener('pointermove', e => { tip(e); if (scrub) { scrub.moved = true; set(at(e)); } });
  plot.addEventListener('pointerleave', () => { if (scrub) return; R('tip').classList.remove('on'); barEls.forEach(x => x.classList.remove('hov')); });
  plot.addEventListener('pointerdown', e => { if (e.button !== 0) return; play(false); scrub = { moved: false }; plot.setPointerCapture(e.pointerId); plot.classList.add('scrub'); });
  const up = e => { if (!scrub) return; const s = scrub; scrub = null; plot.classList.remove('scrub'); set(s.moved ? at(e) : Math.max(0, Math.min(max, Math.round(at(e))))); if (!plot.matches(':hover')) R('tip').classList.remove('on'); };
  plot.addEventListener('pointerup', up); plot.addEventListener('pointercancel', up);
  plot.addEventListener('keydown', e => { const k = { ArrowLeft: 1, ArrowRight: -1, PageUp: 7, PageDown: -7, Home: max, End: -max }[e.key]; if (!k) return; e.preventDefault(); e.stopPropagation(); play(false); set(Math.round(cut) + k); });
  R('play').onclick = () => play(!playing); R('now').onclick = () => { play(false); set(0); };
  set(0, true);
  return { get cut() { return cut; }, set, play,
    // the frame: a replay walks about 3.8 days a second (the whole span in ten seconds), then stops on today
    tick(dt) { if (!playing) return; set(cut - dt * max / 10000); if (cut <= 0) { set(0); play(false); } },
    // how much a note of this age is there at the current cut: 0..1, so notes fade in during a replay instead of popping
    alpha: a => Math.max(0, Math.min(1, a - cut + 1)) };
}
