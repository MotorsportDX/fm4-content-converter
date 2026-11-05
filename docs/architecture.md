# Struktur project

```text
src/fm4_converter/
  fm3/                 Converter sumber FM3, pengemasan, audit dan studi kalibrasi
  fm2/                 Adapter mobil FM2-only: model, fisika, dan paket overlay
  archives/            Pembaca ZIP Forza, STFS, dan image disc Xbox 360 (xiso)
  data/                Data kalibrasi beku untuk CLI (dicek dengan SHA-256)
  cli.py               Konversi satu perintah dari disc pemain ke paket mod
  discs.py             Disc sebagai folder atau .iso, dicek dari default.xex
  mod.py               Format paket mod (mod.json) untuk launcher
  paths.py             Lokasi checkout, tools dan evidence lokal
tests/
  fm3/                 Regresi konversi, fisika, aset dan UI FM3 → FM4
  fm2/                 Regresi pembaca .carbin FM2, transkode, fisika dan pengemasan
  test_project_layout.py
docs/
  fm3.md               Panduan dan hasil validasi jalur FM3 → FM4
  mod-format.md        CLI satu perintah, event progres dan format mod.json
tools/
  carbin_cpu/          Source helper C# dan lisensi
  lzx_bridge/          Source wrapper decoder LZX
research/
  physics-2026-10-20/   Source dan laporan riset lintas versi
  cars-fm2-2026-11-02/  Laporan dan skrip audit riset mobil FM2
third_party/           Snapshot teks lisensi/notice upstream dan manifest hash
outputs/               Hasil konversi, evidence dan decoder lokal; diabaikan Git
external/              Checkout pihak ketiga lokal; diabaikan Git
work/                  Workspace eksperimen lama lokal; diabaikan Git
```

## Package dan cara menjalankan

Project memakai layout `src` dan diinstal sebagai editable checkout. Instalasi
`pip install -e .` menyediakan package `fm4_converter` tanpa dependensi eksternal.
`pip install -r requirements.txt` memasang checkout yang sama dengan extra
`full` dari `pyproject.toml` untuk NumPy, Pillow, dan seluruh suite tes.

Jalankan modul menggunakan nama package, misalnya:

```powershell
.\.venv\Scripts\python.exe -m fm4_converter.fm3.converter --help
.\.venv\Scripts\python.exe -m fm4_converter.fm3.offline_package --help
.\.venv\Scripts\python.exe -m fm4_converter.fm3.build_carbin_cpu --help
.\.venv\Scripts\python.exe -m fm4_converter.fm2.package --help
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

File Python di dalam `src` menggunakan import package; menjalankannya langsung
sebagai path file tidak didukung. Package FM3 tidak diimpor otomatis dari
`fm4_converter`, sehingga import converter inti tetap memakai standard library.
Helper native tetap dibangun terpisah menggunakan petunjuk di
[`tools/carbin_cpu`](../tools/carbin_cpu/README.md) dan
[`METHODS.md`](../research/physics-2026-10-20/METHODS.md).

## Menambah sumber game

Implementasi FM3 berada di `fm4_converter.fm3`. Adapter untuk game sumber lain
dapat ditambahkan sebagai subpackage tersendiri dengan tes dan dokumentasi
masing-masing. Pembaca arsip bersama berada di `archives`; aturan kalibrasi
FM3 tetap berada dalam package FM3 karena belum terbukti berlaku lintas game.

`fm4_converter.fm2` adalah adapter kedua, untuk mobil FM2 yang tidak ada di FM3
maupun FM4. Ia memakai ulang back-end FM3 → FM4: `transcode` menulis model FM2
sebagai model FM3, lalu helper `carbin-cpu` membuat model FM4. `models` membuat
model utama, `_lod0`, `_cockpit` dan velg; `physics` memuat studi kalibrasi
FM2 → FM4 sendiri; `package` menulis semua mobil ke satu overlay. Riset dan
batas validasinya ada di
[`research/cars-fm2-2026-11-02/REPORT.md`](../research/cars-fm2-2026-11-02/REPORT.md);
cara menjalankannya ada di [panduan FM2](fm2.md).

## CLI satu perintah dan data beku

`cli` memanggil `fm3.batch_package` atau `fm2.package` dengan path disc pemain. Untuk FM2,
lokasi disc diarahkan lewat `fm2.sources.configure`. Kalibrasi tidak dibaca dari `outputs/`,
melainkan dari `data/`, salinan beku hasil yang dipakai paket teruji. Bila aturan baru
diterima, perbarui berkas di `data/` beserta hash dan asalnya di `data/__init__.py`.
Format keluaran dan aturan pemasangan ada di [format paket mod](mod-format.md).

## Evidence dan riset

Pemindahan source tidak memindahkan database, aset, image executable, DLL, atau
hasil eksperimen lama. `paths.py` mempertahankan lokasi evidence di bawah
`outputs/`, termasuk `outputs/fm-car-converter/` dan
`outputs/physics-research-2026-10-20/`. Decoder `lzx_bridge.dll` tetap dicari di
`outputs/physics-research-2026-10-20/shared/`.

Script riset historis di `research/physics-2026-10-20/` dijalankan sebagai path
script setelah instalasi editable. Mereka membaca/menulis evidence di lokasi
`outputs` yang sama seperti sebelumnya. Laporan di `research` merupakan catatan
yang dilacak Git; laporan yang dihasilkan ulang ditulis ke `outputs`.
Script riset dapat langsung membaca koleksi lokal atau menulis ulang hasil
riset ketika dijalankan; script tersebut bukan bagian dari test discovery.

`.gitignore` menggunakan daftar file yang diizinkan secara eksplisit. Saat
menambahkan source atau dokumentasi baru, tambahkan path file tersebut ke daftar;
hasil ekstraksi dan binary tetap lokal.

Kredit dan asal komponen dicatat di [CREDITS.md](../CREDITS.md), dengan pemetaan
penggunaan pada [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). Isi
`third_party/` hanya teks lisensi/notice serta metadata atribusi; source dan
binary dependency eksternal tetap disiapkan terpisah.
