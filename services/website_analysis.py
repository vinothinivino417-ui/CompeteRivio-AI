"""Small, cached public-homepage checks; no API keys, login, or JavaScript execution."""
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
import ipaddress
import re
import socket
import threading
import time
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests
import streamlit as st


USER_AGENT = "CompeteRivioWebsiteChecker/1.0"
MAX_SITES = 8
RUN_SECONDS = 45
_lock = threading.Lock()
_last_request = {}
STOP_WORDS = set("the and for with that this your our you are from have has was were will can about more read home contact privacy policy cookie cookies copyright all rights reserved menu login sign into not terms www com http https use their they its also get here any page us on in of to as is it be by or at an a".split())


class WebsiteError(ValueError):
    pass


class RobotsBlocked(WebsiteError):
    pass


def _url_key(value):
    value = str(value or "").strip()
    if not value:
        return ""
    value = "https:" + value if value.startswith("//") else value if "://" in value else "https://" + value
    try:
        parsed = urlsplit(value)
        return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))
    except ValueError:
        return value  # audit_website will label malformed URLs unavailable.


def public_url(value):
    value = str(value or "").strip()
    if value.startswith("//"):
        value = "https:" + value
    elif "://" not in value:
        value = "https://" + value
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise WebsiteError("Use a public HTTP or HTTPS website without login credentials.")
    if parsed.port not in (None, 80, 443):
        raise WebsiteError("Only standard website ports are supported.")
    host = parsed.hostname.rstrip(".").casefold()
    if host == "localhost" or host.endswith((".localhost", ".local")):
        raise WebsiteError("Local and private network addresses cannot be checked.")
    addresses = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(address[4][0]).is_global for address in addresses):
        raise WebsiteError("Local and private network addresses cannot be checked.")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


def _read_response(url, deadline, delay=1.0, maximum=512 * 1024):
    host = urlsplit(url).hostname
    with _lock:
        remaining = deadline - time.monotonic()
        wait = max(0, delay - (time.monotonic() - _last_request.get(host, 0)))
        if remaining <= wait + .2:
            raise WebsiteError("Website check time budget reached; retry this website later.")
        if wait:
            time.sleep(wait)
        remaining = deadline - time.monotonic()
        _last_request[host] = time.monotonic()
        with requests.Session() as session:
            session.trust_env = False  # Do not use .netrc credentials or browser sessions.
            with session.get(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.8"},
                             timeout=(min(3, remaining), min(6, remaining)), stream=True, allow_redirects=False) as response:
                status = response.status_code
                headers = dict(response.headers)
                if status < 200 or status >= 300:
                    return status, headers, ""
                chunks, size = [], 0
                for chunk in response.iter_content(chunk_size=8192):
                    if time.monotonic() >= deadline:
                        raise WebsiteError("Website check time budget reached; retry this website later.")
                    size += len(chunk)
                    if size > maximum:
                        raise WebsiteError("Page exceeds the small-page download limit.")
                    chunks.append(chunk)
                payload = b"".join(chunks)
                try:
                    body = payload.decode(response.encoding or "utf-8", errors="replace")
                except LookupError:
                    body = payload.decode("utf-8", errors="replace")
                return status, headers, body


def _download(url, deadline, robots=False):
    for _ in range(4):
        url = public_url(url)  # Validate every redirect before connecting.
        delay = 1.0
        if not robots:
            policy = _robots_policy(urlsplit(url).scheme + "://" + urlsplit(url).netloc, _deadline=deadline)
            parser = RobotFileParser()
            parser.parse(policy.splitlines())
            if not parser.can_fetch(USER_AGENT, url):
                raise RobotsBlocked("This website's robots.txt does not allow this page to be checked.")
            delay = max(1, parser.crawl_delay(USER_AGENT) or 0)
            rate = parser.request_rate(USER_AGENT)
            if rate and rate.requests:
                delay = max(delay, rate.seconds / rate.requests)
        status, headers, body = _read_response(url, deadline, delay, 64 * 1024 if robots else 512 * 1024)
        if status in (301, 302, 303, 307, 308):
            location = headers.get("Location") or headers.get("location")
            if not location:
                raise WebsiteError("Website redirect has no destination.")
            url = urljoin(url, location)
            continue
        return url, status, headers, body
    raise WebsiteError("Website redirected too many times.")


