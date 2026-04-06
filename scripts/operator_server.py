from __future__ import annotations

import argparse
import hmac
import http.cookies
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mmm_common import ValidationError
from operator_workflow import OperatorService

STATIC_DIR = Path(__file__).resolve().parent / "src" / "static" / "operator"
TOKEN_COOKIE_NAME = "mmm_operator_token"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MMM private operator UI.")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host. Defaults to 127.0.0.1.")
    parser.add_argument("--port", type=int, default=4199, help="HTTP port. Defaults to 4199.")
    parser.add_argument(
        "--token",
        default=None,
        help="Optional shared secret token. Defaults to MMM_OPERATOR_TOKEN when set.",
    )
    parser.add_argument(
        "--preview-origin",
        default="http://127.0.0.1:3000",
        help="Local public-site preview origin to surface in the operator UI.",
    )
    return parser.parse_args()


def is_local_host(host: str) -> bool:
    normalized = (host or "").strip().lower()
    return normalized in {"127.0.0.1", "localhost"}


class OperatorHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        *,
        service: OperatorService,
        token: str | None,
        static_dir: Path = STATIC_DIR,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.service = service
        self.token = token.strip() if token else None
        self.static_dir = static_dir


class OperatorRequestHandler(BaseHTTPRequestHandler):
    server: OperatorHTTPServer

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/api/public-config":
                self._send_json(
                    {
                        "authRequired": bool(self.server.token),
                        "localOnlyNoToken": not self.server.token and is_local_host(self.server.server_address[0]),
                        **self.server.service.public_config(),
                    }
                )
                return

            if path == "/api/bootstrap":
                if not self._require_authorized():
                    return
                self._send_json(self.server.service.bootstrap())
                return

            if path == "/api/logs":
                if not self._require_authorized():
                    return
                self._send_json({"logs": self.server.service.logs()})
                return

            if path == "/api/drafts":
                if not self._require_authorized():
                    return
                self._send_json({"drafts": self.server.service.list_drafts(limit=50)})
                return

            if path.startswith("/api/drafts/"):
                if not self._require_authorized():
                    return
                slug = path.split("/", 3)[3]
                self._send_json(self.server.service.load_draft(slug))
                return

            if path == "/api/mixes":
                if not self._require_authorized():
                    return
                self._send_json({"mixes": self.server.service.list_published_mixes(limit=50)})
                return

            if path.startswith("/api/mixes/") and path.endswith("/youtube"):
                if not self._require_authorized():
                    return
                slug = path[len("/api/mixes/") : -len("/youtube")].strip("/")
                self._send_json(self.server.service.youtube_state(slug))
                return

            self._serve_static(path)
        except (FileNotFoundError, ValidationError, ValueError, RuntimeError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/auth/token":
                self._handle_token_login()
                return

            if path == "/auth/logout":
                self.send_response(HTTPStatus.OK)
                self._clear_token_cookie()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
                return

            if not self._require_authorized():
                return

            if path == "/api/validate":
                self._send_json(self.server.service._log_action("validate-repo", self.server.service.validate_repo))
                return

            if path == "/api/drafts/generate":
                payload = self._read_json_body()
                self._send_json(
                    self.server.service.generate_draft(
                        mix_date=payload.get("date"),
                        mode=str(payload.get("mode") or "local"),
                        with_ai_artwork=bool(payload.get("withAiArtwork")),
                        force=bool(payload.get("force")),
                    )
                )
                return

            if path.startswith("/api/drafts/") and path.endswith("/approve"):
                slug = path[len("/api/drafts/") : -len("/approve")].strip("/")
                payload = self._read_json_body()
                self._send_json(
                    self.server.service.approve_draft(
                        slug,
                        approver=(str(payload.get("by") or "").strip() or None),
                        note=(str(payload.get("note") or "").strip() or None),
                    )
                )
                return

            if path.startswith("/api/drafts/") and path.endswith("/release"):
                slug = path[len("/api/drafts/") : -len("/release")].strip("/")
                payload = self._read_json_body()
                self._send_json(self.server.service.release_draft(slug, feature=bool(payload.get("feature"))))
                return

            if path.startswith("/api/mixes/") and path.endswith("/youtube/sync"):
                slug = path[len("/api/mixes/") : -len("/youtube/sync")].strip("/")
                self._send_json(self.server.service.sync_youtube_state(slug))
                return

            self._send_error_json(HTTPStatus.NOT_FOUND, "Unknown POST endpoint")
        except (FileNotFoundError, ValidationError, ValueError, RuntimeError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def do_PUT(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            if not self._require_authorized():
                return

            if path.startswith("/api/drafts/"):
                slug = path.split("/", 3)[3]
                self._send_json(
                    self.server.service._log_action(
                        "save-draft",
                        lambda: self.server.service.save_draft(slug, self._read_json_body()),
                    )
                )
                return

            if path.startswith("/api/mixes/") and path.endswith("/youtube"):
                slug = path[len("/api/mixes/") : -len("/youtube")].strip("/")
                payload = self._read_json_body()
                selections = payload.get("selections")
                self._send_json(
                    self.server.service._log_action(
                        "update-youtube-selection",
                        lambda: self.server.service.update_youtube_selections(slug, selections),
                    )
                )
                return

            self._send_error_json(HTTPStatus.NOT_FOUND, "Unknown PUT endpoint")
        except (FileNotFoundError, ValidationError, ValueError, RuntimeError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Invalid JSON body: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ValidationError("JSON body must be an object")
        return payload

    def _authorized(self) -> bool:
        expected = self.server.token
        if not expected:
            return True

        header = self.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            supplied = header.split(" ", 1)[1].strip()
            if supplied and hmac.compare_digest(supplied, expected):
                return True

        cookie_header = self.headers.get("Cookie")
        if cookie_header:
            cookie = http.cookies.SimpleCookie()
            cookie.load(cookie_header)
            supplied = cookie.get(TOKEN_COOKIE_NAME)
            if supplied is not None and hmac.compare_digest(supplied.value, expected):
                return True

        return False

    def _require_authorized(self) -> bool:
        if self._authorized():
            return True
        self._send_error_json(HTTPStatus.UNAUTHORIZED, "Valid operator token required")
        return False

    def _set_token_cookie(self) -> None:
        cookie = http.cookies.SimpleCookie()
        cookie[TOKEN_COOKIE_NAME] = self.server.token or ""
        cookie[TOKEN_COOKIE_NAME]["httponly"] = True
        cookie[TOKEN_COOKIE_NAME]["path"] = "/"
        cookie[TOKEN_COOKIE_NAME]["samesite"] = "Strict"
        self.send_header("Set-Cookie", cookie.output(header="").strip())

    def _clear_token_cookie(self) -> None:
        cookie = http.cookies.SimpleCookie()
        cookie[TOKEN_COOKIE_NAME] = ""
        cookie[TOKEN_COOKIE_NAME]["httponly"] = True
        cookie[TOKEN_COOKIE_NAME]["path"] = "/"
        cookie[TOKEN_COOKIE_NAME]["max-age"] = 0
        cookie[TOKEN_COOKIE_NAME]["samesite"] = "Strict"
        self.send_header("Set-Cookie", cookie.output(header="").strip())

    def _handle_token_login(self) -> None:
        if not self.server.token:
            self._send_json({"ok": True, "authRequired": False})
            return
        payload = self._read_json_body()
        supplied = str(payload.get("token") or "").strip()
        if not supplied or not hmac.compare_digest(supplied, self.server.token):
            self._send_error_json(HTTPStatus.UNAUTHORIZED, "Invalid operator token")
            return
        self.send_response(HTTPStatus.OK)
        self._set_token_cookie()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "authRequired": True}).encode("utf-8"))

    def _serve_static(self, path: str) -> None:
        relative_path = "index.html" if path == "/" else path.lstrip("/")
        file_path = (self.server.static_dir / relative_path).resolve()
        try:
            file_path.relative_to(self.server.static_dir.resolve())
        except ValueError:
            self._send_error_json(HTTPStatus.NOT_FOUND, "Not found")
            return

        if not file_path.exists() or not file_path.is_file():
            self._send_error_json(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_type, _ = mimetypes.guess_type(file_path.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type or 'text/plain'}; charset=utf-8")
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

    def _send_json(self, payload: Any, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(payload, indent=2).encode("utf-8"))

    def _send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps({"error": message, "status": int(status)}).encode("utf-8"))


def main() -> int:
    args = parse_args()
    token = args.token
    if token is None:
        import os

        token = str(os.environ.get("MMM_OPERATOR_TOKEN") or "").strip() or None

    if not token and not is_local_host(args.host):
        raise SystemExit("Refusing to bind non-local host without MMM_OPERATOR_TOKEN or --token.")

    service = OperatorService(preview_origin=args.preview_origin)
    server = OperatorHTTPServer(
        (args.host, args.port),
        OperatorRequestHandler,
        service=service,
        token=token,
    )

    auth_label = "shared-token required" if token else "localhost-only, no token configured"
    print(f"MMM operator UI running at http://{args.host}:{args.port} ({auth_label})")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
