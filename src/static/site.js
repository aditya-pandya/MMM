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

let youtubeIframeApiPromise = null;

function loadYoutubeIframeApi() {
  if (window.YT && window.YT.Player) {
    return Promise.resolve(window.YT);
  }

  if (youtubeIframeApiPromise) {
    return youtubeIframeApiPromise;
  }

  youtubeIframeApiPromise = new Promise((resolve, reject) => {
    const existingScript = document.querySelector('script[src="https://www.youtube.com/iframe_api"]');
    const previousReady = window.onYouTubeIframeAPIReady;
    const finish = () => resolve(window.YT);

    window.onYouTubeIframeAPIReady = () => {
      if (typeof previousReady === 'function') {
        previousReady();
      }
      finish();
    };

    if (!existingScript) {
      const script = document.createElement('script');
      script.src = 'https://www.youtube.com/iframe_api';
      script.async = true;
      script.onerror = () => reject(new Error('Failed to load the YouTube IFrame Player API.'));
      document.head.append(script);
    }
  });

  return youtubeIframeApiPromise;
}

function youtubePlayerStateLabel(code) {
  if (!window.YT || !window.YT.PlayerState) return 'Loading';

  switch (code) {
    case window.YT.PlayerState.PLAYING:
      return 'Playing';
    case window.YT.PlayerState.PAUSED:
      return 'Paused';
    case window.YT.PlayerState.BUFFERING:
      return 'Buffering';
    case window.YT.PlayerState.CUED:
      return 'Ready';
    case window.YT.PlayerState.ENDED:
      return 'Ended';
    default:
      return 'Loading';
  }
}

