from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "listening-provider-catalog.json"
SUPPORTED_LISTENING_KINDS = {"listen", "playlist", "album", "track", "set", "embed"}

PROVIDER_CONTAINER_KEYS = {"providers", "links", "providerlinks", "streaming", "entries", "items", "sources"}
EMBED_CONTAINER_KEYS = {"embeds", "embed", "players", "iframes"}
META_KEYS = {"url", "href", "src", "provider", "label", "title", "kind", "note", "summary", "intro", "description"}


def normalize_listening_key(value: Any) -> str:
    return "".join(character for character in str(value or "").strip().lower() if character.isalnum())


def load_provider_catalog(root: Path | None = None) -> dict[str, Any]:
    catalog_path = (root / "data" / "listening-provider-catalog.json") if root else CATALOG_PATH
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    providers = payload.get("providers")
    if not isinstance(providers, dict):
        raise ValueError("listening provider catalog must expose a providers object")
    return payload


@lru_cache(maxsize=1)
def load_default_provider_catalog() -> dict[str, Any]:
    return load_provider_catalog()


def provider_label_from_key(value: Any, catalog: dict[str, Any] | None = None) -> str:
    raw = str(value or "").strip()
    normalized = normalize_listening_key(raw)
    if not normalized:
        return ""
    providers = (catalog or load_default_provider_catalog()).get("providers", {})
    provider = providers.get(normalized)
    if isinstance(provider, dict) and str(provider.get("label") or "").strip():
        return str(provider["label"]).strip()
    return " ".join(part for part in raw.replace("_", " ").replace("-", " ").split() if part).title()


def is_http_url(value: Any) -> bool:
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def parse_url_parts(value: Any) -> tuple[str, str]:
    parsed = urlparse(str(value or "").strip())
    return parsed.netloc.lower(), parsed.path.lower()


def infer_provider_from_url(value: Any, catalog: dict[str, Any] | None = None) -> str:
    host, _ = parse_url_parts(value)
    providers = (catalog or load_default_provider_catalog()).get("providers", {})
    for key, provider in providers.items():
        if host_matches_provider(host, provider):
            return str(provider.get("label") or provider_label_from_key(key, catalog)).strip()
    return "Listening link"


def infer_provider_kind(value: Any) -> str:
    href = str(value or "").strip().lower()
    if not href:
        return "listen"
    if "/embed/" in href or "/embed?" in href or "youtube.com/embed/" in href or "/oembed" in href:
        return "embed"
    if "/playlist/" in href or "videoseries" in href:
        return "playlist"
    if "/album/" in href:
        return "album"
    if "/track/" in href or "/song/" in href:
        return "track"
    if "/sets/" in href:
        return "set"
    return "listen"


def youtube_list_id(value: Any) -> str:
    parsed = urlparse(str(value or "").strip())
    return str(parse_qs(parsed.query).get("list", [""])[0]).strip()


def host_matches_provider(host: str, provider: dict[str, Any]) -> bool:
    host = host.strip().lower()
    if not host or not isinstance(provider, dict):
        return False

    exact_hosts = {str(item).strip().lower() for item in provider.get("trustedHosts", []) if str(item).strip()}
    suffixes = {str(item).strip().lower() for item in provider.get("trustedHostSuffixes", []) if str(item).strip()}

    if host in exact_hosts:
        return True
    return any(host.endswith(suffix) for suffix in suffixes)


def embed_matches_provider(host: str, path: str, provider: dict[str, Any]) -> bool:
    host = host.strip().lower()
    path = path.strip().lower()
    if not host or not isinstance(provider, dict):
        return False

    exact_hosts = {str(item).strip().lower() for item in provider.get("embedHosts", []) if str(item).strip()}
    suffixes = {str(item).strip().lower() for item in provider.get("embedHostSuffixes", []) if str(item).strip()}
    path_hints = [str(item).strip().lower() for item in provider.get("embedPathHints", []) if str(item).strip()]

    host_ok = host in exact_hosts or any(host.endswith(suffix) for suffix in suffixes)
    if not host_ok:
        return False
    if not path_hints:
        return True
    return any(hint in path for hint in path_hints)


