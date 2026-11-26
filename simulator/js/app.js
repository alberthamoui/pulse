// The page around the device: draws the OLED, turns clicks, taps and keys into button
// presses, and runs the panel that controls the simulated Spotify.
(function () {
  'use strict';

  const L = window.LIBRARY;
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const prefs = {
    get(key, fallback) {
      try { return localStorage.getItem(`pulse-sim/${key}`) || fallback; } catch (e) { return fallback; }
    },
    set(key, value) {
      try { localStorage.setItem(`pulse-sim/${key}`, value); } catch (e) { /* not remembered */ }
    },
  };

  const cloud = new window.Cloud();
  const stage = $('#stage');

  // ---- OLED ------------------------------------------------------------------

  const SCALE = 4; // canvas pixels per OLED pixel
  const DOT = 3.4; // lit area of each pixel, the rest is the gap between pixels
  const frame = new Uint8Array(window.OLED_WIDTH * window.OLED_HEIGHT);
  const screens = $$('canvas.oled').map((c) => c.getContext('2d'));
  let framePending = false;

  function drawFrame() {
    framePending = false;
    for (const ctx of screens) {
      ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
      ctx.fillStyle = '#5ee8ff';
      for (let y = 0; y < window.OLED_HEIGHT; y++) {
        for (let x = 0; x < window.OLED_WIDTH; x++) {
          if (frame[y * window.OLED_WIDTH + x]) ctx.fillRect(x * SCALE + 0.3, y * SCALE + 0.3, DOT, DOT);
        }
      }
    }
  }

  // ---- Serial monitor -----------------------------------------------------------

  const serial = $('#serial');
  const MAX_LINES = 600;

  function serialLine(line, ms) {
    const row = document.createElement('div');
    const t = document.createElement('span');
    t.className = 't';
    t.textContent = `${(ms / 1000).toFixed(3).padStart(8)}  `;
    const text = document.createElement('span');
    text.textContent = line;
    if (line.startsWith('[sm]')) text.className = 'sm';
    if (/failed|error|refused|lost|giving up|interrupted|401|429/.test(line)) text.className = 'err';
    row.append(t, text);

    const atBottom = serial.scrollHeight - serial.scrollTop - serial.clientHeight < 24;
    serial.append(row);
    while (serial.childElementCount > MAX_LINES) serial.firstElementChild.remove();
    if (atBottom) serial.scrollTop = serial.scrollHeight;
  }

  $('#serial-clear').addEventListener('click', () => { serial.textContent = ''; });

  // ---- Device ------------------------------------------------------------------

  const device = new window.PulseDevice(cloud, {
    onFrame(buffer) {
      frame.set(buffer);
      if (!framePending) {
        framePending = true;
        requestAnimationFrame(drawFrame);
      }
    },
    onSerial(line, ms) {
      serialLine(line, ms);
      if (line.startsWith('[profiles]')) schedulePlaylists();
    },
    onState(state) {
      for (const li of $$('.states li')) li.classList.toggle('on', li.dataset.state === state);
    },
    onPower(on) {
      stage.classList.toggle('off', !on);
      if (!on) for (const li of $$('.states li')) li.classList.remove('on');
    },
  });

  // ---- Buttons ------------------------------------------------------------------

  // A click or tap can be shorter than the firmware's 30 ms debounce, which a real
  // button never is. Each pin replays the presses in order, down for at least
  // MIN_PRESS_MS and up for at least MIN_GAP_MS, so quick clicks all count.
  const MIN_PRESS_MS = 80;
  const MIN_GAP_MS = 50;
  const held = { nav: false, ok: false }; // what the user is doing right now
  const nextAt = {};
  const timers = new Set();

  function setPin(pin, pressed) {
    if (held[pin] === pressed) return;
    held[pin] = pressed;
    const now = performance.now();
    const at = Math.max(now, nextAt[pin] || 0);
    nextAt[pin] = at + (pressed ? MIN_PRESS_MS : MIN_GAP_MS);
    const apply = () => {
      device.press(pin, pressed);
      for (const el of $$(`[data-pin="${pin}"]`)) el.classList.toggle('down', pressed);
    };
    if (at <= now) {
      apply();
    } else {
      const t = setTimeout(() => { timers.delete(t); apply(); }, at - now);
      timers.add(t);
    }
  }

  function releaseAll() {
    for (const t of timers) clearTimeout(t);
    timers.clear();
    for (const pin of ['nav', 'ok']) {
      held[pin] = false;
      nextAt[pin] = 0;
      device.press(pin, false);
      for (const el of $$(`[data-pin="${pin}"]`)) el.classList.remove('down');
    }
  }

  for (const el of $$('[data-pin]')) {
    const pin = el.dataset.pin;
    el.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation(); // not a drag of the 3D case
      setPin(pin, true);
      try {
        el.setPointerCapture(e.pointerId); // keeps the release even if the pointer slides off
      } catch (err) {
        // pointer already gone: pointerup on the button still releases it
      }
    });
    const release = () => setPin(pin, false);
    el.addEventListener('pointerup', release);
    el.addEventListener('pointercancel', release);
    el.addEventListener('lostpointercapture', release);
    el.addEventListener('contextmenu', (e) => e.preventDefault());
    // Space/Enter on a focused button: the press lasts as long as the key is held
    el.addEventListener('keydown', (e) => {
      if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) { e.preventDefault(); e.stopPropagation(); setPin(pin, true); }
    });
    el.addEventListener('keyup', (e) => {
      if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); setPin(pin, false); }
    });
  }

  // N/O always work; arrows, Enter and Space only when no control of the page has focus
  function keyPin(e) {
    const key = e.key.toLowerCase();
    if (key === 'n') return 'nav';
    if (key === 'o') return 'ok';
    if (e.target.closest('input, button, select, textarea, summary, [role="radio"]')) return null;
    if (key === 'arrowdown' || key === 'arrowright') return 'nav';
    if (key === 'enter' || key === ' ') return 'ok';
    return null;
  }

  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const pin = keyPin(e);
    if (!pin) return;
    e.preventDefault();
    if (!e.repeat) setPin(pin, true);
  });
  document.addEventListener('keyup', (e) => {
    const pin = keyPin(e);
    if (pin) setPin(pin, false);
  });
  window.addEventListener('blur', () => { setPin('nav', false); setPin('ok', false); });

  // ---- Model tabs -------------------------------------------------------------------

  function showModel(model) {
    for (const tab of $$('.models button')) tab.setAttribute('aria-selected', String(tab.dataset.model === model));
    $('#model-proto').classList.toggle('active', model === 'proto');
    $('#model-product').classList.toggle('active', model === 'product');
    stage.setAttribute('aria-labelledby', model === 'proto' ? 'tab-proto' : 'tab-product');
    prefs.set('model', model);
    if (location.hash !== `#${model}`) history.replaceState(null, '', `#${model}`);
    fitProduct();
  }

  for (const tab of $$('.models button')) tab.addEventListener('click', () => showModel(tab.dataset.model));

  // ---- Final product: size, finish and drag to turn ------------------------------------

  const product = $('#model-product');
  const scene = $('#scene');
  const box = $('#box');
  const DEFAULT_TURN = { rx: -16, ry: -26 };
  const turn = { ...DEFAULT_TURN };

  function fitProduct() {
    const width = stage.clientWidth;
    // Room for the case turned to either side
    if (width) product.style.setProperty('--s', Math.min(1.3, width / 720).toFixed(3));
  }
  new ResizeObserver(fitProduct).observe(stage);

  function applyTurn() {
    box.style.setProperty('--rx', `${turn.rx}deg`);
    box.style.setProperty('--ry', `${turn.ry}deg`);
  }

  let drag = null;
  scene.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    drag = { x: e.clientX, y: e.clientY, rx: turn.rx, ry: turn.ry };
    scene.setPointerCapture(e.pointerId);
    scene.classList.add('dragging');
  });
  scene.addEventListener('pointermove', (e) => {
    if (!drag) return;
    turn.ry = Math.max(-70, Math.min(70, drag.ry + (e.clientX - drag.x) * 0.35));
    turn.rx = Math.max(-40, Math.min(8, drag.rx - (e.clientY - drag.y) * 0.25));
    applyTurn();
  });
  const endDrag = () => { drag = null; scene.classList.remove('dragging'); };
  scene.addEventListener('pointerup', endDrag);
  scene.addEventListener('pointercancel', endDrag);
  scene.addEventListener('dblclick', () => { Object.assign(turn, DEFAULT_TURN); applyTurn(); });

  function setFinish(finish) {
    box.classList.remove('graphite', 'bone', 'sage');
    box.classList.add(finish);
    for (const b of $$('.finishes button')) b.setAttribute('aria-checked', String(b.dataset.finish === finish));
    prefs.set('finish', finish);
  }
  for (const b of $$('.finishes button')) b.addEventListener('click', () => setFinish(b.dataset.finish));

  // ---- Panel: song ----------------------------------------------------------------------

  const songs = $('#songs');
  for (const song of L.SONGS) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'song';
    b.setAttribute('role', 'radio');
    b.dataset.id = song.id;
    const title = document.createElement('b');
    title.textContent = song.name;
    if (song.artist && !song.none) {
      const artist = document.createElement('em');
      artist.textContent = ` · ${song.artist}`;
      title.append(artist);
    }
    const hint = document.createElement('small');
    hint.textContent = song.hint;
    b.append(title, hint);
    b.addEventListener('click', () => cloud.set('playing', song.id));
    songs.append(b);
  }

  function renderSongs() {
    for (const b of $$('.song', songs)) b.setAttribute('aria-checked', String(b.dataset.id === cloud.state.playing));
  }

  // ---- Panel: conditions ----------------------------------------------------------------

  for (const key of ['wifi', 'lastfm', 'fallback']) {
    $(`#opt-${key}`).addEventListener('change', (e) => cloud.set(key, e.target.checked));
  }
  for (const b of $$('#opt-api button')) b.addEventListener('click', () => cloud.set('api', b.dataset.value));

  function renderConditions() {
    for (const key of ['wifi', 'lastfm', 'fallback']) $(`#opt-${key}`).checked = cloud.state[key];
    for (const b of $$('#opt-api button')) b.setAttribute('aria-checked', String(b.dataset.value === cloud.state.api));
  }

  // ---- Panel: playlists ---------------------------------------------------------------

  const list = $('#playlists');
  let playlistsPending = false;
  let highlight = null;

  function schedulePlaylists() {
    if (playlistsPending) return;
    playlistsPending = true;
    requestAnimationFrame(renderPlaylists);
  }

  function playlistStatus(p) {
    if (p.owner !== L.USER.id && !p.collaborative) return ['ignored', 'Ignored: followed, not yours'];
    const files = device.flash ? device.flash.files : {};
    const f = files[p.id];
    if (!f) return ['stale', 'Not on the device yet: read on the next sync'];
    if (f.snapshot !== cloud.snapshotOf(p)) return ['stale', 'Changed on Spotify: re-read on the next sync'];
    const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
    return ['ok', `On the device · ${plural(f.artists.length, 'artist')}, ${plural(f.total, 'track')}`];
  }

  function renderPlaylists() {
    playlistsPending = false;
    list.textContent = '';
    for (const p of cloud.state.playlists) {
      const li = document.createElement('li');
      const name = document.createElement('span');
      name.className = 'name';
      name.textContent = p.name;
      if (p.id === L.FALLBACK_ID && cloud.state.fallback) name.append(badge('fallback'));
      if (p.collaborative) name.append(badge('collab'));
      const count = document.createElement('span');
      count.className = 'count';
      count.textContent = `${p.tracks.length} tracks`;
      const [kind, text] = playlistStatus(p);
      const status = document.createElement('span');
      status.className = `status ${kind}`;
      status.textContent = text;
      li.append(name, count, status);
      if (p.id === highlight) {
        li.classList.add('flash');
        requestAnimationFrame(() => requestAnimationFrame(() => li.classList.remove('flash')));
      }
      list.append(li);
    }
    highlight = null;
  }

  function badge(text) {
    const b = document.createElement('span');
    b.className = 'badge';
    b.textContent = text;
    return b;
  }

  // ---- Panel: actions -----------------------------------------------------------------

  function restart() {
    releaseAll();
    device.powerOff();
    setTimeout(() => device.powerOn(), 450);
  }

  $('#act-restart').addEventListener('click', restart);
  $('#act-edit').addEventListener('click', () => cloud.editElsewhere());
  $('#act-reset').addEventListener('click', () => {
    if (!window.confirm('Erase the device’s flash and restore the example playlists?')) return;
    window.PulseFlash.erase();
    cloud.reset();
    serial.textContent = '';
    restart();
  });

  // ---- Start -----------------------------------------------------------------------------

  cloud.onChange((detail) => {
    highlight = detail.added || detail.edited || highlight;
    renderSongs();
    renderConditions();
    schedulePlaylists();
  });

  const fromHash = location.hash.replace('#', '');
  showModel(['proto', 'product'].includes(fromHash) ? fromHash : prefs.get('model', 'proto'));
  window.addEventListener('hashchange', () => {
    const model = location.hash.replace('#', '');
    if (['proto', 'product'].includes(model)) showModel(model);
  });
  setFinish(prefs.get('finish', 'graphite'));
  applyTurn();
  renderSongs();
  renderConditions();
  renderPlaylists();
  device.powerOn();
  requestAnimationFrame(() => requestAnimationFrame(() => scene.classList.add('ready')));
  window.pulseSim = { device, cloud }; // for poking at it from the console
})();
