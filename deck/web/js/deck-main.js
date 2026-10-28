import { THREE, NOW, chrome, boot, typeInto, makeCloud, lineMat, project, days, hex3, cardInfo } from '../hud.js';
import { makeShell, DOT_GLSL } from '../shell.js';
import { makeSkins } from '../skins.js';
import { movable, replaceAll } from '../movable.js'; import { makeTimeline } from '../timeline.js'; import { makeAsk } from '../ask.js';
import { rings, ringWords, hideRingTip } from '../rings.js'; import { makeLive, makeFeed } from '../live.js';
import { H, KC, LAY, Lmap, N, S, TAU, VIEW, W, age, camFrom, camera, clamp, cloud, cur, delay, ease, fitView, go, hidden, mats, nbLines, paint, renderer, root, say, scanFrom, scanOp0, scanner, scene, sets, shell, skins, slice, sweepG, thM, to, view, viewDist, vis, yOf } from './deck/scene.js'; export * from './deck/scene.js';
import { anchors, invertKey, labelCur, labelEls, labelOff, setOpen, settings, wk } from './deck/settings.js'; export * from './deck/settings.js';
import { addLabel, animateIn, clearLabels, decode, eff, labels, lead, leadL, leadSvg, mk, refresh, renderSection, ret, shown, tip, tmp, visible, xh, xv } from './deck/panels.js'; export * from './deck/panels.js';
import { byAny, byPath, mdRender, nh, pick, pk } from './deck/links.js'; export * from './deck/links.js';
import { RD, STILL, asking, cancelEdit, closeReader, docOf, dropTitle, editing, exitEdit, follow, histGo, jumpTo, keepEditing, layoutReader, leaveEdit, loose, note, openReader, readerOpen, readerW, renderNote, saveEdit, startEdit } from './deck/reader.js'; export * from './deck/reader.js';
import './deck/lock-tag.js'; export * from './deck/lock-tag.js';
import { dotHover, lock, pvDot, pvHide, pvI, unlock } from './deck/hover.js'; export * from './deck/hover.js';
import { ask, tl } from './deck/timeline-ask.js'; export * from './deck/timeline-ask.js';
import { live, liveNonce, liveOwn } from './deck/live.js'; export * from './deck/live.js';
import { PICK, dotXY, leftAway, leftW, nearDot } from './deck/input.js'; export * from './deck/input.js';
// ---- 07 Voice: talk to the brain like the voice island (the TALK button, or hold Space). Mic -> /talk/stt -> /talk/ask
// (first sentence early) -> /talk/say per sentence (Kokoro bm_george), played through an analyser so the shell follows the voice.
const TV = RD('voicep'), TB = RD('tbtn'), MUTE = location.hash.includes('mute'), post = (u, body, sig) => fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Deck': '1' }, body: JSON.stringify(body), signal: sig });
const TSUB = { idle: 'click talk or hold space', listening: 'talk now · click or let go to send', thinking: 'looking in your notes', speaking: 'click or esc to stop', unheard: 'speak closer or louder · check the mic below' };
const TBL = { listening: 'SEND', thinking: 'STOP', speaking: 'STOP' };
let talk = 'idle', tgen = 0, tAbort = null, ac = null, mic = null, rec = null, recBits = [], recMode = '', recAt = 0, heardAt = 0, quietAt = 0; S.micAn = null; S.outAn = null; S.src = null; let sayQ = [], sayChain = null, sayMore = false, pumping = false, tJob = null, tId = '', tFake = '', voiceEv = null;   // voiceEv: the voice answer's live event, held while it speaks
const talkBuf = new Float32Array(2048);   // ~43 ms of sound per reading: a steadier loudness than one short window
function tState(st, sub) { talk = st; if (st !== 'speaking' && st !== 'thinking' && voiceEv) { live.release(voiceEv); voiceEv = null; }   /* the voice finished (or stopped): its lines fade calmly now */ TV.dataset.s = st; shell.set(st === 'job' || st === 'unheard' ? 'idle' : st); RD('tbl').textContent = TBL[st] || 'TALK'; RD('tstate').textContent = st === 'error' ? 'ERROR' : st === 'job' ? 'WAITING FOR YOU' : st === 'unheard' ? "I DIDN'T HEAR YOU" : st === 'idle' ? 'READY' : st.toUpperCase(); RD('tsub').textContent = sub ?? TSUB[st] ?? ''; RD('tsub').title = RD('tsub').textContent; }
function tErr(t) { tState('error', t); }
export const notePulse = () => shell.voice * 1.1;   // the answer's notes pulse with the voice
const audio = () => ac || (ac = new AudioContext());
function rms(an) { an.getFloatTimeDomainData(talkBuf); let a = 0; for (let k = 0; k < talkBuf.length; k++) a += talkBuf[k] * talkBuf[k]; return Math.sqrt(a / talkBuf.length); }
const LVI = RD('tlvi'), LVB = RD('tlv'); let floor = .2, lvShown = -1, barLv = 0, barT = 0;   // floor: the room's noise level, so a quiet mic still counts as talking above it
// soft(): the loudness as the shell feels it: a soft knee at the bottom (room noise doesn't flicker) and a soft top (a loud word doesn't slam to the max)
const soft = x => { x = x < -.1 ? 0 : x < .1 ? (x + .1) * (x + .1) / .4 : x; return clamp((1 - Math.exp(-1.8 * x)) / (1 - Math.exp(-1.8))); };
function talkFrame(t) { let lv = 0, felt = 0;
  if (tFake) lv = tFake === 'listening' ? .5 + .3 * Math.sin(t / 130) * Math.sin(t / 410) : tFake === 'speaking' ? Math.max(0, .55 + .45 * Math.sin(t / 90) * Math.sin(t / 260)) : 0;
  else if (talk === 'listening' && S.micAn) { lv = clamp((20 * Math.log10(Math.max(rms(S.micAn), 1e-5)) + 52) / 34); felt = soft((lv - floor - .04) / (.85 - floor)); const now = performance.now(), th = clamp(floor + .16, .22, .38);
    floor = lv < floor ? floor + (lv - floor) * .2 : floor + (lv - floor) * .004; LVB.style.setProperty('--th', Math.round(th * 100) + '%'); LVB.classList.toggle('hear', lv > th);
    if (recMode === 'click') { if (lv > th) { heardAt = heardAt || now; quietAt = now; }   // the island's rule: stop 1.3 s after the voice ends, or 8 s with no voice
      if ((heardAt && now - quietAt > 1300) || (!heardAt && now - recAt > 8000) || now - recAt > 30000) stopRec(true); } }
  else if (talk === 'speaking' && S.outAn) felt = soft(lv = clamp((20 * Math.log10(Math.max(rms(S.outAn), 1e-5)) + 45) / 32));
  if (tFake) felt = lv; S.voiceLv = lv; shell.level(felt, talk === 'speaking' && !S.src && !tFake);   // between two sentences the shell holds the voice
  const dt = Math.min(.05, barT ? (t - barT) / 1000 : .016); barT = t; barLv = lv > barLv ? lv : barLv + (lv - barLv) * (1 - Math.exp(-dt / .15));   // the bar: up at once, down calmly
  const w = Math.round(barLv * 200); if (w !== lvShown && !leftAway) { LVI.style.transform = `scaleX(${w / 200})`; lvShown = w; } }
