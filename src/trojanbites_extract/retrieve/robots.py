from __future__ import annotations

from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser

import httpx


def allowed_by_robots(url: str, user_agent: str, timeout: float = 10.0) -> bool:
    parsed = urlparse(url)
    robots_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", "/robots.txt")
    rp = RobotFileParser()
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(robots_url)
            if resp.status_code >= 400:
                # No robots or inaccessible — conservative allow with note upstream
                return True
            rp.parse(resp.text.splitlines())
    except Exception:
        return True
    return rp.can_fetch(user_agent, url)