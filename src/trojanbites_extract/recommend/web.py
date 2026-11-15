"""Bounded, in-memory public menu retrieval. No disk artifacts or catalog access."""
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from trojanbites_extract.retrieve.fetcher import _is_private_host

USER_AGENT = 'TrojanPlate/1.0 (public menu retrieval)'
MAX_BYTES = 1_500_000


@dataclass
class Page:
    url: str
    text: str
    links: list[str]


def public_url(url: str) -> bool:
    p = urlparse(url)
    return (p.scheme in {'https','http'} and bool(p.hostname) and not p.username and not p.password
            and p.port in {None,80,443} and not _is_private_host(p.hostname))


def _read(url: str, client: httpx.Client) -> tuple[str, str, bytes]:
    for _ in range(4):
        if not public_url(url):
            raise ValueError('Non-public menu URL')
        with client.stream('GET',url) as response:
            if response.is_redirect:
                url = urljoin(url,response.headers['location']); continue
            response.raise_for_status()
            data=bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data)>MAX_BYTES:
                    raise ValueError('Menu page too large')
            return str(response.url),response.headers.get('content-type',''),bytes(data)
    raise ValueError('Too many redirects')


def fetch_page(url: str, *, transport=None) -> Page:
    with httpx.Client(timeout=10,headers={'User-Agent':USER_AGENT},transport=transport,trust_env=False) as client:
        parsed=urlparse(url)
        robots=urljoin(f'{parsed.scheme}://{parsed.netloc}','/robots.txt')
        try:
            _,_,raw=_read(robots,client)
            rules=RobotFileParser();rules.parse(raw.decode(errors='replace').splitlines())
            if not rules.can_fetch(USER_AGENT,url):
                raise ValueError('Menu retrieval disallowed by robots.txt')
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {404,410}:
                raise ValueError('Unable to check robots.txt') from exc
        final,kind,raw=_read(url,client)
        if kind.startswith('application/pdf'):
            import pdfplumber
            with pdfplumber.open(BytesIO(raw)) as pdf:
                text='\n'.join(p.extract_text() or '' for p in pdf.pages[:10])
            return Page(final,text[:24000],[])
        if not any(k in kind for k in ['html','text/plain','application/json']):
            raise ValueError('Unsupported menu format')
        if 'application/json' in kind:
            return Page(final,raw.decode('utf-8'),[])
        soup=BeautifulSoup(raw,'html.parser')
        links=[]
        for a in soup.find_all('a',href=True):
            target=urljoin(final,a['href'])
            if urlparse(target).hostname==urlparse(final).hostname and any(w in (target+' '+a.get_text()).lower() for w in ['menu','nutrition']):
                if target not in links: links.append(target)
        for tag in soup(['script','style','noscript','nav','footer','header']): tag.decompose()
        text='\n'.join(line.strip() for line in soup.get_text('\n').splitlines() if line.strip())
        return Page(final,text[:24000],links[:8])
