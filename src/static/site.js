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
const YOUTUBE_MINIMUM_EMBED_SIZE = 220;
const YOUTUBE_EMBED_BLOCKED_CODES = new Set([5, 100, 101, 150]);

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

function getYoutubeAudioPlayerIndex(instance) {
  return Math.min(Math.max(Number(instance.currentIndex) || 0, 0), Math.max(instance.videoIds.length - 1, 0));
}

function findNextYoutubeQueueIndex(instance, activeIndex) {
  for (let index = activeIndex + 1; index < instance.videoIds.length; index += 1) {
    if (!instance.failedIndexes.has(index)) {
      return index;
    }
  }

  for (let index = 0; index < activeIndex; index += 1) {
    if (!instance.failedIndexes.has(index)) {
      return index;
    }
  }

  return -1;
}

function resolveErroredYoutubeQueueIndex(instance) {
  const fallbackIndex = getYoutubeAudioPlayerIndex(instance);
  const erroredVideoId = String(instance.player?.getVideoData?.()?.video_id || '').trim();
  if (!erroredVideoId) return fallbackIndex;

  const matchedIndex = instance.videoIds.findIndex((videoId) => videoId === erroredVideoId);
  return matchedIndex >= 0 ? matchedIndex : fallbackIndex;
}

function syncYoutubeTracklistUi(instance) {
  if (!instance.trackItems.length) return;

  const activeIndex = getYoutubeAudioPlayerIndex(instance);
  instance.trackItems.forEach((item) => {
    const itemIndex = Number(item.dataset.youtubeQueueIndex || -1);
    const isActive = itemIndex === activeIndex;
    item.classList.toggle('is-active', isActive);
    item.element?.setAttribute('aria-current', isActive ? 'true' : 'false');
    item.trigger?.setAttribute('aria-pressed', isActive ? 'true' : 'false');
  });
}

