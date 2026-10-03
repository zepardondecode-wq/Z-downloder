import html
import re
from urllib.parse import urlparse

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
}


def _resolve_url(url: str) -> str:
    try:
        r = requests.head(url, headers=HEADERS, allow_redirects=True, timeout=15)
        return r.url or url
    except Exception:
        r = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=20, stream=True)
        final = r.url or url
        r.close()
        return final


def _extract_meta(text: str, prop: str):
    patterns = [
        rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(prop)}["\']',
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return html.unescape(m.group(1))
    return None


def _to_original_image(url: str) -> str:
    return re.sub(r"/\d+x(?:\d+)?/", "/originals/", url)


def _extract_video_from_json(text: str):
    candidates = re.findall(r'"url":"(https:[^"]+?\.mp4[^"]*)"', text)
    if not candidates:
        return None
    cleaned = [c.encode().decode("unicode_escape") for c in candidates]
    priority = ["V_HLSV4", "V_720P", "V_EXP7", "V_480P", "V_360P"]
    for tag in priority:
        for item in cleaned:
            if tag in item:
                return item
    return cleaned[0]


def extract_pinterest(url: str) -> dict:
    final_url = _resolve_url(url)
    page = requests.get(final_url, headers=HEADERS, timeout=20)
    page.raise_for_status()
    text = page.text

    video_url = _extract_meta(text, "og:video:secure_url") or _extract_meta(text, "og:video")
    if not video_url:
        video_url = _extract_video_from_json(text)
    if video_url:
        return {
            "kind": "video",
            "title": _extract_meta(text, "og:title") or "Pinterest Pin",
            "thumbnail": _extract_meta(text, "og:image"),
            "url": final_url,
            "media_url": video_url,
        }

    image_url = _extract_meta(text, "og:image")
    if image_url:
        return {
            "kind": "image",
            "title": _extract_meta(text, "og:title") or "Pinterest Pin",
            "thumbnail": _to_original_image(image_url),
            "url": final_url,
            "media_url": _to_original_image(image_url),
        }

    raise ValueError("Media Pinterest tidak ditemukan. Pin mungkin privat, terhapus, atau berubah strukturnya.")
