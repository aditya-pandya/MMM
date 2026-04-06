from __future__ import annotations

import contextlib
import json
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import approve_mix
import generate_ai_artwork
import generate_weekly_draft
import manage_artwork
import publish_mix
import release_weekly
import sync_youtube_matches
import validate_content
from mmm_common import (
    ROOT,
    ValidationError,
    ensure_kebab_case_slug,
    load_canonical_archive_mix_records,
    load_json,
    now_iso,
    validate_mix,
)


def atomic_dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        prefix=f".{path.stem}-",
        suffix=".tmp",
    ) as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError("tags must be an array")
    tags: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = str(item or "").strip()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        tags.append(normalized)
    return tags


def normalize_track_edits(tracks: Any, existing_tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(tracks, list) or not tracks:
        raise ValidationError("tracks must be a non-empty array")

    normalized_tracks: list[dict[str, Any]] = []
    for index, track in enumerate(tracks, start=1):
        if not isinstance(track, dict):
            raise ValidationError(f"track {index} must be an object")

        prior = existing_tracks[index - 1] if index - 1 < len(existing_tracks) and isinstance(existing_tracks[index - 1], dict) else {}
        cleaned = dict(prior)
        cleaned["artist"] = str(track.get("artist") or "").strip()
        cleaned["title"] = str(track.get("title") or "").strip()
        cleaned["why_it_fits"] = str(track.get("why_it_fits") or "").strip()

        if not cleaned["artist"]:
            raise ValidationError(f"track {index} artist must not be empty")
        if not cleaned["title"]:
            raise ValidationError(f"track {index} title must not be empty")
        if not cleaned["why_it_fits"]:
            raise ValidationError(f"track {index} why_it_fits must not be empty")

        normalized_tracks.append(cleaned)
    return normalized_tracks


@dataclass
class WorkflowLogEntry:
    id: int
    action: str
    started_at: str
    finished_at: str
    status: str
    summary: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "status": self.status,
            "summary": self.summary,
            "detail": self.detail,
        }


