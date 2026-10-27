# Struktur project

```text
src/fm4_converter/
  fm3/                 Converter sumber FM3, pengemasan, audit dan studi kalibrasi
  archives/            Pembaca ZIP Forza dan STFS yang dipakai bersama
  paths.py             Lokasi checkout, tools dan evidence lokal
tests/
  fm3/                 Regresi konversi, fisika, aset dan UI FM3 → FM4
  test_project_layout.py
docs/
  fm3.md               Panduan dan hasil validasi jalur FM3 → FM4
tools/
  carbin_cpu/          Source helper C# dan lisensi
  lzx_bridge/          Source wrapper decoder LZX
research/
  physics-2026-10-20/   Source dan laporan riset lintas versi
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
Belum ada adapter game sumber lain yang diimplementasikan.

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
