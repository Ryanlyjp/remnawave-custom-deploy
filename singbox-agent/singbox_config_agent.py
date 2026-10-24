#!/usr/bin/env python3
import hmac
import json
import os
import shutil
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY_BYTES = 4 * 1024 * 1024
TOKEN = os.environ["SINGBOX_AGENT_TOKEN"]
CONFIG_PATH = Path(os.environ.get("SINGBOX_CONFIG_PATH", "/etc/sing-box/config.json"))
SERVICE_NAME = os.environ.get("SINGBOX_SERVICE_NAME", "sing-box.service")
BIND_HOST = os.environ.get("SINGBOX_AGENT_BIND", "127.0.0.1")
PORT = int(os.environ.get("SINGBOX_AGENT_PORT", "18080"))


class Handler(BaseHTTPRequestHandler):
    server_version = "singbox-config-agent/1"

    def log_message(self, message: str, *args: object) -> None:
        print(f"{self.client_address[0]} - {message % args}", flush=True)

    def respond(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authorized(self) -> bool:
        expected = f"Bearer {TOKEN}"
        provided = self.headers.get("Authorization", "")
        return hmac.compare_digest(provided, expected)

    def restore_backup(self, backup_path: Path) -> None:
        if not backup_path.exists():
            return
        try:
            shutil.copy2(backup_path, CONFIG_PATH)
            subprocess.run(
                ["systemctl", "restart", SERVICE_NAME], check=False, timeout=20
            )
        except (OSError, subprocess.SubprocessError):
            pass

    def do_GET(self) -> None:
        if self.path != "/health":
            self.respond(404, {"ok": False})
            return
        if not self.authorized():
            self.respond(401, {"ok": False})
            return
        active = subprocess.run(
            ["systemctl", "is-active", "--quiet", SERVICE_NAME], check=False
        ).returncode == 0
        self.respond(200 if active else 503, {"ok": active})

    def do_PUT(self) -> None:
        if self.path != "/config":
            self.respond(404, {"ok": False})
            return
        if not self.authorized():
            self.respond(401, {"ok": False})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.respond(400, {"ok": False})
            return
        if length < 2 or length > MAX_BODY_BYTES:
            self.respond(413, {"ok": False})
            return

        try:
            payload = json.loads(self.rfile.read(length))
            config = payload["config"]
            if not isinstance(config, dict):
                raise ValueError
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            self.respond(400, {"ok": False})
            return

        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        backup_path = CONFIG_PATH.with_suffix(CONFIG_PATH.suffix + ".rw-agent-backup")
        temp_path: Path | None = None
        config_replaced = False

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=CONFIG_PATH.parent,
                prefix=".singbox-",
                suffix=".json",
                delete=False,
            ) as handle:
                json.dump(config, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                temp_path = Path(handle.name)
            temp_path.chmod(0o600)

            check = subprocess.run(
                ["sing-box", "check", "-c", str(temp_path)],
                capture_output=True,
                check=False,
                timeout=15,
            )
            if check.returncode != 0:
                self.respond(422, {"ok": False, "error": "sing-box check failed"})
                return

            if CONFIG_PATH.exists():
                shutil.copy2(CONFIG_PATH, backup_path)
            os.replace(temp_path, CONFIG_PATH)
            temp_path = None
            config_replaced = True

            restart = subprocess.run(
                ["systemctl", "restart", SERVICE_NAME], check=False, timeout=20
            )
            active = subprocess.run(
                ["systemctl", "is-active", "--quiet", SERVICE_NAME], check=False
            )
            if restart.returncode != 0 or active.returncode != 0:
                self.restore_backup(backup_path)
                self.respond(500, {"ok": False, "error": "service restart failed"})
                return

            self.respond(200, {"ok": True})
        except (OSError, subprocess.SubprocessError):
            if config_replaced:
                self.restore_backup(backup_path)
            self.respond(500, {"ok": False})
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()


if __name__ == "__main__":
    if len(TOKEN) < 32:
        raise SystemExit("SINGBOX_AGENT_TOKEN must contain at least 32 characters")
    ThreadingHTTPServer((BIND_HOST, PORT), Handler).serve_forever()