// the mic picker: the browser's inputs (names show after the first mic permission), remembered; the first time it picks the Yeti
const MICK = 'deckMic', DEV = RD('tdev');
async function listMics() { let ds = []; try { ds = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === 'audioinput' && d.deviceId && d.deviceId !== 'default' && d.deviceId !== 'communications'); } catch {}
  let want = localStorage.getItem(MICK) || ''; if (want && !ds.some(d => d.deviceId === want)) want = ds.some(d => d.label) ? '' : want;
  if (!localStorage.getItem(MICK)) { const y = ds.find(d => /yeti/i.test(d.label)); if (y) { want = y.deviceId; localStorage.setItem(MICK, want); } }
  DEV.innerHTML = '<option value="">system default mic</option>' + ds.map((d, k) => `<option value="${esc(d.deviceId)}">${esc((d.label || 'microphone ' + (k + 1)).replace(/\s*\([0-9a-f]{4}:[0-9a-f]{4}\)$/i, ''))}</option>`).join('');
  DEV.value = ds.some(d => d.deviceId === want) ? want : ''; DEV.title = DEV.selectedOptions[0]?.textContent || ''; }
DEV.onchange = () => { localStorage.setItem(MICK, DEV.value || 'system'); DEV.title = DEV.selectedOptions[0]?.textContent || ''; DEV.blur(); };
if (navigator.mediaDevices) { listMics(); navigator.mediaDevices.addEventListener?.('devicechange', listMics); }
// a desk mic: no echo cancelling (the brain's voice is stopped while it listens), no noise gate and no auto gain (both can swallow a
// quiet voice, and Chrome's auto gain turns the system's mic volume); the server raises a quiet recording instead
const micWant = id => ({ audio: { ...(id && id !== 'system' ? { deviceId: { exact: id } } : {}), channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
async function startRec(mode) {
  if (talk === 'listening') return; stopTalk(); const g = ++tgen; recMode = mode; tState('listening', 'opening the microphone…');
  const id = DEV.value; try { mic = await navigator.mediaDevices.getUserMedia(micWant(id)); }
  catch (e) { if (id && e && (e.name === 'OverconstrainedError' || e.name === 'NotFoundError')) { try { mic = await navigator.mediaDevices.getUserMedia(micWant('')); DEV.value = ''; } catch (e2) { e = e2; } }
    if (!mic) { if (g === tgen) tErr(e && e.name === 'NotAllowedError' ? 'the microphone is blocked: allow it for this page' : 'no microphone: ' + (e && e.message || e)); return; } }
  if (g !== tgen) { mic.getTracks().forEach(x => x.stop()); mic = null; return; }
  if (![...DEV.options].some(o => o.value && !o.textContent.startsWith('microphone '))) listMics();   // the names are known now
  const a = audio(); a.resume(); S.micAn = a.createAnalyser(); S.micAn.fftSize = 2048; a.createMediaStreamSource(mic).connect(S.micAn); floor = .2;
  recBits = []; rec = new MediaRecorder(mic, MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? { mimeType: 'audio/webm;codecs=opus', audioBitsPerSecond: 64000 } : {}); rec.ondataavailable = e => e.data.size && recBits.push(e.data);
  rec.onstop = () => { const type = rec.mimeType || 'audio/webm', send = rec._send, ms = Math.round(performance.now() - recAt); mic && mic.getTracks().forEach(x => x.stop()); mic = null; S.micAn = null; rec = null; LVB.classList.remove('hear'); if (g !== tgen) return;
    if (!send) return tState('idle'); if (ms < 350) return tState('idle', 'too short: hold Space while you talk'); sendAudio(new Blob(recBits, { type }), ms, g); };
  rec.start(250); recAt = performance.now(); heardAt = 0; quietAt = 0; tState('listening'); }
function stopRec(send) { if (rec && rec.state !== 'inactive') { rec._send = send; rec.stop(); } }
// a transcript with no real words (empty, only punctuation, one letter, only "um"/"hmm"): nothing heard, never a question (the server checks too)
const FILLER = new Set('um umm uh uhh uhm erm er ah ahh oh eh hm hmm hmmm mm mmm mhm huh uh-huh mm-hmm hm-hmm'.split(' '));
function saidNothing(t) { const w = String(t || '').toLowerCase().match(/[\p{L}\p{N}]+(?:-[\p{L}\p{N}]+)*/gu) || []; return w.join('').length <= 1 || w.every(x => FILLER.has(x)); }
function sendAudio(blob, ms, g) { tState('thinking', 'turning your words into text…'); tAbort = new AbortController();
  fetch('/talk/stt', { method: 'POST', headers: { 'Content-Type': 'audio/webm', 'X-Deck': '1' }, body: blob, signal: tAbort.signal })
    .then(x => x.json()).then(j => { if (g !== tgen) return; if (j.error) return tErr(j.error);
      if (j.heard === false || saidNothing(j.text)) return tState('unheard', j.why === 'silent' ? 'the mic sent silence · pick your mic below' : 'speak closer or louder · check the mic below');
      askBrain(j.text, 'voice', { ms_record: ms, ms_convert: j.ms_convert, ms_stt: j.ms_stt, engine: j.engine }); })
    .catch(e => { if (g === tgen && e.name !== 'AbortError') tErr('the Deck server did not answer'); }); }
function caption(q, a, typing) { RD('tcap').classList.add('on'); if (q !== undefined) RD('tq').textContent = q; RD('ta').innerHTML = esc(a || '') + (typing ? '<span class="cur"></span>' : ''); }
function askBrain(q, how, stt) { if (saidNothing(q)) return tState('unheard'); const g = ++tgen; tJob = null; tId = ''; RD('tjob').classList.remove('on'); RD('tchips').innerHTML = ''; caption(q, '', true); tState('thinking'); tAbort = new AbortController(); let spoke = '', buf = '';
  post('/talk/ask', { q, how, stt, live: liveNonce() }, tAbort.signal).then(async x => { if (!x.ok) throw new Error('the Deck server said ' + x.status); const rd = x.body.getReader(), dec = new TextDecoder();
    for (;;) { const { value, done } = await rd.read(); if (g !== tgen) return rd.cancel(); if (value) buf += dec.decode(value, { stream: true }); let n;
      while ((n = buf.indexOf('\n')) >= 0) { const line = buf.slice(0, n); buf = buf.slice(n + 1); let ev; try { ev = JSON.parse(line); } catch { continue; }
        if (ev.event === 'first' && !spoke) { spoke = ev.text; caption(undefined, spoke, true); speak(spoke, true); }
        else if (ev.event === 'done') showAnswer(ev, spoke, g); }
      if (done) break; } })
    .catch(e => { if (g === tgen && e.name !== 'AbortError') tErr(String(e.message || e)); }); }
function showAnswer(r, spoke, g) { tId = r.id || ''; caption(undefined, r.answer || '(no answer)');
  const list = (r.sources || []).map(x => ({ x, i: x.c ? byPath.get(x.c + ':' + pk(x.p)) : undefined }));
  RD('tchips').innerHTML = list.map(({ x, i }, n) => `<button ${i === undefined ? 'disabled title="not in the Deck\'s snapshot"' : `data-i="${i}" title="${esc(x.c + '/' + x.p)}  ·  click to open"`} style="--k:${i === undefined ? 'var(--dim)' : KC(DOCS[i].c)}"><i>${String(n + 1).padStart(2, '0')}</i><span>${esc(i === undefined ? x.title : DOCS[i].t)}</span></button>`).join('');
  RD('tchips').querySelectorAll('button[data-i]').forEach(b => b.onclick = () => lock(+b.dataset.i));
  const lit = list.map(o => o.i).filter(i => i !== undefined); live.release(voiceEv);
  voiceEv = liveOwn({ q: RD('tq').textContent, who: 'Deck voice', kind: 'ask', list: lit, secs: list.filter(o => o.i === undefined && o.x.c).map(o => o.x.c), voice: true, hold: true });   /* held until the voice has said it all (tState releases it) */ if (lit.length && S.sel < 0) { clearLabels(); ask.quiet(); lit.forEach(i => addLabel(i, DOCS[i].t)); }
  if (r.kind === 'job' && r.job) { tJob = r.job; RD('tjl').textContent = r.job.label || r.job.id; RD('tjob').classList.add('on'); RD('tyes').disabled = RD('tno').disabled = false; stopVoice(); if (r.answer) speak(r.answer, false); else tState('job'); return; }
  const rest = spoke ? (r.answer.startsWith(spoke) ? r.answer.slice(spoke.length).trim() : (r.rest || '')) : r.answer; speak(rest || '', false); }
// the voice: sentence by sentence (bin/say's split), each made while the one before plays
function sentences(text) { const raw = text.split(/\s+/).join(' ').split(/(?<=[.!?])\s+/).map(x => x.trim()).filter(Boolean), out = [];
  for (const p of raw) { if (out.length && out[out.length - 1].length < 25) out[out.length - 1] += ' ' + p; else out.push(p); } if (!out.length) out.push(text);
  if (out[0].length > 60) { const m = out[0].match(/^(.{12,60}?\bnotes? says?)\s+(.+)$/) || out[0].match(/^(.{20,70}?,)\s+(.+)$/); if (m) out.splice(0, 1, m[1], m[2]); } return out; }
function speak(text, more) { const g = tgen; sayMore = more; if (!text.trim()) return pumping || sayDone();
  for (const part of sentences(text)) { const prev = sayChain || Promise.resolve(); const got = prev.then(() => g === tgen ? post('/talk/say', { text: part }).then(x => x.ok ? x.arrayBuffer() : x.json().then(j => { throw new Error(j.error); })) : null); sayChain = got.catch(() => null); sayQ.push(got); }
  if (!pumping) { pumping = true; playNext(g); } }
async function playNext(g) { if (g !== tgen) return; const got = sayQ.shift(); if (!got) { pumping = false; return sayMore ? tState('thinking', 'still writing the answer…') : sayDone(); }
  let buf; try { buf = await got; } catch (e) { if (g === tgen) { pumping = false; tErr('the voice failed: ' + (e.message || e)); } return; } if (g !== tgen || !buf) return g === tgen ? playNext(g) : undefined;
  if (talk !== 'speaking') tState('speaking'); if (MUTE) { setTimeout(() => playNext(g), 300); return; }
  const a = audio(); a.resume(); let ab; try { ab = await a.decodeAudioData(buf); } catch { return playNext(g); } if (g !== tgen) return;
  S.outAn = S.outAn || (() => { const n = a.createAnalyser(); n.fftSize = 2048; n.connect(a.destination); return n; })(); S.src = a.createBufferSource(); S.src.buffer = ab; S.src.connect(S.outAn);
  S.src.onended = () => { S.src = null; playNext(g); }; S.src.start(); }
function sayDone() { if (talk === 'error') return; sayMore = false; tJob ? tState('job', 'yes or no below') : tState('idle'); }
function stopVoice() { sayQ = []; sayChain = null; sayMore = pumping = false; if (S.src) { S.src.onended = null; try { S.src.stop(); } catch {} S.src = null; } }
function stopTalk(byUser) { const was = talk; tgen++; if (tAbort) tAbort.abort(); tAbort = null; stopRec(false); stopVoice();
  if (byUser && tId && (was === 'thinking' || was === 'speaking')) post('/talk/outcome', { id: tId, what: 'stopped' }).catch(() => {}); tJob ? tState('job', 'yes or no below') : tState('idle', was === 'idle' || was === 'error' || was === 'unheard' ? undefined : 'stopped'); }
RD('tyes').onclick = () => { if (!tJob) return; const job = tJob, g = ++tgen; RD('tyes').disabled = RD('tno').disabled = true; stopVoice(); tState('thinking', (job.label || 'working on it') + '…');
  post('/talk/job', { job, id: tId, confirmed: true }).then(x => x.json()).then(r => { if (g !== tgen) return; tJob = null; RD('tjob').classList.remove('on'); caption(undefined, r.message || 'Done.'); r.speak && r.message ? speak(r.message, false) : tState(r.ok ? 'idle' : 'error', r.ok ? 'done' : 'the job failed'); })
    .catch(() => { if (g === tgen) { tJob = null; RD('tjob').classList.remove('on'); tErr('the Deck server did not answer'); } }); };
RD('tno').onclick = () => { if (!tJob) return; if (tId) post('/talk/outcome', { id: tId, what: 'declined' }).catch(() => {}); tJob = null; RD('tjob').classList.remove('on'); stopTalk(); caption(undefined, "Okay, I won't."); tState('idle'); };
TB.onclick = () => { if (tFake) return; if (talk === 'listening') stopRec(true); else if (talk === 'thinking' || talk === 'speaking') stopTalk(true); else startRec('click'); };
export const typingIn = el => el && el.closest && el.closest('input,textarea,select,[contenteditable=""],[contenteditable="true"]');
addEventListener('keydown', e => { if (e.key === 'Escape' && (talk === 'listening' || talk === 'thinking' || talk === 'speaking')) { e.preventDefault(); e.stopImmediatePropagation(); return stopTalk(true); }
  if (e.code !== 'Space' || e.ctrlKey || e.metaKey || e.altKey || editing || typingIn(e.target) || leftAway) return; e.preventDefault(); e.stopImmediatePropagation(); if (e.repeat) return;
  if (talk === 'thinking' || talk === 'speaking') stopTalk(true); startRec('hold'); }, true);
addEventListener('keyup', e => { if (e.code !== 'Space' || recMode !== 'hold') return; e.preventDefault(); if (rec) stopRec(true); else if (talk === 'listening') { tgen++; tState('idle'); } recMode = ''; }, true);
// test switches (headless): talk=idle|listening|thinking|speaking|error|unheard shows a state with a made-up level; ask=<words> asks the brain in text (add mute); chip=<n> clicks the n-th Ask chip
{ const tm = location.hash.match(/[#&]talk=(\w+)/), am = location.hash.match(/[#&]ask=([^&]+)/);
  if (tm) { tFake = tm[1]; tm[1] === 'error' ? tErr('the microphone is blocked: allow it for this page') : tState(tm[1] in TSUB ? tm[1] : 'idle'); if (tm[1] === 'unheard') caption('', ''), RD('tcap').classList.remove('on'); setTimeout(() => { shell.level(.6); shell.snap(); }, 50); }
  if (am) setTimeout(() => askBrain(decodeURIComponent(am[1]), 'test'), 600);
  const cm = location.hash.match(/[#&]chip=(\d+)/); if (cm) setTimeout(() => { const b = ask.chips()[+cm[1]]; if (b) b.click(); }, 500); }
// frame
let last = performance.now(); renderSection();
function frame(t) {
  const dt = Math.min(50, t - last); last = t;
  if (S.prog < 1) { if (!S.hold) S.prog = Math.min(1, S.prog + dt / 2800); for (let i = 0; i < N; i++) { const e = ease(clamp(S.prog * 1.4 - delay[i])); for (let k = 0; k < 3; k++) cur[i * 3 + k] = S.from[i * 3 + k] + (to[i * 3 + k] - S.from[i * 3 + k]) * e; cur[i * 3 + 1] += Math.sin(Math.PI * e) * .55; } cloud.g.attributes.position.needsUpdate = true; }
  const pe = ease(S.prog); if (Math.abs(S.targetOffX - S.offX) > .3) { S.offX += (S.targetOffX - S.offX) * .12; fitView(); camera.updateProjectionMatrix(); }
  if (!S.drag && S.ty === null && S.hov < 0 && pvDot < 0) S.yaw += dt * (view === 'radar' ? .00003 : .00006);   // the slow turn waits while the mouse rests on a dot or its card, so the dot doesn't slide away from under it
  if (S.ty !== null) { let dy = S.ty - S.yaw; dy = Math.atan2(Math.sin(dy), Math.cos(dy)); S.yaw += dy * .07; if (Math.abs(dy) < .004) S.ty = null; }
  const lookT = view === 'tunnel' ? -.1 : 0;   // during a switch the camera rides the same eased clock as the notes and the ring (starts and lands softly)
  if (S.autoCam && S.prog < 1 && camFrom) { S.pitch = camFrom[0] + (S.pT - camFrom[0]) * pe; S.dist = camFrom[1] + (S.dT - camFrom[1]) * pe; S.lookY = camFrom[2] + (lookT - camFrom[2]) * pe; }
  else { if (S.autoCam) { S.pitch += (S.pT - S.pitch) * .045; S.dist += (S.dT - S.dist) * .045; } S.lookY += (lookT - S.lookY) * .045; }
  tl.tick(dt);
  root.rotation.set(0, S.yaw, 0); camera.position.set(0, Math.sin(S.pitch) * S.dist, Math.cos(S.pitch) * S.dist); camera.lookAt(0, S.lookY, 0); camera.updateMatrixWorld(); root.updateMatrixWorld();   // labels and the reticle are placed with this frame's camera, not the last one
  // structure fade + highlight
  for (const k in vis) vis[k] += ((view === k ? 1 : 0) - vis[k]) * .06; const e = eff();
  for (const m of mats) { const u = m.userData; m.opacity = u.op * vis[u.view] * (u.sec && e ? (u.sec === e ? 1 : .25) : 1); }
  sets.map.visible = vis.map > .02; sets.tunnel.visible = vis.tunnel > .02; sets.radar.visible = vis.radar > .02;
  const sweep = (t * .00045) % TAU; sweepG.rotation.y = -sweep; cloud.m.uniforms.uSweep.value = sweep; cloud.m.uniforms.uSweepOn.value = 0;   // calm (brief 15): the sweep no longer pings notes
  const slY = yOf(S.cutoff); slice.position.y = slY; const cu = cloud.m.uniforms; cu.uScan.value = -2.6 + Math.abs(Math.sin((S.beamT = (S.beamT + dt * .00012) % 1) * Math.PI)) * 5.2; cu.uScanA.value = 0;   /* calm (brief 15): no roaming map beam over the notes */ cu.uScan2.value = slY; cu.uScanB.value = vis.tunnel;
  // scanner ring rides the transition
  scanner.visible = S.prog < 1; scanner.position.y = scanFrom + (yOf(-1) - scanFrom) * ease(S.prog); scanner.material.opacity = S.prog >= 1 ? 0 : .95 * Math.min(clamp(scanOp0 + S.prog * 5), clamp((1 - S.prog) * 4));
  shell.frame(t, ease(S.prog), scanner.position.y, scanner.material.opacity);
  // labels
  const place = [];   // labels are kept inside the free area first, then pushed apart (so the edge can't stack them again)
  const fl = 16 + leftW() + 8, Rr = document.getElementById(readerOpen ? 'reader' : 'right').getBoundingClientRect(), fr = (Rr.width ? Rr.left : W()) - 8;
  COLS.forEach((c, k) => { const a = S.labelFrom[k].clone().lerp(anchors[view][c], pe); labelCur[k].copy(a); tmp.copy(a).applyMatrix4(root.matrixWorld); const [x, y] = project(tmp, camera, W(), H()); const el = labelEls[k];
    const w = el.offsetWidth || 120; place.push({ el, x: clamp(x, fl + w / 2, fr - w / 2), y, y0: y, k, w, h: (el.offsetHeight || 18) + 4, c }); });
  place.sort((p, q) => p.y - q.y);
  for (let it = 0; it < 4; it++) for (let m = 0; m < place.length; m++) for (let n = 0; n < m; n++) { const p = place[m], q = place[n]; if (hidden.has(p.c) || hidden.has(q.c)) continue; if (Math.abs(p.x - q.x) < (p.w + q.w) / 2 + 6 && Math.abs(p.y - q.y) < p.h) p.y = q.y + p.h; }
  for (const p of place) { const o = labelOff[p.k], dy = p.y - p.y0; labelOff[p.k] = o === undefined || STILL ? dy : o + clamp((dy - o) * .18, -3, 3); p.y = p.y0 + labelOff[p.k]; p.el.style.left = p.x + 'px'; p.el.style.top = p.y + 'px'; p.el.style.opacity = hidden.has(p.c) ? 0 : ''; p.el.classList.toggle('dim', !!(e && e !== p.c)); }
  // live searches: lines to the notes, pulses, sections waking (live.js)
  live.frame(t);
  // hover: the nearest dot wins, but stay on the current dot until the mouse is clearly nearer another one (no flicker between neighbours)
  let [best, bd] = S.drag || S.overRd ? [-1, 0] : nearDot(S.mx, S.my); if (S.hov >= 0 && best !== S.hov && !S.drag && !S.overRd && cloud.A[S.hov] >= .5) { const [x, y, z] = dotXY(S.hov), dh = Math.hypot(x - S.mx, y - S.my); if (z <= 1 && dh < PICK + 4 && (best < 0 || bd > dh - 5)) best = S.hov; }
  S.hov = best; renderer.domElement.style.cursor = S.hov >= 0 ? 'pointer' : 'grab'; tip.style.display = 'none'; dotHover(t);
  const taken = place.filter(p => !hidden.has(p.c)).map(p => [p.x - p.w / 2, p.y - p.h / 2, p.x + p.w / 2, p.y + p.h / 2]);   // note labels sit right of their dot (translate 10px, -50%)
  labels.map(l => { tmp.set(cur[l.i * 3], cur[l.i * 3 + 1], cur[l.i * 3 + 2]).applyMatrix4(root.matrixWorld); const [x, y] = project(tmp, camera, W(), H()); return { l, x, y, w: l.el.offsetWidth, h: l.el.offsetHeight + 2 }; }).sort((a, b) => a.y - b.y)
    .forEach(p => { let y = p.y; if (p.w) { for (let it = 0; it < 12; it++) { const r = [p.x + 10, y - p.h / 2, p.x + 10 + p.w, y + p.h / 2], hit = taken.find(b => r[0] < b[2] && r[2] > b[0] && r[1] < b[3] && r[3] > b[1]); if (!hit) break; y = hit[3] + p.h / 2 + 1; } taken.push([p.x + 10, y - p.h / 2, p.x + 10 + p.w, y + p.h / 2]); }
      const o = p.l.oy, dy = y - p.y; p.l.oy = o === undefined || STILL ? dy : o + clamp((dy - o) * .18, -3, 3); p.l.el.style.left = p.x + 'px'; p.l.el.style.top = p.y + p.l.oy + 'px'; });
  if (S.sel >= 0) { const arr = nbLines.geometry.attributes.position.array; DOCS[S.sel].nb.forEach((j, k) => { arr.set([cur[S.sel * 3], cur[S.sel * 3 + 1], cur[S.sel * 3 + 2], cur[j * 3], cur[j * 3 + 1], cur[j * 3 + 2]], k * 6); }); nbLines.geometry.attributes.position.needsUpdate = true; nbLines.visible = true;
    tmp.set(cur[S.sel * 3], cur[S.sel * 3 + 1], cur[S.sel * 3 + 2]).applyMatrix4(root.matrixWorld); const [x, y] = project(tmp, camera, W(), H()); ret.style.display = 'block'; ret.style.left = x + 'px'; ret.style.top = y + 'px'; xh.style.display = xv.style.display = 'block'; xh.style.left = xv.style.left = x + 'px'; xh.style.top = xv.style.top = y + 'px'; lead(x, y, t); } else nbLines.visible = false;
  const sk = skins.tick(t); if (sk) paint(sk); skins.frameTime(dt);
  talkFrame(t); renderer.render(scene, camera); if (!TRACE) requestAnimationFrame(frame);
}
// test switch (headless): trace stops the frame loop; a script steps it with __deck.tick(t) and reads __deck.snap() to look for jumps
const TRACE = location.hash.includes('trace');
if (TRACE) window.__deck = { tick: frame, go, lock, live: () => live.snap(), play: ev => live.play(ev), snap: () => ({ prog: S.prog, w: shell.state && [...shell.obj.children[0].material.uniforms.uW.value.toArray()], scanY: scanner.position.y, scanOp: scanner.material.opacity, cam: camera.position.toArray(), lookY: S.lookY, yaw: S.yaw,
  labels: labelEls.map(e => [parseFloat(e.style.left), parseFloat(e.style.top)]), notes: labels.map(l => [parseFloat(l.el.style.left), parseFloat(l.el.style.top)]), ret: S.sel >= 0 ? [parseFloat(ret.style.left), parseFloat(ret.style.top)] : null,
  lead: S.sel >= 0 ? leadL.getAttribute('points') : '' }),
  // the voice path: talk(state) as the page would, ear(an) puts a fake analyser on the mic and the voice, play(on) says whether a clip plays; voice() reads what the shell is driven by
  talk: st => tState(st), ear: an => { S.micAn = S.outAn = an; }, play: on => { S.src = on ? {} : null; },
  voice: () => { const pick = u => Object.fromEntries(Object.entries(u).filter(([, x]) => typeof x.value === 'number').map(([k, x]) => [k, x.value]));
    const u = shell.obj.children[0].material.uniforms; return { lv: S.voiceLv, ...pick(u), pts: shell.obj.children[1].material.uniforms.uGlow.value, col: u.uCol.value.toArray(), hot: u.uHot.value.toArray(), ...Object.fromEntries(Object.entries(pick(cloud.m.uniforms)).filter(([k]) => /^uV|^uShim/.test(k)).map(([k, x]) => ['dot' + k, x])), pulse: notePulse() }; } };
refresh(); if (!TRACE) requestAnimationFrame(frame);
if (location.hash.includes('probe')) window.__dots = () => { const o = []; for (let i = 0; i < N; i++) { if (cloud.A[i] < .5) continue; const [x, y, z] = dotXY(i); if (z <= 1) o.push([i, Math.round(x), Math.round(y)]); } return { dots: o, sel: S.sel, hov: S.hov, pv: pvI, pvDot, reader: readerOpen }; };   // test switch (headless): where the dots are on screen
if (location.hash.includes('still')) document.head.insertAdjacentHTML('beforeend', '<style>#lockp *,#lockp,#reader,#reader *,#pv,#pv *,.ret2 svg,.ret2 .shock{animation:none!important;transition:none!important}.tg-title{min-height:44px}</style>');
const lm = location.hash.match(/lock=(\d+)/); if (lm) setTimeout(() => lock(+lm[1]), 400);
const hv = location.hash.slice(1).replace(/[!~&].*/, ''); if (hv in VIEW) { if (location.hash.includes('!')) { go(hv); S.prog = 1; cur.set(LAY[hv]); cloud.g.attributes.position.needsUpdate = true; S.pitch = S.pT; S.dist = S.dT; S.labelFrom = COLS.map(c => anchors[hv][c].clone()); for (const k in vis) vis[k] = k === hv ? 1 : 0; } else if (location.hash.includes('~')) { S.from = new Float32Array(Lmap); go(hv); S.prog = +location.hash.split('~')[1]; S.hold = true; } else setTimeout(() => go(hv), 600); }
