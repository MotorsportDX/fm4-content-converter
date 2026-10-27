# Third-party notices

Daftar ini mendampingi [CREDITS.md](CREDITS.md). Audit mencakup source converter,
helper native, reader arsip, dependensi Python, serta tool/referensi riset lokal
yang dapat ditelusuri pada 27 Oktober 2026.

Lisensi dicatat dari snapshot yang digunakan. Lisensi utama project adalah
**GPL-3.0-only**, dijelaskan pada [LICENSE](LICENSE) dan
[cakupan lisensi](docs/licensing.md). Dokumen ini mempertahankan notice upstream
dan header pada file pihak ketiga; lisensi komponen tersebut tetap berlaku.

## Pemetaan penggunaan dan notice

| Komponen | File / pemakaian project | Notice / lisensi snapshot |
|---|---|---|
| ForzaEditor | `tools/carbin_cpu/Program.cs` melalui tiga source eksternal yang dipin oleh `src/fm4_converter/fm3/build_carbin_cpu.py`; referensi `carbin_audit.py`, `texture_audit.py`, `effect_audit.py`. | [GPL v3 upstream](third_party/forzaeditor/LICENSE) dan [third-party notices upstream](third_party/forzaeditor/THIRD-PARTY-NOTICES.md). Header `GPL-3.0-only` yang sudah ada pada adapter/audit dipertahankan. |
| Forza Studio 4.6, Mike Davis | Karya pendahulu ForzaEditor dan penelitian format. | Copyright **2012 Mike Davis** dan izin MIT terdapat pada [notice asli](third_party/forzaeditor/THIRD-PARTY-NOTICES.md#forza-studio-46). |
| MonoGame 3.6.0.1625 / Mono.Xna | Math assembly helper CPU, hash paket diperiksa. | [Ms-PL dan notice MIT Mono.Xna](tools/carbin_cpu/MonoGame-LICENSE.txt), sesuai paket lama yang digunakan. |
| ReXGlue SDK / Xenia | Layout STFS untuk `src/fm4_converter/archives/stfs_reader.py` dan `stfs_zip_io.py`; asal addressing Xenos pada `texture_audit.py`; runtime riset lokal. | [ReXGlue BSD 3-Clause](third_party/rexglue/LICENSE), termasuk kredit **Tom Clay** dan **Ben Vanik / Xenia**; [Xenia BSD notice](third_party/xenia/LICENSE). |
| libmspack | `tools/lzx_bridge/lzx_bridge.c` ditautkan ke `lzxd.c` eksternal untuk reader `src/fm4_converter/archives/forza_zip.py`. | [LGPL v2.1](third_party/libmspack/COPYING.LIB), [header LZX](third_party/libmspack/LZX-NOTICE.txt), dan [AUTHORS](third_party/libmspack/AUTHORS). |
| ForzaTech Studio / asal ForzaTools | Checkout referensi dan cache decoder lokal yang dicari oleh `archive_cpu.py` dan `granny_audit.py`. | [MIT, Copyright (c) 2023 Nenkai](third_party/forzatechstudio/LICENSE), sebagaimana tercantum pada checkout ForzaTech Studio; perhatikan pemisahan DLL proprietary di bawah. |
| carbin-garage | Checkout referensi tambahan, tidak ditautkan ke converter. | README snapshot menyatakan **GPL-3.0-or-later**; [LICENSE pada revisi yang ditinjau](https://github.com/ItsNotPaths/carbin-garage/blob/932b4e7836fa14a9e391e18a839eeded74ba115b/LICENSE). |
| Forza-X360-IO | Checkout referensi format tambahan, tidak diimpor pipeline converter. | Teks **GNU GPL v3** pada [LICENSE snapshot](https://github.com/austinbaccus/Forza-X360-IO/blob/afa8e52056d37d89b4517e881ed19cf79de9f77f/LICENSE); tidak diasumsikan sebagai lisensi semua kode project ini. |
| XenonRecomp / XenonUtils | Tool eksternal untuk XEX/image dan disassembly dalam studi semantik. | [MIT, hedge-dev dan kontributor](third_party/xenonrecomp/LICENSE.md). Komponen di `thirdparty` mempunyai ketentuan tersendiri. |
| GNU binutils / GDB / GAS | Backend PPC pada tool disassembly lokal yang berasal dari `XenonRecomp/thirdparty/disasm`. | [Notice `ppc-dis.c`](third_party/binutils/PPC-DIS-NOTICE.txt): **GPL versi 2 atau lebih baru**, FSF / Ian Lance Taylor. Header `ppc.h` pada snapshot juga menyebut GPL versi 1 atau lebih baru. Kode/binary disassembler tidak dibundel. |
| Ghidra 12.1.3 PUBLIC | Tool analisis statis lokal FM4-re. | [Apache 2.0](third_party/ghidra/LICENSE). Dependensi Ghidra mempunyai notice sendiri di distribusi tool. |
| XEXLoaderWV / fork SaveEditors | Extension loader Ghidra, versi lokal 12.1.3. | Author/fork diverifikasi dari `extension.properties`. Teks lisensi tidak ditemukan pada paket extension terpasang; tidak diberi label lisensi Ghidra maupun lisensi project ini. Source dan binary loader tidak dibundel. [Upstream](https://github.com/zeroKilo/XEXLoaderWV), [fork](https://github.com/SaveEditors/XEXLoaderWV). |
| NumPy 2.3.5 | Fitting dan operasi piksel. | [Notice wheel lengkap](third_party/numpy/LICENSE.txt), diawali BSD 3-Clause NumPy beserta notice komponen bawaannya. |
| Pillow 12.0.0 / PIL | Decode dan pemrosesan gambar CPU. | [Notice wheel lengkap](third_party/pillow/LICENSE), diawali **MIT-CMU** PIL/Pillow beserta notice library bawaan. |
| setuptools / pip | Build editable dan instalasi. | [MIT setuptools](third_party/setuptools/LICENSE), [MIT pip](third_party/pip/LICENSE.txt), dari environment yang diperiksa. |

Salinan `THIRD-PARTY-NOTICES.md` milik ForzaEditor dipertahankan utuh, termasuk
notice komponen yang hanya dipakai editor upstream. Daftar dalam snapshot itu
tidak berarti seluruh komponen editor dipakai converter: helper hanya menautkan
tiga file model yang disebutkan di atas dan math assembly MonoGame.

## Dependensi tool eksternal

Checkout XenonRecomp membawa dependency berikut. Notice ini dicatat sebagai
dependency tool riset; implementasinya tidak disalin ke package Python.

| Komponen | Pembuat / notice |
|---|---|
| xxHash | **Yann Collet**, [BSD 2-Clause](third_party/xenonrecomp-dependencies/xxHash/LICENSE). |
| {fmt} | **Victor Zverovich dan kontributor**, [MIT](third_party/xenonrecomp-dependencies/fmt/LICENSE). |
| toml++ | **Mark Gillard**, [MIT](third_party/xenonrecomp-dependencies/tomlplusplus/LICENSE). |
| SIMDe | **Evan Nemerson dan kontributor**, [MIT](third_party/xenonrecomp-dependencies/simde/COPYING). |
| tiny-AES-c | [kokke/tiny-AES-c](https://github.com/kokke/tiny-AES-c), ketentuan pada source/distribusi tool upstream. |
| TinySHA1 | **Saurav Mohapatra**, [notice ISC-style pada header](third_party/xenonrecomp-dependencies/tinysha1/NOTICE.txt); header mengakui asal `boost::uuid::details`. |
| Xenia Canary | [Acknowledgment XenonRecomp](https://github.com/hedge-dev/XenonRecomp/tree/ddd128bcca99fe8bfbb99bea583c972351fa6ace#special-thanks) untuk asal kode patching XEX; mengikuti notice upstream masing-masing. |

CPython, SQLite, LLVM/Clang, .NET Framework, Eclipse Temurin/OpenJDK dan Git
dicantumkan sebagai runtime/toolchain pada [CREDITS.md](CREDITS.md). Distribusi
toolchain tersebut dipasang terpisah dan mempertahankan notice bawaannya.

## DLL proprietary dan aset game

`xcompress64.dll` / XMem adalah komponen Microsoft, sedangkan `granny2_x64.dll`
adalah komponen Granny dari RAD Game Tools / Epic Games. Lokasi cache di dalam
checkout MIT ForzaTech Studio tidak mengubah pemilik atau ketentuan DLL tersebut.
Project hanya memanggil salinan lokal dengan pemeriksaan hash; DLL, header SDK,
game data dan executable tidak ditambahkan ke repository ini.

## Snapshot notice

[third_party/manifest.json](third_party/manifest.json) mencatat project, upstream,
revisi jika diketahui, lokasi sumber notice, dan SHA-256 setiap salinan. Field
`revision: null` berarti revisi source tidak tercatat, bukan klaim bahwa sebuah
versi tertentu telah diverifikasi. Excerpt ditandai sebagai header notice saja;
salinan lain dipertahankan byte-identik dengan sumber lokalnya.

File di `third_party/` adalah teks lisensi/notice dan metadata atribusi.
Implementasi upstream, dependency binary dan data game tetap di luar Git.
