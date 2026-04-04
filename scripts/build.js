const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const DIST = path.join(ROOT, 'dist');
const DATA_DIR = path.join(ROOT, 'data');
const STATIC_DIR = path.join(ROOT, 'src', 'static');

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function resetDir(dirPath) {
  ensureDir(dirPath);

  for (const entry of fs.readdirSync(dirPath, { withFileTypes: true })) {
    try {
      fs.rmSync(path.join(dirPath, entry.name), { recursive: true, force: true });
    } catch {}
  }
}

function walkJsonFiles(dirPath) {
  if (!fs.existsSync(dirPath)) return [];

  const results = [];
  for (const entry of fs.readdirSync(dirPath, { withFileTypes: true })) {
    const fullPath = path.join(dirPath, entry.name);

    if (entry.isDirectory()) {
      results.push(...walkJsonFiles(fullPath));
    } else if (entry.isFile() && entry.name.endsWith('.json')) {
      results.push(fullPath);
    }
  }

  return results;
}

function readJsonIfExists(filePath, fallback) {
  if (!fs.existsSync(filePath)) return fallback;

  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (error) {
    console.warn(`Could not parse ${path.relative(ROOT, filePath)}: ${error.message}`);
    return fallback;
  }
}

function copyDir(source, destination) {
  if (!fs.existsSync(source)) return;

  ensureDir(destination);

  for (const entry of fs.readdirSync(source, { withFileTypes: true })) {
    const sourcePath = path.join(source, entry.name);
    const destPath = path.join(destination, entry.name);

    if (entry.isDirectory()) {
      copyDir(sourcePath, destPath);
    } else {
      fs.copyFileSync(sourcePath, destPath);
    }
  }
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function stripHtml(value) {
  return String(value ?? '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

function paragraphize(text) {
  const raw = String(text ?? '').trim();
  if (!raw) return '';

  return raw
    .split(/\n\s*\n/)
    .map((paragraph) => `<p>${escapeHtml(paragraph).replace(/\n/g, '<br>')}</p>`)
    .join('');
}

function formatDate(value) {
  if (!value) return 'Date forthcoming';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);

  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(date);
}

function formatMonthYear(value) {
  if (!value) return 'Unscheduled';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);

  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'long',
  }).format(date);
}

function slugify(value) {
  return String(value ?? '')
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function flattenToArray(value) {
  if (!value) return [];
  if (!Array.isArray(value)) return [value];

  const items = [];
  for (const entry of value) {
    items.push(...flattenToArray(entry));
  }
  return items;
}

function sortMixes(mixes) {
  return [...mixes].sort((a, b) => {
    const aDate = a.date ? new Date(a.date).getTime() : -Infinity;
    const bDate = b.date ? new Date(b.date).getTime() : -Infinity;

    if (aDate !== bDate) return bDate - aDate;

    const aNumber = Number(a.number ?? a.issue ?? -Infinity);
    const bNumber = Number(b.number ?? b.issue ?? -Infinity);

    if (!Number.isNaN(aNumber) && !Number.isNaN(bNumber) && aNumber !== bNumber) {
      return bNumber - aNumber;
    }

    return String(a.title ?? '').localeCompare(String(b.title ?? ''));
  });
}

function sortNotes(notes) {
  return [...notes].sort((a, b) => {
    const aDate = a.date ? new Date(a.date).getTime() : -Infinity;
    const bDate = b.date ? new Date(b.date).getTime() : -Infinity;

    if (aDate !== bDate) return bDate - aDate;

    return String(a.title ?? '').localeCompare(String(b.title ?? ''));
  });
}

function sortDrafts(drafts) {
  return [...drafts].sort((a, b) => {
    const aDate = a.date ? new Date(a.date).getTime() : -Infinity;
    const bDate = b.date ? new Date(b.date).getTime() : -Infinity;

    if (aDate !== bDate) return bDate - aDate;

    return String(a.title ?? '').localeCompare(String(b.title ?? ''));
  });
}

function toArray(value) {
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
}

function isLikelyUrl(value) {
  return /^https?:\/\//i.test(String(value || '').trim());
}

function normalizeListeningKey(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '');
}

