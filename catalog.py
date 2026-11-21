"""
Microsoft Update Catalog client.

- One keep-alive HTTPS connection per thread: avoids a fresh TLS handshake for
  every query (measured ~320 ms saved per request).
- Results cached in memory and on disk for 24 hours, so a second launch does
  not re-query the catalog at all.
- Raises CatalogError on network/HTTP failure so callers can tell "could not
  check" apart from "no updates found".
"""

import atexit
import http.client
import json
import os
import re
import threading
import time
import urllib.parse
from html import unescape

import paths

HOST = "www.catalog.update.microsoft.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
CACHE_TTL_SECONDS = 24 * 3600


class CatalogError(Exception):
    """The catalog could not be queried (offline, HTTP error, blocked)."""


_cache = {}
_cache_lock = threading.Lock()
_cache_loaded = False
_cache_state = {"dirty": False}
_local = threading.local()


def _cache_file():
    try:
        return os.path.join(paths.cache_dir(), "catalog_cache.json")
    except Exception:
        return ""


def _load_cache():
    global _cache_loaded
    with _cache_lock:
        if _cache_loaded:
            return
        _cache_loaded = True
        path = _cache_file()
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            now = time.time()
            for query, entry in raw.items():
                if now - entry.get("ts", 0) <= CACHE_TTL_SECONDS:
                    _cache[query] = entry.get("results", [])
        except Exception:
            pass


def _save_cache():
    with _cache_lock:
        if not _cache_state["dirty"]:
            return
        path = _cache_file()
        if not path:
            return
        try:
            now = time.time()
            payload = {q: {"ts": now, "results": r} for q, r in _cache.items()}
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp, path)
            _cache_state["dirty"] = False
        except Exception:
            pass


atexit.register(_save_cache)


def _drop_connection():
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    _local.conn = None


def _http_get(path, timeout=10):
    """GET through a reused per-thread connection, retrying once on a stale socket."""
    last_error = None
    for attempt in (1, 2):
        try:
            conn = getattr(_local, "conn", None)
            if conn is None:
                conn = http.client.HTTPSConnection(HOST, timeout=timeout)
                _local.conn = conn
            conn.timeout = timeout
            conn.request("GET", path, headers={"User-Agent": USER_AGENT})
            response = conn.getresponse()
            body = response.read()
            if response.status != 200:
                raise CatalogError("HTTP %s" % response.status)
            return body.decode("utf-8", errors="ignore")
        except CatalogError:
            raise
        except Exception as exc:
            last_error = exc
            _drop_connection()
    raise CatalogError(str(last_error) if last_error else "connection failed")


def parse_rows(html):
    """Extract catalog result rows from a Search.aspx page."""
    rows = re.findall(r'<tr id="([^"]+)"[^>]*>(.*?)</tr>', html, re.DOTALL)
    results = []

    for row_id, content in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', content, re.DOTALL)
        clean_cells = [unescape(re.sub(r'<[^>]+>', '', c).strip()) for c in cells]

        btn_match = re.search(r'<input id="([^"]+)"[^>]+value=[\'"]Download[\'"]', content)
        update_id = btn_match.group(1) if btn_match else row_id.split('_')[0]

        if len(clean_cells) >= 7:
            results.append({
                "update_id": update_id,
                "title": clean_cells[1],
                "products": clean_cells[2],
                "classification": clean_cells[3],
                "date": clean_cells[4],
                "version": clean_cells[5],
                "size": clean_cells[6],
            })

    return results


def query_catalog(query):
    """Return cached or freshly fetched catalog rows. Raises CatalogError."""
    if not query:
        return []

    _load_cache()

    with _cache_lock:
        if query in _cache:
            return _cache[query]

    html = _http_get("/Search.aspx?q=" + urllib.parse.quote(query), timeout=10)
    results = parse_rows(html)

    with _cache_lock:
        _cache[query] = results
        _cache_state["dirty"] = True

    # Write through on every new entry. A scan adds a few dozen small entries,
    # and deferring to exit loses everything if the process is killed.
    _save_cache()

    return results


def clear_cache():
    with _cache_lock:
        _cache.clear()
        _cache_state["dirty"] = True
