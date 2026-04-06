const state = {
  config: null,
  bootstrap: null,
  selectedDraftSlug: null,
  selectedMixSlug: null,
  youtubeSelections: new Map(),
  bannerTimer: null,
};

const elements = {
  app: document.querySelector("#app"),
  authBadge: document.querySelector("#auth-badge"),
  authPanel: document.querySelector("#auth-panel"),
  authForm: document.querySelector("#auth-form"),
  authError: document.querySelector("#auth-error"),
  tokenInput: document.querySelector("#token-input"),
  logoutButton: document.querySelector("#logout-button"),
  previewOrigin: document.querySelector("#preview-origin"),
  statusBanner: document.querySelector("#status-banner"),
  statDrafts: document.querySelector("#stat-drafts"),
  statPublished: document.querySelector("#stat-published"),
  statNotes: document.querySelector("#stat-notes"),
  statYoutubeReview: document.querySelector("#stat-youtube-review"),
  validateButton: document.querySelector("#validate-button"),
  generateForm: document.querySelector("#generate-form"),
  generateDate: document.querySelector("#generate-date"),
  generateArtwork: document.querySelector("#generate-ai-artwork"),
  draftCount: document.querySelector("#draft-count"),
  mixCount: document.querySelector("#mix-count"),
  draftList: document.querySelector("#draft-list"),
  mixList: document.querySelector("#mix-list"),
  draftForm: document.querySelector("#draft-form"),
  draftEmpty: document.querySelector("#draft-empty"),
  draftTitle: document.querySelector("#draft-title"),
  draftTags: document.querySelector("#draft-tags"),
  draftSummary: document.querySelector("#draft-summary"),
  draftNotes: document.querySelector("#draft-notes"),
  draftFeatured: document.querySelector("#draft-featured"),
  draftStatus: document.querySelector("#draft-status"),
  trackList: document.querySelector("#track-list"),
  trackTemplate: document.querySelector("#track-template"),
  addTrackButton: document.querySelector("#add-track-button"),
  approveButton: document.querySelector("#approve-button"),
  releaseButton: document.querySelector("#release-button"),
  youtubeStatus: document.querySelector("#youtube-status"),
  youtubeSummary: document.querySelector("#youtube-summary"),
  youtubeEmbed: document.querySelector("#youtube-embed"),
  youtubeTrackList: document.querySelector("#youtube-track-list"),
  youtubeSyncButton: document.querySelector("#youtube-sync-button"),
  youtubeSaveButton: document.querySelector("#youtube-save-button"),
  previewList: document.querySelector("#preview-list"),
  logList: document.querySelector("#log-list"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = payload.error || `Request failed with ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function setBadge(label, variant = "muted") {
  elements.authBadge.className = `badge badge--${variant}`;
  elements.authBadge.textContent = label;
}

function setNotice(target, message, isError = false) {
  target.hidden = !message;
  target.textContent = message || "";
  target.className = isError ? "notice notice--error" : "notice notice--muted";
}

function flash(message, tone = "success", persist = false) {
  clearTimeout(state.bannerTimer);
  elements.statusBanner.hidden = !message;
  elements.statusBanner.textContent = message || "";
  elements.statusBanner.className = `status-banner status-banner--${tone}`;
  if (!message || persist) return;
  state.bannerTimer = window.setTimeout(() => {
    elements.statusBanner.hidden = true;
  }, 4200);
}

function readGenerateMode() {
  const checked = document.querySelector('input[name="generate-mode"]:checked');
  return checked ? checked.value : "local";
}

function scoreVariant(score) {
  const numeric = Number(score || 0);
  if (numeric >= 0.95) return "success";
  if (numeric > 0.8) return "muted";
  return "warning";
}

function renderButtonList(container, items, onClick, renderMeta, activeSlug) {
  container.innerHTML = "";
  for (const item of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `collection-item${activeSlug === item.slug ? " is-active" : ""}`;
    button.innerHTML = `
      <strong>${escapeHtml(item.title || item.label || item.slug)}</strong>
      <div class="collection-item__meta">
        <span class="badge badge--muted">${escapeHtml(item.slug || "item")}</span>
      </div>
      <div class="collection-item__detail">${escapeHtml(renderMeta(item))}</div>
    `;
    button.addEventListener("click", () => onClick(item));
    container.append(button);
  }

  if (!items.length) {
    container.innerHTML = '<div class="empty-state"><p class="empty-state__title">Nothing here yet</p><p>This list will fill as drafts and published mixes accumulate.</p></div>';
  }
}

function renderTracks(tracks) {
  elements.trackList.innerHTML = "";
  tracks.forEach((track, index) => {
    const fragment = elements.trackTemplate.content.cloneNode(true);
    const row = fragment.querySelector(".track-row");
    row.dataset.index = String(index);
    row.querySelector(".track-row__meta").textContent = `Track ${String(index + 1).padStart(2, "0")}`;
    row.querySelector('[data-field="artist"]').value = track.artist || "";
    row.querySelector('[data-field="title"]').value = track.title || "";
    row.querySelector('[data-field="why_it_fits"]').value = track.why_it_fits || "";
    row.querySelector('[data-role="remove-track"]').addEventListener("click", () => {
      row.remove();
      renumberTrackRows();
    });
    elements.trackList.append(fragment);
  });
}

function renumberTrackRows() {
  Array.from(elements.trackList.children).forEach((row, index) => {
    row.dataset.index = String(index);
    const meta = row.querySelector(".track-row__meta");
    if (meta) meta.textContent = `Track ${String(index + 1).padStart(2, "0")}`;
  });
}

function collectTrackRows() {
  return Array.from(elements.trackList.children).map((row) => ({
    artist: row.querySelector('[data-field="artist"]').value.trim(),
    title: row.querySelector('[data-field="title"]').value.trim(),
    why_it_fits: row.querySelector('[data-field="why_it_fits"]').value.trim(),
  }));
}

function currentDraftPayload() {
  return {
    title: elements.draftTitle.value.trim(),
    summary: elements.draftSummary.value.trim(),
    notes: elements.draftNotes.value.trim(),
    tags: elements.draftTags.value
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean),
    featured: elements.draftFeatured.checked,
    tracks: collectTrackRows(),
  };
}

function renderDraftDetail(draft) {
  state.selectedDraftSlug = draft.slug;
  elements.draftForm.hidden = false;
  elements.draftEmpty.hidden = true;
  elements.draftTitle.value = draft.title || "";
  elements.draftTags.value = (draft.tags || []).join(", ");
  elements.draftSummary.value = draft.summary || "";
  elements.draftNotes.value = draft.notes || "";
  elements.draftFeatured.checked = Boolean(draft.featured);
  elements.draftStatus.className = `badge ${draft.status === "approved" ? "badge--success" : "badge--muted"}`;
  elements.draftStatus.textContent = `${draft.status} · ${draft.slug}`;
  renderTracks(draft.tracks || []);
}

function renderPreviewRoutes(routes) {
  elements.previewList.innerHTML = "";
  routes.forEach((route) => {
    const wrapper = document.createElement("article");
    wrapper.className = "route-card";
    const previewLine = route.previewUrl
      ? `<a href="${escapeHtml(route.previewUrl)}" target="_blank" rel="noreferrer">${escapeHtml(route.previewUrl)}</a>`
      : `<code>${escapeHtml(route.sourcePath || "local source only")}</code>`;
    wrapper.innerHTML = `
      <strong>${escapeHtml(route.label)}</strong>
      <div class="route-card__detail">${escapeHtml(route.route || route.sourcePath || "n/a")}</div>
      <div class="route-card__detail">${previewLine}</div>
      <div class="route-card__detail">${route.built ? "dist ready" : "build missing"}${route.distPath ? ` · ${escapeHtml(route.distPath)}` : ""}</div>
    `;
    elements.previewList.append(wrapper);
  });
}

function renderLogs(logs) {
  elements.logList.innerHTML = "";
  if (!logs.length) {
    elements.logList.innerHTML = '<div class="empty-state"><p class="empty-state__title">No actions logged yet</p><p>Validation, generation, approvals, and releases will show up here for this session.</p></div>';
    return;
  }

  logs.forEach((entry) => {
    const item = document.createElement("article");
    item.className = "log-entry";
    item.innerHTML = `
      <div class="panel__header">
        <strong>${escapeHtml(entry.action)}</strong>
        <span class="badge ${entry.status === "ok" ? "badge--success" : "badge--danger"}">${escapeHtml(entry.status)}</span>
      </div>
      <div class="route-card__detail">${escapeHtml(entry.finishedAt)}</div>
      <div>${escapeHtml(entry.summary)}</div>
      <pre>${escapeHtml(entry.detail || "")}</pre>
    `;
    elements.logList.append(item);
  });
}

function renderBootstrap(bootstrap) {
  state.bootstrap = bootstrap;
  elements.previewOrigin.textContent = state.config?.previewOrigin || "http://127.0.0.1:3000";
  elements.draftCount.textContent = String(bootstrap.counts.drafts);
  elements.mixCount.textContent = String(bootstrap.counts.published);
  elements.statDrafts.textContent = String(bootstrap.counts.drafts);
  elements.statPublished.textContent = String(bootstrap.counts.published);
  elements.statNotes.textContent = String(bootstrap.counts.notes);
  elements.statYoutubeReview.textContent = String(bootstrap.counts.youtubeReview);

  renderButtonList(
    elements.draftList,
    bootstrap.drafts,
    async (draft) => {
      renderDraftDetail(await api(`/api/drafts/${draft.slug}`));
      renderBootstrap(state.bootstrap || bootstrap);
    },
    (draft) => `${draft.date} · ${draft.status} · ${draft.trackCount} tracks`,
    state.selectedDraftSlug
  );

  renderButtonList(
    elements.mixList,
    bootstrap.published,
    async (mix) => loadYoutubeState(mix.slug),
    (mix) => {
      const youtube = mix.youtube && mix.youtube.summary
        ? (mix.youtube.summary.requiresReview ? "review needed" : "audio-first queue ready")
        : "no saved state";
      return `${mix.publishedAt || "undated"} · ${youtube}`;
    },
    state.selectedMixSlug
  );

  renderPreviewRoutes(bootstrap.previewRoutes || []);
  renderLogs(bootstrap.logs || []);
}

async function refreshBootstrap() {
  const bootstrap = await api("/api/bootstrap");
  renderBootstrap(bootstrap);
  if (state.selectedDraftSlug) {
    renderDraftDetail(await api(`/api/drafts/${state.selectedDraftSlug}`));
  }
  if (state.selectedMixSlug) {
    await loadYoutubeState(state.selectedMixSlug);
  }
}

function renderYoutubeState(payload) {
  state.selectedMixSlug = payload.mix.slug;
  state.youtubeSelections = new Map();
  elements.youtubeSyncButton.disabled = false;
  elements.youtubeSaveButton.disabled = false;
  elements.youtubeStatus.className = "badge badge--muted";
  elements.youtubeStatus.textContent = payload.mix.slug;

  const summary = payload.state && payload.state.summary;
  if (!payload.exists) {
    elements.youtubeSummary.textContent = "No candidate file exists yet. Refresh candidates to create the review state.";
    elements.youtubeTrackList.innerHTML = "";
    elements.youtubeEmbed.hidden = true;
    elements.youtubeSaveButton.disabled = true;
    return;
  }

  const unresolved = summary ? summary.unresolvedTracks : "unknown";
  elements.youtubeSummary.textContent = summary && summary.requiresReview
    ? `${unresolved} track(s) still need review before MMM trusts the queue.`
    : "Every track is resolved. MMM will keep the queue audio-first in its own UI and link out honestly to YouTube.";

  const generatedEmbed = summary && summary.generatedEmbed;
  if (generatedEmbed) {
    elements.youtubeEmbed.hidden = false;
    elements.youtubeEmbed.innerHTML = `
      <strong>Audio-first queue ready</strong>
      <div class="route-card__detail">${escapeHtml(generatedEmbed.title || `Full mix queue for ${payload.mix.title}`)}</div>
      <div class="route-card__detail">${escapeHtml(generatedEmbed.embedLimitation || "YouTube does not expose a true audio-only iframe, so MMM stores this as an audio-first queue link.")}</div>
      <div class="button-row button-row--compact">
        <a class="button button--secondary" href="${escapeHtml(generatedEmbed.watchUrl || generatedEmbed.embedUrl || "#")}" target="_blank" rel="noreferrer">Open queue on YouTube</a>
      </div>
    `;
  } else {
    elements.youtubeEmbed.hidden = true;
    elements.youtubeEmbed.innerHTML = "";
  }

  elements.youtubeTrackList.innerHTML = "";
  (payload.state.tracks || []).forEach((track) => {
    const card = document.createElement("article");
    card.className = "youtube-track";
    const status = track.resolution && track.resolution.status ? track.resolution.status : "pending-review";
    const variant = status === "manual-selected" || status === "auto-resolved" ? "success" : "danger";
    card.innerHTML = `
      <div class="youtube-track__header">
        <div>
          <strong>${escapeHtml(track.displayText)}</strong>
          <div class="route-card__detail">Track ${track.position} · ${escapeHtml(track.query)}</div>
          <div class="route-card__detail">${escapeHtml(track.resolution?.reason || "")}</div>
        </div>
        <span class="badge badge--${variant}">${escapeHtml(status)}</span>
      </div>
    `;

    const candidates = document.createElement("div");
    candidates.className = "candidate-list";
    const selectedVideoId = track.resolution ? track.resolution.selectedVideoId : null;

    (track.candidates || []).forEach((candidate) => {
      const option = document.createElement("label");
      option.className = "candidate";
      const signalList = Array.isArray(candidate.signals) ? candidate.signals : [];
      option.innerHTML = `
        <div class="candidate__top">
          <div class="candidate__radio">
            <input type="radio" name="track-${track.position}" value="${escapeHtml(candidate.videoId)}" ${selectedVideoId === candidate.videoId ? "checked" : ""} />
            <div>
              <strong>${escapeHtml(candidate.title)}</strong>
              <div class="candidate__meta">
                <span class="badge badge--${scoreVariant(candidate.score)}">score ${escapeHtml(candidate.score)}</span>
                <span class="badge badge--muted">${escapeHtml(candidate.channel || "unknown channel")}</span>
              </div>
            </div>
          </div>
          <a href="${escapeHtml(candidate.url)}" target="_blank" rel="noreferrer">${escapeHtml(candidate.url)}</a>
        </div>
        <div class="candidate__signals">
          ${signalList.length
            ? signalList.map((signal) => `<span class="signal-chip">${escapeHtml(signal)}</span>`).join("")
            : '<span class="subtle">No scoring signals captured</span>'}
        </div>
      `;
      option.querySelector("input").addEventListener("change", () => {
        state.youtubeSelections.set(track.position, candidate.videoId);
      });
      candidates.append(option);
    });

    const clearButton = document.createElement("button");
    clearButton.type = "button";
    clearButton.className = "button button--ghost";
    clearButton.textContent = "Clear selection";
    clearButton.addEventListener("click", () => {
      state.youtubeSelections.set(track.position, null);
      candidates.querySelectorAll("input").forEach((input) => {
        input.checked = false;
      });
    });

    card.append(candidates, clearButton);
    elements.youtubeTrackList.append(card);
  });
}

async function loadYoutubeState(slug) {
  renderYoutubeState(await api(`/api/mixes/${slug}/youtube`));
  renderBootstrap(state.bootstrap || { counts: { drafts: 0, published: 0, notes: 0, youtubeReview: 0 }, drafts: [], published: [], previewRoutes: [], logs: [] });
}

async function initialize() {
  state.config = await api("/api/public-config");
  elements.previewOrigin.textContent = state.config.previewOrigin || "http://127.0.0.1:3000";

  if (state.config.authRequired) {
    try {
      await refreshBootstrap();
      setBadge("Unlocked", "success");
      elements.authPanel.hidden = true;
      elements.app.hidden = false;
      elements.logoutButton.hidden = false;
      return;
    } catch {
      setBadge("Token required", "danger");
      elements.authPanel.hidden = false;
      elements.logoutButton.hidden = true;
      return;
    }
  }

  setBadge(state.config.localOnlyNoToken ? "Local-only access" : "Unlocked", state.config.localOnlyNoToken ? "muted" : "success");
  elements.authPanel.hidden = true;
  elements.app.hidden = false;
  elements.logoutButton.hidden = state.config.localOnlyNoToken;
  await refreshBootstrap();
}

elements.authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/auth/token", {
      method: "POST",
      body: JSON.stringify({ token: elements.tokenInput.value }),
    });
    elements.authError.hidden = true;
    elements.authPanel.hidden = true;
    elements.app.hidden = false;
    elements.logoutButton.hidden = false;
    setBadge("Unlocked", "success");
    flash("Operator surface unlocked.", "success");
    await refreshBootstrap();
  } catch (error) {
    setNotice(elements.authError, error.message, true);
  }
});

elements.logoutButton.addEventListener("click", async () => {
  await api("/auth/logout", { method: "POST", body: "{}" });
  window.location.reload();
});

elements.generateForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/drafts/generate", {
      method: "POST",
      body: JSON.stringify({
        date: elements.generateDate.value || null,
        mode: readGenerateMode(),
        withAiArtwork: elements.generateArtwork.checked,
      }),
    });
    flash("Draft generation finished and local state refreshed.", "success");
    await refreshBootstrap();
  } catch (error) {
    flash(error.message, "error", true);
  }
});

elements.validateButton.addEventListener("click", async () => {
  try {
    await api("/api/validate", { method: "POST", body: "{}" });
    flash("Validation completed. Check the session log for details.", "info");
    await refreshBootstrap();
  } catch (error) {
    flash(error.message, "error", true);
  }
});

elements.draftForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.selectedDraftSlug) return;
  try {
    const payload = await api(`/api/drafts/${state.selectedDraftSlug}`, {
      method: "PUT",
      body: JSON.stringify(currentDraftPayload()),
    });
    renderDraftDetail(payload);
    flash(`Saved ${state.selectedDraftSlug}.`, "success");
    await refreshBootstrap();
  } catch (error) {
    flash(error.message, "error", true);
  }
});

elements.addTrackButton.addEventListener("click", () => {
  const currentTracks = collectTrackRows();
  currentTracks.push({ artist: "", title: "", why_it_fits: "" });
  renderTracks(currentTracks);
});

elements.approveButton.addEventListener("click", async () => {
  if (!state.selectedDraftSlug) return;
  const reviewer = window.prompt("Approve as", "");
  const note = window.prompt("Optional approval note", "");
  try {
    await api(`/api/drafts/${state.selectedDraftSlug}/approve`, {
      method: "POST",
      body: JSON.stringify({ by: reviewer, note }),
    });
    flash(`Approved ${state.selectedDraftSlug}.`, "success");
    await refreshBootstrap();
  } catch (error) {
    flash(error.message, "error", true);
  }
});

elements.releaseButton.addEventListener("click", async () => {
  if (!state.selectedDraftSlug) return;
  const feature = window.confirm("Feature this mix during release?");
  try {
    await api(`/api/drafts/${state.selectedDraftSlug}/release`, {
      method: "POST",
      body: JSON.stringify({ feature }),
    });
    flash(`Released ${state.selectedDraftSlug}.`, "success");
    await refreshBootstrap();
  } catch (error) {
    flash(error.message, "error", true);
  }
});

elements.youtubeSyncButton.addEventListener("click", async () => {
  if (!state.selectedMixSlug) return;
  try {
    renderYoutubeState(await api(`/api/mixes/${state.selectedMixSlug}/youtube/sync`, { method: "POST", body: "{}" }));
    flash(`Refreshed YouTube candidates for ${state.selectedMixSlug}.`, "info");
    await refreshBootstrap();
  } catch (error) {
    flash(error.message, "error", true);
  }
});

elements.youtubeSaveButton.addEventListener("click", async () => {
  if (!state.selectedMixSlug) return;
  try {
    const selections = Array.from(state.youtubeSelections.entries()).map(([position, selectedVideoId]) => ({
      position,
      selectedVideoId,
    }));
    renderYoutubeState(
      await api(`/api/mixes/${state.selectedMixSlug}/youtube`, {
        method: "PUT",
        body: JSON.stringify({ selections }),
      })
    );
    flash(`Saved YouTube selections for ${state.selectedMixSlug}.`, "success");
    await refreshBootstrap();
  } catch (error) {
    flash(error.message, "error", true);
  }
});

initialize().catch((error) => {
  setBadge("Boot failed", "danger");
  flash(error.message, "error", true);
});