function providerLabelFromKey(value) {
  const raw = String(value || '').trim();
  const normalized = normalizeListeningKey(raw);

  if (!normalized) return '';

  const knownProviders = {
    applemusic: 'Apple Music',
    bandcamp: 'Bandcamp',
    mixcloud: 'Mixcloud',
    soundcloud: 'SoundCloud',
    spotify: 'Spotify',
    youtube: 'YouTube',
  };

  if (knownProviders[normalized]) return knownProviders[normalized];

  return raw
    .replace(/[_-]+/g, ' ')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function inferProviderFromUrl(url) {
  const href = String(url || '').toLowerCase();
  if (!href) return 'Listening link';
  if (href.includes('spotify.com')) return 'Spotify';
  if (href.includes('music.apple.com')) return 'Apple Music';
  if (href.includes('youtube.com') || href.includes('youtu.be')) return 'YouTube';
  if (href.includes('bandcamp.com')) return 'Bandcamp';
  if (href.includes('soundcloud.com')) return 'SoundCloud';
  if (href.includes('mixcloud.com')) return 'Mixcloud';
  return 'Listening link';
}

function inferProviderKind(url) {
  const href = String(url || '').toLowerCase();
  if (!href) return 'listen';
  if (href.includes('/embed/') || href.includes('/embed?') || href.includes('youtube.com/embed/') || href.includes('/oembed')) return 'embed';
  if (href.includes('/playlist/')) return 'playlist';
  if (href.includes('/album/')) return 'album';
  if (href.includes('/track/') || href.includes('/song/')) return 'track';
  if (href.includes('/sets/')) return 'set';
  if (href.includes('videoseries')) return 'playlist';
  return 'listen';
}

function isMegaUrl(url) {
  const href = String(url || '').toLowerCase();
  return href.includes('mega.co.nz') || href.includes('mega.nz');
}

function isTumblrLegacyCover(mix) {
  const sourcePlatform = String(mix?.source?.platform || mix?.sourcePlatform || '').toLowerCase();
  const imageUrl = String(mix?.cover?.imageUrl || mix?.image || '').toLowerCase();
  return sourcePlatform === 'tumblr' && imageUrl.includes('media.tumblr.com');
}

function sanitizeLegacyHtml(html) {
  let cleaned = String(html || '').trim();
  if (!cleaned) return '';

  cleaned = cleaned.replace(/<p>\s*<figure[\s\S]*?<\/figure>\s*<\/p>/gi, '');
  cleaned = cleaned.replace(/<figure[\s\S]*?<\/figure>/gi, '');
  cleaned = cleaned.replace(/<a\b[^>]*href="https?:\/\/(?:www\.)?(?:mega\.co\.nz|mega\.nz)[^"]*"[^>]*>[\s\S]*?<\/a>/gi, '');
  cleaned = cleaned.replace(/<p>\s*(?:Download(?: album)?\s*:?)?\s*(?:\||&nbsp;|\u00a0|\s)*<\/p>/gi, '');
  cleaned = cleaned.replace(/<p>\s*<\/p>/gi, '');

  return cleaned.trim();
}

function normalizeComparableText(value) {
  return stripHtml(String(value || ''))
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
}

function splitParagraphs(value) {
  return String(value || '')
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
}

function buildTrackSearchLinks(track) {
  if (!track || typeof track !== 'object') return null;

  const artist = String(track.artist || '').trim();
  const title = String(track.title || '').trim();
  const displayText = String(track.displayText || '').trim();
  const position = Number(track.position || 0);
  const query = [artist, title].filter(Boolean).join(' ').trim() || displayText;

  if (!query) return null;

  return {
    position,
    artist,
    title,
    displayText: displayText || query,
    youtubeUrl: `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}`,
    isFavorite: Boolean(track.isFavorite),
  };
}

function getYouTubePlaylistId(value) {
  const raw = String(value || '').trim();
  if (!raw || !raw.includes('youtu')) return '';

  try {
    const url = new URL(raw);
    const hostname = url.hostname.toLowerCase();
    if (!hostname.includes('youtube.com') && !hostname.includes('youtu.be')) return '';
    return String(url.searchParams.get('list') || '').trim();
  } catch {
    return '';
  }
}

function isYouTubePlaylistProvider(provider) {
  if (!provider || typeof provider !== 'object') return false;
  return provider.provider === 'YouTube' && Boolean(getYouTubePlaylistId(provider.url));
}

function isYouTubePlaylistEmbed(embed) {
  if (!embed || typeof embed !== 'object') return false;
  const url = String(embed.url || '');
  return embed.provider === 'YouTube' && Boolean(getYouTubePlaylistId(url)) && url.includes('/embed/videoseries');
}

function getDistinctMixNotes(mix) {
  const blocked = new Set(
    [mix.excerpt, mix.coverCredit, mix.summary]
      .map((value) => normalizeComparableText(value))
      .filter(Boolean)
  );

  return splitParagraphs(mix.notes).filter((paragraph) => {
    const normalized = normalizeComparableText(paragraph);
    if (!normalized || blocked.has(normalized)) return false;
    if (mix.coverCredit && normalized.includes(normalizeComparableText(mix.coverCredit))) return false;
    return true;
  });
}

function resolvePlaylistEmbed(mix) {
  const providers = Array.isArray(mix.listening?.providers) ? mix.listening.providers : [];
  const embeds = Array.isArray(mix.listening?.embeds) ? mix.listening.embeds : [];
  const providerIds = new Set(providers.map((provider) => getYouTubePlaylistId(provider.url)).filter(Boolean));

  for (const embed of embeds) {
    if (!isYouTubePlaylistEmbed(embed)) continue;

    const playlistId = getYouTubePlaylistId(embed.url);
    if (!providerIds.size || providerIds.has(playlistId)) return embed;
  }

  return null;
}

function getCompactListeningLinks(mix) {
  const providers = Array.isArray(mix.listening?.providers) ? mix.listening.providers : [];
  const allowedKinds = new Set(['playlist', 'album', 'track', 'set']);

  return providers.filter((provider) => {
    if (!provider || typeof provider !== 'object') return false;
    const url = String(provider.url || '').trim();
    const kind = String(provider.kind || '').trim().toLowerCase();
    if (!url) return false;
    return allowedKinds.has(kind);
  });
}

function collectListeningEntries(rawEntries, mode = 'provider', startMode = mode) {
  const items = [];
  const providerContainerKeys = new Set(['providers', 'links', 'providerlinks', 'streaming', 'entries', 'items', 'sources']);
  const embedContainerKeys = new Set(['embeds', 'embed', 'players', 'iframes']);
  const metaKeys = new Set(['url', 'href', 'src', 'provider', 'label', 'title', 'kind', 'note', 'summary', 'intro', 'description']);

  function visit(value, currentMode = startMode, providerHint = '') {
    if (!value) return;

    if (Array.isArray(value)) {
      for (const entry of value) {
        visit(entry, currentMode, providerHint);
      }
      return;
    }

    if (typeof value === 'string') {
      const url = value.trim();
      if (!url || !isLikelyUrl(url) || isMegaUrl(url)) return;

      if (currentMode === 'embed') {
        items.push({
          mode: currentMode,
          provider: providerHint || inferProviderFromUrl(url),
          title: '',
          url,
          note: '',
        });
        return;
      }

      items.push({
        mode: currentMode,
        provider: providerHint || inferProviderFromUrl(url),
        label: '',
        url,
        kind: inferProviderKind(url),
        note: '',
      });
      return;
    }

    if (typeof value !== 'object') return;

    const url = String(value.url || value.href || value.src || '').trim();
    if (url && !isMegaUrl(url)) {
      if (currentMode === 'embed') {
        items.push({
          mode: currentMode,
          provider: value.provider || providerHint || inferProviderFromUrl(url),
          title: value.title || value.label || '',
          url,
          note: value.note || value.summary || '',
        });
      } else {
        items.push({
          mode: currentMode,
          provider: value.provider || providerHint || inferProviderFromUrl(url),
          label: value.label || value.title || '',
          url,
          kind: value.kind || inferProviderKind(url),
          note: value.note || value.summary || '',
        });
      }
    }

    for (const [key, child] of Object.entries(value)) {
      const normalizedKey = normalizeListeningKey(key);
      if (!child || metaKeys.has(normalizedKey)) continue;

      const nextMode = embedContainerKeys.has(normalizedKey)
        ? 'embed'
        : providerContainerKeys.has(normalizedKey)
          ? 'provider'
          : currentMode;
      const nextHint = providerContainerKeys.has(normalizedKey) || embedContainerKeys.has(normalizedKey)
        ? providerHint
        : providerLabelFromKey(key) || providerHint;

      visit(child, nextMode, nextHint);
    }
  }

  for (const entry of flattenToArray(rawEntries)) {
    visit(entry, startMode, '');
  }

  const deduped = new Map();
  for (const item of items) {
    if (item.mode !== mode) continue;

    const url = String(item.url || '').trim();
    if (!url) continue;

    const provider = String(item.provider || inferProviderFromUrl(url)).trim() || (mode === 'embed' ? 'Embed' : 'Listening link');
    const key = `${provider}::${url}`;
    if (deduped.has(key)) continue;

    if (mode === 'embed') {
      deduped.set(key, {
        provider,
        title: String(item.title || '').trim(),
        url,
        note: String(item.note || '').trim(),
      });
      continue;
    }

    deduped.set(key, {
      provider,
      label: String(item.label || '').trim(),
      url,
      kind: String(item.kind || inferProviderKind(url)).trim() || 'listen',
      note: String(item.note || '').trim(),
    });
  }

  return Array.from(deduped.values());
}

function normalizeListening(mix) {
  const listening = mix.listening && typeof mix.listening === 'object' ? mix.listening : {};
  const providerRoots = [
    listening.providers,
    listening.links,
    mix.providers,
    mix.providerLinks,
    mix.streaming,
  ];
  const embedRoots = [
    listening.embeds,
    mix.embeds,
  ];
  const providerEntries = collectListeningEntries(providerRoots, 'provider', 'provider');
  const explicitEmbeds = [
    ...collectListeningEntries(providerRoots, 'embed', 'provider').filter((entry) => inferProviderKind(entry.url) === 'embed'),
    ...collectListeningEntries(embedRoots, 'embed', 'embed'),
  ];
  const derivedEmbeds = providerEntries
    .filter((provider) => isYouTubePlaylistProvider(provider))
    .map((provider) => {
      const playlistId = getYouTubePlaylistId(provider.url);
      return {
        provider: provider.provider,
        title: provider.label || `${provider.provider} playlist`,
        url: `https://www.youtube.com/embed/videoseries?list=${encodeURIComponent(playlistId)}`,
        note: provider.note,
      };
    });
  const embedEntries = Array.from(
    new Map(
      [...derivedEmbeds, ...explicitEmbeds]
        .filter((entry) => {
          if (!entry || typeof entry !== 'object') return false;
          if (isYouTubePlaylistEmbed(entry)) return true;
          return Boolean(String(entry.provider || '').trim() && String(entry.url || '').trim());
        })
        .map((entry) => [`${entry.provider}::${entry.url}`, entry])
    ).values()
  );

  return {
    intro: String(listening.intro || listening.summary || mix.listeningIntro || '').trim(),
    providers: providerEntries,
    embeds: embedEntries,
  };
}

function normalizeMixes(rawMixes) {
  if (!Array.isArray(rawMixes)) return [];

  return sortMixes(
    rawMixes.map((mix, index) => {
      const title = mix.displayTitle || mix.title || mix.name || `Untitled Mix ${index + 1}`;
      const intro = Array.isArray(mix.intro) ? mix.intro.join('\n\n') : '';
      const slug = mix.slug || slugify(title) || `mix-${index + 1}`;
      const excerpt = mix.excerpt || mix.summary || mix.description || intro || 'A hand-built mix, archived carefully.';
      const notes = mix.notes || mix.body || mix.story || intro || '';
      const tracklist = Array.isArray(mix.tracklist)
        ? mix.tracklist
        : Array.isArray(mix.tracks)
          ? mix.tracks
          : [];
      const tags = Array.isArray(mix.tags) ? mix.tags : [];
      const archivalCover = isTumblrLegacyCover(mix);
      const links = {
        ...(mix.links && typeof mix.links === 'object' ? mix.links : {}),
        ...(mix.download?.url ? { [mix.download.label || 'Download mix']: mix.download.url } : {}),
      };
      const primaryLinks = Object.fromEntries(
        Object.entries(links).filter(([, href]) => typeof href === 'string' && href.trim() && !isMegaUrl(href))
      );
      const legacyLinks = Object.fromEntries(
        Object.entries(links).filter(([, href]) => typeof href === 'string' && href.trim() && isMegaUrl(href))
      );

      return {
        ...mix,
        title,
        slug,
        excerpt,
        notes,
        tracklist,
        tags,
        links,
        date: mix.date || mix.published_at || mix.publishDate || mix.publishedAt || '',
        number: mix.number ?? mix.issue ?? mix.volume ?? mix.mixNumber ?? '',
        runtime: mix.runtime || mix.duration || '',
        image: archivalCover ? '' : mix.image || mix.coverImage || mix.heroImage || mix.cover?.imageUrl || '',
        imageAlt: mix.imageAlt || mix.coverAlt || mix.cover?.alt || `${title} artwork`,
        coverCredit: mix.cover?.credit || mix.coverCredit || '',
        sourceUrl: mix.source?.sourceUrl || mix.sourceUrl || '',
        sourcePlatform: mix.source?.platform || mix.sourcePlatform || '',
        legacyHtml: sanitizeLegacyHtml(mix.legacy?.descriptionHtml || mix.descriptionHtml || ''),
        primaryLinks,
        legacyLinks,
        usesArchivalCoverFallback: archivalCover,
        listening: normalizeListening(mix),
      };
    })
  );
}

function normalizeDrafts(rawDrafts) {
  if (!Array.isArray(rawDrafts)) return [];

  return sortDrafts(
    rawDrafts.map((draft, index) => {
      const title = String(draft.title || `Draft ${index + 1}`).trim();
      const slug = String(draft.slug || slugify(title) || `draft-${index + 1}`).trim();
      const notes = String(draft.notes || '').trim();
      const tracks = Array.isArray(draft.tracks) ? draft.tracks : [];

      return {
        ...draft,
        title,
        slug,
        status: String(draft.status || 'draft').trim(),
        date: draft.date || '',
        summary: String(draft.summary || '').trim(),
        notes,
        excerpt: String(draft.summary || notes || 'Editorial draft in progress.').trim(),
        trackCount: tracks.length,
        favoriteCount: tracks.filter((track) => track?.favorite || track?.is_favorite).length,
        tags: Array.isArray(draft.tags) ? draft.tags : [],
      };
    })
  );
}

function normalizeNote(note, index = 0) {
  const bodyParagraphs = Array.isArray(note.body)
    ? note.body.filter((item) => typeof item === 'string' && item.trim())
    : typeof note.body === 'string' && note.body.trim()
      ? [note.body.trim()]
      : typeof note.content === 'string' && note.content.trim()
        ? [note.content.trim()]
        : [];
  const relatedMixSlugs = Array.isArray(note.relatedMixSlugs)
    ? note.relatedMixSlugs.filter(Boolean)
    : note.mixSlug || note.mix_slug
      ? [note.mixSlug || note.mix_slug]
      : [];

  return {
    ...note,
    title: note.title || `Note ${index + 1}`,
    slug: note.slug || slugify(note.title || `note-${index + 1}`),
    date: note.publishedAt || note.date || note.published_at || '',
    excerpt: note.excerpt || note.summary || note.description || '',
    body: bodyParagraphs.join('\n\n'),
    bodyParagraphs,
    relatedMixSlugs,
    tags: Array.isArray(note.tags) ? note.tags : [],
  };
}

function normalizeNotes(raw) {
  if (!raw) return [];
  const items = Array.isArray(raw) ? raw : Array.isArray(raw.notes) ? raw.notes : [];

  return sortNotes(items.map((note, index) => normalizeNote(note, index)));
}

function loadMixes() {
  const directMixes = readJsonIfExists(path.join(DATA_DIR, 'mixes.json'), null);
  const archiveIndex = readJsonIfExists(path.join(DATA_DIR, 'archive', 'index.json'), null);
  const publishedMixFiles = walkJsonFiles(path.join(DATA_DIR, 'published'));
  const importedMixFiles = walkJsonFiles(path.join(DATA_DIR, 'imported', 'mixes'));

  const publishedMixes = publishedMixFiles
    .map((filePath) => readJsonIfExists(filePath, null))
    .filter(Boolean);

  const importedMixes = importedMixFiles
    .map((filePath) => readJsonIfExists(filePath, null))
    .filter(Boolean)
    .filter((mix) => !mix.status || mix.status === 'published')
    .map((mix) => ({
      ...mix,
      title: mix.displayTitle || mix.title,
      excerpt: mix.summary,
      notes: Array.isArray(mix.intro) ? mix.intro.join('\n\n') : '',
      date: mix.publishedAt,
      number: mix.mixNumber,
      image: mix.cover?.imageUrl,
      imageAlt: mix.cover?.alt,
      links: {
        ...(mix.links || {}),
        ...(mix.download?.url ? { [mix.download.label || 'Download mix']: mix.download.url } : {}),
      },
    }));

  const fromDirect = Array.isArray(directMixes) ? directMixes : directMixes?.mixes || [];
  const fromArchive = Array.isArray(archiveIndex?.mixes) ? archiveIndex.mixes : [];
  const combined = [...fromDirect, ...fromArchive, ...importedMixes, ...publishedMixes];
  const deduped = Array.from(new Map(combined.map((mix) => [mix.slug || mix.id || mix.title, mix])).values());

  return normalizeMixes(deduped);
}

function loadNotes() {
  const flexibleNotes = readJsonIfExists(path.join(DATA_DIR, 'notes.json'), null);
  if (flexibleNotes) return normalizeNotes(flexibleNotes);

  const notesIndex = readJsonIfExists(path.join(DATA_DIR, 'notes-index.json'), null);
  const indexedItems = Array.isArray(notesIndex?.items) ? notesIndex.items : [];
  const noteFiles = walkJsonFiles(path.join(DATA_DIR, 'notes'));

  const detailedNotes = noteFiles
    .map((filePath) => readJsonIfExists(filePath, null))
    .filter(Boolean);
  const detailedBySlug = new Map(
    detailedNotes.map((note, index) => {
      const normalized = normalizeNote(note, index);
      return [normalized.slug, normalized];
    })
  );

  const merged = indexedItems.map((item, index) => {
    const normalizedIndexItem = normalizeNote(item, index);
    const detailed = detailedBySlug.get(normalizedIndexItem.slug);
    return detailed ? { ...normalizedIndexItem, ...detailed } : normalizedIndexItem;
  });

  const indexedSlugs = new Set(merged.map((note) => note.slug));
  for (const detailed of detailedBySlug.values()) {
    if (!indexedSlugs.has(detailed.slug)) merged.push(detailed);
  }

  return sortNotes(merged);
}

function loadDrafts() {
  const draftFiles = walkJsonFiles(path.join(DATA_DIR, 'drafts'));
  const drafts = draftFiles
    .map((filePath) => readJsonIfExists(filePath, null))
    .filter(Boolean)
    .filter((draft) => !draft.status || draft.status === 'draft' || draft.status === 'approved');

  return normalizeDrafts(drafts);
}

function attachRelationships(mixes, notes) {
  const mixesBySlug = new Map(mixes.map((mix) => [mix.slug, mix]));

  const notesWithRelations = notes.map((note) => ({
    ...note,
    relatedMixes: note.relatedMixSlugs.map((slug) => mixesBySlug.get(slug)).filter(Boolean),
  }));

  const notesByMixSlug = new Map();
  for (const note of notesWithRelations) {
    for (const slug of note.relatedMixSlugs) {
      const current = notesByMixSlug.get(slug) || [];
      current.push(note);
      notesByMixSlug.set(slug, current);
    }
  }

  const mixesWithRelations = mixes.map((mix, index) => ({
    ...mix,
    relatedNotes: notesByMixSlug.get(mix.slug) || [],
    highlightedTracks: mix.tracklist.filter((track) => track && typeof track === 'object' && track.isFavorite),
    newerMix: index > 0 ? mixes[index - 1] : null,
    olderMix: index < mixes.length - 1 ? mixes[index + 1] : null,
  }));

  return {
    mixes: mixesWithRelations,
    notes: notesWithRelations,
  };
}

function relativePrefix(depth) {
  return depth <= 0 ? './' : '../'.repeat(depth);
}

function navLinks(depth) {
  const base = relativePrefix(depth);
  return [
    { href: `${base}`, label: 'Home', key: 'home' },
    { href: `${base}archive/`, label: 'Archive', key: 'archive' },
    { href: `${base}about/`, label: 'About', key: 'about' },
    { href: `${base}notes/`, label: 'Notes', key: 'notes' },
    { href: `${base}studio/`, label: 'Studio', key: 'studio' },
  ];
}

function renderLayout({ depth = 0, currentNav = '', title, description, eyebrow = 'Monday Music Mix', content }) {
  const assetBase = `${relativePrefix(depth)}assets/`;
  const nav = navLinks(depth)
    .map((item) => {
      const active = item.key === currentNav ? 'is-active' : '';
      return `<a class="site-nav__link ${active}" href="${item.href}">${item.label}</a>`;
    })
    .join('');
  const year = new Date().getFullYear();

  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>${escapeHtml(title)} · Monday Music Mix</title>
    <meta name="description" content="${escapeHtml(description)}">
    <link rel="stylesheet" href="${assetBase}site.css">
    <script src="${assetBase}site.js" defer></script>
  </head>
  <body>
    <div class="page-shell">
      <header class="site-header">
        <div class="site-header__inner">
          <a class="site-brand" href="${relativePrefix(depth)}">
            <span class="site-brand__eyebrow">MMM</span>
            <span class="site-brand__name">Monday Music Mix</span>
          </a>
          <nav class="site-nav" aria-label="Primary">
            ${nav}
          </nav>
        </div>
      </header>
      <main class="site-main">
        ${content}
      </main>
      <footer class="site-footer">
        <div>
          <p class="site-footer__eyebrow">${escapeHtml(eyebrow)}</p>
          <p class="site-footer__copy">Handmade, music-first, and archived without pretending to be larger than life.</p>
        </div>
        <div class="site-footer__meta">© ${year} Monday Music Mix</div>
      </footer>
    </div>
  </body>
</html>`;
}

function renderTagList(tags) {
  if (!tags.length) return '';
  return `<ul class="tag-list">${tags.map((tag) => `<li>${escapeHtml(tag)}</li>`).join('')}</ul>`;
}

function countTopTags(items, limit = 3) {
  const counts = new Map();

  for (const item of items) {
    const tags = Array.isArray(item?.tags) ? item.tags : [];
    for (const tag of tags) {
      const normalized = String(tag || '').trim();
      if (!normalized) continue;
      counts.set(normalized, (counts.get(normalized) || 0) + 1);
    }
  }

  return Array.from(counts.entries())
    .sort((a, b) => {
      if (b[1] !== a[1]) return b[1] - a[1];
      return a[0].localeCompare(b[0]);
    })
    .slice(0, limit)
    .map(([tag]) => tag);
}

function buildSearchBlob(parts) {
  return parts
    .flatMap((part) => (Array.isArray(part) ? part : [part]))
    .map((part) => String(part || '').trim())
    .filter(Boolean)
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function renderDiscoveryControls({
  title,
  description,
  queryLabel,
  queryPlaceholder,
  itemLabelSingular,
  itemLabelPlural,
  totalCount,
  filters,
}) {
  return `<section
      class="discovery-panel"
      data-discovery
      data-item-label-singular="${escapeHtml(itemLabelSingular)}"
      data-item-label-plural="${escapeHtml(itemLabelPlural)}"
      data-total-count="${escapeHtml(String(totalCount))}"
    >
      <div class="discovery-panel__header">
        <div>
          <p class="eyebrow">Discovery</p>
          <h2>${escapeHtml(title)}</h2>
        </div>
        <p class="supporting-copy">${escapeHtml(description)}</p>
      </div>
      <div class="discovery-panel__controls">
        <label class="discovery-search">
          <span class="discovery-search__label">${escapeHtml(queryLabel)}</span>
          <input
            class="discovery-search__input"
            type="search"
            placeholder="${escapeHtml(queryPlaceholder)}"
            autocomplete="off"
            spellcheck="false"
            data-discovery-input
          >
        </label>
        <p class="discovery-panel__summary" data-discovery-summary>
          Showing all ${escapeHtml(String(totalCount))} ${escapeHtml(totalCount === 1 ? itemLabelSingular : itemLabelPlural)}.
        </p>
      </div>
      <div class="discovery-filter-row" aria-label="Filter ${escapeHtml(itemLabelPlural)}">
        ${filters
          .map(
            (filter, index) => `<button
                class="discovery-filter${index === 0 ? ' is-active' : ''}"
                type="button"
                data-discovery-filter="${escapeHtml(filter.value)}"
                aria-pressed="${index === 0 ? 'true' : 'false'}"
              >${escapeHtml(filter.label)}</button>`
          )
          .join('')}
      </div>
    </section>`;
}

function renderRouteList(routes) {
  if (!routes.length) {
    return '<p class="supporting-copy">No routes to suggest yet.</p>';
  }

  return `<div class="related-list">
    ${routes
      .map(
        (route) => `<a class="related-card" href="${escapeHtml(route.href)}">
          <p class="related-card__meta">${escapeHtml(route.kicker || 'Route')}</p>
          <h3>${escapeHtml(route.title)}</h3>
          <p>${escapeHtml(route.description || '')}</p>
        </a>`
      )
      .join('')}
  </div>`;
}

function renderCover(mix, compact = false) {
  if (mix.image) {
    return `<figure class="mix-cover ${compact ? 'mix-cover--compact' : ''}"><img src="${escapeHtml(mix.image)}" alt="${escapeHtml(mix.imageAlt)}"></figure>`;
  }

  return `<div class="mix-cover mix-cover--placeholder ${compact ? 'mix-cover--compact' : ''}">
    <div class="mix-cover__body">
      <span class="mix-cover__kicker">${mix.usesArchivalCoverFallback ? 'Archive mix' : 'No artwork yet'}</span>
      <strong>${escapeHtml(mix.title)}</strong>
      <p>${escapeHtml(
        mix.usesArchivalCoverFallback
          ? 'Legacy Tumblr artwork is preserved as source context, but it is not being presented here as canonical album art.'
          : 'Artwork has not been added for this mix yet.'
      )}</p>
      ${mix.coverCredit ? `<p class="mix-cover__credit">${escapeHtml(mix.coverCredit)}</p>` : ''}
    </div>
  </div>`;
}

function renderMixMiniList(mixes, { basePath = '', emptyMessage = '' } = {}) {
  if (!mixes.length) {
    return emptyMessage ? `<p class="supporting-copy">${escapeHtml(emptyMessage)}</p>` : '';
  }

  return `<div class="related-list">
    ${mixes
      .map(
        (mix) => `<a class="related-card" href="${basePath}${escapeHtml(mix.slug)}/">
          <p class="related-card__meta">${escapeHtml(formatMonthYear(mix.date))}${mix.number !== '' ? ` · Mix ${escapeHtml(mix.number)}` : ''}</p>
          <h3>${escapeHtml(mix.title)}</h3>
          <p>${escapeHtml(mix.excerpt)}</p>
        </a>`
      )
      .join('')}
  </div>`;
}

function renderNoteMiniList(notes, { basePath = '', emptyMessage = '' } = {}) {
  if (!notes.length) {
    return emptyMessage ? `<p class="supporting-copy">${escapeHtml(emptyMessage)}</p>` : '';
  }

  return `<div class="related-list">
    ${notes
      .map(
        (note) => `<a class="related-card" href="${basePath}${escapeHtml(note.slug)}/">
          <p class="related-card__meta">${escapeHtml(note.date ? formatDate(note.date) : 'Undated note')}</p>
          <h3>${escapeHtml(note.title)}</h3>
          <p>${escapeHtml(note.excerpt || 'A note tied to this corner of the archive.')}</p>
        </a>`
      )
      .join('')}
  </div>`;
}

function renderResourceSection(mix) {
  const resourceCards = [];

  if (mix.sourceUrl) {
    resourceCards.push(`
      <article class="resource-card">
        <p class="resource-card__eyebrow">Source</p>
        <h3>Original post</h3>
        <a class="text-link" href="${escapeHtml(mix.sourceUrl)}">Open source</a>
      </article>
    `);
  }

  if (mix.coverCredit) {
    resourceCards.push(`
      <article class="resource-card">
        <p class="resource-card__eyebrow">Artwork</p>
        <h3>Cover credit</h3>
        <p>${escapeHtml(mix.coverCredit)}</p>
      </article>
    `);
  }

  const linkItems = Object.entries(mix.primaryLinks || {}).filter(([, href]) => typeof href === 'string' && href.trim());
  if (linkItems.length) {
    resourceCards.push(`
      <article class="resource-card">
        <p class="resource-card__eyebrow">Archive links</p>
        <h3>Other preserved links</h3>
        <div class="button-row button-row--compact">
          ${linkItems
            .map(([label, href]) => `<a class="button button--secondary" href="${escapeHtml(href)}">${escapeHtml(label.replace(/_/g, ' '))}</a>`)
            .join('')}
        </div>
      </article>
    `);
  }

  const suppressedLinks = Object.entries(mix.legacyLinks || {}).filter(([, href]) => typeof href === 'string' && href.trim());
  if (suppressedLinks.length) {
    resourceCards.push(`
      <article class="resource-card">
        <p class="resource-card__eyebrow">Archive cleanup</p>
        <h3>Legacy download removed</h3>
        <p>Dead Mega links stay in the JSON for provenance but are intentionally hidden from the page.</p>
      </article>
    `);
  }

  if (!resourceCards.length) return '';

  return `<section class="section-block section-block--compact">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Source</p>
          <h2>Provenance</h2>
        </div>
      </div>
      <div class="resource-grid resource-grid--compact">${resourceCards.join('')}</div>
    </section>`;
}

function renderListeningSection(mix) {
  const playlistEmbed = resolvePlaylistEmbed(mix);
  const listeningLinks = getCompactListeningLinks(mix);

  if (!playlistEmbed && !listeningLinks.length) return '';

  return `<section class="section-block section-block--compact">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Listening</p>
          <h2>${playlistEmbed ? 'Playlist' : 'Links'}</h2>
        </div>
      </div>
      ${playlistEmbed
        ? `<div class="embed-stack">
            <article class="embed-card">
              <div class="embed-card__frame">
                <iframe
                  src="${escapeHtml(playlistEmbed.url)}"
                  title="${escapeHtml(playlistEmbed.title || `YouTube playlist for ${mix.title}`)}"
                  loading="lazy"
                  allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
                  referrerpolicy="strict-origin-when-cross-origin"
                ></iframe>
              </div>
            </article>
          </div>`
        : ''}
      ${listeningLinks.length
        ? `<div class="button-row button-row--compact">
            ${listeningLinks
              .map((provider) => `<a class="button button--secondary" href="${escapeHtml(provider.url)}">${escapeHtml(provider.label || `Open on ${provider.provider}`)}</a>`)
              .join('')}
          </div>`
        : ''}
    </section>`;
}

function renderHomePage({ mixes, notes, site }) {
  const featuredSlug = site.featuredMixSlug || site.featured_mix_slug;
  const featured = featuredSlug
    ? mixes.find((mix) => mix.slug === featuredSlug) || mixes[0]
    : mixes[0];
  const recent = featured ? mixes.filter((mix) => mix.slug !== featured.slug).slice(0, 4) : mixes.slice(0, 4);
  const recentNotes = notes.slice(0, 2);
  const featuredNotes = featured?.relatedNotes?.slice(0, 2) || [];
  const intro = site.homeIntro || site.homepage_intro || 'A personal archive for mixes built slowly, sequenced by hand, and kept with just enough context to matter later.';
  const description = featured ? featured.excerpt : 'A darker editorial archive for handmade mixes and notes.';

  const featureBlock = featured
    ? `<section class="hero-grid">
        <div>
          <p class="eyebrow">Current mix</p>
          <h1>${escapeHtml(featured.title)}</h1>
          <p class="hero-copy">${escapeHtml(featured.excerpt)}</p>
          <div class="meta-row">
            <span>${escapeHtml(formatDate(featured.date))}</span>
            ${featured.runtime ? `<span>${escapeHtml(featured.runtime)}</span>` : ''}
            ${featured.number !== '' ? `<span>Mix ${escapeHtml(featured.number)}</span>` : ''}
            ${featured.relatedNotes.length ? `<span>${escapeHtml(String(featured.relatedNotes.length))} related note${featured.relatedNotes.length === 1 ? '' : 's'}</span>` : ''}
          </div>
          ${renderTagList(featured.tags)}
          <div class="button-row">
            <a class="button" href="mixes/${escapeHtml(featured.slug)}/">Open mix</a>
            <a class="button button--secondary" href="archive/">Browse archive</a>
          </div>
        </div>
        ${renderCover(featured)}
      </section>`
    : `<section class="hero-grid hero-grid--empty">
        <div>
          <p class="eyebrow">Monday Music Mix</p>
          <h1>Archive in progress.</h1>
          <p class="hero-copy">${escapeHtml(intro)}</p>
          <div class="button-row">
            <a class="button" href="archive/">Visit archive</a>
            <a class="button button--secondary" href="about/">About the project</a>
          </div>
        </div>
        <div class="callout-panel">
          <p class="callout-panel__eyebrow">No mixes published yet</p>
          <p>That is intentional. The site is ready for real entries as soon as the data lands under data/.</p>
        </div>
      </section>`;

  const recentBlock = recent.length
    ? `<section class="section-block">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Recent mixes</p>
            <h2>Small archive, real entries.</h2>
          </div>
          <a class="text-link" href="archive/">See all</a>
        </div>
        <div class="list-stack">
          ${recent
            .map(
              (mix) => `<a class="archive-row" href="mixes/${escapeHtml(mix.slug)}/">
                <div>
                  <p class="archive-row__meta">${escapeHtml(formatMonthYear(mix.date))}${mix.number !== '' ? ` · Mix ${escapeHtml(mix.number)}` : ''}</p>
                  <h3>${escapeHtml(mix.title)}</h3>
                  <p class="archive-row__submeta">${mix.highlightedTracks.length ? `${escapeHtml(String(mix.highlightedTracks.length))} highlighted track${mix.highlightedTracks.length === 1 ? '' : 's'}` : 'No highlighted tracks marked'}${mix.relatedNotes.length ? ` · ${escapeHtml(String(mix.relatedNotes.length))} related note${mix.relatedNotes.length === 1 ? '' : 's'}` : ''}</p>
                </div>
                <p>${escapeHtml(mix.excerpt)}</p>
              </a>`
            )
            .join('')}
        </div>
      </section>`
    : '';

  const notesBlock = recentNotes.length
    ? `<section class="section-block section-block--split">
        <div>
          <p class="eyebrow">From the notebook</p>
          <h2>Notes that explain why a mix stayed around.</h2>
          <p class="supporting-copy">Short editorial fragments now have their own pages and stay wired back into the archive.</p>
          <div class="button-row">
            <a class="button button--secondary" href="notes/">Browse notes</a>
          </div>
        </div>
        <div>
          ${renderNoteMiniList(recentNotes, { basePath: 'notes/' })}
        </div>
      </section>`
    : '';

  const featuredRelationBlock = featured && featuredNotes.length
    ? `<section class="section-block section-block--split">
        <div>
          <p class="eyebrow">Connected reading</p>
          <h2>Notes related to ${escapeHtml(featured.title)}</h2>
          <p class="supporting-copy">The homepage now exposes the writing closest to the featured mix instead of leaving it stranded on a separate index.</p>
        </div>
        <div>
          ${renderNoteMiniList(featuredNotes, { basePath: 'notes/' })}
        </div>
      </section>`
    : '';

  const valuesBlock = `<section class="section-block section-block--split">
      <div>
        <p class="eyebrow">Why it exists</p>
        <h2>Less brand world, more listening habit.</h2>
      </div>
      <div class="prose">
        <p>${escapeHtml(intro)}</p>
        <p>${escapeHtml(site.homeSecondary || 'The visual language stays dark, editorial, and grounded: late-night listening, track sequencing, and the useful residue that remains after repeat plays.')}</p>
        <p><a class="text-link" href="studio/">Open the local studio dashboard</a></p>
      </div>
    </section>`;
  return renderLayout({
    depth: 0,
    currentNav: 'home',
    title: 'Home',
    description,
    content: `${featureBlock}${recentBlock}${notesBlock}${featuredRelationBlock}${valuesBlock}`,
  });
}

function renderArchivePage({ mixes }) {
  const topTags = countTopTags(mixes);
  const discoveryFilters = [
    { label: 'All mixes', value: 'all' },
    { label: 'Related notes', value: 'state:has-related' },
    { label: 'Highlighted tracks', value: 'state:has-highlights' },
    ...topTags.map((tag) => ({ label: `Tag: ${tag}`, value: `tag:${tag}` })),
  ];
  const body = mixes.length
    ? `<section class="page-intro">
        <p class="eyebrow">Archive</p>
        <h1>Published mixes</h1>
        <p class="page-intro__copy">A chronological run of finished mixes, each with whatever notes, artwork, and track sequencing survived the urge to over-explain.</p>
      </section>
      ${renderDiscoveryControls({
        title: 'Search archive',
        description: 'Filter by title, tags, dates, highlighted tracks, or whether a mix already has notes attached.',
        queryLabel: 'Search archive',
        queryPlaceholder: 'Title, tag, date, note count...',
        itemLabelSingular: 'mix',
        itemLabelPlural: 'mixes',
        totalCount: mixes.length,
        filters: discoveryFilters,
      })}
      <section class="list-stack list-stack--archive">
        ${mixes
          .map(
            (mix) => `<a
              class="archive-row archive-row--full"
              href="../mixes/${escapeHtml(mix.slug)}/"
              data-discovery-item
              data-discovery-tags="${escapeHtml(mix.tags.join('|'))}"
              data-discovery-states="${escapeHtml(
                [mix.relatedNotes.length ? 'has-related' : '', mix.highlightedTracks.length ? 'has-highlights' : '']
                  .filter(Boolean)
                  .join('|')
              )}"
              data-discovery-search="${escapeHtml(
                buildSearchBlob([
                  mix.title,
                  mix.excerpt,
                  mix.tags,
                  formatDate(mix.date),
                  formatMonthYear(mix.date),
                  mix.number !== '' ? `mix ${mix.number}` : '',
                  mix.highlightedTracks.length ? `${mix.highlightedTracks.length} highlighted tracks` : '',
                  mix.relatedNotes.length ? `${mix.relatedNotes.length} related notes` : 'no related notes',
                ])
              )}"
            >
              <div>
                <p class="archive-row__meta">${escapeHtml(formatDate(mix.date))}${mix.number !== '' ? ` · Mix ${escapeHtml(mix.number)}` : ''}</p>
                <h2>${escapeHtml(mix.title)}</h2>
                <p class="archive-row__submeta">${mix.highlightedTracks.length ? `${escapeHtml(String(mix.highlightedTracks.length))} highlighted track${mix.highlightedTracks.length === 1 ? '' : 's'}` : 'No highlighted tracks marked'}${mix.relatedNotes.length ? ` · ${escapeHtml(String(mix.relatedNotes.length))} related note${mix.relatedNotes.length === 1 ? '' : 's'}` : ''}</p>
                ${renderTagList(mix.tags)}
              </div>
              <p>${escapeHtml(mix.excerpt)}</p>
            </a>`
          )
          .join('')}
      </section>
      <section class="empty-state" hidden data-discovery-empty>
        <div class="callout-panel">
          <p class="callout-panel__eyebrow">No matches</p>
          <p>Try a different tag, clear the search, or return to all mixes.</p>
        </div>
      </section>`
    : `<section class="page-intro">
        <p class="eyebrow">Archive</p>
        <h1>Archive in progress</h1>
        <p class="page-intro__copy">No published mixes yet. The build is wired to read data from data/mixes.json as soon as entries exist.</p>
      </section>
      <section class="empty-state">
        <div class="callout-panel">
          <p class="callout-panel__eyebrow">Holding page</p>
          <p>Better a small real archive than an invented back catalog. When the first mix appears in the data, it will land here automatically.</p>
        </div>
      </section>`;

  return renderLayout({
    depth: 1,
    currentNav: 'archive',
    title: 'Archive',
    description: 'Published Monday Music Mix entries.',
    content: body,
  });
}

function renderMixPage({ mix }) {
  const trackSection = mix.tracklist.length
    ? `<section class="section-block section-block--primary">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Tracklist</p>
            <h2>Full sequence</h2>
            <p class="supporting-copy">${escapeHtml(String(mix.tracklist.length))} tracks${mix.highlightedTracks.length ? ` · ${escapeHtml(String(mix.highlightedTracks.length))} favorites marked in source` : ''}</p>
          </div>
        </div>
        <ol class="tracklist">
          ${mix.tracklist
            .map((track, index) => {
              const normalized = typeof track === 'string' ? { title: track } : track || {};
              const artist = normalized.artist ? ` — ${escapeHtml(normalized.artist)}` : '';
              const title = normalized.title || normalized.displayText || `Track ${index + 1}`;
              const annotation = normalized.note ? `<p>${escapeHtml(normalized.note)}</p>` : '';
              return `<li>
                <div>
                  <strong>${String(normalized.position || index + 1).padStart(2, '0')}</strong>
                  <span>${escapeHtml(title)}${artist}</span>
                  ${normalized.isFavorite ? '<em class="track-favorite">Favorite</em>' : ''}
                </div>
                ${annotation}
              </li>`;
            })
            .join('')}
        </ol>
      </section>`
    : `<section class="section-block">
        <div class="callout-panel">
          <p class="callout-panel__eyebrow">Tracklist pending</p>
          <p>This page is ready for a tracklist as soon as tracks are added to the source data.</p>
        </div>
      </section>`;

  const distinctMixNotes = getDistinctMixNotes(mix);
  const notesSection = distinctMixNotes.length
    ? `<section class="section-block section-block--split">
        <div>
          <p class="eyebrow">Context</p>
          <h2>Archive notes</h2>
        </div>
        <div class="prose">${paragraphize(distinctMixNotes.join('\n\n'))}</div>
      </section>`
    : '';

  const relatedNotesSection = `<section class="section-block section-block--split">
      <div>
        <p class="eyebrow">Related notes</p>
        <h2>Writing tied to this mix</h2>
      </div>
      <div>
        ${renderNoteMiniList(mix.relatedNotes, {
          basePath: '../../notes/',
          emptyMessage: 'No notes point back to this mix yet.',
        })}
      </div>
    </section>`;

  const adjacentMixes = [mix.olderMix, mix.newerMix].filter(Boolean);
  const navigationSection = adjacentMixes.length
    ? `<section class="section-block section-block--split">
        <div>
          <p class="eyebrow">Archive</p>
          <h2>More mixes</h2>
        </div>
        <div class="adjacent-grid">
          ${mix.olderMix
            ? `<a class="adjacent-card" href="../${escapeHtml(mix.olderMix.slug)}/">
                <p class="adjacent-card__eyebrow">Previous mix</p>
                <h3>${escapeHtml(mix.olderMix.title)}</h3>
                <p>${escapeHtml(formatDate(mix.olderMix.date))}</p>
              </a>`
            : ''}
          ${mix.newerMix
            ? `<a class="adjacent-card" href="../${escapeHtml(mix.newerMix.slug)}/">
                <p class="adjacent-card__eyebrow">Next mix</p>
                <h3>${escapeHtml(mix.newerMix.title)}</h3>
                <p>${escapeHtml(formatDate(mix.newerMix.date))}</p>
              </a>`
            : ''}
        </div>
      </section>`
    : '';

  return renderLayout({
    depth: 2,
    currentNav: 'archive',
    title: mix.title,
    description: stripHtml(mix.excerpt),
    eyebrow: mix.title,
    content: `<section class="mix-hero">
        <div>
          <p class="eyebrow">Mix detail</p>
          <h1>${escapeHtml(mix.title)}</h1>
          <p class="hero-copy">${escapeHtml(mix.excerpt)}</p>
          <div class="meta-row">
            <span>${escapeHtml(formatDate(mix.date))}</span>
            ${mix.runtime ? `<span>${escapeHtml(mix.runtime)}</span>` : ''}
            ${mix.number !== '' ? `<span>Mix ${escapeHtml(mix.number)}</span>` : ''}
            ${mix.highlightedTracks.length ? `<span>${escapeHtml(String(mix.highlightedTracks.length))} highlighted</span>` : ''}
            ${mix.relatedNotes.length ? `<span>${escapeHtml(String(mix.relatedNotes.length))} related note${mix.relatedNotes.length === 1 ? '' : 's'}</span>` : ''}
          </div>
          ${renderTagList(mix.tags)}
          <div class="button-row">
            <a class="button button--secondary" href="../../archive/">Back to archive</a>
          </div>
        </div>
        ${renderCover(mix)}
      </section>
      ${trackSection}
      ${renderListeningSection(mix)}
      ${notesSection}
      ${relatedNotesSection}
      ${navigationSection}
      ${renderResourceSection(mix)}`,
  });
}

function renderStudioPage({ site, drafts, mixes, notes }) {
  const featuredSlug = site.featuredMixSlug || site.featured_mix_slug;
  const featuredMix = featuredSlug ? mixes.find((mix) => mix.slug === featuredSlug) || null : null;
  const latestDraft = drafts[0] || null;
  const latestPublished = mixes[0] || null;
  const latestNote = notes[0] || null;
  const latestPublishedWithoutNote = mixes.find((mix) => mix.relatedNotes.length === 0) || null;
  const publishedWithNotes = mixes.filter((mix) => mix.relatedNotes.length > 0).length;
  const notesWithRelations = notes.filter((note) => note.relatedMixes.length > 0).length;
  const approvedDrafts = drafts.filter((draft) => draft.status === 'approved').length;
  const draftDrafts = drafts.filter((draft) => draft.status === 'draft').length;
  const nextActions = [];
  const validationSignals = [];

  if (featuredSlug) {
    validationSignals.push(featuredMix ? 'Featured mix slug resolves to a published mix.' : 'Featured mix slug does not resolve to a published mix yet.');
  } else {
    validationSignals.push('No featured mix slug is set yet.');
  }

  validationSignals.push(
    latestDraft
      ? `Latest draft is currently marked ${latestDraft.status}.`
      : 'There is no local draft mix file right now.'
  );

  validationSignals.push(
    mixes.length
      ? `${publishedWithNotes} of ${mixes.length} published mix${mixes.length === 1 ? '' : 'es'} already have note context attached.`
      : 'There are no published mixes to validate against note coverage yet.'
  );

  const validationHeadline = !featuredSlug || featuredMix
    ? latestDraft?.status === 'approved'
      ? 'Ready for validate/build pass'
      : 'Editorial review still pending'
    : 'Needs data attention';
  const validationCopy = !featuredSlug || featuredMix
    ? latestDraft?.status === 'approved'
      ? 'The current data shape looks coherent from the site build, but schema validation still needs a local run before publishing.'
      : 'The site can render the current state cleanly, but the latest draft still needs review before it feels publishable.'
    : 'The dashboard found a featured mix reference that does not point at a published entry, so validation should wait until that is corrected.';

  if (latestDraft) {
    nextActions.push(
      latestDraft.status === 'approved'
        ? `Run validation and build against ${latestDraft.title}, then publish when the page and metadata still look intentional.`
        : `Review ${latestDraft.title} and promote it from ${latestDraft.status} to approved once the sequencing feels done.`
    );
  } else {
    nextActions.push('Generate the next weekly draft so the studio reflects the upcoming mix instead of staying empty.');
  }

  if (!featuredMix && mixes[0]) {
    nextActions.push('Update data/site.json so a published mix is featured on the homepage instead of falling back automatically.');
  }

  if (latestPublishedWithoutNote) {
    nextActions.push(`Add a note or mix-context paragraph for ${latestPublishedWithoutNote.title} so the archive coverage does not stall at the latest listening work.`);
  }

  if (notes.length < mixes.length && !latestPublishedWithoutNote) {
    nextActions.push('Add another note to capture why a recent published mix still matters to the archive.');
  }

  if (!nextActions.length) {
    nextActions.push('Validate, build, and publish when the next approved mix is ready.');
  }

  const statCards = [
    {
      label: 'Draft mixes',
      value: String(drafts.length),
      detail: latestDraft ? `Latest: ${latestDraft.title}` : 'No draft mix files found',
    },
    {
      label: 'Published mixes',
      value: String(mixes.length),
      detail: mixes[0] ? `Latest published: ${mixes[0].title}` : 'No published archive yet',
    },
    {
      label: 'Notes',
      value: String(notes.length),
      detail: notes[0] ? `Latest note: ${notes[0].title}` : 'No note files found',
    },
    {
      label: 'Featured mix',
      value: featuredMix?.displayTitle || featuredMix?.title || 'Unset',
      detail: featuredMix ? formatDate(featuredMix.date) : 'Check data/site.json',
    },
    {
      label: 'Validation posture',
      value: validationHeadline,
      detail: 'Schema validation is still a separate local command.',
    },
  ];
  const healthCards = [
    {
      eyebrow: 'Draft queue',
      title: latestDraft?.title || 'No draft available',
      body: latestDraft
        ? `${draftDrafts} draft${draftDrafts === 1 ? '' : 's'} waiting on review, ${approvedDrafts} approved.`
        : 'Generate the next weekly draft to give the studio a clear editing target.',
      detail: latestDraft ? `${formatDate(latestDraft.date)} · ${latestDraft.trackCount} tracks · ${latestDraft.status}` : '',
    },
    {
      eyebrow: 'Archive coverage',
      title: `${publishedWithNotes}/${mixes.length || 0} published mixes carry note context`,
      body: mixes.length
        ? `${notesWithRelations} of ${notes.length} note${notes.length === 1 ? '' : 's'} already point back into the archive.`
        : 'Coverage will appear here once published mixes land in the archive.',
      detail: latestPublishedWithoutNote ? `Latest gap: ${latestPublishedWithoutNote.title}` : 'Recent published mixes all have at least one related note.',
    },
    {
      eyebrow: 'Validation posture',
      title: validationHeadline,
      body: validationCopy,
      detail: validationSignals.join(' '),
    },
  ];
  const recentRoutes = [
    latestPublished
      ? {
          href: `../mixes/${latestPublished.slug}/`,
          kicker: 'Latest mix',
          title: latestPublished.title,
          description: `${formatDate(latestPublished.date)} · ${latestPublished.relatedNotes.length} related note${latestPublished.relatedNotes.length === 1 ? '' : 's'}`,
        }
      : null,
    featuredMix
      ? {
          href: `../mixes/${featuredMix.slug}/`,
          kicker: 'Featured',
          title: featuredMix.title,
          description: 'Current homepage lead story.',
        }
      : null,
    latestNote
      ? {
          href: `../notes/${latestNote.slug}/`,
          kicker: 'Latest note',
          title: latestNote.title,
          description: latestNote.excerpt || 'Newest archive note.',
        }
      : null,
    {
      href: '../archive/',
      kicker: 'Overview',
      title: 'Archive',
      description: 'Check the full published run and scan for thin metadata.',
    },
    {
      href: '../notes/',
      kicker: 'Overview',
      title: 'Notes',
      description: 'Review what writing is already attached to the archive.',
    },
  ].filter(Boolean);
  let content = `<section class="page-intro page-intro--wide">
      <div>
        <p class="eyebrow">Studio</p>
        <h1>Local editorial state</h1>
      </div>
      <div>
        <p class="page-intro__copy page-intro__copy--large">A static dashboard generated from the JSON already in this repo: drafts, published mixes, notes, and the next few operator moves.</p>
      </div>
    </section>`;
  content += `<section class="stats-grid">
      ${statCards
        .map((card) => `<article class="stat-card">
          <p class="stat-card__label">${escapeHtml(card.label)}</p>
          <h2>${escapeHtml(card.value)}</h2>
          <p>${escapeHtml(card.detail)}</p>
        </article>`)
        .join('')}
    </section>`;
  content += `<section class="section-block studio-grid">
      ${healthCards
        .map(
          (card) => `<article class="resource-card">
            <p class="resource-card__eyebrow">${escapeHtml(card.eyebrow)}</p>
            <h3>${escapeHtml(card.title)}</h3>
            <p>${escapeHtml(card.body)}</p>
            ${card.detail ? `<p class="supporting-copy">${escapeHtml(card.detail)}</p>` : ''}
          </article>`
        )
        .join('')}
    </section>`;
  content += `<section class="section-block section-block--split">
      <div>
        <p class="eyebrow">Recent routes</p>
        <h2>What to open next</h2>
      </div>
      <div>
        ${renderRouteList(recentRoutes)}
      </div>
    </section>`;
  content += `<section class="section-block section-block--split">
      <div>
        <p class="eyebrow">Operator commands</p>
        <h2>Local commands worth keeping close</h2>
      </div>
      <div class="command-list">
        <code>python3 scripts/validate_content.py</code>
        <code>python3 scripts/generate_weekly_draft.py --mode auto</code>
        <code>python3 scripts/publish_mix.py &lt;slug-or-path&gt; --feature</code>
        <code>npm run build</code>
      </div>
    </section>`;
  content += `<section class="section-block section-block--split">
      <div>
        <p class="eyebrow">Recommended next actions</p>
        <h2>What the current data suggests</h2>
      </div>
      <div class="action-list">
        ${nextActions.map((action) => `<p>${escapeHtml(action)}</p>`).join('')}
      </div>
    </section>`;

  return renderLayout({
    depth: 1,
    currentNav: 'studio',
    title: 'Studio',
    description: 'Local editorial dashboard for Monday Music Mix.',
    content,
  });
}

function renderAboutPage({ site, about }) {
  const headline = about.headline || site.tagline || 'A personal archive for mixes built slowly and kept with care.';
  const sections = Array.isArray(about.sections) ? about.sections : [];
  const body = sections.length
    ? sections
        .map(
          (section) => `<section class="section-block section-block--split">
            <div>
              <p class="eyebrow">${escapeHtml(section.label || 'About')}</p>
              <h2>${escapeHtml(section.title || '')}</h2>
            </div>
            <div class="prose">${paragraphize(section.body || section.text || '')}</div>
          </section>`
        )
        .join('')
    : `<section class="section-block section-block--split">
        <div>
          <p class="eyebrow">Why build it this way</p>
          <h2>Grounded, personal, and music-first.</h2>
        </div>
        <div class="prose">
          <p>Monday Music Mix is meant to feel like a real archive instead of a manufactured mythology. The point is sequencing, listening, and keeping the amount of context that still matters later.</p>
          <p>The site favors restraint: dark surfaces, roomy typography, and pages that can hold both finished mixes and partial notes without pretending everything is already complete.</p>
        </div>
      </section>
      <section class="section-block section-block--split">
        <div>
          <p class="eyebrow">What will live here</p>
          <h2>Mixes, notes, and useful residue.</h2>
        </div>
        <div class="prose">
          <p>Published mixes, tracklists, artwork when it exists, and notebook fragments when they earn their place. No runtime dependency on external prototypes, but the visual spirit stays editorial and nocturnal.</p>
        </div>
      </section>`;

  return renderLayout({
    depth: 1,
    currentNav: 'about',
    title: 'About',
    description: stripHtml(headline),
    content: `<section class="page-intro page-intro--wide">
        <div>
          <p class="eyebrow">About</p>
          <h1>${escapeHtml(about.title || 'About Monday Music Mix')}</h1>
        </div>
        <div>
          <p class="page-intro__copy page-intro__copy--large">${escapeHtml(headline)}</p>
        </div>
      </section>
      ${body}`,
  });
}

function renderNotesPage({ notes }) {
  const hasNotes = notes.length > 0;
  const topTags = countTopTags(notes);
  const discoveryFilters = [
    { label: 'All notes', value: 'all' },
    { label: 'Linked mixes', value: 'state:has-related' },
    ...topTags.map((tag) => ({ label: `Tag: ${tag}`, value: `tag:${tag}` })),
  ];
  const body = hasNotes
    ? `<section class="page-intro">
        <p class="eyebrow">Notes</p>
        <h1>Notebook fragments</h1>
        <p class="page-intro__copy">Small observations around sequencing, atmosphere, and the songs that took time to reveal themselves.</p>
      </section>
      ${renderDiscoveryControls({
        title: 'Search notes',
        description: 'Filter by note title, tags, dates, or whether a note already connects back to published mixes.',
        queryLabel: 'Search notes',
        queryPlaceholder: 'Title, tag, date, related mix...',
        itemLabelSingular: 'note',
        itemLabelPlural: 'notes',
        totalCount: notes.length,
        filters: discoveryFilters,
      })}
      <section class="notes-grid">
        ${notes
          .map(
            (note) => `<article
              class="note-card"
              data-discovery-item
              data-discovery-tags="${escapeHtml(note.tags.join('|'))}"
              data-discovery-states="${escapeHtml(note.relatedMixes.length ? 'has-related' : '')}"
              data-discovery-search="${escapeHtml(
                buildSearchBlob([
                  note.title,
                  note.excerpt,
                  note.body,
                  note.tags,
                  formatDate(note.date),
                  note.relatedMixes.map((mix) => mix.title),
                  note.relatedMixes.length ? `${note.relatedMixes.length} related mixes` : 'standalone note',
                ])
              )}"
            >
              <p class="note-card__meta">${escapeHtml(note.date ? formatDate(note.date) : 'Undated note')}</p>
              <h2>${escapeHtml(note.title)}</h2>
              <p>${escapeHtml(note.excerpt || stripHtml(note.body).slice(0, 180) || 'A short note waiting for more context.')}</p>
              ${note.tags.length ? renderTagList(note.tags) : ''}
              ${note.relatedMixes.length
                ? `<p class="note-card__link">Related mixes: ${note.relatedMixes
                    .map((mix) => `<a href="../mixes/${escapeHtml(mix.slug)}/">${escapeHtml(mix.title)}</a>`)
                    .join(', ')}</p>`
                : ''}
              <p class="note-card__link"><a href="./${escapeHtml(note.slug)}/">Read note</a></p>
            </article>`
          )
          .join('')}
      </section>
      <section class="empty-state" hidden data-discovery-empty>
        <div class="callout-panel">
          <p class="callout-panel__eyebrow">No matches</p>
          <p>Try a different tag, clear the search, or return to all notes.</p>
        </div>
      </section>`
    : `<section class="page-intro">
        <p class="eyebrow">Notes</p>
        <h1>Holding page for future notes</h1>
        <p class="page-intro__copy">This route is live now and ready to turn into an index once note data exists. Until then, it stays honest about being a placeholder.</p>
      </section>
      <section class="section-block section-block--split">
        <div>
          <p class="eyebrow">Current state</p>
          <h2>Useful residue comes later.</h2>
        </div>
        <div class="prose">
          <p>No notes data was found, so this page acts as a clean holding page. Add data/notes-index.json plus note files under data/notes/, or provide a flexible data/notes.json, and the page will render them automatically.</p>
          <p>Expected fields are flexible: title, date, excerpt, body, tags, and optional related mix slugs.</p>
        </div>
      </section>`;

  return renderLayout({
    depth: 1,
    currentNav: 'notes',
    title: 'Notes',
    description: 'Notebook fragments and future writing around the mixes.',
    content: body,
  });
}

function renderNotePage({ note, allNotes }) {
  const currentIndex = allNotes.findIndex((candidate) => candidate.slug === note.slug);
  const previousNote = currentIndex >= 0 && currentIndex < allNotes.length - 1 ? allNotes[currentIndex + 1] : null;
  const nextNote = currentIndex > 0 ? allNotes[currentIndex - 1] : null;
  const adjacentNotes = [previousNote, nextNote].filter(Boolean);

  return renderLayout({
    depth: 2,
    currentNav: 'notes',
    title: note.title,
    description: stripHtml(note.excerpt || note.body),
    eyebrow: note.title,
    content: `<section class="page-intro page-intro--wide">
        <div>
          <p class="eyebrow">Note detail</p>
          <h1>${escapeHtml(note.title)}</h1>
          <div class="meta-row">
            <span>${escapeHtml(note.date ? formatDate(note.date) : 'Undated note')}</span>
            ${note.relatedMixes.length ? `<span>${escapeHtml(String(note.relatedMixes.length))} related mix${note.relatedMixes.length === 1 ? '' : 'es'}</span>` : ''}
          </div>
          ${renderTagList(note.tags)}
        </div>
        <div>
          <p class="page-intro__copy page-intro__copy--large">${escapeHtml(note.excerpt || 'A short note from the archive notebook.')}</p>
          <div class="button-row">
            <a class="button button--secondary" href="../../notes/">Back to notes</a>
          </div>
        </div>
      </section>
      <section class="section-block section-block--split">
        <div>
          <p class="eyebrow">Body</p>
          <h2>Kept in plain text on purpose</h2>
        </div>
        <div class="prose">${paragraphize(note.body)}</div>
      </section>
      <section class="section-block section-block--split">
        <div>
          <p class="eyebrow">Related mixes</p>
          <h2>Where this note attaches to the archive</h2>
        </div>
        <div>
          ${renderMixMiniList(note.relatedMixes, {
            basePath: '../../mixes/',
            emptyMessage: 'This note is currently standalone.',
          })}
        </div>
      </section>
      ${adjacentNotes.length
        ? `<section class="section-block section-block--split">
            <div>
              <p class="eyebrow">Continue reading</p>
              <h2>Prev and next notes</h2>
            </div>
            <div class="adjacent-grid">
              ${previousNote
                ? `<a class="adjacent-card" href="../${escapeHtml(previousNote.slug)}/">
                    <p class="adjacent-card__eyebrow">Previous note</p>
                    <h3>${escapeHtml(previousNote.title)}</h3>
                    <p>${escapeHtml(previousNote.date ? formatDate(previousNote.date) : 'Undated note')}</p>
                  </a>`
                : ''}
              ${nextNote
                ? `<a class="adjacent-card" href="../${escapeHtml(nextNote.slug)}/">
                    <p class="adjacent-card__eyebrow">Next note</p>
                    <h3>${escapeHtml(nextNote.title)}</h3>
                    <p>${escapeHtml(nextNote.date ? formatDate(nextNote.date) : 'Undated note')}</p>
                  </a>`
                : ''}
            </div>
          </section>`
        : ''}`,
  });
}

function writePage(relativePath, html) {
  const destination = path.join(DIST, relativePath);
  ensureDir(path.dirname(destination));
  fs.writeFileSync(destination, html);
}

function build() {
  resetDir(DIST);

  const siteSource = readJsonIfExists(path.join(DATA_DIR, 'site.json'), {});
  const about = readJsonIfExists(path.join(DATA_DIR, 'about.json'), {});
  const site = {
    ...siteSource,
    title: siteSource.title || siteSource.site_title || 'Monday Music Mix',
    homeIntro: siteSource.homeIntro || siteSource.homepage_intro || '',
  };
  const relationshipGraph = attachRelationships(loadMixes(), loadNotes());
  const mixes = relationshipGraph.mixes;
  const notes = relationshipGraph.notes;
  const drafts = loadDrafts();

  copyDir(STATIC_DIR, path.join(DIST, 'assets'));

  writePage('index.html', renderHomePage({ mixes, notes, site }));
  writePage(path.join('archive', 'index.html'), renderArchivePage({ mixes }));
  writePage(path.join('about', 'index.html'), renderAboutPage({ site, about }));
  writePage(path.join('notes', 'index.html'), renderNotesPage({ notes }));
  writePage(path.join('studio', 'index.html'), renderStudioPage({ site, drafts, mixes, notes }));

  for (const mix of mixes) {
    writePage(path.join('mixes', mix.slug, 'index.html'), renderMixPage({ mix }));
  }

  for (const note of notes) {
    writePage(path.join('notes', note.slug, 'index.html'), renderNotePage({ note, allNotes: notes }));
  }

  fs.writeFileSync(path.join(DIST, '.nojekyll'), '');

  console.log(`Built ${mixes.length} mix page(s) and ${notes.length} note page(s) into ${path.relative(ROOT, DIST)}`);
}

build();
