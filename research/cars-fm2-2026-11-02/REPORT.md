# Mobil FM2 → FM4: riset awal dan pilihan rute

Riset 2 November 2026. Semua pemeriksaan offline dan statis: katalog mobil dibaca
dari evidence [riset fisika 20 Oktober](../physics-2026-10-20/REPORT.md), ZIP mobil
dibaca langsung dari disc, game dan emulator tidak dijalankan. Hasil per mobil ada di
`outputs/car-fm2-research-2026-11-02/inventory.json` (diabaikan Git) dan dapat dibuat
ulang:

```powershell
.\.venv\Scripts\python.exe research/cars-fm2-2026-11-02/inventory.py
```

Sumber: FM2 USA Disc 1 dan Bonus Disc, FM3 USA Disc 1 (katalog Ultimate Collection
ikut dibaca), FM4 Japan/Asia Disc 1 serta delapan DLC FM4. Path lengkap ada di
konstanta script dan di [METHODS](../physics-2026-10-20/METHODS.md).

Dekode model (bagian 5) memakai [`carbin_fm2.py`](carbin_fm2.py) dan
[`survey_carbin.py`](survey_carbin.py); hasilnya di
`outputs/car-fm2-research-2026-11-02/carbin_survey.json`:

```powershell
.\.venv\Scripts\python.exe research/cars-fm2-2026-11-02/survey_carbin.py
```

## Ringkasan

- **Rute yang dipilih: FM2 → FM4 langsung**, sebagai adapter sumber baru
  (`fm4_converter/fm2/`) yang memakai ulang back-end FM4 project. Tidak melalui
  file FM3 sebagai format antara.
- Mobil FM2 yang juga ada di FM3 **diambil dari FM3**, bukan dari FM2, karena aset
  FM3 lebih lengkap dan jalurnya sudah ada.
- Dari 349 definisi mobil FM2, hanya **55 yang tidak ada di FM3 maupun FM4**.
  Kebanyakan varian tuner dan livery balap dari mobil yang sudah ada di FM4.
- Seluruh 310 ZIP mobil FM2 base hanya berisi **satu `.carbin`**. Tidak ada model
  kokpit, `_lod0`, kaliper dan rotor terpisah, ataupun tekstur interior yang
  dibutuhkan susunan mobil FM4. Ini risiko terbesar, dan rute mana pun tidak
  menghilangkannya.
- **`.carbin` FM2 sudah dapat didekode.** Decoder riset membaca 310/310 file tanpa
  gagal. Posisi, UV0 dan normal cocok dengan FM3 untuk mobil yang ada di kedua game
  (1,23 juta pasangan vertex). UV FM2 ternyata fixed-point 16-bit, bukan half float
  seperti yang diasumsikan Forza Studio. Isi file hanya LOD1–LOD5; tidak ada LOD0.
- **FM4 tidak menolak mobil yang tidak punya `_lod0` atau `_cockpit`.** Loader
  menggantinya dengan model placeholder `nul_car_00` dari disc FM4, jadi file
  tersebut tetap harus dibuat. `.carbin` utama FM4 berisi LOD1–5, sama dengan FM2.
- **Prototipe penulis model FM4 sudah ada** (bagian 7). Untuk `JAG_XK_07` ia membuat model
  utama, `_lod0`, dan `_cockpit` yang lolos audit statis. Prosesnya: transkode FM2 ke tata
  letak biner FM3, lalu konverter FM3 → FM4 yang sudah ada, lalu `CloseUpFromLod1`.
- **`JAG_XK_07` sudah dibalap di Motorsport DX** (bagian 8), dalam paket overlay uji dengan
  tekstur dan thumbnail FM2 serta database donor `JAG_XKRS_09`. Mobil tampil di Car Select
  sebagai "XK Coupe (FM2)", model 3D-nya dirender di garasi, dan Quick Race dengan AI
  berjalan sampai menu pause tanpa crash di kamera kokpit, bumper, dan chase. Fisikanya
  masih milik donor.
- **Spion kokpit dan velg FM2 sudah berjalan di game** (bagian 9). Kaca spion FM2 dipetakan ke
  material spion FM4 dengan UV 0–1, dan pantulannya hidup. Velg FM2 dikonversi dengan LOD0 dari
  LOD1; 407/407 velg FM2 lolos audit. Kecerahan interior sesuai kalibrasi 74 mobil FM2∩FM4, dan
  plafon hitam memang berasal dari atlas FM2.
- **Fisika FM2 dikalibrasi ke FM4** (bagian 10). Pada 184 pasangan FM2∩FM4, nilai FM2 (dengan 46
  aturan skala dan konvensi FM4) lebih dekat ke FM4 asli daripada donor pada 34 dari 46 grup
  fisika, termasuk kurva torsi, massa, transmisi, dan pegas. `JAG_XK_07` dengan fisika FM2
  (kelas B, mesin NA, 1.595 kg) balapan sampai finis tanpa crash.

## 1. Rute sumber per mobil

Pencocokan memakai `MediaName` lebih dulu, lalu `Data_Car.Id`. ID mobil tetap
sama lintas versi (contoh `247 = TOY_2000GT_69` di FM2, FM3 dan FM4).

| Rute | Jumlah | Arti |
|---|---:|---|
| `fm4_same_name` | 200 | Sudah ada di FM4 disc/DLC dengan nama yang sama |
| `fm4_same_id_renamed` | 45 | ID sama di FM4 tetapi `MediaName` berbeda |
| `fm3_source` | 49 | Ada di FM3 Disc 1 tetapi tidak di FM4; masuk jalur FM3 → FM4 |
| `fm2_only` | **55** | Tidak ada di FM3 maupun FM4; memerlukan adapter FM2 |

**Mobil `fm4_same_id_renamed` belum tentu identik.** Sebagian besar hanya berganti
tahun atau akhiran DLC (`FER_612_05` → `FER_612_04`, `AUD_R8_DLC` → `AUD_R8_08`,
`FOR_MustangSaleenS281_00` → `SAL_S281_00`). Tetapi `FER_355GTS_94` →
`FER_355Berlinetta_94` adalah bodi berbeda (targa vs coupe), dan
`PEU_207RCup_DLC1` → `PEU_207Super2000_07` juga perlu dicek. Daftar lengkapnya ada
di `inventory.json`.

**Status 49 mobil `fm3_source` di paket `fm3-only-v1`:** 47 sudah terkemas dan 2
gagal (`PON_GTO_68`, `TOY_35_Supra_04`). Lima di antaranya cocok lewat ID dengan
nama FM3 yang berbeda (`AUD_8_R10_DLC1` → `AUD_8_R10_06`, `POR_997GT2_DLC` →
`POR_997GT2_08`, `MAS_GranTurismo_DLC` → `MAS_GranTurismo_08`, `PEU_908_DLC2` →
`PEU_8_908_07`, `POR_996GT1_DLC2` → `POR_996GT1_98`). Mobil-mobil ini tidak perlu
diambil dari FM2.

### 55 mobil FM2-only

| Kelompok | Contoh |
|---|---|
| Tuner Jepang | AB Flug RX-7 dan Supra, VeilSide Supra '98 (2 varian), Mines Evo VI, Tommy Kaira Impreza/R34, RE Amemiya RX-7, Mugen S2000, Do-Luck NSX, VIS Integra/MR2, Wings West Civic, TOM'S Soarer, Border MR2 |
| Tuner AS/Eropa | Hennessey Viper, Lingenfelter dan Guldstrand Corvette, Foose IS300, AWE Silver Bullet S4, Sparco Evo VIII |
| Livery balap bernomor | Audi R8 #1/#88, Viper ACR #77, Viper GTS-R #58, Porsche 996/911 GT3 Cup dan RSR (#22, #23, #44, #57, #81), SEAT Cupra GT #5 |
| Mobil produksi atau prototipe yang tidak ada di FM3/FM4 | Jaguar XK '07, Lotus Exige '05, Lotus Elise 135R, Camaro SS '02, Acura RL A-Spec, Chrysler ME Four-Twelve, Protos Spirra, TVR Tuscan R, Evo VI TME, Evo VIII GSR, Evo IX GT, Skyline GT-R Nür '02, Fairlady 432R, Fairlady Z POE, Focus SVT '03, Supra Forza SE |
| Bonus Disc | Nissan 350Z '07, Altima '07, Dodge Challenger Concept '06, Maserati MC12 Corsa |