def collect_listening_entries(
    raw_entries: list[Any],
    catalog: dict[str, Any],
    mode: str = "provider",
    start_mode: str | None = None,
) -> tuple[list[dict[str, str]], list[str]]:
    items: list[dict[str, str]] = []
    warnings: list[str] = []
    start_mode = start_mode or mode

    def visit(value: Any, current_mode: str, provider_hint: str) -> None:
        if value is None:
            return

        if isinstance(value, list):
            for entry in value:
                visit(entry, current_mode, provider_hint)
            return

        if isinstance(value, str):
            url = value.strip()
            if not url:
                return
            if not is_http_url(url):
                warnings.append(f"{current_mode} entry uses a non-http(s) URL: {url}")
                return

            inferred_provider = infer_provider_from_url(url, catalog)
            provider_source = "key" if provider_hint else "url-inferred"
            if current_mode == "embed":
                items.append(
                    {
                        "mode": current_mode,
                        "provider": provider_hint or inferred_provider,
                        "providerSource": provider_source,
                        "title": "",
                        "url": url,
                        "kind": "embed",
                        "note": "",
                    }
                )
                return

            items.append(
                {
                    "mode": current_mode,
                    "provider": provider_hint or inferred_provider,
                    "providerSource": provider_source,
                    "label": "",
                    "url": url,
                    "kind": infer_provider_kind(url),
                    "note": "",
                }
            )
            return

        if not isinstance(value, dict):
            warnings.append(f"{current_mode} entry should be an object, array, or URL string")
            return

        url = str(value.get("url") or value.get("href") or value.get("src") or "").strip()
        explicit_provider = str(value.get("provider") or "").strip()
        provider_value = explicit_provider or provider_hint or infer_provider_from_url(url, catalog)
        provider_source = "field" if explicit_provider else "key" if provider_hint else "url-inferred"
        has_entry_shape = any(str(value.get(key, "")).strip() for key in ("provider", "label", "title", "kind", "note", "summary"))
        if url:
            if not is_http_url(url):
                warnings.append(f"{current_mode} entry uses a non-http(s) URL: {url}")
            elif current_mode == "embed":
                items.append(
                    {
                        "mode": current_mode,
                        "provider": provider_value,
                        "providerSource": provider_source,
                        "title": str(value.get("title") or value.get("label") or "").strip(),
                        "url": url,
                        "kind": "embed",
                        "note": str(value.get("note") or value.get("summary") or "").strip(),
                    }
                )
            else:
                items.append(
                    {
                        "mode": current_mode,
                        "provider": provider_value,
                        "providerSource": provider_source,
                        "label": str(value.get("label") or value.get("title") or "").strip(),
                        "url": url,
                        "kind": str(value.get("kind") or infer_provider_kind(url)).strip(),
                        "note": str(value.get("note") or value.get("summary") or "").strip(),
                    }
                )
        elif has_entry_shape:
            warnings.append(f"{current_mode} entry is missing a valid http(s) URL")

        for key, child in value.items():
            normalized_key = normalize_listening_key(key)
            if normalized_key in META_KEYS or child is None:
                continue
            next_mode = "embed" if normalized_key in EMBED_CONTAINER_KEYS else "provider" if normalized_key in PROVIDER_CONTAINER_KEYS else current_mode
            next_hint = provider_hint if normalized_key in PROVIDER_CONTAINER_KEYS | EMBED_CONTAINER_KEYS else provider_label_from_key(key, catalog) or provider_hint
            visit(child, next_mode, next_hint)

    for entry in raw_entries:
        visit(entry, start_mode, "")

    deduped: dict[tuple[str, str, str], dict[str, str]] = {}
    for item in items:
        if item["mode"] != mode:
            continue
        provider = str(item.get("provider") or infer_provider_from_url(item.get("url"), catalog)).strip() or ("Embed" if mode == "embed" else "Listening link")
        url = str(item.get("url") or "").strip()
        kind = str(item.get("kind") or ("embed" if mode == "embed" else "listen")).strip()
        provider_source = str(item.get("providerSource") or "url-inferred").strip() or "url-inferred"
        key = (provider, url, kind)
        deduped.setdefault(
            key,
            {
                **item,
                "provider": provider,
                "providerSource": provider_source,
                "url": url,
                "kind": kind,
            },
        )

    return list(deduped.values()), warnings


