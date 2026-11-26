// Example data for the simulated Spotify and Last.fm. The playlists are made up; each
// is a list of [artist, number of tracks]. The songs cover every path of the device.
(function () {
  'use strict';

  const USER = { id: 'demo', displayName: 'Alex' };
  const FALLBACK_ID = 'pl-fallback';

  const PLAYLISTS = [
    { id: 'pl-drive', name: 'late night drive', artists: [
      ['The Weeknd', 6], ['The Midnight', 5], ['Kavinsky', 4], ['M83', 4], ['Chromatics', 3],
      ['Daft Punk', 3], ['Tame Impala', 2], ['Lana Del Rey', 2]] },
    { id: 'pl-indie', name: 'indie mornings', artists: [
      ['Phoenix', 5], ['Vampire Weekend', 5], ['Two Door Cinema Club', 4], ['Tame Impala', 4],
      ['MGMT', 3], ['Foster the People', 3], ['Mac DeMarco', 3], ['Arctic Monkeys', 2]] },
    { id: 'pl-gym', name: 'gym', artists: [
      ['Kanye West', 5], ['Travis Scott', 5], ['Kendrick Lamar', 4], ['Eminem', 4], ['Drake', 4],
      ['Daft Punk', 2], ['The Weeknd', 2]] },
    { id: 'pl-focus', name: 'deep focus', artists: [
      ['Tycho', 6], ['Bonobo', 5], ['Nils Frahm', 4], ['Ólafur Arnalds', 4], ['Jon Hopkins', 3],
      ['Four Tet', 3], ['Boards of Canada', 3]] },
    { id: 'pl-br', name: 'música brasileira', artists: [
      ['Tim Maia', 5], ['Caetano Veloso', 5], ['Gilberto Gil', 4], ['Jorge Ben Jor', 4],
      ['Marisa Monte', 3], ['Os Mutantes', 3], ['Gal Costa', 3], ['Djavan', 3]] },
    { id: 'pl-2000s', name: 'throwbacks 2000s', artists: [
      ['The Strokes', 4], ['The Killers', 4], ['Arctic Monkeys', 3], ['Franz Ferdinand', 3],
      ['Kings of Leon', 3], ['Yeah Yeah Yeahs', 2], ['MGMT', 2], ['Phoenix', 1]] },
    { id: 'pl-rain', name: 'rainy day', artists: [
      ['Bon Iver', 4], ['Sufjan Stevens', 4], ['Phoebe Bridgers', 4], ['Radiohead', 3],
      ['Nick Drake', 3], ['Novo Amor', 3], ['Lana Del Rey', 2]] },
    { id: 'pl-sunday', name: 'sunday morning cooking with the windows open', artists: [
      ['Khruangbin', 5], ['Vulfpeck', 4], ['Tom Misch', 4], ['Mac DeMarco', 3], ['Anderson .Paak', 3],
      ['Jorge Ben Jor', 2], ['Tim Maia', 2]] },
    { id: 'pl-road', name: 'road trip', artists: [
      ['Fleetwood Mac', 4], ['Tame Impala', 3], ['The Killers', 3], ['Arctic Monkeys', 2],
      ['Kings of Leon', 2], ['Phoenix', 2], ['Foster the People', 2], ['The Strokes', 2],
      ['Khruangbin', 2]] },
    { id: 'pl-electro', name: 'chill electronic', artists: [
      ['Caribou', 4], ['Jamie xx', 4], ['Fred again..', 4], ['Bonobo', 3], ['Four Tet', 3],
      ['Kaytranada', 3], ['Tycho', 2], ['Daft Punk', 2]] },
    { id: 'pl-rock', name: 'rock classics', artists: [
      ['Led Zeppelin', 5], ['Pink Floyd', 5], ['The Beatles', 5], ['The Rolling Stones', 4],
      ['Queen', 4], ['Fleetwood Mac', 2], ['Radiohead', 1]] },
    { id: 'pl-jazz', name: 'late night jazz', artists: [
      ['Miles Davis', 5], ['John Coltrane', 4], ['Bill Evans', 4], ['Chet Baker', 3],
      ['Nina Simone', 3]] },
    // Someone else's collaborative playlist: Pulse ranks it too
    { id: 'pl-party', name: 'party (collab)', owner: 'friend', collaborative: true, artists: [
      ['Dua Lipa', 4], ['The Weeknd', 3], ['Calvin Harris', 3], ['Doja Cat', 3], ['Daft Punk', 2],
      ['Kaytranada', 2]] },
    // Followed but not yours: Pulse ignores it
    { id: 'pl-top', name: 'Top Hits (followed)', owner: 'spotify', artists: [
      ['Sabrina Carpenter', 5], ['Dua Lipa', 4], ['The Weeknd', 3]] },
    // secrets::FALLBACK_PLAYLIST_ID: shows as "Fallback" on the device
    { id: FALLBACK_ID, name: 'pulse fallback', artists: [['Men I Trust', 1]] },
  ];

  // Songs that can be "playing". in: playlists that already have this exact track.
  const SONGS = [
    { id: 'tr-letithappen', name: 'Let It Happen', artist: 'Tame Impala', in: [],
      hint: 'In 3 playlists: ranked by share' },
    { id: 'tr-getlucky', name: 'Get Lucky', artist: 'Daft Punk', in: [],
      hint: 'In 4 playlists: the list scrolls' },
    { id: 'tr-blinding', name: 'Blinding Lights', artist: 'The Weeknd', in: ['pl-drive', 'pl-party'],
      hint: 'Already in 2 playlists: marked "in"' },
    { id: 'tr-everything', name: 'Everything In Its Right Place', artist: 'Radiohead', in: [],
      hint: 'Long title: the header scrolls' },
    { id: 'tr-aguas', name: 'Águas de Março', artist: 'Elis Regina', in: [],
      hint: 'Artist in no playlist: Last.fm (~)' },
    { id: 'tr-showme', name: 'Show Me How', artist: 'Men I Trust', in: [],
      hint: 'Only in the fallback: Last.fm (~)' },
    { id: 'tr-garage', name: 'Garage Demo #3', artist: "The Neighbours' Band", in: [],
      hint: 'No match anywhere: manual list' },
    { id: 'local', name: 'voice memo.m4a', artist: 'Me', local: true,
      hint: 'Local file: can’t be added' },
    { id: 'podcast', name: 'Episode 112: Synths', artist: 'A podcast', podcast: true,
      hint: 'Podcast: not a song' },
    { id: 'none', name: 'Nothing playing', artist: '', none: true, hint: 'Spotify is idle' },
  ];

  // artist.getSimilar. Artists missing here are unknown to Last.fm (error 6).
  const SIMILAR = {
    'Elis Regina': [['Tom Jobim', 1], ['Gal Costa', 0.82], ['Chico Buarque', 0.79],
      ['Caetano Veloso', 0.74], ['Marisa Monte', 0.61], ['Gilberto Gil', 0.55], ['Djavan', 0.42]],
    'Men I Trust': [['Mac DeMarco', 0.71], ['Khruangbin', 0.64], ['Tom Misch', 0.44],
      ['Tame Impala', 0.38], ['Phoebe Bridgers', 0.2], ['Bonobo', 0.18]],
  };

  const slug = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

  // Full playlists with one track per entry, as /playlists/{id}/items would return them
  function buildPlaylists() {
    return PLAYLISTS.map((p) => {
      const tracks = [];
      for (const [artist, count] of p.artists) {
        for (let i = 0; i < count; i++) {
          tracks.push({ id: `tr-${p.id}-${slug(artist)}-${i}`, artistId: `ar-${slug(artist)}`, artistName: artist });
        }
      }
      for (const song of SONGS) {
        if ((song.in || []).includes(p.id)) {
          tracks.push({ id: song.id, artistId: `ar-${slug(song.artist)}`, artistName: song.artist });
        }
      }
      return {
        id: p.id,
        name: p.name,
        owner: p.owner || USER.id,
        collaborative: Boolean(p.collaborative),
        snapshot: 1,
        tracks,
      };
    });
  }

  window.LIBRARY = { USER, FALLBACK_ID, SONGS, SIMILAR, slug, buildPlaylists };
})();
