from urllib.parse import quote
import requests

BASE = "https://www.tikwm.com/api/"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"


def resolve_tiktok(url: str) -> dict:
    headers = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    r = requests.get(BASE, params={"url": url, "hd": 1}, headers=headers, timeout=30)
    r.raise_for_status()
    payload = r.json()
    if payload.get("code") not in (0, "0"):
        raise ValueError(payload.get("msg") or "TikWM gagal mengambil data TikTok")
    data = payload.get("data") or {}
    images = data.get("images") or data.get("image_post") or []
    if images:
        return {
            "kind": "slideshow",
            "title": data.get("title") or "TikTok Photo",
            "thumbnail": data.get("cover") or data.get("origin_cover"),
            "images": images,
            "music": (data.get("music") or ""),
            "id": data.get("id"),
            "author": (data.get("author") or {}).get("unique_id") if isinstance(data.get("author"), dict) else None,
        }
    video = data.get("hdplay") or data.get("play") or data.get("wmplay")
    if video:
        return {
            "kind": "video",
            "title": data.get("title") or "TikTok Video",
            "thumbnail": data.get("cover") or data.get("origin_cover"),
            "media_url": video,
            "music": data.get("music"),
            "author": (data.get("author") or {}).get("unique_id") if isinstance(data.get("author"), dict) else None,
        }
    raise ValueError("TikWM tidak mengembalikan media untuk URL tersebut.")