function syncYoutubeAudioPlayerUi(instance) {
  const player = instance.player;
  if (!player || !instance.isReady) return;

  const index = getYoutubeAudioPlayerIndex(instance);
  const currentTime = Number(player.getCurrentTime?.() || 0);
  const duration = Number(player.getDuration?.() || 0);
  const playerState = typeof player.getPlayerState === 'function' ? player.getPlayerState() : -1;
  const isPlaying = window.YT && playerState === window.YT.PlayerState.PLAYING;
  const videoData = typeof player.getVideoData === 'function' ? player.getVideoData() || {} : {};
  const queueCount = instance.videoIds.length;
  const resolvedLabel = instance.trackLabels[index] || videoData.title || `Track ${index + 1}`;
  const hasLinkedTracklist = instance.trackItems.length > 0;

  instance.state.textContent = youtubePlayerStateLabel(playerState);
  instance.state.classList.toggle('is-active', Boolean(isPlaying));
  instance.track.textContent = resolvedLabel;
  instance.meta.textContent = `Track ${index + 1} of ${queueCount}${hasLinkedTracklist ? ' · tracklist below stays in sync' : ''}${videoData.title ? ` · YouTube: ${videoData.title}` : ''}`;
  instance.elapsed.textContent = formatClock(currentTime);
  instance.duration.textContent = formatClock(duration);
  const isMuted = Boolean(player.isMuted?.());
  const toggleLabel = isPlaying ? 'Pause queue' : 'Play queue';
  const muteLabel = isMuted ? 'Unmute audio' : 'Mute audio';

  if (instance.toggleIcon) {
    instance.toggleIcon.className = `ph ${isPlaying ? 'ph-pause' : 'ph-play'}`;
  }
  if (instance.toggleLabel) {
    instance.toggleLabel.textContent = toggleLabel;
  }
  instance.toggle.setAttribute('aria-label', toggleLabel);
  instance.toggle.setAttribute('title', toggleLabel);

  if (instance.muteIcon) {
    instance.muteIcon.className = `ph ${isMuted ? 'ph-speaker-slash' : 'ph-speaker-high'}`;
  }
  if (instance.muteLabel) {
    instance.muteLabel.textContent = muteLabel;
  }
  instance.mute.setAttribute('aria-label', muteLabel);
  instance.mute.setAttribute('title', muteLabel);

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

  syncYoutubeTracklistUi(instance);
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
      instance.shouldAutoplay = false;
      instance.player.pauseVideo();
    } else {
      instance.shouldAutoplay = true;
      requestYoutubePlayback(instance);
    }
    syncYoutubeAudioPlayerUi(instance);
  });

  instance.previous.addEventListener('click', () => {
    playYoutubeQueueIndex(instance, getYoutubeAudioPlayerIndex(instance) - 1);
  });

  instance.next.addEventListener('click', () => {
    playYoutubeQueueIndex(instance, getYoutubeAudioPlayerIndex(instance) + 1);
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

  instance.trackItems.forEach((item) => {
    if (!item.trigger) return;
    item.trigger.addEventListener('click', () => {
      const index = Number(item.dataset.youtubeQueueIndex || -1);
      playYoutubeQueueIndex(instance, index);
    });
  });
}

function playYoutubeQueueIndex(instance, nextIndex, options = {}) {
  const { autoplay = true } = options;
  if (!instance.player || !instance.isReady) return;
  if (!Number.isInteger(nextIndex) || nextIndex < 0 || nextIndex >= instance.videoIds.length) return;

  instance.currentIndex = nextIndex;
  instance.shouldAutoplay = Boolean(autoplay);
  const videoId = instance.videoIds[nextIndex];
  if (!videoId) return;

  if (autoplay) {
    instance.player.loadVideoById(videoId);
  } else {
    instance.player.cueVideoById(videoId);
  }

  syncYoutubeAudioPlayerUi(instance);
}

function requestYoutubePlayback(instance) {
  if (!instance.player || !instance.isReady || !window.YT) return;

  const currentIndex = getYoutubeAudioPlayerIndex(instance);
  const currentVideoId = instance.videoIds[currentIndex];
  if (!currentVideoId) return;

  try {
    instance.player.unMute?.();
  } catch {}

  const playerState = typeof instance.player.getPlayerState === 'function' ? instance.player.getPlayerState() : -1;
  const shouldLoadWithinGesture = [
    window.YT.PlayerState.CUED,
    window.YT.PlayerState.UNSTARTED,
    window.YT.PlayerState.ENDED,
  ].includes(playerState);

  try {
    if (shouldLoadWithinGesture) {
      instance.player.loadVideoById(currentVideoId);
    } else {
      instance.player.playVideo();
    }
  } catch {}

  window.setTimeout(() => {
    if (!instance.player || !instance.isReady || !instance.shouldAutoplay || !window.YT) return;
    const nextState = typeof instance.player.getPlayerState === 'function' ? instance.player.getPlayerState() : -1;
    if (nextState === window.YT.PlayerState.PLAYING || nextState === window.YT.PlayerState.BUFFERING) {
      return;
    }

    try {
      instance.player.playVideo();
    } catch {}
  }, 700);
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
    currentIndex: 0,
    isReady: false,
    isScrubbing: false,
    shouldAutoplay: false,
    pollTimer: null,
    player: null,
    failedIndexes: new Set(),
    queueKey: String(root.dataset.queueKey || '').trim(),
    state: root.querySelector('[data-youtube-player-state]'),
    track: root.querySelector('[data-youtube-player-track]'),
    meta: root.querySelector('[data-youtube-player-meta]'),
    progress: root.querySelector('[data-youtube-player-progress]'),
    elapsed: root.querySelector('[data-youtube-player-elapsed]'),
    duration: root.querySelector('[data-youtube-player-duration]'),
    previous: root.querySelector('[data-youtube-player-previous]'),
    toggle: root.querySelector('[data-youtube-player-toggle]'),
    toggleIcon: root.querySelector('[data-youtube-player-toggle-icon]'),
    toggleLabel: root.querySelector('[data-youtube-player-toggle-label]'),
    next: root.querySelector('[data-youtube-player-next]'),
    mute: root.querySelector('[data-youtube-player-mute]'),
    muteIcon: root.querySelector('[data-youtube-player-mute-icon]'),
    muteLabel: root.querySelector('[data-youtube-player-mute-label]'),
    volume: root.querySelector('[data-youtube-player-volume]'),
    host: root.querySelector('[data-youtube-player-host]'),
    trackItems: [],
  };

  if (instance.queueKey) {
    const tracklist = document.querySelector(`[data-youtube-queue-tracklist="${instance.queueKey}"]`);
    if (tracklist) {
      instance.trackItems = Array.from(tracklist.querySelectorAll('[data-youtube-queue-index]')).map((item) => ({
        element: item,
        dataset: item.dataset,
        classList: item.classList,
        trigger: item.querySelector('[data-youtube-track-trigger]'),
      }));
    }
  }

  bindYoutubeAudioPlayerEvents(instance);
  setYoutubeAudioPlayerDisabled(instance, true);
  syncYoutubeTracklistUi(instance);

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
    width: String(YOUTUBE_MINIMUM_EMBED_SIZE),
    height: String(YOUTUBE_MINIMUM_EMBED_SIZE),
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
        instance.currentIndex = 0;
        event.target.cueVideoById(instance.videoIds[0]);
        try {
          event.target.setVolume(Number(instance.volume.value || 100));
        } catch {}
        setYoutubeAudioPlayerDisabled(instance, false);
        startYoutubeAudioPlayerPolling(instance);
      },
      onStateChange: (event) => {
        if (window.YT && event.data === window.YT.PlayerState.ENDED) {
          const activeIndex = getYoutubeAudioPlayerIndex(instance);
          if (activeIndex < instance.videoIds.length - 1) {
            playYoutubeQueueIndex(instance, activeIndex + 1);
            return;
          }
        }
        syncYoutubeAudioPlayerUi(instance);
      },
      onError: (event) => {
        const errorCode = Number(event?.data);
        const shouldSkip = YOUTUBE_EMBED_BLOCKED_CODES.has(errorCode);
        const currentIndex = getYoutubeAudioPlayerIndex(instance);
        const erroredIndex = resolveErroredYoutubeQueueIndex(instance);

        if (erroredIndex !== currentIndex) {
          return;
        }

        if (instance.failedIndexes.has(erroredIndex)) {
          return;
        }

        instance.failedIndexes.add(erroredIndex);

        if (shouldSkip) {
          const fallbackIndex = findNextYoutubeQueueIndex(instance, erroredIndex);
          if (fallbackIndex >= 0) {
            instance.currentIndex = fallbackIndex;
            const fallbackVideoId = instance.videoIds[fallbackIndex];

            try {
              if (instance.shouldAutoplay) {
                instance.player.loadVideoById(fallbackVideoId);
              } else {
                instance.player.cueVideoById(fallbackVideoId);
              }
            } catch {}

            if (instance.meta) {
              instance.meta.textContent = instance.shouldAutoplay
                ? `Track ${erroredIndex + 1} is blocked for embedded playback. Skipping to track ${fallbackIndex + 1}.`
                : `Track ${erroredIndex + 1} is blocked for embedded playback. Queued track ${fallbackIndex + 1} instead.`;
            }
            syncYoutubeTracklistUi(instance);
            return;
          }
        }

        instance.shouldAutoplay = false;
        if (instance.meta) {
          instance.meta.textContent = 'Playback is unavailable for this queue here. Open it on YouTube instead.';
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
