"""Server URL for the desktop client.

In production the installer writes this file's override at install time
(plan section 4.1) so staff never type a URL. The JSON override lets dev
point at a different server without rebuilding the client.
"""
import json
from pathlib import Path

DEFAULT_SERVER_URL = "http://localhost:8000"
CONFIG_PATH = Path.home() / ".erp-client" / "config.json"


def get_server_url() -> str:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            return data.get("server_url", DEFAULT_SERVER_URL)
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_SERVER_URL
