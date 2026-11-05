# Konversi satu perintah dan format paket mod

`fm4_converter.cli` menjalankan seluruh jalur FM3 → FM4 atau FM2 → FM4 dari disc milik
pemain dan menghasilkan satu **paket mod**: berkas overlay untuk FM4 Disc 1 beserta
`mod.json` yang dibaca launcher, misalnya Motorsport DX. Converter tidak memasang paket
dan tidak menjalankan game.

## Menjalankan

```powershell
python -m fm4_converter.cli convert --game fm3 `
    --disc "<FM3 Disc 1: folder atau .iso>" --disc2 "<FM3 Disc 2: folder atau .iso>" `
    --fm4 "<folder FM4 Disc 1>" --content-root "<...\4D530910\00000002>" `
    --helper "<carbin-cpu.exe>" --out "<folder paket baru>" --json

python -m fm4_converter.cli convert --game fm2 `
    --disc "<disc FM2>" --bonus-disc "<Bonus Disc FM2>" `
    --fm4 "<folder FM4 Disc 1>" --content-root "<...>" --helper "<carbin-cpu.exe>" --out "<folder baru>"

python -m fm4_converter.cli identify "<folder atau .iso>"   # game, nomor disc, peran
python -m fm4_converter.cli verify "<folder paket>"         # cek hash setiap berkas
```

Setelah `pip install -e .`, perintah yang sama tersedia sebagai `fm4-convert`.

| Argumen | Isi |
|---|---|
| `--disc` | FM3 Disc 1 atau disc FM2. Folder hasil ekstrak (berisi `default.xex`), folder `Media`-nya, atau image `.iso` (Redump maupun hasil rebuild). |
| `--disc2` | FM3 Disc 2 (Content Install Disc), opsional. Tanpa disc ini, 26 mobil yang asetnya hanya ada di Disc 2 dilewati (`skipped`). |
| `--bonus-disc` | Bonus Disc FM2, opsional. Tanpa disc ini, empat mobil DLC FM2 dilewati. |
| `--fm4` | Folder FM4 Disc 1 yang sudah diekstrak, yaitu folder yang dimainkan launcher. Image FM4 ditolak. |
| `--content-root` | DLC FM4 yang terpasang. Kunci database dan tabel nama dari pack ini dihormati, jadi bangun paket terhadap DLC yang benar-benar dimiliki pemain. |
| `--helper` | `carbin-cpu.exe` hasil [build helper](../tools/carbin_cpu/README.md). Paket yang sudah diuji dibuat dengan `carbin-cpu-v9`. |
| `--cache` | Folder untuk berkas yang diekstrak dari `.iso`, DLC FM2 dan model FM2. Bila diberikan, folder ini disimpan supaya proses berikutnya bisa melanjutkan. Bila tidak, dipakai `<out>.cache` yang dihapus setelah berhasil. |
| `--cars` | Hanya MediaName tertentu. |
| `--json` | Progres sebagai JSON lines di stdout; log converter pindah ke stderr. |

Setiap disc dicek dari `default.xex` (title ID dan nomor disc) sebelum konversi dimulai,
sehingga disc yang salah ditolak dengan pesan yang jelas. Dari image, hanya folder yang
dibutuhkan yang diekstrak: database, mobil, velg, tabel nama dan thumbnail; untuk Disc 2 dan
Bonus Disc, paket kontennya.

Kalibrasi diambil dari data beku di [`src/fm4_converter/data`](../src/fm4_converter/data/__init__.py),
yaitu aturan yang dipakai paket `fm3-only-v3` dan FM2 `package-v5`. Setiap berkas dicek
dengan SHA-256 saat dibaca.

## Event progres (`--json`)

Satu objek JSON per baris:

```json
{"event": "stage", "stage": "check", "message": "Checking the discs"}
{"event": "extract", "role": "fm3-disc1", "file": "Media/Cars/X.zip", "done": 123, "total": 456}
{"event": "stage", "stage": "package", "message": "Converting 81 FM3 cars"}
{"event": "car", "index": 1, "total": 81, "car": "CHE_Cobalt_05", "status": "packaged", "error": null}
{"event": "done", "package": "...", "mod": "...\\mod.json", "packaged": 81, "failed": 0, "skipped": 0}
{"event": "error", "message": "DiscError: ..."}
```

`stage` bernilai `check`, `extract`, `dlc` (khusus FM2), `package`, lalu `describe`. Event
`extract` dikirim paling sering dua kali per detik. Kode keluar 0 berarti paket selesai dan
lolos `verify`; 1 berarti ada event `error`. Mobil yang gagal tidak menghentikan mobil lain;
paket tetap ditulis selama minimal satu mobil berhasil.

## Isi paket

```text
<paket>/
  mod.json         Dibaca launcher
  files/Media/...  Overlay dengan tata letak FM4 Disc 1
  manifest.json    Manifest lengkap converter (input, hash, keputusan per mobil)
  reports/         Laporan audit per mobil
