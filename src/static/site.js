function normalizeDiscoveryText(value) {
  return String(value || '')
    .toLowerCase()
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

function matchesFilter(item, filterValue) {
  if (!filterValue || filterValue === 'all') return true;

  const [kind, rawValue] = filterValue.split(':');
  const value = String(rawValue || '').trim().toLowerCase();

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
});
