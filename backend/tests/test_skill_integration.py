import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from test_workflows import image_bytes

SCRIPT = Path(__file__).resolve().parents[2] / "skills" / "shiyi-api" / "scripts" / "shiyi_api.py"


def test_packaged_cli_reads_real_api_and_private_image_without_scoring(account, tmp_path):
    original = account.post("/api/v1/items", json={"title": "CLI合成原题", "subject": "math", "kind": "problem",
                            "question": "一个明确问题", "answer": "保密参考答案"}).json()
    child = account.post("/api/v1/items", json={"title": "CLI合成小任务", "subject": "math",
                         "question": "一个薄弱点", "answer": "保密子答案", "source_item_id": original["id"]}).json()
    assert account.post(f"/api/v1/items/{original['id']}/reviews", json={"rating": "again", "expected_version": 0,
                        "independent_completed": False, "blocker": "合成卡点"}).status_code == 201
    media = account.post("/api/v1/media", files={"file": ("test.png", image_bytes(), "image/png")}).json()
    key = account.post("/api/v1/keys", json={"name": "cli-read", "scopes": ["read"]}).json()["token"]
    paths = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            paths.append(self.path)
            headers = {"Authorization": self.headers["Authorization"]} if self.headers.get("Authorization") else {}
            response = account.get(self.path, headers=headers)
            self.send_response(response.status_code)
            self.send_header("Content-Type", response.headers.get("content-type", "application/json"))
            self.send_header("Content-Length", str(len(response.content)))
            self.end_headers()
            self.wfile.write(response.content)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"api_url": f"http://127.0.0.1:{server.server_port}", "api_key": key}), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("SHIYI_API_URL", "SHIYI_API_KEY", "SHIYI_CONFIG")}
    env["PYTHONIOENCODING"] = "utf-8"

    def cli(*args):
        response = subprocess.run([sys.executable, str(SCRIPT), "--config", str(config), "--no-proxy", *args],
                                  env=env, capture_output=True, encoding="utf-8", timeout=20)
        assert key not in response.stdout + response.stderr
        assert response.returncode == 0, response.stderr
        return json.loads(response.stdout)

    try:
        assert cli("context")["permissions"] == ["read"]
        assert cli("doctor")["agent_support"] is True
        recent = cli("reviews", "--independent-completed", "false", "--has-blocker", "true")
        assert recent["total"] == 1
        assert recent["items"][0]["blocker"] == "合成卡点"
        assert "answer_text" not in recent["items"][0]
        assert cli("weaknesses")["total"] == 0  # Initial failure is not cross-day forgetting.
        related = cli("list", "--source-item-id", original["id"], "--question-only")
        assert [i["id"] for i in related["items"]] == [child["id"]]
        assert "保密子答案" not in json.dumps(related, ensure_ascii=False)
        saved = tmp_path / "download.webp"
        assert cli("download", media["id"], "--out", str(saved))["bytes"] > 0
        assert saved.read_bytes().startswith(b"RIFF")
        body = tmp_path / "fields.json"
        body.write_text(json.dumps({"rating": "good", "expected_version": 1, "expected_item_version": 1,
                                   "independent_completed": True}), encoding="utf-8")
        before = len(paths)
        prepared = cli("review-prepare", original["id"], "--file", str(body), "--out", str(tmp_path / "attempt.json"))
        assert prepared["submitted"] is False
        assert len(paths) == before
        assert account.get(f"/api/v1/items/{original['id']}/reviews").json()["total"] == 1
        assert account.get(f"/api/v1/items/{child['id']}/reviews").json()["total"] == 0
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
