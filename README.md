# FM4 Content Converter

Prototipe offline untuk mengonversi konfigurasi mobil stock dan aset FM3 ke
format FM4. Source utama berada di [`work/fm-car-converter`](work/fm-car-converter/README.md).
Hasil konversi masih memerlukan validasi game; proyek ini belum merupakan
converter seluruh mobil atau pembuat DLC siap pasang.

## Setup Python

Gunakan Python **3.11 atau lebih baru, 64-bit**. Dari root repository di PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

Perintah memakai interpreter virtual environment secara langsung sehingga tidak
memerlukan aktivasi PowerShell. `.venv` dan paket terpasang tetap lokal dan
diabaikan Git. Versi NumPy dan Pillow dipin di `requirements.txt` agar setup
dapat direproduksi. Gunakan interpreter `.venv` yang sama untuk menjalankan
script dan tes.

Converter inti `converter.py`, termasuk adapter `--code-semantics`, hanya
memerlukan standard library. Untuk jalur ini, pembuatan `.venv` cukup; instalasi
`requirements.txt` bersifat opsional. NumPy diperlukan untuk fitting riset;
jalur thumbnail/pengemasan aset dan suite lengkap juga memerlukan Pillow.

## Menjalankan dan menguji

```powershell
.\.venv\Scripts\python.exe work/fm-car-converter/converter.py --help
.\.venv\Scripts\python.exe -m unittest discover -s work/fm-car-converter -p test_converter.py -v
# Setelah menginstal requirements.txt:
.\.venv\Scripts\python.exe -m unittest discover -s work/fm-car-converter -p "test_*.py" -v
```

Database dan aset game harus tersedia secara lokal. Default path database,
opsi `--fm3`/`--fm4`, contoh konversi, serta batas validasi dijelaskan di
[README converter](work/fm-car-converter/README.md). Tes database dapat skip
jika fixture lokal tidak tersedia; tes fitting dapat skip tanpa NumPy.
Discovery suite lengkap memerlukan kedua paket Python di atas sejak import.
Hasil tes lulus tidak membuktikan tampilan atau handling di game.

## Dependensi di luar pip

- Konversi model memerlukan helper CPU C# yang dibangun dengan compiler Windows
  .NET Framework 4.x, Git, serta source dan paket matematika pada revisi terpin.
  Ikuti [petunjuk build helper](work/fm-car-converter/carbin_cpu/README.md).
- Pembacaan arsip method-21 memerlukan decoder lokal `lzx_bridge.dll` dari
  riset di `outputs/physics-research-2026-10-20/shared/`. Fallback XMem dan
  decoder Granny memerlukan DLL lokal dengan hash yang diperiksa; lihat
  [dokumentasi audit aset](work/fm-car-converter/README.md).
- Audit executable memerlukan image dan alat disassembly lokal yang disebutkan
  pada dokumentasi converter.

`pip install` hanya memasang NumPy dan Pillow, bukan dependensi native tersebut.
Data game, database hasil, DLL/EXE, virtual environment, cache, dan checkout
pihak ketiga tidak masuk Git. Folder riset hanya mengizinkan source dan laporan
yang tercantum secara eksplisit dalam `.gitignore`.
