# FM3 → FM4 stock-car database prototype

Jalur FM3 ini adalah implementasi sumber pertama dalam
[FM4 Content Converter](../README.md), project untuk mengonversi konten
kendaraan dari berbagai game ke Forza Motorsport 4. Dokumentasi berikut khusus
untuk jalur FM3 → FM4; dukungan game sumber lain masih direncanakan.

Prototype offline yang dimulai dari Toyota 2000GT 1969 (`TOY_2000GT_69`) dan diperluas ke benchmark 30 mobil. Membaca database asli melalui SQLite read-only, mengekstrak konfigurasi stock berdasarkan relasi, menghasilkan database terpisah dengan schema FM4, lalu membandingkannya dengan konfigurasi asli FM4 berdasarkan peran komponen.

Prototype database memerlukan Python 3.11+ dan standard library. Jalur pengemasan/validasi aset juga memerlukan NumPy dan Pillow, helper model CPU, serta decoder lokal yang dijelaskan di bawah. Perintah converter tidak menjalankan game, memasang DLC, mengubah database sumber, atau mengedit save/profile.

## Menjalankan

Siapkan Python 3.11+ 64-bit mengikuti [setup repository](../README.md#setup-python).
Converter inti tidak memerlukan paket pip. Untuk fitting riset, pengemasan aset
dan seluruh suite tes, instal dependensi terpin dari root workspace:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

Contoh `python` di bawah mengasumsikan interpreter `.venv` tersebut. Gunakan
`.\.venv\Scripts\python.exe` sebagai pengganti `python` jika environment belum
diaktifkan. Dependensi native helper/decoder disiapkan terpisah sesuai petunjuk
aset di bawah.

Dari root workspace:

```powershell
python -m fm4_converter.fm3.converter --out outputs/fm-car-converter/toyota-2000gt-run2
python -m unittest discover -s tests -p test_converter.py -v
```

Default sumber adalah database FM3 USA regular dan FM4 Japan/Asia Disc 1 lokal. Gunakan `--fm3` dan `--fm4` untuk path alternatif. `--out` wajib folder baru di luar kedua direktori game. `--media-name` dan `--id-base` tersedia untuk eksperimen; cakupan yang telah diperiksa adalah Toyota dan panel 30 mobil stock pada dump ini. Ini belum merupakan batch converter untuk seluruh mobil atau DLC siap pasang.

## Studi kalibrasi lintas mobil

```powershell
python -m fm4_converter.fm3.calibration --out outputs/fm-car-converter/calibration-new-run --compare-heldout
python -m unittest discover -s tests -p "test_*.py" -v
```

Studi membandingkan 309 pasangan dengan MediaName/tahun/make yang sama, setelah mengeluarkan Toyota dan lima varian yang berubah identitas. Split 236 training dan 73 validation dikelompokkan menurut engine FM3. Parameter aturan dan ambang disimpan sebelum validasi. Toyota baru dibandingkan sesudah aturan dibekukan.

Lima aturan steering/ABS lolos ambang; faktor steering angle mempunyai pengecualian. Hipotesis tingkat suspensi mengurangi error tetapi pemilihan tingkat hanya benar 38/51 (74,51%) pada subset validation tercakup, di bawah ambang 75%. Ambang dipertahankan; profil ini belum diterima untuk pemakaian otomatis.

`--compare-heldout` menghasilkan dua database penelitian terpisah: `toyota-conservative` dan `toyota-experimental`, serta `TOYOTA_COMPARISON.md`. Selisih Toyota berkurang dari 36 menjadi 31 dengan aturan konservatif; eksperimen suspensi menghasilkan 7 kolom berbeda. Hasil Toyota tidak membuktikan bahwa pemilihan tingkat akan benar untuk mobil lain.

Untuk memakai file aturan yang telah dibentuk:

```powershell
python -m fm4_converter.fm3.converter --out outputs/fm-car-converter/next-stock-run --calibration-rules outputs/fm-car-converter/calibration-new-run/rules.json
```

Tanpa `--calibration-rules`, converter tetap memakai baseline semula. Dengan file aturan, mode default `conservative` hanya menerapkan pola yang lolos. Mode `estimated` juga menghormati penolakan profil suspensi. Mode `experimental` secara eksplisit melewati gerbang profil tersebut hanya untuk membuat kandidat riset offline; output tetap ditandai belum siap dipasang.

Kapasitas tangki, compound stock, kalibrasi CG native, dan grip chassis tidak mempunyai konversi universal yang telah terbukti. Transformasi representasi `CMHeight` yang kemudian ditemukan melalui kode dijelaskan pada bagian adapter koordinat di bawah. Ringkasan seluruh 36 kolom, contoh mapping ambigu, hasil per mobil dan regresi tersimpan pada laporan/JSON studi. Nilai native dan toleransi pembulatan tidak merupakan validasi handling.

## Studi lanjutan tujuh kolom

`remaining.py` memakai NumPy untuk fitting; menjalankan converter dengan file aturan yang sudah terbentuk tetap hanya memerlukan standard library. Lima fold menurut engine pada **236 training** memilih model sebelum evaluasi **73 validation**. Toyota tidak masuk fitting. Validation tersebut dipakai ulang dari studi sebelumnya; hasilnya bukan test set independen baru.

```powershell
python -m fm4_converter.fm3.remaining --out outputs/fm-car-converter/remaining7-new-run --previous-rules outputs/fm-car-converter/calibration-v2/rules.json
python -m unittest discover -s tests -p "test_*.py" -v
```

Studi menemukan hubungan antar empat kolom grip pada 309/309 pasangan, tetapi nilai grip depan masih harus diestimasi. Rumus regresi yang dibulatkan ke grid 0,005 menghasilkan 53/73 nilai depan tepat pada validation. Estimasi CG dari CMHeight, ride height dan bounding box FM3 mengurangi MAE validation dari 0,164358 menjadi 0,0120329 dalam skala kolom database; tidak ada klaim kesamaan handling.

Pada Toyota, grip depan/belakang menjadi 0,965/0,9825 (FM4 asli 0,970/0,985), dan CMHeight menjadi 0,4159 (asli 0,4421). Jumlah kolom fisika berbeda tetap tujuh, meski lima nilainya lebih dekat. Semua model compound yang diuji kalah dari identity pada CV. Prediksi diagnostik tangki 60 kebetulan cocok dengan target Toyota, tetapi model memiliki p90 error CV 30 dan tidak diterapkan; diperlukan spesifikasi independen. Kandidat mempertahankan compound 5 dan tangki 20.

`rules.json` studi lanjutan dapat digunakan melalui argumen converter yang sama. Aturan baru hanya aktif pada `--calibration-mode experimental`, setelah gerbang numerik CV/validation lolos. Mode conservative/estimated tidak berubah dan gerbang suspensi lama tetap ditolak. Prediksi di luar domain training tidak diterapkan. Perubahan compound eksperimental, jika terpilih pada studi lain, juga memperbarui audit seluruh dependensi kurva ban native FM4.

Artefak studi mencakup protokol kandidat, aturan sebelum/sesudah validation, semua hasil CV, per-mobil validation, ambiguitas, tiga kandidat SQLite, laporan perbandingan Toyota, dan manifest hash. Tes fitting baru memerlukan NumPy dan database lokal; jika dependensi tidak ada, tes tersebut dilaporkan skip.

## Benchmark 30 mobil

`benchmark.py` menjalankan lima kandidat per mobil: baseline, conservative, experimental, refined_conservative dan refined_experimental. Panel tetap berisi 18 RWD, 6 FWD, 6 AWD, 19 mesin depan, 11 mesin tengah, termasuk rotary dan diesel race. Seluruh mobil berasal dari validation sebelumnya, bukan training; ini tetap bukan test set independen baru. Identitas panel dibekukan sebelum konversi lengkap, dan kasus sulit tidak diganti dengan mobil yang lebih mudah.

```powershell
python -m fm4_converter.fm3.refinements --out outputs/fm-car-converter/refinements-next --rules outputs/fm-car-converter/remaining7-v2/rules.json
python -m fm4_converter.fm3.benchmark --out outputs/fm-car-converter/benchmark-next --rules outputs/fm-car-converter/refinements-next/rules.json
```

Pada panel ini, terdapat 13.433 perbandingan kolom fisika stock per mode dan dua role stock yang belum direkonstruksi. Selisih baseline/conservative/experimental/refined_conservative/refined_experimental: **1.159 / 1.010 / 596 / 992 / 564**. Refined memperbaiki 18 kolom pada conservative dan 32 pada experimental tanpa regresi tambahan di panel. Eksperimen lengkap masih memperburuk 69 kolom terhadap baseline pada delapan mobil; counts merupakan kolom, termasuk nilai tuning berkorelasi, bukan ukuran kesamaan handling.

Aturan baru ditulis ke profil terpisah. `GameFrictionScaleBraking` 1,01→1,0025 didukung 54 training/19 validation. Camber compression/expansion 0→0,25 hanya pada suspensi independen didukung 60 training/30 validation, dihitung per mobil. Kedua aturan lolos gerbang conservative pada profil baru. Lookup pengereman 1,03→1,005 dan 1,05→1,01 serta front toe 0,5→0 tetap eksperimen karena dukungan validation terbatas atau ada pengecualian. Sumber nilai lain dan solid axle tidak diubah. Profil lama tetap menghasilkan aturan lama.

Benchmark juga menemukan kebutuhan berikut:

- Inertia transmisi berbeda pada 23 mobil, aero/drag pada tujuh mobil, dan final drive pada enam mobil; belum ada faktor universal.
- Viper GTS-R 2000 mempunyai data mesin/massa berbeda antara versi game: 6.200/8.000 cc, 8/10 silinder, 1.350/1.150 kg. Kesamaan nama dan ID belum cukup sebagai kesamaan varian fisika.
- Ferrari 333 SP memiliki 151/123 sampel kurva dan MaxRPM 15.000/12.250. Raw index comparison tetap disimpan, tetapi tidak dianggap pembandingan kurva pada grid RPM identik.
- Viper GTS-R dan Ferrari 333 SP mempunyai stock restrictor FM4 yang tidak ada dalam graph FM3. Comparator mencatat dua role hilang; struktur patch yang lolos tidak berarti semua part target tersedia.
- Audi R10 memiliki DefSpringRate belakang 151,1875 di atas Max 150 pada kedua game. Validator mempertahankan dan memperingatkan triplet tuning yang diwarisi persis dari sumber. Pelanggaran baru atau Min>Max tetap gagal; nilainya tidak di-clamp.

Artefak per mobil berisi lima SQLite terpisah, source/reference IR, semua nilai comparator, dependensi ban native, perubahan per mode, dan diagnosis varian/kurva/stock role. ID setiap mobil memiliki blok terpisah; kelima mode adalah alternatif dan tidak boleh digabung menjadi satu paket. Graph ban global diperiksa terpisah dari totals kolom fisika. EngineGraphingMaxPower/Torque dan manufacturer roda diklasifikasikan sebagai metadata, tetapi tetap tercantum dalam comparison.

## Perbaikan audit dan eksperimen berikutnya

Hasil canonical berada di `outputs/fm-car-converter/next-stage-v1/`. **Tidak ada aturan numerik baru yang dipromosikan:** conservative tetap 992 selisih, sementara eksperimen pengganti suspensi menghasilkan **807**, lebih banyak daripada 564 pada refined_experimental. Toyota juga berubah dari 7 menjadi 19 selisih pada eksperimen baru. Seluruh mode lama tetap tersedia dan 450 artefak kandidat/comparison/ban lama direproduksi identik.

Peningkatan yang diterapkan pada converter:

- Semua proposal diperiksa sebelum mutasi, termasuk kolom tumpang tindih, nilai nonfinite, mapping hilang, provenance, metadata model, dan serialisasi hash. Kegagalan tidak meninggalkan sebagian perubahan.
- Profil suspensi baru tidak kembali ke aturan lama saat abstain. Suspensi adjustable, race, anomali tuning, dan nilai di luar dukungan training dipertahankan.
- `compatibility.json` mengaudit konfigurasi/displacement, massa, domain torque, dan stock role sesudah konversi. Benchmark mempertahankan total semua 30 mobil dan memberi strata 29 pasangan yang lolos kriteria spesifikasi serta 28 yang juga memiliki domain/role sama. Audit pasangan memerlukan reference; tidak memberi jawaban target untuk mobil FM3-only.

`suspension_v2.py` menguji 78 kandidat tier pada training engine-group CV; semuanya gagal gerbang. Alternatif partial-component dipilih dari training, tetapi validation menghasilkan 4/53 mobil memburuk (7,55%, batas 5%), sehingga tetap ditolak. Mode experimental dapat menyimpannya sebagai kandidat riset; conservative/estimated abstain. Pada panel 30, jumlah kolom memburuk terhadap baseline FM3 turun 69→41, tetapi terhadap eksperimen sebelumnya 40 membaik dan 286 memburuk, tersebar pada 19 mobil. Penurunan risiko terhadap baseline tersebut bukan peningkatan akurasi keseluruhan.

`drivetrain_v2.py` mengelompokkan engine, payload mesin identik, dan keluarga model saat CV. Offset inertia +0,0008 untuk lingkup race modern memperbaiki 12 prediksi CV tanpa regresi; validation hanya mencakup Audi R10, di bawah kebutuhan empat mobil/tiga keluarga. Aturan ditolak pada semua mode. Inertia, final drive, dan aero tidak diberi faktor baru.

`compatibility.py` mengaudit 309 pasangan: 308 lolos kriteria spesifikasi, sembilan perubahan massa untuk review, tiga perubahan domain torque, dan enam perubahan stock role. Lima kasus memiliki restrictor FM4 baru; satu intercooler FM3 tidak ada pada target. Sintesis restrictor ditolak karena pola training yang mendukung hanya dua Viper, dan FM4 juga memiliki stock restrictor non-neutral. Perbedaan indeks kurva pada domain berbeda tidak diartikan sebagai error pada RPM identik.

Reproduksi dengan direktori output baru:

```powershell
python -m fm4_converter.fm3.suspension_v2 --out outputs/fm-car-converter/suspension-study-new
python -m fm4_converter.fm3.drivetrain_v2 --out outputs/fm-car-converter/drivetrain-study-new
python -m fm4_converter.fm3.next_stage --base-rules outputs/fm-car-converter/benchmark30-refinements-v1/rules.json --suspension-model outputs/fm-car-converter/suspension-study-new/rules.json --drivetrain-model outputs/fm-car-converter/drivetrain-study-new/rules.json --previous-benchmark outputs/fm-car-converter/benchmark30-v3 --out outputs/fm-car-converter/next-stage-new
```

Studi final: `suspension-v2-study4`, `drivetrain-v2-reviewed`, dan `compatibility-v3`. Validation 73 mobil dipakai ulang, bukan test set independen; pengelompokan engine suspensi belum menjamin independensi semua chassis/trim. Uji integrasi menghasilkan 210 SQLite benchmark dan empat Toyota, semuanya lolos validasi struktur; satu peringatan tuning bawaan Audi R10 tetap dilaporkan. **91 tes lulus**, database asli tidak berubah. Hasil ini belum merupakan DLC atau uji handling game.

## Adapter koordinat v1 berdasarkan kode FM3/FM4 — hasil historis

Bagian ini mencatat hasil versi pertama. Opsi `--code-semantics` sekarang menjalankan v2 yang dijelaskan di bagian berikutnya; pemilihan stock ride height dari `DefRideHeight` di v1 telah diganti berdasarkan bukti tambahan.

Studi `outputs/fm-car-converter/code-semantics-v1/REPORT.md` membandingkan executable retail FM3 USA dan FM4 Japan/Asia. Image diekstrak ulang dan identitasnya diverifikasi; instruksi FM4 hasil recomp yang digunakan dicocokkan dengan disassembly byte asli. Analisis ini tidak menjalankan game.

FM3 memasukkan `CMHeight + Data_CarBody.BottomCenterWheelbasePosy` ke pusat komponen massa utama. FM4 lebih dahulu mengurangi `CMHeight` dengan rata-rata tinggi stock depan/belakang yang dibobot distribusi massa efektif. Untuk body/origin yang sama, stock part dengan seluruh `WeightDistDiff = 0`, dan distribusi dalam domain yang didukung:

```text
FM4.CMHeight = FM3.CMHeight
             + FM4.Data_Car.RearStockRideHeight
             + (FM4.Data_Car.FrontStockRideHeight
                - FM4.Data_Car.RearStockRideHeight) * CMBackFront
```

`code_semantics.py` menerapkan transformasi ini melalui opsi baru `--code-semantics`. Opsi tidak aktif secara default. Adapter menolak perubahan body, input massa yang terlihat, pilihan role stock, distribusi nonzero-delta, serta estimasi CG/rate yang bertentangan. Validasi dilakukan sebelum mutasi. Tinggi stock yang dipakai adalah nilai yang benar-benar ditulis ke `Data_Car` kandidat; cara prototype memilih tinggi tersebut dari source `DefRideHeight` masih merupakan asumsi tersendiri. Jangan menyamakan kolom tersebut dengan `Data_CarBody.ModelFrontStockRideHeight`/`ModelRearStockRideHeight`.

```powershell
python -m fm4_converter.fm3.converter --out outputs/fm-car-converter/toyota-code-new --calibration-rules outputs/fm-car-converter/benchmark30-refinements-v1/rules.json --calibration-mode conservative --code-semantics
```

Jalur default/tuning, interpolasi dan pemakaian rate spring/damper/anti-roll yang ditelusuri sama pada kedua game. Tidak ditemukan dasar untuk pengali rate global; faktor massa runtime sudah diterapkan game. `effective_physics.py` membandingkan 18 koefisien ternormalisasi per mobil, atau memakai faktor massa jika diberikan secara eksplisit. Audi R10 dengan default 151,1875 di atas maksimum 150 menghasilkan koefisien default efektif 150 melalui normalisasi runtime, tanpa mengedit database.

Benchmark baru memakai 30 mobil panel lama dan Toyota terpisah, semuanya dengan refined_conservative:

- Input Y pusat komponen massa utama dipertahankan pada **31/31** mobil.
- **558/558** koefisien suspensi ternormalisasi tetap sama dengan FM3; kesamaan faktor massa runtime belum diukur.
- Evaluasi 11 instruksi aritmetika asli FM4 cocok pada **31/31** mobil, error maksimum 3,30e-8. Tes juga mencakup 250 sampel normal; ini bukan emulasi PPC lengkap.
- Hanya `CMHeight` berubah dari kandidat konservatif sebelumnya. Selisih kolom native tetap **992 → 992** pada panel 30 dan **31 → 31** pada Toyota. Kesamaan nilai native merupakan tujuan kalibrasi terpisah.
- Toyota: raw `CMHeight` **0,2539 → 0,4070** menghasilkan input lokal **0,2539**, dibanding **0,1008** jika disalin mentah. FM4 asli menggunakan raw **0,4421** dan input lokal **0,2890**.
- **113 tes lulus**; seluruh 31 kandidat lolos validasi struktur. Panel bukan test set independen baru.

`code_semantics.json` mencatat bukti dan asumsi transformasi; `effective_comparison.json` memisahkan pelestarian input FM3 dari perbandingan native FM4. Ringkasan benchmark dan hash ada di `code-semantics-v1/benchmark31/`.

Pembuktian ini terbatas pada input komponen massa utama dan koefisien yang ditelusuri. Pusat massa agregat seluruh kendaraan, geometri/collision aset, solver lengkap, title update, serta handling belum divalidasi. Field baru FM4 `MaxStretchDeltaFromRideHeight` mempunyai fungsi batas extension, tetapi nilai konversi yang tepat belum ditentukan. Adapter belum menghasilkan DLC siap pasang.

## Stock ride height dan extension cap dari FM4-re — v2

`--code-semantics` sekarang memakai `spring.front.MaxRideHeight` dan `spring.rear.MaxRideHeight` FM3 sebagai `Data_Car.FrontStockRideHeight` dan `RearStockRideHeight` FM4. Instruksi setup FM3 di `0x827294D8..0x82729578` memakai batas maksimum ini sebagai referensi; jalur FM4 di `0x8281EC20..0x8281ECC8` memakai kolom `Data_Car`. Kolom `Data_CarBody.Model*StockRideHeight` tetap terpisah. Tinggi efektif/default yang dipilih slider tetap mengikuti Min/Def/Max sumber.

Kompensasi `CMHeight` memakai tinggi referensi baru tersebut agar input komponen massa utama tetap terjaga. Pada tujuh mobil adjustable dalam panel lama, kedua tinggi referensi dan raw `CMHeight` naik 0,05 dibanding adapter v1. Pada 24 mobil lain termasuk Toyota, nilai kandidat v1 tetap sama.

`MaxStretchDeltaFromRideHeight` adalah cap tambahan FM4 atas bound yang dihitung helper extension FM3. Nilai cohort 0,5 tetap dipakai **hanya setelah audit per axle** menyatakan cap tidak aktif untuk seluruh interval spring part stock terpilih. Identitas setup yang diverifikasi adalah `sag = 4.903325080871582 * axle_fraction / normalized_spring_rate`; faktor massa yang sama pada berat dan spring saling menghilangkan. Helper memakai `sag` jika <= 0,07, selain itu `max(0,07, 0,75*sag)`, dengan konstanta float32 asli. Cap yang terlalu kecil, nilai nonfinite, spring range nonpositif, perubahan input yang dibutuhkan, atau provenance hilang ditolak sebelum mutasi. Converter tidak otomatis memperbesar cap.

Audit mencakup offset posisi relatif terhadap radius ban dan scalar spring-rest/extension setup. Kalibrasi camber/toe yang sudah ada tetap dicatat terpisah; kecocokan offset ini tidak membuktikan keseluruhan kinematika suspensi, model ban, massa terakit, atau handling sama. Part upgrade/swap dan title update belum dicakup.

Hasil canonical berada di `outputs/fm-car-converter/ride-height-v2/final/`; penjelasan di `outputs/fm-car-converter/ride-height-v2/REPORT.md`. Benchmark tetap panel lama 30 mobil + Toyota, bukan test set independen:

- 31/31 SQLite lolos validasi struktur.
- Offset referensi suspensi sesuai FM3: 24/31 → 31/31; input pusat komponen massa utama tetap 31/31.
- 558/558 koefisien suspensi ternormalisasi tetap sama.
- Semua 62 axle lolos audit cap terhadap rentang spring; slack minimum sekitar 0,391514.
- 5.000 perbandingan aritmetika terhadap byte instruksi asli, 558 pemeriksaan suspensi per mobil, dan 31 pemeriksaan kompensasi CG lulus.
- Selisih kolom fisika terhadap mobil FM4 native pada panel 30 menjadi 992 → 1.006: 14 kolom tinggi referensi kini sengaja mengikuti referensi FM3. Ini tidak mengukur kesamaan handling atau akurasi tuning native.

Tanpa `--code-semantics`, kebijakan legacy masih tersedia untuk reproduksi eksperimen lama. Gunakan opsi tersebut untuk konversi dengan validasi baru:

```powershell
python -m fm4_converter.fm3.converter --out outputs/fm-car-converter/toyota-suspension-new --calibration-rules outputs/fm-car-converter/benchmark30-refinements-v1/rules.json --calibration-mode conservative --code-semantics
python -m fm4_converter.fm3.ride_height_audit --out outputs/fm-car-converter/ride-height-new
python -m unittest discover -s tests -p "test_*.py" -v
```

Audit memakai image lokal yang diikat hash, katalog assembly `I:/FM4-re/out/db/asm.json`, dan disassembler offline dari riset sebelumnya. Ia mencocokkan 2.973 instruksi dari empat fungsi FM4 dengan byte image asli; pseudocode Ghidra yang telah diberi `nop` VMX128 bukan sumber perhitungan numerik. NumPy diperlukan untuk menjalankan 12 tes model kalibrasi lama; converter dan evaluasi baru menggunakan standard library.

## Kandidat impor mobil tambahan — pemeriksaan offline

`offline_package.py` menyiapkan kandidat stock di direktori baru tanpa memasang
ke game, mengubah profil, menjalankan game, atau memakai GPU. Per 20 Oktober
2026, pengujian game/GPU lanjutan memerlukan izin pengguna. Paket tetap mempunyai
`accepted: false` dan `runtime_tested: false` sampai tampilan dan pemakaian di
game benar-benar diuji. Lolos tes Python bukan bukti bahwa mobil sudah dapat
dimainkan.

Chevrolet Cobalt SS 2005 (`CHE_Cobalt_05`, ordinal 305), yang tidak ada pada
database FM4 target, digunakan sebagai kandidat pertama. Jalur impor sekarang:

- Mengizinkan mobil tanpa pembanding native FM4. Comparator menandai referensi
  tidak tersedia, tanpa menampilkan nol error palsu.
- Mengalokasikan ID komponen dalam rentang kecil, mempertahankan ordinal mobil
  yang bebas, menambahkan metadata menu/warna/posisi, dan memakai nama literal
  karena ID string FM3 tidak tersedia di FM4.
- Memakai adapter `--code-semantics` untuk stock ride height, kompensasi pusat
  komponen massa utama, dan pemeriksaan `MaxStretchDeltaFromRideHeight`.
- Mengonversi carbin melalui [adapter CPU beratribusi](../tools/carbin_cpu/README.md).
  Bodi, kokpit, LOD, rem dan roda memakai geometri sumber FM3. Tidak ada model
  donor yang diam-diam menggantikan mobil.
- Memeriksa struktur, setiap posisi vertex, normal, UV, topologi, draw list,
  kanal vertex tambahan, partikel kaca dan kata deformasi. Model FM3 mentah,
  format yang tidak didukung, buffer rusak dan drift di luar batas ditolak.
- Menyesuaikan nama berkas caliper/rotor menjadi `*_lod0.carbin`, menyesuaikan
  fetch tekstur warna dengan format FM4 sambil mempertahankan piksel, dan
  membuat ZIP beserta direktori dan mount `zipmanifest.xml` yang benar.
- Memetakan titik kamera eksplisit `CarPartPositions.PartId 4` FM3 ke `PartId 9`
  FM4. Selektor dibuktikan dari byte executable asli di `0x8246230C` dan
  `0x8267CEBC`; kedua game menambahkan offset kokpit yang sama. Ini menjaga
  basepoint kamera sumber, bukan mengestimasi titik dari mobil donor. Kamera
  yang memakai default INI belum ditransformasikan otomatis.
- Memeriksa benturan ID terhadap ZIP DLC yang diberikan, lalu membaca ulang
  graph stock dari database gabungan.

Hasil Cobalt offline v4: 12 model, 111 section, 1.250 mesh, 300.825 vertex dan
1.377.612 pemeriksaan UV; 222.034 kata deformasi dipertahankan. Error posisi
maksimum 0,0824 mm dan normal 0,00339 derajat. UV tetap dibatasi kuantisasi
per mesh, bukan dianggap bit-identik. Parser juga membaca 22 model FM4 asli
sebagai kontrol format. Sembilan header tekstur warna cocok dengan kontrol
native FM4, dan seluruh piksel sumber dipertahankan.

70 baris fisika/presentasi dimasukkan ke salinan database, tanpa benturan pada
delapan database DLC yang diperiksa. Seluruh **143 tes CPU lulus tanpa skip**.
Uji awal sebelum konversi aset lengkap memperlihatkan model pengganti atau
showroom kosong; itu bukan bukti keberhasilan paket v4. Paket v4 belum pernah
dijalankan di game. Detail dan hash lokal berada di
`outputs/fm-car-converter/import-v1/cobalt-offline-v4/`.

Lanjutan 21 Oktober 2026, kandidat `appearance-v1/cobalt-offline-v5` menambahkan
audit material, tekstur dan driver/kokpit **tanpa menjalankan game atau GPU**:

- `appearance_audit.py` mengikuti pemetaan part/material dan LOD per mesh dari
  loader FM4. 1.250 mesh cocok dengan 67 teknik pada kedua effect race/UI.
  Alias rem, prefiks `cockpit_`, akhiran roda `_V2`, serta front window diperiksa
  sebelum paket ditulis. Parameter `CockpitBumpScale` sumber tetap valid.
- `effect_audit.py` membaca metadata teknik/pass dan tabel konstanta shader.
  Pemeriksaan dependensi mengikuti sampler yang dikonfigurasi, bukan semua
  sampler yang dideklarasikan oleh pixel shader bersama. Misalnya `emblem`
  tidak otomatis memerlukan `badge2.xds`.
- `texture_audit.py` memeriksa batas blok seluruh 192 mip pada 20 XDS.
  Piksel sumber tetap utuh; codec DXT1/DXT5 tidak ditukar. Header warna
  dibandingkan dengan kontrol native yang memakai codec sama. Atlas kokpit,
  lampu, bodi dan roda juga didekode dengan Pillow pada CPU untuk inspeksi.
- Pemeriksaan geometri kini mencakup 285.935 sumbu tangent yang tersimpan
  pada vertex FM3 40 byte; error maksimum 0,00339 derajat. Tes korupsi
  membalik tangent tanpa mengubah normal untuk memastikan kesalahan normal
  map seperti ini ditolak. Frame vertex 16/44 byte masih direkonstruksi dari
  UV dan perlu dinilai saat rendering diizinkan.
- Header rig, empat frame gauge lama, serta 11 frame tambahan netral diperiksa
  pada semua 12 model. Atribut driver versi 6 dalam CarAttributes versi 15
  dipertahankan, termasuk offset tangan eksplisit. Tidak ada pemindahan
  kursi/tangan menggunakan mobil donor.
- 30 dependensi tekstur dan 68 aset driver FM4 native diperiksa. Empat GR2
  memerlukan decoder XMem CPU cadangan karena reader libmspack riset tidak
  mendukung stream tersebut. `archive_cpu.py` memeriksa hash decoder sebelum
  memakainya dan tetap mewajibkan ukuran serta CRC hasil yang tepat. Decoder
  lokal default berasal dari cache referensi ForzaTechStudio; lokasi alternatif
  dapat diberikan lewat `FM_XCOMPRESS_DLL` dengan hash yang sama. DLL tidak
  dibundel dalam source maupun paket mobil.

Pemetaan loader/driver didukung pencocokan 2.439 instruksi dari enam fungsi
FM4-re dengan disassembly byte image asli; tidak ada guest code yang dieksekusi.
Paket v5 mempertahankan seluruh 44 payload v4, karena tidak ditemukan alasan
berbasis bukti untuk mengubah material, piksel atau rig tersebut. Perubahan
utama adalah pemeriksaan sebelum pengemasan dan cakupan decoder arsip.
Database berisi graph yang sama; perbedaan byte hanya versi SQLite penulis.
Seluruh **159 tes CPU lulus tanpa skip**. Laporan lokal:
`outputs/fm-car-converter/appearance-v1/REPORT.md`.

`offline_appearance_structure_passed` hanya mencakup struktur, referensi dan
pelestarian data. Pencahayaan shader, binding sampler dinamis, pose tangan
selama animasi dan hasil di layar belum dibuktikan. Paket tetap belum dipasang,
belum diuji runtime dan belum diterima. Catatan izin ini diperbarui di bawah.

Lanjutan 21 Oktober 2026, kandidat `binding-animation-v1/cobalt-offline-v6`
memperluas pemeriksaan offline berdasarkan FM4-re:

- `sampler_audit.py` memeriksa register sampler per pass, per technique, dan
  per pustaka race/UI. Nomor slot tidak diasumsikan sama antar-material:
  `envSampler` pada `body` memakai s5, sedangkan `outer_rim` memakai s1.
  Binding `baseSampler` membedakan atlas mobil dan roda serta LOD0/LOD rendah.
  Empat `blurRimSampler` mengarah ke `wheel0..3.xds`, bukan varian `_lod0`.
  Empat sampler blur ban mengarah ke `Shared/tire{a,b,c}{0..3}.xds` sesuai
  kategori ban. Ketiga cabang diperiksa, sehingga ada 42 dependensi tekstur.
- `granny_audit.py` membaca metadata GR2 little-endian v7 dengan pointer 32/64-bit,
  memverifikasi CRC internal, batas section/fixup, dan tipe. Dekompresi section
  memakai DLL lokal dengan SHA-256 terpin, tanpa menjalankan game atau renderer.
  Default DLL berada di cache referensi ForzaTechStudio yang sama dengan
  penelitian sebelumnya; `FM_GRANNY_DLL` dapat menunjuk salinan ber-hash sama.
  DLL dan aset game tidak dibundel ke source converter.
- `driver_audit.py` memeriksa hierarki dua model tangan, pemilihan klip berdasarkan
  `Use10_2Animations`/`HasPaddleShifter`, track tulang, serta data kurva
  (dimensi, nilai finite, knot, durasi). Cobalt memakai keluarga kemudi biasa dan
  stick shift. Kedua cabang sisi shifter diperiksa; ini bukan klaim bahwa
  kedua klip shift dimainkan bersamaan.
- Paket ditolak bila dependensi yang diperiksa hilang, register bertabrakan,
  rig memiliki siklus, track tulang penting hilang, atau kurva rusak. Tidak ada
  perubahan pose/tekstur Cobalt yang dibenarkan oleh pemeriksaan baru ini;
  payload game tetap sama dengan v5.

`offline_sampler_metadata_passed` dan `offline_driver_animation_data_passed`
adalah pemeriksaan statis. Nilai sampler global saat draw, eksekusi shader, IK,
blend animasi, kontak tangan dengan setir, dan animasi tubuh `driver.anim.bin`
belum dibuktikan melalui playback. `s_varianceShadowMap` baru ditelusuri sampai
handle, sedangkan sumber binding runtime `trackLightmapSampler` belum ditutup.
Keduanya dilaporkan sebagai batas pemeriksaan, tidak ditandai lulus runtime.

Pengguna sudah mengizinkan GPU untuk pekerjaan offline pada 21 Oktober 2026.
Tahap ini tetap memakai CPU; game tidak dijalankan. Izin tersebut tidak mengubah
`accepted=false`, `installed=false`, atau `runtime_tested=false`.

```powershell
python -m fm4_converter.fm3.offline_package --media-name CHE_Cobalt_05 --display-name "Cobalt SS (FM3)" --model-helper <helper-directory>/carbin-cpu.exe --rules outputs/fm-car-converter/benchmark30-refinements-v1/rules.json --out <new-package-directory>
# Tambahkan --overlay-zip <DLC.zip> berulang kali untuk setiap overlay yang akan dipasang.
python -m unittest discover -s tests -p "test_*.py" -v
```

Folder `files/` adalah overlay berkas yang telah disiapkan, **bukan disc lengkap
atau DLC Xbox bertanda tangan**. `reports/stock.slt` mencakup baris stock dan
metadata presentasi; `manifest.json` memuat hash serta status belum diterima.
Tidak ada perintah peluncuran otomatis. Sebelum dinyatakan siap, kandidat
memerlukan pemeriksaan material/shading, driver, kokpit, menu, suara, pemuatan
lintasan dan berkendara di game setelah pengguna memberi izin. Upgrade,
swaps, semua mobil FM3, title update dan instalasi Xbox belum dicakup.

Lanjutan 21 Oktober 2026: v6 sempat diuji di game atas izin pengguna. Cobalt
muncul di showroom/lintasan, dapat bergerak dan dibelokkan; kokpit serta tangan
driver tampil. Uji singkat tersebut menemukan nama kosong pada daftar peserta,
thumbnail berlatar putih, dan ketidaksesuaian kelas/PI yang masih perlu ditinjau.
Game kemudian ditutup atas permintaan pengguna. Laporan sesi tetap tersimpan
di `outputs/fm-car-converter/runtime-v6/REPORT.md`; hasil itu khusus v6.

Kandidat **`ui-v1/cobalt-offline-v7`** memperbaiki dua masalah UI secara offline:

- `ui_names.py` mengembalikan `DisplayName` dan `ModelShort` ke referensi `_&`
  milik Cobalt 2005, lalu menambahkan kedua entri bernilai `Cobalt SS (FM3)` ke
  `Data_Car.str` dalam 18 arsip bahasa FM4. Label yang sama dipakai di semua
  bahasa sebagai identitas impor. Seluruh 1.006 nama lama per bahasa, ordinal
  lama, metadata opsional, dan 3.279 member arsip lain tetap utuh. Benturan
  identitas ditolak. Jalur pembaca nama peserta membaca angka setelah dua
  karakter awal, sehingga teks literal v6 menghasilkan kunci nol. Bukti
  FM4-re dicocokkan dengan 719 instruksi dari byte image asli.
- `ui_thumbnail.py` membuat atlas XDS 768x288 dengan slot besar 608x288 dan
  slot kecil 288x160 yang disimpan terputar 90 derajat. Latar putih dihilangkan
  secara terbatas, proporsi gambar dipertahankan, dan warna memakai alpha
  premultiplied sesuai kontrol native. Kedua slot memakai gambar Cobalt FM3
  asli dari sudut yang sama; belum ada render samping terpisah. Penghilangan
  matte ini telah ditinjau untuk Cobalt, bukan jaminan universal semua mobil.
- Manifest ZIP memperbarui lokasi direktori 18 arsip bahasa tanpa mengubah
  prioritas mount bawaan. Paket kini berisi 23 berkas. Arsip mobil/roda identik
  dengan v6; perbandingan seluruh 198 tabel memastikan hanya dua kolom nama
  pada `Data_Car` 305 yang berubah. Fisika dan kelas/PI tidak diubah.

Seluruh **180 tes CPU lulus tanpa skip**. Pratinjau thumbnail hasil paket telah
diperiksa di CPU. Laporan dan verifikasi lokal ada di
`outputs/fm-car-converter/ui-v1/REPORT.md` dan `final-verification.json`.
Paket v7 belum dipasang dan belum dijalankan; `runtime_tested=false` serta
`accepted=false`. Tampilan nama peserta dan kedua slot thumbnail di UI nyata
masih memerlukan uji game setelah izin berikutnya. Pada tahap v7 ini tidak
ada peluncuran game atau pemakaian GPU oleh converter.

## Hasil prototype fisika

- `candidate_stock.slt`: tabel FM4 dengan baris stock hasil konversi dan ID eksperimen yang tidak berbenturan dengan database dasar target.
- `MAPPING.md`, `mapping.json`: peran/tabel, mapping per kolom, aturan transformasi, kolom yang tidak dapat dipertahankan, serta referensi metadata yang belum diaudit.
- `REPORT.md`, `comparison.json`: selisih terhadap Toyota FM4 asli. ID baru, padding kurva, dan pembulatan numerik dipisahkan dari perubahan kalibrasi.
- `source_ir.json`, `candidate_ir.json`, `reference_fm4_ir.json`: data berdasarkan peran komponen, termasuk kurva zero-throttle asli yang tidak bisa diwakili langsung dalam schema FM4.
- `external_dependencies.json`: registry dan 19 baris keluarga ban FM4 yang dipakai. Tabel ban global tidak ditulis ke patch.
- `assumptions.json`, `id_map.json`, `validation.json`, `manifest.json`: aturan sementara, ID, pemeriksaan dan hash.

## Pemisahan converter dan pembanding

Converter tidak membaca kalibrasi mobil FM4 yang menjadi jawaban pembanding. Input target yang diizinkan adalah schema, ID yang sudah terpakai, registry umum, dan nilai default dari pemilik lain. Untuk Toyota, cohort default mengecualikan ordinal 247 dan drivetrain 1. Comparator baru mengekstrak Toyota FM4 sesudah kandidat dibuat.

Pengujian memodifikasi nilai kalibrasi Toyota FM4 dalam salinan database in-memory dan memastikan hasil converter tidak berubah. Pengujian authorizer juga membatasi pembacaan `Data_Car` target hanya pada ID untuk pemeriksaan bentrok.

Mapping yang bersifat hipotesis tetap diberi label: pemisahan grip chassis ke lat/long, pemindahan zero-throttle scale, pemilihan compound dengan nama sama, serta default travel/CVT. Penyalinan kolom dengan nama sama adalah kompatibilitas struktur, bukan bukti kesamaan satuan atau makna runtime.

## Batas prototype fisika dan paket impor

Output `converter.py` sendiri adalah patch studi fisika. ID tinggi pada jalur ini hanya namespace SQLite eksperimen, belum diverifikasi aman untuk loader; metadata instalasi sumber dipertahankan untuk studi. Jalur `offline_package.py` yang dijelaskan di atas memakai ID komponen kecil, metadata menu dan pemeriksaan DLC eksplisit untuk kandidat impor. Kedua output belum merupakan DLC siap pasang atau bukti bahwa mobil sudah dapat dimainkan.

Prototype fisika mencakup body, mesin, drivetrain, pilihan part stock, wheel, torque, spring/damper, anti-roll, aero, dan optional tire modifier. Paket impor menambahkan konversi model, tekstur, metadata presentasi dan ZIP untuk kandidat Cobalt; pembuktian geometri tidak menggantikan uji renderer, collision atau handling. Upgrade non-stock, swaps, pilihan tune pemain dan title update tetap di luar cakupan. Beberapa metadata referensi/enum/sentinel dipertahankan tanpa validasi dan dicatat dalam mapping.

PI dan kolom `Sim*` yang masih berasal dari FM3 adalah metadata lama. Angkanya bukan hasil benchmark converter. Perbedaan dengan FM4 dilaporkan sebagai kalibrasi atau metadata, tanpa persentase kemiripan handling.

## Pengujian

Tes memerlukan kedua database lokal; jika tidak tersedia, suite menyatakan skip. Tes mencakup read-only sumber, pemilihan stock non-level-zero, roundtrip SQLite/schema/dependency, ID collision, kurva ban FM4, kurva torsi dan data yang tidak terwakili, isolasi data pembanding, serta penolakan schema baru, referensi hilang, stock ambigu, kurva rusak, overwrite output, dan output di direktori game.

Source converter berada di `src/fm4_converter/fm3`, tes di `tests/fm3`, dan
helper native di `tools/carbin_cpu`. Hanya source dan dokumentasi yang
diizinkan masuk Git. Database hasil, nilai per kolom, dan hasil ekstraksi tetap menjadi artefak lokal.