`inventory.json` mencatat `near_matches` untuk tiap mobil, yaitu mobil FM3/FM4 dengan
merek sama dan selisih tahun ≤ 1. Daftar ini bukan bukti duplikat. Contohnya
`FOR_FocusSportSVT_03` di samping `FOR_FocusSVT_03`, dan `MIT_LancerEvoVIIIGSR_04`
di samping `MIT_LancerEvoVIIIMR_04`. Keduanya perlu dibandingkan sebelum dianggap
mobil baru.

## 2. Bentuk aset mobil FM2

Seluruh 310 ZIP mobil FM2 base diperiksa. Empat mobil Bonus Disc FM2-only berada di
paket STFS dan belum dibuka dalam riset ini.

| Pemeriksaan | Hasil FM2 (310 ZIP) |
|---|---|
| `.carbin` per ZIP | 1 pada **semua** ZIP |
| Word pertama `.carbin` | `00000002` pada semua ZIP |
| Kompresi ZIP | method 8 (deflate) pada semua ZIP |
| `LiveryMasks/` | ada di 309 ZIP |

Perbandingan dengan mobil yang sama di FM3 (`ACU_42_NSX_02`), serta mobil FM4:

| | FM2 | FM3 | FM4 |
|---|---|---|---|
| Member ZIP | 10 | 30 | 32 (contoh `MAZ_Miata_94`) |
| `.carbin` | 1 (`<car>.carbin`) | 11: bodi, `_lod0`, `_cockpit`, 4 kaliper, 4 rotor | 11; nama kaliper/rotor berakhiran `_lod0` |
| Word pertama `.carbin` bodi | `00000002` | `00000001` | `00000002` |
| Tekstur `_lod0` dan `interior_lod0.xds` | tidak ada | ada | ada |
| Header `.xds` | `00000003 00000001` | sama | sama |
| Kompresi ZIP | deflate (8) | LZX (21) | LZX (21), satu stored |

Penafsiran:

- **Terkonfirmasi:** FM2 tidak membawa model kokpit, model `_lod0`, ataupun
  kaliper/rotor terpisah. Converter FM3 saat ini memetakan 11 model sumber ke
  11 model FM4, sehingga pola satu-ke-satu tersebut tidak berlaku untuk FM2.
- **Terkonfirmasi:** word versi FM2 berbeda dari FM3, sehingga pembaca FM3
  (`CarbinModelMotorsport3` di helper CPU) tidak dapat dipakai langsung.
- **Belum diketahui:** apakah layout `.carbin` FM2 mirip FM4 karena word versinya
  sama-sama 2. Kesamaan satu word tidak membuktikan kesamaan struktur.
- **Inferensi:** kontainer tekstur XDS memakai header yang sama di ketiga game,
  sehingga tekstur bodi kemungkinan besar dapat dipakai tanpa encode ulang. Format
  piksel per tekstur belum dibandingkan.
- `LiveryMasks` adalah bagian sistem livery FM2 dan tidak ada di ZIP FM3/FM4.

## 3. Mengapa tidak FM2 → FM3 → FM4

1. **Kesalahan kalibrasi fisika akan bertumpuk.** Aturan FM3 → FM4 di
   `fm3/calibration.py` dan `value_scales.py` dibuat dari pasangan mobil FM3/FM4.
   Data ban berubah di setiap generasi (lihat bagian ban di
   [REPORT fisika](../physics-2026-10-20/REPORT.md)). Rute lewat FM3 membutuhkan
   aturan FM2 → FM3 lalu FM3 → FM4, padahal ada 200 pasangan FM2∩FM4 bernama sama,
   ditambah sebagian dari 45 yang berganti nama, untuk kalibrasi langsung.
2. **Format antara tidak dapat divalidasi.** Hasil FM2 → FM3 tidak akan diuji di
   FM3, dan helper `carbin-cpu` hanya membaca FM3 serta menulis FM4. Penulis FM3
   tidak ada.
3. **Restrukturisasi database cukup sekali.** Upgrade FM2 terhubung lewat
   `Data_Car.Id = Ordinal`, sedangkan FM3/FM4 memisahkan body dan drivetrain.
   Pemetaan langsung ke bentuk FM4 menghindari dua kali restrukturisasi.
4. **FM3 tidak menyediakan bagian yang hilang.** FM3 tidak memiliki ke-55 mobil
   tersebut, sehingga kokpit dan `_lod0` tetap harus ditangani pada rute mana pun.

Komponen yang dapat dipakai ulang dari jalur FM3: penulisan model FM4 di helper CPU,
pengemasan overlay dan pemeriksaan ID terhadap DLC (`batch_package.py`), PI dan
kelas, nama UI, thumbnail, serta pembaca arsip bersama di `archives/`. Aturan
kalibrasi tetap per sumber, sesuai [arsitektur](../../docs/architecture.md).

## 4. Langkah berikutnya

Urutan berdasarkan risiko. Sudah dikerjakan: dekode `.carbin` FM2 (bagian 5), perilaku
loader FM4 untuk file yang tidak ada (bagian 6), prototipe model utama, `_lod0`, serta
`_cockpit` (bagian 7), uji game `JAG_XK_07` (bagian 8), kokpit, spion, dan velg FM2
(bagian 9), serta kalibrasi fisika FM2 → FM4 (bagian 10).

1. **Sisa fisika:** `CMHeight` dari bounding box model, pemasangan turbo/supercharger FM2 tanpa
   part donor yang sama, serta uji kendali dengan mobil lain.
2. **Verifikasi 45 mobil `fm4_same_id_renamed`** dan kandidat `near_matches`
   sebelum menetapkan daftar final FM2-only.
3. **Section dan bagian yang tidak ada di FM2**: section `wheel`, `undercarriagea` dan
   `exhaust*` tambahan FM3 (bagian 5.3), kaliper/rotor sendiri, gauge cluster, jarum, dan
   `a_pillar` (bagian 9.4); kini donor atau tidak ada.
4. Buka paket STFS Bonus Disc untuk aset 4 mobil FM2-only dari paket bonus.
5. Sisa format: 12 nilai S16 terakhir vertex FM2, header 0x100 byte, record 140 byte,
   dan arti pembagian dua buffer vertex (bagian 5.4 dan 7.3).

## 5. Dekode `.carbin` FM2

### 5.1 Acuan dan decoder

Forza Studio (Mike Davis, MIT), yang ada di checkout ForzaEditor terpin untuk helper
CPU, sudah memiliki jalur baca `ForzaVersion.Two` di `ForzaCarBin.cs`,
`ForzaCarSection.cs`, `ForzaCarSubSection.cs` dan `ForzaVertex.cs`. Jalur itu hanya
untuk ekspor; tidak ada penulis FM2. `CarbinModel.cs` ForzaEditor dan carbin-garage
hanya mendeteksi FM2 tanpa membacanya.

[`carbin_fm2.py`](carbin_fm2.py) mengikuti urutan baca Forza Studio, dengan
perbedaan berikut:

- exception tidak ditelan, setiap baca diperiksa terhadap panjang file;
- pass 1 (mencari buffer bersama) dan pass 2 (membaca section) harus berakhir di
  offset yang sama;
- setiap indeks harus berada di dalam buffer yang dirujuk section-nya;
- UV dibaca sebagai fixed-point (bagian 5.2).

Struktur yang terkonfirmasi:

```text
type u32 = 2 · 0x100 byte · u32 · N×140 byte · 0x6C byte · daftar draw · u32
section × N   (marker 0x2C9, origin + bounds 9×f32, nama, subsection × M)
  subsection   (nama material, tipe indeks 6 = tri strip, LOD 1..5, indeks u16)
buffer "glass": u32 jumlah, u32 stride 60, vertex
buffer "body":  u32 jumlah, u32 stride 60, vertex
0x000DECAF
```

Berbeda dari FM3/FM4, section FM2 tidak menyimpan vertex sendiri. Semua section
memakai salah satu dari dua buffer vertex bersama, dipilih oleh pasangan word
`vbTest`. Indeks setiap section bersifat lokal dan ditumpuk berurutan di buffer itu.
Nama "glass" dan "body" berasal dari Forza Studio dan tidak akurat: pada NSX, section
`trunk` berada di buffer "glass".

### 5.2 Hasil survei 310 mobil

