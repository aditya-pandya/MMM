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
  fs.rmSync(dirPath, { recursive: true, force: true });
  ensureDir(dirPath);
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
      const links = mix.links && typeof mix.links === 'object' ? mix.links : {};

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
      };
    })
  );
}

function normalizeNotes(raw) {
  if (!raw) return [];
  const items = Array.isArray(raw) ? raw : Array.isArray(raw.notes) ? raw.notes : [];

  return items.map((note, index) => ({
    title: note.title || `Note ${index + 1}`,
    slug: note.slug || slugify(note.title || `note-${index + 1}`),
    date: note.date || note.published_at || '',
    excerpt: note.excerpt || note.summary || note.description || '',
    body: note.body || note.content || '',
    mixSlug: note.mixSlug || note.mix_slug || '',
    tags: Array.isArray(note.tags) ? note.tags : [],
  }));
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
    .map((mix) => {
      const downloadLink = mix.download?.url
        ? { [mix.download.label || 'Download']: mix.download.url }
        : {};

      return {
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
          ...downloadLink,
        },
      };
    });

  const fromDirect = Array.isArray(directMixes) ? directMixes : directMixes?.mixes || [];
  const fromArchive = Array.isArray(archiveIndex?.mixes) ? archiveIndex.mixes : [];
  const combined = [...fromDirect, ...fromArchive, ...publishedMixes, ...importedMixes];
  const deduped = Array.from(new Map(combined.map((mix) => [mix.slug || mix.id || mix.title, mix])).values());

  return normalizeMixes(deduped);
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

function renderLinkButtons(links) {
  const items = Object.entries(links).filter(([, href]) => typeof href === 'string' && href.trim());
  if (!items.length) return '';

  return `<div class="button-row">${items
    .map(([label, href]) => `<a class="button button--secondary" href="${escapeHtml(href)}">${escapeHtml(label.replace(/_/g, ' '))}</a>`)
    .join('')}</div>`;
}

function renderHomePage({ mixes, site }) {
  const featuredSlug = site.featuredMixSlug || site.featured_mix_slug;
  const featured = featuredSlug
    ? mixes.find((mix) => mix.slug === featuredSlug) || mixes[0]
    : mixes[0];
  const recent = featured ? mixes.filter((mix) => mix.slug !== featured.slug).slice(0, 4) : mixes.slice(0, 4);
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
                </div>
                <p>${escapeHtml(mix.excerpt)}</p>
              </a>`
            )
            .join('')}
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
    content: `${featureBlock}${recentBlock}${valuesBlock}`,
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
          </div>
          ${renderTagList(mix.tags)}
          <div class="button-row">
            <a class="button button--secondary" href="../../archive/">Back to archive</a>
          </div>
          ${renderLinkButtons(mix.links)}
        </div>
        ${renderCover(mix)}
      </section>
      ${notesSection}
      ${trackSection}`,
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
              ${note.mixSlug ? `<p class="note-card__link">Related mix: <a href="../mixes/${escapeHtml(note.mixSlug)}/">${escapeHtml(note.mixSlug)}</a></p>` : ''}
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
          <p>No notes data was found, so this page acts as a clean holding page. Add data/notes.json with an array of entries or an object containing a notes array, and the page will render them automatically.</p>
          <p>Expected fields are flexible: title, date, excerpt, body, tags, and an optional mixSlug if a note should point back to a specific mix.</p>
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

function writePage(relativePath, html) {
  const destination = path.join(DIST, relativePath);
  ensureDir(path.dirname(destination));
  fs.writeFileSync(destination, html);
}

function build() {
  resetDir(DIST);

  const siteSource = readJsonIfExists(path.join(DATA_DIR, 'site.json'), {});
  const about = readJsonIfExists(path.join(DATA_DIR, 'about.json'), {});
  const notesSource = readJsonIfExists(path.join(DATA_DIR, 'notes.json'), []);

  const site = {
    ...siteSource,
    title: siteSource.title || siteSource.site_title || 'Monday Music Mix',
    homeIntro: siteSource.homeIntro || siteSource.homepage_intro || '',
  };
  const mixes = loadMixes();
  const notes = normalizeNotes(notesSource);

  copyDir(STATIC_DIR, path.join(DIST, 'assets'));

  writePage('index.html', renderHomePage({ mixes, site }));
  writePage(path.join('archive', 'index.html'), renderArchivePage({ mixes }));
  writePage(path.join('about', 'index.html'), renderAboutPage({ site, about }));
  writePage(path.join('notes', 'index.html'), renderNotesPage({ notes }));

  for (const mix of mixes) {
    writePage(path.join('mixes', mix.slug, 'index.html'), renderMixPage({ mix }));
  }

  fs.writeFileSync(path.join(DIST, '.nojekyll'), '');

  console.log(`Built ${mixes.length} mix page(s) into ${path.relative(ROOT, DIST)}`);
}

build();
