// Unit tests for app/rules.js (no window needed): crabbox run -- node --test viz/app/test/
'use strict';
const test = require('node:test'), assert = require('node:assert');
const { linkAction, mayLoad, allowPermission, fitBounds } = require('../rules');
const O = 'http://127.0.0.1:8765';

test('the microphone is allowed for the Deck, only the microphone, only for the Deck', () => {
  assert.equal(allowPermission('media', O + '/deck.html', { mediaTypes: ['audio'] }, O), true);
  assert.equal(allowPermission('media', O, { mediaType: 'audio' }, O), true);   // the check before listing the mics
  assert.equal(allowPermission('media', O + '/deck.html', { mediaTypes: ['video'] }, O), false, 'camera');
  assert.equal(allowPermission('media', O + '/deck.html', { mediaTypes: ['audio', 'video'] }, O), false, 'mic + camera together');
  assert.equal(allowPermission('media', O, { mediaType: 'video' }, O), false);
  assert.equal(allowPermission('media', O, { mediaType: 'unknown' }, O), false);
  assert.equal(allowPermission('media', O, { mediaTypes: [] }, O), false);
  assert.equal(allowPermission('media', O, {}, O), false);
  assert.equal(allowPermission('media', O, undefined, O), false);
  for (const url of ['https://example.com/', 'http://127.0.0.1:9999/deck.html', 'http://127.0.0.1.evil.com:8765/', 'file:///etc/passwd', 'not a url'])
    assert.equal(allowPermission('media', url, { mediaTypes: ['audio'] }, O), false, url);
  for (const p of ['notifications', 'geolocation', 'clipboard-read', 'clipboard-sanitized-write', 'display-capture', 'midi', 'midiSysex',
    'fullscreen', 'pointerLock', 'openExternal', 'hid', 'serial', 'usb', 'idle-detection', 'window-management', 'unknown'])
    assert.equal(allowPermission(p, O + '/deck.html', { mediaTypes: ['audio'] }, O), false, p);
});

test('links: the Deck stays, web links go to the browser, the rest is refused', () => {
  assert.equal(linkAction(O + '/deck.html#map', O), 'stay');
  assert.equal(linkAction('http://localhost:8765/deck.html', O), 'stay');
  assert.equal(linkAction('https://example.com/a', O), 'browser');
  assert.equal(linkAction('http://127.0.0.1:9999/', O), 'browser');
  for (const u of ['file:///etc/passwd', 'mailto:a@b.c', 'javascript:alert(1)', 'ssh://host', 'nonsense'])
    assert.equal(linkAction(u, O), 'refuse', u);
});

test('requests: only the Deck server and in-memory data', () => {
  assert.equal(mayLoad(O + '/data.js', O), true);
  assert.equal(mayLoad('data:image/png;base64,AA', O), true);
  assert.equal(mayLoad('blob:http://127.0.0.1:8765/x', O), true);
  for (const u of ['https://fonts.googleapis.com/css', 'http://127.0.0.1:47821/say', 'ws://example.com/'])
    assert.equal(mayLoad(u, O), false, u);
});

test('window memory: saved size and place are made safe', () => {
  const one = [{ x: 0, y: 0, width: 2560, height: 1440 }];
  assert.deepEqual(fitBounds(null, one), { width: 1600, height: 1000 });
  assert.deepEqual(fitBounds({ x: 100, y: 50, width: 1800, height: 1100 }, one), { x: 100, y: 50, width: 1800, height: 1100 });
  assert.deepEqual(fitBounds({ x: 100, y: 50, width: 9000, height: 9000 }, one), { width: 2560, height: 1440 }, 'too big (its middle was off the screen: no place)');
  assert.deepEqual(fitBounds({ x: -200, y: 0, width: 3000, height: 1500 }, one), { x: 0, y: 0, width: 2560, height: 1440 }, 'too big, middle on the screen');
  assert.deepEqual(fitBounds({ x: 10, y: 10, width: 20, height: 20 }, one), { x: 10, y: 10, width: 800, height: 500 }, 'too small');
  assert.deepEqual(fitBounds({ x: 5000, y: 50, width: 1800, height: 1100 }, one), { width: 1800, height: 1100 }, 'screen gone: no place');
  assert.deepEqual(fitBounds({ x: 2500, y: 0, width: 1800, height: 1100 }, [...one, { x: 2560, y: 0, width: 1920, height: 1080 }]),
    { x: 2560, y: 0, width: 1800, height: 1080 }, 'second screen');
  assert.deepEqual(fitBounds({ width: 'x', height: null }, one), { width: 1600, height: 1000 }, 'broken file');
});
