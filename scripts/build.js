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
    error.message = `Could not parse ${path.relative(ROOT, filePath)}: ${error.message}`;
    throw error;
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

function normalizeParagraphs(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item || '').trim()).filter(Boolean);
  }

  const raw = String(value || '').trim();
  return raw ? [raw] : [];
}

function renderParagraphs(value) {
  return normalizeParagraphs(value).map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`).join('');
}

function formatDate(value) {
  if (!value) return 'Date forthcoming';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);

  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'UTC',
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

function formatUtcDate(value) {
  if (!value) return 'Date forthcoming';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);

  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'UTC',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(date);
}

function formatInlineList(items) {
  const values = items.map((item) => String(item || '').trim()).filter(Boolean);
  if (!values.length) return '';
  if (values.length === 1) return values[0];
  if (values.length === 2) return `${values[0]} and ${values[1]}`;
  return `${values.slice(0, -1).join(', ')}, and ${values.at(-1)}`;
}

function humanizeToken(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  if (/^[a-z]{2,5}$/i.test(raw)) return raw.toUpperCase();

  return raw
    .replace(/[_-]+/g, ' ')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
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

const LISTENING_PROVIDER_CATALOG = readJsonIfExists(path.join(DATA_DIR, 'listening-provider-catalog.json'), {
  schemaVersion: '1.0',
  providers: {},
});
const SUPPORTED_LISTENING_KINDS = new Set(['listen', 'playlist', 'album', 'track', 'set', 'embed']);
const PROVIDER_CONTAINER_KEYS = new Set(['providers', 'links', 'providerlinks', 'streaming', 'entries', 'items', 'sources']);
const EMBED_CONTAINER_KEYS = new Set(['embeds', 'embed', 'players', 'iframes']);
const LISTENING_META_KEYS = new Set(['url', 'href', 'src', 'provider', 'label', 'title', 'kind', 'note', 'summary', 'intro', 'description']);

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
  const provider = LISTENING_PROVIDER_CATALOG.providers?.[normalized];
  if (provider?.label) return String(provider.label).trim();

  return raw
    .replace(/[_-]+/g, ' ')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function inferProviderFromUrl(url) {
  const { host } = getUrlParts(url);
  if (!host) return 'Listening link';

  for (const [key, provider] of Object.entries(LISTENING_PROVIDER_CATALOG.providers || {})) {
    if (hostMatchesProvider(host, provider)) {
      return String(provider.label || providerLabelFromKey(key)).trim() || 'Listening link';
    }
  }

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

function getUrlParts(url) {
  try {
    const parsed = new URL(String(url || '').trim());
    return {
      host: parsed.hostname.toLowerCase(),
      pathname: parsed.pathname.toLowerCase(),
      searchParams: parsed.searchParams,
    };
  } catch {
    return {
      host: '',
      pathname: '',
      searchParams: new URLSearchParams(),
    };
  }
}

function hostMatchesProvider(host, provider) {
  const exactHosts = new Set((provider?.trustedHosts || []).map((entry) => String(entry || '').trim().toLowerCase()).filter(Boolean));
  const suffixes = (provider?.trustedHostSuffixes || []).map((entry) => String(entry || '').trim().toLowerCase()).filter(Boolean);
  if (exactHosts.has(host)) return true;
  return suffixes.some((suffix) => host.endsWith(suffix));
}

function embedMatchesProvider(host, pathname, provider) {
  const exactHosts = new Set((provider?.embedHosts || []).map((entry) => String(entry || '').trim().toLowerCase()).filter(Boolean));
  const suffixes = (provider?.embedHostSuffixes || []).map((entry) => String(entry || '').trim().toLowerCase()).filter(Boolean);
  const pathHints = (provider?.embedPathHints || []).map((entry) => String(entry || '').trim().toLowerCase()).filter(Boolean);
  const hostOk = exactHosts.has(host) || suffixes.some((suffix) => host.endsWith(suffix));
  if (!hostOk) return false;
  if (!pathHints.length) return true;
  return pathHints.some((hint) => pathname.includes(hint));
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

function collectListeningEntries(rawEntries, mode = 'provider', startMode = mode) {
  const items = [];

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
      const providerSource = providerHint ? 'key' : 'url-inferred';

      if (currentMode === 'embed') {
        items.push({
          mode: currentMode,
          provider: providerHint || inferProviderFromUrl(url),
          providerSource,
          title: '',
          url,
          kind: 'embed',
          note: '',
        });
        return;
      }

      items.push({
        mode: currentMode,
        provider: providerHint || inferProviderFromUrl(url),
        providerSource,
        label: '',
        url,
        kind: inferProviderKind(url),
        note: '',
      });
      return;
    }

    if (typeof value !== 'object') return;

    const url = String(value.url || value.href || value.src || '').trim();
    const explicitProvider = String(value.provider || '').trim();
    const providerSource = explicitProvider ? 'field' : providerHint ? 'key' : 'url-inferred';
    if (url && !isMegaUrl(url)) {
      if (currentMode === 'embed') {
        items.push({
          mode: currentMode,
          provider: explicitProvider || providerHint || inferProviderFromUrl(url),
          providerSource,
          title: value.title || value.label || '',
          url,
          kind: 'embed',
          note: value.note || value.summary || '',
        });
      } else {
        items.push({
          mode: currentMode,
          provider: explicitProvider || providerHint || inferProviderFromUrl(url),
          providerSource,
          label: value.label || value.title || '',
          url,
          kind: value.kind || inferProviderKind(url),
          note: value.note || value.summary || '',
        });
      }
    }

    for (const [key, child] of Object.entries(value)) {
      const normalizedKey = normalizeListeningKey(key);
      if (!child || LISTENING_META_KEYS.has(normalizedKey)) continue;

      const nextMode = EMBED_CONTAINER_KEYS.has(normalizedKey)
        ? 'embed'
        : PROVIDER_CONTAINER_KEYS.has(normalizedKey)
          ? 'provider'
          : currentMode;
      const nextHint = PROVIDER_CONTAINER_KEYS.has(normalizedKey) || EMBED_CONTAINER_KEYS.has(normalizedKey)
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
    const providerSource = String(item.providerSource || 'url-inferred').trim() || 'url-inferred';
    const key = `${provider}::${url}`;
    if (deduped.has(key)) continue;

    if (mode === 'embed') {
      deduped.set(key, {
        provider,
        providerSource,
        title: String(item.title || '').trim(),
        url,
        kind: 'embed',
        note: String(item.note || '').trim(),
      });
      continue;
    }

    deduped.set(key, {
      provider,
      providerSource,
      label: String(item.label || '').trim(),
      url,
      kind: String(item.kind || inferProviderKind(url)).trim() || 'listen',
      note: String(item.note || '').trim(),
    });
  }

  return Array.from(deduped.values());
}

function classifyListeningSurface(entry, mode, providerUrlsByKey = new Map()) {
  const semantics = mode === 'embed' ? 'embedded-preview' : 'external-link';
  const url = String(entry?.url || '').trim();
  const provider = String(entry?.provider || inferProviderFromUrl(url)).trim() || 'Listening link';
  const providerKey = normalizeListeningKey(provider);
  const providerSource = String(entry?.providerSource || 'url-inferred').trim() || 'url-inferred';
  const providerCatalog = LISTENING_PROVIDER_CATALOG.providers?.[providerKey];
  const kind = String(entry?.kind || (mode === 'embed' ? 'embed' : inferProviderKind(url))).trim().toLowerCase();
  const warnings = [];
  let confidenceLevel = 'uncertain';
  let confidenceReason = 'This stays visible as a lead, not a verified listening mirror.';

  if (!isLikelyUrl(url)) {
    warnings.push(`${mode} "${provider}" is missing a valid http(s) URL`);
  } else if (providerSource === 'url-inferred') {
    warnings.push(`${mode} "${provider}" only infers its provider from the URL and stays uncertain until curated explicitly`);
  } else if (!providerCatalog || typeof providerCatalog !== 'object') {
    warnings.push(`${mode} "${provider}" is not in the curated listening provider catalog`);
  } else {
    const { host, pathname } = getUrlParts(url);
    if (mode === 'provider') {
      let validProvider = true;
      if (!SUPPORTED_LISTENING_KINDS.has(kind) || kind === 'embed') {
        warnings.push(`provider "${provider}" uses unsupported kind "${entry?.kind}"`);
        validProvider = false;
      }
      if (!hostMatchesProvider(host, providerCatalog)) {
        warnings.push(`provider "${provider}" URL does not match the curated host list`);
        validProvider = false;
      }
      if (validProvider) {
        const supportedKinds = new Set((providerCatalog.supportedKinds || []).map((value) => String(value || '').trim().toLowerCase()).filter(Boolean));
        if (supportedKinds.size && !supportedKinds.has(kind)) {
          warnings.push(`provider "${provider}" kind "${kind}" is outside the curated support list`);
        } else {
          confidenceLevel = 'trusted-link-only';
          confidenceReason = 'Provider label, URL, and link shape match the curated listening data.';
        }
      }
    } else {
      let validEmbed = true;
      if (!embedMatchesProvider(host, pathname, providerCatalog)) {
        warnings.push(`embed "${provider}" is not using a curated provider/embed URL pair`);
        validEmbed = false;
      }
      if (validEmbed) {
        const expectedProviderUrls = providerUrlsByKey.get(providerKey) || new Set();
        if (providerKey === 'youtube' && expectedProviderUrls.size) {
          const embedListId = getYouTubePlaylistId(url);
          const knownListIds = new Set(Array.from(expectedProviderUrls).map((providerUrl) => getYouTubePlaylistId(providerUrl)).filter(Boolean));
          if (embedListId && knownListIds.size && !knownListIds.has(embedListId)) {
            warnings.push(`embed "${provider}" playlist does not match the curated provider URL`);
          } else {
            confidenceLevel = 'trusted-embed-ready';
            confidenceReason = 'Provider label and embed URL match the curated playback data.';
          }
        } else {
          confidenceLevel = 'trusted-embed-ready';
          confidenceReason = 'Provider label and embed URL match the curated playback data.';
        }
      }
    }
  }

  return {
    ...entry,
    provider,
    providerKey,
    providerSource,
    kind,
    semantics,
    confidenceLevel,
    confidenceReason,
    warnings,
  };
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
  const providerEmbedEntries = collectListeningEntries(providerRoots, 'embed', 'provider')
    .filter((entry) => inferProviderKind(entry.url) === 'embed');
  const explicitEmbeds = collectListeningEntries(embedRoots, 'embed', 'embed');
  const embedEntries = Array.from(
    new Map(
      [...providerEmbedEntries, ...explicitEmbeds]
        .filter((entry) => entry && typeof entry === 'object' && String(entry.url || '').trim())
        .map((entry) => [`${entry.provider}::${entry.url}`, entry])
    ).values()
  );

  const warnings = [];
  const providerUrlsByKey = new Map();
  const normalizedProviders = providerEntries.map((entry) => classifyListeningSurface(entry, 'provider'));
  for (const entry of normalizedProviders) {
    warnings.push(...entry.warnings);
    if (entry.confidenceLevel === 'trusted-link-only' && entry.providerKey) {
      if (!providerUrlsByKey.has(entry.providerKey)) providerUrlsByKey.set(entry.providerKey, new Set());
      providerUrlsByKey.get(entry.providerKey).add(entry.url);
    }
  }

  const normalizedEmbeds = embedEntries.map((entry) => classifyListeningSurface(entry, 'embed', providerUrlsByKey));
  for (const entry of normalizedEmbeds) {
    warnings.push(...entry.warnings);
  }

  const trustedProviders = normalizedProviders.filter((entry) => entry.confidenceLevel === 'trusted-link-only');
  const uncertainProviders = normalizedProviders.filter((entry) => entry.confidenceLevel === 'uncertain');
  const trustedEmbeds = normalizedEmbeds.filter((entry) => entry.confidenceLevel === 'trusted-embed-ready');
  const uncertainEmbeds = normalizedEmbeds.filter((entry) => entry.confidenceLevel === 'uncertain');
  const dedupedWarnings = Array.from(new Set(warnings));

  return {
    intro: String(listening.intro || listening.summary || mix.listeningIntro || '').trim(),
    providers: normalizedProviders,
    embeds: normalizedEmbeds,
    trustedProviders,
    uncertainProviders,
    trustedEmbeds,
    uncertainEmbeds,
    warnings: dedupedWarnings,
    summary: {
      trustedLinkCount: trustedProviders.length,
      trustedEmbedCount: trustedEmbeds.length,
      uncertainCount: uncertainProviders.length + uncertainEmbeds.length,
      surfaceCount: normalizedProviders.length + normalizedEmbeds.length,
    },
  };
}

function auditListeningPayload(mix) {
  const title = String(mix.displayTitle || mix.title || mix.slug || 'Untitled mix').trim();
  const listening = mix.listening;

  if (listening != null && (typeof listening !== 'object' || Array.isArray(listening))) {
    return {
      warnings: ['listening must be an object when present'],
      warningCount: 1,
      hasListeningSurface: false,
      summary: `${title}: listening must be an object when present`,
    };
  }

  const normalizedListening = normalizeListening(mix);
  const dedupedWarnings = Array.isArray(normalizedListening.warnings) ? normalizedListening.warnings : [];
  return {
    warnings: dedupedWarnings,
    warningCount: dedupedWarnings.length,
    hasListeningSurface: (normalizedListening.summary?.surfaceCount || 0) > 0,
    trustedLinkCount: normalizedListening.summary?.trustedLinkCount || 0,
    trustedEmbedCount: normalizedListening.summary?.trustedEmbedCount || 0,
    uncertainCount: normalizedListening.summary?.uncertainCount || 0,
    summary: dedupedWarnings.length ? `${title}: ${dedupedWarnings[0]}` : '',
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
        listeningHealth: auditListeningPayload(mix),
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
  const relatedNoteSlugs = Array.isArray(note.relatedNoteSlugs) ? note.relatedNoteSlugs.filter(Boolean) : [];
  const rawSeries = note.series && typeof note.series === 'object' ? note.series : null;
  const series = rawSeries
    ? {
        slug: String(rawSeries.slug || '').trim(),
        title: String(rawSeries.title || '').trim(),
        description: String(rawSeries.description || '').trim(),
        order: Number.isInteger(rawSeries.order) ? rawSeries.order : null,
      }
    : null;

  return {
    ...note,
    title: note.title || `Note ${index + 1}`,
    slug: note.slug || slugify(note.title || `note-${index + 1}`),
    date: note.publishedAt || note.date || note.published_at || '',
    excerpt: note.excerpt || note.summary || note.description || '',
    body: bodyParagraphs.join('\n\n'),
    bodyParagraphs,
    relatedMixSlugs,
    relatedNoteSlugs,
    series: series && series.slug && series.title ? series : null,
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

function buildSeriesGroups(notes) {
  const groups = new Map();

  for (const note of notes) {
    if (!note.series?.slug || !note.series?.title) continue;
    const existing = groups.get(note.series.slug) || {
      slug: note.series.slug,
      title: note.series.title,
      description: note.series.description || '',
      notes: [],
    };
    existing.notes.push(note);
    if (!existing.description && note.series.description) {
      existing.description = note.series.description;
    }
    groups.set(note.series.slug, existing);
  }

  return Array.from(groups.values())
    .map((group) => ({
      ...group,
      notes: [...group.notes].sort((a, b) => {
        const aOrder = Number.isInteger(a.series?.order) ? a.series.order : Infinity;
        const bOrder = Number.isInteger(b.series?.order) ? b.series.order : Infinity;
        if (aOrder !== bOrder) return aOrder - bOrder;

        const aDate = a.date ? new Date(a.date).getTime() : -Infinity;
        const bDate = b.date ? new Date(b.date).getTime() : -Infinity;
        if (aDate !== bDate) return bDate - aDate;

        return String(a.title || '').localeCompare(String(b.title || ''));
      }),
    }))
    .sort((a, b) => {
      const aDate = a.notes[0]?.date ? new Date(a.notes[0].date).getTime() : -Infinity;
      const bDate = b.notes[0]?.date ? new Date(b.notes[0].date).getTime() : -Infinity;
      return bDate - aDate;
    });
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

function normalizeTagLabel(value) {
  return String(value || '')
    .trim()
    .replace(/\s+/g, ' ');
}

function normalizeFacetToken(value) {
  const normalized = normalizeTagLabel(value)
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');

  return normalized;
}

function pluralize(count, singular, plural = `${singular}s`) {
  return count === 1 ? singular : plural;
}

function uniqueValues(values) {
  return Array.from(
    new Set(
      flattenToArray(values)
        .map((value) => String(value || '').trim())
        .filter(Boolean)
    )
  );
}

function joinFilterValues(values) {
  return uniqueValues(values).join('|');
}

function buildTagMetadata(tags) {
  const deduped = new Map();

  for (const tag of flattenToArray(tags)) {
    const label = normalizeTagLabel(tag);
    const value = normalizeFacetToken(label);
    if (!label || !value || deduped.has(value)) continue;

    deduped.set(value, {
      label,
      value,
      searchTerms: uniqueValues([
        label,
        label.replace(/[-_]+/g, ' '),
        value,
        value.replace(/-/g, ' '),
      ]),
    });
  }

  return Array.from(deduped.values());
}

function countTopTags(items, limit = 3) {
  const counts = new Map();

  for (const item of items) {
    const tags = Array.isArray(item?.discovery?.tags) ? item.discovery.tags : buildTagMetadata(item?.tags);
    for (const tag of tags) {
      const current = counts.get(tag.value) || { ...tag, count: 0 };
      current.count += 1;
      counts.set(tag.value, current);
    }
  }

  return Array.from(counts.values())
    .sort((a, b) => {
      if (b.count !== a.count) return b.count - a.count;
      return a.label.localeCompare(b.label);
    })
    .slice(0, limit);
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

function makeDiscoveryFilter(value, label, count) {
  return {
    value,
    label: count > 0 ? `${label} · ${count}` : label,
  };
}

function buildMixDiscovery(mix) {
  const tags = buildTagMetadata(mix.tags);
  const filterValues = [];
  const facetLabels = [];
  const trackArtists = mix.tracklist.map((track) => track?.artist).filter(Boolean);
  const trackTitles = mix.tracklist.map((track) => track?.title || track?.displayText).filter(Boolean);
  const relatedNoteTags = mix.relatedNotes.flatMap((note) => buildTagMetadata(note.tags).flatMap((tag) => tag.searchTerms));
  const relatedNoteTitles = mix.relatedNotes.map((note) => note.title).filter(Boolean);
  const relatedNoteExcerpts = mix.relatedNotes.map((note) => note.excerpt || note.body).filter(Boolean);
  const topArtists = Array.isArray(mix.stats?.topArtists) ? mix.stats.topArtists : [];
  const favoriteTracks = Array.isArray(mix.stats?.favoriteTracks) ? mix.stats.favoriteTracks : [];
  const coverTracks = Array.isArray(mix.stats?.coverTracks) ? mix.stats.coverTracks : [];
  const remixTracks = Array.isArray(mix.stats?.remixTracks) ? mix.stats.remixTracks : [];
  const listeningProviders = Array.isArray(mix.listening?.providers) ? mix.listening.providers : [];
  const listeningEmbeds = Array.isArray(mix.listening?.embeds) ? mix.listening.embeds : [];

  for (const tag of tags) {
    filterValues.push(`tag:${tag.value}`);
  }

  if (mix.relatedNotes.length) {
    filterValues.push('state:has-related');
    facetLabels.push('related notes');
  }
  if (mix.highlightedTracks.length) {
    filterValues.push('state:has-highlights');
    facetLabels.push('highlighted tracks');
  }
  if ((mix.listening?.summary?.surfaceCount || 0) > 0) {
    filterValues.push('state:has-listening');
    facetLabels.push('listening surfaces');
  }

  const sourceValue = normalizeFacetToken(mix.sourcePlatform);
  if (sourceValue) {
    filterValues.push(`source:${sourceValue}`);
    facetLabels.push(`${mix.sourcePlatform} source`);
  }
  if ((mix.stats?.coverCount || 0) > 0) {
    filterValues.push('texture:covers');
    facetLabels.push('cover versions');
  }
  if ((mix.stats?.remixCount || 0) > 0) {
    filterValues.push('texture:remixes');
    facetLabels.push('remixes');
  }

  return {
    tags,
    filters: uniqueValues(filterValues),
    filtersText: joinFilterValues(filterValues),
    tagsText: joinFilterValues(tags.map((tag) => tag.value)),
    searchBlob: buildSearchBlob([
      mix.title,
      mix.displayTitle,
      mix.slug.replace(/-/g, ' '),
      mix.excerpt,
      mix.notes,
      mix.coverCredit,
      mix.sourcePlatform,
      formatDate(mix.date),
      formatMonthYear(mix.date),
      mix.number !== '' ? `mix ${mix.number}` : '',
      mix.highlightedTracks.length ? `${mix.highlightedTracks.length} highlighted tracks` : '',
      mix.relatedNotes.length ? `${mix.relatedNotes.length} related notes` : 'no related notes',
      mix.listening?.summary?.surfaceCount ? `${mix.listening.summary.surfaceCount} listening surfaces` : '',
      mix.usesArchivalCoverFallback ? 'archival cover fallback tumblr import' : '',
      tags.flatMap((tag) => tag.searchTerms),
      facetLabels,
      trackArtists,
      trackTitles,
      topArtists,
      favoriteTracks,
      coverTracks,
      remixTracks,
      relatedNoteTitles,
      relatedNoteExcerpts,
      relatedNoteTags,
      listeningProviders.flatMap((provider) => [provider.provider, provider.label, provider.note, provider.kind]),
      listeningEmbeds.flatMap((embed) => [embed.provider, embed.title, embed.note]),
    ]),
  };
}

function buildNoteDiscovery(note) {
  const tags = buildTagMetadata(note.tags);
  const filterValues = tags.map((tag) => `tag:${tag.value}`);
  const relatedMixTags = note.relatedMixes.flatMap((mix) => mix.discovery?.tags?.flatMap((tag) => tag.searchTerms) || []);
  const relatedMixTracks = note.relatedMixes.flatMap((mix) => mix.tracklist.map((track) => track?.displayText || track?.title).filter(Boolean));
  const relatedMixArtists = note.relatedMixes.flatMap((mix) => mix.tracklist.map((track) => track?.artist).filter(Boolean));
  const relatedMixNotes = note.relatedMixes.flatMap((mix) => mix.relatedNotes.map((relatedNote) => relatedNote.title).filter(Boolean));
  const relatedNoteTitles = (note.relatedNotes || []).map((relatedNote) => relatedNote.title).filter(Boolean);

  if (note.relatedMixes.length) {
    filterValues.push('state:has-related');
  }
  if (note.series?.slug) {
    filterValues.push('state:in-series');
    filterValues.push(`series:${note.series.slug}`);
  }
  if ((note.relatedNotes || []).length) {
    filterValues.push('state:has-note-links');
  }

  return {
    tags,
    filters: uniqueValues(filterValues),
    filtersText: joinFilterValues(filterValues),
    tagsText: joinFilterValues(tags.map((tag) => tag.value)),
    searchBlob: buildSearchBlob([
      note.title,
      note.slug.replace(/-/g, ' '),
      note.excerpt,
      note.body,
      note.date ? formatDate(note.date) : '',
      note.series?.title || '',
      note.series?.description || '',
      note.relatedMixes.length ? `${note.relatedMixes.length} related mixes` : 'standalone note',
      note.relatedNotes?.length ? `${note.relatedNotes.length} related notes` : '',
      tags.flatMap((tag) => tag.searchTerms),
      note.relatedMixes.flatMap((mix) => [
        mix.title,
        mix.displayTitle,
        mix.excerpt,
        mix.sourcePlatform,
        mix.number !== '' ? `mix ${mix.number}` : '',
      ]),
      relatedMixTags,
      relatedMixArtists,
      relatedMixTracks,
      relatedMixNotes,
      relatedNoteTitles,
    ]),
  };
}

function annotateDiscovery(mixes, notes) {
  const mixesWithDiscovery = mixes.map((mix) => ({
    ...mix,
    discovery: buildMixDiscovery(mix),
  }));
  const mixBySlug = new Map(mixesWithDiscovery.map((mix) => [mix.slug, mix]));
  const notesWithResolvedMixes = notes.map((note) => ({
    ...note,
    relatedMixes: note.relatedMixSlugs.map((slug) => mixBySlug.get(slug)).filter(Boolean),
  }));
  const notesBySlug = new Map(notesWithResolvedMixes.map((note) => [note.slug, note]));
  const seriesGroups = buildSeriesGroups(notesWithResolvedMixes);
  const seriesBySlug = new Map(seriesGroups.map((group) => [group.slug, group]));
  const notesWithNoteLinks = notesWithResolvedMixes.map((note) => {
    const seriesGroup = note.series?.slug ? seriesBySlug.get(note.series.slug) || null : null;
    const seriesNotes = seriesGroup ? seriesGroup.notes.filter((candidate) => candidate.slug !== note.slug) : [];
    const explicitRelatedNotes = note.relatedNoteSlugs.map((slug) => notesBySlug.get(slug)).filter(Boolean);
    const relatedNotes = Array.from(
      new Map([...seriesNotes, ...explicitRelatedNotes].map((candidate) => [candidate.slug, candidate])).values()
    );

    return {
      ...note,
      seriesGroup,
      seriesNotes,
      explicitRelatedNotes,
      relatedNotes,
    };
  });
  const notesWithDiscovery = notesWithNoteLinks.map((note) => ({
    ...note,
    discovery: buildNoteDiscovery(note),
  }));
  const notesByMixSlug = new Map();

  for (const note of notesWithDiscovery) {
    for (const slug of note.relatedMixSlugs) {
      const current = notesByMixSlug.get(slug) || [];
      current.push(note);
      notesByMixSlug.set(slug, current);
    }
  }

  return {
    mixes: mixesWithDiscovery.map((mix) => ({
      ...mix,
      relatedNotes: notesByMixSlug.get(mix.slug) || mix.relatedNotes || [],
      discovery: buildMixDiscovery({
        ...mix,
        relatedNotes: notesByMixSlug.get(mix.slug) || mix.relatedNotes || [],
      }),
    })),
    notes: notesWithDiscovery,
    noteSeries: seriesGroups,
  };
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

function renderAboutSection(section) {
  const summary = section.summary ? `<p class="supporting-copy">${escapeHtml(section.summary)}</p>` : '';
  const body = renderParagraphs(section.body);
  const items = Array.isArray(section.items) && section.items.length
    ? `<div class="prose">${section.items
        .map((item) => `<p><strong>${escapeHtml(item.label)}:</strong> ${escapeHtml(item.text)}</p>`)
        .join('')}</div>`
    : '';
  const links = Array.isArray(section.links) && section.links.length
    ? `<div class="related-list">
        ${section.links
          .map(
            (link) => `<a class="related-card" href="${escapeHtml(link.href)}">
              <p class="related-card__meta">${escapeHtml(section.label)}</p>
              <h3>${escapeHtml(link.label)}</h3>
              <p>${escapeHtml(link.description || '')}</p>
            </a>`
          )
          .join('')}
      </div>`
    : '';

  return `<section class="section-block section-block--split">
      <div>
        <p class="eyebrow">${escapeHtml(section.label || 'About')}</p>
        <h2>${escapeHtml(section.title || '')}</h2>
        ${summary}
      </div>
      <div>
        <div class="prose">${body}</div>
        ${items}
        ${links}
      </div>
    </section>`;
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
  const sourcePlatform = providerLabelFromKey(mix.sourcePlatform || mix.source?.platform || '');
  const sourceFeedType = humanizeToken(mix.source?.feedType || '');
  const importedAt = mix.source?.importedAt || '';
  const guid = String(mix.source?.guid || '').trim();
  const sourceSummaryParts = [];
  const cleanupParagraphs = [];
  const residueParagraphs = [];
  const suppressedLinks = Object.entries(mix.legacyLinks || {}).filter(([, href]) => typeof href === 'string' && href.trim());

  if (mix.sourceUrl) {
    const importSource = [sourcePlatform, sourceFeedType].filter(Boolean).join(' ');
    if (importSource && importedAt) {
      sourceSummaryParts.push(`Imported from ${importSource} on ${formatUtcDate(importedAt)}.`);
    } else if (importSource) {
      sourceSummaryParts.push(`Imported from ${importSource}.`);
    } else if (importedAt) {
      sourceSummaryParts.push(`Imported on ${formatUtcDate(importedAt)}.`);
    }

    if (guid && guid !== mix.sourceUrl) {
      sourceSummaryParts.push('A separate source GUID is preserved alongside the post URL.');
    }

    resourceCards.push(`
      <article class="resource-card">
        <p class="resource-card__eyebrow">Original source</p>
        <h3>Original post</h3>
        ${sourceSummaryParts.map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`).join('')}
        <a class="text-link" href="${escapeHtml(mix.sourceUrl)}">Open original post</a>
      </article>
    `);
  }

  if (suppressedLinks.length) {
    cleanupParagraphs.push(
      suppressedLinks.length === 1
        ? 'A legacy Mega download URL survives in the archived source data, but it is intentionally withheld from the published page.'
        : `${suppressedLinks.length} legacy Mega download URLs survive in the archived source data, but they are intentionally withheld from the published page.`
    );
  }

  if (mix.usesArchivalCoverFallback) {
    cleanupParagraphs.push('Tumblr-hosted artwork stays available as archival context, but it is not promoted into the primary cover slot without stronger metadata.');
  }

  if (cleanupParagraphs.length) {
    resourceCards.push(`
      <article class="resource-card">
        <p class="resource-card__eyebrow">Archive cleanup</p>
        <h3>Cleanup choices</h3>
        ${cleanupParagraphs.map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`).join('')}
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

  if (mix.legacyHtml) {
    residueParagraphs.push('A sanitized copy of the original post HTML is kept for repair and import cleanup work.');

    const residueDetails = [];
    if (mix.legacy?.tumblrHeading) residueDetails.push('original Tumblr heading');
    if (mix.legacy?.favoriteTrackCue) residueDetails.push('favorite-track cue');
    if (mix.coverCredit && mix.usesArchivalCoverFallback) residueDetails.push('archived artwork credit');
    if (suppressedLinks.length) residueDetails.push('download trace');

    if (residueDetails.length) {
      residueParagraphs.push(`It still preserves the ${formatInlineList(residueDetails)}.`);
    }
  } else if (mix.coverCredit && mix.usesArchivalCoverFallback) {
    residueParagraphs.push('Archived artwork credit survives in the source data even though it is not treated as canonical cover metadata.');
  }

  if (mix.coverCredit && mix.usesArchivalCoverFallback) {
    residueParagraphs.push(`Archived artwork credit: ${mix.coverCredit}.`);
  } else if (mix.coverCredit) {
    residueParagraphs.push(`Cover credit: ${mix.coverCredit}.`);
  }

  if (residueParagraphs.length) {
    resourceCards.push(`
      <article class="resource-card">
        <p class="resource-card__eyebrow">Preserved residue</p>
        <h3>Legacy snapshot</h3>
        ${residueParagraphs.map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`).join('')}
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
  const listening = mix.listening && typeof mix.listening === 'object' ? mix.listening : {};
  const trustedEmbeds = Array.isArray(listening.trustedEmbeds) ? listening.trustedEmbeds : [];
  const trustedProviders = Array.isArray(listening.trustedProviders) ? listening.trustedProviders : [];
  const uncertainProviders = Array.isArray(listening.uncertainProviders) ? listening.uncertainProviders : [];
  const uncertainEmbeds = Array.isArray(listening.uncertainEmbeds) ? listening.uncertainEmbeds : [];
  const actionableTrustedLinks = trustedProviders.filter((provider) => {
    const kind = String(provider.kind || '').trim().toLowerCase();
    return ['playlist', 'album', 'track', 'set'].includes(kind);
  });
  const uncertainSurfaces = [...uncertainEmbeds, ...uncertainProviders];

  if (!trustedEmbeds.length && !actionableTrustedLinks.length && !uncertainSurfaces.length) return '';

  const intro = listening.intro ? `<p class="listening-section__intro">${escapeHtml(listening.intro)}</p>` : '';
  const summaryBits = [];
  if (trustedEmbeds.length) summaryBits.push(`${trustedEmbeds.length} verified preview${trustedEmbeds.length === 1 ? '' : 's'}`);
  if (actionableTrustedLinks.length) summaryBits.push(`${actionableTrustedLinks.length} verified external link${actionableTrustedLinks.length === 1 ? '' : 's'}`);
  if (uncertainSurfaces.length) summaryBits.push(`${uncertainSurfaces.length} uncertain lead${uncertainSurfaces.length === 1 ? '' : 's'}`);
  const summary = summaryBits.length ? `<p class="listening-section__summary">${escapeHtml(summaryBits.join(' · '))}</p>` : '';

  return `<section class="section-block section-block--compact">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Listening</p>
          <h2>Listening surfaces</h2>
        </div>
      </div>
      ${intro}
      ${summary}
      ${trustedEmbeds.length
        ? `<div class="listening-subsection">
            <p class="listening-subsection__title">Embedded preview</p>
            <div class="embed-stack">
              ${trustedEmbeds
                .map((embed) => `<article class="embed-card">
                    <div class="embed-card__frame">
                      <iframe
                        src="${escapeHtml(embed.url)}"
                        title="${escapeHtml(embed.title || `${embed.provider} preview for ${mix.title}`)}"
                        loading="lazy"
                        allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
                        referrerpolicy="strict-origin-when-cross-origin"
                      ></iframe>
                    </div>
                    <div class="embed-card__meta">
                      <p class="provider-card__eyebrow">${escapeHtml(embed.confidenceLevel === 'trusted-embed-ready' ? 'Trusted embed-ready' : 'Embedded preview')}</p>
                      <h3>${escapeHtml(embed.title || `${embed.provider} preview`)}</h3>
                      <p>${escapeHtml(embed.confidenceReason)}</p>
                      ${embed.note ? `<p>${escapeHtml(embed.note)}</p>` : ''}
                    </div>
                  </article>`)
                .join('')}
            </div>
          </div>`
        : ''}
      ${actionableTrustedLinks.length
        ? `<div class="listening-subsection">
            <p class="listening-subsection__title">External links</p>
            <div class="provider-grid">
              ${actionableTrustedLinks
                .map((provider) => `<article class="provider-card">
                    <p class="provider-card__eyebrow">Trusted link only</p>
                    <h3>${escapeHtml(provider.label || `Open on ${provider.provider}`)}</h3>
                    <p>${escapeHtml(provider.confidenceReason)}</p>
                    ${provider.note ? `<p>${escapeHtml(provider.note)}</p>` : ''}
                    <div class="button-row button-row--compact">
                      <a class="button button--secondary" href="${escapeHtml(provider.url)}">${escapeHtml(provider.label || `Open on ${provider.provider}`)}</a>
                    </div>
                  </article>`)
                .join('')}
            </div>
          </div>`
        : ''}
      ${uncertainSurfaces.length
        ? `<div class="listening-subsection">
            <p class="listening-subsection__title">Uncertain leads</p>
            <div class="provider-grid">
              ${uncertainSurfaces
                .map((entry) => `<article class="provider-card provider-card--uncertain">
                    <p class="provider-card__eyebrow">Uncertain</p>
                    <h3>${escapeHtml(entry.title || entry.label || entry.provider || 'Listening lead')}</h3>
                    <p>${escapeHtml(entry.confidenceReason || 'This stays visible as a lead, not a verified listening mirror.')}</p>
                    ${entry.note ? `<p>${escapeHtml(entry.note)}</p>` : ''}
                    ${entry.url ? `<div class="button-row button-row--compact"><a class="button button--secondary" href="${escapeHtml(entry.url)}">Inspect link</a></div>` : ''}
                  </article>`)
                .join('')}
            </div>
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
  const relatedCount = mixes.filter((mix) => mix.relatedNotes.length > 0).length;
  const highlightCount = mixes.filter((mix) => mix.highlightedTracks.length > 0).length;
  const listeningCount = mixes.filter((mix) => (mix.listening?.summary?.surfaceCount || 0) > 0).length;
  const tumblrCount = mixes.filter((mix) => normalizeFacetToken(mix.sourcePlatform) === 'tumblr').length;
  const coverCount = mixes.filter((mix) => (mix.stats?.coverCount || 0) > 0).length;
  const remixCount = mixes.filter((mix) => (mix.stats?.remixCount || 0) > 0).length;
  const discoveryFilters = [
    { label: 'All mixes', value: 'all' },
    makeDiscoveryFilter('state:has-related', 'Related notes', relatedCount),
    makeDiscoveryFilter('state:has-highlights', 'Highlighted tracks', highlightCount),
    ...(listeningCount ? [makeDiscoveryFilter('state:has-listening', 'Listening surfaces', listeningCount)] : []),
    ...(tumblrCount ? [makeDiscoveryFilter('source:tumblr', 'Tumblr source', tumblrCount)] : []),
    ...(coverCount ? [makeDiscoveryFilter('texture:covers', 'Covers', coverCount)] : []),
    ...(remixCount ? [makeDiscoveryFilter('texture:remixes', 'Remixes', remixCount)] : []),
    ...topTags.map((tag) => makeDiscoveryFilter(`tag:${tag.value}`, `Tag: ${tag.label}`, tag.count)),
  ];
  const body = mixes.length
    ? `<section class="page-intro">
        <p class="eyebrow">Archive</p>
        <h1>Published mixes</h1>
        <p class="page-intro__copy">A chronological run of finished mixes, each with whatever notes, artwork, and track sequencing survived the urge to over-explain.</p>
      </section>
      ${renderDiscoveryControls({
        title: 'Search archive',
        description: 'Filter by titles, tracks, notes, and a few grounded archive signals pulled directly from the mix data.',
        queryLabel: 'Search archive',
        queryPlaceholder: 'Title, artist, track, note, year...',
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
              data-discovery-tags="${escapeHtml(mix.discovery.tagsText)}"
              data-discovery-states="${escapeHtml(joinFilterValues(mix.discovery.filters.filter((value) => value.startsWith('state:')).map((value) => value.slice(6))))}"
              data-discovery-filters="${escapeHtml(mix.discovery.filtersText)}"
              data-discovery-search="${escapeHtml(mix.discovery.searchBlob)}"
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
  const orphanNotes = notes.filter((note) => note.relatedMixes.length === 0);
  const approvedDrafts = drafts.filter((draft) => draft.status === 'approved').length;
  const draftDrafts = drafts.filter((draft) => draft.status === 'draft').length;
  const listeningIssueMixes = mixes.filter((mix) => (mix.listeningHealth?.warningCount || 0) > 0);
  const listeningIssueCount = listeningIssueMixes.reduce((total, mix) => total + (mix.listeningHealth?.warningCount || 0), 0);
  const mixesWithListening = mixes.filter((mix) => mix.listeningHealth?.hasListeningSurface).length;
  const noteCoverageGaps = mixes.length - publishedWithNotes;
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
  if (orphanNotes.length) {
    validationSignals.push(`${orphanNotes.length} note${orphanNotes.length === 1 ? '' : 's'} currently sit without a related published mix.`);
  }
  if (listeningIssueCount) {
    validationSignals.push(`${listeningIssueCount} listening/provider warning${listeningIssueCount === 1 ? '' : 's'} need a manual pass.`);
  }

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

  if (listeningIssueMixes.length) {
    nextActions.push(`Review listening/provider payloads for ${listeningIssueMixes[0].title} so the archive only signals trustworthy playback surfaces.`);
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
    {
      label: 'Listening warnings',
      value: String(listeningIssueCount),
      detail: listeningIssueMixes.length ? `Latest flagged: ${listeningIssueMixes[0].title}` : 'No suspicious listening/provider payloads surfaced',
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
        ? `${noteCoverageGaps} published gap${noteCoverageGaps === 1 ? '' : 's'} remain. ${notesWithRelations} of ${notes.length} note${notes.length === 1 ? '' : 's'} already point back into the archive.`
        : 'Coverage will appear here once published mixes land in the archive.',
      detail: latestPublishedWithoutNote
        ? `Latest gap: ${latestPublishedWithoutNote.title}${orphanNotes.length ? ` · Orphan note${orphanNotes.length === 1 ? '' : 's'}: ${orphanNotes.length}` : ''}`
        : orphanNotes.length
          ? `Recent published mixes are covered, but ${orphanNotes.length} note${orphanNotes.length === 1 ? '' : 's'} still have no archive attachment.`
          : 'Recent published mixes all have at least one related note.',
    },
    {
      eyebrow: 'Listening health',
      title: listeningIssueCount
        ? `${listeningIssueCount} warning${listeningIssueCount === 1 ? '' : 's'} across ${listeningIssueMixes.length} mix${listeningIssueMixes.length === 1 ? '' : 'es'}`
        : `${mixesWithListening}/${mixes.length || 0} published mixes carry listening surfaces`,
      body: listeningIssueCount
        ? 'The page can still build cleanly, but these listening/provider payloads look suspicious enough to review before they read as authoritative.'
        : mixesWithListening
          ? `${mixes.length - mixesWithListening} published mix${mixes.length - mixesWithListening === 1 ? '' : 'es'} still rely on the archive page alone with no provider mirror attached.`
          : 'No published mixes carry explicit listening/provider data yet.',
      detail: listeningIssueMixes.length
        ? listeningIssueMixes.slice(0, 3).map((mix) => mix.listeningHealth.summary).filter(Boolean).join(' · ')
        : mixesWithListening
          ? 'Current listening surfaces resolve to supported provider and embed patterns.'
          : 'Add explicit provider data only when the archive has something real to point at.',
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
  const introParagraphs = normalizeParagraphs(about.intro);
  const structuredSections = [
    about.editorialNote ? renderAboutSection(about.editorialNote) : '',
    ...sections.map((section) => renderAboutSection(section)),
    about.closing ? renderAboutSection(about.closing) : '',
  ].filter(Boolean);
  const body = structuredSections.length
    ? structuredSections.join('')
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
          ${introParagraphs.length ? `<div class="prose">${renderParagraphs(introParagraphs)}</div>` : ''}
        </div>
      </section>
      ${body}`,
  });
}