```

## `mod.json`, versi 1

| Field | Isi |
|---|---|
| `format`, `format_version` | `"fm4-mod"`, `1` |
| `id`, `name`, `kind`, `source_game` | Misalnya `"fm3-cars"`, `"FM3 cars"`, `"car-overlay"`, `"FM3"` |
| `created`, `converter` | Waktu UTC, nama dan versi converter |
| `experimental` | Selalu `true` untuk sekarang |
| `files_root` | `"files"` |
| `files` | `{path: {sha256, size}}` untuk setiap berkas di `files/` |
| `replaces` | Path yang sudah ada di FM4 Disc 1 dan diganti (database gabungan, `zipmanifest.xml`) |
| `adds` | Path baru (ZIP mobil dan velg, `stringtables.zip`, `Thumbnails.zip`, audio) |
| `writes` | `replaces` + `adds`, untuk cek konflik |
| `cars` | `[{media, name, status, requires, error}]`, dengan status `packaged`, `failed` atau `skipped` |
| `packaged`, `failed` | Jumlah mobil |
| `requires` | Pack DLC FM4 yang dibutuhkan sebagian mobil (misalnya Porsche Expansion) |
| `sources` | Disc yang dibaca: peran, path, folder atau iso, title ID, nomor disc, media ID |
| `built_against` | FM4 Disc 1 (media ID, hash `gamedb.slt` dan `zipmanifest.xml`) dan daftar pack DLC (path relatif dan ukuran) yang dipakai saat membangun |
| `notes` | Catatan untuk ditampilkan ke pemain |

## Aturan untuk launcher

1. Jalankan `verify` (atau cek `files` sendiri) sebelum memasang.
2. Pasang hanya bila FM4 Disc 1 dan pack DLC pemain sama dengan `built_against`. Bila
   berbeda, minta pemain membangun ulang paket: database dan tabel nama di paket adalah
   salinan gabungan dari keadaan saat dibangun.
3. Pasang tanpa menulis ke disc asli: salin atau hardlink disc, lalu ganti berkas di
   `writes` dengan salinan baru, seperti [`fm3.test_disc`](../src/fm4_converter/fm3/test_disc.py).
4. Dua mod yang menulis path yang sama tidak bisa dipasang bersamaan
   (`fm4_converter.mod.conflicts`). Paket FM3 dan FM2 sama-sama mengganti `gamedb.slt`,
   `zipmanifest.xml`, `stringtables.zip` dan `Thumbnails.zip`, jadi untuk sekarang hanya
   satu yang bisa aktif. Menggabungkan keduanya butuh tahap merge yang belum ada.
5. Tampilkan `notes` dan status `failed`/`skipped` dari `cars` kepada pemain.

## Verifikasi 5 November 2026

Dijalankan dari folder disc USA (FM3 Disc 1 + 2, FM2 + Bonus Disc), FM4 Japan/Asia Disc 1
dan content root uji Motorsport DX, dengan `carbin-cpu-v9`:

| Jalur | Hasil | Dibanding paket teruji |
|---|---|---|
| FM3 | 81 dari 81 mobil, 8,5 menit | 119 dari 119 berkas identik dengan `fm3-only-v3` |
| FM2 | 55 dari 55 mobil, 3,7 menit (DLC sudah di cache) | 80 dari 103 berkas identik dengan `package-v5`; donor sama untuk 55 mobil |

Ke-23 berkas FM2 yang berbeda adalah ZIP mobil (dan `zipmanifest.xml`, yang mencatat
ukurannya). Di setiap ZIP hanya `_cockpit.carbin` yang berbeda. `package-v5` memakai ulang
model kokpit dari cache `models/` yang dibuat 4 November pukul 14:03, sebelum
`models.cockpit_renames` diubah dari nama material saja menjadi pasangan bagian/material
(commit `00b4be9`). CLI membangun model baru dengan aturan sekarang. Kokpit ke-23 mobil itu
belum diuji di game dengan aturan baru; mobil yang terdampak antara lain JAG_XK_07, Lancer
Evo VI–IX, RX-7 (INGS, AB Flug, RE Amemiya), Lotus Elise/Exige, dan Celica APR.

Pembacaan `.iso` diuji pada image FM4 USA Disc 1 dan Disc 2 (partisi XGD3): `gamedb.slt`
hasil baca identik dengan folder ekstrak. Image FM2 dan FM3 belum tersedia untuk diuji;
tes memakai image XDVDFS sintetis pada offset partisi 0 dan XGD3.

## Batas

- Converter tetap butuh Python 3.11+, NumPy, Pillow, `carbin-cpu.exe`, dan decoder LZX
  `lzx_bridge.dll` ([`tools/lzx_bridge`](../tools/lzx_bridge/lzx_bridge.c) dengan `lzxd.c`
  libmspack). Variabel lingkungan `FM4_LZX_BRIDGE` menunjuk DLL itu; tanpa variabel ini
  dipakai build riset di `outputs/`. Launcher menyiapkan semuanya di komputer pemain.
- Image FM4 tidak diterima. Launcher sudah punya FM4 Disc 1 yang diekstrak.
- Data kalibrasi beku hanya mewakili rilis disc yang diuji: FM3 USA, FM2 USA, dan FM4
  USA atau Japan/Asia (database identik).