@st.cache_data(ttl=3600, show_spinner=False)
def _robots_policy(origin, _deadline):
    _, status, headers, body = _download(origin + "/robots.txt", _deadline, robots=True)
    if status in (404, 410):
        return "User-agent: *\nAllow: /"
    if status in (401, 403):
        return "User-agent: *\nDisallow: /"
    if status != 200 or "html" in headers.get("Content-Type", headers.get("content-type", "")).lower():
        raise WebsiteError("robots.txt could not be verified; the page was not fetched.")
    return body


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.description, self.meta_keywords = [], "", ""
        self.headings, self.visible, self.links = [], [], []
        self._title, self._head, self._skip = False, False, 0
        self._heading, self._anchor = None, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "head": self._head = True
        if tag == "title": self._title = True
        if tag in ("script", "style", "noscript", "svg"): self._skip += 1
        if tag == "meta":
            label = (attrs.get("name") or attrs.get("property") or "").lower()
            if label == "description" or (label == "og:description" and not self.description):
                self.description = attrs.get("content") or ""
            if label == "keywords": self.meta_keywords = attrs.get("content") or ""
        if tag in ("h1", "h2"): self._heading = [tag, []]
        if tag == "a": self._anchor = [attrs.get("href") or "", []]

    def handle_endtag(self, tag):
        if tag == "title": self._title = False
        if tag == "head": self._head = False
        if tag in ("script", "style", "noscript", "svg"): self._skip = max(0, self._skip - 1)
        if self._heading and tag == self._heading[0]:
            self.headings.append(" ".join(self._heading[1]))
            self._heading = None
        if tag == "a" and self._anchor:
            self.links.append((self._anchor[0], " ".join(self._anchor[1])))
            self._anchor = None

    def handle_data(self, data):
        if self._skip: return
        value = " ".join(data.split())
        if not value: return
        if self._title: self.title.append(value)
        if not self._head: self.visible.append(value)
        if self._heading: self._heading[1].append(value)
        if self._anchor: self._anchor[1].append(value)


def extract_page(html, url):
    parser = PageParser()
    parser.feed(html)
    visible = " ".join(parser.visible)
    words = [word.lower() for word in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", visible)
             if word.lower() not in STOP_WORDS]
    emails = set(re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", visible))
    phones, services = set(), []
    for href, label in parser.links:
        if href.lower().startswith("mailto:"):
            emails.update(re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", href.split("?", 1)[0]))
        elif href.lower().startswith("tel:"):
            phones.add(href[4:].split("?", 1)[0][:60])
        destination = urlsplit(urljoin(url, href))
        if label and destination.hostname == urlsplit(url).hostname and re.search(r"service|product|department|specialit|specialt|treatment|categor", destination.path, re.IGNORECASE):
            services.append(label[:140])
    return {"Page title": " ".join(parser.title)[:300], "Description": " ".join(parser.description.split())[:700],
            "Headings": list(dict.fromkeys(value[:180] for value in parser.headings))[:12],
            "On-page keyword candidates": [word for word, _ in Counter(words).most_common(12)],
            "Declared meta keywords": [value.strip()[:80] for value in parser.meta_keywords.split(",") if value.strip()][:12],
            "Service/product link labels": list(dict.fromkeys(services))[:12],
            "Email links/text": sorted(value for value in emails if len(value) <= 254)[:10], "Phone links": sorted(phones)[:10]}


@st.cache_data(ttl=86400, show_spinner=False)
def _audit_public(url, _deadline):
    final_url, status, headers, body = _download(url, _deadline)
    if status in (401, 403, 429):
        raise RobotsBlocked(f"Website access is restricted (HTTP {status}); no bypass was attempted.")
    if status != 200:
        raise WebsiteError(f"Website returned HTTP {status}.")
    content_type = headers.get("Content-Type", headers.get("content-type", "")).lower()
    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
        raise WebsiteError("The URL did not return an HTML webpage.")
    return {"Status": "Available", "Requested URL": url, "Source URL": final_url,
            "Retrieved at (UTC)": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "Scope": "Supplied/listed webpage HTML only; ownership, branch identity, and script-rendered content are not verified.",
            **extract_page(body, final_url)}


def audit_website(url, deadline=None):
    if not str(url or "").strip():
        return {"Status": "Unavailable", "Source URL": "", "Reason": "No website URL supplied or listed."}
    try:
        return _audit_public(_url_key(url), _deadline=deadline or time.monotonic() + 20)
    except RobotsBlocked as error:
        return {"Status": "Blocked", "Source URL": str(url), "Reason": str(error)}
    except (WebsiteError, requests.RequestException, OSError, ValueError) as error:
        return {"Status": "Unavailable", "Source URL": str(url), "Reason": str(error)}


def enrich_websites(business, competitors, progress=None):
    deadline = time.monotonic() + RUN_SECONDS
    checked, results = 0, {}
    entities = [business] + competitors
    records = [None] * len(entities)
    def priority(index):
        item = entities[index]
        url = item.get("website" if index == 0 else "Website", "") or ""
        old = item.get("Website analysis", {})
        if old.get("Status") == "Skipped" or not old or _url_key(old.get("Requested URL", url)) != _url_key(url):
            return 0
        return 2 if old.get("Status") == "Available" else 1
    for index in sorted(range(len(entities)), key=priority):
        item = entities[index]
        url = item.get("website" if index == 0 else "Website", "") or ""
        key = _url_key(url)
        name = item.get("name" if index == 0 else "Name", "Business")
        if url and key in results:
            audit = dict(results[key])
        elif url and (checked >= MAX_SITES or time.monotonic() >= deadline):
            old = item.get("Website analysis", {})
            if old.get("Status") == "Available" and _url_key(old.get("Requested URL")) == key:
                audit = old
            else:
                audit = {"Status": "Skipped", "Source URL": url, "Reason": "Per-run website limit reached; use Check websites to retry later."}
        else:
            if url:
                checked += 1
                if progress: progress(f"Checking public website for {name}...")
            audit = audit_website(url, deadline=deadline)
            if url: results[key] = audit
        records[index] = {**item, "Website analysis": audit}
    return records[0], records[1:]
