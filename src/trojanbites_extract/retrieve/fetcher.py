from __future__ import annotations

import hashlib
import ipaddress
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from trojanbites_extract.retrieve.robots import allowed_by_robots
from trojanbites_extract.settings import get_settings, load_extraction_config

ALLOWED_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "application/pdf",
    "text/plain",
    "application/json",
    "image/png",
    "image/jpeg",
    "image/webp",
}


@dataclass
class RawArtifact:
    url: str
    ok: bool
    http_status: int | None
    content_type: str | None
    content_hash: str | None
    bytes_path: Path | None
    fetched_at: datetime
    robots_status: str
    error: str | None = None
    final_url: str | None = None


def _is_private_host(hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return True
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return True
    return False


class SafeFetcher:
    def __init__(self):
        cfg = load_extraction_config().get("fetch", {})
        self.connect_timeout = float(cfg.get("connect_timeout_s", 15))
        self.read_timeout = float(cfg.get("read_timeout_s", 30))
        self.max_bytes = int(cfg.get("max_bytes", 15_728_640))
        self.user_agent = cfg.get(
            "user_agent", "TrojanBitesExtract/0.1 (+local)"
        )
        self.artifacts_dir = get_settings().artifacts_dir

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        wait=wait_exponential_jitter(initial=1, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _get(self, client: httpx.Client, url: str) -> httpx.Response:
        return client.get(url)

    def fetch(self, url: str) -> RawArtifact:
        now = datetime.now(timezone.utc)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return RawArtifact(
                url=url,
                ok=False,
                http_status=None,
                content_type=None,
                content_hash=None,
                bytes_path=None,
                fetched_at=now,
                robots_status="blocked_scheme",
                error="Only http/https allowed",
            )
        if not parsed.hostname or _is_private_host(parsed.hostname):
            return RawArtifact(
                url=url,
                ok=False,
                http_status=None,
                content_type=None,
                content_hash=None,
                bytes_path=None,
                fetched_at=now,
                robots_status="ssrf_blocked",
                error="Host resolves to private/reserved IP",
            )

        if not allowed_by_robots(url, self.user_agent):
            return RawArtifact(
                url=url,
                ok=False,
                http_status=None,
                content_type=None,
                content_hash=None,
                bytes_path=None,
                fetched_at=now,
                robots_status="disallowed",
                error="robots.txt disallows fetch",
            )

        timeout = httpx.Timeout(self.connect_timeout, read=self.read_timeout)
        headers = {"User-Agent": self.user_agent, "Accept": "*/*"}
        try:
            with httpx.Client(
                timeout=timeout, follow_redirects=True, headers=headers
            ) as client:
                resp = self._get(client, url)
                content = resp.content
                if len(content) > self.max_bytes:
                    return RawArtifact(
                        url=url,
                        ok=False,
                        http_status=resp.status_code,
                        content_type=resp.headers.get("content-type"),
                        content_hash=None,
                        bytes_path=None,
                        fetched_at=now,
                        robots_status="allowed",
                        error=f"Response exceeds max_bytes={self.max_bytes}",
                        final_url=str(resp.url),
                    )
                ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                if ctype and ctype not in ALLOWED_CONTENT_TYPES and not ctype.startswith("text/"):
                    return RawArtifact(
                        url=url,
                        ok=False,
                        http_status=resp.status_code,
                        content_type=ctype,
                        content_hash=None,
                        bytes_path=None,
                        fetched_at=now,
                        robots_status="allowed",
                        error=f"Disallowed content-type: {ctype}",
                        final_url=str(resp.url),
                    )
                if resp.status_code >= 400:
                    return RawArtifact(
                        url=url,
                        ok=False,
                        http_status=resp.status_code,
                        content_type=ctype,
                        content_hash=None,
                        bytes_path=None,
                        fetched_at=now,
                        robots_status="allowed",
                        error=f"HTTP {resp.status_code}",
                        final_url=str(resp.url),
                    )
                digest = hashlib.sha256(content).hexdigest()
                path = self.artifacts_dir / f"{digest[:2]}" / digest
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    path.write_bytes(content)
                return RawArtifact(
                    url=url,
                    ok=True,
                    http_status=resp.status_code,
                    content_type=ctype or "application/octet-stream",
                    content_hash=digest,
                    bytes_path=path,
                    fetched_at=now,
                    robots_status="allowed",
                    final_url=str(resp.url),
                )
        except Exception as exc:  # noqa: BLE001
            return RawArtifact(
                url=url,
                ok=False,
                http_status=None,
                content_type=None,
                content_hash=None,
                bytes_path=None,
                fetched_at=now,
                robots_status="allowed",
                error=str(exc),
            )