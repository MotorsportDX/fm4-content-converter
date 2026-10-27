# FM4 Content Converter

**`fm4-content-converter`** dikembangkan untuk mengonversi konten kendaraan dari
berbagai game ke **Forza Motorsport 4**. FM4 menjadi format tujuan, sementara
dukungan format sumber akan diperluas secara bertahap. Cakupan yang dituju
meliputi konfigurasi kendaraan, model, tekstur, dan metadata presentasi.

## Status dan arah pengembangan

Project masih berupa prototipe riset. Jalur yang saat ini diimplementasikan
adalah **FM3 → FM4**; dukungan game sumber lain masih direncanakan.

| Sumber | Status | Cakupan saat ini |
|---|---|---|
| Forza Motorsport 3 | Prototipe | Konversi database mobil stock, model dan tekstur, metadata UI, serta audit offline |
| Game lain | Direncanakan | Format dan cakupan akan ditentukan untuk setiap adapter sumber |

Jalur fisika FM3 telah dievaluasi pada panel 30 mobil. Impor aset dikembangkan
melalui Chevrolet Cobalt SS 2005: kandidat v6 pernah menjalani uji game singkat,
sedangkan kandidat v7 dengan perbaikan UI masih memerlukan uji game. Hasil ini
belum membuktikan dukungan seluruh mobil, kesamaan handling, atau DLC siap pasang.
Source dan dokumentasi implementasi FM3 berada di
[`src/fm4_converter/fm3`](src/fm4_converter/fm3/) dan [panduan FM3](docs/fm3.md).

Arah pengembangan berikutnya adalah menambahkan adapter pembaca untuk game
sumber lain, memetakan data dan asetnya ke kebutuhan FM4, serta memvalidasi
hasil setiap jalur melalui audit offline dan pengujian di game. Perbedaan
satuan, struktur, dan fitur antar-game perlu ditangani pada setiap adapter;
cakupan dukungan akan dicatat bersama batas validasinya.

## Struktur repository

```text
src/fm4_converter/       Package Python: adapter FM3 dan pembaca arsip bersama
tests/                  Tes regresi dan verifikasi package
docs/                   Panduan converter dan struktur project
tools/                  Source helper CPU C# dan wrapper LZX
research/               Source serta laporan riset lintas versi
outputs/                Hasil/evidence lokal; diabaikan Git
external/, work/        Dependensi dan eksperimen lokal; diabaikan Git
```

Lihat [panduan struktur](docs/architecture.md) untuk batas package, lokasi
fixture, dan cara menambahkan adapter game sumber lain.

## Setup Python

Gunakan Python **3.11 atau lebih baru, 64-bit**. Dari root repository di PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

Perintah memakai interpreter virtual environment secara langsung sehingga tidak
memerlukan aktivasi PowerShell. `.venv` dan paket terpasang tetap lokal dan
diabaikan Git. Versi NumPy dan Pillow dipin pada extra `full` di `pyproject.toml` agar setup
dapat direproduksi. Gunakan interpreter `.venv` yang sama untuk menjalankan
script dan tes.

Converter inti FM3 `converter.py`, termasuk adapter `--code-semantics`, hanya
memerlukan standard library. Untuk jalur ini, instal package dengan
`.\.venv\Scripts\python.exe -m pip install -e .`; dependensi extra `full`
bersifat opsional. NumPy diperlukan untuk fitting riset;
jalur thumbnail/pengemasan aset dan suite lengkap juga memerlukan Pillow.

## Menjalankan dan menguji

```powershell
.\.venv\Scripts\python.exe -m fm4_converter.fm3.converter --help
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_converter.py -v
# Setelah menginstal requirements.txt:
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Database dan aset game harus tersedia secara lokal. Default path database,
opsi `--fm3`/`--fm4`, contoh konversi, serta batas validasi dijelaskan di
[README jalur FM3 → FM4](docs/fm3.md). Tes database dapat skip
jika fixture lokal tidak tersedia; tes fitting dapat skip tanpa NumPy.
Discovery suite lengkap memerlukan kedua paket Python di atas sejak import.
Hasil tes lulus tidak membuktikan tampilan atau handling di game.

## Dependensi di luar pip

- Konversi model memerlukan helper CPU C# yang dibangun dengan compiler Windows
  .NET Framework 4.x, Git, serta source dan paket matematika pada revisi terpin.
  Ikuti [petunjuk build helper](tools/carbin_cpu/README.md).
- Pembacaan arsip method-21 memerlukan decoder lokal `lzx_bridge.dll` dari
  riset di `outputs/physics-research-2026-10-20/shared/`. Fallback XMem dan
  decoder Granny memerlukan DLL lokal dengan hash yang diperiksa; lihat
  [dokumentasi audit aset](docs/fm3.md).
- Audit executable memerlukan image dan alat disassembly lokal yang disebutkan
  pada dokumentasi converter.

`pip install -r requirements.txt` memasang package editable beserta NumPy dan
Pillow. Dependensi native disiapkan terpisah.
Data game, database hasil, DLL/EXE, virtual environment, cache, dan checkout
pihak ketiga tidak masuk Git. Folder `research/` hanya mengizinkan source dan laporan
yang tercantum secara eksplisit dalam `.gitignore`.
