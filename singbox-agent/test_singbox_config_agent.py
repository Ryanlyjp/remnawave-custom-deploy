import importlib.util
import json
import os
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SINGBOX_AGENT_TOKEN", "test-token-with-at-least-32-characters")

MODULE_PATH = Path(__file__).with_name("singbox_config_agent.py")
SPEC = importlib.util.spec_from_file_location("singbox_config_agent", MODULE_PATH)
assert SPEC and SPEC.loader
agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent)


class Result:
    def __init__(self, returncode: int = 0):
        self.returncode = returncode


class AgentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "config.json"
        self.config_path.write_text('{"old":true}\n')
        agent.CONFIG_PATH = self.config_path
        self.server = agent.ThreadingHTTPServer(("127.0.0.1", 0), agent.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp_dir.cleanup()

    def request(self, path: str, payload: object | None = None, authorized: bool = True):
        headers = {}
        if authorized:
            headers["Authorization"] = f"Bearer {agent.TOKEN}"
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            f"{self.url}{path}", data=data, headers=headers, method="GET" if data is None else "PUT"
        )
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def test_requires_bearer_token(self) -> None:
        status, body = self.request("/health", authorized=False)
        self.assertEqual((status, body), (401, {"ok": False}))

    def test_rejects_invalid_payload_without_changing_config(self) -> None:
        status, body = self.request("/config", {"config": []})
        self.assertEqual((status, body), (400, {"ok": False}))
        self.assertEqual(self.config_path.read_text(), '{"old":true}\n')

    @patch.object(agent.subprocess, "run")
    def test_rejects_failed_singbox_check(self, run) -> None:
        run.return_value = Result(1)
        status, body = self.request("/config", {"config": {"new": True}})
        self.assertEqual(status, 422)
        self.assertEqual(body["error"], "sing-box check failed")
        self.assertEqual(self.config_path.read_text(), '{"old":true}\n')

    @patch.object(agent.subprocess, "run")
    def test_replaces_valid_config_atomically(self, run) -> None:
        run.side_effect = [Result(), Result(), Result()]
        status, body = self.request("/config", {"config": {"new": True}})
        self.assertEqual((status, body), (200, {"ok": True}))
        self.assertEqual(json.loads(self.config_path.read_text()), {"new": True})
        backup = self.config_path.with_suffix(".json.rw-agent-backup")
        self.assertEqual(json.loads(backup.read_text()), {"old": True})

    @patch.object(agent.subprocess, "run")
    def test_restores_backup_when_restart_fails(self, run) -> None:
        run.side_effect = [Result(), Result(1), Result(1), Result()]
        status, body = self.request("/config", {"config": {"new": True}})
        self.assertEqual(status, 500)
        self.assertEqual(body["error"], "service restart failed")
        self.assertEqual(json.loads(self.config_path.read_text()), {"old": True})

    @patch.object(agent.subprocess, "run")
    def test_restores_backup_when_restart_times_out(self, run) -> None:
        run.side_effect = [
            Result(),
            subprocess.TimeoutExpired("systemctl", 20),
            Result(),
        ]
        status, body = self.request("/config", {"config": {"new": True}})
        self.assertEqual(status, 500)
        self.assertEqual(body, {"ok": False})
        self.assertEqual(json.loads(self.config_path.read_text()), {"old": True})


if __name__ == "__main__":
    unittest.main()
