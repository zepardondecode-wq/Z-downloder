import ipaddress
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import requests
import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from .pinterest_adapter import extract_pinterest
from .tikwm import resolve_tiktok

APP = FastAPI(title="Z-downloder", version="1.0.0")
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TMP_DIR = Path(tempfile.gettempdir()) / "z-downloder"
TMP_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_HOSTS = {
    "tiktok.com", "www.tiktok.com", "m.tiktok.com", "vt.tiktok.com", "vm.tiktok.com",
    "instagram.com", "www.instagram.com", "m.instagram.com",
    "facebook.com", "www.facebook.com", "m.facebook.com", "fb.watch",
    "pinterest.com", "www.pinterest.com", "pin.it",
}


def is_allowed_public_url(url: str) -> bool:
    try:
        p = urlparse(url)
        if p.scheme not in {"http", "https"} or not p.hostname:
            return False
        host = p.hostname.lower().rstrip(".")
        if host in ALLOWED_HOSTS or any(host.endswith("." + base) for base in ALLOWED_HOSTS):
            return True
        # explicit deny for private/local targets even if a malicious redirect is supplied later
        try:
            ip = ipaddress.ip_address(host)
            return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)
        except ValueError:
            return False
    except Exception:
        return False


def platform_for(url: str) -> str:
    host = urlparse(url).hostname.lower()
    if "tiktok" in host:
        return "tiktok"
    if "instagram" in host:
        return "instagram"
    if "facebook" in host or host == "fb.watch":
        return "facebook"
    if "pinterest" in host or host == "pin.it":
        return "pinterest"
    raise HTTPException(400, "Platform tidak didukung.")


def safe_name(value: str, fallback: str = "z-downloder") -> str:
    value = re.sub(r"[^\w\- ]+", "", value, flags=re.UNICODE).strip()
    return (value[:100] or fallback).replace(" ", "_")


def yt_metadata(url: str) -> dict:
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def cleanup(path: str):
    try:
        p = Path(path)
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        else:
            p.unlink(missing_ok=True)
    except Exception:
        pass


