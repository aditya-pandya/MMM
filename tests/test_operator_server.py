from __future__ import annotations

import json
import sys
import threading
from http.client import HTTPConnection
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from operator_server import OperatorHTTPServer, OperatorRequestHandler
from operator_workflow import OperatorService
from test_approval_and_release import seed_repo


@pytest.fixture()
def running_server(tmp_path):
    seed_repo(tmp_path)
    service = OperatorService(repo_root=tmp_path, preview_origin="http://127.0.0.1:3000")
    server = OperatorHTTPServer(
        ("127.0.0.1", 0),
        OperatorRequestHandler,
        service=service,
        token="secret-token",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def request_json(server, method: str, path: str, body: dict | None = None, token: str | None = None):
    connection = HTTPConnection(*server.server_address)
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = None if body is None else json.dumps(body)
    if payload is not None:
        headers["Content-Type"] = "application/json"
    connection.request(method, path, body=payload, headers=headers)
    response = connection.getresponse()
    raw = response.read().decode("utf-8")
    data = json.loads(raw)
    connection.close()
    return response.status, data


def test_operator_server_requires_token_for_private_endpoints(running_server):
    status, payload = request_json(running_server, "GET", "/api/bootstrap")
    assert status == 401
    assert "token" in payload["error"].lower()


def test_operator_server_can_save_draft_with_bearer_token(running_server):
    status, payload = request_json(running_server, "GET", "/api/drafts/mmm-for-2026-04-13", token="secret-token")
    assert status == 200
    assert payload["slug"] == "mmm-for-2026-04-13"

    status, payload = request_json(
        running_server,
        "PUT",
        "/api/drafts/mmm-for-2026-04-13",
        body={
            "title": "Edited in browser",
            "summary": "Updated summary",
            "notes": "Updated notes",
            "tags": ["weekly-draft"],
            "featured": False,
            "tracks": [
                {"artist": "Broadcast", "title": "Pendulum", "why_it_fits": "Sets the tone."},
                {"artist": "Air", "title": "All I Need", "why_it_fits": "Keeps things warm."},
                {"artist": "Stereolab", "title": "French Disko", "why_it_fits": "Adds momentum."},
            ],
        },
        token="secret-token",
    )
    assert status == 200
    assert payload["title"] == "Edited in browser"

    status, logs_payload = request_json(running_server, "GET", "/api/logs", token="secret-token")
    assert status == 200
    assert logs_payload["logs"][0]["action"] == "save-draft"
