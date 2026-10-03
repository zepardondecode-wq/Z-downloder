# Z-downloder

Downloader web bertema gothic hitam/transparan untuk media publik dari:

- TikTok video
- TikTok photo slideshow
- Instagram Reels/video publik
- Facebook Reels/video publik
- Pinterest video/image Pin

Backend utama: `yt-dlp` untuk TikTok/Instagram/Facebook. TikTok slideshow memakai resolver TikWM sebagai fallback khusus photo mode, lalu slide dapat dirender ke MP4 dengan FFmpeg. Pinterest mengikuti konsep script sumber pengguna: resolve `pin.it`, ambil OpenGraph media, lalu fallback scan JSON embedded untuk URL MP4. Ia juga mempertahankan prinsip bahwa konten privat/login tidak diakses.

## Jalankan lokal

```bash
docker build -t z-downloder .
docker run --rm -p 10000:10000 z-downloder
```

Buka `http://localhost:10000`.

## Deploy ke Render

Hubungkan repo GitHub ke Render, pilih **New → Web Service**, runtime Docker. Blueprint `render.yaml` sudah siap.

Render menjalankan container dengan `PORT`. Service sudah bind ke `0.0.0.0`.

Catatan: filesystem Render default bersifat ephemeral; aplikasi ini hanya memakai `/tmp` untuk file sementara dan menghapus file setelah response download selesai. Tidak dibutuhkan persistent disk untuk file hasil sementara.

Gunakan konten publik yang memang kamu punya izin untuk mengunduh/menggunakannya. Fitur login/cookie browser tidak disediakan.
