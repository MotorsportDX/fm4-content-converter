# Metode dan reproduksi riset fisika Forza

Seluruh pekerjaan dilakukan lokal terhadap folder yang diberikan. Tidak ada pencarian web, unduhan dependensi, game/emulator/installer, atau eksekusi SQL yang berasal dari paket game. Pembacaan menggunakan Python 3.11, SQLite read-only/in-memory, ZIP parser, parser STFS, dan decoder data LZX lokal. Executable game dan title-update patches tidak dijalankan atau diterapkan.

## Isi repo dan hasil lokal

Repo menyertakan enam dokumen riset dan source alat analisis yang ditinjau. Hasil JSON/CSV/schema, salinan metadata SQL/XML/SQLite, binary decoder, disassembly, loaded image, serta cache Python tetap diabaikan Git. Laporan dapat dibaca langsung setelah clone; evidence perlu dibuat kembali menggunakan data game milik pengguna.

Path sumber `D:\Data` pada script adalah lokasi koleksi yang diteliti. Sesuaikan konstanta `ROOT`, `ROOTS`, `BASE`, `JP` atau `JP2` pada script terkait jika lokasi koleksi berbeda. Source SDK, libmspack dan image lama dalam `work/` tidak ikut clone. Siapkan dependensi tersebut secara lokal bila ingin menjalankan tahap yang membutuhkannya; script riset tidak mengunduhnya.

## Sumber dan pemisahan versi

| Versi | Root sumber |
|---|---|
| FM2 | `D:\Data\FM2\USA` |
| FM3 | `D:\Data\FM3\USA` |
| FM3 Ultimate Collection | `D:\Data\FM3\USA Ultimate Collection` |
| FM4 | `D:\Data\forza-motorsport-4` |

Setiap laporan menjabarkan nama direktori disc lengkap. FM4 baseline memakai extracted Japan/Asia di root; versi USA dibandingkan untuk file inti dan sampel aset. Folder `mods` bukan baseline. Delapan DLC dan tiga TU yang benar-benar ditemukan dicatat satu per satu. File yang berada dalam container tidak dihitung sebagai file filesystem loose. Metadata game asli dicatat dengan ejaan/ID aslinya.

## Lapisan pemeriksaan

1. Inventori direktori, ukuran, extension dan sumber media; SHA256 file penting dan paket.
2. SQLite dibuka dengan URI `mode=ro`, beberapa analisis juga `immutable=1`. DB di dalam paket dideserialize ke memori atau diekstrak ke output lokal terpilih, lalu dibaca. Tidak ada source database yang dimutasi.
3. Schema, jumlah baris, primary key dan relasi komponen diperiksa. Stock menggunakan `IsStock=1`. Patch tables dapat tidak memiliki PK; pembanding memakai PK schema base bila tersedia. Perbedaan skema struktural dibedakan dari whitespace SQL schema.
4. INI/XML dibaca sebagai parameter, bukan bukti eksekusi. Unit dinyatakan hanya bila didukung nama field/konteks; sisanya dipertahankan native.
5. File table STFS dibaca tanpa mounting atau instalasi. Inner ZIP besar dibaca melalui file-like seekable interface supaya metadata kecil tidak memerlukan ekstraksi seluruh aset.
6. ZIP compression method21 didekode dengan LZX dari libmspack yang sudah tersedia lokal. Output harus cocok dengan ukuran dan CRC32 ZIP. XML diurai, SQLite diperiksa integritasnya, dan arrays MLP diperiksa offset/bounds yang tersedia.
7. Perbandingan lintas versi memisahkan definisi data, asset availability, metadata install/unlock, dan executable. Shared IDs tidak otomatis berarti perilaku identik.

## Parser dan ketepatan bukti

`src/fm4_converter/archives/stfs_reader.py` mengimplementasikan layout dari source lokal ReXGlue/Xenia:

- `work/rexglue-sdk/include/rex/filesystem/devices/stfs_xbox.h`
- `work/rexglue-sdk/src/filesystem/devices/stfs_container_device.cpp`

Execution metadata menggunakan offset Media ID `0x354`, Version `0x358`, BaseVersion `0x35C`, Title ID `0x360`. Parser memeriksa rentang pembacaan, siklus block chain, jumlah alokasi, dan SHA1 payload blocks terpilih. `src/fm4_converter/archives/stfs_zip_io.py` menyediakan random access terhadap isi file STFS dan memeriksa SHA1 setiap blok data yang diakses.

**Batas validasi:** SHA1 dibandingkan dengan hash entry di paket yang sama. Seluruh ancestry hash tree, directory block digest dan signature Microsoft tidak diautentikasi. Listing ZIP hanya memvalidasi struktur central-directory; CRC payload diperiksa untuk member yang benar-benar dibaca/didekompresi. Aset grafis/audio yang hanya terdaftar tidak diklaim seluruhnya tervalidasi.

`src/fm4_converter/archives/forza_zip.py` membaca frame length, melepas framing ZIP method21, lalu memanggil `shared/lzx_bridge.dll`. Bridge adalah decoder data buatan riset yang ditautkan ke **libmspack lokal**, bukan executable game. Decoder mencoba ukuran window yang tersedia dan hanya menerima hasil yang cocok dengan ukuran dan CRC32. Kecocokan itu membuktikan payload terdecode dengan konsisten; tidak membuktikan semua arsip method21 di luar dataset memakai satu window universal.

