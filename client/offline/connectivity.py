"""Online/offline detection: a reachability probe against the server's
health endpoint, used to decide whether reads/writes go direct or through
the SQLite cache/outbox (plan section 1.5).
"""
import requests

from client.config import get_server_url


def is_online(timeout: float = 2.0) -> bool:
    try:
        resp = requests.get(f"{get_server_url()}/api/v1/health", timeout=timeout)
        return resp.status_code == 200
    except requests.RequestException:
        return False
