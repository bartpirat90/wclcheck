"""OAuth2 client_credentials gegen Warcraft Logs; Token wird lokal bis Ablauf gecacht."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

TOKEN_URL = "https://www.warcraftlogs.com/oauth/token"
_REFRESH_MARGIN_S = 120


class AuthError(Exception):
    pass


class TokenProvider:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        cache_dir: Path,
        http: httpx.Client,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http
        self._path = cache_dir / "token.json"
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        # Token nur wiederverwenden, wenn er zur selben Client-ID gehört.
        if data.get("client_id") != self._client_id:
            return
        self._token = data.get("access_token")
        self._expires_at = float(data.get("expires_at", 0))

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {
                    "client_id": self._client_id,
                    "access_token": self._token,
                    "expires_at": self._expires_at,
                }
            ),
            "utf-8",
        )

    def invalidate(self) -> None:
        self._token = None
        self._expires_at = 0.0

    def token(self) -> str:
        if self._token and time.time() < self._expires_at - _REFRESH_MARGIN_S:
            return self._token
        resp = self._http.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self._client_id, self._client_secret),
        )
        if resp.status_code != 200:
            raise AuthError(
                f"Token-Abruf fehlgeschlagen ({resp.status_code}): {resp.text[:200]}"
            )
        body = resp.json()
        self._token = body["access_token"]
        self._expires_at = time.time() + float(body.get("expires_in", 3600))
        self._save()
        return self._token
