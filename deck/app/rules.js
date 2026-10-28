// What the Deck's window lets through (plain functions, so app/test/ can check them without a window).
'use strict';

// the Deck's own address: exactly http://127.0.0.1:<port> (the server's Host check also takes localhost)
const isDeck = (url, origin) => { try { const u = new URL(url); return u.origin === origin || u.origin === origin.replace('127.0.0.1', 'localhost'); } catch { return false; } };

// a link or a navigation: 'stay' (the Deck's own pages), 'browser' (a web link: the normal browser opens it), 'refuse' (anything else)
function linkAction(url, origin) {
  if (isDeck(url, origin)) return 'stay';
  try { return /^https?:$/.test(new URL(url).protocol) ? 'browser' : 'refuse'; } catch { return 'refuse'; }
}

// a request the page makes: only the Deck's own server, plus the page's in-memory data: and blob: addresses; nothing leaves the computer
const mayLoad = (url, origin) => isDeck(url, origin) || /^(data|blob|devtools):/.test(url);

// a permission the page asks for (or checks): only the microphone, only for the Deck's own address. Camera, screen, notifications,
// location, clipboard, MIDI and the rest are refused. details: Electron's { mediaTypes } (a request) or { mediaType } (a check).
function allowPermission(permission, url, details, origin) {
  if (permission !== 'media' || !isDeck(url, origin)) return false;
  const kinds = details && (details.mediaTypes || (details.mediaType ? [details.mediaType] : []));
  return Array.isArray(kinds) && kinds.length > 0 && kinds.every(k => k === 'audio');
}

// the saved window size and place, made safe: at least 800x500, no bigger than the screen it was on, and the place only if the
// window's middle is still on one of today's screens (else the desktop places it). On Wayland Hyprland decides the place anyway.
function fitBounds(saved, areas) {
  const out = { width: 1600, height: 1000 };
  if (!saved || !Array.isArray(areas) || !areas.length) return out;
  const n = v => Number.isFinite(v) ? Math.round(v) : null, w = n(saved.width), h = n(saved.height), x = n(saved.x), y = n(saved.y);
  const on = x !== null && y !== null && w && h ? areas.find(a => x + w / 2 >= a.x && x + w / 2 < a.x + a.width && y + h / 2 >= a.y && y + h / 2 < a.y + a.height) : null;
  const room = on || areas.reduce((a, b) => a.width * a.height >= b.width * b.height ? a : b);
  if (w) out.width = Math.max(800, Math.min(w, room.width));
  if (h) out.height = Math.max(500, Math.min(h, room.height));
  if (on) { out.x = Math.max(on.x, Math.min(x, on.x + on.width - out.width)); out.y = Math.max(on.y, Math.min(y, on.y + on.height - out.height)); }
  return out;
}

module.exports = { isDeck, linkAction, mayLoad, allowPermission, fitBounds };
