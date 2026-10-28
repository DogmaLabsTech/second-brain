import { KC, RD, S, addLabel, ask, byPath, clamp, clearLabels, editing, leftAway, live, liveNonce, liveOwn, lock, pk, shell } from '../deck-main.js';
// ---- 07 Voice: talk to the brain like the voice island (the TALK button, or hold Space). Mic -> /talk/stt -> /talk/ask
// (first sentence early) -> /talk/say per sentence (Kokoro bm_george), played through an analyser so the shell follows the voice.
const TV = RD('voicep'), TB = RD('tbtn'), MUTE = location.hash.includes('mute'), post = (u, body, sig) => fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Deck': '1' }, body: JSON.stringify(body), signal: sig });
const TSUB = { idle: 'click talk or hold space', listening: 'talk now · click or let go to send', thinking: 'looking in your notes', speaking: 'click or esc to stop', unheard: 'speak closer or louder · check the mic below' };
const TBL = { listening: 'SEND', thinking: 'STOP', speaking: 'STOP' };
let talk = 'idle', tgen = 0, tAbort = null, ac = null, mic = null, rec = null, recBits = [], recMode = '', recAt = 0, heardAt = 0, quietAt = 0; S.micAn = null; S.outAn = null; S.src = null; let sayQ = [], sayChain = null, sayMore = false, pumping = false, tJob = null, tId = '', tFake = '', voiceEv = null;   // voiceEv: the voice answer's live event, held while it speaks
const talkBuf = new Float32Array(2048);   // ~43 ms of sound per reading: a steadier loudness than one short window
export function tState(st, sub) { talk = st; if (st !== 'speaking' && st !== 'thinking' && voiceEv) { live.release(voiceEv); voiceEv = null; }   /* the voice finished (or stopped): its lines fade calmly now */ TV.dataset.s = st; shell.set(st === 'job' || st === 'unheard' ? 'idle' : st); RD('tbl').textContent = TBL[st] || 'TALK'; RD('tstate').textContent = st === 'error' ? 'ERROR' : st === 'job' ? 'WAITING FOR YOU' : st === 'unheard' ? "I DIDN'T HEAR YOU" : st === 'idle' ? 'READY' : st.toUpperCase(); RD('tsub').textContent = sub ?? TSUB[st] ?? ''; RD('tsub').title = RD('tsub').textContent; }
function tErr(t) { tState('error', t); }
export const notePulse = () => shell.voice * 1.1;   // the answer's notes pulse with the voice
const audio = () => ac || (ac = new AudioContext());
function rms(an) { an.getFloatTimeDomainData(talkBuf); let a = 0; for (let k = 0; k < talkBuf.length; k++) a += talkBuf[k] * talkBuf[k]; return Math.sqrt(a / talkBuf.length); }
const LVI = RD('tlvi'), LVB = RD('tlv'); let floor = .2, lvShown = -1, barLv = 0, barT = 0;   // floor: the room's noise level, so a quiet mic still counts as talking above it
// soft(): the loudness as the shell feels it: a soft knee at the bottom (room noise doesn't flicker) and a soft top (a loud word doesn't slam to the max)
const soft = x => { x = x < -.1 ? 0 : x < .1 ? (x + .1) * (x + .1) / .4 : x; return clamp((1 - Math.exp(-1.8 * x)) / (1 - Math.exp(-1.8))); };
export function talkFrame(t) { let lv = 0, felt = 0;
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
