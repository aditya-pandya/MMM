/* ==========================================================================
   Monday Music Mix — client runtime
   - Persistent bottom player (YouTube IFrame API, mini visible video)
   - pjax router: swaps <main> so playback survives navigation
   - Discovery search/filter (archive + notes)
   - MediaSession, keyboard shortcuts, track deep links (#t=N)
   ========================================================================== */

(() => {
  'use strict';

  /* ------------------------------------------------------------------ *
   * Utilities
   * ------------------------------------------------------------------ */

  function formatClock(totalSeconds) {
    const safeSeconds = Math.max(0, Math.floor(Number(totalSeconds) || 0));
    const hours = Math.floor(safeSeconds / 3600);
    const minutes = Math.floor((safeSeconds % 3600) / 60);
    const seconds = safeSeconds % 60;
    if (hours > 0) {
      return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }
    return `${minutes}:${String(seconds).padStart(2, '0')}`;
  }

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

  function setRangeFill(input, ratio) {
    input.style.setProperty('--fill', `${Math.max(0, Math.min(100, ratio * 100))}%`);
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
   * Persistent player
   * ------------------------------------------------------------------ */

  const BLOCKED_ERROR_CODES = new Set([5, 100, 101, 150]);
  const STALLED_AUTOPLAY_MS = 1800;
  const STALLED_RECOVERY_SKIP_MS = 4200;
  // YouTube pre-roll ads look exactly like a stalled video through the IFrame
  // API (the song reports unstarted/buffering until the ad ends). When the
  // browser is known to allow playback - the listener just pressed play, or
  // something already played - a stall is almost always an ad, so wait it out.
  const AD_WAIT_NOTICE_MS = 2500;
  const AD_GRACE_MS = 75000;
  const GESTURE_WINDOW_MS = 5000;
  const PLAYER_STATE_STORAGE_KEY = 'mmm-player-state-v1';
  const PLAYER_STATE_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
  const PLAYER_STATE_SAVE_INTERVAL_MS = 4000;

  function normalizeResumePayload(payload) {
    if (!payload || !Array.isArray(payload.videoIds)) return null;
    const videoIds = payload.videoIds.map((value) => String(value || '').trim()).filter(Boolean);
    if (!videoIds.length) return null;
    return {
      slug: String(payload.slug || ''),
      title: String(payload.title || 'Mix'),
      url: String(payload.url || ''),
      videoIds,
      labels: Array.isArray(payload.labels) ? payload.labels.map((value) => String(value || '').trim()) : [],
      cover: String(payload.cover || ''),
      watchUrl: String(payload.watchUrl || ''),
    };
  }

  function serializeResumeState(payload, trackIndex = 0, positionSeconds = 0, updatedAt = Date.now()) {
    const normalizedPayload = normalizeResumePayload(payload);
    if (!normalizedPayload) return '';
    return JSON.stringify({
      slug: normalizedPayload.slug,
      trackIndex: Math.max(0, Math.floor(Number(trackIndex) || 0)),
      positionSeconds: Math.max(0, Number(positionSeconds) || 0),
      updatedAt: Number(updatedAt) || 0,
      payload: normalizedPayload,
    });
  }

  function deserializeResumeState(serialized) {
    try {
      const parsed = JSON.parse(String(serialized || ''));
      const payload = normalizeResumePayload(parsed?.payload);
      const updatedAt = Number(parsed?.updatedAt || 0);
      if (!payload || !updatedAt || String(parsed?.slug || '') !== payload.slug) return null;
      return {
        slug: payload.slug,
        trackIndex: Math.max(0, Math.floor(Number(parsed.trackIndex) || 0)),
        positionSeconds: Math.max(0, Number(parsed.positionSeconds) || 0),
        updatedAt,
        payload,
      };
    } catch {
      return null;
    }
  }

  const player = {
    bar: null,
    els: {},
    yt: null,
    ready: false,
    queue: null, // {slug, title, url, videoIds, labels, cover, watchUrl}
    index: 0,
    pendingIndex: null,
    shouldAutoplay: false,
    autoplayRequestedAt: 0,
    lastRecoveryAttemptAt: 0,
    failedIndexes: new Set(),
    statusOverride: null,
    isScrubbing: false,
    pollTimer: null,
    hasPlayedSinceGesture: false,
    consecutiveStallSkips: 0,
    resumeIndexOnBlock: null,
    lastGestureAt: 0,
    adWait: false,
  };
  let lastPlayerStateSaveAt = 0;
  let resumePrompt = null;
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
    const live = Boolean(player.queue && player.queue.slug === activeVinyl.slug);
    activeVinyl.handle.setPlaying(live && isPlaying());
    // The needle: which groove band is playing, and how far into it.
    if (typeof activeVinyl.handle.setProgress === 'function') {
      const duration = Number(player.yt?.getDuration?.() || 0);
      const current = Number(player.yt?.getCurrentTime?.() || 0);
      const index = live ? clampIndex(player.index) : -1;
      const fraction = index >= 0 && duration > 0 ? Math.min(1, Math.max(0, current / duration)) : 0;
      activeVinyl.handle.setProgress(index, fraction);
    }
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

  async function initVinyl(scope, mixPayload) {
    const vinylPayload = readJsonScript(scope, '[data-vinyl-payload]');
    const mount = scope.querySelector('[data-vinyl-mount]');
    if (!vinylPayload || !mount) return;
    try {
      const MMMVinyl = await loadVinylScript();
      if (!MMMVinyl?.isSupported?.()) return;
      if (!document.documentElement.contains(mount)) return;

      teardownVinyl();
      const vinylKey = vinylPayload.key || vinylPayload.title || 'mount';
      const fontFamilies = typeof MMMVinyl.facesFor === 'function'
        ? MMMVinyl.facesFor(vinylKey)
        : [];
      const art = mount.closest('.mix-hero__art');
      const resizeHandler = () => {
        window.clearTimeout(vinylResizeTimer);
        vinylResizeTimer = window.setTimeout(() => activeVinyl?.handle?.resize?.(), 120);
      };
      const handle = MMMVinyl.mount(mount, {
        ...vinylPayload,
        describedBy: vinylPayload.describedBy || vinylPayload.hintId,
        intro: true,
        reducedMotion: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
        fontCss: vinylFontCss(fontFamilies),
        fontFamilies,
        onTrackHover: (index) => markGrooveHover(index),
        onTrackPick: (index) => {
          if (!mixPayload || !Number.isInteger(index) || index < 0 || index >= mixPayload.videoIds.length) return;
          if (player.queue && player.queue.slug === mixPayload.slug && player.ready) {
            playIndex(index);
          } else {
            playQueue(mixPayload, index);
          }
        },
        onReady: (readyHandle) => {
          if (activeVinyl?.handle !== readyHandle || readyHandle.error) return;
          art?.classList.add('is-vinyl-mounted');
          if (Array.isArray(vinylPayload.durations) && vinylPayload.durations.length) {
            readyHandle.setTracks?.(vinylPayload.durations);
          }
          syncVinylPlayback();
        },
      });
      activeVinyl = {
        handle,
        slug: String(mixPayload?.slug || ''),
        resizeHandler,
      };
      window.addEventListener('resize', resizeHandler);
      window.addEventListener('orientationchange', resizeHandler);
      bindTracklistToVinyl(scope);
      syncVinylPlayback();
    } catch {}
  }

  function savePlayerState({ force = false, positionSeconds = null } = {}) {
    if (!player.queue || !player.yt) return false;
    const now = Date.now();
    if (!force && (!isPlaying() || now - lastPlayerStateSaveAt < PLAYER_STATE_SAVE_INTERVAL_MS)) return false;
    const position = positionSeconds === null
      ? Number(player.yt.getCurrentTime?.() || 0)
      : Number(positionSeconds || 0);
    const serialized = serializeResumeState(player.queue, player.index, position, now);
    if (!serialized) return false;
    try {
      window.localStorage.setItem(PLAYER_STATE_STORAGE_KEY, serialized);
      lastPlayerStateSaveAt = now;
      return true;
    } catch {
      return false;
    }
  }

  function readSavedPlayerState(now = Date.now()) {
    try {
      const saved = deserializeResumeState(window.localStorage.getItem(PLAYER_STATE_STORAGE_KEY));
      if (!saved) return null;
      const age = Number(now) - saved.updatedAt;
      return age >= 0 && age < PLAYER_STATE_MAX_AGE_MS ? saved : null;
    } catch {
      return null;
    }
  }

  function dismissResumePrompt() {
    if (resumePrompt) resumePrompt.remove();
    resumePrompt = null;
  }

  function showResumePrompt(savedState) {
    if (!savedState?.payload || resumePrompt) return null;
    const pill = document.createElement('aside');
    pill.className = 'resume-pill';
    pill.dataset.resumePill = '';
    pill.setAttribute('aria-label', 'Continue listening');

    const resumeButton = document.createElement('button');
    resumeButton.type = 'button';
    resumeButton.className = 'resume-pill__action';
    resumeButton.textContent = `Continue listening — ${savedState.payload.title}, track ${savedState.trackIndex + 1}`;
    resumeButton.addEventListener('click', () => {
      dismissResumePrompt();
      playQueue(savedState.payload, savedState.trackIndex, {
        autoplay: true,
        positionSeconds: savedState.positionSeconds,
      });
    });

    const dismissButton = document.createElement('button');
    dismissButton.type = 'button';
    dismissButton.className = 'resume-pill__dismiss';
    dismissButton.setAttribute('aria-label', 'Dismiss continue listening');
    dismissButton.textContent = '×';
    dismissButton.addEventListener('click', dismissResumePrompt);

    pill.append(resumeButton, dismissButton);
    document.body.append(pill);
    resumePrompt = pill;
    return pill;
  }

  function maybeShowResumePrompt() {
    if (parseTrackHash() !== null) return null;
    const savedState = readSavedPlayerState();
    return savedState ? showResumePrompt(savedState) : null;
  }

  function bindPlayerElements() {
    const bar = document.querySelector('[data-player-bar]');
    if (!bar) return false;
    player.bar = bar;
    player.els = {
      host: bar.querySelector('[data-player-host]'),
      notice: bar.querySelector('[data-player-notice]'),
      mixLink: bar.querySelector('[data-player-mix-link]'),
      mix: bar.querySelector('[data-player-mix]'),
      track: bar.querySelector('[data-player-track]'),
      meta: bar.querySelector('[data-player-meta]'),
      previous: bar.querySelector('[data-player-previous]'),
      toggle: bar.querySelector('[data-player-toggle]'),
      toggleIcon: bar.querySelector('[data-player-toggle-icon]'),
      next: bar.querySelector('[data-player-next]'),
      progress: bar.querySelector('[data-player-progress]'),
      elapsed: bar.querySelector('[data-player-elapsed]'),
      duration: bar.querySelector('[data-player-duration]'),
      mute: bar.querySelector('[data-player-mute]'),
      muteIcon: bar.querySelector('[data-player-mute-icon]'),
      volume: bar.querySelector('[data-player-volume]'),
      external: bar.querySelector('[data-player-external]'),
    };
    return true;
  }

  function clampIndex(index) {
    if (!player.queue) return 0;
    return Math.min(Math.max(Number(index) || 0, 0), Math.max(player.queue.videoIds.length - 1, 0));
  }

  function currentLabel(index) {
    if (!player.queue) return '—';
    return player.queue.labels[index] || `Track ${index + 1}`;
  }

  function isPlaying() {
    return Boolean(
      window.YT &&
      player.yt &&
      typeof player.yt.getPlayerState === 'function' &&
      player.yt.getPlayerState() === window.YT.PlayerState.PLAYING
    );
  }

  function stateLabel() {
    if (player.statusOverride) return player.statusOverride;
    if (!window.YT || !player.yt || typeof player.yt.getPlayerState !== 'function') return '';
    switch (player.yt.getPlayerState()) {
      case window.YT.PlayerState.PLAYING: return '';
      case window.YT.PlayerState.BUFFERING: return 'Buffering…';
      case window.YT.PlayerState.PAUSED: return 'Paused';
      case window.YT.PlayerState.ENDED: return 'Ended';
      default: return '';
    }
  }

  // Play-mix buttons double as pause/resume once their mix is the live queue.
  function syncPlayMixButtons() {
    const playing = isPlaying();
    for (const button of document.querySelectorAll('[data-play-mix]')) {
      const slug = button.dataset.playMixSlug || '';
      const live = Boolean(slug && player.queue && player.queue.slug === slug);
      const state = !live ? 'idle' : playing ? 'playing' : 'paused';
      if (button.dataset.playState === state) continue;
      button.dataset.playState = state;
      button.classList.toggle('is-playing', state === 'playing');
      const icon = button.querySelector('i');
      if (icon) icon.className = `ph-fill ${state === 'playing' ? 'ph-pause' : 'ph-play'}`;
      const text = button.querySelector('span');
      const label = state === 'playing' ? 'Pause' : state === 'paused' ? 'Resume' : 'Play mix';
      if (text) text.textContent = label;
      const title = button.dataset.playMixTitle || '';
      button.setAttribute('aria-label', title ? `${label === 'Play mix' ? 'Play' : label} ${title}` : label);
    }
  }

  function syncTracklistUi() {
    syncPlayMixButtons();
    const list = document.querySelector('[data-tracklist]');
    if (!list) {
      syncVinylPlayback();
      return;
    }
    const matches = player.queue && list.dataset.tracklist === player.queue.slug;
    const playing = isPlaying();
    list.querySelectorAll('[data-track-index]').forEach((item) => {
      const itemIndex = Number(item.dataset.trackIndex);
      const active = Boolean(matches) && itemIndex === player.index;
      item.classList.toggle('is-active', active);
      item.classList.toggle('is-paused', active && !playing);
      const row = item.querySelector('.tracklist__row');
      if (row) row.setAttribute('aria-current', active ? 'true' : 'false');
    });
    syncVinylPlayback();
  }

  function syncPlayerUi() {
    if (!player.bar || !player.queue) {
      syncVinylPlayback();
      return;
    }
    const els = player.els;
    const index = clampIndex(player.index);
    const count = player.queue.videoIds.length;
    const playing = isPlaying();
    const currentTime = Number(player.yt?.getCurrentTime?.() || 0);
    const duration = Number(player.yt?.getDuration?.() || 0);

    if (window.YT && player.yt && typeof player.yt.getPlayerState === 'function') {
      const st = player.yt.getPlayerState();
      if ([window.YT.PlayerState.CUED, window.YT.PlayerState.PLAYING, window.YT.PlayerState.PAUSED, window.YT.PlayerState.BUFFERING].includes(st)) {
        player.pendingIndex = null;
      }
      if (!player.shouldAutoplay || st === window.YT.PlayerState.PLAYING) {
        player.autoplayRequestedAt = 0;
        player.lastRecoveryAttemptAt = 0;
      }
    }

    els.mix.textContent = player.queue.title;
    els.mixLink.href = player.queue.url || '#';
    els.track.textContent = currentLabel(index);
    const state = player.adWait && !player.statusOverride ? 'Ad on YouTube — your song is next' : stateLabel();
    els.meta.textContent = state ? `${state} · Track ${index + 1} of ${count}` : `Track ${index + 1} of ${count}`;
    els.elapsed.textContent = formatClock(currentTime);
    els.duration.textContent = formatClock(duration);

    if (els.toggleIcon) {
      els.toggleIcon.className = `ph-fill ${playing ? 'ph-pause' : 'ph-play'}`;
    }
    els.toggle.setAttribute('aria-label', playing ? 'Pause' : 'Play');
    els.previous.disabled = index <= 0;
    els.next.disabled = index >= count - 1;
    els.progress.disabled = duration <= 0;

    if (!player.isScrubbing && duration > 0) {
      els.progress.value = String(Math.min(1000, Math.round((currentTime / duration) * 1000)));
      setRangeFill(els.progress, currentTime / duration);
    }

    const muted = Boolean(player.yt?.isMuted?.());
    if (els.muteIcon) {
      els.muteIcon.className = `ph ${muted ? 'ph-speaker-slash' : 'ph-speaker-high'}`;
    }
    if (player.yt && typeof player.yt.getVolume === 'function' && !muted) {
      const volume = Number(player.yt.getVolume() || 0);
      els.volume.value = String(volume);
      setRangeFill(els.volume, volume / 100);
    }

    if (els.external) {
      const watchUrl = player.queue.watchUrl || '';
      els.external.hidden = !watchUrl;
      if (watchUrl) els.external.href = watchUrl;
    }

    if (playing) {
      player.hasPlayedSinceGesture = true;
      player.consecutiveStallSkips = 0;
      player.resumeIndexOnBlock = null;
    }
    updateMediaSessionState(playing);
    syncTracklistUi();
    if (playing) savePlayerState();
  }

  function findNextPlayableIndex(fromIndex) {
    if (!player.queue) return -1;
    const count = player.queue.videoIds.length;
    for (let i = fromIndex + 1; i < count; i += 1) {
      if (!player.failedIndexes.has(i)) return i;
    }
    for (let i = 0; i < fromIndex; i += 1) {
      if (!player.failedIndexes.has(i)) return i;
    }
    return -1;
  }

  function markUnavailable(message) {
    player.shouldAutoplay = false;
    player.autoplayRequestedAt = 0;
    player.lastRecoveryAttemptAt = 0;
    player.statusOverride = message;
    setAdWait(false);
    syncPlayerUi();
  }

  function playbackIsGestureBacked(requestedAt) {
    if (player.hasPlayedSinceGesture) return true;
    const gestureAt = Number(player.lastGestureAt || 0);
    return gestureAt > 0 && requestedAt > 0 && requestedAt - gestureAt <= GESTURE_WINDOW_MS && requestedAt >= gestureAt - 250;
  }

  function setAdWait(waiting) {
    const next = Boolean(waiting);
    if (player.adWait === next) return;
    player.adWait = next;
    player.bar?.classList?.toggle('is-waiting', next);
    if (player.els?.notice) player.els.notice.hidden = !next;
  }

  function recoverStalledPlayback() {
    if (!player.yt || !player.ready || !window.YT || !player.shouldAutoplay || !player.queue) {
      setAdWait(false);
      return;
    }
    const st = typeof player.yt.getPlayerState === 'function' ? player.yt.getPlayerState() : -1;
    const now = Date.now();
    const requestedAt = Number(player.autoplayRequestedAt || 0);
    const elapsed = requestedAt > 0 ? now - requestedAt : 0;
    const patient = playbackIsGestureBacked(requestedAt);

    // Some ads report PLAYING while the song's own clock sits at zero.
    if (st === window.YT.PlayerState.PLAYING) {
      const position = Number(player.yt.getCurrentTime?.() || 0);
      setAdWait(patient && requestedAt > 0 && position < 0.3 && elapsed >= AD_WAIT_NOTICE_MS);
      return;
    }

    const stallable = new Set([-1, window.YT.PlayerState.UNSTARTED, window.YT.PlayerState.BUFFERING, window.YT.PlayerState.CUED]);
    if (!stallable.has(st)) {
      setAdWait(false);
      return;
    }

    const activeIndex = clampIndex(player.index);
    if (patient) setAdWait(elapsed >= AD_WAIT_NOTICE_MS);

    if (elapsed >= (patient ? AD_GRACE_MS : STALLED_RECOVERY_SKIP_MS)) {
      setAdWait(false);
      // A blanket autoplay block (browser policy, background tab) looks like a
      // stalled track. If skips keep happening before anything ever played,
      // stop burning through the queue and hand control back to the user.
      if (!player.hasPlayedSinceGesture && player.consecutiveStallSkips >= 2) {
        player.failedIndexes.clear();
        player.consecutiveStallSkips = 0;
        markUnavailable('Tap play to start.');
        playIndex(player.resumeIndexOnBlock ?? activeIndex, { autoplay: false });
        return;
      }
      player.consecutiveStallSkips = (player.consecutiveStallSkips || 0) + 1;
      if (player.resumeIndexOnBlock === null || player.resumeIndexOnBlock === undefined) {
        player.resumeIndexOnBlock = activeIndex;
      }
      player.failedIndexes.add(activeIndex);
      const fallback = findNextPlayableIndex(activeIndex);
      if (fallback >= 0) {
        playIndex(fallback, { autoplay: true });
        return;
      }
      markUnavailable('Playback is unavailable here — open it on YouTube.');
      return;
    }

    // Reloading restarts an ad, so only nudge when autoplay may be blocked.
    if (!patient && elapsed >= STALLED_AUTOPLAY_MS && Number(player.lastRecoveryAttemptAt || 0) < requestedAt) {
      player.lastRecoveryAttemptAt = now;
      try {
        player.yt.loadVideoById(player.queue.videoIds[activeIndex]);
      } catch {}
    }
  }

  function startPolling() {
    window.clearInterval(player.pollTimer);
    player.pollTimer = window.setInterval(() => {
      syncPlayerUi();
      recoverStalledPlayback();
    }, 500);
    syncPlayerUi();
  }

  function playIndex(index, options = {}) {
    const { autoplay = true, positionSeconds = 0 } = options;
    if (!player.yt || !player.ready || !player.queue) return;
    const nextIndex = clampIndex(index);
    player.statusOverride = null;
    setAdWait(false);
    player.index = nextIndex;
    player.pendingIndex = nextIndex;
    player.shouldAutoplay = Boolean(autoplay);
    player.autoplayRequestedAt = autoplay ? Date.now() : 0;
    player.lastRecoveryAttemptAt = 0;
    const videoId = player.queue.videoIds[nextIndex];
    if (!videoId) return;
    const startSeconds = Math.max(0, Number(positionSeconds) || 0);
    const videoRequest = startSeconds > 0 ? { videoId, startSeconds } : videoId;
    if (autoplay) {
      player.yt.loadVideoById(videoRequest);
    } else {
      player.yt.cueVideoById(videoRequest);
    }
    savePlayerState({ force: true, positionSeconds: startSeconds });
    updateMediaSessionMetadata();
    syncPlayerUi();
  }

  function togglePlayback() {
    if (!player.yt || !player.ready || !window.YT) return;
    if (isPlaying()) {
      player.shouldAutoplay = false;
      player.autoplayRequestedAt = 0;
      player.yt.pauseVideo();
      savePlayerState({ force: true });
    } else {
      player.shouldAutoplay = true;
      player.statusOverride = null;
      player.autoplayRequestedAt = Date.now();
      const st = typeof player.yt.getPlayerState === 'function' ? player.yt.getPlayerState() : -1;
      const shouldLoad = [window.YT.PlayerState.CUED, window.YT.PlayerState.UNSTARTED, window.YT.PlayerState.ENDED].includes(st);
      try {
        if (shouldLoad) {
          player.yt.loadVideoById(player.queue.videoIds[clampIndex(player.index)]);
        } else {
          player.yt.playVideo();
        }
      } catch {}
    }
    syncPlayerUi();
  }

  function seekBy(seconds) {
    if (!player.yt || !player.ready) return;
    const duration = Number(player.yt.getDuration?.() || 0);
    if (duration <= 0) return;
    const next = Math.max(0, Math.min(duration, Number(player.yt.getCurrentTime?.() || 0) + seconds));
    player.yt.seekTo(next, true);
    syncPlayerUi();
  }

  /* MediaSession */

  function absoluteUrl(href) {
    try {
      return new URL(href, window.location.href).href;
    } catch {
      return '';
    }
  }

  function updateMediaSessionMetadata() {
    if (!('mediaSession' in navigator) || !player.queue) return;
    const index = clampIndex(player.index);
    const artwork = player.queue.cover
      ? [{ src: absoluteUrl(player.queue.cover), sizes: '512x512', type: 'image/png' }]
      : [];
    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: currentLabel(index),
        artist: player.queue.title,
        album: 'Monday Music Mix',
        artwork,
      });
    } catch {}
  }

  function updateMediaSessionState(playing) {
    if (!('mediaSession' in navigator)) return;
    try {
      navigator.mediaSession.playbackState = playing ? 'playing' : 'paused';
    } catch {}
  }

  function bindMediaSessionHandlers() {
    if (!('mediaSession' in navigator)) return;
    const handlers = {
      play: () => togglePlayback(),
      pause: () => togglePlayback(),
      previoustrack: () => playIndex(player.index - 1),
      nexttrack: () => playIndex(player.index + 1),
      seekbackward: () => seekBy(-10),
      seekforward: () => seekBy(10),
    };
    for (const [action, handler] of Object.entries(handlers)) {
      try {
        navigator.mediaSession.setActionHandler(action, handler);
      } catch {}
    }
  }

  /* Boot / queue loading */

  async function ensureYoutubePlayer() {
    if (player.yt) return true;
    try {
      await loadYoutubeIframeApi();
    } catch {
      markUnavailable('Playback is unavailable here — open it on YouTube.');
      return false;
    }

    await new Promise((resolve) => {
      const mount = document.createElement('div');
      mount.id = 'mmm-player-mount';
      player.els.host.replaceChildren(mount);
      player.yt = new window.YT.Player('mmm-player-mount', {
        width: '320',
        height: '180',
        videoId: player.queue.videoIds[clampIndex(player.index)],
        playerVars: {
          autoplay: 0,
          controls: 0,
          modestbranding: 1,
          rel: 0,
          playsinline: 1,
        },
        events: {
          onReady: (event) => {
            player.ready = true;
            try {
              event.target.setVolume(Number(player.els.volume.value || 100));
            } catch {}
            startPolling();
            resolve();
          },
          onStateChange: (event) => {
            if (window.YT && event.data === window.YT.PlayerState.ENDED) {
              const activeIndex = clampIndex(player.index);
              if (activeIndex < player.queue.videoIds.length - 1) {
                playIndex(activeIndex + 1);
                return;
              }
            }
            if (window.YT && event.data === window.YT.PlayerState.PAUSED) {
              savePlayerState({ force: true });
            }
            syncPlayerUi();
          },
          onError: (event) => {
            const code = Number(event?.data);
            const erroredIndex = Number.isInteger(player.pendingIndex) ? clampIndex(player.pendingIndex) : clampIndex(player.index);
            if (player.failedIndexes.has(erroredIndex)) return;
            player.failedIndexes.add(erroredIndex);
            player.pendingIndex = null;
            if (BLOCKED_ERROR_CODES.has(code)) {
              const fallback = findNextPlayableIndex(erroredIndex);
              if (fallback >= 0) {
                playIndex(fallback, { autoplay: player.shouldAutoplay });
                return;
              }
            }
            markUnavailable('Playback is unavailable here — open it on YouTube.');
          },
        },
      });
    });

    bindMediaSessionHandlers();
    return true;
  }

  async function playQueue(payload, startIndex = 0, options = {}) {
    const { autoplay = true, positionSeconds = 0 } = options;
    const normalizedPayload = normalizeResumePayload(payload);
    if (!normalizedPayload) return;
    if (!player.bar) return;
    dismissResumePrompt();

    const sameQueue = player.queue && player.queue.slug === normalizedPayload.slug;
    if (!sameQueue) {
      player.queue = {
        ...normalizedPayload,
        url: absoluteUrl(normalizedPayload.url || window.location.pathname),
      };
      player.failedIndexes = new Set();
      player.statusOverride = null;
      player.index = clampIndex(startIndex);
    }

    player.bar.hidden = false;
    document.body.classList.add('has-player');

    const booted = await ensureYoutubePlayer();
    if (!booted) return;

    if (sameQueue && clampIndex(startIndex) === clampIndex(player.index) && Number(positionSeconds || 0) <= 0) {
      if (autoplay && !isPlaying()) togglePlayback();
      return;
    }
    playIndex(startIndex, { autoplay, positionSeconds });
  }

  function bindPlayerControls() {
    const els = player.els;
    if (!els.toggle) return;

    els.toggle.addEventListener('click', togglePlayback);
    els.previous.addEventListener('click', () => playIndex(player.index - 1));
    els.next.addEventListener('click', () => playIndex(player.index + 1));

    els.mute.addEventListener('click', () => {
      if (!player.yt || !player.ready) return;
      if (player.yt.isMuted()) {
        player.yt.unMute();
      } else {
        player.yt.mute();
      }
      syncPlayerUi();
    });

    els.volume.addEventListener('input', () => {
      if (!player.yt || !player.ready) return;
      const volume = Number(els.volume.value || 100);
      player.yt.setVolume(volume);
      if (player.yt.isMuted() && volume > 0) player.yt.unMute();
      setRangeFill(els.volume, volume / 100);
    });

    els.progress.addEventListener('input', () => {
      if (!player.yt || !player.ready) return;
      player.isScrubbing = true;
      const duration = Number(player.yt.getDuration?.() || 0);
      const nextTime = duration > 0 ? (Number(els.progress.value || 0) / 1000) * duration : 0;
      els.elapsed.textContent = formatClock(nextTime);
      setRangeFill(els.progress, duration > 0 ? nextTime / duration : 0);
    });

    els.progress.addEventListener('change', () => {
      if (!player.yt || !player.ready) return;
      const duration = Number(player.yt.getDuration?.() || 0);
      const nextTime = duration > 0 ? (Number(els.progress.value || 0) / 1000) * duration : 0;
      player.yt.seekTo(nextTime, true);
      player.isScrubbing = false;
      savePlayerState({ force: true, positionSeconds: nextTime });
      syncPlayerUi();
    });

    setRangeFill(els.volume, 1);
  }

  /* Keyboard shortcuts */

  function isTypingTarget(target) {
    if (!(target instanceof Element)) return false;
    const tag = target.tagName.toLowerCase();
    return tag === 'input' || tag === 'textarea' || tag === 'select' || target.isContentEditable;
  }

  function bindKeyboard() {
    document.addEventListener('keydown', (event) => {
      if (isTypingTarget(event.target) || !player.queue || !player.ready) return;
      if (event.code === 'Space') {
        event.preventDefault();
        togglePlayback();
      } else if (event.key === 'ArrowRight' && event.shiftKey) {
        event.preventDefault();
        playIndex(player.index + 1);
      } else if (event.key === 'ArrowLeft' && event.shiftKey) {
        event.preventDefault();
        playIndex(player.index - 1);
      } else if (event.key === 'ArrowRight') {
        event.preventDefault();
        seekBy(10);
      } else if (event.key === 'ArrowLeft') {
        event.preventDefault();
        seekBy(-10);
      }
    });
  }

  /* ------------------------------------------------------------------ *
   * Discovery (search + filter)
   * ------------------------------------------------------------------ */

  function matchesFilter(item, filterValue) {
    if (!filterValue || filterValue === 'all') return true;
    const normalized = normalizeDiscoveryText(filterValue).replace(/\s+/g, '-');
    if (readPipeSet(item.dataset.discoveryFilters).has(normalized)) return true;
    const [kind, rawValue] = filterValue.split(':');
    const value = normalizeDiscoveryText(rawValue).replace(/\s+/g, '-');
    if (kind === 'tag') return readPipeSet(item.dataset.discoveryTags).has(value);
    if (kind === 'state') return readPipeSet(item.dataset.discoveryStates).has(value);
    return true;
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
      const noun = visibleCount === 1 ? singular : plural;
      summary.textContent = query || filterValue !== 'all'
        ? `${visibleCount} ${noun} match the current view.`
        : `Showing all ${visibleCount} ${noun}.`;
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

  function initPage(main) {
    const scope = main || document;

    initReveal(scope);
    initParallaxField(scope);
    initCountUps(scope);

    for (const root of scope.querySelectorAll('[data-discovery]')) {
      initDiscovery(root);
    }

    const payload = readMixPayload(scope);
    initVinyl(scope, payload);

    for (const button of scope.querySelectorAll('[data-play-mix]')) {
      if (payload?.slug) {
        button.dataset.playMixSlug = payload.slug;
        button.dataset.playMixTitle = payload.title || '';
      }
      button.addEventListener('click', () => {
        if (!payload) return;
        if (player.queue && player.queue.slug === payload.slug && player.ready) {
          togglePlayback();
        } else {
          playQueue(payload, 0);
        }
      });
    }

    for (const button of scope.querySelectorAll('[data-track-play]')) {
      button.addEventListener('click', () => {
        const index = Number(button.dataset.trackPlay);
        if (!payload || !Number.isInteger(index)) return;
        playQueue(payload, index);
        try {
          history.replaceState(history.state, '', `#t=${index + 1}`);
        } catch {}
      });
    }

    const deepLinkIndex = parseTrackHash();
    if (payload && deepLinkIndex !== null && deepLinkIndex < payload.videoIds.length) {
      playQueue(payload, deepLinkIndex, { autoplay: false });
      const row = scope.querySelector(`[data-track-index="${deepLinkIndex}"]`);
      if (row) row.scrollIntoView({ block: 'center' });
    }

    syncTracklistUi();
    syncVinylPlayback();
  }

  /* ------------------------------------------------------------------ *
   * pjax router — swap <main>, keep the player alive
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

    const currentAmbient = document.querySelector('[data-ambient]');
    const newAmbient = newDoc.querySelector('[data-ambient]');
    if (currentAmbient && newAmbient) {
      const currentArt = currentAmbient.querySelector('.ambient__art');
      const newArt = newAmbient.querySelector('.ambient__art');
      const currentSrc = currentArt?.getAttribute('src') || '';
      const newSrc = newArt?.getAttribute('src') || '';
      if (currentSrc !== newSrc) {
        if (currentArt) currentArt.remove();
        if (newArt) currentAmbient.prepend(newArt.cloneNode(true));
      }
    }

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
    if (art.classList.contains('is-vinyl-mounted')) return art.querySelector('.mix-hero__vinyl');
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
      if (anchor.closest('.site-header, .player-bar')) continue;
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

  async function navigateTo(url, { push = true, source = null } = {}) {
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
      if (!swapMain(newDoc)) {
        window.location.assign(url);
        return;
      }
      if (push) {
        history.pushState({ pjax: true }, '', url);
      }
      currentPageUrl = window.location.href;
      countPjaxPageview(url);
      const hashIndex = url.indexOf('#');
      if (hashIndex === -1) {
        window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
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
      if (!isRoutableLink(anchor, event)) return;
      event.preventDefault();
      navigateTo(anchor.href, { source: anchor });
    });

    document.addEventListener('mouseover', (event) => {
      const anchor = event.target instanceof Element ? event.target.closest('a') : null;
      if (!isRoutableLink(anchor, null)) return;
      fetchPage(anchor.href).catch(() => {});
    });

    window.addEventListener('popstate', () => {
      navigateTo(window.location.href, { push: false });
    });

    history.replaceState({ pjax: true }, '', window.location.href);
  }

  /* ------------------------------------------------------------------ *
   * Boot
   * ------------------------------------------------------------------ */

  document.addEventListener('DOMContentLoaded', () => {
    // Remember the last real interaction: playback requested right after one
    // is allowed by the browser, so a stall then means an ad, not a block.
    const noteGesture = () => {
      player.lastGestureAt = Date.now();
    };
    document.addEventListener('pointerdown', noteGesture, true);
    document.addEventListener('keydown', noteGesture, true);
    if (bindPlayerElements()) {
      bindPlayerControls();
      bindKeyboard();
      bindRouter();
    }
    initPage(document.querySelector('[data-pjax-root]'));
    maybeShowResumePrompt();
  });

  window.addEventListener?.('pagehide', () => {
    teardownVinyl();
    savePlayerState({ force: true });
  });

  // Internal hooks for automated tests and console debugging only.
  window.__MMM__ = {
    player,
    playIndex,
    togglePlayback,
    recoverStalledPlayback,
    syncPlayerUi,
    teardownVinyl,
    markUnavailable,
    normalizeResumePayload,
    serializeResumeState,
    deserializeResumeState,
    savePlayerState,
    readSavedPlayerState,
    showResumePrompt,
    PLAYER_STATE_STORAGE_KEY,
    PLAYER_STATE_MAX_AGE_MS,
    STALLED_AUTOPLAY_MS,
    STALLED_RECOVERY_SKIP_MS,
    AD_WAIT_NOTICE_MS,
    AD_GRACE_MS,
    setAdWait,
  };
})();
