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

function normalizeMixes(rawMixes) {
  if (!Array.isArray(rawMixes)) return [];

  return sortMixes(
    rawMixes.map((mix, index) => {
      const title = mix.title || mix.displayTitle || mix.name || `Untitled Mix ${index + 1}`;
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
      const links = {
        ...(mix.links && typeof mix.links === 'object' ? mix.links : {}),
        ...(mix.download?.url ? { [mix.download.label || 'Download mix']: mix.download.url } : {}),
      };

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
        image: mix.image || mix.coverImage || mix.heroImage || mix.cover?.imageUrl || '',
        imageAlt: mix.imageAlt || mix.coverAlt || mix.cover?.alt || `${title} artwork`,
        coverCredit: mix.cover?.credit || mix.coverCredit || '',
        sourceUrl: mix.source?.sourceUrl || mix.sourceUrl || '',
        legacyHtml: mix.legacy?.descriptionHtml || mix.descriptionHtml || '',
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
  const combined = [...fromDirect, ...fromArchive, ...publishedMixes, ...importedMixes];
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

function renderCover(mix, compact = false) {
  if (mix.image) {
    return `<figure class="mix-cover ${compact ? 'mix-cover--compact' : ''}"><img src="${escapeHtml(mix.image)}" alt="${escapeHtml(mix.imageAlt)}"></figure>`;
  }

  return `<div class="mix-cover mix-cover--placeholder ${compact ? 'mix-cover--compact' : ''}">
    <div>
      <span class="mix-cover__kicker">No artwork yet</span>
      <strong>${escapeHtml(mix.title)}</strong>
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
        <h3>Original Tumblr post</h3>
        <p>The imported source page stays linked so the archive can always point back to the original post.</p>
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

  const linkItems = Object.entries(mix.links || {}).filter(([, href]) => typeof href === 'string' && href.trim());
  if (linkItems.length) {
    resourceCards.push(`
      <article class="resource-card">
        <p class="resource-card__eyebrow">Links</p>
        <h3>Listen or download</h3>
        <div class="button-row">
          ${linkItems
            .map(([label, href]) => `<a class="button button--secondary" href="${escapeHtml(href)}">${escapeHtml(label.replace(/_/g, ' '))}</a>`)
            .join('')}
        </div>
      </article>
    `);
  }

  const legacyHtml = String(mix.legacyHtml || '').trim();
  if (!resourceCards.length && !legacyHtml) return '';

  return `${resourceCards.length
    ? `<section class="section-block">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Resources</p>
            <h2>Links, provenance, and source residue</h2>
          </div>
        </div>
        <div class="resource-grid">${resourceCards.join('')}</div>
      </section>`
    : ''}${legacyHtml
    ? `<section class="section-block section-block--split">
        <div>
          <p class="eyebrow">Original post</p>
          <h2>Imported Tumblr snapshot</h2>
        </div>
        <div class="legacy-embed">${legacyHtml}</div>
      </section>`
    : ''}`;
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
  const body = mixes.length
    ? `<section class="page-intro">
        <p class="eyebrow">Archive</p>
        <h1>Published mixes</h1>
        <p class="page-intro__copy">A chronological run of finished mixes, each with whatever notes, artwork, and track sequencing survived the urge to over-explain.</p>
      </section>
      <section class="list-stack list-stack--archive">
        ${mixes
          .map(
            (mix) => `<a class="archive-row archive-row--full" href="../mixes/${escapeHtml(mix.slug)}/">
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
  const highlightedSection = mix.highlightedTracks.length
    ? `<section class="section-block">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Highlights</p>
            <h2>Favorite tracks marked in the source</h2>
          </div>
        </div>
        <ul class="highlight-list">
          ${mix.highlightedTracks
            .map((track) => `<li>${escapeHtml(track.displayText || `${track.artist} - ${track.title}`)}</li>`)
            .join('')}
        </ul>
      </section>`
    : '';

  const trackSection = mix.tracklist.length
    ? `<section class="section-block">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Tracklist</p>
            <h2>Sequenced by hand</h2>
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

  const notesSection = mix.notes
    ? `<section class="section-block section-block--split">
        <div>
          <p class="eyebrow">Notes</p>
          <h2>What stayed worth saying</h2>
        </div>
        <div class="prose">${paragraphize(mix.notes)}</div>
      </section>`
    : '';

  const relatedNotesSection = `<section class="section-block section-block--split">
      <div>
        <p class="eyebrow">Related notes</p>
        <h2>Writing that points back to this mix</h2>
        <p class="supporting-copy">Notes can reference one or more mixes, so this section stays data-driven and only fills when those relationships exist.</p>
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
          <p class="eyebrow">Continue through the archive</p>
          <h2>Prev and next mix links</h2>
          <p class="supporting-copy">A mix detail page should feel connected to the rest of the run, not like a dead end.</p>
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
      ${notesSection}
      ${highlightedSection}
      ${trackSection}
      ${relatedNotesSection}
      ${navigationSection}
      ${renderResourceSection(mix)}`,
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
  const body = hasNotes
    ? `<section class="page-intro">
        <p class="eyebrow">Notes</p>
        <h1>Notebook fragments</h1>
        <p class="page-intro__copy">Small observations around sequencing, atmosphere, and the songs that took time to reveal themselves.</p>
      </section>
      <section class="notes-grid">
        ${notes
          .map(
            (note) => `<article class="note-card">
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

  copyDir(STATIC_DIR, path.join(DIST, 'assets'));

  writePage('index.html', renderHomePage({ mixes, notes, site }));
  writePage(path.join('archive', 'index.html'), renderArchivePage({ mixes }));
  writePage(path.join('about', 'index.html'), renderAboutPage({ site, about }));
  writePage(path.join('notes', 'index.html'), renderNotesPage({ notes }));

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