class OperatorService:
    def __init__(
        self,
        *,
        repo_root: Path = ROOT,
        preview_origin: str = "http://127.0.0.1:3000",
        log_limit: int = 40,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.data_dir = self.repo_root / "data"
        self.drafts_dir = self.data_dir / "drafts"
        self.published_dir = self.data_dir / "published"
        self.imported_dir = self.data_dir / "imported" / "mixes"
        self.notes_dir = self.data_dir / "notes"
        self.archive_dir = self.data_dir / "archive"
        self.youtube_dir = self.data_dir / "youtube"
        self.dist_dir = self.repo_root / "dist"
        self.preview_origin = preview_origin.rstrip("/")
        self.log_limit = log_limit
        self._log_lock = threading.Lock()
        self._logs: list[WorkflowLogEntry] = []
        self._next_log_id = 1

    @contextlib.contextmanager
    def _patched_repo_modules(self) -> Iterator[None]:
        media_dir = self.data_dir / "media"
        media_workspaces_dir = media_dir / "workspaces"
        artwork_registry_path = media_dir / "artwork-registry.json"
        patch_targets = [
            (generate_weekly_draft, "DRAFTS_DIR", self.drafts_dir),
            (generate_weekly_draft, "PUBLISHED_DIR", self.published_dir),
            (generate_weekly_draft, "NOTES_DIR", self.notes_dir),
            (generate_weekly_draft, "IMPORTED_MIXES_DIR", self.imported_dir),
            (generate_weekly_draft, "ARCHIVE_INDEX_PATH", self.archive_dir / "index.json"),
            (generate_weekly_draft, "SITE_PATH", self.data_dir / "site.json"),
            (generate_weekly_draft, "TASTE_PROFILE_PATH", self.data_dir / "taste-profile.json"),
            (publish_mix, "DRAFTS_DIR", self.drafts_dir),
            (publish_mix, "PUBLISHED_DIR", self.published_dir),
            (publish_mix, "ARCHIVE_INDEX_PATH", self.archive_dir / "index.json"),
            (publish_mix, "LEGACY_ARCHIVE_INDEX_PATH", self.data_dir / "archive-index.json"),
            (publish_mix, "MIXES_JSON_PATH", self.data_dir / "mixes.json"),
            (publish_mix, "SITE_PATH", self.data_dir / "site.json"),
            (sync_youtube_matches, "ROOT", self.repo_root),
            (sync_youtube_matches, "IMPORTED_MIXES_DIR", self.imported_dir),
            (sync_youtube_matches, "YOUTUBE_DIR", self.youtube_dir),
            (generate_ai_artwork, "ROOT", self.repo_root),
            (generate_ai_artwork, "DRAFTS_DIR", self.drafts_dir),
            (manage_artwork, "ROOT", self.repo_root),
            (manage_artwork, "MEDIA_DIR", media_dir),
            (manage_artwork, "MEDIA_WORKSPACES_DIR", media_workspaces_dir),
            (manage_artwork, "ARTWORK_REGISTRY_PATH", artwork_registry_path),
        ]
        originals: list[tuple[Any, str, Any]] = []
        try:
            for module, attribute, value in patch_targets:
                originals.append((module, attribute, getattr(module, attribute)))
                setattr(module, attribute, value)
            yield
        finally:
            for module, attribute, value in reversed(originals):
                setattr(module, attribute, value)

    def _relative_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.repo_root).as_posix()
        except ValueError:
            return path.resolve().as_posix()

    def _track_count(self, mix: dict[str, Any]) -> int:
        tracks = mix.get("tracks")
        return len(tracks) if isinstance(tracks, list) else 0

    def _youtube_state_path(self, slug: str) -> Path:
        return self.youtube_dir / f"{slug}.json"

    def _load_valid_draft(self, path: Path) -> dict[str, Any]:
        result = validate_mix(load_json(path))
        if result.flavor != "editorial":
            raise ValidationError(f"Expected draft/editorial mix content in {path}")
        payload = dict(result.mix)
        payload["_path"] = path.resolve()
        return payload

    def _load_published_mix(self, path: Path) -> dict[str, Any]:
        result = validate_mix(load_json(path))
        if result.flavor != "published":
            raise ValidationError(f"Expected published mix content in {path}")
        payload = dict(result.mix)
        payload["_path"] = path.resolve()
        return payload

    def resolve_draft_path(self, draft_arg: str) -> Path:
        candidate = Path(draft_arg)
        if candidate.exists():
            return candidate.resolve()
        slug = ensure_kebab_case_slug(draft_arg, "draft slug")
        draft_path = self.drafts_dir / f"{slug}.json"
        if draft_path.exists():
            return draft_path.resolve()
        raise FileNotFoundError(f"Draft not found: {draft_arg}")

    def resolve_canonical_mix_record(self, slug: str) -> dict[str, Any]:
        normalized_slug = ensure_kebab_case_slug(slug, "mix slug")
        records = load_canonical_archive_mix_records(
            published_dir=self.published_dir,
            imported_dir=self.imported_dir,
        )
        for record in records:
            if record["slug"] == normalized_slug:
                return record
        raise FileNotFoundError(f"Canonical mix not found: {normalized_slug}")

    def _build_draft_summary(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = Path(payload["_path"])
        return {
            "slug": payload["slug"],
            "title": payload["title"],
            "date": payload["date"],
            "status": payload["status"],
            "summary": payload["summary"],
            "notes": payload["notes"],
            "tags": payload.get("tags", []),
            "featured": bool(payload.get("featured")),
            "approval": payload.get("approval"),
            "trackCount": self._track_count(payload),
            "path": self._relative_path(path),
            "updatedAt": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
        }

    def _build_draft_detail(self, payload: dict[str, Any]) -> dict[str, Any]:
        summary = self._build_draft_summary(payload)
        summary["tracks"] = payload.get("tracks", [])
        return summary

    def _build_mix_summary(self, payload: dict[str, Any]) -> dict[str, Any]:
        slug = payload["slug"]
        youtube_path = self._youtube_state_path(slug)
        youtube_summary = None
        if youtube_path.exists():
            youtube_payload = load_json(youtube_path)
            if isinstance(youtube_payload, dict):
                youtube_summary = {
                    "path": self._relative_path(youtube_path),
                    "updatedAt": youtube_payload.get("updatedAt"),
                    "summary": youtube_payload.get("summary"),
                }
        return {
            "slug": slug,
            "title": payload.get("displayTitle") or payload["title"],
            "publishedAt": payload.get("publishedAt"),
            "summary": payload.get("summary"),
            "trackCount": self._track_count(payload),
            "path": self._relative_path(Path(payload["_path"])),
            "sourcePlatform": str(payload.get("source", {}).get("platform") or "").strip(),
            "youtube": youtube_summary,
        }

    def list_drafts(self, *, limit: int = 12) -> list[dict[str, Any]]:
        drafts: list[dict[str, Any]] = []
        if not self.drafts_dir.exists():
            return drafts
        for path in sorted(self.drafts_dir.glob("*.json")):
            drafts.append(self._load_valid_draft(path))
        drafts.sort(key=lambda item: (item.get("date") or "", item["slug"]), reverse=True)
        return [self._build_draft_summary(item) for item in drafts[:limit]]

    def list_published_mixes(self, *, limit: int = 12) -> list[dict[str, Any]]:
        mixes: list[dict[str, Any]] = []
        if not self.published_dir.exists():
            return mixes
        for path in sorted(self.published_dir.glob("*.json")):
            mixes.append(self._load_published_mix(path))
        mixes.sort(key=lambda item: (item.get("publishedAt") or item.get("date") or "", item["slug"]), reverse=True)
        return [self._build_mix_summary(item) for item in mixes[:limit]]

    def _load_note_summaries(self, *, limit: int = 4) -> list[dict[str, Any]]:
        notes: list[dict[str, Any]] = []
        if not self.notes_dir.exists():
            return notes
        for path in sorted(self.notes_dir.glob("*.json")):
            payload = load_json(path)
            if not isinstance(payload, dict):
                continue
            notes.append(
                {
                    "slug": str(payload.get("slug") or path.stem),
                    "title": str(payload.get("title") or path.stem),
                    "publishedAt": payload.get("publishedAt"),
                    "path": self._relative_path(path),
                }
            )
        notes.sort(key=lambda item: (item.get("publishedAt") or "", item["slug"]), reverse=True)
        return notes[:limit]

    def _build_preview_routes(self) -> list[dict[str, Any]]:
        routes = [
            {"label": "Home", "route": "/", "distPath": self.dist_dir / "index.html"},
            {"label": "Studio", "route": "/studio/", "distPath": self.dist_dir / "studio" / "index.html"},
        ]

        drafts: list[dict[str, Any]] = []
        if self.drafts_dir.exists():
            for path in sorted(self.drafts_dir.glob("*.json")):
                drafts.append(self._load_valid_draft(path))
        if drafts:
            drafts.sort(key=lambda item: (item.get("date") or "", item["slug"]), reverse=True)
            latest_draft = drafts[0]
            routes.append(
                {
                    "label": "Latest Draft JSON",
                    "route": None,
                    "distPath": None,
                    "sourcePath": self._relative_path(Path(latest_draft["_path"])),
                }
            )

        mixes = self.list_published_mixes(limit=1)
        if mixes:
            latest_mix = mixes[0]
            routes.append(
                {
                    "label": f"Latest Mix: {latest_mix['title']}",
                    "route": f"/mixes/{latest_mix['slug']}/",
                    "distPath": self.dist_dir / "mixes" / latest_mix["slug"] / "index.html",
                }
            )

        notes = self._load_note_summaries(limit=1)
        if notes:
            latest_note = notes[0]
            routes.append(
                {
                    "label": f"Latest Note: {latest_note['title']}",
                    "route": f"/notes/{latest_note['slug']}/",
                    "distPath": self.dist_dir / "notes" / latest_note["slug"] / "index.html",
                }
            )

        preview_records: list[dict[str, Any]] = []
        for route in routes:
            dist_path = route.get("distPath")
            record = {
                "label": route["label"],
                "route": route.get("route"),
                "sourcePath": route.get("sourcePath"),
                "previewUrl": None if not route.get("route") else f"{self.preview_origin}{route['route']}",
                "distPath": None if dist_path is None else self._relative_path(dist_path),
                "built": bool(dist_path and Path(dist_path).exists()),
            }
            preview_records.append(record)
        return preview_records

    def _add_log(self, *, action: str, status: str, summary: str, detail: str, started_at: str, finished_at: str) -> None:
        with self._log_lock:
            entry = WorkflowLogEntry(
                id=self._next_log_id,
                action=action,
                started_at=started_at,
                finished_at=finished_at,
                status=status,
                summary=summary,
                detail=detail,
            )
            self._next_log_id += 1
            self._logs.insert(0, entry)
            del self._logs[self.log_limit :]

    def _log_action(self, action: str, runner: Any) -> Any:
        started_at = now_iso()
        try:
            result = runner()
        except Exception as exc:
            self._add_log(
                action=action,
                status="error",
                summary=str(exc),
                detail=str(exc),
                started_at=started_at,
                finished_at=now_iso(),
            )
            raise

        summary = ""
        if isinstance(result, dict):
            summary = str(result.get("slug") or result.get("mixSlug") or result.get("draft") or result.get("status") or action)
            detail = json.dumps(result, indent=2)
        else:
            summary = action
            detail = str(result)

        self._add_log(
            action=action,
            status="ok",
            summary=summary,
            detail=detail,
            started_at=started_at,
            finished_at=now_iso(),
        )
        return result

    def logs(self) -> list[dict[str, Any]]:
        with self._log_lock:
            return [entry.to_dict() for entry in self._logs]

    def public_config(self) -> dict[str, Any]:
        return {
            "previewOrigin": self.preview_origin,
            "repoRoot": self.repo_root.as_posix(),
        }

    def bootstrap(self) -> dict[str, Any]:
        drafts = self.list_drafts(limit=10)
        mixes = self.list_published_mixes(limit=10)
        youtube_review = [
            mix
            for mix in mixes
            if mix.get("youtube", {}).get("summary", {}).get("requiresReview")
        ]
        return {
            "counts": {
                "drafts": len(list(self.drafts_dir.glob("*.json"))) if self.drafts_dir.exists() else 0,
                "published": len(list(self.published_dir.glob("*.json"))) if self.published_dir.exists() else 0,
                "notes": len(list(self.notes_dir.glob("*.json"))) if self.notes_dir.exists() else 0,
                "youtubeReview": len(youtube_review),
            },
            "drafts": drafts,
            "published": mixes,
            "notes": self._load_note_summaries(),
            "youtubeReview": youtube_review,
            "previewRoutes": self._build_preview_routes(),
            "logs": self.logs(),
        }

    def load_draft(self, slug: str) -> dict[str, Any]:
        path = self.resolve_draft_path(slug)
        return self._build_draft_detail(self._load_valid_draft(path))

    def save_draft(self, slug: str, edits: dict[str, Any]) -> dict[str, Any]:
        path = self.resolve_draft_path(slug)
        current = self._load_valid_draft(path)
        existing_tracks = current.get("tracks", []) if isinstance(current.get("tracks"), list) else []

        updated = dict(current)
        updated.pop("_path", None)
        updated["title"] = str(edits.get("title") or "").strip()
        updated["summary"] = str(edits.get("summary") or "").strip()
        updated["notes"] = str(edits.get("notes") or "").strip()
        updated["tags"] = normalize_tags(edits.get("tags"))
        updated["featured"] = bool(edits.get("featured"))
        updated["tracks"] = normalize_track_edits(edits.get("tracks"), existing_tracks)
        validated = validate_mix(updated)
        atomic_dump_json(path, validated.mix)
        payload = dict(validated.mix)
        payload["_path"] = path.resolve()
        return self._build_draft_detail(payload)

    def validate_repo(self) -> dict[str, Any]:
        report = validate_content.build_report(self.repo_root)
        return {
            "errors": report["errors"],
            "warnings": report["warnings"],
            "counts": report.get("counts", {}),
            "issues": report.get("issues", []),
        }

    def generate_draft(
        self,
        *,
        mix_date: str | None,
        mode: str,
        with_ai_artwork: bool,
        force: bool = False,
    ) -> dict[str, Any]:
        def runner() -> dict[str, Any]:
            preflight = self.validate_repo()
            if preflight["errors"]:
                raise ValidationError(
                    f"repository validation failed with {preflight['errors']} error(s); run python3 scripts/validate_content.py"
                )
            resolved_date = date.fromisoformat(mix_date) if mix_date else generate_weekly_draft.resolve_mix_date(None)
            with self._patched_repo_modules():
                output_path = generate_weekly_draft.generate_weekly_draft(
                    resolved_date,
                    mode=mode,
                    force=force,
                )
                artwork_result = None
                if with_ai_artwork:
                    artwork_result = generate_ai_artwork.generate_ai_artwork(str(output_path), force=force)
            payload = self._load_valid_draft(output_path)
            return {
                "draft": self._build_draft_detail(payload),
                "artwork": artwork_result,
                "validation": preflight,
            }

        return self._log_action("generate-draft", runner)

    def approve_draft(self, slug: str, *, approver: str | None, note: str | None) -> dict[str, Any]:
        path = self.resolve_draft_path(slug)

        def runner() -> dict[str, Any]:
            result = approve_mix.approve_mix(
                path,
                approver=approver,
                approval_note=note,
                repo_root=self.repo_root,
                validate_repo=True,
            )
            result["draft"] = self.load_draft(slug)
            return result

        return self._log_action("approve-draft", runner)

    def release_draft(self, slug: str, *, feature: bool) -> dict[str, Any]:
        path = self.resolve_draft_path(slug)

        def runner() -> dict[str, Any]:
            with self._patched_repo_modules():
                return release_weekly.release_mix(path, repo_root=self.repo_root, feature=feature)

        return self._log_action("release-draft", runner)

    def youtube_state(self, slug: str) -> dict[str, Any]:
        record = self.resolve_canonical_mix_record(slug)
        state_path = self._youtube_state_path(record["slug"])
        state = load_json(state_path) if state_path.exists() else None
        return {
            "mix": {
                "slug": record["slug"],
                "title": record["mix"].get("displayTitle") or record["mix"].get("title"),
                "sourcePath": self._relative_path(record["path"]),
                "sourceName": record["sourceName"],
                "sourcePlatform": str(record["mix"].get("source", {}).get("platform") or "").strip(),
                "trackCount": self._track_count(record["mix"]),
            },
            "state": state,
            "statePath": self._relative_path(state_path),
            "exists": state_path.exists(),
        }

    def sync_youtube_state(self, slug: str) -> dict[str, Any]:
        record = self.resolve_canonical_mix_record(slug)

        def runner() -> dict[str, Any]:
            with self._patched_repo_modules():
                payload = sync_youtube_matches.sync_mix(record["path"])
            return self.youtube_state(payload["mixSlug"])

        return self._log_action("sync-youtube", runner)

    def update_youtube_selections(self, slug: str, selections: list[dict[str, Any]]) -> dict[str, Any]:
        normalized_slug = ensure_kebab_case_slug(slug, "mix slug")
        state_path = self._youtube_state_path(normalized_slug)
        if not state_path.exists():
            raise FileNotFoundError(f"YouTube state not found for {normalized_slug}; sync candidates first.")

        payload = load_json(state_path)
        if not isinstance(payload, dict):
            raise ValidationError("YouTube state must be an object")

        selection_by_position: dict[int, str | None] = {}
        for item in selections:
            if not isinstance(item, dict):
                raise ValidationError("each selection must be an object")
            position = item.get("position")
            if not isinstance(position, int) or isinstance(position, bool) or position < 1:
                raise ValidationError("selection position must be a positive integer")
            video_id = item.get("selectedVideoId")
            normalized_video_id = None if video_id is None else str(video_id).strip()
            if normalized_video_id == "":
                normalized_video_id = None
            selection_by_position[position] = normalized_video_id

        mix_record = self.resolve_canonical_mix_record(normalized_slug)
        track_states = payload.get("tracks")
        if not isinstance(track_states, list):
            raise ValidationError("YouTube state tracks must be an array")

        updated_tracks: list[dict[str, Any]] = []
        for track in track_states:
            if not isinstance(track, dict):
                raise ValidationError("YouTube state tracks must contain objects")
            position = int(track.get("position"))
            candidate_video_id = selection_by_position.get(position, "__leave__")
            updated_track = dict(track)
            candidates = updated_track.get("candidates") if isinstance(updated_track.get("candidates"), list) else []

            if candidate_video_id == "__leave__":
                updated_tracks.append(updated_track)
                continue

            if candidate_video_id is None:
                updated_track["resolution"] = {
                    "status": "pending-review" if candidates else "no-candidate",
                    "selectedVideoId": None,
                    "confidenceScore": 0.0,
                    "reason": "Selection cleared by the operator. Review is still required before MMM can trust the queue.",
                    "holdbackReason": "manual-clear",
                }
                updated_tracks.append(updated_track)
                continue

            matched_candidate = next(
                (candidate for candidate in candidates if str(candidate.get("videoId") or "").strip() == candidate_video_id),
                None,
            )
            if matched_candidate is None:
                raise ValidationError(f"track {position} candidate '{candidate_video_id}' is not in the saved candidate set")

            updated_track["resolution"] = {
                "status": "manual-selected",
                "selectedVideoId": candidate_video_id,
                "confidenceScore": round(max(float(matched_candidate.get("score") or 0.0), 0.999), 3),
                "reason": "Human-reviewed against the stored candidate set and selected explicitly.",
                "holdbackReason": None,
            }
            updated_tracks.append(updated_track)

        sync_youtube_matches.apply_duplicate_holdbacks(updated_tracks)

        resolved_tracks = sum(
            1
            for track in updated_tracks
            if str(track.get("resolution", {}).get("selectedVideoId") or "").strip()
            and track.get("resolution", {}).get("status") in {"auto-resolved", "manual-selected"}
        )
        unresolved_tracks = len(updated_tracks) - resolved_tracks
        generated_embed = (
            sync_youtube_matches.build_generated_embed(mix_record["mix"], updated_tracks)
            if unresolved_tracks == 0
            else None
        )

        payload["updatedAt"] = now_iso()
        payload["tracks"] = updated_tracks
        payload["summary"] = {
            "totalTracks": len(updated_tracks),
            "resolvedTracks": resolved_tracks,
            "unresolvedTracks": unresolved_tracks,
            "requiresReview": unresolved_tracks > 0,
            "generatedEmbed": generated_embed,
        }
        atomic_dump_json(state_path, payload)
        return self.youtube_state(normalized_slug)
