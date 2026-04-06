const state = {
  config: null,
  bootstrap: null,
  selectedDraftSlug: null,
  selectedMixSlug: null,
  youtubeSelections: new Map(),
};

const elements = {
  app: document.querySelector("#app"),
  authBadge: document.querySelector("#auth-badge"),
  authPanel: document.querySelector("#auth-panel"),
  authForm: document.querySelector("#auth-form"),
  authError: document.querySelector("#auth-error"),
  tokenInput: document.querySelector("#token-input"),
  logoutButton: document.querySelector("#logout-button"),
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

function setBadge(label, variant = "muted") {
  elements.authBadge.className = `pill pill--${variant}`;
  elements.authBadge.textContent = label;
}

function setNotice(target, message, isError = false) {
  target.hidden = !message;
  target.textContent = message || "";
  target.className = isError ? "notice notice--error" : "notice notice--muted";
}

function renderButtonList(container, items, onClick, renderMeta) {
  container.innerHTML = "";
  for (const item of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button button--ghost list-item";
    button.innerHTML = `
      <strong>${escapeHtml(item.title || item.label || item.slug)}</strong>
      <div class="subtle">${escapeHtml(renderMeta(item))}</div>
    `;
    button.addEventListener("click", () => onClick(item));
    container.append(button);
  }
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function readGenerateMode() {
  const checked = document.querySelector('input[name="generate-mode"]:checked');
  return checked ? checked.value : "local";
}

function renderTracks(tracks) {
  elements.trackList.innerHTML = "";
  tracks.forEach((track, index) => {
    const fragment = elements.trackTemplate.content.cloneNode(true);
    const row = fragment.querySelector(".track-row");
    row.dataset.index = String(index);
    row.querySelector(".track-row__meta").textContent = `Track ${index + 1}`;
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
    if (meta) meta.textContent = `Track ${index + 1}`;
  });
}

function collectTrackRows() {
  return Array.from(elements.trackList.children).map((row) => ({
    artist: row.querySelector('[data-field="artist"]').value.trim(),
    title: row.querySelector('[data-field="title"]').value.trim(),
    why_it_fits: row.querySelector('[data-field="why_it_fits"]').value.trim(),
  }));
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
  elements.draftStatus.className = `pill ${draft.status === "approved" ? "pill--success" : "pill--muted"}`;
  elements.draftStatus.textContent = `${draft.status} · ${draft.slug}`;
  renderTracks(draft.tracks || []);
}

function renderPreviewRoutes(routes) {
  elements.previewList.innerHTML = "";
  routes.forEach((route) => {
    const wrapper = document.createElement("article");
    wrapper.className = "list-item";
    const previewLine = route.previewUrl
      ? `<a href="${escapeHtml(route.previewUrl)}" target="_blank" rel="noreferrer">${escapeHtml(route.previewUrl)}</a>`
      : `<span>${escapeHtml(route.sourcePath || "local source only")}</span>`;
    wrapper.innerHTML = `
      <strong>${escapeHtml(route.label)}</strong>
      <div class="subtle">${escapeHtml(route.route || route.sourcePath || "n/a")}</div>
      <div>${previewLine}</div>
      <div class="subtle">${route.built ? "dist ready" : "build missing"}${route.distPath ? ` · ${escapeHtml(route.distPath)}` : ""}</div>
    `;
    elements.previewList.append(wrapper);
  });
}

function renderLogs(logs) {
  elements.logList.innerHTML = "";
  if (!logs.length) {
    elements.logList.innerHTML = '<div class="empty-state">Actions you run here will show up as a short session log.</div>';
    return;
  }
  logs.forEach((entry) => {
    const item = document.createElement("article");
    item.className = "log-entry";
    item.innerHTML = `
      <div class="panel__header">
        <strong>${escapeHtml(entry.action)}</strong>
        <span class="pill ${entry.status === "ok" ? "pill--success" : "pill--danger"}">${escapeHtml(entry.status)}</span>
      </div>
      <div class="subtle">${escapeHtml(entry.finishedAt)}</div>
      <div>${escapeHtml(entry.summary)}</div>
      <pre>${escapeHtml(entry.detail || "")}</pre>
    `;
    elements.logList.append(item);
  });
}

function renderBootstrap(bootstrap) {
  state.bootstrap = bootstrap;
  elements.draftCount.textContent = String(bootstrap.counts.drafts);
  elements.mixCount.textContent = String(bootstrap.counts.published);
  renderButtonList(
    elements.draftList,
    bootstrap.drafts,
    async (draft) => renderDraftDetail(await api(`/api/drafts/${draft.slug}`)),
    (draft) => `${draft.date} · ${draft.status} · ${draft.trackCount} tracks`
  );
  renderButtonList(
    elements.mixList,
    bootstrap.published,
    async (mix) => loadYoutubeState(mix.slug),
    (mix) => {
      const youtube = mix.youtube && mix.youtube.summary
        ? (mix.youtube.summary.requiresReview ? "YouTube review needed" : "YouTube resolved")
        : "No saved YouTube state";
      return `${mix.publishedAt || "undated"} · ${youtube}`;
    }
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

function renderYoutubeState(payload) {
  state.selectedMixSlug = payload.mix.slug;
  state.youtubeSelections = new Map();
  elements.youtubeSyncButton.disabled = false;
  elements.youtubeSaveButton.disabled = false;
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
    ? `${unresolved} track(s) still need explicit review before MMM can trust the queue.`
    : "Every track is resolved. The generated embed queue is ready.";

  const generatedEmbed = summary && summary.generatedEmbed;
  if (generatedEmbed) {
    elements.youtubeEmbed.hidden = false;
    elements.youtubeEmbed.innerHTML = `
      <strong>Generated embed ready</strong>
      <div><a href="${escapeHtml(generatedEmbed.embedUrl)}" target="_blank" rel="noreferrer">${escapeHtml(generatedEmbed.embedUrl)}</a></div>
      <div class="subtle">${escapeHtml(generatedEmbed.watchUrl || "")}</div>
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
    card.innerHTML = `
      <div class="youtube-track__header">
        <div>
          <strong>${escapeHtml(track.displayText)}</strong>
          <div class="subtle">Track ${track.position} · ${escapeHtml(track.query)}</div>
        </div>
        <span class="pill ${status === "manual-selected" || status === "auto-resolved" ? "pill--success" : "pill--danger"}">${escapeHtml(status)}</span>
      </div>
    `;
    const candidates = document.createElement("div");
    candidates.className = "stack";
    const selectedVideoId = track.resolution ? track.resolution.selectedVideoId : null;
    (track.candidates || []).forEach((candidate) => {
      const option = document.createElement("label");
      option.className = "candidate";
      option.innerHTML = `
        <div>
          <input type="radio" name="track-${track.position}" value="${escapeHtml(candidate.videoId)}" ${selectedVideoId === candidate.videoId ? "checked" : ""} />
          <strong>${escapeHtml(candidate.title)}</strong>
        </div>
        <div class="subtle">${escapeHtml(candidate.channel || "unknown channel")} · score ${escapeHtml(candidate.score)}</div>
        <a href="${escapeHtml(candidate.url)}" target="_blank" rel="noreferrer">${escapeHtml(candidate.url)}</a>
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
}

async function initialize() {
  state.config = await api("/api/public-config");
  if (state.config.authRequired) {
    try {
      await refreshBootstrap();
      setBadge("Unlocked", "success");
      elements.authPanel.hidden = true;
      elements.app.hidden = false;
      elements.logoutButton.hidden = false;
      return;
    } catch (error) {
      setBadge("Token required", "danger");
      elements.authPanel.hidden = false;
      elements.logoutButton.hidden = true;
      return;
    }
  }

  setBadge(state.config.localOnlyNoToken ? "Local-only, no token" : "Unlocked", state.config.localOnlyNoToken ? "muted" : "success");
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
    await refreshBootstrap();
  } catch (error) {
    alert(error.message);
  }
});

elements.validateButton.addEventListener("click", async () => {
  try {
    await api("/api/validate", { method: "POST", body: "{}" });
    await refreshBootstrap();
  } catch (error) {
    alert(error.message);
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
    await refreshBootstrap();
  } catch (error) {
    alert(error.message);
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
    await refreshBootstrap();
  } catch (error) {
    alert(error.message);
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
    await refreshBootstrap();
  } catch (error) {
    alert(error.message);
  }
});

elements.youtubeSyncButton.addEventListener("click", async () => {
  if (!state.selectedMixSlug) return;
  try {
    renderYoutubeState(await api(`/api/mixes/${state.selectedMixSlug}/youtube/sync`, { method: "POST", body: "{}" }));
    await refreshBootstrap();
  } catch (error) {
    alert(error.message);
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
    await refreshBootstrap();
  } catch (error) {
    alert(error.message);
  }
});

initialize().catch((error) => {
  setBadge("Boot failed", "danger");
  alert(error.message);
});
