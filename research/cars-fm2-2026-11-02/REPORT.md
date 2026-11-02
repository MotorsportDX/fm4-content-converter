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

Urutan berdasarkan risiko. Dekode `.carbin` FM2 (bagian 5) dan perilaku loader FM4
untuk file yang tidak ada (bagian 6) sudah dikerjakan.

1. **Bentuk `_lod0` dan `_cockpit` dari data FM2** (bagian 6.4): penulis FM4 untuk
   LOD1 FM2 sebagai LOD0, serta kokpit dari section interior FM2. Perlu dipastikan
   section mana yang wajib, misalnya `a_pillar`, dan dari mana posisi kamera kokpit
   berasal.
2. **Roda dan section yang tidak ada di FM2.** Roda FM2 berada di `Media/wheels`,
   sedangkan bodi FM3 memuat section `wheel`; `undercarriagea` dan beberapa
   `exhaust*` juga hanya ada di FM3 (bagian 5.3).
3. **Kalibrasi fisika FM2 → FM4** dengan pasangan FM2∩FM4, mengikuti metode
   benchmark 30 mobil FM3.
4. **Verifikasi 45 mobil `fm4_same_id_renamed`** dan kandidat `near_matches`
   sebelum menetapkan daftar final FM2-only.
5. Buka paket STFS Bonus Disc untuk aset 4 mobil FM2-only dari paket bonus.
6. Sisa format: 32 byte terakhir vertex FM2, header 0x100 byte, record 140 byte,
   dan arti pembagian dua buffer vertex (bagian 5.4).

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

- 32 byte terakhir vertex. Kandidatnya data kerusakan/deformasi atau frame tangent.
  Tangent FM3 di offset 36 tidak muncul langsung di vertex FM2.
- Isi header 0x100 byte, record 140 byte, blok 0x6C byte dan 0x1C byte di setiap
  section. Decoder melewatinya seperti Forza Studio.
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

## Batas riset

Katalog FM3/FM4/DLC berasal dari evidence riset 20 Oktober yang dibangun dari
database lokal, bukan dibaca ulang dari disc. Kecocokan nama atau ID tidak
membuktikan geometri, fisika, atau livery yang identik. Decoder `.carbin` FM2 hanya
diverifikasi terhadap FM3 untuk LOD1; LOD2–5 dibaca dengan aturan yang sama tetapi
tidak dibandingkan. Belum ada penulis FM4 untuk model FM2, dan belum ada pengujian
di game.