def classify_surface(
    entry: dict[str, Any],
    mode: str,
    catalog: dict[str, Any],
    provider_urls_by_key: dict[str, set[str]] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    provider_urls_by_key = provider_urls_by_key or {}
    semantics = "embedded-preview" if mode == "embed" else "external-link"
    provider_name = str(entry.get("provider") or "").strip() or infer_provider_from_url(entry.get("url"), catalog)
    provider_key = normalize_listening_key(provider_name)
    provider_catalog = catalog.get("providers", {}).get(provider_key)
    url = str(entry.get("url") or "").strip()
    kind = str(entry.get("kind") or ("embed" if mode == "embed" else infer_provider_kind(url))).strip().lower()
    provider_source = str(entry.get("providerSource") or "url-inferred").strip() or "url-inferred"
    warnings: list[str] = []
    confidence_level = "uncertain"
    confidence_reason = "This surface is kept as a lead, not a verified listening mirror."

    if not is_http_url(url):
      warnings.append(f"{mode} '{provider_name}' is missing a valid http(s) URL")
    elif provider_source == "url-inferred":
      warnings.append(f"{mode} '{provider_name}' only infers its provider from the URL and stays uncertain until curated explicitly")
    elif not isinstance(provider_catalog, dict):
      warnings.append(f"{mode} '{provider_name}' is not in the curated listening provider catalog")
    else:
      host, path = parse_url_parts(url)
      if mode == "provider":
          valid_provider = True
          if kind not in SUPPORTED_LISTENING_KINDS - {"embed"}:
              warnings.append(f"provider '{provider_name}' uses unsupported kind '{entry.get('kind')}'")
              valid_provider = False
          if not host_matches_provider(host, provider_catalog):
              warnings.append(f"provider '{provider_name}' URL does not match the curated host list: {url}")
              valid_provider = False
          if valid_provider:
              supported_kinds = {str(item).strip().lower() for item in provider_catalog.get("supportedKinds", []) if str(item).strip()}
              if supported_kinds and kind not in supported_kinds:
                  warnings.append(f"provider '{provider_name}' kind '{kind}' is outside the curated support list")
              else:
                  confidence_level = "trusted-link-only"
                  confidence_reason = "Provider label, URL, and link shape match the curated listening data."
      else:
          valid_embed = True
          if not embed_matches_provider(host, path, provider_catalog):
              warnings.append(f"embed '{provider_name}' is not using a curated provider/embed URL pair: {url}")
              valid_embed = False
          if valid_embed:
              expected_provider_urls = provider_urls_by_key.get(provider_key, set())
              if provider_key == "youtube" and expected_provider_urls:
                  embed_list_id = youtube_list_id(url)
                  known_ids = {youtube_list_id(provider_url) for provider_url in expected_provider_urls if youtube_list_id(provider_url)}
                  if embed_list_id and known_ids and embed_list_id not in known_ids:
                      warnings.append(f"embed '{provider_name}' playlist does not match the curated provider URL")
                  else:
                      confidence_level = "trusted-embed-ready"
                      confidence_reason = "Provider label and embed URL match the curated playback data."
              else:
                  confidence_level = "trusted-embed-ready"
                  confidence_reason = "Provider label and embed URL match the curated playback data."

    normalized = {
        **entry,
        "provider": provider_name,
        "providerKey": provider_key,
        "providerSource": provider_source,
        "kind": kind,
        "semantics": semantics,
        "confidenceLevel": confidence_level,
        "confidenceReason": confidence_reason,
    }
    return normalized, warnings


def normalize_published_listening(mix: dict[str, Any], catalog: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    listening = mix.get("listening")
    warnings: list[str] = []

    if listening is not None and not isinstance(listening, dict):
        return {
            "intro": "",
            "providers": [],
            "embeds": [],
            "summary": {
                "trustedLinkCount": 0,
                "trustedEmbedCount": 0,
                "uncertainCount": 0,
                "surfaceCount": 0,
            },
        }, ["listening must be an object when present"]

    listening_obj = listening if isinstance(listening, dict) else {}
    provider_roots = [
        listening_obj.get("providers"),
        listening_obj.get("links"),
        mix.get("providers"),
        mix.get("providerLinks"),
        mix.get("streaming"),
    ]
    embed_roots = [
        listening_obj.get("embeds"),
        mix.get("embeds"),
    ]

    providers, provider_warnings = collect_listening_entries(provider_roots, catalog, "provider", "provider")
    embeds_from_providers, embed_from_provider_warnings = collect_listening_entries(provider_roots, catalog, "embed", "provider")
    embeds, embed_warnings = collect_listening_entries(embed_roots, catalog, "embed", "embed")
    warnings.extend(provider_warnings)
    warnings.extend(embed_from_provider_warnings)
    warnings.extend(embed_warnings)

    provider_urls_by_key: dict[str, set[str]] = {}
    normalized_providers: list[dict[str, Any]] = []
    for provider in providers:
        normalized, entry_warnings = classify_surface(provider, "provider", catalog)
        warnings.extend(entry_warnings)
        normalized_providers.append(normalized)
        if normalized["confidenceLevel"] == "trusted-link-only" and normalized["providerKey"]:
            provider_urls_by_key.setdefault(normalized["providerKey"], set()).add(normalized["url"])

    all_embeds = list({(entry["provider"], entry["url"]): entry for entry in [*embeds_from_providers, *embeds]}.values())
    normalized_embeds: list[dict[str, Any]] = []
    for embed in all_embeds:
        normalized, entry_warnings = classify_surface(embed, "embed", catalog, provider_urls_by_key)
        warnings.extend(entry_warnings)
        normalized_embeds.append(normalized)

    trusted_link_count = sum(1 for entry in normalized_providers if entry["confidenceLevel"] == "trusted-link-only")
    trusted_embed_count = sum(1 for entry in normalized_embeds if entry["confidenceLevel"] == "trusted-embed-ready")
    uncertain_count = sum(1 for entry in [*normalized_providers, *normalized_embeds] if entry["confidenceLevel"] == "uncertain")

    return {
        "intro": str(listening_obj.get("intro") or listening_obj.get("summary") or mix.get("listeningIntro") or "").strip(),
        "providers": normalized_providers,
        "embeds": normalized_embeds,
        "summary": {
            "trustedLinkCount": trusted_link_count,
            "trustedEmbedCount": trusted_embed_count,
            "uncertainCount": uncertain_count,
            "surfaceCount": len(normalized_providers) + len(normalized_embeds),
        },
    }, list(dict.fromkeys(warnings))