| Pemeriksaan | Hasil |
|---|---|
| File terbaca tanpa error | 310 / 310 |
| Sisa byte setelah buffer | tepat 4 byte, nilainya `000DECAF` pada semua file |
| Marker section | 0x2C9 pada seluruh 10.584 section |
| Section per mobil | 12–81 |
| LOD subsection | hanya 1–5; **tidak ada LOD0** |
| Indeks | tri strip u16 (143.115 subsection), tri list 5 subsection |
| Segitiga LOD1 per mobil | 13.812–72.869 |
| Stride vertex | 60 byte pada semua buffer |
| UV1 | nol pada semua vertex 310 mobil |

Layout vertex 60 byte:

| Offset | Isi | Status |
|---:|---|---|
| 0 | posisi xyz × w, 4 half float; posisi akhir = hasil + origin section | Terkonfirmasi lewat FM3 |
| 8 | UV0, 2 × u16 fixed-point | Terkonfirmasi lewat FM3 |
| 12 | UV1, format sama | Selalu nol |
| 16 | normal 11:11:10 bertanda | Terkonfirmasi lewat FM3 |
| 20 | 4 byte, sama dengan word FM3 di offset 28 | 84% identik |
| 24 | 4 byte, sama dengan word FM3 di offset 32 | 61% identik |
| 28 | 32 byte | Belum diketahui |

**UV FM2 = `(word − 32768) / 1310,72`**, artinya rentang [−25, 25) dengan langkah
kuantisasi ±0,00076. Forza Studio membaca word ini sebagai half float lalu
mengalikannya dengan 12800 (lalu membalik tanda). Nilai half hanya linear terhadap
word selama exponent ≤ 1, sehingga pembacaan itu hanya benar untuk UV di
[0; ~1,56). UV negatif atau ≥ 1,56 terbaca salah. Fit pada vertex yang cocok di DB9, RS6 dan NSX memberi skala 1/1310,6–1/1310,7
dengan offset tetap sekitar +0,00036 (setengah langkah). Skala 32768/25 tetap dipakai;
offset setengah langkah konsisten dengan pemotongan saat encoding, tetapi belum
dibuktikan.

### 5.3 Pembanding dengan FM3

146 mobil FM2 juga memiliki ZIP di FM3 Disc 1. LOD1 bodi FM3 dibaca dengan
`carbin_audit` project.

| Pemeriksaan | Hasil |
|---|---|
| Bounding box selain Y-min | median selisih 0 m, p90 0,029 m, maksimum 0,135 m |
| Y-min | FM3 median 0,269 m lebih rendah, karena section tambahan FM3 |
| Section yang hanya ada di FM3 | `undercarriagea` (145 mobil), `wheel` (137), `exhausta` (49), `exhaustLa/Ra` (32) |
| Pasangan vertex dengan posisi unik yang cocok | 1.230.446 |
| UV dalam 2 langkah kuantisasi | 1.164.943 (94,7%) |
| Median selisih UV per mobil | median 0,00055 (126 mobil berpasangan) |
| p99 sudut normal per mobil | median 0,000001°; p90 0,11° |

Kesimpulan: bodi FM3 pada mobil yang ada di kedua game sebagian besar adalah bodi FM2
yang dibawa ulang, ditambah roda, undercarriage, exhaust dan model LOD0/kokpit baru.
Kecocokan ini membuktikan decoder untuk posisi, UV0 dan normal. Pencilan berasal dari
mobil yang dimodel ulang di FM3; sebagian besar selisih UV di atas 2 langkah ada pada
mobil seperti `acu_rsxtypes_02` yang UV-nya dibuat ulang di FM3.

### 5.4 Yang belum diketahui

- 32 byte terakhir vertex. *Diperbarui di bagian 7.3:* isinya 16 nilai S16. Empat yang
  pertama adalah nilai ambient yang juga ada di FM3, dan FM2 tidak menyimpan tangent.
- Isi header 0x100 byte, record 140 byte, blok 0x6C byte dan 0x1C byte di setiap
  section. Decoder melewatinya seperti Forza Studio. *Diperbarui di bagian 7.2:* blok 0x6C
  berisi driver rig, dan word sebelum vbTest adalah rentang vertex section.
- Arti dua buffer vertex dan nilai `vbTest` selain pemilih buffer.
- Model roda FM2 di `Media/wheels` belum diperiksa.

## 6. Loader model FM4 untuk file yang tidak ada

### 6.1 Sumber

Analisis statis atas `default.xex` FM4 di checkout FM4-re lokal (`external/FM4-re`,
diabaikan Git): tabel string `out/db/strings.jsonl`, disassembly `out/db/asm.json`
dan hasil dekompilasi Ghidra `out/dec5/8290b428.c`. Game dan emulator tidak
dijalankan.

### 6.2 Fungsi 0x8290B428: path model mobil dan fallback

