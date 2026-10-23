/* ==========================================================================
   Monday Music Mix: client runtime
   - The player: a small card that plays a mix's YouTube playlist in
     YouTube's own player. We never drive the queue song by song; YouTube
     plays the list, we listen to its events and point the song bar, the
     record and the tracklist at whatever is on.
   - pjax router: swaps <main> so the player keeps going between pages
   - Discovery search/filter, the wall of Mondays, the inlay card
   - Keyboard shortcuts, track deep links (#t=N)
   ========================================================================== */

(() => {
  'use strict';

  /* ------------------------------------------------------------------ *
   * Utilities
   * ------------------------------------------------------------------ */

  function normalizeDiscoveryText(value) {
    return String(value || '')
      .normalize('NFKD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/&/g, ' and ')
      .replace(/[^a-z0-9]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function readPipeSet(value) {
    return new Set(
      String(value || '')
        .split('|')
        .map((item) => item.trim().toLowerCase())
        .filter(Boolean)
    );
  }

  const runtimeScript = document.currentScript || document.querySelector('script[src*="site.js"]');
  // Resolve to an absolute URL once, at boot: the raw attribute is relative to
  // the page that loaded the script, and pjax changes the page under it.
  const runtimeScriptSrc = (() => {
    try {
      return new URL(runtimeScript?.getAttribute('src') || 'assets/site.js', document.baseURI).href;
    } catch {
      return 'assets/site.js';
    }
  })();
  const assetBase = runtimeScriptSrc.replace(/site\.js(?:\?.*)?$/, '');
  const assetVersion = (() => {
    try {
      return new URL(runtimeScriptSrc, window.location.href).searchParams.get('v') || '';
    } catch {
      const match = /[?&]v=([^&]+)/.exec(runtimeScriptSrc);
      return match ? match[1] : '';
    }
  })();

  function assetHref(path) {
    return `${assetBase}${path}${assetVersion ? `?v=${encodeURIComponent(assetVersion)}` : ''}`;
  }

  function readJsonScript(scope, selector) {
    const script = (scope || document).querySelector(selector);
    if (!script) return null;
    try {
      return JSON.parse(script.textContent);
    } catch {
      return null;
    }
  }

  /* ------------------------------------------------------------------ *
   * YouTube IFrame API loader
   * ------------------------------------------------------------------ */

  let youtubeApiPromise = null;

  function loadYoutubeIframeApi() {
    if (window.YT && window.YT.Player) return Promise.resolve(window.YT);
    if (youtubeApiPromise) return youtubeApiPromise;

    youtubeApiPromise = new Promise((resolve, reject) => {
      const previousReady = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = () => {
        if (typeof previousReady === 'function') previousReady();
        resolve(window.YT);
      };
      if (!document.querySelector('script[src="https://www.youtube.com/iframe_api"]')) {
        const script = document.createElement('script');
        script.src = 'https://www.youtube.com/iframe_api';
        script.async = true;
        script.onerror = () => reject(new Error('Failed to load the YouTube IFrame Player API.'));
        document.head.append(script);
      }
    });

    return youtubeApiPromise;
  }

  /* ------------------------------------------------------------------ *
   * The player
   * ------------------------------------------------------------------ */

  // YouTube's embed policy: the player stays visible and at least 200x200
  // while it plays. The screen is sized for that in site.css; minimising the
  // player always pauses it first.
  const SKIP_UNPLAYABLE_MS = 1600;
  // After this many songs in a row refuse to play, stop skipping: YouTube is
  // refusing this page, not one song (a LAN address does that).
  const GIVE_UP_AFTER_FAILURES = 3;
  const POLL_MS = 500;
  // A song we skipped to that hasn't even loaded by now has failed too;
  // YouTube doesn't always say so. (Loaded but waiting for a tap is fine.)
  const STALL_MS = 6000;

  const tv = {
    root: null,
    els: {},
    yt: null,
    ready: false,
    queue: null, // normalizeQueue() shape
    index: 0,
    state: -1,
    playing: false,
    ended: false,
    blocked: false,
    // { index, refused } while a song that won't play is being skipped.
    error: null,
    loadFailed: false,
    failStreak: 0,
    tucked: false,
    pollTimer: 0,
    skipTimer: 0,
    watchdog: 0,
    pendingStart: null,
    creating: null,
  };

  function ytState(name) {
    return window.YT?.PlayerState?.[name];
  }

  function clampIndex(index) {
    if (!tv.queue) return 0;
    return Math.min(Math.max(Math.floor(Number(index) || 0), 0), tv.queue.videoIds.length - 1);
  }

  function absolutize(href) {
    try {
      return href ? new URL(href, document.baseURI).href : '';
    } catch {
      return href || '';
    }
  }

  // The queue holds only the songs that are on YouTube. rows[i] is the
  // tracklist row (and the groove on the record) of queued song i; with
  // nothing missing, it is just i.
  function queueRows(payload) {
    const count = Array.isArray(payload?.videoIds) ? payload.videoIds.length : 0;
    const rows = Array.isArray(payload?.rows) ? payload.rows.map((value) => Number(value)) : [];
    return rows.length === count && rows.every((value) => Number.isInteger(value) && value >= 0)
      ? rows
      : Array.from({ length: count }, (_, index) => index);
  }

  // Which queued song a tracklist row or a groove is: -1 for a song that
  // isn't on YouTube.
  function songForRow(payload, row) {
    return queueRows(payload).indexOf(Number(row));
  }

  function rowForSong(index) {
    const row = tv.queue?.rows?.[index];
    return Number.isInteger(row) ? row : index;
  }

  // Payload URLs are relative to the page that rendered them; the player
  // outlives that page, so pin them down the moment a mix is tuned in.
  function normalizeQueue(payload) {
    if (!payload || !Array.isArray(payload.videoIds)) return null;
    const videoIds = payload.videoIds.map((value) => String(value || '').trim()).filter(Boolean);
    if (!videoIds.length) return null;
    return {
      rows: queueRows({ videoIds, rows: payload.rows }),
      songCount: Math.max(Number(payload.songCount) || 0, videoIds.length),
      slug: String(payload.slug || ''),
      title: String(payload.title || 'Mix'),
      number: String(payload.number || ''),
      url: absolutize(payload.url),
      videoIds,
      labels: Array.isArray(payload.labels) ? payload.labels.map((value) => String(value || '').trim()) : [],
      tracks: Array.isArray(payload.tracks)
        ? payload.tracks.map((track) => ({ title: String(track?.title || '').trim(), artist: String(track?.artist || '').trim() }))
        : [],
      durations: Array.isArray(payload.durations) ? payload.durations.map((value) => Math.max(0, Number(value) || 0)) : [],
      cover: absolutize(payload.cover),
      playlistId: String(payload.playlistId || ''),
      watchUrl: String(payload.watchUrl || ''),
      musicUrl: String(payload.musicUrl || ''),
      theme: payload.theme && typeof payload.theme === 'object' ? payload.theme : null,
    };
  }

  function trackParts(index) {
    const track = tv.queue?.tracks[index];
    if (track?.title) return track;
    return { title: tv.queue?.labels[index] || `Song ${index + 1}`, artist: '' };
  }

  function trackLabel(index) {
    const { title, artist } = trackParts(index);
    return artist ? `${title} by ${artist}` : title;
  }

  // Each segment of the song bar is one song, as wide as the song is long.
  function segmentWeights(queue) {
    const known = queue.durations.filter((value) => value > 0);
    const fallback = known.length ? known.reduce((sum, value) => sum + value, 0) / known.length : 1;
    return queue.videoIds.map((_, index) => (queue.durations[index] > 0 ? queue.durations[index] : fallback));
  }

  function bindTvElements() {
    const root = document.querySelector('[data-tv]');
    if (!root) return false;
    tv.root = root;
    tv.els = {
      screen: root.querySelector('[data-tv-screen]'),
      host: root.querySelector('[data-tv-host]'),
      cover: root.querySelector('[data-tv-cover]'),
      caption: root.querySelector('[data-tv-caption]'),
      bar: root.querySelector('[data-tv-ticks]'),
      mix: root.querySelector('[data-tv-mix]'),
      track: root.querySelector('[data-tv-track]'),
      artist: root.querySelector('[data-tv-artist]'),
      count: root.querySelector('[data-tv-count]'),
      prev: root.querySelector('[data-tv-prev]'),
      toggle: root.querySelector('[data-tv-toggle]'),
      toggleIcon: root.querySelector('[data-tv-toggle-icon]'),
      next: root.querySelector('[data-tv-next]'),
      external: root.querySelector('[data-tv-external]'),
      tuck: root.querySelector('[data-tv-tuck]'),
      power: root.querySelector('[data-tv-power]'),
      puck: root.querySelector('[data-tv-puck]'),
      puckLabel: root.querySelector('[data-tv-puck-label]'),
    };
    return true;
  }

  function buildBar() {
    const { bar } = tv.els;
    if (!bar || !tv.queue) return;
    bar.replaceChildren(
      ...segmentWeights(tv.queue).map((weight, index) => {
        const segment = document.createElement('button');
        segment.type = 'button';
        segment.className = 'tv__seg';
        segment.dataset.tvTick = String(index);
        segment.style.flexGrow = String(weight);
        segment.tabIndex = index === tv.index ? 0 : -1;
        segment.setAttribute('aria-label', `Song ${index + 1}: ${trackLabel(index)}`);
        const fill = document.createElement('span');
        fill.className = 'tv__seg-fill';
        segment.append(fill);
        return segment;
      })
    );
  }

  function currentFraction() {
    const duration = Number(tv.yt?.getDuration?.() || 0);
    const time = Number(tv.yt?.getCurrentTime?.() || 0);
    return duration > 0 ? Math.min(1, Math.max(0, time / duration)) : 0;
  }

  function setBar(index, fraction) {
    for (const segment of tv.els.bar?.children || []) {
      const position = Number(segment.dataset.tvTick);
      const current = position === index && !tv.ended;
      segment.classList.toggle('is-current', current);
      segment.classList.toggle('is-done', position < index || tv.ended);
      segment.tabIndex = position === index ? 0 : -1;
      if (current) {
        segment.setAttribute('aria-current', 'true');
        segment.style.setProperty('--progress', String(fraction));
      } else {
        segment.removeAttribute('aria-current');
        segment.style.removeProperty('--progress');
      }
    }
  }

  const THEME_VARS = {
    bg: '--tv-bg',
    raised: '--tv-raised',
    text: '--tv-text',
    textDim: '--tv-dim',
    accent: '--tv-accent',
    onAccent: '--tv-on-accent',
    line: '--tv-line',
  };

  // The player wears its own mix's colours, wherever you browse.
  function paintSet() {
    const { root, els, queue } = tv;
    if (!root || !queue) return;
    for (const [key, name] of Object.entries(THEME_VARS)) {
      if (queue.theme?.[key]) root.style.setProperty(name, queue.theme[key]);
      else root.style.removeProperty(name);
    }
    root.style.colorScheme = queue.theme?.scheme || '';
    if (els.cover) {
      if (queue.cover) els.cover.src = queue.cover;
      else els.cover.removeAttribute('src');
    }
    if (els.mix) {
      els.mix.textContent = queue.number ? `No.${queue.number} · ${queue.title}` : queue.title;
      els.mix.href = queue.url || '#';
    }
  }

  function externalHref() {
    const queue = tv.queue;
    if (!queue) return '#';
    const videoId = queue.videoIds[tv.index];
    if (queue.playlistId && videoId) {
      return `https://www.youtube.com/watch?v=${encodeURIComponent(videoId)}&list=${encodeURIComponent(queue.playlistId)}&index=${tv.index + 1}`;
    }
    // Pick the mix up on YouTube from the song that is on now.
    return `https://www.youtube.com/watch_videos?video_ids=${queue.videoIds.slice(tv.index).join(',')}`;
  }

  function syncTvUi() {
    const { root, els, queue } = tv;
    if (!root) return;
    const live = Boolean(queue);
    root.hidden = !live;
    document.body.classList.toggle('has-tv', live && !tv.tucked);
    if (!live) return;

    root.classList.toggle('is-ready', tv.ready && !tv.blocked);
    root.classList.toggle('is-playing', tv.playing);
    root.classList.toggle('is-ended', tv.ended);
    root.classList.toggle('is-blocked', tv.blocked);
    root.classList.toggle('is-tucked', tv.tucked);

    setBar(tv.index, tv.playing || tv.state === ytState('PAUSED') ? currentFraction() : 0);
    if (!tv.skipTimer) {
      const { title, artist } = trackParts(tv.index);
      if (tv.blocked) {
        if (els.track) els.track.textContent = "YouTube won't play this mix here.";
        if (els.artist) els.artist.textContent = 'Open it on YouTube with the arrow above.';
      } else if (tv.ended) {
        if (els.track) els.track.textContent = "That's the mix.";
        if (els.artist) els.artist.textContent = 'Press play to hear it again.';
      } else {
        if (els.track) els.track.textContent = title;
        if (els.artist) els.artist.textContent = artist;
      }
    }
    if (els.count) els.count.textContent = `Song ${rowForSong(tv.index) + 1} of ${queue.songCount || queue.videoIds.length}`;
    // Whenever YouTube can't play, the cover and a short note sit over its
    // error screen.
    root.classList.toggle('is-erroring', Boolean(tv.error || tv.blocked || tv.loadFailed));
    renderCaption();
    if (els.toggle) {
      const label = tv.playing ? 'Pause' : tv.ended ? 'Play the mix again' : 'Play';
      els.toggle.setAttribute('aria-label', label);
      els.toggle.title = label;
    }
    setIcon(els.toggleIcon, tv.playing ? 'pause' : 'play');
    if (els.external) els.external.href = externalHref();
    if (els.puck) els.puck.hidden = !tv.tucked;
    if (els.puckLabel) els.puckLabel.textContent = `${queue.number ? `No.${queue.number}` : queue.title} · paused`;
  }

  // Icons are <svg><use href="#icon-name"> from the page's sprite.
  function setIcon(svg, name) {
    svg?.querySelector('use')?.setAttribute('href', `#icon-${name}`);
  }

  const SMALL_NUMBERS = ['zero', 'one', 'two', 'three', 'four'];

  // Songs are numbered as the tracklist numbers them, skipped songs included.
  function songNumber(index) {
    const number = rowForSong(index) + 1;
    return number < SMALL_NUMBERS.length ? SMALL_NUMBERS[number] : String(number);
  }

  function youtubeLink(label, href) {
    const link = document.createElement('a');
    link.href = href;
    link.target = '_blank';
    link.rel = 'noopener';
    link.textContent = label;
    return link;
  }

  // The note on the cover: two lines at most, with a way out to YouTube when
  // YouTube is the only place a song (or the mix) will play.
  function renderCaption() {
    const caption = tv.els.caption;
    if (!caption || !tv.queue) return;
    if (tv.loadFailed) {
      caption.replaceChildren("YouTube didn't load. Open the mix on ", youtubeLink('YouTube', externalHref()), '.');
    } else if (tv.blocked) {
      caption.replaceChildren("YouTube won't play this mix here. Open it on ", youtubeLink('YouTube', externalHref()), '.');
    } else if (tv.error) {
      const id = tv.queue.videoIds[tv.error.index];
      const watch = id ? `https://www.youtube.com/watch?v=${encodeURIComponent(id)}` : externalHref();
      if (tv.error.refused) {
        caption.replaceChildren(`Song ${songNumber(tv.error.index)} only plays on `, youtubeLink('YouTube', watch), '.');
      } else {
        caption.replaceChildren(`Song ${songNumber(tv.error.index)} won't play right now.`);
      }
    } else {
      caption.textContent = tv.ended ? "That's the mix." : 'Loading';
    }
  }

  // After a play button is pressed, make sure the player card that opens
  // doesn't sit on top of it (on a phone it docks along the bottom).
  function keepClearOfPlayer(element) {
    if (!element) return;
    window.setTimeout(() => {
      const card = tv.root?.querySelector('.tv__card');
      if (!card || tv.root.hidden || tv.tucked || !document.documentElement.contains(element)) return;
      const box = card.getBoundingClientRect();
      const rect = element.getBoundingClientRect();
      const overlap = rect.bottom + 16 - box.top;
      if (overlap > 0 && rect.right > box.left && rect.left < box.right) {
        const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        window.scrollBy({ top: overlap, behavior: still ? 'auto' : 'smooth' });
      }
    }, 520);
  }

  function syncPlayButtons() {
    for (const button of document.querySelectorAll('[data-play-mix]')) {
      const slug = button.dataset.playMixSlug || '';
      const live = Boolean(slug && tv.queue && tv.queue.slug === slug);
      const playing = live && tv.playing;
      button.setAttribute('aria-pressed', playing ? 'true' : 'false');
      button.classList.toggle('is-on', live);
      setIcon(button.querySelector('.btn__icon'), playing ? 'pause' : 'play');
      const title = button.dataset.playMixTitle || 'this mix';
      button.setAttribute('aria-label', playing ? `Pause ${title}` : live ? `Resume ${title}` : `Play ${title}`);
    }
  }

  function syncTracklistUi() {
    const list = document.querySelector('[data-tracklist]');
    if (list) {
      const matches = Boolean(tv.queue && list.dataset.tracklist === tv.queue.slug);
      const activeRow = matches ? rowForSong(tv.index) : -1;
      let activeItem = null;
      for (const item of list.querySelectorAll('[data-track-index]')) {
        const active = matches && Number(item.dataset.trackIndex) === activeRow && !tv.ended;
        item.classList.toggle('is-active', active);
        item.classList.toggle('is-paused', active && !tv.playing);
        item.querySelector('.tracklist__row')?.setAttribute('aria-current', active ? 'true' : 'false');
        if (active) activeItem = item;
      }
      placeNowNote(list, activeItem);
    }
    syncPlayButtons();
    syncVinylPlayback();
  }

  // The handwritten "It's on now." (built once per mix page) follows the song
  // that's playing, just after its artist, and its arrow is drawn again each
  // time it moves.
  function placeNowNote(list, item) {
    const note = list.closest('section')?.querySelector('[data-track-now]');
    if (!note) return;
    const artist = item?.querySelector('.tracklist__artist');
    const slot = artist || item?.querySelector('.tracklist__end');
    if (!slot) {
      note.hidden = true;
      return;
    }
    if (note.parentElement === slot && !note.hidden) return;
    if (artist) slot.append(note);
    else slot.prepend(note);
    note.hidden = false;
    const words = note.querySelector('.hand-note');
    if (words) playNoteGroup(words, 0);
  }

  function syncAll() {
    syncTvUi();
    syncTracklistUi();
  }

  // Which song is on, by video id. YouTube's own list position can drift
  // from ours when it drops a song it won't play, so ids are the truth.
  function currentVideoId() {
    const data = tv.yt?.getVideoData?.();
    if (data?.video_id) return String(data.video_id);
    const match = /[?&]v=([^&#]+)/.exec(String(tv.yt?.getVideoUrl?.() || ''));
    return match ? decodeURIComponent(match[1]) : '';
  }

  function readPlayerIndex() {
    if (!tv.queue || !tv.yt) return;
    const id = currentVideoId();
    let index = id ? tv.queue.videoIds.indexOf(id) : -1;
    if (index < 0) {
      const position = Number(tv.yt.getPlaylistIndex?.());
      const list = tv.yt.getPlaylist?.();
      index = Array.isArray(list) && list.length ? tv.queue.videoIds.indexOf(list[position]) : position;
    }
    if (Number.isInteger(index) && index >= 0 && index < tv.queue.videoIds.length) tv.index = index;
  }

  // Where song `index` (or the next one YouTube still has) sits in YouTube's list.
  function playerPosition(index) {
    const list = tv.yt?.getPlaylist?.();
    if (!Array.isArray(list) || !list.length) return index;
    for (let next = index; next < tv.queue.videoIds.length; next += 1) {
      const position = list.indexOf(tv.queue.videoIds[next]);
      if (position >= 0) return position;
    }
    return -1;
  }

  function playAtSong(index) {
    const position = playerPosition(index);
    if (position < 0) {
      tv.ended = true;
      tv.yt?.stopVideo?.();
      syncAll();
      return;
    }
    tv.yt?.playVideoAt?.(position);
  }

  function startPolling() {
    if (tv.pollTimer) return;
    tv.pollTimer = window.setInterval(() => {
      if (!tv.yt || !tv.ready) return;
      const before = tv.index;
      readPlayerIndex();
      if (before !== tv.index) {
        syncAll();
      } else {
        setBar(tv.index, currentFraction());
        syncVinylPlayback();
      }
    }, POLL_MS);
  }

  function stopPolling() {
    window.clearInterval(tv.pollTimer);
    tv.pollTimer = 0;
  }

  function queueArgs(queue, index) {
    return queue.playlistId
      ? [{ listType: 'playlist', list: queue.playlistId, index }]
      : [queue.videoIds, index];
  }

  function loadQueue(index, autoplay) {
    if (!tv.yt || !tv.queue) return;
    const method = autoplay ? 'loadPlaylist' : 'cuePlaylist';
    tv.yt[method](...queueArgs(tv.queue, index));
  }

  function onTvState(event) {
    tv.state = Number(event?.data);
    readPlayerIndex();
    const last = tv.queue ? tv.queue.videoIds.length - 1 : 0;
    tv.playing = tv.state === ytState('PLAYING');
    if (tv.playing || tv.state === ytState('BUFFERING')) tv.ended = false;
    if (tv.state === ytState('ENDED') && tv.index >= last) tv.ended = true;
    if (tv.playing) {
      tv.error = null;
      // YouTube's embed rules: never sound without a visible player. If
      // something resumed it while minimised (a media key), open it again.
      if (tv.tucked) tv.tucked = false;
      tv.failStreak = 0;
      window.clearTimeout(tv.watchdog);
      tv.watchdog = 0;
      tv.root?.classList.add('has-played');
      startPolling();
    } else {
      stopPolling();
    }
    syncAll();
  }

  function onTvError(event) {
    const code = Number(event?.data);
    if (!tv.queue) return;
    const failed = tv.index;
    const last = tv.queue.videoIds.length - 1;
    tv.failStreak += 1;
    window.clearTimeout(tv.skipTimer);
    tv.skipTimer = 0;
    if (tv.failStreak >= GIVE_UP_AFTER_FAILURES) {
      tv.blocked = true;
      syncAll();
      return;
    }
    const refused = code === 101 || code === 150;
    tv.error = { index: failed, refused };
    syncAll();
    if (tv.els.track) {
      tv.els.track.textContent = refused
        ? `Song ${songNumber(failed)} only plays on YouTube.`
        : `Song ${songNumber(failed)} won't play right now.`;
    }
    if (tv.els.artist) tv.els.artist.textContent = failed < last ? 'Moving on to the next song.' : '';
    tv.skipTimer = window.setTimeout(() => {
      tv.skipTimer = 0;
      if (failed < last) {
        playAtSong(failed + 1);
        armWatchdog();
      } else {
        tv.error = null;
        tv.ended = true;
        syncAll();
      }
    }, SKIP_UNPLAYABLE_MS);
  }

  function armWatchdog() {
    window.clearTimeout(tv.watchdog);
    tv.watchdog = window.setTimeout(() => {
      tv.watchdog = 0;
      if (!tv.queue || tv.playing || tv.ended || tv.blocked) return;
      if (Number(tv.yt?.getDuration?.() || 0) > 0) return;
      onTvError({ data: 'stalled' });
    }, STALL_MS);
  }

  // The mix goes into the embed URL itself (first video plus the rest as its
  // playlist, or the real playlist id), so the player holds the songs even
  // when the API's postMessage commands can't reach it, as from a plain-http
  // LAN address. Track N is always playlist index N.
  function embedVars(queue, index, autoplay) {
    const base = { playsinline: 1, rel: 0, iv_load_policy: 3, autoplay: autoplay ? 1 : 0 };
    if (queue.playlistId) return { videoId: undefined, playerVars: { ...base, listType: 'playlist', list: queue.playlistId, index } };
    // `playlist` must list every song, the first included: through the API,
    // YouTube treats it as the whole list and drops a starting video not in it.
    return { videoId: queue.videoIds[0], playerVars: { ...base, playlist: queue.videoIds.join(',') } };
  }

  function createPlayer(YT, index, autoplay) {
    if (tv.creating) return tv.creating;
    const mount = document.createElement('div');
    tv.els.host.replaceChildren(mount);
    const { videoId, playerVars } = embedVars(tv.queue, index, autoplay);
    tv.creating = new Promise((resolve) => {
      tv.yt = new YT.Player(mount, {
        width: '100%',
        height: '100%',
        ...(videoId ? { videoId } : {}),
        playerVars,
        events: {
          onReady: () => {
            tv.ready = true;
            const start = tv.pendingStart ?? index;
            tv.pendingStart = null;
            // A real playlist already starts at `index`; the anonymous queue
            // starts on track one, so move to the requested track.
            if (!tv.queue.playlistId && start > 0) playAtSong(start);
            else if (autoplay) tv.yt.playVideo();
            syncAll();
            resolve(tv.yt);
          },
          onStateChange: onTvState,
          onError: onTvError,
        },
      });
    }).finally(() => {
      tv.creating = null;
    });
    return tv.creating;
  }

  async function tuneIn(payload, startIndex = 0, { autoplay = true } = {}) {
    const queue = normalizeQueue(payload);
    if (!queue) return;
    const sameMix = Boolean(tv.queue && tv.queue.slug === queue.slug);
    tv.queue = queue;
    tv.index = clampIndex(startIndex);
    tv.ended = false;
    tv.tucked = false;
    tv.blocked = false;
    tv.error = null;
    tv.loadFailed = false;
    tv.failStreak = 0;
    if (!sameMix) {
      buildBar();
      paintSet();
    }
    syncAll();

    if (tv.yt && tv.ready) {
      if (sameMix) playAtSong(tv.index);
      else loadQueue(tv.index, autoplay);
      return;
    }
    tv.pendingStart = tv.index;
    try {
      const YT = await loadYoutubeIframeApi();
      if (!tv.queue || tv.queue.slug !== queue.slug) return;
      await createPlayer(YT, tv.index, autoplay);
    } catch {
      tv.loadFailed = true;
      syncAll();
      if (tv.els.track) tv.els.track.textContent = "YouTube didn't load.";
      if (tv.els.artist) tv.els.artist.textContent = 'The mix is still on YouTube.';
    }
  }

  function playIndex(index) {
    if (!tv.queue) return;
    const next = clampIndex(index);
    if (tv.yt && tv.ready) {
      tv.index = next;
      tv.ended = false;
      playAtSong(next);
      syncAll();
    } else {
      tuneIn(tv.queue, next);
    }
  }

  function togglePlayback() {
    if (!tv.yt || !tv.ready) return;
    if (tv.tucked) untuck();
    if (tv.ended) {
      playIndex(0);
    } else if (tv.playing) {
      tv.yt.pauseVideo();
    } else {
      tv.yt.playVideo();
    }
  }

  function tuck() {
    if (!tv.queue) return;
    tv.yt?.pauseVideo?.();
    tv.tucked = true;
    syncAll();
    tv.els.puck?.focus();
  }

  function untuck({ resume = false } = {}) {
    tv.tucked = false;
    syncAll();
    if (resume && tv.ready) tv.yt?.playVideo?.();
    tv.els.toggle?.focus();
  }

  function powerOff() {
    stopPolling();
    window.clearTimeout(tv.skipTimer);
    window.clearTimeout(tv.watchdog);
    tv.skipTimer = 0;
    tv.watchdog = 0;
    try {
      tv.yt?.destroy?.();
    } catch {}
    tv.yt = null;
    tv.ready = false;
    tv.queue = null;
    tv.playing = false;
    tv.ended = false;
    tv.blocked = false;
    tv.error = null;
    tv.loadFailed = false;
    tv.failStreak = 0;
    tv.tucked = false;
    tv.state = -1;
    tv.els.host?.replaceChildren();
    tv.root?.classList.remove('has-played', 'is-ready', 'is-playing', 'is-ended', 'is-tucked');
    syncAll();
  }

  /* The song bar: click a segment to play that song; arrow keys move along it. */

  function bindBar() {
    const { bar } = tv.els;
    if (!bar) return;
    bar.addEventListener('click', (event) => {
      const segment = event.target instanceof Element ? event.target.closest('[data-tv-tick]') : null;
      if (segment) playIndex(Number(segment.dataset.tvTick));
    });
    bar.addEventListener('keydown', (event) => {
      const segments = Array.from(bar.children);
      const at = segments.indexOf(document.activeElement);
      if (at < 0) return;
      const target = { ArrowRight: at + 1, ArrowLeft: at - 1, Home: 0, End: segments.length - 1 }[event.key];
      if (target === undefined) return;
      event.preventDefault();
      const next = segments[Math.max(0, Math.min(segments.length - 1, target))];
      for (const segment of segments) segment.tabIndex = segment === next ? 0 : -1;
      next.focus();
    });
  }

  function bindTvControls() {
    const { els } = tv;
    els.toggle?.addEventListener('click', togglePlayback);
    els.prev?.addEventListener('click', () => playIndex(tv.index - 1));
    els.next?.addEventListener('click', () => playIndex(tv.index + 1));
    els.tuck?.addEventListener('click', tuck);
    els.puck?.addEventListener('click', () => untuck({ resume: true }));
    els.power?.addEventListener('click', powerOff);
    els.external?.addEventListener('click', () => tv.yt?.pauseVideo?.());
    bindBar();
  }

  /* Keyboard: space plays and pauses, shift+arrows change tracks, arrows seek. */

  function isTypingTarget(target) {
    if (!(target instanceof Element)) return false;
    const tag = target.tagName.toLowerCase();
    return tag === 'input' || tag === 'textarea' || tag === 'select' || target.isContentEditable;
  }

  function isControlTarget(target) {
    return target instanceof Element && Boolean(target.closest('button, a, [role="slider"]'));
  }

  function bindKeyboard() {
    document.addEventListener('keydown', (event) => {
      if (isTypingTarget(event.target) || !tv.queue || !tv.ready) return;
      if (event.code === 'Space' && !isControlTarget(event.target)) {
        event.preventDefault();
        togglePlayback();
      } else if (event.key === 'ArrowRight' && event.shiftKey) {
        event.preventDefault();
        playIndex(tv.index + 1);
      } else if (event.key === 'ArrowLeft' && event.shiftKey) {
        event.preventDefault();
        playIndex(tv.index - 1);
      } else if ((event.key === 'ArrowRight' || event.key === 'ArrowLeft') && !isControlTarget(event.target)) {
        event.preventDefault();
        const now = Number(tv.yt?.getCurrentTime?.() || 0);
        tv.yt?.seekTo?.(Math.max(0, now + (event.key === 'ArrowRight' ? 10 : -10)), true);
      }
    });
  }


  /* ------------------------------------------------------------------ *
   * The record
   * ------------------------------------------------------------------ */

  let vinylScriptPromise = null;
  let activeVinyl = null;
  let vinylResizeTimer = 0;

  const VINYL_FONT_FACES = [
    ['Permanent Marker', 'permanent-marker-400.woff2'],
    ['Rock Salt', 'rock-salt-400.woff2'],
    ['Sedgwick Ave', 'sedgwick-ave-400.woff2'],
    ['Gochi Hand', 'gochi-hand-400.woff2'],
    ['Architects Daughter', 'architects-daughter-400.woff2'],
    ['Indie Flower', 'indie-flower-400.woff2'],
    ['Shadows Into Light Two', 'shadows-into-light-two-400.woff2'],
    ['Reenie Beanie', 'reenie-beanie-400.woff2'],
    ['Patrick Hand', 'patrick-hand-400.woff2'],
    ['Kalam', 'kalam-400.woff2'],
    ['Just Another Hand', 'just-another-hand-400.woff2'],
  ];

  function vinylFontCss(families) {
    const selected = Array.isArray(families) && families.length
      ? VINYL_FONT_FACES.filter(([family]) => families.includes(family))
      : VINYL_FONT_FACES;
    return selected
      .map(([family, file]) => `@font-face{font-family:"${family}";src:url("${assetBase}vinyl-fonts/${file}${assetVersion ? `?v=${encodeURIComponent(assetVersion)}` : ''}") format("woff2");font-weight:400;font-style:normal;font-display:block;}`)
      .join('\n');
  }

  function loadVinylScript() {
    if (window.MMMVinyl) return Promise.resolve(window.MMMVinyl);
    if (vinylScriptPromise) return vinylScriptPromise;
    vinylScriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = assetHref('vinyl.js');
      script.async = true;
      script.onload = () => resolve(window.MMMVinyl);
      script.onerror = () => reject(new Error('Failed to load vinyl.js'));
      document.head.append(script);
    });
    vinylScriptPromise.catch(() => {
      vinylScriptPromise = null;
    });
    return vinylScriptPromise;
  }

  function syncVinylPlayback() {
    if (!activeVinyl?.handle?.setPlaying) return;
    const live = Boolean(tv.queue && tv.queue.slug === activeVinyl.slug && !tv.ended);
    activeVinyl.handle.setPlaying(live && tv.playing);
    // The needle: which groove band is playing, and how far into it. There
    // is a band for every song, the ones that aren't on YouTube included.
    if (typeof activeVinyl.handle.setProgress === 'function') {
      const duration = Number(tv.yt?.getDuration?.() || 0);
      const current = Number(tv.yt?.getCurrentTime?.() || 0);
      const index = live ? rowForSong(tv.index) : -1;
      const fraction = index >= 0 && duration > 0 ? Math.min(1, Math.max(0, current / duration)) : 0;
      activeVinyl.handle.setProgress(index, fraction);
    }
  }

  // Picking the groove of a song that isn't on YouTube: "Not on YouTube" for
  // a moment, just above where it was clicked, or over the middle of the
  // record from the keyboard. Screen readers hear the song's name with it.
  const VINYL_NOTE_MS = 2200;
  let vinylNoteTimer = 0;

  function showVinylNote(art, point, title) {
    const note = art?.parentElement?.querySelector('[data-vinyl-note]');
    if (!note) return;
    const box = art.getBoundingClientRect();
    let x = point?.x;
    let y = point?.y;
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      const frame = stageFrame(art);
      x = ((frame.x + 1) / 2) * box.width;
      y = ((1 - frame.y) / 2) * box.height;
    }
    note.style.setProperty('--note-x', `${Math.round(Math.min(Math.max(x, 80), box.width - 80))}px`);
    note.style.setProperty('--note-y', `${Math.round(Math.max(y, 48))}px`);
    const name = document.createElement('span');
    name.className = 'sr-only';
    name.textContent = title ? `${title}. ` : '';
    note.replaceChildren(name, 'Not on YouTube');
    note.classList.remove('is-shown');
    void note.offsetWidth;
    note.classList.add('is-shown');
    window.clearTimeout(vinylNoteTimer);
    vinylNoteTimer = window.setTimeout(() => {
      note.classList.remove('is-shown');
      // Empty once it has faded, so a screen reader doesn't find it later.
      vinylNoteTimer = window.setTimeout(() => {
        vinylNoteTimer = 0;
        note.replaceChildren();
      }, 400);
    }, VINYL_NOTE_MS);
  }

  // Tracklist rows and record bands mirror each other's hover.
  function markGrooveHover(index) {
    for (const item of document.querySelectorAll('[data-tracklist] [data-track-index]')) {
      item.classList.toggle('is-groove-hover', Number(item.dataset.trackIndex) === index);
    }
  }

  function bindTracklistToVinyl(scope) {
    const list = scope.querySelector('[data-tracklist]');
    if (!list || list.dataset.vinylBound) return;
    list.dataset.vinylBound = 'true';
    const highlight = (index) => activeVinyl?.handle?.setHighlight?.(index);
    list.addEventListener('pointerover', (event) => {
      const item = event.target instanceof Element ? event.target.closest('[data-track-index]') : null;
      if (item) highlight(Number(item.dataset.trackIndex));
    });
    list.addEventListener('pointerleave', () => highlight(-1));
    list.addEventListener('focusin', (event) => {
      const item = event.target instanceof Element ? event.target.closest('[data-track-index]') : null;
      if (item) highlight(Number(item.dataset.trackIndex));
    });
    list.addEventListener('focusout', () => highlight(-1));
  }

  function teardownVinyl() {
    window.clearTimeout(vinylResizeTimer);
    vinylResizeTimer = 0;
    if (activeVinyl?.resizeHandler) {
      window.removeEventListener('resize', activeVinyl.resizeHandler);
      window.removeEventListener('orientationchange', activeVinyl.resizeHandler);
    }
    try {
      activeVinyl?.handle?.destroy?.();
    } catch {}
    activeVinyl = null;
  }

  // On a mix page the record and its sleeve fill a box on the stage: beside
  // the words on wide or short-and-wide screens, above them on narrow ones.
  // The box is measured, not guessed, so the record never runs under the
  // words, the header or the player card. It is worked out in page
  // coordinates against the first screenful, and handed to the renderer in
  // the canvas's own NDC: centre x/y and half-extents w/h.
  function stageFrame(art = document.querySelector('.mix-hero--stage .mix-hero__art')) {
    const fallback = window.matchMedia('(min-width: 961px)').matches ? { x: 0.4, y: -0.1 } : { x: 0, y: 0.04 };
    const rect = art?.getBoundingClientRect();
    if (!rect || rect.width < 40 || rect.height < 40) return fallback;
    const scrollY = window.scrollY || 0;
    const box = { left: rect.left, right: rect.right, top: rect.top + scrollY, bottom: rect.bottom + scrollY, width: rect.width, height: rect.height };
    const body = art.closest('.mix-hero--stage')?.querySelector('.mix-hero__body');
    const beside = window.matchMedia('(min-width: 961px), (orientation: landscape) and (max-height: 520px)').matches;
    const headerHeight = document.querySelector('.site-header')?.offsetHeight || 0;
    const pad = Math.round(Math.min(36, Math.max(12, box.width * 0.022)));
    let left = box.left + pad;
    let right = box.right - pad;
    let top = Math.max(box.top, headerHeight) + pad;
    let bottom = Math.min(box.bottom, Math.max(box.top + 160, window.innerHeight)) - pad;
    if (body && beside) {
      left = Math.max(left, body.getBoundingClientRect().right + Math.max(24, pad));
    } else if (body) {
      // The words start a little over the record's lower edge, under the wash.
      const first = body.firstElementChild?.getBoundingClientRect();
      if (first) bottom = Math.min(bottom, first.top + scrollY + Math.min(90, box.height * 0.12));
    }
    // An open player card is fixed to the bottom right of the window: give it
    // up whichever strip of the box costs less.
    const tv = document.querySelector('[data-tv]');
    const card = tv && !tv.hidden && !tv.classList.contains('is-tucked') ? tv.querySelector('.tv__card') : null;
    const c = card?.getBoundingClientRect();
    if (c && c.width && c.left < right && c.right > left && c.top < bottom && c.bottom > top) {
      const gap = 16;
      const keepAbove = (bottom - top) > 0 ? (Math.min(bottom, c.top - gap) - top) * (right - left) : 0;
      const keepLeft = (Math.min(right, c.left - gap) - left) * (bottom - top);
      if (keepAbove >= keepLeft) bottom = Math.min(bottom, c.top - gap);
      else right = Math.min(right, c.left - gap);
    }
    if (right - left < 80 || bottom - top < 80) return fallback;
    return {
      x: (((left + right) / 2 - box.left) / box.width) * 2 - 1,
      y: 1 - (((top + bottom) / 2 - box.top) / box.height) * 2,
      w: (right - left) / box.width,
      h: (bottom - top) / box.height,
    };
  }

  // Where the flat cover sits, as fractions of the art box, so the WebGL
  // sleeve can take over on exactly that rectangle.
  function coverStartRect(art) {
    const cover = art?.querySelector('.mix-hero__cover');
    const a = art?.getBoundingClientRect();
    const c = cover?.getBoundingClientRect();
    if (!a || !c || !a.width || !a.height || !c.width) return null;
    return { x: (c.left - a.left) / a.width, y: (c.top - a.top) / a.height, w: c.width / a.width, h: c.height / a.height };
  }

  async function initVinyl(scope, mixPayload) {
    const vinylPayload = readJsonScript(scope, '[data-vinyl-payload]');
    const mount = scope.querySelector('[data-vinyl-mount]');
    if (!vinylPayload || !mount) return;
    try {
      const MMMVinyl = await loadVinylScript();
      // The first WebGL call of a page blocks until the browser's GPU side
      // is up. Straight after load that was a 230 to 270ms task on a cold
      // start; once the page has painted and gone idle it costs a few ms.
      // The flat cover holds the stage meanwhile.
      await new Promise((resolve) => {
        if (window.requestIdleCallback) window.requestIdleCallback(() => resolve(), { timeout: 600 });
        else window.setTimeout(resolve, 200);
      });
      if (!document.documentElement.contains(mount)) return;
      if (!MMMVinyl?.isSupported?.()) return;

      teardownVinyl();
      const vinylKey = vinylPayload.key || vinylPayload.title || 'mount';
      const fontFamilies = typeof MMMVinyl.facesFor === 'function'
        ? MMMVinyl.facesFor(vinylKey)
        : [];
      const art = mount.closest('.mix-hero__art');
      const onStage = Boolean(mount.closest('.mix-hero--stage'));
      // Where a groove was picked, for the note; null from the keyboard.
      let pickPoint = null;
      if (art) {
        art.addEventListener('pointerdown', (event) => {
          const box = art.getBoundingClientRect();
          pickPoint = { x: event.clientX - box.left, y: event.clientY - box.top };
        }, { capture: true });
        art.addEventListener('keydown', () => {
          pickPoint = null;
        }, { capture: true });
      }
      const resizeHandler = () => {
        window.clearTimeout(vinylResizeTimer);
        vinylResizeTimer = window.setTimeout(() => {
          if (onStage) activeVinyl?.handle?.setFrame?.(stageFrame(art));
          activeVinyl?.handle?.resize?.();
        }, 120);
      };
      const number = String(vinylPayload.number || '').padStart(3, '0');
      const handle = MMMVinyl.mount(mount, {
        ...vinylPayload,
        imageAlt: `${vinylPayload.title}, Mix No.${number}. The record in front of its sleeve.`,
        describedBy: vinylPayload.describedBy || vinylPayload.hintId,
        // The page has already fetched and decoded the cover for the flat
        // <img>; the renderer paints its sleeve from that instead of fetching
        // it a second time.
        coverImage: art?.querySelector('.mix-hero__cover img') || null,
        intro: true,
        ...(onStage ? { layout: 'stack', frame: stageFrame(), startRect: coverStartRect(art) } : {}),
        reducedMotion: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
        // The faces are declared once, in site.css; the renderer only loads
        // the ones this mix uses. Injecting a second set here, with ?v, made
        // every face download twice.
        fontFamilies,
        onTrackHover: (index) => markGrooveHover(index),
        // A groove is a tracklist row. One whose song isn't on YouTube plays
        // nothing: a small note says so instead.
        onTrackPick: (row) => {
          if (!mixPayload || !Number.isInteger(row) || row < 0) return;
          const index = songForRow(mixPayload, row);
          if (index < 0) {
            showVinylNote(art, pickPoint, vinylPayload.tracks?.[row]?.title);
            return;
          }
          playFromPage(mixPayload, index);
        },
        onReady: (readyHandle) => {
          if (activeVinyl?.handle !== readyHandle || readyHandle.error) return;
          art?.classList.add('is-vinyl-mounted');
          if (Array.isArray(vinylPayload.durations) && vinylPayload.durations.length) {
            readyHandle.setTracks?.(vinylPayload.durations);
            if (mixPayload) {
              const queued = new Set(queueRows(mixPayload));
              readyHandle.setUnplayable?.(vinylPayload.durations.map((_, row) => row).filter((row) => !queued.has(row)));
            }
          }
          syncVinylPlayback();
        },
        // If the GPU drops the context the flat cover comes back until the
        // renderer has rebuilt itself.
        onContextLost: () => art?.classList.remove('is-vinyl-mounted'),
        onContextRestored: (restored) => {
          if (activeVinyl?.handle === restored) art?.classList.add('is-vinyl-mounted');
        },
      });
      activeVinyl = {
        handle,
        slug: String(mixPayload?.slug || ''),
        resizeHandler,
      };
      window.addEventListener('resize', resizeHandler);
      window.addEventListener('orientationchange', resizeHandler);
      if (onStage) {
        // Reframe when the player card opens, closes or tucks away, so the
        // spinning record and its label stay clear of the card.
        const tvRoot = document.querySelector('[data-tv]');
        let reframeQueued = 0;
        const reframe = () => {
          if (reframeQueued) return;
          reframeQueued = window.requestAnimationFrame(() => {
            reframeQueued = 0;
            if (activeVinyl?.handle === handle) handle.setFrame?.(stageFrame(art));
          });
        };
        const watcher = new MutationObserver(reframe);
        if (tvRoot) watcher.observe(tvRoot, { attributes: true, attributeFilter: ['hidden', 'class'] });
        watcher.observe(document.body, { attributes: true, attributeFilter: ['class'] });
        const destroyHandle = handle.destroy;
        handle.destroy = () => {
          watcher.disconnect();
          if (reframeQueued) window.cancelAnimationFrame(reframeQueued);
          destroyHandle();
        };
      }
      bindTracklistToVinyl(scope);
      syncVinylPlayback();
    } catch {}
  }

  /* ------------------------------------------------------------------ *
   * Discovery (search + filter)
   * ------------------------------------------------------------------ */

  /* ------------------------------------------------------------------ *
   * Discovery (search + filter)
   * ------------------------------------------------------------------ */

  // A chip's value ("texture:covers", "state:has-highlights", "tag:indie") is
  // stored as-is in each card's data-discovery-filters, so test that first.
  // Anything unrecognised matches nothing rather than everything.
  function matchesFilter(item, filterValue) {
    if (!filterValue || filterValue === 'all') return true;
    if (readPipeSet(item.dataset.discoveryFilters).has(filterValue.trim().toLowerCase())) return true;
    const [kind, ...rest] = filterValue.split(':');
    const value = normalizeDiscoveryText(rest.join(':')).replace(/\s+/g, '-');
    if (kind === 'tag') return readPipeSet(item.dataset.discoveryTags).has(value);
    if (kind === 'state') return readPipeSet(item.dataset.discoveryStates).has(value);
    return false;
  }

  // "One mix matches.", "Three mixes match.", "12 mixes match."
  const DISCOVERY_NUMBER_WORDS = ['No', 'One', 'Two', 'Three', 'Four'];

  function discoveryCountLine(count, singular, plural) {
    const number = count < DISCOVERY_NUMBER_WORDS.length ? DISCOVERY_NUMBER_WORDS[count] : String(count);
    return `${number} ${count === 1 ? singular : plural} ${count === 1 ? 'matches' : 'match'}.`;
  }

  function matchesQuery(item, query) {
    if (!query) return true;
    const haystack = normalizeDiscoveryText(item.dataset.discoverySearch);
    return query.split(' ').filter(Boolean).every((term) => haystack.includes(term));
  }

  function updateDiscovery(root) {
    const items = Array.from(root.parentElement.querySelectorAll('[data-discovery-item]'));
    const input = root.querySelector('[data-discovery-input]');
    const summary = root.querySelector('[data-discovery-summary]');
    const emptyState = root.parentElement.querySelector('[data-discovery-empty]');
    const buttons = Array.from(root.querySelectorAll('[data-discovery-filter]'));
    const activeButton = buttons.find((button) => button.getAttribute('aria-pressed') === 'true');
    const filterValue = activeButton?.dataset.discoveryFilter || 'all';
    const query = normalizeDiscoveryText(input?.value || '');
    let visibleCount = 0;

    for (const item of items) {
      const visible = matchesFilter(item, filterValue) && matchesQuery(item, query);
      item.hidden = !visible;
      if (visible) visibleCount += 1;
    }

    if (summary) {
      const singular = root.dataset.itemLabelSingular || 'item';
      const plural = root.dataset.itemLabelPlural || 'items';
      summary.textContent = query || filterValue !== 'all'
        ? discoveryCountLine(visibleCount, singular, plural)
        : `Showing all ${visibleCount} ${visibleCount === 1 ? singular : plural}.`;
    }

    if (emptyState) emptyState.hidden = visibleCount !== 0;
  }

  function initDiscovery(root) {
    const input = root.querySelector('[data-discovery-input]');
    const buttons = Array.from(root.querySelectorAll('[data-discovery-filter]'));

    if (input) input.addEventListener('input', () => updateDiscovery(root));

    for (const button of buttons) {
      button.addEventListener('click', () => {
        for (const candidate of buttons) {
          const isActive = candidate === button;
          candidate.classList.toggle('is-active', isActive);
          candidate.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        }
        updateDiscovery(root);
      });
    }

    updateDiscovery(root);
  }

  /* ------------------------------------------------------------------ *
   * Page wiring (runs on initial load and after every pjax swap)
   * ------------------------------------------------------------------ */

  function readMixPayload(scope) {
    return readJsonScript(scope, '[data-mix-payload]');
  }

  function parseTrackHash() {
    const match = /(?:^|[#&])t=(\d+)/.exec(window.location.hash || '');
    if (!match) return null;
    const oneBased = Number(match[1]);
    return Number.isInteger(oneBased) && oneBased >= 1 ? oneBased - 1 : null;
  }

  const REVEAL_SELECTOR = [
    '.section-block',
    '.mix-card',
    '.about-hero',
    '.about-intro',
    '.about-chapter',
    '.about-stats__item',
    '.about-closing',
    '.cover-marquee',
    '.page-intro',
  ].join(', ');

  let revealObserver = null;

  function revealEverything() {
    for (const element of document.querySelectorAll('.reveal:not(.is-revealed)')) {
      element.classList.add('is-revealed');
    }
  }

  function initReveal(scope) {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if (!('IntersectionObserver' in window)) return;
    // Degenerate viewports (0-size embeds, some headless captures) never
    // intersect anything — content must not depend on the observer there.
    if (!window.innerHeight || !window.innerWidth) return;

    if (!revealObserver) {
      revealObserver = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (entry.isIntersecting) {
              entry.target.classList.add('is-revealed');
              revealObserver.unobserve(entry.target);
            }
          }
        },
        { threshold: 0.08, rootMargin: '0px 0px -8% 0px' }
      );
    }

    let cardIndex = 0;
    let marked = 0;
    for (const element of scope.querySelectorAll(REVEAL_SELECTOR)) {
      if (element.classList.contains('reveal')) continue;
      element.classList.add('reveal');
      marked += 1;
      if (element.classList.contains('mix-card') || element.classList.contains('about-stats__item')) {
        element.style.setProperty('--reveal-delay', `${(cardIndex % 6) * 70}ms`);
        cardIndex += 1;
      }
      revealObserver.observe(element);
    }

    // Failsafe: if the observer revealed nothing shortly after marking (broken
    // IO, exotic embed), show everything rather than leave a blank page.
    if (marked > 0) {
      window.setTimeout(() => {
        if (!document.querySelector('.reveal.is-revealed')) revealEverything();
      }, 1500);
    }
  }

  /* Hand marks and notes, in pencil (handMark() and handNote() in build.js).
     A mark's SVG is its box and its shape. rough.js (assets/rough.js, loaded
     just before this file) redraws it as two sketchy graphite passes along
     the same paths, at the box's measured size, seeded per mark so it looks
     the same on every visit, and draws it again when the window resizes. A
     star is drawn as a doodled one. Notes get a small seeded tilt per word
     and are written on in a line wipe at a steady pen speed.
     Marks are only drawn once they come near the screen, so the work stays
     off the first paint, and are written on in order as they come into
     view: a note's own arrow follows its words, or leads them when it comes
     first. With reduced motion everything is simply there. Without rough.js
     the clean SVG paths draw on instead (sizeHandMarks keeps their pen even). */
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const PENCIL = { bowing: 1.2, msChar: 30, jitter: 1.3, lineGap: 140 };
  // Per kind: how many points of the mark's path the pencil follows (rough.js
  // bends its own line between them), how rough it goes, and how far a pass
  // may stray in pixels. rough.js strays up to 2px by default, which turns a
  // 30px arrow into string, so small marks stray less. An arrowhead is
  // three points, drawn a little steadier.
  const PENCIL_KINDS = {
    underline: { points: 8, roughness: 1, offset: 1.4 },
    circle: { points: 16, roughness: 0.9, offset: 1 },
    bracket: { points: 12, roughness: 0.8, offset: 0.6 },
    arrow: { points: 5, roughness: 0.9, offset: 0.8 },
    hook: { points: 6, roughness: 0.9, offset: 0.7 },
    star: { points: 0, roughness: 0.9, offset: 0.7 },
    reach: { points: 12, roughness: 1, offset: 1.2 },
    drop: { points: 12, roughness: 1, offset: 1.2 },
    scribble: { points: 24, roughness: 0.8, offset: 0.8 },
  };
  const PENCIL_HEAD = { points: 3, roughness: 0.6, offset: 0.5 };
  const PENCIL_EASE = 'cubic-bezier(0.65, 0.05, 0.36, 1)';
  const HAND_MARK_FIRST_SCREEN_MS = 600;
  const HAND_MARK_LATE_DELAY_MS = 150;
  let handMarkObserver = null;
  let pencilNearObserver = null;
  let handMarkResizeTimer = 0;
  let handMarkResizeBound = false;
  let handMarksShownAt = 0;
  let pencilProbe = null;
  // How many marks were drawn and how long it took, for checking the cost.
  const pencilStats = { marks: 0, ms: 0 };

  // A star as people doodle it (in the star mark's 44 x 42 box): one line,
  // five points, crossing itself, started bottom left and not quite closed.
  const DOODLE_STAR = (() => {
    const P = [0, 1, 2, 3, 4].map((k) => {
      const a = ((-90 + k * 72) * Math.PI) / 180;
      return [22 + 19.5 * Math.cos(a), 22.5 + 19.5 * Math.sin(a)];
    });
    return [
      [P[3][0] - 0.6, P[3][1] + 0.8],
      [P[0][0] + 0.8, P[0][1] - 0.4],
      [P[2][0] + 0.4, P[2][1] + 0.6],
      [P[4][0] - 0.8, P[4][1] + 0.6],
      [P[1][0] + 0.9, P[1][1] - 0.3],
      [P[3][0] + 2.4, P[3][1] - 2.2],
    ];
  })();

  function pencilHash(text) {
    let h = 2166136261;
    for (let i = 0; i < text.length; i += 1) {
      h ^= text.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  function pencilRandom(seed) {
    let a = seed >>> 0;
    return () => {
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function pencilStill() {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function pencilCanDraw() {
    return typeof window.rough?.svg === 'function';
  }

  // A time from a custom property ("650ms", "1.2s"), or the fallback.
  function msVar(element, name, fallback) {
    const value = window.getComputedStyle(element).getPropertyValue(name).trim();
    const number = parseFloat(value);
    if (!Number.isFinite(number)) return fallback;
    return value.endsWith('ms') ? number : value.endsWith('s') ? number * 1000 : number;
  }

  function sizeHandMarks(scope) {
    for (const svg of scope.querySelectorAll('[data-hand-mark]:not(.is-pencil)')) {
      const box = svg.viewBox?.baseVal;
      const rect = svg.getBoundingClientRect();
      if (!box?.width || !box.height || !rect.width || !rect.height) continue;
      // The narrower axis sets the pen; the other reads as pressure.
      const scale = Math.min(rect.width / box.width, rect.height / box.height);
      const pen = parseFloat(window.getComputedStyle(svg).getPropertyValue('--pen')) || 2;
      svg.style.strokeWidth = (pen / scale).toFixed(3);
    }
  }

  // The mark's own paths, sampled once in its viewBox units.
  function pencilSource(svg) {
    if (svg._pencil) return svg._pencil;
    if (!pencilProbe) {
      pencilProbe = document.createElementNS(SVG_NS, 'svg');
      pencilProbe.setAttribute('aria-hidden', 'true');
      pencilProbe.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden;visibility:hidden;pointer-events:none';
      document.body.append(pencilProbe);
    }
    const box = svg.viewBox.baseVal;
    const kind = (/hand-mark--(\w+)/.exec(svg.getAttribute('class') || '') || [])[1] || '';
    const strokes = [...svg.querySelectorAll(':scope > path')].map((path) => {
      const probe = document.createElementNS(SVG_NS, 'path');
      probe.setAttribute('d', path.getAttribute('d'));
      pencilProbe.append(probe);
      const length = probe.getTotalLength();
      const points = [];
      for (let i = 0; i <= 32; i += 1) {
        const point = probe.getPointAtLength((length * i) / 32);
        points.push([point.x, point.y]);
      }
      probe.remove();
      return points;
    });
    const index = [...document.querySelectorAll('[data-hand-mark]')].indexOf(svg);
    svg._pencil = {
      kind,
      vw: box.width,
      vh: box.height,
      stretch: svg.getAttribute('preserveAspectRatio') === 'none',
      strokes,
      seed: pencilHash(`${window.location.pathname}|${kind}|${index}`),
    };
    return svg._pencil;
  }

  function pencilThin(points, count) {
    if (points.length <= count) return points;
    return Array.from({ length: count }, (_, i) => points[Math.round((i * (points.length - 1)) / (count - 1))]);
  }

  function pencilParts(svg) {
    return [...svg.querySelectorAll(':scope > .pencil path')];
  }

  function hidePencil(svg) {
    for (const path of pencilParts(svg)) {
      const length = path.getTotalLength() + 4;
      path._length = length;
      path.style.strokeDasharray = `${length} ${length}`;
      path.style.strokeDashoffset = `${length}`;
    }
  }

  // Draws (or draws again) a mark in pencil at its box's size. Stretchy marks
  // fill the box; the others keep their shape, centred. Returns false while
  // the box has no size yet (a note that's still hidden).
  function drawPencilMark(svg) {
    const started = performance.now();
    const style = window.getComputedStyle(svg);
    const w = parseFloat(style.width);
    const h = parseFloat(style.height);
    if (!(w > 0 && h > 0)) return false;
    const src = pencilSource(svg);
    const pen = parseFloat(style.getPropertyValue('--pen')) || 2;
    let sx;
    let sy;
    let ox = 0;
    let oy = 0;
    if (src.stretch) {
      sx = w / src.vw;
      sy = h / src.vh;
    } else {
      const s = Math.min(w / src.vw, h / src.vh);
      sx = s;
      sy = s;
      ox = (w - src.vw * s) / 2;
      oy = (h - src.vh * s) / 2;
    }
    const map = ([x, y]) => [ox + x * sx, oy + y * sy];
    const rc = window.rough.svg(svg);
    const kind = PENCIL_KINDS[src.kind] || PENCIL_KINDS.scribble;
    const options = (spec) => ({
      stroke: 'currentColor',
      strokeWidth: Number((pen * (src.kind === 'underline' ? 1.05 : 0.85)).toFixed(2)),
      roughness: spec.roughness,
      maxRandomnessOffset: spec.offset,
      bowing: PENCIL.bowing,
      seed: (src.seed % 10000) + 1,
      disableMultiStroke: false,
    });
    const nodes = src.kind === 'star'
      ? [rc.linearPath(DOODLE_STAR.map(map), options(kind))]
      : src.strokes.map((stroke, i) => {
          const spec = i === 0 ? kind : PENCIL_HEAD;
          const points = pencilThin(stroke, spec.points).map(map);
          return i === 0 ? rc.curve(points, options(spec)) : rc.linearPath(points, options(spec));
        });
    svg.querySelector(':scope > .pencil')?.remove();
    const group = document.createElementNS(SVG_NS, 'g');
    group.setAttribute('class', 'pencil');
    nodes.forEach((node, i) => {
      for (const path of node.querySelectorAll('path')) {
        path.setAttribute('fill', 'none');
        if (i > 0) path.dataset.head = '';
      }
      group.append(node);
    });
    svg.setAttribute('viewBox', `0 0 ${w.toFixed(2)} ${h.toFixed(2)}`);
    svg.append(group);
    svg.classList.add('is-pencil');
    svg._pencilSize = `${w}x${h}`;
    if (!svg._pencilShown) hidePencil(svg);
    pencilStats.marks += 1;
    pencilStats.ms += performance.now() - started;
    return true;
  }

  // Writes a mark on: its main stroke (both passes) over `duration`, then any
  // head. Without rough.js the clean paths draw on through their CSS.
  function playPencilMark(svg, delay, duration) {
    const drawn = svg.classList.contains('is-pencil') || (pencilCanDraw() && drawPencilMark(svg));
    if (!drawn) {
      sizeHandMarks(svg.parentElement || document);
      svg.style.setProperty('--draw-delay', `${delay}ms`);
      svg.style.setProperty('--draw-duration', `${duration}ms`);
      svg.classList.remove('is-drawn');
      void svg.getBoundingClientRect();
      svg.classList.add('is-drawn');
      return;
    }
    svg._pencilShown = true;
    const parts = pencilParts(svg);
    if (pencilStill()) {
      for (const path of parts) {
        path.style.strokeDasharray = '';
        path.style.strokeDashoffset = '';
      }
      return;
    }
    hidePencil(svg);
    const run = (path, start, length, easing) => {
      for (const old of path.getAnimations()) old.cancel();
      const animation = path.animate([{ strokeDashoffset: path._length }, { strokeDashoffset: 0 }], {
        duration: length,
        delay: start,
        easing,
        fill: 'both',
      });
      animation.onfinish = () => {
        path.style.strokeDasharray = '';
        path.style.strokeDashoffset = '';
        animation.cancel();
      };
    };
    const main = parts.filter((path) => !('head' in path.dataset));
    const heads = parts.filter((path) => 'head' in path.dataset);
    const each = main.length ? duration / main.length : duration;
    main.forEach((path, i) => run(path, delay + i * each * 0.92, each, PENCIL_EASE));
    heads.forEach((path, i) => run(path, delay + duration - 40 + i * 120, 240, 'ease-out'));
  }

  // Each word sits a little off, the way handwriting does: a tilt, a lift and
  // a size, seeded by the note's words so it's the same on every visit.
  function wordJitter(text) {
    const random = pencilRandom(pencilHash(`${text}pencil`));
    return text.split(' ').map((word) => ({
      word,
      r: `${((random() - 0.5) * 2.4 * PENCIL.jitter).toFixed(2)}deg`,
      y: `${((random() - 0.5) * 0.1 * PENCIL.jitter).toFixed(3)}em`,
      s: (1 + (random() - 0.5) * 0.07 * PENCIL.jitter).toFixed(3),
    }));
  }

  function prepNote(note) {
    if (note.dataset.pencil !== undefined) return;
    const text = note.textContent.replace(/\s+/g, ' ').trim();
    note.dataset.pencil = '';
    if (!text) return;
    const words = wordJitter(text);
    note.textContent = '';
    words.forEach(({ word, r, y, s }, i) => {
      const span = document.createElement('span');
      span.className = 'hw';
      span.textContent = word;
      span.style.setProperty('--r', r);
      span.style.setProperty('--y', y);
      span.style.setProperty('--s', s);
      note.append(span);
      if (i < words.length - 1) note.append(' ');
    });
  }

  // Writes a note on, a word at a time, at a steady pen speed, with a small
  // pause at each new line. Returns how long that takes.
  function writeNote(note, delay) {
    prepNote(note);
    note.classList.remove('is-unwritten');
    const words = [...note.querySelectorAll(':scope > .hw')];
    if (pencilStill() || !words.length) return 0;
    let at = 0;
    let lastTop = null;
    for (const word of words) {
      const top = word.offsetTop;
      if (lastTop !== null && top > lastTop + 4) at += PENCIL.lineGap;
      lastTop = top;
      const duration = Math.max(60, word.textContent.length * PENCIL.msChar);
      for (const old of word.getAnimations()) old.cancel();
      word.classList.add('is-writing');
      const animation = word.animate(
        [
          { maskPosition: '100% 0', webkitMaskPosition: '100% 0' },
          { maskPosition: '0% 0', webkitMaskPosition: '0% 0' },
        ],
        { duration, delay: delay + at, easing: 'linear', fill: 'both' }
      );
      animation.onfinish = () => {
        word.classList.remove('is-writing');
        animation.cancel();
      };
      at += duration + PENCIL.msChar * 0.9;
    }
    return at;
  }

  // The marks that belong to a note: an arrow beside it, in the same wrapper.
  function noteMarks(note) {
    return [...(note.parentElement?.children || [])].filter((child) => child !== note && child.matches('[data-hand-mark]'));
  }

  // A note and its arrow play in the order they sit: an arrow that comes
  // first leads the words, one that comes after follows them.
  function playNoteGroup(note, delay) {
    const marks = noteMarks(note);
    const before = marks.filter((mark) => mark.compareDocumentPosition(note) & Node.DOCUMENT_POSITION_FOLLOWING);
    const after = marks.filter((mark) => !before.includes(mark));
    let start = delay;
    for (const mark of before) {
      const duration = msVar(mark, '--draw-duration', 420);
      playPencilMark(mark, start, duration);
      start += duration * 0.75;
    }
    const length = writeNote(note, start);
    for (const mark of after) playPencilMark(mark, start + length + 60, msVar(mark, '--draw-duration', 480));
  }

  // After a resize (or once the fonts arrive) a box can change size; draw
  // those marks again, as they stand.
  function redrawPencil(root) {
    if (!pencilCanDraw()) {
      sizeHandMarks(root);
      return;
    }
    for (const svg of root.querySelectorAll('.hand-mark.is-pencil')) {
      const style = window.getComputedStyle(svg);
      if (`${parseFloat(style.width)}x${parseFloat(style.height)}` === svg._pencilSize) continue;
      if (svg.getAnimations({ subtree: true }).some((animation) => animation.playState === 'running')) continue;
      drawPencilMark(svg);
    }
  }

  function whenIdle(work) {
    if ('requestIdleCallback' in window) window.requestIdleCallback(work, { timeout: 1500 });
    else window.setTimeout(work, 200);
  }

  function initHandMarks(scope) {
    const marks = [...scope.querySelectorAll('[data-hand-mark]')];
    const notes = [...scope.querySelectorAll('.hand-note')];
    if (!marks.length && !notes.length) return;
    const canDraw = pencilCanDraw();
    document.documentElement.classList.toggle('has-pencil', canDraw);
    if (!canDraw) sizeHandMarks(scope);
    if (!handMarkResizeBound) {
      handMarkResizeBound = true;
      window.addEventListener('resize', () => {
        window.clearTimeout(handMarkResizeTimer);
        handMarkResizeTimer = window.setTimeout(() => redrawPencil(document), 180);
      });
      document.fonts?.ready?.then(() => redrawPencil(document));
    }

    // Captions on the home wall only show under the pointer: they take their
    // tilt when the page is idle and are never written on. "It's on now."
    // is written each time site.js moves it (placeNowNote).
    const captions = notes.filter((note) => note.classList.contains('home-wall__caption'));
    const written = notes.filter((note) => !captions.includes(note) && !note.closest('[data-track-now]'));
    if (captions.length) whenIdle(() => captions.forEach(prepNote));
    written.forEach(prepNote);
    const owned = new Set(notes.flatMap(noteMarks));
    const standalone = marks.filter((mark) => !owned.has(mark));

    const still = pencilStill();
    const watching = 'IntersectionObserver' in window && window.innerHeight > 0;
    if (!watching) {
      for (const mark of marks) {
        mark._pencilShown = true;
        if (!(canDraw && drawPencilMark(mark))) mark.classList.add('is-drawn');
      }
      return;
    }

    // Near the screen: draw (hidden until it's written on, unless still).
    if (canDraw) {
      pencilNearObserver?.disconnect();
      pencilNearObserver = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (!entry.isIntersecting) continue;
            if (still) entry.target._pencilShown = true;
            if (drawPencilMark(entry.target)) pencilNearObserver.unobserve(entry.target);
          }
        },
        { rootMargin: '320px 0px' }
      );
      for (const mark of marks) pencilNearObserver.observe(mark);
    }
    if (still) {
      if (!canDraw) for (const mark of marks) mark.classList.add('is-drawn');
      return;
    }

    // In view: write on. A delay times a mark or note against the first
    // screen; one that only comes into view later starts almost at once.
    for (const note of written) note.classList.add('is-unwritten');
    handMarksShownAt = performance.now();
    handMarkObserver?.disconnect();
    handMarkObserver = new IntersectionObserver(
      (entries) => {
        const late = performance.now() - handMarksShownAt > HAND_MARK_FIRST_SCREEN_MS;
        const timed = (delay) => (late ? Math.min(delay, HAND_MARK_LATE_DELAY_MS) : delay);
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const target = entry.target;
          handMarkObserver.unobserve(target);
          if (target.classList.contains('hand-note')) {
            playNoteGroup(target, timed(msVar(target, '--note-delay', 0)));
          } else {
            playPencilMark(target, timed(msVar(target, '--draw-delay', 0)), msVar(target, '--draw-duration', 850));
          }
        }
      },
      { threshold: 0.5 }
    );
    for (const target of [...standalone, ...written]) handMarkObserver.observe(target);
  }

  function initParallaxField(scope) {
    const field = scope.querySelector('[data-parallax-field]');
    if (!field) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if (window.matchMedia('(pointer: coarse)').matches) return;

    let raf = 0;
    field.addEventListener('pointermove', (event) => {
      if (raf) return;
      raf = window.requestAnimationFrame(() => {
        raf = 0;
        const rect = field.getBoundingClientRect();
        const px = ((event.clientX - rect.left) / rect.width - 0.5) * 2;
        const py = ((event.clientY - rect.top) / rect.height - 0.5) * 2;
        field.style.setProperty('--px', px.toFixed(3));
        field.style.setProperty('--py', py.toFixed(3));
      });
    });
    field.addEventListener('pointerleave', () => {
      field.style.setProperty('--px', '0');
      field.style.setProperty('--py', '0');
    });
  }

  function animateCount(element, target) {
    const duration = 1400;
    const start = performance.now();
    const step = (now) => {
      const progress = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      element.textContent = String(Math.round(target * eased));
      if (progress < 1) window.requestAnimationFrame(step);
    };
    window.requestAnimationFrame(step);
  }

  function initCountUps(scope) {
    const values = scope.querySelectorAll('[data-count]');
    if (!values.length) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if (!('IntersectionObserver' in window) || !window.innerHeight) return;

    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const target = Number(entry.target.dataset.count);
        if (Number.isFinite(target)) {
          entry.target.textContent = '0';
          animateCount(entry.target, target);
        }
        observer.unobserve(entry.target);
      }
    }, { threshold: 0.4 });

    for (const value of values) observer.observe(value);
  }

  // Home: the wall of covers only drifts while some of it is on screen.
  let homeWallObserver = null;

  function initHomeWall(scope) {
    homeWallObserver?.disconnect();
    homeWallObserver = null;
    const wall = scope.querySelector('[data-home-wall]');
    if (!wall || !('IntersectionObserver' in window)) return;
    homeWallObserver = new IntersectionObserver((entries) => {
      for (const entry of entries) wall.classList.toggle('is-still', !entry.isIntersecting);
    });
    homeWallObserver.observe(wall);
  }

  // About: the floating covers, the scroll cue and the drifting rows only
  // move while they're on screen and the tab is in view (.is-still pauses
  // them, the same way as the home wall).
  let stillAwayObserver = null;
  let stillAwayBound = false;

  function syncStillAway() {
    const away = document.visibilityState === 'hidden';
    for (const element of document.querySelectorAll('[data-still-away]')) {
      element.classList.toggle('is-still', away || element.dataset.offscreen === 'true');
    }
  }

  function initStillAway(scope) {
    stillAwayObserver?.disconnect();
    stillAwayObserver = null;
    const elements = scope.querySelectorAll('[data-still-away]');
    if (!elements.length || !('IntersectionObserver' in window)) return;
    stillAwayObserver = new IntersectionObserver((entries) => {
      for (const entry of entries) entry.target.dataset.offscreen = entry.isIntersecting ? 'false' : 'true';
      syncStillAway();
    });
    for (const element of elements) stillAwayObserver.observe(element);
    if (!stillAwayBound) {
      stillAwayBound = true;
      document.addEventListener('visibilitychange', syncStillAway);
    }
  }

  /* ------------------------------------------------------------------ *
   * Small handmade bits: the on-air lamp, the wall, the inlay card
   * ------------------------------------------------------------------ */

  function initOnAir() {
    const lamp = document.querySelector('[data-on-air]');
    if (!lamp) return;
    const monday = new Date().getDay() === 1;
    lamp.classList.toggle('is-live', monday);
    lamp.title = monday ? "It's Monday." : 'Lights up on Mondays';
  }

  function localIsoDay(date) {
    const pad = (value) => String(value).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  }

  let wallNotesResizeBound = false;

  // The build knows which Mondays had mixes; only the reader knows what today is.
  function initMondaysWall(scope) {
    const wall = scope.querySelector('[data-mondays-wall]');
    if (!wall) return;
    const today = localIsoDay(new Date());
    let next = null;
    for (const cell of wall.querySelectorAll('[data-monday]')) {
      const day = cell.dataset.monday;
      cell.classList.toggle('is-future', day > today);
      cell.classList.remove('is-next');
      if (!next && day >= today) next = cell;
    }
    if (next && !next.classList.contains('wall__cell--mix')) {
      next.classList.add('is-next');
      next.setAttribute('aria-label', 'Next Monday');
    } else {
      next = null;
    }
    // The build wrote "The next one goes here." on its own next Monday; move it
    // if the reader's is a different one, and drop it if there isn't one.
    const note = wall.querySelector('[data-wall-note="next"]');
    if (note) {
      if (next && note.parentElement !== next) {
        note.parentElement.classList.remove('has-note');
        next.append(note);
        next.classList.add('has-note');
      }
      note.hidden = !next;
    }
    fitWallNotes(wall);
    // The notes' width depends on the pencil font, so fit again once it's in.
    document.fonts?.ready?.then(() => {
      if (wall.isConnected) fitWallNotes(wall);
    });
    if (!wallNotesResizeBound) {
      wallNotesResizeBound = true;
      window.addEventListener('resize', () => {
        const current = document.querySelector('[data-mondays-wall]');
        if (current) fitWallNotes(current);
      });
    }
  }

  // Each margin note leans toward the open side of the wall, so one near the
  // right edge reads leftward. The wall wraps on phones, so this is measured.
  function fitWallNotes(wall) {
    const box = wall.querySelector('.wall__grid')?.getBoundingClientRect();
    if (!box?.width) return;
    const notes = [...wall.querySelectorAll('[data-wall-note]')].filter((note) => !note.hidden);
    for (const note of notes) {
      const words = note.querySelector('.hand-note');
      note.removeAttribute('data-crowded');
      words?.style.removeProperty('--shift');
      const cell = note.parentElement.getBoundingClientRect();
      const preferred = cell.left + cell.width / 2 > box.left + box.width / 2 ? 'west' : 'east';
      // The note's width decides in the end: if it spills past the wall on
      // the open side, the other side wins when it spills less.
      const spill = (side) => {
        note.dataset.side = side;
        const rect = note.getBoundingClientRect();
        return Math.max(0, box.left - rect.left) + Math.max(0, rect.right - box.right);
      };
      const first = spill(preferred);
      if (first > 0 && spill(preferred === 'west' ? 'east' : 'west') >= first) note.dataset.side = preferred;
      // A note that hangs under its square (on a phone) keeps its arrow on
      // the square and slides its words inside the wall.
      if (words && window.getComputedStyle(note).flexDirection.startsWith('column')) {
        const rect = words.getBoundingClientRect();
        const shift = Math.max(0, box.left - rect.left) - Math.max(0, rect.right - box.right);
        if (shift) words.style.setProperty('--shift', `${Math.round(shift)}px`);
      }
    }
    // Two notes that would land on each other (the comeback and next Monday
    // side by side on a phone): the later one steps aside.
    const taken = [];
    for (const note of notes) {
      const rect = note.querySelector('.hand-note')?.getBoundingClientRect();
      if (!rect) continue;
      const clash = taken.some((other) => rect.left < other.right && rect.right > other.left && rect.top < other.bottom && rect.bottom > other.top);
      if (clash) note.setAttribute('data-crowded', '');
      else taken.push(rect);
    }
  }

  async function copyText(text) {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.append(area);
    area.select();
    const ok = document.execCommand('copy');
    area.remove();
    if (!ok) throw new Error('copy failed');
  }

  function initTakeHome(scope) {
    const section = scope.querySelector('[data-take-home]');
    if (!section) return;
    const status = section.querySelector('[data-copy-status]');
    section.querySelector('[data-print-inlay]')?.addEventListener('click', () => window.print());
    section.querySelector('[data-copy-tracklist]')?.addEventListener('click', async () => {
      const text = readJsonScript(section, '[data-tracklist-text]');
      if (typeof text !== 'string') return;
      try {
        await copyText(text);
        if (status) status.textContent = 'Copied. Paste it into your music app, or send it to a friend.';
      } catch {
        if (status) status.textContent = "Couldn't copy that. The full list is on the inlay card.";
      }
    });
  }

  /* ------------------------------------------------------------------ *
   * Page wiring (runs on initial load and after every pjax swap)
   * ------------------------------------------------------------------ */

  // A play request from the page: same mix just changes track or toggles,
  // a different mix retunes the set.
  function playFromPage(payload, index = null) {
    const sameMix = Boolean(tv.queue && payload && tv.queue.slug === payload.slug && tv.ready);
    if (sameMix && index === null) {
      togglePlayback();
    } else if (sameMix) {
      playIndex(index);
    } else {
      tuneIn(payload, index ?? 0);
    }
  }

  function initPage(main) {
    const scope = main || document;

    initReveal(scope);
    initHandMarks(scope);
    initParallaxField(scope);
    initCountUps(scope);
    initHomeWall(scope);
    initStillAway(scope);
    initMondaysWall(scope);
    initTakeHome(scope);

    for (const root of scope.querySelectorAll('[data-discovery]')) {
      initDiscovery(root);
    }

    const payload = readMixPayload(scope);
    initVinyl(scope, payload);

    // #t=N is row N of the tracklist. A song that isn't on YouTube can't be cued.
    const deepLinkRow = parseTrackHash();
    const deepLinkSong = payload && deepLinkRow !== null ? songForRow(payload, deepLinkRow) : -1;
    const cued = deepLinkSong >= 0 ? deepLinkSong : null;

    for (const button of scope.querySelectorAll('[data-play-mix]')) {
      if (payload?.slug) {
        button.dataset.playMixSlug = payload.slug;
        button.dataset.playMixTitle = payload.title || '';
      }
      // Warm the YouTube API up while the pointer is on its way to the button.
      button.addEventListener('pointerenter', () => loadYoutubeIframeApi().catch(() => {}), { once: true });
      button.addEventListener('click', () => {
        if (!payload) return;
        const liveHere = tv.queue && tv.queue.slug === payload.slug;
        playFromPage(payload, liveHere ? null : cued);
        keepClearOfPlayer(button.closest('[data-keep-clear]') || button);
      });
    }

    // A row's play button carries its row; the queue may be shorter than the
    // tracklist when a song isn't on YouTube.
    for (const button of scope.querySelectorAll('[data-track-play]')) {
      button.addEventListener('click', () => {
        const row = Number(button.dataset.trackPlay);
        const index = payload && Number.isInteger(row) ? songForRow(payload, row) : -1;
        if (index < 0) return;
        playFromPage(payload, index);
        keepClearOfPlayer(button);
        try {
          history.replaceState(history.state, '', `#t=${row + 1}`);
        } catch {}
      });
    }

    if (cued !== null) {
      const row = scope.querySelector(`[data-track-index="${deepLinkRow}"]`);
      row?.classList.add('is-cued');
      row?.scrollIntoView({ block: 'center' });
    }

    syncTracklistUi();
  }

  /* ------------------------------------------------------------------ *
   * pjax router: swap <main>, keep the set playing
   * ------------------------------------------------------------------ */

  const prefetchCache = new Map();
  const PREFETCH_LIMIT = 24;

  function isRoutableLink(anchor, event) {
    if (!anchor || anchor.target || anchor.hasAttribute('download')) return false;
    if (event && (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0)) return false;
    const href = anchor.getAttribute('href') || '';
    if (!href || href.startsWith('#') || href.startsWith('mailto:') || href.startsWith('tel:')) return false;
    let url;
    try {
      url = new URL(anchor.href, window.location.href);
    } catch {
      return false;
    }
    if (url.origin !== window.location.origin) return false;
    if (url.pathname === window.location.pathname && url.hash) return false;
    if (/\.(png|jpe?g|gif|webp|svg|pdf|zip|mp3|json|xml)$/i.test(url.pathname)) return false;
    return true;
  }

  async function fetchPage(url) {
    const key = url.split('#')[0];
    if (prefetchCache.has(key)) return prefetchCache.get(key);
    const promise = fetch(key, { headers: { 'X-Requested-With': 'pjax' } }).then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.text();
    });
    prefetchCache.set(key, promise);
    promise.catch(() => prefetchCache.delete(key));
    if (prefetchCache.size > PREFETCH_LIMIT) {
      prefetchCache.delete(prefetchCache.keys().next().value);
    }
    return promise;
  }

  function applyDocumentChrome(newDoc) {
    document.title = newDoc.title;

    const headSelectors = [
      'meta[name="description"]',
      'meta[property="og:title"]',
      'meta[property="og:description"]',
      'meta[property="og:type"]',
      'meta[property="og:url"]',
      'meta[property="og:site_name"]',
      'meta[property="og:image"]',
      'meta[property="og:image:alt"]',
      'meta[name="twitter:card"]',
      'link[rel="canonical"]',
    ];
    for (const selector of headSelectors) {
      const currentNode = document.querySelector(selector);
      const newNode = newDoc.querySelector(selector);
      if (!newNode) {
        currentNode?.remove();
      } else if (currentNode) {
        currentNode.replaceWith(document.importNode(newNode, true));
      } else {
        document.head.append(document.importNode(newNode, true));
      }
    }

    const newStyle = newDoc.documentElement.getAttribute('style') || '';
    document.documentElement.setAttribute('style', newStyle);

    const newTheme = newDoc.querySelector('meta[name="theme-color"]')?.getAttribute('content') || '';
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', newTheme);

    // Header and footer links are relative to the page that rendered them, so
    // a page at another depth needs its own (otherwise Home from a mix page
    // could point at /mixes/).
    for (const selector of ['.site-header', '.site-footer']) {
      const current = document.querySelector(selector);
      const next = newDoc.querySelector(selector);
      if (current && next) current.replaceWith(document.importNode(next, true));
    }
    initOnAir();

    const navCurrent = newDoc.querySelector('[data-pjax-root]')?.dataset.navCurrent || '';
    for (const link of document.querySelectorAll('.site-nav__link')) {
      link.classList.toggle('is-active', link.dataset.navKey === navCurrent);
    }
  }

  function swapMain(newDoc) {
    const currentMain = document.querySelector('[data-pjax-root]');
    const newMain = newDoc.querySelector('[data-pjax-root]');
    if (!currentMain || !newMain) return false;
    const adopted = document.importNode(newMain, true);
    teardownVinyl();
    currentMain.replaceWith(adopted);
    adopted.classList.add('pjax-enter');
    applyDocumentChrome(newDoc);
    initPage(adopted);
    return true;
  }

  function countPjaxPageview(url) {
    if (typeof window.goatcounter?.count !== 'function') return;
    try {
      const destination = new URL(url, window.location.href);
      window.goatcounter.count({
        path: `${destination.pathname}${destination.search}`,
        title: document.title,
      });
    } catch {}
  }

  /* Shared-element morph: the cover you click flies into the mix hero, and the
     hero flies back into its card on the way out. Only one element per side
     carries the name, and only for the duration of the transition. */
  const COVER_TRANSITION_NAME = 'mix-cover';
  let currentPageUrl = window.location?.href || '';

  function mixSlugFromUrl(url) {
    try {
      const match = /\/mixes\/([^/]+)\/?$/.exec(new URL(url, window.location.href).pathname);
      return match ? decodeURIComponent(match[1]) : '';
    } catch {
      return '';
    }
  }

  function heroCoverIn(root) {
    const art = root?.querySelector('.mix-hero__art');
    if (!art) return null;
    // A full-width record stage doesn't morph into a small card cover.
    if (art.classList.contains('is-vinyl-mounted')) {
      return art.closest('.mix-hero--stage') ? null : art.querySelector('.mix-hero__vinyl');
    }
    return art.querySelector('.mix-hero__cover') || art;
  }

  function cardCoverIn(root, slug, preferred) {
    if (!root || !slug) return null;
    const pick = (anchor) => anchor?.querySelector('.mix-card__frame, .hero-grid__art img, img') || null;
    if (preferred && mixSlugFromUrl(preferred.href) === slug) {
      const own = preferred.matches('.hero-grid__art') ? preferred : pick(preferred);
      if (own) return own;
    }
    for (const anchor of root.querySelectorAll('a[href]')) {
      if (anchor.closest('.site-header, .tv')) continue;
      if (mixSlugFromUrl(anchor.href) !== slug) continue;
      const target = anchor.matches('.hero-grid__art') ? anchor : pick(anchor);
      if (target) return target;
    }
    return null;
  }

  function inViewport(element) {
    const rect = element?.getBoundingClientRect?.();
    if (!rect || !rect.width || !rect.height) return false;
    return rect.bottom > 0 && rect.top < window.innerHeight && rect.right > 0 && rect.left < window.innerWidth;
  }

  function nameForTransition(element) {
    if (!element) return null;
    element.style.viewTransitionName = COVER_TRANSITION_NAME;
    return element;
  }

  // Each history entry remembers how far down the page was, so Back and
  // Forward land where the reader left off.
  function rememberScroll() {
    try {
      history.replaceState({ ...(history.state || {}), pjax: true, scrollY: window.scrollY }, '');
    } catch {}
  }

  // Bring the element a URL's hash names into view, honouring its
  // scroll-margin-top. False when there's no such element (#t=3 on a mix page
  // is a song cue, which initPage handles).
  function targetForHash(hash) {
    try {
      const id = decodeURIComponent(String(hash || '').replace(/^#/, ''));
      return id ? document.getElementById(id) : null;
    } catch {
      return null;
    }
  }

  // Where the element sits in the layout, ignoring transforms: a section still
  // sliding in on its scroll reveal would otherwise be measured 22px low.
  function scrollToTarget(target, behavior) {
    let top = 0;
    for (let node = target; node; node = node.offsetParent) top += node.offsetTop;
    const margin = parseFloat(window.getComputedStyle(target).scrollMarginTop) || 0;
    window.scrollTo({ top: Math.max(0, top - margin), behavior });
  }

  function scrollToHash(hash, behavior = 'instant' in window ? 'instant' : 'auto') {
    const target = targetForHash(hash);
    if (!target) return false;
    scrollToTarget(target, behavior);
    return true;
  }

  // A link to an anchor on this same page: move there, and give it its own
  // history entry so Back returns to where the reader was.
  function followSamePageHash(anchor, event) {
    if (!anchor || anchor.target || anchor.hasAttribute('download')) return false;
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return false;
    let url;
    try {
      url = new URL(anchor.href, window.location.href);
    } catch {
      return false;
    }
    if (url.origin !== window.location.origin || !samePage(url.href, window.location.href)) return false;
    const target = targetForHash(url.hash);
    if (!target) return false;
    event.preventDefault();
    rememberScroll();
    history.pushState({ pjax: true }, '', url.href);
    currentPageUrl = window.location.href;
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    scrollToTarget(target, still ? ('instant' in window ? 'instant' : 'auto') : 'smooth');
    return true;
  }

  // Late layout (a font swapping in) can nudge the target after the jump, so
  // line it up again shortly after, unless the reader has scrolled since.
  function holdOnHash(hash) {
    let expected = window.scrollY;
    const realign = () => {
      if (Math.abs(window.scrollY - expected) > 3) return;
      scrollToHash(hash);
      expected = window.scrollY;
    };
    window.setTimeout(realign, 300);
    window.setTimeout(realign, 900);
  }

  function samePage(a, b) {
    try {
      const x = new URL(a, window.location.href);
      const y = new URL(b, window.location.href);
      return x.pathname === y.pathname && x.search === y.search;
    } catch {
      return false;
    }
  }

  async function navigateTo(url, { push = true, source = null, scrollY = null } = {}) {
    let html;
    try {
      html = await fetchPage(url);
    } catch {
      window.location.assign(url);
      return;
    }

    const newDoc = new DOMParser().parseFromString(html, 'text/html');
    const canMorph = Boolean(document.startViewTransition) && !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const fromSlug = mixSlugFromUrl(currentPageUrl);
    const toSlug = mixSlugFromUrl(url);
    const named = [];
    let resolveIncoming = null;

    if (canMorph && toSlug && toSlug !== fromSlug) {
      const outgoing = cardCoverIn(document.querySelector('[data-pjax-root]'), toSlug, source);
      if (inViewport(outgoing)) {
        named.push(nameForTransition(outgoing));
        resolveIncoming = (main) => heroCoverIn(main);
      }
    } else if (canMorph && fromSlug && !toSlug) {
      const outgoing = heroCoverIn(document.querySelector('[data-pjax-root]'));
      if (inViewport(outgoing)) {
        named.push(nameForTransition(outgoing));
        resolveIncoming = (main) => {
          const target = cardCoverIn(main, fromSlug);
          if (!inViewport(target)) return null;
          // A card still waiting on its scroll reveal would be captured invisible.
          target.closest('.reveal')?.classList.add('is-revealed');
          return target;
        };
      }
    }

    const doSwap = () => {
      if (push) rememberScroll();
      if (!swapMain(newDoc)) {
        window.location.assign(url);
        return;
      }
      if (push) {
        history.pushState({ pjax: true, scrollY: 0 }, '', url);
      }
      currentPageUrl = window.location.href;
      countPjaxPageview(url);
      const hash = new URL(url, window.location.href).hash;
      const instant = 'instant' in window ? 'instant' : 'auto';
      if (Number.isFinite(scrollY)) {
        window.scrollTo({ top: scrollY, behavior: instant });
      } else if (!hash) {
        window.scrollTo({ top: 0, behavior: instant });
      } else if (scrollToHash(hash)) {
        holdOnHash(hash);
      } else if (!document.querySelector('[data-pjax-root] .is-cued')) {
        window.scrollTo({ top: 0, behavior: instant });
      }
      if (resolveIncoming) {
        const incoming = resolveIncoming(document.querySelector('[data-pjax-root]'));
        if (incoming) named.push(nameForTransition(incoming));
      }
    };

    if (document.startViewTransition) {
      const transition = document.startViewTransition(doSwap);
      // An interrupted transition (a second click, a hidden tab) rejects these;
      // the swap itself still ran, so there is nothing to recover.
      transition.ready?.catch(() => {});
      transition.finished
        ?.catch(() => {})
        .then(() => {
          for (const element of named) element.style.viewTransitionName = '';
        });
    } else {
      doSwap();
    }
  }

  function bindRouter() {
    document.addEventListener('click', (event) => {
      const anchor = event.target instanceof Element ? event.target.closest('a') : null;
      if (followSamePageHash(anchor, event)) return;
      if (!isRoutableLink(anchor, event)) return;
      event.preventDefault();
      navigateTo(anchor.href, { source: anchor });
    });

    document.addEventListener('mouseover', (event) => {
      const anchor = event.target instanceof Element ? event.target.closest('a') : null;
      if (!isRoutableLink(anchor, null)) return;
      fetchPage(anchor.href).catch(() => {});
    });

    let scrollTimer = 0;
    window.addEventListener('popstate', (event) => {
      // A save still waiting from the page we're leaving must not land on this entry.
      window.clearTimeout(scrollTimer);
      const saved = Number(event.state?.scrollY);
      const scrollY = Number.isFinite(saved) ? saved : null;
      // Only the hash changed (a same-page anchor): stay on the page and move.
      if (samePage(window.location.href, currentPageUrl)) {
        currentPageUrl = window.location.href;
        if (scrollY !== null) {
          window.scrollTo({ top: scrollY, behavior: 'instant' in window ? 'instant' : 'auto' });
        } else if (!scrollToHash(window.location.hash)) {
          window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
        }
        return;
      }
      navigateTo(window.location.href, { push: false, scrollY });
    });

    // The router puts the page back itself, after the new content is in.
    if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
    history.replaceState({ ...(history.state || {}), pjax: true, scrollY: window.scrollY }, '', window.location.href);
    window.addEventListener('scroll', () => {
      window.clearTimeout(scrollTimer);
      scrollTimer = window.setTimeout(rememberScroll, 150);
    }, { passive: true });
  }

  /* ------------------------------------------------------------------ *
   * Boot
   * ------------------------------------------------------------------ */

  document.addEventListener('DOMContentLoaded', () => {
    if (bindTvElements()) {
      bindTvControls();
      bindKeyboard();
      bindRouter();
    }
    initOnAir();
    initPage(document.querySelector('[data-pjax-root]'));
  });

  window.addEventListener?.('pagehide', () => {
    teardownVinyl();
  });

  // Internal hooks for automated tests and console debugging only.
  window.__MMM__ = {
    tv,
    tuneIn,
    playIndex,
    togglePlayback,
    tuck,
    untuck,
    powerOff,
    onTvState,
    onTvError,
    normalizeQueue,
    songForRow,
    segmentWeights,
    embedVars,
    syncAll,
    teardownVinyl,
    matchesFilter,
    discoveryCountLine,
    pencilStats,
    wordJitter,
    SKIP_UNPLAYABLE_MS,
    STALL_MS,
  };
})();
