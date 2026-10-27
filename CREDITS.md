# Credits

FM4 Content Converter berterima kasih kepada para pembuat tool, peneliti format,
dan kontributor berikut. Pemeriksaan ini dilakukan pada **27 Oktober 2026**
terhadap source yang dilacak Git, dokumentasi, manifest build, checkout
referensi lokal, dan alat riset yang digunakan untuk evidence project.

Setiap entri menjelaskan bentuk pemakaiannya. Revisi adalah snapshot yang
ditemukan atau dipin oleh project, bukan pernyataan tentang rilis terbaru.
Teks lisensi dan pemetaan file tersedia di
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md); salinan notice dicatat beserta
hash di [third_party/manifest.json](third_party/manifest.json).

## Kode, format, dan komponen yang digunakan

| Project / pembuat | Penggunaan dalam project ini | Snapshot / asal |
|---|---|---|
| [ForzaEditor](https://github.com/FMdangaina/ForzaEditor) — **FMdangaina dan kontributor** | Tiga source `CarbinModel.cs`, `CarbinModelMotorsport3.cs`, dan `ObjMesh.cs` ditautkan ke helper CPU lokal. Juga menjadi referensi parser carbin, XDS, dan metadata effect pada audit Python. | [`8807c7d137646dab8d9eecab7e8d5a6602ef58aa`](https://github.com/FMdangaina/ForzaEditor/tree/8807c7d137646dab8d9eecab7e8d5a6602ef58aa); revisi diperiksa oleh `build_carbin_cpu.py`. |
| **Forza Studio 4.6 — Mike Davis / Ernegien** | Karya awal ekstraksi dan penelitian format Forza yang menjadi dasar ForzaEditor. Kredit dan notice MIT aslinya dipertahankan. | [Notice upstream yang disalin](third_party/forzaeditor/THIRD-PARTY-NOTICES.md#forza-studio-46). |
| [MonoGame](https://github.com/MonoGame/MonoGame) — **The MonoGame Team**, dengan bagian dari **The Mono.Xna Team** | `MonoGame.Framework.dll` menyediakan operasi vector, matrix, quaternion dan tipe kompatibel XNA untuk helper CPU. | NuGet `MonoGame.Framework.DesktopGL` **3.6.0.1625**, hash paket diperiksa saat build; [notice versi tersebut](tools/carbin_cpu/MonoGame-LICENSE.txt). |
| [Xenia](https://github.com/xenia-project/xenia) — **Ben Vanik dan kontributor Xenia** | Referensi layout STFS melalui ReXGlue dan asal algoritme addressing tekstur Xenos melalui ForzaEditor. Juga merupakan dasar bagian runtime ReXGlue yang dipakai pada uji lokal. | `stfs_xbox.h`, `stfs_container_device.cpp`, dan `texture_address.h`; [notice](third_party/xenia/LICENSE). |
| [ReXGlue SDK](https://github.com/rexglue/rexglue-sdk) — **Tom Clay dan kontributor**, dengan karya Xenia | Struktur STFS menjadi referensi pembaca arsip Python. Runtime/recompiler juga dipakai dalam lingkungan riset dan uji FM4 lokal. | Checkout lokal [`f5337cdc947ff6d4c4196737e2c807a48f2a1fc2`](https://github.com/rexglue/rexglue-sdk/tree/f5337cdc947ff6d4c4196737e2c807a48f2a1fc2). |
| [libmspack](https://github.com/kyz/libmspack) — **Stuart Caie dan kontributor** | Implementasi LZX `lzxd.c` ditautkan ke decoder lokal `lzx_bridge.dll`, dipanggil pembaca ZIP method-21. Wrapper project berada di `tools/lzx_bridge/`. | Submodule lokal [`305907723a4e7ab2018e58040059ffb5e77db837`](https://github.com/kyz/libmspack/tree/305907723a4e7ab2018e58040059ffb5e77db837); [author upstream](third_party/libmspack/AUTHORS). |
| [ForzaTech Studio](https://github.com/D3FEKT/ForzaTechStudio) — **D3FEKT dan kontributor** | Checkout referensi format dan lokasi cache DLL lokal yang dipakai untuk fallback dekompresi XMem serta dekompresi section Granny/GR2. DLL tersebut tetap mempunyai pemilik dan ketentuan sendiri. | [`4f373c5fb192551ce5249e320dd79b1399b693ca`](https://github.com/D3FEKT/ForzaTechStudio/tree/4f373c5fb192551ce5249e320dd79b1399b693ca). |
| [ForzaTools](https://github.com/Nenkai/ForzaTools) — **Nenkai**, serta penelitian format oleh **Doliman100** | Kredit asal library/penelitian yang dinyatakan oleh ForzaTech Studio. Entri ini mempertahankan kredit upstream; tidak menyatakan ada library ForzaTools yang ditautkan langsung oleh package Python. | Bagian Credits pada README ForzaTech Studio; notice source mencantumkan **Copyright (c) 2023 Nenkai**. |

Kredit libmspack juga mencakup para pembuat metode LZX, **Jonathan Forbes dan
Tomi Poutanen**, serta adaptasi oleh **Microsoft Corporation**, sebagaimana
tercatat pada [header upstream](third_party/libmspack/LZX-NOTICE.txt).

## Checkout referensi tambahan

Checkout berikut ada dalam cache riset dan telah ditinjau dalam audit kredit.
Tidak ditemukan tautan build atau import langsung dari keduanya pada converter
saat ini; keduanya dicatat sebagai referensi tambahan.

| Project / pembuat | Lingkup referensi | Snapshot lokal |
|---|---|---|
| [carbin-garage](https://github.com/ItsNotPaths/carbin-garage) — **ItsNotPaths dan kontributor** | Tool dan dokumentasi porting arsip mobil Forza Xbox 360. | [`932b4e7836fa14a9e391e18a839eeded74ba115b`](https://github.com/ItsNotPaths/carbin-garage/tree/932b4e7836fa14a9e391e18a839eeded74ba115b). |
| [Forza-X360-IO](https://github.com/austinbaccus/Forza-X360-IO) — **Austin Baccus / austinbaccus**, **Anton Dorozhkin / Doliman100**, dan kontributor | Importer Blender dan penelitian format track, model, material serta shader era Xbox 360. | [`afa8e52056d37d89b4517e881ed19cf79de9f77f`](https://github.com/austinbaccus/Forza-X360-IO/tree/afa8e52056d37d89b4517e881ed19cf79de9f77f). |

Acknowledgment pada referensi tersebut juga menyebut **Mike Davis**, **Warshack**
(struktur/dokumentasi UDLC), **SoulBrix** (referensi exporter FM4),
**Spencer Leagra / Fox-GAMING**, **Carver**, dan **RichieMR2**. Nama-nama ini
dipertahankan sebagai kredit komunitas dari upstream, tanpa mengatribusikan
kode converter ini kepada mereka.

## Alat riset, disassembly, dan lingkungan uji

| Project / pembuat | Penggunaan yang ditelusuri |
|---|---|
| [XenonRecomp / XenonUtils](https://github.com/hedge-dev/XenonRecomp) — **hedge-dev dan kontributor** | Pembacaan image XEX dan API disassembly PPC untuk helper riset lokal `dump`, `disassemble`, dan `disasm-range`. Checkout lokal: [`ddd128bcca99fe8bfbb99bea583c972351fa6ace`](https://github.com/hedge-dev/XenonRecomp/tree/ddd128bcca99fe8bfbb99bea583c972351fa6ace). |
| [GNU binutils / GDB / GAS](https://www.gnu.org/software/binutils/) — **Free Software Foundation**, **Ian Lance Taylor / Cygnus Support**, dan kontributor | Backend PowerPC disassembler yang dibawa dalam `XenonRecomp/thirdparty/disasm`, termasuk `ppc-dis.c`. Notice file ini mempunyai ketentuan GPL tersendiri; bukan hanya MIT milik wrapper XenonRecomp. |
| [Xenia Canary](https://github.com/xenia-canary/xenia-canary) — **kontributor Xenia Canary** | Asal kode patching XEX yang diakui oleh XenonRecomp. Kredit ini bersifat tidak langsung melalui tool upstream; studi converter memakai image retail yang dicatat pada evidence. |
| [Ghidra](https://github.com/NationalSecurityAgency/ghidra) — **National Security Agency dan kontributor** | Analisis statis, decompilation dan katalog assembly di workspace FM4-re. Instalasi lokal **12.1.3 PUBLIC**; hasil numerik diverifikasi lagi terhadap byte image asli. |
| [XEXLoaderWV](https://github.com/zeroKilo/XEXLoaderWV) — **Warranty Voider / zeroKilo**, serta [fork SaveEditors](https://github.com/SaveEditors/XEXLoaderWV) | Loader XEX untuk Ghidra. Metadata extension terpasang mencatat **Warranty Voider; SaveEditors fork maintenance**, versi **12.1.3**. |
| [FM4-PC](https://github.com/dfebri446/FM4-PC) — project terkait milik pengembang, menggunakan **ReXGlue/Xenia** | Lingkungan game lokal untuk pengujian kandidat Cobalt v6. Executable dan game data tetap berada di luar source converter; bukan dependensi instalasi Python. |

Dependensi pendukung tool XenonRecomp juga diberi kredit sesuai source yang ada
di checkout lokal: [xxHash](https://github.com/Cyan4973/xxHash) — **Yann Collet**;
[{fmt}](https://github.com/fmtlib/fmt) — **Victor Zverovich dan kontributor**;
[toml++](https://github.com/marzer/tomlplusplus) — **Mark Gillard**;
[SIMDe](https://github.com/simd-everywhere/simde) — **Evan Nemerson dan kontributor**;
[tiny-AES-c](https://github.com/kokke/tiny-AES-c) — **kokke dan kontributor**;
dan [TinySHA1](https://github.com/mohaps/TinySHA1) — **Saurav Mohapatra**, berdasarkan
implementasi `boost::uuid::details`. Ini adalah dependensi tool eksternal,
bukan source yang disalin ke package converter.

## Dependensi Python dan toolchain

| Project / pembuat | Peran |
|---|---|
| [CPython / Python](https://www.python.org/) — **Python Software Foundation dan kontributor** | Interpreter, standard library, unittest, SQLite bindings, ZIP, XML, hashing dan ctypes. |
| [SQLite](https://sqlite.org/) — **D. Richard Hipp dan kontributor SQLite** | Pembacaan database melalui modul `sqlite3`, database kandidat, dan pemeriksaan integritas. |
| [NumPy](https://numpy.org/) — **NumPy Developers** | Fitting numerik dan operasi piksel thumbnail; versi project **2.3.5**. |
| [Pillow / PIL](https://python-pillow.org/) — **Jeffrey A. Clark dan kontributor Pillow**, **Fredrik Lundh**, serta **Secret Labs AB** | Decode, resize dan pemrosesan gambar CPU; versi project **12.0.0**. |
| [setuptools](https://github.com/pypa/setuptools) — **Python Packaging Authority dan kontributor** | Build backend dan instalasi editable pada `pyproject.toml`. |
| [pip](https://github.com/pypa/pip) — **pip developers** | Instalasi package dan dependensi. |
| [MonoGame / Mono.Xna](https://github.com/MonoGame/MonoGame) | Library matematika helper C#; detail pemakaian dan notice versi terpin dicatat di atas. |
| [LLVM / Clang](https://llvm.org/) — **LLVM Project dan kontributor** | Compiler lokal untuk wrapper decoder dan alat riset native. |
| [.NET Framework](https://dotnet.microsoft.com/en-us/download/dotnet-framework) — **Microsoft** | Compiler C# dan runtime helper CPU Windows. |
| [Eclipse Temurin / OpenJDK](https://adoptium.net/) — **Eclipse Adoptium, OpenJDK dan kontributor** | Runtime Java bagi Ghidra; distribusi lokal Temurin **21.0.12.1+1**. |
| [Git](https://git-scm.com/) — **Git contributors** | Pengelolaan source serta pemeriksaan revisi dan kebersihan checkout helper. |

Notice NumPy dan Pillow yang disalin mencakup pemberitahuan library bawaan
distribusi wheel masing-masing. Kredit dan ketentuan komponen tersebut tetap
dipertahankan di dalam teks notice lengkap.

## Komponen proprietary dan sumber data

- **Microsoft** — decoder lokal `xcompress64.dll` / API XMem dari ekosistem
  Xbox 360. Hak decoder tidak ditentukan oleh lisensi MIT ForzaTech Studio.
- **RAD Game Tools / Epic Games** — Granny 3D dan `granny2_x64.dll` untuk
  dekompresi data animasi/rig GR2 lokal.
- **Turn 10 Studios / Microsoft** — game Forza Motorsport, schema/data dan
  aset asli yang diteliti. Nama kendaraan serta merek terkait tetap milik
  pemegang hak masing-masing.

Project ini tidak dibentuk atau disponsori oleh para pembuat tool maupun
pemegang hak game di atas. Database, aset game, image executable dan decoder
proprietary tidak disertakan dalam repository.

## Pemeliharaan kredit

Saat menambahkan source atau adapter, catat upstream, pembuat, revisi, file yang
dipakai, dan bentuk penggunaan. Simpan notice yang relevan dan perbarui
`THIRD_PARTY_NOTICES.md` beserta manifest snapshot. Jika asal atau lisensi belum
teridentifikasi, catat batas bukti tersebut secara eksplisit.