Fungsi ini menyusun path file model satu mobil dari `game:\media\cars\` dan
`MediaName`, dengan akhiran `.carBin`, `_lod0.carbin`, `_cockpit.carbin`,
`_s_lod0.carbin`, `_cockpit_s.carbin` dan `\CarAttribs.xml`. Setiap path diperiksa
lewat metode vtable `+0x54` pada objek file system parameter kedua. Bila hasilnya
false, path itu diganti dengan file mobil placeholder:

| File mobil yang tidak ada | Pengganti (alamat string) |
|---|---|
| `<car>.carBin` | `game:\media\cars\nul_car_00\nul_car_00.carBin` (0x82151924), folder ikut diganti |
| `<car>_lod0.carbin` | `nul_car_00_lod0.carbin` (0x8215189C) |
| `<car>_cockpit.carbin` | `nul_car_00_cockpit.carbin` (0x82151864) |
| `<car>_s_lod0.carbin` | `nul_car_00_s_lod0.carbin` (0x8215182C) |
| `<car>_cockpit_s.carbin` | `nul_car_00_cockpit_s.carbin` (0x821517F4) |
| `CarAttribs.xml` | string kosong |

Varian `_s` dipilih oleh bit 4 pada byte `+0x9DAC` objek konfigurasi (mode `_SLOD`).
Path LOD0 dan kokpit yang dipakai akhirnya dipilih oleh `0x828F86C8` berdasarkan bit
itu, lalu diperiksa sekali lagi dengan fallback yang sama.

- **Terkonfirmasi** (byte dan dekompilasi): urutan path, pemeriksaan per file, dan
  path pengganti `nul_car_00`. `nul_car_00.zip` ada di disc FM4 dengan set lengkap:
  bodi, `_lod0`, `_cockpit`, kaliper dan rotor.
- **Inferensi:** metode `+0x54` adalah pemeriksaan "file ada". Pola
  periksa-lalu-ganti mendukungnya, begitu juga catatan uji awal Cobalt di
  [docs/fm3.md](../../docs/fm3.md) yang memperlihatkan "model pengganti" sebelum aset
  lengkap dikemas.
- **Akibatnya:** mobil FM2 tanpa `_lod0` dan `_cockpit` tidak ditolak, tetapi akan
  memakai LOD0 dan kokpit `nul_car_00`. Bentuknya tidak cocok dengan bodi mobil
  FM2, sehingga kedua file harus dibuat sendiri.

String `keepLOD0Car` hanya dipakai oleh parser opsi command line
(`CForzaCommandLineParameters`), bukan oleh data mobil.

### 6.3 Isi tiga model FM4 dan perbandingan dengan FM2

| File FM4 | LOD mesh | Isi (contoh `MAZ_Miata_94`) |
|---|---|---|
| `<car>.carbin` | 1–5 | bodi eksterior lengkap |
| `<car>_lod0.carbin` | 0 | bodi eksterior, termasuk `wheel` dan `undercarriagea` |
| `<car>_cockpit.carbin` | 0 | `interior`, kursi, setir, spion, `a_pillar`, kap, kaca depan, jarum `speed/tach/fuel_{min,mid,max}` |

Sampel 54 ZIP disc FM4 (setiap ZIP keenam, dibuat ulang dengan
[`fm4_model_files.py`](fm4_model_files.py)): 53 mobil punya ketiga file, tidak ada
satu pun yang punya varian `_s`. Dari 52 kokpit yang terbaca:

| Section kokpit | Mobil FM4 (dari 52) | Mobil FM2 yang punya (dari 310) |
|---|---:|---:|
| `interior` | 52 | 310 |
| `steering_wheel` | 52 | 310 |
| `a_pillar` | 52 | **0** |
| `hooda` | 50 | 301 |
| `mirrorL` / `mirrorR` | 48 / 44 | 306 / 293 |
| `seatR` / `seatL` | 48 / 46 | 263 / 287 |
| `glassF` | 42 | 236 |
| jarum `fuel_*` / `tach_*` / `speed_*` | 39 / 39 / 37 | 0 |

Satu kokpit (`FER_F430Scuderia_07`) gagal dibaca `carbin_audit` karena float
non-finite. Section FM2 di atas berada di dalam bodi LOD1–5, bukan di file kokpit
terpisah. FM2 sendiri tidak mempunyai kamera kokpit; fitur itu baru ada di FM3.

- `.carbin` utama FM2 (LOD1–5) dapat dipetakan langsung ke `.carbin` utama FM4.
- Kokpit FM4 tanpa jarum gauge ada preseden native: 13 dari 52 sampel tidak punya
  `fuel_*`/`tach_*`. Jadi kokpit FM2 tanpa jarum tidak melanggar pola data disc.
- `a_pillar` ada di semua sampel FM4 tetapi tidak di FM2. Apakah section ini wajib
  belum diketahui.

### 6.4 Konsekuensi untuk konverter

| File FM4 | Usulan sumber FM2 | Risiko |
|---|---|---|
| `<car>.carbin` | LOD1–5 FM2, dikonversi ke format FM4 | Format vertex dan section berbeda (bagian 5); roda dan undercarriage tidak ada |
| `<car>_lod0.carbin` | LOD1 FM2 dinaikkan menjadi LOD0 | Detail lebih rendah dari LOD0 native; kapan LOD0 dipakai saat balapan belum dipastikan |
| `<car>_cockpit.carbin` | Section `interior`, `steering_wheel`, kursi, spion, `hooda`, `glassF` dari LOD1 FM2 | Interior FM2 dibuat untuk dilihat dari luar; tanpa jarum gauge dan `a_pillar`; posisi kamera kokpit belum diketahui sumbernya |

Alternatif menonaktifkan kamera kokpit per mobil belum ditemukan. String
`OpenCockpit` (atribut `CarAttributes`) dan `IDS_ForcedCamera_Cockpit` ada, tetapi
konsumennya belum ditelusuri.

## 7. Prototipe penulis model FM4 (`JAG_XK_07`)

Prototipe 3 November 2026. Ia membuat tiga file model FM4 untuk satu mobil FM2-only, lalu
mengauditnya secara statis. Game tidak dijalankan.

```powershell
.\.venv\Scripts\python.exe research/cars-fm2-2026-11-02/prototype_fm4_model.py JAG_XK_07 --donor JAG_XKRS_09
.\.venv\Scripts\python.exe research/cars-fm2-2026-11-02/check_fm2_to_fm3.py --helper <carbin-cpu-v9>\carbin-cpu.exe
```

Hasilnya ada di `outputs/car-fm2-prototype-2026-11-03/` (diabaikan Git). Script prototipe
memakai helper `carbin-cpu` v9. Helper ini dibangun ulang dengan perintah baru `closeup`
(lihat [README helper](../../tools/carbin_cpu/README.md)); hasil `convert` v5 byte-identik
dengan v4. V6 menambahkan daftar penggantian nama material ke `closeup` (bagian 8.2); model
utama dan `_lod0` `JAG_XK_07` dari v6 byte-identik dengan v5; v7–v9 dijelaskan di bagian 9.

### 7.1 Alur

1. [`fm2_to_fm3.py`](fm2_to_fm3.py) menulis ulang `.carbin` FM2 ke tata letak `.carbin` FM3
   (type 1, vertex 40 byte).
2. `carbin-cpu convert` membuat model utama FM4 (LOD1–5). Ini konverter FM3 → FM4 yang sama
   dengan yang dipakai untuk mobil FM3, dan hasilnya diaudit dengan
   `carbin_audit.audit_conversion`.
3. `carbin-cpu closeup`, yaitu `CloseUpFromLod1` milik ForzaEditor, membuat `_lod0` dan
   `_cockpit` dari LOD1 model utama.

Tata letak FM3 di langkah 1 hanya dipakai sebagai bentuk biner antara di dalam konverter.
Ini **bukan** rute FM2 → FM3 → FM4 yang ditolak di bagian 3. Tidak ada paket, data, atau
kalibrasi FM3 yang dibuat. Langkah ini dipilih karena penulis model FM4 yang sudah teruji
hanya menerima input FM3. Keberatan nomor 2 di bagian 3 (format antara yang tidak
tervalidasi) dijawab di bagian 7.4: hasil transkode dibandingkan dengan file FM3 asli dari
145 mobil yang ada di kedua game.

### 7.2 Perbedaan FM2 dan FM3 yang ditangani transkoder

| Bagian | FM2 | FM3 (ditulis) |
|---|---|---|
| Blok format header | `0x2CA, 1, N` di 0x104 | `0xD, 0xB, 1, N` |
| Record 140 byte | sama | disalin |
| Sisa header | 0x6C byte: word 1, driver rig 24 float, `(4, 4)` | 0x1AC byte: word 3, driver rig, 0xA8 byte konstan, 4 gauge frame netral, dua float akhir, `(4, 4)` |
| Draw list | sama | disalin |
| Marker section | 0x2C9 | 2 |
| Sebelum vbTest | word rentang vertex `(first, last)` u16 di buffer bersama | tidak ada |
| Setelah nama | 8 byte (`2, 1`) | 4 byte (`2`) |
| Vertex | dua buffer bersama di akhir file | buffer LOD per section; indeks tetap lokal |
| Subsection | 8 byte, nama, (tipe indeks, LOD) | 9 byte, nama, (LOD, tipe), 56 byte konstan, 4 byte nol di akhir |
| Setelah subsection | — | `2`, buffer LOD0 kosong; trailer 24 byte konstan |

Semua nilai "konstan" di FM3 diambil dari survei 78–200 mobil disc FM3. Isinya selalu
sama, kecuali satu byte di 646 dari 40.978 subsection, dan byte itu tetap ditimpa konverter
FM4. Dua float akhir header (x, y = −2x) belum diketahui artinya. Nilainya diisi median FM3:
−0,3388 dan 0,6791.

Word rentang vertex sama dengan base yang dihitung decoder di semua 310 mobil. Field ini
yang sebelumnya dilewati sebagai "skip 4" di bagian 5.1.

### 7.3 Vertex 60 → 40 byte dan 32 byte terakhir FM2

| FM3 | Sumber FM2 |
|---|---|
| 0–7 posisi (half xyz·w) | 0–7, disalin; bounds FM2 simetris sehingga rumus FM3 (origin + pusat + xyz·w) memberi posisi yang sama |
| 8–11 UV0 (half) | 8–11, fixed-point u16 → half (kehilangan presisi sebatas half, seperti mobil FM3) |
| 12–15 UV1 | nol |
| 16–19 normal 11:11:10 | 16–19, disalin |
| 20–27 empat S16 "ambient" | S16 di 28–35 × 1,48 |
| 28–31 word damage, 32–35 word berikutnya | 20–23, 24–27 |
| 36–39 sumbu Z frame tangent | dihitung: −dP/dv dari UV segitiga semua LOD section itu, diproyeksikan ke bidang normal (nol bila panjangnya < 0,1) |

Dari 32 byte yang sebelumnya belum diketahui (bagian 5.4), 28–59 ternyata berisi 16 nilai
S16. Empat nilai pertama berkorelasi 0,96–0,99 dengan empat nilai ambient FM3, yang di FM4
dipakai sebagai cahaya ambient terpanggang (vertex 24–31). Rasionya 1,47–1,49 pada 39.031
pasangan vertex. FM3 memanggang ulang nilai ini, jadi skala 1,48 hanya pendekatan. Arti 12
nilai sisanya belum diketahui dan tidak dipakai. FM2 tidak menyimpan frame tangent.

Empat mobil disc FM2 punya satu section 3–6 vertex dengan posisi NaN (`w = 0x7FFF`) dan
bounds ±1,7e38: `che_corvettelingenfelter_02` `winga`, `fer_gto_84` `headlightRdown`,
`mit_fto_98` `skirtRa`, dan `sea_5_cupragt_05` `lexanRR`. Transkoder menciutkan section
seperti ini ke satu titik dengan bounds ±1 mm. Draw list tetap utuh, dan bagian itu juga
tidak bisa tergambar di FM2.

### 7.4 Validasi transkoder dan konversi FM4 pada semua mobil FM2

Hasil `check_fm2_to_fm3.py --helper` untuk semua 310 mobil disc FM2
(`outputs/car-fm2-research-2026-11-02/fm2_to_fm3_check.json`):

| Pemeriksaan | Hasil |
|---|---|
| Transkode, dibaca `carbin_audit` (FM3) | 310/310 |
| Hasil transkode vs decoder FM2 | posisi ≤ 0,00013 mm, normal ≤ 0,000002°, UV ≤ 0,0078 (kuantisasi half untuk \|UV\| 8–16); urutan section, mesh, LOD, dan indeks identik; 17 vertex non-finite di 4 mobil dipindah (bagian 7.3) |
| `carbin-cpu convert` + `audit_conversion` FM4 | **310/310 lolos**; posisi ≤ 0,093 mm, normal ≤ 0,0034°, UV ≤ 0,0004 |
| Header vs FM3 asli (146 mobil di kedua game) | struktur identik di 146/146; record sama di 48, driver rig sama di 29 (sisanya data per mobil yang direvisi di FM3) |
| Sumbu Z tangent hasil hitung vs FM3 asli | 607.329 pasangan vertex: median dot 0,9988, 87,5% di atas 0,9 |
| Ambient (×1,48) vs FM3 asli | median selisih 0,015–0,026, p90 0,09–0,14 (skala S16 /32767) |

Run pertama menemukan dua masalah, keduanya sudah diperbaiki. Pertama, gauge frame bergeser
dua word karena region konstan setelah driver rig ternyata 0xA8 byte, bukan 0xB0. Kedua,
dua mobil (`toy_supraforzase_92`, `tvr_tuscanr_01`) gagal audit FM4 dengan normal bergeser
0,07° dan 0,78°: sumbu −dP/dv hampir sejajar normal sehingga quaternion frame tidak stabil.
Sekarang sumbu diproyeksikan ke bidang normal, dan diisi nol bila panjang sisanya di bawah
0,1. Untuk sumbu nol, writer FM4 memakai sumbu bawaannya.

### 7.5 `_lod0` dan `_cockpit`

`CloseUpFromLod1` menyalin mesh LOD1 menjadi LOD0, dengan indeks 32-bit dan vertex di
buffer LOD0. Ia membuang vertex yang hanya dipakai LOD2–5, lalu menghitung ulang bounds dan
centroid.

Pembagian section mengikuti mobil disc FM4 (contoh `JAG_XKRS_09`): `_cockpit` berisi kursi,
`steering_wheel`, `cagerace`, `glassLF`/`glassRF`, `mirrorL`/`mirrorR`, `interior`,
`glassF`, dan `hooda`, sedangkan sisanya masuk `_lod0`. Kaca depan, kap, dan spion hanya ada
di kokpit, jadi game menggambar kedua file bersama di LOD0.

FM2 tidak punya header close-up, sehingga header kedua file diambil dari file sejenis milik
mobil donor FM4. Untuk `JAG_XK_07` donornya `JAG_XKRS_09`, yang bodinya sama. Header kokpit
FM4 tidak punya record dan menyimpan titik-titik kokpit (kemungkinan cermin dan kamera) serta
gauge frame. Semua nilai itu milik donor. Blok cermin di 0x104 dinolkan dengan flag 1, karena
FM2 tidak punya mesh `mirrorMiddle` (aturan `carbin_audit.audit_mirror_block`).

Hasil `JAG_XK_07`:

| File | Isi | Audit |
|---|---|---|
| `jag_xk_07.carbin` | 36 section, 523 mesh, 30.579 vertex; 1,40 MB | `audit_conversion` lolos: record dan driver rig terjaga, 4 gauge frame lama dan 11 baru netral; posisi ≤ 0,075 mm, normal ≤ 0,0033°, UV ≤ 0,0002; 26.681 word damage |
| `jag_xk_07_lod0.carbin` | 25 section, 96 mesh, 23.654 segitiga, 22.799 vertex; 1,02 MB (donor 5,2 MB) | segitiga demi segitiga sama dengan LOD1: posisi ≤ 0,073 mm, normal ≤ 0,00001°, UV dan word damage sama; header sama dengan donor mulai 0x154 |
| `jag_xk_07_cockpit.carbin` | 11 section, 20 mesh, 3.399 segitiga, 3.448 vertex; 0,15 MB (donor 2,1 MB) | sama dengan LOD1: posisi ≤ 0,052 mm; header sama dengan donor mulai 0x154 |

Section `_lod0` dan `_cockpit` bersama-sama mencakup semua 36 section model utama tanpa
tumpang tindih. Dibanding kokpit donor, yang tidak ada adalah `a_pillar` dan enam jarum
`speed_*`/`tach_*`.

### 7.6 Batas prototipe

- Uji game dan paketnya dicatat di bagian 8.
- `_lod0` sedetail LOD1, dan kokpit memakai interior FM2 yang dibuat untuk dilihat dari luar.
  Ukurannya sekitar 1/5 dan 1/14 file donor.
- Model utama tidak punya section `wheel` dan `undercarriagea`, yang dimiliki model FM4.
- Titik kokpit dan gauge frame di header kokpit milik donor. Untuk mobil FM2-only tanpa
  kembaran bodi di FM4, donor harus dipilih per mobil, dan pengaruh nilainya belum diketahui.
- Skala ambient 1,48, dua float akhir header, dan sumbu tangent hasil hitungan adalah
  pendekatan yang perlu dicek dengan render.

## 8. Uji game `JAG_XK_07` (paket overlay uji)

Uji 3 November 2026 di Motorsport DX. [`package_fm2_test.py`](package_fm2_test.py) membuat
overlay dengan bentuk yang sama seperti paket FM3 `batch_package.py`, untuk satu mobil saja:
satu `gamedb.slt`, `Media/Cars/JAG_XK_07.zip`, `Thumbnails.zip`, `stringtables.zip` dan
`zipmanifest.xml`.

```powershell
.\.venv\Scripts\python.exe research/cars-fm2-2026-11-02/prototype_fm4_model.py JAG_XK_07 --donor JAG_XKRS_09
.\.venv\Scripts\python.exe research/cars-fm2-2026-11-02/package_fm2_test.py JAG_XK_07 --donor JAG_XKRS_09 --out <paket-baru>
python -m fm4_converter.fm3.test_disc --disc <FM4 Disc 1> --package <paket-baru> --out <disc-uji>
```

Paket `outputs/car-fm2-prototype-2026-11-03/package-v1` dan disc uji
`D:\Data\FM3-to-FM4-tests\fm2-xk07-v1` tidak masuk Git.

### 8.1 Isi paket

| Bagian | Sumber | Catatan |
|---|---|---|
| Model utama, `_lod0`, `_cockpit` | bagian 7 | material kokpit `interior` → `plastic` (8.2) |
| `nodamage`, `damage`, `lights`, `damagelights` | ZIP FM2 | header XDS FM2 sama dengan FM3, jadi `convert_texture` FM3 dipakai apa adanya (konstanta fetch warna FM4, piksel tidak berubah) |
| `*_lod0.xds` | tekstur FM2 yang sama | `_lod0` memakai UV LOD1, jadi atlas LOD1 dipakai juga untuk LOD0 (resolusi FM2) |
| `interior_lod0.xds` | `Nodamage.xds` FM2 | lihat 8.2 |
| `carattribs.xml`, `physics/maxdata.xml` | FM2 | CarAttributes versi 4 / Driver 5 punya preseden native FM4 |
| `shadersettings.xml` | dibuat | hanya `CockpitPlasticPaintScale` 0,169 (aturan mobil FM3) |
| 4 kaliper, 4 rotor | donor `JAG_XKRS_09` | FM2 tidak punya |
| Database | graf stock donor, 60 baris | `Data_Car.Id` 490 (Id FM2), `MediaName`/`Year` FM2; kunci lain baru, kunci DLC terpasang dilewati. Fisika, kelas A, PI 524, velg, `CarPartPositions`, `CameraOverrides`, `CarExceptions` dan `Combo_Colors` milik donor |
| Nama | `Data_Car.str` FM2 | "XK Coupe (FM2)" / "Jaguar XK Coupe (FM2)", dua kunci bebas tertinggi, di semua tabel bahasa yang menang |
| Thumbnail | `Thumbnail_490.xds` FM2 | DXT5 256×128 yang sudah punya alpha cutout; langsung disusun ke atlas FM4 768×288 tanpa penghapusan matte dan tanpa kurva warna FM3 |
| Audio | tidak dikirim | `CarModelTuning.zip` FM4 masih berisi `JAG_XK_07_CMT.xml`; mesin memakai `Data_Engine` donor |

Tidak dikirim: `LiveryMasks/*.xds` FM2 (FM4 memakai `.tga`) dan `ContentSummary.HTM`.
`appearance_audit.audit` lolos: semua teknik ada di efek race dan UI FM4, semua tekstur
yang dirujuk ada, dan rig driver terbaca. Database paket membaca ulang graf yang sama dan
lolos `integrity_check`.

### 8.2 Material interior di kokpit

Audit pertama gagal: `technique()` memetakan mesh LOD0 di part kokpit (`interior`, `seatL`,
`seatR`, `steering_wheel`) ke `cockpit_<material>`, dan `cockpit_interior` tidak ada di efek
FM4. Teknik `interior` (LOD1–5) membaca atlas bodi lewat `baseSampler`/`damageSampler`,
sedangkan semua teknik kokpit bertekstur membaca `CockpitInteriorHiSampler`, yaitu
`Interior_LOD0.xds` di folder mobil (`Shared.zip textures.xml`).

Solusinya: perintah `closeup` v6 menerima daftar `lama baru`, dan prototipe mengganti
`interior` → `plastic` hanya di `_cockpit` (4 mesh). `interior_lod0.xds` diisi atlas bodi
FM2, sehingga UV mesh tetap menunjuk ke teksel yang sama. Model utama tetap memakai teknik
`interior`. Audit segitiga di bagian 7.5 tetap lolos dengan nama baru tersebut.

### 8.3 Hasil Motorsport DX

Harness `e2e.py` (FM4-PC), BuildRoot `I:\FM4-build-usa`, `--profile copy --native`,
`FM4_GAME_CMDLINE=engageaionstart`, langkah Quick Race seperti mobil FM3: merek dipilih
lewat OCR "British automobile", mobil lewat "XK Coupe (FM2)". Setelah start, Back ditekan
empat kali dengan jeda 7 detik untuk berganti kamera. Run
`I:\FM4-build-usa\e2e\fm2-xk07-v1`.

| Pemeriksaan | Hasil |
|---|---|
| Car Select | merek Jaguar menampilkan "2007 Jaguar XK Coupe (FM2)", kelas A 524; model 3D dirender lengkap di garasi (bodi, kaca, lampu, velg donor) |
| Balapan | Bernese Alps Festival Circuit, 12 mobil, start 228 detik setelah launch; balapan sampai menu pause dan kembali, tanpa crash (`crashed` null, `goal_reached` true) |
| Kamera | kokpit: dasbor, konsol tengah, setir, tangan driver, dan spion samping tampil; bumper/hood; chase: bodi, kaca, dan lampu belakang benar |
| Error runtime | kunci sama dengan baseline mobil FM3 (`v5race-*`), ditambah satu error cache shader emulator: file `4D530910.rtv.d3d12.xpso` tidak dapat dibuka untuk ditulis. Error ini tidak berkaitan dengan konten |

Yang terlihat tetapi belum diukur (capture 640×360):

- Kokpit tidak punya `a_pillar`, gauge cluster dan jarum, serta spion tengah, sesuai bagian
  7.5. Panel bawah kiri kokpit tampak sangat terang.
- Kamera kokpit dengan header donor `JAG_XKRS_09` berada di posisi pengemudi yang wajar.
  Untuk mobil tanpa kembaran bodi di FM4, hal ini belum diuji.

### 8.4 Batas

- Satu mobil dan satu run. Fisika, suara mesin, kelas, dan PI masih milik donor. Kalibrasi
  FM2 → FM4 ada di bagian 4.
- Livery editor, foto, replay, dan kerusakan belum diuji, dan livery mask FM2 tidak dikirim.
- Paket ini terpisah dari overlay FM3 `fm3-content-v5`. FM4 hanya membaca satu database,
  jadi menggabungkannya membutuhkan pengemasan bersama.

## 9. Kokpit dan velg `JAG_XK_07`

Lanjutan 3 November 2026. Model dibuat ulang dengan helper v9, yang menambahkan pada `closeup`
penggantian nama material per section beserta UV spion, dan perintah baru `lod0`. Model utama dan
`_lod0` tetap byte-identik dengan v5. Paket uji `package-v3` (spion) dan `package-v4` (spion +
velg FM2) dijalankan di Motorsport DX dengan `--keep-ppm` (capture 1280×720) dan
`FM4_CAPTURE_STATS=1`. Run: `I:\FM4-build-usa\e2e\fm2-cockpit-*`.

### 9.1 Ukuran kokpit terhadap donor

Pembanding adalah `JAG_XKRS_09` asli di disc uji yang sama, dengan langkah yang sama, yaitu Quick
Race Bernese Alps dan kamera kokpit. Median luma patch kokpit selama 25 detik balapan
(`stats.csv`):

| Patch | XK07 (FM2) | XKR-S asli |
|---|---:|---:|
| `road` | 37,9 | 37,9 |
| `dashboard` | 29,0 | 16,7 |
| `wheel` | 41,0 | 70,8 |
| `sky` | 1,8 | 164,9 |
| seluruh frame | 43,4 | 73,0 |

- **Pencahayaan setara.** Patch jalan sama persis. [`cockpit_paint_fm2.py`](cockpit_paint_fm2.py)
  menghitung, untuk 74 mobil di FM2 dan disc FM4, rasio albedo `cockpit_plastic` FM4 yang tampil
  (tekstur × paint scale) terhadap albedo atlas FM2 di UV mesh `interior`. Mediannya 0,18 (IQR
  0,08–0,61), praktis sama dengan 0,169 yang sudah dipakai (aturan FM3). Nilai itu dipertahankan.
- **Plafon hitam berasal dari sumber.** Selisih `sky` dan seluruh frame datang dari plafon. Teksel
  atlas FM2 di vertex plafon bernilai tepat 0, dan median seluruh vertex `interior` juga 0. FM2
  tidak punya kamera kokpit, jadi interiornya dibuat untuk dilihat lewat jendela. Kursi XK FM2
  berwarna gading (luminans linear median 0,35), dan itulah panel terang di kiri bawah kokpit.
- **`a_pillar` belum mendesak.** `a_pillar` FM4 adalah bagian eksterior yang terlihat dari kabin:
  76% normalnya menghadap keluar, dan bentangnya z −1,87 sampai 1,91 m. Atap juga tetap ada di
  `body` pada `_lod0` (1.769 vertex di atas 0,95 m). Pada XK07, pilar dalam kiri dan kanan sudah
  tampil dari mesh `interior` FM2, jadi section ini belum ditambahkan.

### 9.2 Spion

Mesh `chrome` FM2 di `mirrorL`, `mirrorR`, dan `interior` cocok dengan mesh spion donor dalam
posisi, ukuran (0,21 × 0,12 × 0,08 m), dan arah normal (z 0,93). Di FM4 pantulan hanya
digambar untuk material `mirrorLeft`, `mirrorRight`, dan `mirrorMiddle`.

1. **Paket v2 (ganti nama saja):** spion tidak lagi hitam, tetapi hanya berwarna rata. Material
   spion FM4 menampilkan gambar spion di UV 0–1, sedangkan UV kaca FM2 masih menunjuk ke
   potongan atlas kecil (u 0,23–0,27).
2. **Konvensi FM4:** 798 dari 830 mesh spion LOD0 di 305 kokpit disc FM4 punya UV 0–1, dengan U
   naik bersama X model dan V bersama Y.
3. **Helper v8/v9:** UV mesh yang diganti nama menjadi material spion ditulis langsung dari posisi
   X/Y bila vertexnya tidak dipakai mesh lain. Ini berlaku untuk ketiga spion XK07. Bila vertexnya
   dipakai bersama, transform UV di-fit ulang, dan ditolak bila galatnya di atas 0,05 (kaca FM2
   melengkung, galat affine-nya 0,057). Blok spion tengah di header kokpit kini dihitung dari
   `mirrorMiddle` (`carbin_audit.mirror_block`).
4. **Paket v3:** spion tengah dan kedua spion samping menampilkan pantulan hidup (mobil AI di
   belakang terlihat), seperti donor.

### 9.3 Velg

Velg FM2 adalah `.carbin` type 1 dengan satu section `wheel` dan hanya buffer vertex pertama.
Decoder sebelumnya berhenti di akhir file karena buffer kedua kosong dan tidak ada penanda
`0x000DECAF` penutup. Kini [`carbin_fm2.py`](carbin_fm2.py) membaca 407 dari 411 velg; empat sisanya
(`5zigen_hyper_5zr_02`, `enkei_rs5`, `mht_crossover_wheel`, `por_550_56`) berformat lain.

Velg FM3 (type 2) memuat mesh LOD1–5 dengan urutan yang sama persis seperti FM2, ditambah mesh
LOD0. Headernya: type 2, 20 byte nol, lalu blok format yang sama seperti mobil FM3. Sebanyak 270
dari 389 velg FM3 identik sampai dua float akhir. Rig velg FM3 hanya berisi 1,0 di float ketujuh,
dan word ke-41 setelah rig bernilai 0. [`fm2_to_fm3.py`](fm2_to_fm3.py) memakai konstanta itu, dan
dua float akhir diisi median velg FM3.

Alur velg di [`prototype_fm4_model.py`](prototype_fm4_model.py):

1. transkode ke velg FM3;
2. `carbin-cpu convert` menjadi velg FM4 type 3 dengan LOD1–5, diaudit `audit_conversion`;
3. `carbin-cpu lod0` (`Lod0FromLod1` ForzaEditor) menyalin LOD1 tanpa ban ke LOD0, seperti 441
   dari 442 velg FM4, dengan draw list LOD0 dan rentang LOD 0–5 di header 0x15C.

`audit_wheel_lod0` membandingkan LOD1–5 sebelum dan sesudah, serta setiap mesh LOD0 dengan mesh
LOD1-nya.

[`check_fm2_wheels.py`](check_fm2_wheels.py) menjalankan alur ini pada semua velg FM2:

| Pemeriksaan | Hasil |
|---|---|
| Velg berformat FM2 | 407 dari 411, 0 gagal |
| `audit_conversion` | posisi ≤ 0,016 mm, normal ≤ 0,0034°, UV ≤ 0,0004 |
| LOD1–5 setelah `lod0` | posisi ≤ 0,016 mm |
| LOD0 terhadap LOD1 | identik |
| Header vs velg FM3 asli (172 velg di kedua game) | 135 identik selain dua float akhir; 37 velg FM3 punya word 1 dan vektor kecil di 0x4–0x10 (x 0,02–0,07 m, kemungkinan offset velg) yang tidak ada di FM2 dan ditulis 0 |

Velg `JAG_XK_07` (`List_Wheels.MediaName` FM2 sama dengan nama mobil): 4.761 vertex, 22 mesh
LOD1–5, dan 4 mesh LOD0 dengan 3.046 segitiga. `package-v4` mengirim `Media/Wheels/JAG_XK_07.zip`
berisi model ini dan tekstur velg FM2 (DXT1/DXT5 256×256, dengan `convert_texture`).
`wheel_lod0.xds` diisi `wheel.xds`, karena LOD0 memakai UV LOD1. Baris `List_Wheels` tetap milik
donor kecuali `MediaName`, sehingga massa velg dan `BrakeDrawOffset` masih nilai XKR-S.
`appearance_audit` lolos.

Hasil run `fm2-cockpit-xk07v4`: tidak ada crash, dan kunci error sama dengan run sebelumnya. Di
garasi Car Select, velg 10 palang XK '07 FM2 dirender di LOD0 bersama ban dan kaliper donor.

### 9.4 Batas

- Plafon dan sebagian besar interior FM2 tetap hitam, sesuai atlas FM2. Mengganti plafon dengan
  `cockpit_headliner` (warna konstanta FM4) berarti menambah tampilan yang tidak ada di sumber,
  dan butuh pemisahan mesh per segitiga.
- Gauge cluster, jarum, dan `a_pillar` belum ada.
- Offset velg dari 37 velg FM3 tidak punya padanan di FM2. Pengaruh nilai 0 belum diuji pada
  velg yang membutuhkannya.
- Kaliper, rotor, dan massa velg masih milik donor. Section `undercarriagea` dan `exhaust*`
  tambahan FM3 (bagian 5.3) belum ditangani.

## 10. Kalibrasi fisika FM2 → FM4

Lanjutan 3 November 2026. [`physics_fm2.py`](physics_fm2.py) membaca konfigurasi stock FM2,
membandingkannya dengan mobil yang sama di FM4, dan menulis hasilnya ke paket uji lewat
`package_fm2_test.py --physics`. Hasil di `outputs/car-fm2-research-2026-11-02/physics/study.json`:

```powershell
.\.venv\Scripts\python.exe research/cars-fm2-2026-11-02/physics_fm2.py
```

### 10.1 Extractor dan pasangan

`extract` mengikuti `IsStock=1` lewat `Ordinal` dan `EngineID`, lalu menyusun hasilnya dalam
role, tabel, dan nama kolom FM4 seperti `converter.extract_stock`. Hampir semua tabel part FM2
punya padanan FM4 dengan kolom bernama sama; perbedaannya:

- `List_UpgradeWeight` → `List_UpgradeCarBodyWeight`, `List_UpgradeEngineCamValves` →
  `List_UpgradeEngineCamshaft`, `List_UpgradeEngineBlock` → `List_UpgradeEngineDisplacement`,
  transmisi/kopling/diferensial/driveline → `List_UpgradeDrivetrain*`, `List_UpgradeEngineTurbo`
  → turbo single atau twin.
- Satu baris FM2 dipecah per gandar: anti-roll, lebar ban, dan ukuran rim.
- Geometri model (`Model*`, `BottomCenterWheelbasePos*`) pindah dari `Data_Car` ke
  `Data_CarBody`. Drive type pindah dari `Data_Engine` ke `Data_Drivetrain`. Ukuran ban stock
  pindah ke kolom `Data_Car` bernama baru.
- Skala kurva zero-throttle masuk ke `ZeroThrottleTorqueScale`, seperti jalur FM3.

Kolom FM4 tanpa sumber FM2 tetap milik donor. Contohnya: grip chassis, part oil
cooling/piston/valves (semuanya 1,0 di donor), `MaxStretchDeltaFromRideHeight`, `CVTShiftTime`,
dan bounding box bodi. `AutoSteerOverrideID` juga tetap donor, karena ambang STM FM2 (1,5/2,5 pada
310 mobil) tidak ada di `AutoSteerOverrides` FM4 (hanya 1,5/3,0).

**Pasangan.** Id, `MediaName`, tahun, dan merek harus sama di FM2 dan disc FM4. Hasilnya 184
pasangan: 147 training dan 37 validation, dibagi per mesin FM2 seperti jalur FM3. Sebanyak 18
Id dikeluarkan karena nama atau tahunnya berbeda.

### 10.2 Aturan skala (metode `value_scales`)

`value_scales.study` kini menerima observasi dari sumber lain (`rows`, `salt`); jalur FM3 tidak
berubah. Dari 453 kolom yang dibandingkan:

- **278 tidak sistematis:** identity sudah cocok pada ≥ 80% training.
- **46 aturan diterima**, terutama konvensi FM4 yang seragam di hampir semua mobil:
  - rate kemudi 105;
  - TCS 33 dan 0,5;
  - lima parameter ABS;
  - bumpstop 200 dan 2, clamp damper 10;
  - `TireAeroHack*`.

  Ada juga skala linear: `SteerMaxAngle`, `CMHeight`, `GameFrictionScaleBraking`, rate damper
  maksimum, dan PI serta rating.
- **86 ditolak validation**, dan 43 lainnya tidak punya kandidat sah atau barisnya kurang.

Rate pegas, damper, dan anti-roll, tinggi suspensi, massa, rasio gigi, serta kurva torsi tidak
punya skala global. FM4 menyetel ulang nilai ini per mobil:

- `DefSpringRate` FM2 tidak sama dengan FM4 pada satu pasangan pun (median rasio 0,87; p10–p90
  0,59–1,50), dan juga tidak sama dengan FM3 (0 dari 368 gandar).
- Kurva torsi: 157 pasangan punya jumlah sampel dan RPM maksimum yang sama, tetapi hanya 4 yang
  sampelnya identik.

Ada pula konvensi yang tergantung jenis penggerak. Di FM4, LSD tengah bernilai 0 pada 335 dari
335 mobil RWD, sedangkan di FM2 96% mobil RWD menyimpan nilai. `drive_conventions` mencatat
kolom diferensial yang bernilai tunggal pada ≥ 99% mobil FM4 sejenis penggerak.

### 10.3 FM2 atau donor

Untuk mobil FM2-only, pilihannya bukan identity melawan aturan, melainkan nilai FM2 melawan
donor. Maka setiap pasangan juga diberi donor, dengan aturan yang sama seperti paket uji: mobil
FM4 drivable lain dengan merek dan penggerak yang sama, serta massa dan tenaga terdekat. Contoh
donor yang sering terpilih: `SUB_LegacyB4GT_10` dan `CHE_CamaroZ28_79`.

Kolom yang bekerja bersama diputuskan sebagai satu grup:

- pegas kedua gandar beserta tinggi stock;
- anti-roll kedua gandar;
- transmisi beserta `NumGears`;
- kurva torsi beserta camshaft, displacement, dan `GameTorqueScale`;
- massa beserta CM dan `CurbWeight`;
- ban dan rim;
- geometri bodi, aero bodi beserta `GameDragScale`, dan part aero;
- LSD, dan skala boost.

Kolom lain diputuskan sendiri-sendiri.

**Skor.** Skor grup adalah rata-rata, per kolom, dari galat FM2 / (galat FM2 + galat donor).
Galat kolom kontinu adalah MAE dibagi rata-rata |FM4|; galat kategori adalah 1 − kecocokan.
Kurva torsi dibandingkan sebagai torsi efektif (sampel × `TorqueScale` × `GameTorqueScale`) pada
grid RPM FM4, dibagi torsi puncak. FM2 dipakai hanya bila skornya ≤ 0,5 pada training **dan**
validation.

| Grup | Skor FM2 training / validation | Sumber |
|---|---|---|
| Kurva torsi dan mesin (12 kolom) | 0,21 / 0,17 | FM2 |
| Massa dan CM (10) | 0,22 / 0,18 | FM2 |
| Transmisi (14) | 0,18 / 0,22 | FM2 |
| Pegas dan damper (39) | 0,28 / 0,27 | FM2 |
| Ban dan rim (12) | 0,11 / 0,20 | FM2 |
| Geometri bodi (8) | 0,16 / 0,13 | FM2 |
| LSD (7) | 0,44 / 0,36 | FM2 |
| Anti-roll (6), aero bodi (7) | 0,47 / 0,46 | FM2 |
| Part aero depan/belakang (10) | 0,51 / 0,50 | donor |
| Turbo (9), supercharger DSC (7) | 0,52 / 0,64; 0,43 / 1,00 | donor |

Galat kurva torsi efektif rata-rata 0,14 (FM2) melawan 0,38 (donor) pada training, dan 0,17
melawan 0,46 pada validation. FM2 lebih dekat pada 116 dari 147 dan 31 dari 37 pasangan. Dari 46
grup fisika, 34 memakai FM2. Sisanya donor, antara lain:

- inersia mesin, flywheel, dan driveline;
- waktu kopling;
- massa mesin dan velg;
- satu titik ABS.

### 10.4 `JAG_XK_07` dengan fisika FM2

`physics_fm2.apply` menimpa graf stock donor yang sudah dikloning:

- Grup FM2 memakai nilai FM2, atau aturan yang diterima bila ada.
- Triplet stock yang di FM2 tidak bisa disetel (Min = Def = Max) tetap begitu, seperti 384 dari
  503 suspensi stock FM4.
- Sampel torsi tak aktif diisi 0, dan slot gigi tak terpakai diisi −1, keduanya konvensi FM4.
- Kelas dihitung ulang dari PI dengan `performance_index.apply`.
- Part aspirasi donor yang tidak dimiliki mobil FM2 dibuang. Untuk XK07, DSC dan intercooler
  XKR-S dibuang; DSC itu memberi skala boost 1,442.
- Enum yang tidak dikenal FM4 ditolak, begitu pula triplet yang tidak berurutan.

`package-v6` mengubah 126 nilai; contohnya:

| Nilai | Donor XKR-S | FM2 → FM4 |
|---|---:|---:|
| Massa | 1.760 kg | 1.595 kg |
| PI mentah / kelas | 0,4439 / A | 0,3869 / B |
| Aspirasi | DSC 0,884 bar | NA |
| Kurva torsi | 81 sampel, maks 8.000 rpm | 86 sampel, maks 8.500 rpm |
| Redline | 6.500 rpm | 7.000 rpm |
| Final drive / waktu ganti gigi | 3,31 / 0,20 s | 3,46 / 0,146 s |
| Pegas depan / belakang | 51,0 / 45,2 | 49,0 / 43,4 |
| Tinggi stock depan | 0,137 m | 0,162 m |
| Rem depan | 15 in, 6 piston | 13 in, 4 piston |
| Rim depan / belakang | 20 / 20 in | 21 / 21 in |

### 10.5 Uji game

Semua run memakai Quick Race Bernese Alps sampai finis dengan AI mengemudikan mobil pemain,
`FM4_FIXED_SEED=1` dan `FM4_FIXED_FRAME_TIME=1`. Durasi diukur dari event layar.

| Run | Fisika | Kelas | Durasi balapan | Posisi |
|---|---|---|---:|---|
| `fm2-xk07-v4-fin` | donor | A | 258,7 s | 1st |
| `fm2-xk07-v5-fin` | FM2 (`package-v5`) | B | 262,4 s | 1st |
| `fm2-xk07-v5-fin2` | FM2 (`package-v5`) | B | 262,4 s | 1st |
| `fm2-xk07-v6-fin` | FM2 (`package-v6`) | B | 262,1 s | 1st |

- Tidak ada crash, dan kunci error runtime sama dengan run sebelumnya.
- Dua run v5 hanya berselisih 0,02 s, jadi hasilnya dapat diulang.
- Mobil dengan fisika FM2 3,7 s lebih lambat daripada versi donor, sesuai mesin NA ±300 hp
  melawan XKR-S supercharged.
- Kelas yang berbeda bisa mengubah lawan AI di grid, jadi angka ini bukan ukuran kemiripan
  handling.
- `package-v5` dibuat sebelum konvensi penggerak dan keputusan per kolom. Selisihnya dengan v6
  adalah LSD tengah RWD (v5: 464, v6: 0), titik ABS belakang, waktu kopling, serta inersia mesin,
  flywheel, dan driveline.

### 10.6 Batas

- Studi membandingkan nilai database, bukan handling. Skor ≤ 0,5 berarti nilai FM2 lebih dekat
  ke angka FM4 asli daripada donor, bukan bahwa mobil terasa seperti di FM4.
- Validation 37 pasangan dipakai untuk memilih sumber per grup; tidak ada test set ketiga. Donor
  pada studi dipilih otomatis, sedangkan donor paket dipilih manual.
- `CMHeight` memakai aturan linear (MAE 0,069). Jalur FM3 punya estimasi dari ride height dan
  bounding box (`code_semantics`); padanannya untuk FM2 belum dikerjakan.
- Turbo dan supercharger FM2 belum bisa dipasang bila donor tidak punya part yang sama
  (`apply` menolak). Massa velg, aero part, dan grip chassis tetap milik donor.

## Batas riset

Katalog FM3/FM4/DLC berasal dari evidence riset 20 Oktober yang dibangun dari
database lokal, bukan dibaca ulang dari disc. Kecocokan nama atau ID tidak
membuktikan geometri, fisika, atau livery yang identik. Decoder `.carbin` FM2 hanya
diverifikasi terhadap FM3 untuk LOD1; LOD2–5 dibaca dengan aturan yang sama tetapi
tidak dibandingkan. Penulis model FM4 (bagian 7) baru prototipe, diaudit secara statis
untuk satu mobil lengkap dan model utama semua mobil FM2. Uji game baru dilakukan untuk
satu mobil di satu lintasan (bagian 8–10). Kalibrasi fisika (bagian 10) dinilai pada nilai
database pasangan FM2∩FM4, bukan pada perilaku berkendara.