function renderNotesPage({ notes }) {
  const hasNotes = notes.length > 0;
  const topTags = countTopTags(notes);
  const linkedCount = notes.filter((note) => note.relatedMixes.length > 0).length;
  const seriesGroups = buildSeriesGroups(notes);
  const discoveryFilters = [
    { label: 'All notes', value: 'all' },
    makeDiscoveryFilter('state:has-related', 'Linked mixes', linkedCount),
    makeDiscoveryFilter('state:in-series', 'In a series', notes.filter((note) => note.series?.slug).length),
    makeDiscoveryFilter('state:has-note-links', 'Linked notes', notes.filter((note) => note.relatedNotes?.length).length),
    ...seriesGroups.map((group) => makeDiscoveryFilter(`series:${group.slug}`, `Series: ${group.title}`, group.notes.length)),
    ...topTags.map((tag) => makeDiscoveryFilter(`tag:${tag.value}`, `Tag: ${tag.label}`, tag.count)),
  ];
  const seriesSection = seriesGroups.length
    ? `<section class="section-block section-block--compact">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Series</p>
            <h2>Small runs of related notes</h2>
          </div>
          <p class="supporting-copy">Series stay lightweight: just note metadata and direct links back into the notebook.</p>
        </div>
        <div class="related-list">
          ${seriesGroups
            .map((group) => {
              const anchor = group.notes[0];
              const description = group.description || `${group.notes.length} note${group.notes.length === 1 ? '' : 's'} currently grouped under ${group.title}.`;
              return `<a class="related-card" href="./${escapeHtml(anchor.slug)}/">
                <p class="related-card__meta">${escapeHtml(`${group.notes.length} note${group.notes.length === 1 ? '' : 's'} in series`)}</p>
                <h3>${escapeHtml(group.title)}</h3>
                <p>${escapeHtml(description)}</p>
              </a>`;
            })
            .join('')}
        </div>
      </section>`
    : '';
  const body = hasNotes
    ? `<section class="page-intro">
        <p class="eyebrow">Notes</p>
        <h1>Notebook fragments</h1>
        <p class="page-intro__copy">Small observations around sequencing, atmosphere, and the songs that took time to reveal themselves.</p>
      </section>
      ${seriesSection}
      ${renderDiscoveryControls({
        title: 'Search notes',
        description: 'Filter by note text, related mixes, and the small set of tags already carried in the notebook.',
        queryLabel: 'Search notes',
        queryPlaceholder: 'Title, phrase, mix, tag...',
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
              data-discovery-tags="${escapeHtml(note.discovery.tagsText)}"
              data-discovery-states="${escapeHtml(joinFilterValues(note.discovery.filters.filter((value) => value.startsWith('state:')).map((value) => value.slice(6))))}"
              data-discovery-filters="${escapeHtml(note.discovery.filtersText)}"
              data-discovery-search="${escapeHtml(note.discovery.searchBlob)}"
            >
              <p class="note-card__meta">${escapeHtml(note.date ? formatDate(note.date) : 'Undated note')}</p>
              ${note.series?.title
                ? `<p class="note-card__meta">${escapeHtml(
                    note.series.order && note.seriesGroup?.notes?.length
                      ? `${note.series.title} · Part ${note.series.order} of ${note.seriesGroup.notes.length}`
                      : note.series.title
                  )}</p>`
                : ''}
              <h2>${escapeHtml(note.title)}</h2>
              <p>${escapeHtml(note.excerpt || stripHtml(note.body).slice(0, 180) || 'A short note waiting for more context.')}</p>
              ${note.tags.length ? renderTagList(note.tags) : ''}
              ${note.relatedMixes.length
                ? `<p class="note-card__link">Related mixes: ${note.relatedMixes
                    .map((mix) => `<a href="../mixes/${escapeHtml(mix.slug)}/">${escapeHtml(mix.title)}</a>`)
                    .join(', ')}</p>`
                : ''}
              ${note.relatedNotes?.length
                ? `<p class="note-card__link">Nearby notes: ${note.relatedNotes
                    .map((relatedNote) => `<a href="./${escapeHtml(relatedNote.slug)}/">${escapeHtml(relatedNote.title)}</a>`)
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
  const seriesSummary = note.series?.title
    ? note.series.order && note.seriesGroup?.notes?.length
      ? `${note.series.title} · Part ${note.series.order} of ${note.seriesGroup.notes.length}`
      : note.series.title
    : '';
  const contextualRelatedNotes = note.explicitRelatedNotes || [];

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
            ${seriesSummary ? `<span>${escapeHtml(seriesSummary)}</span>` : ''}
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
      ${note.seriesGroup
        ? `<section class="section-block section-block--split">
            <div>
              <p class="eyebrow">Series</p>
              <h2>${escapeHtml(note.seriesGroup.title)}</h2>
            </div>
            <div>
              <div class="prose">
                ${note.seriesGroup.description ? `<p>${escapeHtml(note.seriesGroup.description)}</p>` : ''}
                <p>${escapeHtml(
                  note.series?.order && note.seriesGroup.notes.length
                    ? `This note sits at part ${note.series.order} of ${note.seriesGroup.notes.length} in the series.`
                    : `This note is part of a ${note.seriesGroup.notes.length}-note series.`
                )}</p>
              </div>
              ${renderNoteMiniList(note.seriesNotes || [], {
                basePath: '../',
                emptyMessage: 'This series currently only contains this note.',
              })}
            </div>
          </section>`
        : ''}
      ${contextualRelatedNotes.length
        ? `<section class="section-block section-block--split">
            <div>
              <p class="eyebrow">Related notes</p>
              <h2>Nearby reading from the notebook</h2>
            </div>
            <div>
              ${renderNoteMiniList(contextualRelatedNotes, {
                basePath: '../',
              })}
            </div>
          </section>`
        : ''}
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
  const discoveryGraph = annotateDiscovery(relationshipGraph.mixes, relationshipGraph.notes);
  const mixes = discoveryGraph.mixes;
  const notes = discoveryGraph.notes;
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
