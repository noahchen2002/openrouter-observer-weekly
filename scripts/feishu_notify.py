"""Feishu (Lark) notification helpers for the daily pipeline.

This module supports sending a text message and uploading/sending a file to a
group chat via Feishu OpenAPI using a bot app credential.

Environment variables (recommended for launchd):
- FEISHU_APP_ID / FEISHU_APP_SECRET: used to fetch tenant_access_token
  (preferred, because token auto-refreshes)
- FEISHU_TENANT_ACCESS_TOKEN: if set, uses this token directly
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


def _api_base() -> str:
    # NOTE: _get_env is defined below; this function is only called at runtime,
    # after module import completed.
    value = _get_env("FEISHU_API_BASE").strip()  # type: ignore[name-defined]
    return (value or "https://open.feishu.cn/open-apis").rstrip("/")


class FeishuNotifyError(RuntimeError):
    pass


@dataclass(frozen=True)
class FeishuAuth:
    tenant_access_token: str


def _parse_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and ((value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")):
            value = value[1:-1]
        values[key] = value
    return values


def _get_env(name: str) -> str:
    """Get env var; if FEISHU_ENV_FILE is set, read from it as fallback."""
    direct = os.getenv(name)
    if direct is not None and str(direct).strip() != "":
        return str(direct).strip()
    env_file = (os.getenv("FEISHU_ENV_FILE") or "").strip()
    if env_file:
        values = _parse_dotenv(Path(env_file).expanduser())
        value = values.get(name)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


def _require_env(name: str) -> str:
    value = _get_env(name).strip()
    if not value:
        raise FeishuNotifyError(f"Missing required env var: {name}")
    return value


def get_tenant_access_token(*, timeout: float = 15.0) -> str:
    direct = _get_env("FEISHU_TENANT_ACCESS_TOKEN").strip()
    if direct:
        return direct

    app_id = _get_env("FEISHU_APP_ID").strip()
    app_secret = _get_env("FEISHU_APP_SECRET").strip()
    if not app_id or not app_secret:
        raise FeishuNotifyError(
            "Missing Feishu credentials. Set either FEISHU_TENANT_ACCESS_TOKEN or "
            "(FEISHU_APP_ID + FEISHU_APP_SECRET).",
        )

    url = f"{_api_base()}/auth/v3/tenant_access_token/internal"
    payload = {"app_id": app_id, "app_secret": app_secret}
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=payload)
    data = resp.json()
    if resp.status_code >= 400 or data.get("code", 0) != 0:
        raise FeishuNotifyError(f"Failed to get tenant_access_token: status={resp.status_code} body={data}")
    token = str(data.get("tenant_access_token") or "").strip()
    if not token:
        raise FeishuNotifyError(f"tenant_access_token missing in response: {data}")
    return token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def send_text_message(
    *, chat_id: str, text: str, receive_id_type: str = "chat_id", timeout: float = 15.0
) -> dict[str, Any]:
    token = get_tenant_access_token(timeout=timeout)
    url = f"{_api_base()}/im/v1/messages"
    params = {"receive_id_type": receive_id_type}
    payload = {
        "receive_id": chat_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False),
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, params=params, json=payload, headers=_headers(token))
    data = resp.json()
    if resp.status_code >= 400 or data.get("code", 0) != 0:
        raise FeishuNotifyError(f"Failed to send text message: status={resp.status_code} body={data}")
    return data


def send_interactive_card(
    *, chat_id: str, card: dict[str, Any], receive_id_type: str = "chat_id", timeout: float = 15.0
) -> dict[str, Any]:
    """Send an interactive card via the app (bot) identity.

    receive_id_type: "chat_id" for a group, or "open_id" to DM a single user.
    """
    token = get_tenant_access_token(timeout=timeout)
    url = f"{_api_base()}/im/v1/messages"
    params = {"receive_id_type": receive_id_type}
    payload = {
        "receive_id": chat_id,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, params=params, json=payload, headers=_headers(token))
    data = resp.json()
    if resp.status_code >= 400 or data.get("code", 0) != 0:
        raise FeishuNotifyError(f"Failed to send interactive card: status={resp.status_code} body={data}")
    return data


def upload_file(*, path: Path, timeout: float = 60.0) -> str:
    """Upload a local file and return file_key for im/v1/messages (msg_type=file)."""
    token = get_tenant_access_token(timeout=timeout)
    url = f"{_api_base()}/im/v1/files"
    file_bytes = path.read_bytes()
    # file_type must be one of: opus, mp4, pdf, doc, xls, ppt, stream (not "file").
    files = {"file": (path.name, file_bytes, "application/octet-stream")}
    data = {"file_type": "stream", "file_name": path.name}
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, data=data, files=files, headers=_headers(token))
    body = resp.json()
    if resp.status_code >= 400 or body.get("code", 0) != 0:
        raise FeishuNotifyError(f"Failed to upload file: status={resp.status_code} body={body}")
    file_key = (((body.get("data") or {}).get("file_key")) or "").strip()
    if not file_key:
        raise FeishuNotifyError(f"file_key missing in upload response: {body}")
    return file_key


def send_file_message(*, chat_id: str, file_key: str, timeout: float = 15.0) -> dict[str, Any]:
    token = get_tenant_access_token(timeout=timeout)
    url = f"{_api_base()}/im/v1/messages"
    params = {"receive_id_type": "chat_id"}
    payload = {
        "receive_id": chat_id,
        "msg_type": "file",
        "content": json.dumps({"file_key": file_key}, ensure_ascii=False),
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, params=params, json=payload, headers=_headers(token))
    data = resp.json()
    if resp.status_code >= 400 or data.get("code", 0) != 0:
        raise FeishuNotifyError(f"Failed to send file message: status={resp.status_code} body={data}")
    return data


def send_html_file(*, chat_id: str, html_path: Path, timeout: float = 60.0) -> None:
    if not html_path.exists():
        raise FeishuNotifyError(f"HTML file not found: {html_path}")
    file_key = upload_file(path=html_path, timeout=timeout)
    send_file_message(chat_id=chat_id, file_key=file_key, timeout=timeout)