function readJsonDataset(element, key, fallback) {
  try {
    const raw = element.dataset[key];
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function setYoutubeAudioPlayerDisabled(instance, disabled) {
  instance.previous.disabled = disabled;
  instance.toggle.disabled = disabled;
  instance.next.disabled = disabled;
  instance.mute.disabled = disabled;
  instance.volume.disabled = disabled;
  instance.progress.disabled = disabled;
}

function syncYoutubeAudioPlayerUi(instance) {
  const player = instance.player;
  if (!player || !instance.isReady || typeof player.getPlaylistIndex !== 'function') return;

  const index = Math.max(0, Number(player.getPlaylistIndex?.() || 0));
  const currentTime = Number(player.getCurrentTime?.() || 0);
  const duration = Number(player.getDuration?.() || 0);
  const playerState = typeof player.getPlayerState === 'function' ? player.getPlayerState() : -1;
  const isPlaying = window.YT && playerState === window.YT.PlayerState.PLAYING;
  const videoData = typeof player.getVideoData === 'function' ? player.getVideoData() || {} : {};
  const queueCount = instance.videoIds.length;
  const resolvedLabel = instance.trackLabels[index] || videoData.title || `Track ${index + 1}`;

  instance.state.textContent = youtubePlayerStateLabel(playerState);
  instance.state.classList.toggle('is-active', Boolean(isPlaying));
  instance.track.textContent = resolvedLabel;
  instance.meta.textContent = `Track ${index + 1} of ${queueCount}${videoData.title ? ` · YouTube: ${videoData.title}` : ''}`;
  instance.elapsed.textContent = formatClock(currentTime);
  instance.duration.textContent = formatClock(duration);
  instance.toggle.textContent = isPlaying ? 'Pause' : 'Play';
  instance.mute.textContent = player.isMuted?.() ? 'Unmute' : 'Mute';
  instance.previous.disabled = index <= 0;
  instance.next.disabled = index >= queueCount - 1;
  instance.mute.disabled = false;
  instance.volume.disabled = false;
  instance.toggle.disabled = false;
  instance.progress.disabled = duration <= 0;

  if (!instance.isScrubbing && duration > 0) {
    instance.progress.value = String(Math.min(1000, Math.round((currentTime / duration) * 1000)));
  }

  if (typeof player.getVolume === 'function') {
    instance.volume.value = String(player.getVolume());
  }
}

function startYoutubeAudioPlayerPolling(instance) {
  window.clearInterval(instance.pollTimer);
  instance.pollTimer = window.setInterval(() => syncYoutubeAudioPlayerUi(instance), 500);
  syncYoutubeAudioPlayerUi(instance);
}

function bindYoutubeAudioPlayerEvents(instance) {
  instance.toggle.addEventListener('click', () => {
    if (!instance.player || !instance.isReady || !window.YT) return;
    if (instance.player.getPlayerState() === window.YT.PlayerState.PLAYING) {
      instance.player.pauseVideo();
    } else {
      instance.player.playVideo();
    }
    syncYoutubeAudioPlayerUi(instance);
  });

  instance.previous.addEventListener('click', () => {
    if (!instance.player || !instance.isReady) return;
    instance.player.previousVideo();
    syncYoutubeAudioPlayerUi(instance);
  });

  instance.next.addEventListener('click', () => {
    if (!instance.player || !instance.isReady) return;
    instance.player.nextVideo();
    syncYoutubeAudioPlayerUi(instance);
  });

  instance.mute.addEventListener('click', () => {
    if (!instance.player || !instance.isReady) return;
    if (instance.player.isMuted()) {
      instance.player.unMute();
    } else {
      instance.player.mute();
    }
    syncYoutubeAudioPlayerUi(instance);
  });

  instance.volume.addEventListener('input', () => {
    if (!instance.player || !instance.isReady) return;
    instance.player.setVolume(Number(instance.volume.value || 100));
    if (instance.player.isMuted() && Number(instance.volume.value || 0) > 0) {
      instance.player.unMute();
    }
    syncYoutubeAudioPlayerUi(instance);
  });

  instance.progress.addEventListener('input', () => {
    if (!instance.player || !instance.isReady) return;
    instance.isScrubbing = true;
    const duration = Number(instance.player.getDuration?.() || 0);
    const nextTime = duration > 0 ? (Number(instance.progress.value || 0) / 1000) * duration : 0;
    instance.elapsed.textContent = formatClock(nextTime);
  });

  instance.progress.addEventListener('change', () => {
    if (!instance.player || !instance.isReady) return;
    const duration = Number(instance.player.getDuration?.() || 0);
    const nextTime = duration > 0 ? (Number(instance.progress.value || 0) / 1000) * duration : 0;
    instance.player.seekTo(nextTime, true);
    instance.isScrubbing = false;
    syncYoutubeAudioPlayerUi(instance);
  });
}

async function initYoutubeAudioPlayer(root, index) {
  const videoIds = readJsonDataset(root, 'videoIds', [])
    .map((value) => String(value || '').trim())
    .filter(Boolean);

  if (!videoIds.length) return;

  const instance = {
    root,
    videoIds,
    trackLabels: readJsonDataset(root, 'trackLabels', []).map((value) => String(value || '').trim()),
    isReady: false,
    isScrubbing: false,
    pollTimer: null,
    player: null,
    state: root.querySelector('[data-youtube-player-state]'),
    track: root.querySelector('[data-youtube-player-track]'),
    meta: root.querySelector('[data-youtube-player-meta]'),
    progress: root.querySelector('[data-youtube-player-progress]'),
    elapsed: root.querySelector('[data-youtube-player-elapsed]'),
    duration: root.querySelector('[data-youtube-player-duration]'),
    previous: root.querySelector('[data-youtube-player-previous]'),
    toggle: root.querySelector('[data-youtube-player-toggle]'),
    next: root.querySelector('[data-youtube-player-next]'),
    mute: root.querySelector('[data-youtube-player-mute]'),
    volume: root.querySelector('[data-youtube-player-volume]'),
    host: root.querySelector('[data-youtube-player-host]'),
  };

  bindYoutubeAudioPlayerEvents(instance);
  setYoutubeAudioPlayerDisabled(instance, true);

  try {
    await loadYoutubeIframeApi();
  } catch {
    if (instance.meta) {
      instance.meta.textContent = 'Playback is unavailable here. Open the queue on YouTube instead.';
    }
    if (instance.state) {
      instance.state.textContent = 'Unavailable';
    }
    return;
  }

  const mountId = `youtube-audio-player-${index + 1}`;
  if (instance.host && !instance.host.querySelector(`#${mountId}`)) {
    const mount = document.createElement('div');
    mount.id = mountId;
    instance.host.replaceChildren(mount);
  }

  instance.player = new window.YT.Player(mountId, {
    width: '1',
    height: '1',
    videoId: instance.videoIds[0],
    playerVars: {
      autoplay: 0,
      controls: 0,
      modestbranding: 1,
      rel: 0,
      playsinline: 1,
    },
    events: {
      onReady: (event) => {
        instance.isReady = true;
        event.target.cuePlaylist(instance.videoIds, 0, 0);
        try {
          event.target.setVolume(Number(instance.volume.value || 100));
        } catch {}
        setYoutubeAudioPlayerDisabled(instance, false);
        startYoutubeAudioPlayerPolling(instance);
      },
      onStateChange: () => {
        syncYoutubeAudioPlayerUi(instance);
      },
      onError: () => {
        if (instance.meta) {
          instance.meta.textContent = 'Playback hit a YouTube error. Open the queue on YouTube instead.';
        }
        if (instance.state) {
          instance.state.textContent = 'Error';
          instance.state.classList.remove('is-active');
        }
      },
    },
  });
}

function initYoutubeAudioPlayers() {
  const roots = document.querySelectorAll('[data-youtube-audio-player]');
  roots.forEach((root, index) => {
    initYoutubeAudioPlayer(root, index);
  });
}

function readPipeSet(value) {
  return new Set(
    String(value || '')
      .split('|')
      .map((item) => item.trim().toLowerCase())
      .filter(Boolean)
  );
}

function matchesFilter(item, filterValue) {
  if (!filterValue || filterValue === 'all') return true;

  const normalizedFilterValue = normalizeDiscoveryText(filterValue).replace(/\s+/g, '-');
  const genericFilters = readPipeSet(item.dataset.discoveryFilters);
  if (genericFilters.has(normalizedFilterValue)) {
    return true;
  }

  const [kind, rawValue] = filterValue.split(':');
  const value = normalizeDiscoveryText(rawValue).replace(/\s+/g, '-');

  if (kind === 'tag') {
    return readPipeSet(item.dataset.discoveryTags).has(value);
  }

  if (kind === 'state') {
    return readPipeSet(item.dataset.discoveryStates).has(value);
  }

  return true;
}

function matchesQuery(item, query) {
  if (!query) return true;

  const haystack = normalizeDiscoveryText(item.dataset.discoverySearch);
  const terms = query.split(' ').filter(Boolean);

  return terms.every((term) => haystack.includes(term));
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

  if (emptyState) {
    emptyState.hidden = visibleCount !== 0;
  }
}

function initDiscovery(root) {
  const input = root.querySelector('[data-discovery-input]');
  const buttons = Array.from(root.querySelectorAll('[data-discovery-filter]'));

  if (input) {
    input.addEventListener('input', () => updateDiscovery(root));
  }

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

document.addEventListener('DOMContentLoaded', () => {
  const discoveryRoots = document.querySelectorAll('[data-discovery]');
  for (const root of discoveryRoots) {
    initDiscovery(root);
  }

  initYoutubeAudioPlayers();
});