def download_with_ytdlp(url: str, mode: str, title: str | None = None) -> Path:
    job = Path(tempfile.mkdtemp(prefix="job_", dir=TMP_DIR))
    stem = safe_name(title or "download")
    outtmpl = str(job / (stem + ".%(ext)s"))
    postprocessors = []
    if mode == "mp3":
        fmt = "bestaudio/best"
        postprocessors = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    else:
        fmt = "bv*+ba/b"
        postprocessors = [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}]

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": fmt,
        "merge_output_format": "mp4" if mode == "mp4" else None,
        "outtmpl": outtmpl,
        "postprocessors": postprocessors,
        "retries": 2,
        "socket_timeout": 30,
    }
    if opts["merge_output_format"] is None:
        opts.pop("merge_output_format")

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        candidates = sorted(job.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        candidates = [p for p in candidates if p.is_file() and not p.name.endswith(".part")]
        if not candidates:
            raise RuntimeError("yt-dlp selesai tetapi file hasil tidak ditemukan.")
        return candidates[0]
    except Exception:
        cleanup(str(job))
        raise


def resolve_tiktok_payload(url: str) -> dict:
    try:
        payload = resolve_tiktok(url)
        return payload
    except Exception:
        # TikWM is the slideshow fallback. Regular video then falls back to yt-dlp.
        try:
            info = yt_metadata(url)
            return {
                "kind": "video" if info.get("duration") is not None else "unknown",
                "title": info.get("title") or "TikTok",
                "thumbnail": info.get("thumbnail"),
                "author": info.get("uploader"),
                "yt": True,
            }
        except Exception as exc:
            raise HTTPException(502, f"TikTok gagal diproses: {exc}")


def download_direct(url: str, ext: str = ".bin") -> Path:
    job = Path(tempfile.mkdtemp(prefix="direct_", dir=TMP_DIR))
    filename = safe_name(Path(urlparse(url).path).stem or "media") + ext
    path = job / filename
    with requests.get(url, stream=True, timeout=45, headers={"User-Agent": "Mozilla/5.0"}) as r:
        r.raise_for_status()
        with path.open("wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)
    return path


def make_slideshow_mp4(images: list[str], title: str, music_url: str | None = None) -> Path:
    job = Path(tempfile.mkdtemp(prefix="slideshow_", dir=TMP_DIR))
    list_file = job / "concat.txt"
    img_dir = job / "images"
    img_dir.mkdir()
    local_images = []
    for i, image_url in enumerate(images):
        ext = ".jpg"
        try:
            path = urlparse(image_url).path
            if "." in Path(path).name:
                ext = Path(path).suffix[:5]
        except Exception:
            pass
        out = img_dir / f"img_{i:03d}{ext if ext in {'.jpg', '.jpeg', '.png', '.webp'} else '.jpg'}"
        with requests.get(image_url, stream=True, timeout=45, headers={"User-Agent": "Mozilla/5.0"}) as r:
            r.raise_for_status()
            with out.open("wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    if chunk:
                        f.write(chunk)
        local_images.append(out)

    with list_file.open("w", encoding="utf-8") as f:
        for img in local_images:
            f.write(f"file '{img.as_posix().replace("'", "'\\''")}'\n")
            f.write("duration 2.5\n")
        if local_images:
            f.write(f"file '{local_images[-1].as_posix().replace("'", "'\\''")}'\n")

    output = job / f"{safe_name(title, 'tiktok_slideshow')}.mp4"
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p",
        "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart"
    ]
    audio_path = None
    if music_url:
        try:
            audio_path = download_direct(music_url, ".mp3")
            cmd += ["-i", str(audio_path), "-shortest", "-c:a", "aac", "-b:a", "192k"]
        except Exception:
            pass
    cmd += [str(output)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    return output


class ResolveRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


class DownloadRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    format: Literal["mp4", "mp3"] = "mp4"


@APP.get("/health")
def health():
    return {"status": "ok", "service": "z-downloder"}


@APP.post("/api/resolve")
def resolve(req: ResolveRequest):
    url = req.url.strip()
    if not is_allowed_public_url(url):
        raise HTTPException(400, "URL tidak valid atau domain tidak didukung.")
    platform = platform_for(url)
    try:
        if platform == "pinterest":
            data = extract_pinterest(url)
        elif platform == "tiktok":
            payload = resolve_tiktok_payload(url)
            data = {
                "kind": "video" if payload.get("kind") == "video" else payload.get("kind", "video"),
                "title": payload.get("title") or "TikTok",
                "thumbnail": payload.get("thumbnail"),
                "author": payload.get("author"),
            }
            if payload.get("images"):
                data["image_count"] = len(payload["images"])
        else:
            info = yt_metadata(url)
            data = {
                "kind": "video",
                "title": info.get("title") or platform.title(),
                "thumbnail": info.get("thumbnail"),
                "author": info.get("uploader") or info.get("channel"),
                "duration": info.get("duration"),
            }
        return {"ok": True, "platform": platform, "data": data}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Gagal mengambil metadata: {exc}")


@APP.post("/api/download")
def download(req: DownloadRequest):
    url = req.url.strip()
    if not is_allowed_public_url(url):
        raise HTTPException(400, "URL tidak valid atau domain tidak didukung.")
    platform = platform_for(url)

    temp_path = None
    try:
        if platform == "tiktok":
            payload = resolve_tiktok(url)
            if payload.get("kind") == "slideshow":
                if req.format == "mp3":
                    music = payload.get("music")
                    if not music:
                        raise HTTPException(400, "Slideshow ini tidak menyediakan audio yang bisa diekstrak.")
                    temp_path = download_direct(music, ".mp3")
                else:
                    temp_path = make_slideshow_mp4(payload.get("images") or [], payload.get("title") or "tiktok_slideshow", payload.get("music"))
            else:
                temp_path = download_with_ytdlp(url, req.format, payload.get("title"))
        elif platform == "pinterest":
            data = extract_pinterest(url)
            if data["kind"] == "image" and req.format == "mp4":
                raise HTTPException(400, "Pin gambar tidak punya track video. Gunakan format MP3 hanya bila tersedia di video Pin.")
            if data["kind"] == "image" and req.format == "mp3":
                raise HTTPException(400, "Pin gambar tidak memiliki audio.")
            if req.format == "mp4":
                temp_path = download_direct(data["media_url"], ".mp4")
            else:
                src = download_direct(data["media_url"], ".mp4")
                out = src.with_suffix(".mp3")
                subprocess.run(["ffmpeg", "-y", "-i", str(src), "-vn", "-codec:a", "libmp3lame", "-q:a", "2", str(out)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                temp_path = out
        else:
            info = yt_metadata(url)
            temp_path = download_with_ytdlp(url, req.format, info.get("title"))

        media = mimetypes.guess_type(temp_path.name)[0] or ("audio/mpeg" if req.format == "mp3" else "video/mp4")
        headers = {"Content-Disposition": f'attachment; filename="{temp_path.name}"'}
        return FileResponse(str(temp_path), media_type=media, headers=headers, background=BackgroundTask(cleanup, str(temp_path.parent)))
    except HTTPException:
        if temp_path:
            cleanup(str(temp_path.parent))
        raise
    except Exception as exc:
        if temp_path:
            cleanup(str(temp_path.parent))
        raise HTTPException(502, f"Download gagal: {exc}")


APP.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
