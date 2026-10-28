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

module.exports = { isDeck, linkAction, mayLoad };