Source pihak ketiga ada di `work/XenonRecomp/thirdparty/libmspack/libmspack/mspack/lzxd.c`; lisensinya terdapat pada source tree libmspack. Source decoder pihak ketiga tidak disalin ke paket laporan. Atribusi sumber STFS mengacu pada [pemberitahuan ReXGlue/Xenia](../../outputs/FM4-source-control/third-party-notices/ReXGlue-LICENSE.txt) (artefak lokal). File `lzx_bridge.c` adalah wrapper kecil untuk runtime lokal. Distribusi ulang binary di luar mesin ini memerlukan penanganan lisensi dependensinya.

Cross-reference FM4 adalah tahap opsional yang memerlukan `work/fm4/loaded-image.bin` dan `work/fm4/sections.tsv`, keduanya artefak lokal yang tidak ikut clone. `static_xrefs.py` membaca image sebagai data dan menghasilkan kandidat referensi; disassembly historis memakai alat lokal terpisah dan `static_xrefs_disassembly.txt` tidak dibuat ulang oleh script tersebut. Hash image dan alamat tersedia di `fm4/static_xrefs.json`. Provenance image belum diikat ulang ke XEX input, sehingga temuan tersebut merupakan tambahan, bukan landasan untuk menyatakan perilaku build retail tertentu.

## Reproduksi inti

Dari root repository, setelah [instalasi editable](../../README.md#setup-python),
dengan interpreter `.venv` yang sama:

```powershell
python research\physics-2026-10-20\cross_version.py
python research\physics-2026-10-20\research_dlc.py
python research\physics-2026-10-20\finalize_dlc.py
```

Contoh di atas hanya membentuk perbandingan lintas versi dan evidence/laporan DLC. Untuk pemeriksaan `validate_outputs.py`, seluruh evidence per-game harus sudah tersedia; script itu bukan tes yang dapat dijalankan pada clone tanpa data. Setelah seluruh output tersedia, jalankan `python research\physics-2026-10-20\validate_outputs.py`.

Source/laporan yang dilacak Git berada di `research/physics-2026-10-20`.
Pembaca arsip bersama berada di `src/fm4_converter/archives`; source wrapper
LZX berada di `tools/lzx_bridge`.

Skrip menulis ulang **hasil riset di `outputs/physics-research-2026-10-20`**, tidak sumber D:\Data. Path sumber tertera di script. `research_dlc.py` memerlukan DLL decoder hasil build lokal (tidak disertakan dalam Git) dan `stfs_zip_io.py`.

Untuk membangun ulang decoder, dari root workspace dengan source/toolchain lokal yang sama:

```powershell
& 'C:\Program Files\LLVM\bin\clang.exe' -shared -O2 `
  -I work\XenonRecomp\thirdparty\libmspack\libmspack\mspack `
  tools\lzx_bridge\lzx_bridge.c `
  work\XenonRecomp\thirdparty\libmspack\libmspack\mspack\lzxd.c `
  -o outputs\physics-research-2026-10-20\shared\lzx_bridge.dll
```

Urutan script per-game untuk evidence yang dicakup tooling tersedia dalam subfolder masing-masing: FM2 `analyze.py`, `deep_evidence.py`, `bonus_evidence.py`, `bonus_nested.py`, `mlp_evidence.py`; FM3 `research.py`, `compare.py`, `package_zip.py`, `decode_assets.py`, `finish_evidence.py`; FM4 `inspect_fm4.py`, `inspect_disc2.py`, `catalog_fm4.py`, `static_xrefs.py`. `fm3/disc2_packages.json` dan beberapa hasil inspeksi historis berasal dari pembacaan lokal terpisah dan tidak otomatis dibuat ulang oleh rangkaian script ini. Laporan final disusun dari keluaran tersebut dan diperiksa terpisah; menjalankan satu script tidak otomatis membangun ulang seluruh narasi laporan.

## Pembacaan istilah dan angka

- “Mobil” pada hitungan mentah adalah record Data_Car. FM4 mempunyai dua record non-drivable yang dijelaskan terpisah.
- “Track record” dapat berupa ribbon, reverse, section, drag, homespace/UI atau arena. Bukan otomatis sirkuit unik.
- “Union base+paket” menghitung ID unik tanpa memasang paket. Bukan klaim menu runtime atau lisensi aktif.
- “Data sama” dapat berarti hash byte identik atau nilai field sama; laporan menyebut jenis pembandingnya. CRC+size+method member tidak sama dengan hash seluruh archive.
- “Konfigurasi Hz” bukan pengukuran cadence. Nilai raw 239/359 tidak dijadikan bukti 240/360 Hz.
- “Friction curve” adalah data lookup yang ditemukan; nama ini tidak menetapkan rumus ban komersial tertentu.
- “Terkonfirmasi” berlaku pada fakta yang dibaca, bukan otomatis pada penafsiran fisika dan alur runtime.

Kebutuhan riset lanjutan yang paling menentukan: `.col` topology/material binding, unit/axis conversion, pemilihan dan interpolasi kurva, combined slip, urutan modifier dan integrator, serta semantik patch executable. Semua itu masih dapat diperdalam melalui analisis statis offline.
