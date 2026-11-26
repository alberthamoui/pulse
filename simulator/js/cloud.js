// The outside world the device talks to: Wi-Fi, the Spotify Web API and Last.fm.
// Everything is local and made up (js/library.js), with network latency and the
// failures the firmware handles. The state persists in localStorage, so a page reload
// keeps your library like a real account would.
(function () {
  'use strict';

  const STORAGE_KEY = 'pulse-sim/cloud';
  const L = window.LIBRARY;

  function readStorage(key) {
    try {
      return JSON.parse(localStorage.getItem(key));
    } catch (e) {
      return null;
    }
  }

  function writeStorage(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
      // private mode or storage blocked: the simulator still works, it just won't remember
    }
  }

  class Cloud {
    constructor() {
      const saved = readStorage(STORAGE_KEY);
      this.state = saved && saved.version === 1 ? saved : Cloud.fresh();
      this.listeners = [];
    }

    static fresh() {
      return {
        version: 1,
        playlists: L.buildPlaylists(),
        playing: 'tr-letithappen',
        wifi: true,
        api: 'ok', // ok | rate | auth
        lastfm: true,
        fallback: true,
        edits: 0,
      };
    }

    reset() {
      this.state = Cloud.fresh();
      this.changed();
    }

    onChange(fn) { this.listeners.push(fn); }

    changed(detail) {
      writeStorage(STORAGE_KEY, this.state);
      for (const fn of this.listeners) fn(detail || {});
    }

    set(key, value) {
      this.state[key] = value;
      this.changed({ key });
    }

    song(id) { return L.SONGS.find((s) => s.id === id); }

    playlist(id) { return this.state.playlists.find((p) => p.id === id); }

    snapshotOf(p) { return `${p.id}~${p.snapshot}`; }

    // Someone edits a playlist from their phone: its snapshot_id changes
    editElsewhere() {
      const mine = this.state.playlists.filter((p) => p.owner === L.USER.id && p.id !== L.FALLBACK_ID);
      const p = mine[this.state.edits % mine.length];
      const donor = this.state.playlists[(this.state.edits * 7 + 3) % this.state.playlists.length];
      const track = donor.tracks[this.state.edits % donor.tracks.length];
      p.tracks.push({ ...track, id: `${track.id}-copy${this.state.edits}` });
      p.snapshot++;
      this.state.edits++;
      this.changed({ edited: p.id });
      return p;
    }

    // ---- Network -------------------------------------------------------------------

    latency(min, max) { return min + Math.random() * (max - min); }

    getMe() {
      return { id: L.USER.id, display_name: L.USER.displayName };
    }

    currentlyPlaying() {
      const song = this.song(this.state.playing);
      if (!song || song.none) return { status: 204 };
      if (song.podcast) return { status: 200, currently_playing_type: 'episode', item: { name: song.name } };
      return {
        status: 200,
        currently_playing_type: 'track',
        item: {
          id: song.local ? null : song.id,
          name: song.name,
          is_local: Boolean(song.local),
          artists: [{ id: song.local ? null : `ar-${L.slug(song.artist)}`, name: song.artist }],
        },
      };
    }

    // GET /me/playlists?limit&offset
    listPlaylists(offset, limit) {
      const all = this.state.playlists;
      const items = all.slice(offset, offset + limit).map((p) => ({
        id: p.id,
        name: p.name,
        snapshot_id: this.snapshotOf(p),
        collaborative: p.collaborative,
        owner: { id: p.owner },
        items: { total: p.tracks.length },
      }));
      return { items, next: offset + limit < all.length ? 'more' : null };
    }

    // GET /playlists/{id}/items?limit&offset
    playlistItems(id, offset, limit) {
      const p = this.playlist(id);
      if (!p) return { status: 404 };
      const items = p.tracks.slice(offset, offset + limit).map((t) => ({
        item: { id: t.id, artists: [{ id: t.artistId, name: t.artistName }] },
      }));
      return { status: 200, items, next: offset + limit < p.tracks.length ? 'more' : null };
    }

    // POST /playlists/{id}/items
    addItem(id, track) {
      const p = this.playlist(id);
      if (!p) return { status: 404 };
      p.tracks.push({ id: track.trackId, artistId: track.artistId, artistName: track.artistName });
      p.snapshot++;
      this.changed({ added: id });
      return { status: 201, snapshot_id: this.snapshotOf(p) };
    }

    // GET ws.audioscrobbler.com/2.0/?method=artist.getsimilar
    similarArtists(artist, limit) {
      const similar = L.SIMILAR[artist];
      if (!similar) return { error: 6, message: 'The artist you supplied could not be found' };
      return { artists: similar.slice(0, limit).map(([name, match]) => ({ name, match })) };
    }
  }

  window.Cloud = Cloud;
  window.simStorage = { read: readStorage, write: writeStorage };
})();
