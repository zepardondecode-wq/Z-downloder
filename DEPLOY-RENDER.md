# Deploy Z-downloder ke Render.com

## Cara paling mudah

1. Buat repository GitHub baru.
2. Upload seluruh isi folder proyek ini.
3. Di Render: **New → Web Service**.
4. Pilih repository tersebut.
5. Pilih runtime **Docker**.
6. Biarkan Render membaca `Dockerfile`.
7. Health Check Path: `/health`.
8. Deploy.

`render.yaml` juga tersedia untuk Blueprint deploy.

## Environment

Tidak ada secret wajib. Port dibaca dari environment `PORT`.

## Setelah live

Buka URL `https://nama-service.onrender.com`.

## Catatan operasional

Render Free web service dapat spin down setelah idle. Download pertama setelah idle bisa terasa lebih lambat karena container perlu hidup kembali.

Hasil download tidak disimpan permanen. File dibuat di `/tmp`, dikirim sebagai response, lalu dibersihkan. Bila kamu ingin penyimpanan permanen/history server-side, tambahkan object storage atau persistent disk.
