// The Pulse firmware, ported line by line from firmware/src to run in the browser.
// Each class below mirrors one file (buttons.cpp, display.cpp, profiles.cpp, ...), with
// the same timings, texts, Serial logs and C arithmetic (integer division, 32-bit float).
// What the ESP32 gets from the outside world (Wi-Fi, Spotify, Last.fm) comes from
// js/cloud.js instead, and LittleFS is kept in localStorage.
(function () {
  'use strict';

  const cfg = window.cfg;
  const L = window.LIBRARY;

  const FLASH_KEY = 'pulse-sim/flash';
  const WIFI_SSID = 'home-2.4G';

  class PowerOff extends Error {}

  // ---- C helpers -------------------------------------------------------------------

  const idiv = (a, b) => Math.trunc(a / b); // int / int
  const f32 = Math.fround;                   // float
  const utf8 = new TextEncoder();

  // strcasecmp over the UTF-8 bytes, like on the ESP32
  function strcasecmp(a, b) {
    const x = utf8.encode(a);
    const y = utf8.encode(b);
    const lower = (c) => (c >= 65 && c <= 90 ? c + 32 : c);
    for (let i = 0; ; i++) {
      const c1 = i < x.length ? lower(x[i]) : 0;
      const c2 = i < y.length ? lower(y[i]) : 0;
      if (c1 !== c2 || c1 === 0) return c1 - c2;
    }
  }

  // ---- backend.h / backend.cpp -----------------------------------------------------

  function errorMessage(err) {
    switch (err) {
      case 'None': return '';
      case 'NoWifi': return 'No Wi-Fi';
      case 'NothingPlaying': return 'Nothing playing';
      case 'LocalFile': return 'Local file';
      case 'NoPlaylists': return 'No playlists';
      case 'RateLimited': return 'API busy';
      case 'AuthExpired': return 'Reauthorize';
      default: return 'API error';
    }
  }

  function errorDetail(err) {
    switch (err) {
      case 'LocalFile': return 'not in catalog';
      case 'AuthExpired': return 'get_refresh_token.py';
      default: return '';
    }
  }

  function candidate(fields) {
    return { playlistId: '', name: '', weight: 0, hasTrack: false, similar: false, kind: 'Playlist', ...fields };
  }

  // ---- buttons.cpp -----------------------------------------------------------------

  class Buttons {
    constructor(dev) {
      this.dev = dev;
      const button = (pin) => ({ pin, raw: false, stable: false, rawSince: 0, pressedAt: 0, holdFired: false, suppressed: false });
      this.nav = button('nav');
      this.ok = button('ok');
      this.pending = 'None';
    }

    digitalReadLow(b) { return this.dev.pins[b.pin]; }

    begin() { this.suppressUntilRelease(); }

    update(b, now) {
      const raw = this.digitalReadLow(b);
      if (raw !== b.raw) {
        b.raw = raw;
        b.rawSince = now;
      }
      if (now - b.rawSince < cfg.DEBOUNCE_MS) return 0;

      if (b.raw === b.stable) {
        if (!b.stable) b.suppressed = false;
        return 0;
      }

      b.stable = b.raw;
      if (b.stable) {
        b.pressedAt = now;
        b.holdFired = false;
        return 1;
      }
      return -1;
    }

    poll() {
      if (this.pending !== 'None') {
        const ev = this.pending;
        this.pending = 'None';
        return ev;
      }

      const now = this.dev.millis();
      let navEv = 'None';
      let okEv = 'None';

      let edge = this.update(this.nav, now);
      if (edge > 0 && !this.nav.suppressed) navEv = 'NavPress';
      if (edge < 0) this.nav.suppressed = false;

      edge = this.update(this.ok, now);
      if (edge < 0) {
        if (!this.ok.suppressed && !this.ok.holdFired) okEv = 'OkClick';
        this.ok.suppressed = false;
      } else if (this.ok.stable && !this.ok.suppressed && !this.ok.holdFired &&
                 now - this.ok.pressedAt >= cfg.HOLD_RESYNC_MS) {
        this.ok.holdFired = true;
        okEv = 'OkHold';
      }

      if (navEv !== 'None') {
        this.pending = okEv;
        return navEv;
      }
      return okEv;
    }

    suppressUntilRelease() {
      for (const b of [this.nav, this.ok]) b.suppressed = b.stable || this.digitalReadLow(b);
      this.pending = 'None';
    }
  }

  // ---- display.cpp -----------------------------------------------------------------

  const FONT_BIG = 'u8g2_font_logisoso24_tr';
  const FONT_TEXT = 'u8g2_font_6x10_tf';
  const FONT_SMALL = 'u8g2_font_5x7_tf';
  const WIDTH = 128;
  const ROW_H = 10;
  const LIST_TOP = 21;
  const SCROLLBAR_W = 3;

  function marqueeOffset(overflow, elapsedMs) {
    const scrollMs = Math.floor(overflow * 1000 / cfg.SCROLL_PX_PER_S);
    const cycle = cfg.SCROLL_PAUSE_MS + scrollMs + cfg.SCROLL_PAUSE_MS;
    let t = elapsedMs % cycle;
    if (t < cfg.SCROLL_PAUSE_MS) return 0;
    t -= cfg.SCROLL_PAUSE_MS;
    if (t < scrollMs) return Math.floor(t * cfg.SCROLL_PX_PER_S / 1000);
    return overflow;
  }

  class Display {
    constructor(u8g2) { this.u8g2 = u8g2; }

    begin() {
      this.u8g2.setMaxClipWindow();
      this.u8g2.setFontMode(1);
    }

    drawClipped(x, y, w, top, bottom, text, scroll, elapsedMs) {
      const u = this.u8g2;
      const overflow = u.getUTF8Width(text) - w;
      if (overflow <= 0) {
        u.drawUTF8(x, y, text);
        return false;
      }
      const offset = scroll ? marqueeOffset(overflow, elapsedMs) : 0;
      u.setClipWindow(x, top, x + w, bottom);
      u.drawUTF8(x - offset, y, text);
      u.setMaxClipWindow();
      return scroll;
    }

    idle() {
      const u = this.u8g2;
      u.clearBuffer();
      u.setFont(FONT_BIG);
      const title = 'PULSE';
      u.drawStr(idiv(WIDTH - u.getStrWidth(title), 2), 44, title);
      u.sendBuffer();
    }

    progress(label, pct) {
      const u = this.u8g2;
      if (pct > 100) pct = 100;
      u.clearBuffer();
      u.setFont(FONT_TEXT);
      u.drawUTF8(idiv(WIDTH - u.getUTF8Width(label), 2), 26, label);
      u.drawFrame(14, 34, 100, 10);
      u.drawBox(16, 36, idiv(96 * pct, 100), 6);
      u.sendBuffer();
    }

    select(track, items, manual, selected, first, elapsedMs) {
      const u = this.u8g2;
      let animating = false;
      u.clearBuffer();

      u.setFont(FONT_TEXT);
      animating = this.drawClipped(0, 8, WIDTH, 0, 10, track.name, true, elapsedMs) || animating;
      u.setFont(FONT_SMALL);
      animating = this.drawClipped(0, 17, WIDTH, 10, 18, track.artistName, true, elapsedMs) || animating;
      u.drawHLine(0, 19, WIDTH);

      const hasScrollbar = items.length > cfg.LIST_ROWS;
      const rowW = hasScrollbar ? WIDTH - SCROLLBAR_W : WIDTH;

      u.setFont(FONT_TEXT);
      for (let i = 0; i < cfg.LIST_ROWS && first + i < items.length; ++i) {
        const idx = first + i;
        const item = items[idx];
        const isSel = idx === selected;
        const top = LIST_TOP + i * ROW_H;
        const baseline = top + 8;

        if (isSel) {
          u.drawBox(0, top, rowW, ROW_H);
          u.setDrawColor(0);
        }

        let nameW = rowW - 4;
        let tag = '';
        if (item.hasTrack) {
          tag = 'in';
        } else if (!manual && item.kind === 'Playlist') {
          const prefix = item.similar ? '~' : '';
          const p = Math.min(999, Math.trunc(f32(f32(item.weight * 100) + 0.5)));
          tag = p < 1 ? `${prefix}<1%` : `${prefix}${p}%`;
        }
        if (tag !== '') {
          const tagW = u.getUTF8Width(tag);
          u.drawUTF8(rowW - 2 - tagW, baseline, tag);
          nameW -= tagW + 4;
        }
        animating = this.drawClipped(2, baseline, nameW, top, top + ROW_H, item.name, isSel, elapsedMs) || animating;
        u.setDrawColor(1);
      }

      if (hasScrollbar) {
        const trackH = cfg.LIST_ROWS * ROW_H;
        const thumbH = Math.max(3, Math.floor(trackH * cfg.LIST_ROWS / items.length));
        const thumbY = LIST_TOP + idiv((trackH - thumbH) * first, items.length - cfg.LIST_ROWS);
        u.drawBox(WIDTH - 2, thumbY, 2, thumbH);
      }

      u.sendBuffer();
      return animating;
    }

    message(line1, line2, elapsedMs) {
      const u = this.u8g2;
      let animating = false;
      u.clearBuffer();
      u.setFont(FONT_TEXT);

      const centered = (text, y) => {
        const w = u.getUTF8Width(text);
        if (w <= WIDTH - 4) {
          u.drawUTF8(idiv(WIDTH - w, 2), y, text);
        } else {
          animating = this.drawClipped(2, y, WIDTH - 4, y - 9, y + 2, text, true, elapsedMs) || animating;
        }
      };

      const twoLines = line2 !== null && line2 !== undefined && line2 !== '';
      centered(line1, twoLines ? 26 : 36);
      if (twoLines) centered(line2, 44);

      u.sendBuffer();
      return animating;
    }
  }

  // ---- LittleFS --------------------------------------------------------------------

  // The profiles the firmware keeps in /p/<id>.txt, one object per file
  class Flash {
    constructor() {
      const saved = window.simStorage.read(FLASH_KEY);
      this.files = saved && saved.p ? saved.p : {};
    }

    save() { window.simStorage.write(FLASH_KEY, { p: this.files }); }

    static erase() { window.simStorage.write(FLASH_KEY, { p: {} }); }
  }

  // ---- spotify_client.cpp ----------------------------------------------------------

  class SpotifyClient {
    constructor(dev) {
      this.dev = dev;
      this.hasToken = false;
    }

    get cloud() { return this.dev.cloud; }

    async refreshAccessToken() {
      this.hasToken = false;
      if (!this.cloud.state.wifi) return 'NoWifi';
      await this.dev.delay(this.cloud.latency(200, 400));
      if (!this.cloud.state.wifi) return 'NoWifi';
      if (this.cloud.state.api === 'auth') {
        this.dev.log('[auth] failed to refresh the token: HTTP 400 {"error":"invalid_grant","error_description":"Refresh token revoked"}');
        return 'AuthExpired';
      }
      this.hasToken = true;
      this.dev.log('[auth] access token refreshed (expires in 3600s)');
      return 'None';
    }

    async ensureToken() {
      return this.hasToken ? 'None' : this.refreshAccessToken();
    }

    // respond() plays the part of api.spotify.com; returns { err, status, data }
    async call(method, url, respond) {
      const tokenErr = await this.ensureToken();
      if (tokenErr !== 'None') return { err: tokenErr, status: 0 };

      await this.dev.delay(this.cloud.latency(150, 380));
      if (!this.cloud.state.wifi) {
        this.dev.log(`[api] ${method} ${url}: connection lost`);
        return { err: 'NoWifi', status: -1 };
      }
      if (this.cloud.state.api === 'auth') {
        // The access token was revoked along with the refresh token
        this.dev.log('[api] 401: refreshing the token and retrying');
        const err = await this.refreshAccessToken();
        return { err: err === 'None' ? 'Api' : err, status: 401 };
      }
      if (this.cloud.state.api === 'rate') {
        this.dev.log('[api] 429: Retry-After of 90s, giving up');
        return { err: 'RateLimited', status: 429 };
      }

      const data = respond();
      const status = data.status || 200;
      if (status < 200 || status >= 300) {
        this.dev.log(`[api] ${method} ${url}: HTTP ${status} {"error":{"status":${status}}}`);
        return { err: 'Api', status, data };
      }
      return { err: 'None', status, data };
    }

    async getMe() {
      const r = await this.call('GET', '/me', () => this.cloud.getMe());
      if (r.err !== 'None') return { err: r.err };
      const user = { id: r.data.id || '', displayName: r.data.display_name || '' };
      if (user.displayName === '') user.displayName = user.id;
      return { err: user.id === '' ? 'Api' : 'None', user };
    }
  }

  // ---- lastfm.cpp ------------------------------------------------------------------

  async function fetchSimilarArtists(dev, artist) {
    const cloud = dev.cloud;
    if (!cloud.state.lastfm || artist === '' || !cloud.state.wifi) return null;
    await dev.delay(cloud.latency(300, 600));
    const doc = cloud.similarArtists(artist, cfg.LASTFM_SIMILAR_LIMIT);
    if (doc.error !== undefined) {
      dev.log(`[lastfm] error ${doc.error}: ${doc.message}`);
      return null;
    }
    const out = doc.artists.filter((a) => a.name !== '' && a.match > 0)
      .map((a) => ({ name: a.name, match: f32(a.match) }));
    dev.log(`[lastfm] ${out.length} artists similar to ${artist}`);
    return out.length > 0 ? out : null;
  }

  // ---- profiles.cpp ----------------------------------------------------------------

  const FORMAT_TAG = 'PULSE3';

  function selectCandidates(ranked, maxCount) {
    let matches = ranked.filter((c) => c.weight > 0);
    if (matches.length === 0) {
      ranked.sort((a, b) => strcasecmp(a.name, b.name));
      return false;
    }
    matches = matches.map((c, i) => [c, i])
      .sort((a, b) => b[0].weight - a[0].weight || a[1] - b[1]) // stable_sort
      .map(([c]) => c);
    if (matches.length > maxCount) matches.length = maxCount;
    ranked.splice(0, ranked.length, ...matches);
    return true;
  }

  class Profiles {
    constructor(dev, client) {
      this.dev = dev;
      this.client = client;
      this.flash = dev.flash;
      this.userId = '';
      this.playlists = [];
    }

    begin() {
      for (const id of Object.keys(this.flash.files)) {
        const p = this.readHeader(id);
        if (p) this.playlists.push(p);
      }
      this.dev.log(`[profiles] ${this.playlists.length} playlists in the cache`);
    }

    setUserId(id) { this.userId = id; }

    readHeader(id) {
      const f = this.flash.files[id];
      if (!f || f.tag !== FORMAT_TAG || f.snapshot === '') return null;
      return { id, name: f.name, snapshot: f.snapshot, total: f.total, apiTotal: 0 };
    }

    write(p, counts, tracks) {
      // std::map: the "a" lines come out sorted by artist id
      const artists = [...counts.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1))
        .map(([id, a]) => [id, a.n, a.name]);
      this.flash.files[p.id] = { tag: FORMAT_TAG, snapshot: p.snapshot, name: p.name, total: p.total, artists, tracks };
      this.flash.save();
      return true;
    }

    async fetchPlaylists(out) {
      for (let offset = 0; ; offset += cfg.PAGE_LIMIT) {
        const url = `/me/playlists?limit=${cfg.PAGE_LIMIT}&offset=${offset}`;
        const r = await this.client.call('GET', url, () => this.dev.cloud.listPlaylists(offset, cfg.PAGE_LIMIT));
        if (r.err !== 'None') return r.err;

        for (const p of r.data.items) {
          const mine = this.userId === p.owner.id;
          if (!mine && !p.collaborative) continue;
          const pl = { id: p.id, name: p.name, snapshot: p.snapshot_id, total: 0, apiTotal: p.items.total };
          if (pl.id !== '' && !out.some((o) => o.id === pl.id)) out.push(pl);
        }
        if (r.data.next === null) break;
      }
      return 'None';
    }

    async build(p, done, toFetch, progress) {
      this.dev.log(`[profiles] reading '${p.name}' (${p.apiTotal} tracks)`);
      const counts = new Map();
      const tracks = [];
      let total = 0;
      let status = 0;

      for (let offset = 0; ; offset += cfg.PAGE_LIMIT) {
        const url = `/playlists/${p.id}/items?limit=${cfg.PAGE_LIMIT}&offset=${offset}&fields=next,items(item(id,artists(id,name)))`;
        const r = await this.client.call('GET', url, () => this.dev.cloud.playlistItems(p.id, offset, cfg.PAGE_LIMIT));
        status = r.status;
        if (r.err !== 'None') return { err: r.err, status };

        for (const it of r.data.items) {
          const track = it.item;
          if (!track) continue;
          if (track.id) tracks.push(track.id);
          const artist = track.artists[0];
          if (!artist || !artist.id) continue;
          let a = counts.get(artist.id);
          if (!a) counts.set(artist.id, (a = { n: 0, name: artist.name }));
          a.n++;
          ++total;
        }

        done.value += r.data.items.length;
        if (toFetch > 0) progress(Math.min(99, Math.floor(done.value * 100 / toFetch)));
        if (r.data.next === null) break;
      }

      p.total = total;
      this.write(p, counts, tracks);
      this.dev.log(`[profiles] '${p.name}': ${total} tracks, ${counts.size} artists`);
      return { err: 'None', status };
    }

    removeStale() {
      for (const id of Object.keys(this.flash.files)) {
        if (!this.playlists.some((p) => p.id === id)) {
          delete this.flash.files[id];
          this.dev.log(`[profiles] removed /p/${id}.txt`);
        }
      }
      this.flash.save();
    }

    async sync(force, progress) {
      const start = this.dev.millis();
      progress(0);

      if (this.userId === '') {
        const me = await this.client.getMe();
        if (me.err !== 'None') return me.err;
        this.userId = me.user.id;
      }

      const fresh = [];
      let err = await this.fetchPlaylists(fresh);
      if (err !== 'None') return err;

      const rebuild = fresh.map(() => false);
      let toFetch = 0;
      let toRebuild = 0;
      fresh.forEach((p, i) => {
        const cached = this.readHeader(p.id);
        if (!force && cached && cached.snapshot === p.snapshot) {
          p.total = cached.total;
        } else {
          rebuild[i] = true;
          toFetch += p.apiTotal;
          ++toRebuild;
        }
      });
      this.dev.log(`[profiles] ${fresh.length} playlists, ${toRebuild} to rebuild (${toFetch} tracks)`);

      const kept = [];
      const keepOld = (p) => {
        const cached = this.readHeader(p.id);
        if (cached) {
          cached.name = p.name;
          kept.push(cached);
        }
      };

      const done = { value: 0 };
      let rebuilt = 0;
      for (let i = 0; i < fresh.length; ++i) {
        if (!rebuild[i]) {
          kept.push(fresh[i]);
          continue;
        }
        if (err !== 'None') {
          keepOld(fresh[i]);
          continue;
        }

        const r = await this.build(fresh[i], done, toFetch, progress);
        if (r.err === 'None') {
          kept.push(fresh[i]);
          ++rebuilt;
        } else if (r.status === 403) {
          this.dev.log(`[profiles] no access to '${fresh[i].name}', skipped`);
        } else if (r.err === 'RateLimited' || r.err === 'NoWifi' || r.err === 'AuthExpired') {
          this.dev.log('[profiles] sync interrupted');
          err = r.err;
          keepOld(fresh[i]);
        } else {
          this.dev.log(`[profiles] failed on '${fresh[i].name}', keeping the previous profile`);
          keepOld(fresh[i]);
        }
      }

      this.playlists = kept;
      this.removeStale();
      progress(100);
      this.dev.log(`[profiles] ${this.playlists.length} playlists ready, ${rebuilt} rebuilt, in ${((this.dev.millis() - start) / 1000).toFixed(1)}s`);
      return err;
    }

    weights(track) {
      return this.playlists.map((p) => {
        const c = candidate({ playlistId: p.id, name: p.name });
        const f = this.flash.files[p.id];
        if (f) {
          const artist = f.artists.find((a) => a[0] === track.artistId);
          const count = artist ? artist[1] : 0;
          c.hasTrack = track.trackId !== '' && f.tracks.includes(track.trackId);
          if (p.total > 0) c.weight = f32(count / p.total);
        }
        return c;
      });
    }

    recordAdd(playlistId, track, snapshot) {
      const entry = this.playlists.find((p) => p.id === playlistId);
      if (!entry) return;
      const f = this.flash.files[playlistId];
      const p = this.readHeader(playlistId);
      if (!f || !p) return;

      const counts = new Map(f.artists.map(([id, n, name]) => [id, { n, name }]));
      if (track.artistId !== '') {
        let a = counts.get(track.artistId);
        if (!a) counts.set(track.artistId, (a = { n: 0, name: track.artistName }));
        a.n++;
        ++p.total;
      }
      p.name = entry.name;
      if (snapshot !== '') p.snapshot = snapshot;

      this.write(p, counts, [...f.tracks, track.trackId]);
      entry.total = p.total;
      entry.snapshot = p.snapshot;
      this.dev.log(`[profiles] '${p.name}' updated: ${p.total} tracks`);
    }

    similarWeights(similar, out) {
      const hits = [];
      const df = similar.map(() => 0);

      this.playlists.forEach((p, i) => {
        const f = this.flash.files[p.id];
        if (!f) return;
        const counts = similar.map(() => 0);
        for (const [, n, name] of f.artists) {
          similar.forEach((s, j) => {
            if (strcasecmp(name, s.name) === 0) counts[j] += n;
          });
        }
        similar.forEach((s, j) => {
          if (counts[j] === 0) return;
          ++df[j];
          hits.push({ playlist: i, artist: j, n: counts[j] });
        });
      });

      const total = f32(this.playlists.length);
      const scores = this.playlists.map(() => 0);
      for (const h of hits) {
        const p = this.playlists[h.playlist];
        if (p.total === 0) continue;
        const tf = f32(h.n / p.total);
        const idf = f32(Math.log(f32(total / df[h.artist])));
        scores[h.playlist] = f32(scores[h.playlist] + f32(f32(similar[h.artist].match * tf) * idf));
      }

      this.playlists.forEach((p, i) => {
        if (scores[i] <= 0) return;
        const via = hits.filter((h) => h.playlist === i).slice(0, 3)
          .map((h) => `${similar[h.artist].name} (${similar[h.artist].match.toFixed(2)})`).join(', ');
        this.dev.log(`[lastfm] '${p.name}': ${(scores[i] * 100).toFixed(2)}% via ${via}`);
      });

      for (const c of out) {
        const i = this.playlists.findIndex((pl) => pl.id === c.playlistId);
        if (i < 0) continue;
        c.weight = scores[i];
        c.similar = true;
      }
    }
  }

  // ---- spotify_backend.cpp ---------------------------------------------------------

  class SpotifyBackend {
    constructor(dev, client, profiles) {
      this.dev = dev;
      this.client = client;
      this.profiles = profiles;
    }

    async fetchNowPlaying(out, progress) {
      progress(20);
      const r = await this.client.call('GET', '/me/player/currently-playing', () => this.dev.cloud.currentlyPlaying());
      progress(70);
      if (r.err !== 'None') return r.err;

      const doc = r.data;
      const track = doc.item;
      if (r.status === 204 || !track) return 'NothingPlaying';
      if ((doc.currently_playing_type || 'track') !== 'track') return 'NothingPlaying';

      out.name = track.name || '';
      out.artistName = (track.artists[0] && track.artists[0].name) || '';
      if (track.is_local) {
        this.dev.log(`[spotify] local file: ${out.name}`);
        return 'LocalFile';
      }
      out.trackId = track.id || '';
      out.artistId = (track.artists[0] && track.artists[0].id) || '';
      if (out.trackId === '') return 'LocalFile';
      return 'None';
    }

    // Returns { matched, candidates }
    async rank(track, progress) {
      const out = this.profiles.weights(track);

      const fallback = candidate({
        playlistId: this.dev.cloud.state.fallback ? L.FALLBACK_ID : '',
        name: 'Fallback',
        kind: 'Fallback',
      });
      const found = out.findIndex((c) => c.playlistId === fallback.playlistId);
      if (found >= 0) {
        fallback.hasTrack = out[found].hasTrack;
        out.splice(found, 1);
      }

      const cancel = candidate({ name: 'Cancel', kind: 'Cancel' });
      const extras = [];
      if (fallback.playlistId !== '') extras.push(fallback);
      extras.push(cancel);

      let maxCount = cfg.MAX_SUGGESTIONS;
      const direct = out.some((c) => c.weight > 0);
      if (!direct && this.dev.cloud.state.lastfm) {
        this.dev.log(`[lastfm] ${track.artistName} is in no playlist, looking up similar artists`);
        progress(80);
        const similar = await fetchSimilarArtists(this.dev, track.artistName);
        if (similar) {
          progress(90);
          this.profiles.similarWeights(similar, out);
          maxCount = cfg.LASTFM_SUGGESTIONS;
        }
      }

      const matched = selectCandidates(out, maxCount);
      if (matched) out.push(...extras);
      else out.unshift(...extras);
      return { matched, candidates: out };
    }

    async addTrack(track, playlist, progress) {
      progress(20);
      const r = await this.client.call('POST', `/playlists/${playlist.playlistId}/items`,
        () => this.dev.cloud.addItem(playlist.playlistId, track));
      progress(80);
      if (r.err !== 'None') return r.err;
      this.profiles.recordAdd(playlist.playlistId, track, r.data.snapshot_id || '');
      progress(100);
      return 'None';
    }

    resyncAll(progress) { return this.profiles.sync(true, progress); }
  }

  // ---- state_machine.cpp -----------------------------------------------------------

  class StateMachine {
    constructor(dev, display, buttons, backend) {
      this.dev = dev;
      this.display = display;
      this.buttons = buttons;
      this.backend = backend;
      this.state = 'Idle';
      this.stateSince = 0;
      this.lastInput = 0;
      this.scrollStart = 0;
      this.track = { trackId: '', name: '', artistId: '', artistName: '' };
      this.candidates = [];
      this.manual = false;
      this.selected = 0;
      this.first = 0;
      this.line1 = '';
      this.line2 = '';
      this.dirty = true;
      this.animating = false;
      this.lastFrame = 0;
    }

    begin() { this.enterIdle(); }

    enter(next) {
      this.dev.log(`[sm] ${this.state.toUpperCase()} -> ${next.toUpperCase()}`);
      this.state = next;
      this.stateSince = this.scrollStart = this.lastInput = this.dev.millis();
      this.dirty = true;
      this.animating = false;
      this.dev.hooks.onState(next);
    }

    enterIdle() {
      this.candidates = [];
      this.enter('Idle');
    }

    enterError(err) {
      this.line1 = errorMessage(err);
      this.line2 = errorDetail(err);
      this.dev.log(`[sm] error: ${this.line1}`);
      this.enter('Error');
    }

    async tick() {
      const now = this.dev.millis();
      const ev = this.buttons.poll();

      switch (this.state) {
        case 'Idle':
          if (ev === 'NavPress' || ev === 'OkClick') await this.loadNowPlaying();
          else if (ev === 'OkHold') await this.resync();
          break;
        case 'Select':
          if (ev === 'NavPress') {
            this.moveSelection();
          } else if (ev === 'OkClick') {
            await this.confirmSelection();
          } else if (now - this.lastInput >= cfg.SELECT_TIMEOUT_MS) {
            this.dev.log('[sm] timeout on SELECT, nothing added');
            this.enterIdle();
          }
          break;
        case 'Done':
          if (now - this.stateSince >= cfg.DONE_MS) this.enterIdle();
          break;
        case 'Error':
          if (now - this.stateSince >= cfg.ERROR_MS) this.enterIdle();
          break;
        default:
          break;
      }

      this.render(this.dev.millis());
    }

    async loadNowPlaying() {
      this.enter('Loading');
      const progress = (pct) => this.display.progress('Loading', pct);
      progress(0);

      const track = { trackId: '', name: '', artistId: '', artistName: '' };
      const err = await this.backend.fetchNowPlaying(track, progress);
      this.track = track;
      if (err !== 'None') {
        this.enterError(err);
      } else {
        const ranked = await this.backend.rank(track, progress);
        this.manual = !ranked.matched;
        this.candidates = ranked.candidates;
        progress(100);
        // Cancel is always in the list: with nothing else, there's nowhere to add the song
        if (this.candidates.every((c) => c.kind === 'Cancel')) {
          this.enterError('NoPlaylists');
        } else {
          this.dev.log(`[sm] playing: ${track.name} - ${track.artistName} (${this.candidates.length} playlists, ${this.manual ? 'manual' : 'ranking'})`);
          this.selected = this.first = 0;
          this.enter('Select');
        }
      }
      this.buttons.suppressUntilRelease();
    }

    moveSelection() {
      this.selected = (this.selected + 1) % this.candidates.length;
      if (this.selected < this.first) {
        this.first = this.selected;
      } else if (this.selected >= this.first + cfg.LIST_ROWS) {
        this.first = this.selected - cfg.LIST_ROWS + 1;
      }
      this.lastInput = this.scrollStart = this.dev.millis();
      this.dirty = true;
    }

    async confirmSelection() {
      const chosen = this.candidates[this.selected];
      if (chosen.kind === 'Cancel') {
        this.dev.log('[sm] cancelled, nothing added');
        this.enterIdle();
        return;
      }
      if (chosen.hasTrack) {
        this.dev.log(`[sm] already in ${chosen.name}, nothing added`);
        this.line1 = 'Already in';
        this.line2 = chosen.name;
        this.enter('Done');
        return;
      }

      this.enter('Loading');
      const progress = (pct) => this.display.progress('Adding', pct);
      progress(0);

      const err = await this.backend.addTrack(this.track, chosen, progress);
      if (err !== 'None') {
        this.enterError(err);
      } else {
        this.dev.log(`[sm] added to ${chosen.name}`);
        this.line1 = 'Added to';
        this.line2 = chosen.name;
        this.enter('Done');
      }
      this.buttons.suppressUntilRelease();
    }

    async resync() {
      this.dev.log('[sm] resyncing every playlist');
      this.enter('Loading');
      const progress = (pct) => this.display.progress('Syncing', pct);
      progress(0);

      const err = await this.backend.resyncAll(progress);
      if (err !== 'None') {
        this.enterError(err);
      } else {
        this.line1 = 'Playlists';
        this.line2 = 'synced';
        this.enter('Done');
      }
      this.buttons.suppressUntilRelease();
    }

    render(now) {
      if (!this.dirty && !(this.animating && now - this.lastFrame >= cfg.FRAME_MS)) return;

      switch (this.state) {
        case 'Idle':
          this.display.idle();
          this.animating = false;
          break;
        case 'Select':
          this.animating = this.display.select(this.track, this.candidates, this.manual, this.selected,
            this.first, now - this.scrollStart);
          break;
        case 'Done':
        case 'Error':
          this.animating = this.display.message(this.line1, this.line2, now - this.scrollStart);
          break;
        default:
          break;
      }
      this.dirty = false;
      this.lastFrame = now;
    }
  }

  // ---- main.cpp --------------------------------------------------------------------

  class Device {
    // hooks: onFrame(buffer), onSerial(line, ms), onState(name), onPower(on)
    constructor(cloud, hooks) {
      this.cloud = cloud;
      this.hooks = { onFrame() {}, onSerial() {}, onState() {}, onPower() {}, ...hooks };
      this.pins = { nav: false, ok: false }; // true = pressed (the pin reads LOW)
      this.generation = 0;
      this.on = false;
      this.u8g2 = new window.U8G2();
      this.u8g2.onSendBuffer = (buffer) => this.hooks.onFrame(buffer);
    }

    millis() { return Math.floor(performance.now() - this.bootAt); }

    // delay() that stops the running code when the power goes off
    delay(ms) {
      const generation = this.generation;
      return new Promise((resolve, reject) => {
        setTimeout(() => (generation === this.generation ? resolve() : reject(new PowerOff())), ms);
      });
    }

    log(line) { this.hooks.onSerial(line, this.millis()); }

    press(pin, pressed) { this.pins[pin] = pressed; }

    powerOn() {
      this.generation++;
      this.on = true;
      this.bootAt = performance.now();
      this.flash = new Flash();
      this.display = new Display(this.u8g2);
      this.buttons = new Buttons(this);
      this.spotify = new SpotifyClient(this);
      this.profiles = new Profiles(this, this.spotify);
      this.backend = new SpotifyBackend(this, this.spotify, this.profiles);
      this.machine = new StateMachine(this, this.display, this.buttons, this.backend);
      this.hooks.onPower(true);
      this.run().catch((e) => {
        if (!(e instanceof PowerOff)) console.error(e);
      });
    }

    powerOff() {
      this.generation++;
      this.on = false;
      this.u8g2.clearBuffer();
      this.u8g2.sendBuffer();
      this.hooks.onPower(false);
    }

    async run() {
      await this.setup();
      for (;;) {
        await this.machine.tick();
        await this.delay(1);
      }
    }

    async showMessage(line1, line2, durationMs) {
      const start = this.millis();
      while (this.millis() - start < durationMs) {
        this.display.message(line1, line2, this.millis() - start);
        await this.delay(cfg.FRAME_MS);
      }
    }

    async connectWifi() {
      this.log(`[wifi] connecting to ${WIFI_SSID}`);
      const start = this.millis();
      let connectAt = null;
      for (;;) {
        const elapsed = this.millis() - start;
        if (this.cloud.state.wifi && connectAt === null) connectAt = elapsed + this.cloud.latency(900, 1600);
        if (connectAt !== null && elapsed >= connectAt && this.cloud.state.wifi) break;
        if (elapsed >= cfg.WIFI_TIMEOUT_MS) {
          this.log('[wifi] failed (status 1)');
          return false;
        }
        this.display.progress('Connecting Wi-Fi', idiv(elapsed * 100, cfg.WIFI_TIMEOUT_MS));
        await this.delay(200);
      }
      this.log('[wifi] connected, IP 192.168.1.42, signal -58 dBm');
      return true;
    }

    async bootOnline() {
      if (!(await this.connectWifi())) {
        await this.showMessage(errorMessage('NoWifi'), '', cfg.ERROR_MS);
        return;
      }

      this.display.progress('Signing in to Spotify', 50);
      const me = await this.spotify.getMe();
      if (me.err !== 'None') {
        await this.showMessage(errorMessage(me.err), errorDetail(me.err), cfg.ERROR_MS);
        return;
      }

      this.log(`[spotify] user: ${me.user.displayName} (id ${me.user.id})`);
      await this.showMessage('Hi,', me.user.displayName, cfg.GREETING_MS);

      this.profiles.setUserId(me.user.id);
      const syncErr = await this.profiles.sync(false, (pct) => this.display.progress('Syncing', pct));
      if (syncErr !== 'None') {
        await this.showMessage(errorMessage(syncErr), errorDetail(syncErr), cfg.ERROR_MS);
      }
    }

    async setup() {
      this.log('');
      this.log('[pulse] boot');
      this.display.begin();
      this.buttons.begin();
      this.profiles.begin();
      await this.bootOnline();
      this.machine.begin();
    }
  }

  window.PulseDevice = Device;
  window.PulseFlash = Flash;
})();
