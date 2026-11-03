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

## Uji e2e Motorsport DX, kelas/PI dan nama di bawah DLC — v9

Lanjutan 1 November 2026. Kandidat diuji di Motorsport DX (FM4-PC) melalui
harness e2e: BuildRoot `I:\FM4-build-usa`, `--native`, profil salinan dengan
Disc 2 dan delapan paket DLC terimpor, data game dari salinan disc uji Japan/Asia.
Langkah OCR memilih Free Play → Quick Race → Chevrolet → mobil "2005 Chevrolet",
balapan dikendarai AI (`engageaionstart`), lalu menu pause dibuka.

`test_disc.py` membuat salinan disc uji: semua berkas asli di-hardlink dan setiap
berkas overlay mengganti link-nya dengan salinan baru, sehingga disc asli tidak
pernah ditulis (hash berkas yang diganti diperiksa sebelum dan sesudah).

```powershell
python -m fm4_converter.fm3.test_disc --disc "<FM4 Disc 1>" --package <package-directory> --out <new-test-dir>\disc
```

Uji v7 menemukan dua masalah yang tidak terlihat secara offline:

- **Kelas/PI.** FM4 menampilkan angka PI dengan menginterpolasi
  `Data_Car.PerformanceIndex` mentah pada batas `CarClasses.MaxPerformanceIndex`,
  tetapi huruf kelas diambil dari `ClassID`. Seluruh 503 mobil FM4 dan 415 mobil FM3
  konsisten dengan batas game masing-masing, namun batasnya berbeda. PI mentah FM3
  Cobalt (0,164646) tampil sebagai **D 209**, padahal PI 209 di FM4 adalah kelas E.
  `performance_index.py` memetakan skala mentah FM3 → FM4 dari pasangan
  `calibration.collect` (split engine yang sama). Kandidat identity/linear/hinge
  (knot di batas kelas FM3) dipilih dengan CV 5-fold per engine pada training;
  kandidat paling sederhana dalam 1,05× MAE CV terbaik dipilih sebelum validation.
  Terpilih linear `FM4 = 0,16879 + 0,77211 × FM3` (domain training 0–0,99445).
  Validation: kelas benar **62/73** (identity 11/73), MAE 0,0179 (identity 0,1005);
  gerbang ≥75% lolos. `ClassID` selalu diturunkan dari batas FM4 untuk PI yang
  ditulis; di luar domain atau model tidak diterima, PI mentah dipertahankan.
  Cobalt menjadi **C 366**, sama kelas dengan Golf GTI 2006/2010 dan Ion 2006 yang
  di FM3 berada di sekitar PI yang sama.
- **Nama mobil kosong di Car Select dan daftar peserta.** Disc 2 dan setiap DLC
  membawa `StringTables_pri_N.zip` berisi `<lang>/Data_Car.str` kumulatif
  (prioritas 151–25039), sedangkan arsip bahasa disc dipasang pada prioritas 80.
  Resolver mount melayani setiap path dari ZIP berprioritas tertinggi, sehingga entri
  v7 di arsip disc tidak pernah dibaca. Eksperimen di game mengonfirmasi bahwa ZIP
  `game:\media\stringtables.zip` memasang anggota `<lang>/` di
  `media\stringtables\` dan, di atas tabel pemenang, hanya menggantikan
  `Data_Car.str`. `ui_names.py` kini mengambil tabel pemenang per bahasa dari disc
  dan `--content-root` (paket terpasang), menambah dua entri, dan memasang
  `stringtables.zip` pada prioritas pemenang + 1. Arsip bahasa disc tidak lagi
  diubah. Nama seluruh 18 Chevrolet lain, termasuk mobil DLC, identik dengan run
  tanpa override.

```powershell
python -m fm4_converter.fm3.performance_index --out outputs/fm-car-converter/pi-class-new/pi-model.json
python -m fm4_converter.fm3.offline_package --media-name CHE_Cobalt_05 --display-name "Cobalt SS (FM3)" --model-helper <helper-directory>/carbin-cpu.exe --rules outputs/fm-car-converter/benchmark30-refinements-v1/rules.json --pi-model outputs/fm-car-converter/pi-class-new/pi-model.json --content-root "<user-data>\0000000000000000\4D530910\00000002" --out <new-package-directory>
```

Override nama terikat pada set konten yang diberikan: paket yang dipasang kemudian
dengan prioritas lebih tinggi kembali menyembunyikan nama ini (tanpa merusak nama
lain), dan paket harus dibangun ulang. `--content-root` juga menambahkan patch
database semua paket terpasang ke pemeriksaan benturan ID.

Hasil run e2e (captures dan log tetap di `I:\FM4-build-usa\e2e\`, tidak masuk Git):

| Run | Kandidat | Car Select | Daftar peserta |
|---|---|---|---|
| `cobalt-v7-1` | v7 | "2005 Chevrolet", nama kosong, D 209 | memilih Cobalt 2010 bawaan karena OCR "Cobalt" (langkah uji diperbaiki) |
| `cobalt-v8-1` | v7 + PI | nama kosong, **C 366** | nama kosong, C 366; lawan kelas C 352–382 |
| `cobalt-v8x-1` | v8 + override eksperimen | **Cobalt SS (FM3)**, C 366 | **Cobalt SS (FM3)** |
| `cobalt-v9-1` | v9 dari converter | **Cobalt SS (FM3)**, C 366 | **Cobalt SS (FM3)**, C 366; lawan C/D 332–383, posisi 3/12 di lap 1 |

Paket v9 berisi enam berkas (sebelumnya 23): mobil, roda, thumbnail, database,
`stringtables.zip` (prioritas 25040) dan `zipmanifest.xml`. Dibanding v7, database
hanya berbeda pada `PerformanceIndex` dan `ClassID` baris `Data_Car` 305.
Semua run mencapai balapan tanpa crash. Kunci error runtime sama pada setiap run
(`update:\media.zip` tidak ditemukan, satu pesan XAM, dua `BaseHeap::Release`) dan
tidak spesifik pada mobil impor. Slot thumbnail besar tampil benar di atas latar
garasi game; slot kecil masih memakai sudut 3/4 depan, bukan profil samping seperti
mobil native. Laporan dan frame penting: `outputs/fm-car-converter/pi-class-v1/`.
Paket tetap `accepted=false`: handling, suara, kamera selain kokpit, dan
upgrade belum dinilai. PI yang dipetakan adalah estimasi skala, bukan PI hasil
perhitungan fisika FM4.

## Skala dan konvensi nilai FM3 → FM4 — v10

Lanjutan 1 November 2026. `value_scales.py` menjalankan jalur paket saat ini
(aturan refined conservative + `code_semantics`) pada seluruh 309 pasangan mobil
yang sama di kedua game dan membandingkan setiap kolom hasil konversi dengan mobil
native FM4: 612 kolom, 182 memiliki selisih, 29 di antaranya sistematis (≥20% mobil
training berbeda). Untuk setiap kolom sistematis, kandidat `constant` (nilai tunggal
di ≥99% baris FM4), `lookup` (enum, hanya pemetaan yang konsisten ≥95% dengan
dukungan ≥3 mobil), `linear` dan `loglinear` (monoton, hanya di domain training)
dipilih dengan CV 5-fold per engine pada training, lalu dibekukan sebelum
validation. Gerbang: kategori ≥95% tepat dan lebih baik dari identity; kontinu
MAE validation ≤ 0,5 × MAE identity. Hasil float dibulatkan ke grid desimal
terkasar (0,01/0,005/0,0025/0,001) yang memuat ≥99% baris FM4 kolom tersebut, atau ke
6 desimal bila tidak ada; integer mengikuti kelipatan nilai FM4 training.

Kolom milik adapter lain tidak dipelajari: identitas, metadata integrasi,
`PerformanceIndex`/`ClassID` (`performance_index.py`), tinggi stock dan `CMHeight`
(`code_semantics`), kurva torsi, serta rate pegas/damper/antiroll. Rate tersebut
dinormalisasi identik oleh kedua game (558/558 koefisien yang ditelusuri), sehingga
selisih FM4 adalah setelan ulang per mobil, bukan satuan; adapter juga mengaudit
batas ekstensi terhadap rate itu.

| Kolom | Aturan | Validation (aturan / identity) | Status |
|---|---|---|---|
| Speed/Handling/Launch Rating | linear | MAE 0,116 / 0,549; 0,116 / 0,334; 0,186 / 1,256 | diterima |
| Acceleration/Braking Rating | loglinear | MAE 0,070 / 1,623; 0,136 / 0,274 | diterima |
| SimLatGees60/120MPH, SimTimeTo60MPH | linear | MAE 0,014 / 0,108; 0,021 / 0,104; 0,173 / 0,353 s | diterima |
| `MakeIcon` → `BOING`, `GaugeID` → −1 | constant | 73/73 (0/73, 41/73) | diterima |
| `List_Wheels.DisplayName` '' → `NULL` | lookup | 73/73 (0/73) | diterima |
| Grip chassis 4 kolom | linear | MAE 0,0026 / 0,0073 (depan); 0,0028 / 0,0063 (belakang) | diterima, **fisika: opt-in** |
| `GameFrictionScaleBraking` | linear, grid 0,0025 | MAE 0,0007 / 0,0088; 53/73 tepat (identity 54/73 tepat dengan galat lebih besar pada sisanya) | diterima, **fisika: opt-in** |
| Sim top speed, jarak rem, quarter mile, 0–100 | linear/loglinear | perbaikan < 50% | ditolak |
| `BaseCost`, `FamilyBodyID`, `GameDragScale`, `GameTorqueScale`, inertia transmisi | — | tidak lebih baik dari identity | ditolak |
| `GasTankSize`, `HasRaceLivery` | — | tidak ada kandidat sah | ditolak |

Aturan metadata dan konvensi diterapkan secara default melalui `--value-scales`.
Aturan fisika lolos gerbang tetapi mengubah handling, sehingga hanya berlaku dengan
`--physics-scales`. Kolom ditolak tetap memakai nilai FM3. Untuk mobil yang hanya
ada di FM3, nilai hasil aturan adalah estimasi skala FM4, bukan nilai yang pernah
dibuat Turn 10; kecocokan persis hanya dapat diperiksa pada pasangan.

```powershell
python -m fm4_converter.fm3.value_scales --rules outputs/fm-car-converter/benchmark30-refinements-v1/rules.json --out outputs/fm-car-converter/value-scales-new/rules.json
python -m fm4_converter.fm3.offline_package ... --pi-model <pi-model.json> --value-scales <rules.json> [--physics-scales] --content-root <...> --out <new-package-directory>
```

Cobalt v10 (default, tanpa fisika): Speed 5,22→5,06, Handling 4,92→4,61,
Acceleration 3,93→5,82, Launch 4,77→6,19, Braking 4,68→4,48, 0–60 6,85→7,12 s,
lateral G 60 mph 0,890→0,811. Nilai ini berada di antara rekan kelas C FM4
(Golf GTI 2006/2010, Ion 2006, Focus ST 2006, Civic Type R 2007). Hanya baris
`Data_Car` 305 dan velg yang berubah dibanding v9.

Run e2e `cobalt-v10-1` (pengaturan sama dengan v9): Car Select menampilkan
"Cobalt SS (FM3)", C 366 dan rating 5,1 / 4,6 / 5,8 / 6,2 / 4,5; logo Chevrolet
tetap tampil dengan `MakeIcon = BOING` karena FM4 mengambil logo dari
`List_CarMake`. Daftar peserta: Cobalt SS (FM3) C 366, posisi 3 di antara lawan
C/D 330–383. Tanpa crash; kunci error runtime sama dengan run sebelumnya.
Cobalt v11 (`--physics-scales`) mengubah grip chassis depan 0,9725→0,982288 dan
belakang 1,0→0,99422; rem tetap 1,0 karena hasil aturan pada grid FM4 sama dengan
nilai FM3. Database v11 hanya berbeda dari v10 pada empat kolom grip tersebut.
Uji pembanding dengan `FM4_FIXED_SEED=1` dan `FM4_FIXED_FRAME_TIME=1` (grid, lawan
dan AI driver sama) hingga balapan 2 lap selesai:

| Run | Durasi start → finis pemain | Posisi |
|---|---|---|
| `cobalt-v11-fin` | 280,7 s | 1st |
| `cobalt-v10-fin` | 280,5 s | 1st |
| `cobalt-v10-fin2` | 280,8 s | 1st |

Selisih v11 berada di dalam variasi dua run v10 (±0,3 s), jadi perubahan grip ±1%
tidak terukur dengan AI driver pada satu lintasan. Durasi diukur dari event layar
(waktu dinding), bukan dari timer balapan. Uji ini membuktikan v11 dimuat dan
dikendarai sampai finis tanpa crash atau error baru; tidak membuktikan handling
lebih mirip FM4. Kemenangan AI di ketiga run juga belum berarti mobil terlalu cepat
untuk kelasnya: pembandingnya mobil native yang dikendarai AI driver yang sama.

## Semua mobil FM3-only dalam satu paket — fm3-only-v1

Lanjutan 2 November 2026. Daftar mobil dihitung ulang, bukan diambil dari disc
saja: FM3 USA punya 415 mobil, 100 di antaranya tidak ada di database Disc 1 FM4,
tetapi 19 dari 100 itu (misalnya Porsche 911 GT2 '95, 959, Carrera GT) sudah
dibawa patch DLC FM4 yang terpasang. Tersisa **81 mobil FM3-only**. Aset 55 mobil ada
di `Media/Cars` Disc 1 FM3; 26 lainnya hanya ada di paket STFS Disc 2 FM3
(`4D53084D0CCF0013/14/15`, ZIP `<n>_pri_65.zip` berisi folder `media/cars/<nama>/`).

FM4 hanya membaca satu `gamedb.slt`, satu `Data_Car.str` per bahasa dan satu mount
atlas thumbnail, sehingga paket per mobil tidak bisa digabung dengan menyalin file.
`batch_package.py` merencanakan mobil satu per satu terhadap database paket yang terus
bertambah. Dengan begitu kunci baru tidak saling bertabrakan, sementara setiap kunci di
patch DLC yang terpasang tetap dicadangkan (`reserved`). Hasilnya satu overlay: satu
database, ZIP per mobil dan per velg, satu `Thumbnails.zip`, satu `stringtables.zip`
dan satu `zipmanifest.xml`.

```powershell
python -m fm4_converter.fm3.batch_package --model-helper <carbin-cpu-v4>\carbin-cpu.exe --rules <rules.json> --pi-model <pi-model.json> --value-scales <rules.json> --content-root <...\4D530910\00000002> --out <paket-baru>
```

Aturan tambahan yang dibutuhkan agar banyak mobil bisa lolos. Semuanya punya preseden
di FM4 sendiri atau sudah dibuktikan; selain itu tetap ditolak:

- **Velg**: velg yang sudah dibawa FM4 (disc atau DLC terpasang) dipakai ulang dan
  ikut diaudit, tetapi tidak dikirim lagi. Velg yang dipakai beberapa mobil impor
  hanya dikonversi sekali.
- **Registry DLC**: make Porsche (ID 39) hanya ada di Porsche Expansion
  (`34_pri_65.zip`). Converter memakai baris registry DLC hanya bila disc tidak
  punya padanannya, lalu mencatatnya di `requires` mobil tersebut.
- **Kunci nama**: patch DLC FM4 memakai ulang beberapa kunci `Data_Car.str` FM3
  (kunci DisplayName DBR9 FM3 = Lotus Eleven FM4, Corvette C6.R = Scion FR-S).
  `ui_names.rekey` memindahkan mobil semacam itu ke kunci bebas tertinggi di semua
  tabel bahasa, sehingga tidak ada nama FM4 yang ditimpa.
- **`carattribs.xml` versi lama**: FM4 membawa mobil native dengan CarAttributes
  4/10/11/12/13/14 dan mobil tanpa file itu (FOR_5_FGFalcon_11, MER_1_CClass_11).
  Audit menerima versi/tata letak gauge yang sama dengan preseden native. Bila
  `Use10_2Animations`/`HasPaddleShifter` tidak ada, dipakai klip standar dan
  asumsinya dicatat.
- **Material**: override `shadersettings.xml` yang tidak terikat ke konstanta efek
  (CockpitPaintScale ada di 22 mobil native), elemen kosong (GMC_Syclone_92), tidak
  adanya `shadersettings.xml` (63 mobil native), normal map cockpit tertentu yang
  tidak ada (`plastic2_NRM` pada AST_One77_10 dan tiga lainnya, `leather2_NRM` pada
  CHE_CobaltSS_10 dan tiga lainnya, `wood.xds` pada MER_SLSAMG_11), serta nama teknik tanpa efek yang persis
  dipakai mobil native (`Material__1` pada TVR_Sagaris_05,
  `cockpit_Tail_light_lod0` pada CHE_CamaroSS_10). Semua kasus ini dicatat di
  `appearance_validation.json`.
- **Geometri**: beberapa section FM3 punya vertex di luar bounds-nya sendiri (|q|
  sampai 4,1 pada lampu FER_30_333SP_98). Encoder FM4 meng-clamp vertex itu sampai
  0,45 m. Helper `carbin-cpu-v4` menambahkan patch tercatat (`build_carbin_cpu.PATCHES`,
  `tools/carbin_cpu/Motorsport3Bounds.cs`) yang hanya untuk section tersebut menghitung
  ulang bounds menurut konvensi FM4 (pusat AABB, simetris). Output untuk section
  lain identik byte demi byte dengan v3 (Cobalt 11/11 carbin).
- **Audit geometri** kini memodelkan perilaku konverter untuk half UV NaN (dibaca 0;
  satu UV2 pada FER_88_550Maranello_03) dan untuk sumbu tangent sumber nol atau
  sejajar normal (fallback +Z/+X).
- **Thumbnail**: render FM3 yang memotong mobil di tepi gambar (sayap MC12) diterima
  bila paling banyak 10% piksel border tertutup mobil.
- **`WeightDistDiff`**: oil cooler stock pada tiga mobil "IE" bernilai sekitar 2e-4.
  Delta stock dengan jumlah ≤ 1e-3 diterima, beserta batas efeknya pada tinggi
  berbobot (`weighted_height_uncertainty_m`). Delta yang lebih besar tetap ditolak.
- **PaintScale cockpit** (lihat bagian "Interior cockpit putih" di bawah): converter
  menambahkan konstanta paint-scale FM4 untuk setiap teknik cockpit yang dipakai
  model ke `shadersettings.xml`. Nilai dan isi sumber lain tidak diubah; audit
  menerima perubahan pada file itu hanya bila hasilnya sama persis dengan aturan.
- **Blok spion tengah**: header model cockpit FM4 (word 0x104..0x153) diisi dari mesh
  `mirrorMiddle` (`carbin_audit.mirror_block`, cocok untuk 261/261 cockpit native).

Hasil `outputs/fm-car-converter/fm3-only-v1/package` dengan aturan refined
conservative, model PI, `--value-scales` tanpa fisika, dan content root uji:
**73 dari 81 mobil terkemas** dalam satu overlay (110 file, 1,93 GiB). Asal velg: 33
dikonversi, 27 velg disc FM4, 5 velg DLC terpasang, dan 8 velg dipakai bersama di paket.
Sebanyak 24 mobil berasal dari Disc 2 FM3, dan 11 mendapat kunci nama baru. Ada 12 mobil
yang butuh Porsche Expansion dan/atau pack `0003`; daftarnya di `requires` manifest.
Sebaran kelas: R3 24, R2 21, S 8, R1 6, B 4, C 4, A 2, D 2, E 1, X 1.

Pembaruan 3 November 2026: kedelapan mobil di bawah kini terkemas (paket
`fm3-only-v2`, **81 dari 81**), dengan aturan berikut:

- **CAD_8_CTSV_08**: tag penutup yang tidak punya pembuka di `shadersettings.xml` sumber
  dibuang. Hanya tag itu, dan tercatat di laporan aset (`repaired_source_xml`).
- **Empat mobil IE**: stok berat mereka adalah weight reduction level 1, dan
  `CurbWeight` FM3 = `InitialMass` baris itu. Seperti semua mobil FM4,
  `CurbWeight × 100` diset sama dengan massa bodi stok. Input massa fisika tidak
  berubah, dan asumsinya tercatat (`stock_weight_reduction_sets_catalog_weight`).
- **F430 GT, Supra #35, GTO '68**: material tanpa teknik efek FM4 (`body2`, `LOD1`,
  `bump_plastic`, `bump_stitching`, `leather`, `bump_leather`) diterima seperti nama
  teknik tak dikenal yang dibawa mobil FM4 sendiri (TVR Sagaris, Camaro SS). Audit kini
  melaporkan semua teknik yang hilang sekaligus. Ketiganya wajib lolos uji game.

**Livery balap stok.** FM4 menggambar livery stok sebuah mobil hanya bila
`Data_Car.HasRaceLivery` = 1 (mobil balap FM4 seperti 333SP dan GT-R #12 2010). Converter
dulu selalu menulis 0, sehingga mobil balap FM3 tampil polos di garasi dan saat balapan;
hanya gambar Car Select, yang diambil dari FM3, menampilkan livery. Sejak paket
`fm3-only-v3` nilainya diambil dari `HasLivery` FM3: 64 mobil balap = 1, 17 mobil jalan = 0.
Livery FM3 sendiri ada di model `.carbin` dan tidak perlu berkas tambahan.

Aveo5 LT dan Aveo5 LT IE bernama sama di data FM3 (`DisplayName` "Aveo5 LT"); hanya
`ModelShort` yang berbeda ("Aveo5 +").

Alasan penolakan sebelumnya:

| Mobil | Alasan |
|---|---|
| PON_GTO_68 | material `bump_plastic` pada part `wheel` LOD3, teknik tidak ada |
| TOY_35_Supra_04 | material bernama `LOD1` pada `bumperFrameF` |
| FER_71_F430GT_08 | material `body2` pada bumper depan |
| CAD_8_CTSV_08 | `shadersettings.xml` sumber rusak (tag penutup berlebih) |
| HON_FitSportIE_09, NIS_VersaIE_09, TOY_YarisSIE_08, CHE_Aveo5IE_09 | massa bodi stock ≠ `CurbWeight` × 100 (part pengurang bobot stock); tidak ada mobil native FM4 dengan pola ini |

Uji e2e Motorsport DX (Quick Race, Disc 2 + 8 DLC, AI driver, tanpa crash, kunci
error runtime sama dengan baseline Cobalt):

| Run | Mobil | Yang diuji | Car Select | Hasil |
|---|---|---|---|---|
| fm3only72-dbr9 | #008 Bell Motorsports DBR9 (FM3) | kunci nama dipindah, paket 72 | R2 842 | balapan, cockpit + tangan driver |
| fm3only-dodge | SRT4 (FM3) | sumber Disc 2 FM3 | C 423 | balapan |
| fm3only-porsche | Boxster S (FM3) | make dari DLC, CarAttributes v10 | B 463 | balapan |
| fm3only-a4 | A4 Touring Car (FM3) | tanpa carattribs, bounds direfit | R2 830 | balapan; lawan AI "GT500 SC430 (FM3)" |

Target OCR pemilihan make memakai teks sejarah pabrikan. Logo di strip bisa
memuat nama pabrikan lain (logo "ASTON MARTIN" terbaca saat Alfa Romeo masih terpilih).
Empat run tidak membuktikan 69 mobil lainnya; handling, suara, upgrade dan tune belum
dinilai.

### Interior cockpit putih — penyebab dan perbaikan

Paket di atas menampilkan interior mobil jalanan putih polos (SRT4, juga Cobalt sejak
v9). Penyebabnya dicari dengan bisect di Motorsport DX memakai SRT4 ACR native FM4
(model dan tekstur interiornya hampir sama dengan SRT4 FM3) sebagai pembanding.
Frame tersimpan di `outputs/fm-car-converter/cockpit-paint-v1/runtime/`.

| Varian SRT4 (FM3) | Interior |
|---|---|
| paket asli | putih |
| + blok spion tengah di header cockpit | putih |
| carbin cockpit diganti carbin native SRT4 ACR | putih |
| shadersettings, carattribs, interior_lod0, leather2_nrm, versiondata dan buildnumber dari ACR | gelap normal |
| hanya `shadersettings.xml` dari ACR | gelap normal |
| kontrol: SRT4 ACR native | gelap normal |

Efek cockpit FM4 mengalikan tekstur interior dengan konstanta paint-scale
(`PaintScale`, `CockpitPaintScale`, `CockpitPlasticPaintScale`). Mobil tanpa setting
memakai default global `Shared.zip/ShaderSettings/Normal.xml`, misalnya 0,5 untuk
plastic/leather/cloth/solid, 0,35 untuk mottled, 0,3 untuk bump_plastic, dan 0,002
untuk metal. Bila teknik tidak ada di file itu, dipakai initializer effect 1,0
(dibaca dari `shaders_v16.fxobj`; cara bacanya dicek dengan `MinCockpitShadow` 0 dan
`ShadowDarkeningRamp` 4). Efek FM3 tidak punya konstanta ini.

Pada 117 mobil yang ada di kedua game, FM4 menampilkan material cockpit di sekitar 0,38×
default dikali albedo tekstur FM3-nya. Ada dua cara: tekstur digelapkan (mayoritas,
tanpa setting) atau tekstur dipertahankan dengan setting rendah (SRT4 ACR: plastic 0,108).
Tekstur FM3 pada nilai default menjadi sekitar 2,6× terlalu terang.

Percobaan pertama mengira default-nya 1,0, sehingga nilai yang dipakai dua kali terlalu
tinggi (plastic 0,325). Hasilnya interior SRT4 masih putih.

Rasio yang diukur adalah (albedo FM4 × setting atau default) / albedo FM3, berupa
luminans linear yang disampel pada UV vertex LOD0 tiap mesh
(`cockpit-paint-v1/ratio_all.py`). Mediannya: wood 0,096*, bump_plastic 0,113,
bump_plastic3 0,115*, mottled 0,137, solid 0,153, rubber 0,159, plastic 0,169,
bump_leather 0,183, bump_plastic2 0,187, stitching dan bump_leather3 0,191*, cloth
0,206, badge 0,208, bump_leather2 0,216, leather 0,220, reflector 0,398,
gauge_emissive 0,416, metal 0,002. Teknik bertanda * dipakai kurang dari 20 mobil,
sehingga nilainya = default × 0,382, median gabungan rasio/default non-metal (1.118
sampel). `appearance_audit.COCKPIT_PAINT_SCALES` menuliskan nilai ini untuk teknik yang
dipakai model cockpit. Setting yang sudah ada di sumber dibiarkan. `cockpit_body` (cat
bodi) dan `cockpit_shadowMap` tidak disentuh. Teknik tanpa data pembanding
(`cockpit_metal2`, `cockpit_smooth_metal`) dicatat dan dibiarkan pada default. Tekstur
tidak diubah.

Ke-73 mobil paket `fm3-only-v1/package-paint` mendapat setting ini, tanpa teknik yang tak
terukur. Paket ini menggantikan `fm3-only-v1/package`. Hasilnya tetap 73 dari 81 mobil
dengan delapan penolakan yang sama. Satu jebakan sempat ditemukan: DOD_57_ViperGTSR_00
menulis elemen `cockpit_carbon_fiber` dua kali, sehingga verifikasi kini membandingkan
semua entri sumber secara berurutan.

Uji e2e pada disc `fm3-only-paint` (Quick Race, AI driver, tanpa crash, kunci error sama
dengan baseline):

| Run | Mobil | Interior |
|---|---|---|
| paint-srt4 | SRT4 (FM3) | abu-abu dengan shading, sedikit lebih terang dari SRT4 ACR native (setting median 0,169 vs 0,108 milik ACR) |
| paint-cobalt | Cobalt SS (FM3) | abu-abu, dasbor dan panel pintu terbaca |
| paint-a4b | A4 Touring Car (FM3) | interior balap hitam, tidak berubah |

Penilaian ini visual pada satu lintasan dan satu waktu siang. Belum ada pengukuran
luminans per patch terhadap mobil native.

### Uji sampel 15 mobil

Sampel ini dipilih per jenis risiko, di luar lima mobil yang sudah diuji sebelumnya. Semua
run memakai disc `fm3-only-paint`, Quick Race dengan AI driver, dan balapan sekitar 25
detik. Frame tersimpan di `outputs/fm-car-converter/fm3-only-v1/runtime/sample15/`.

| Mobil | Risiko yang diwakili | Kelas | Interior/cockpit |
|---|---|---|---|
| Aveo5 LT (FM3) | kelas terendah (E) | E | normal |
| Solstice (FM3) | CarAttributes v10 | D | normal; panel dasbor terang (diduga sewarna bodi) |
| X5 xDrive48i (FM3) | SUV jalanan | D | normal |
| Tom's W123 MR-S (FM3) | Disc 2, CarAttributes v4 | C | normal |
| GranTurismo (FM3) | kunci nama dipindah | B | dasbor abu muda; bagian bawah dan kursi sangat terang, belum dipastikan |
| Cayman S (FM3) | make dari DLC Porsche | A | normal |
| #1 Peugeot 207 Super 2000 (FM3) | Disc 2, velg DLC, butuh pack 0003 | A | normal |
| 911 GT2 (997) (FM3) | kunci dipindah, Porsche | S | normal; lingkar setir abu muda |
| #24 At-Speed S60 R (FM3) | Disc 2, velg dikonversi | S | normal |
| #25 Britek FG Falcon (FM3) | kunci dipindah | R3 | normal |
| #57 Carsport Viper GTS-R (FM3) | Disc 2, attr v4, elemen shadersettings ganda | R3 | normal |
| #9 Vitaphone MC12 (FM3) | velg dibagi, tanpa spion tengah | R2 | normal |
| C-Class Touring Car (FM3) | tanpa carattribs | R2 | normal |
| #30 MOMO Doran F333 SP (FM3) | bounds lampu direfit | R1 | normal (kokpit terbuka) |
| #8 Peugeot Sport 908 (FM3) | kelas X | X | normal |

Semua 15 mobil lolos: bisa dipilih, nama dan kelas tampil, balapan berjalan, tanpa crash,
dan tiga kunci error runtime sama dengan baseline.

Beberapa run pertama memilih mobil yang salah, dan kesalahan ini diperbaiki sebelum hasil
dicatat:
- Teks OCR pemilihan make yang melintasi dua baris gagal terbaca ("Alfieri | Maserati").
  "William Durant" ternyata juga ada di sejarah Buick, dan "Bavarian" di sejarah Audi.
  Target kini dicek terhadap semua teks sejarah di `List_CarMake.str`.
- Tiga target mobil lebih dulu cocok dengan mobil **bawaan** FM4 bernama mirip: #9 SP Tools
  FG Falcon 2011, Peugeot 207 Super 2000, dan Mercedes-AMG C-Class Touring Car. Ketiganya
  diulang dengan target yang memuat "(FM3)" (Falcon diganti #25 Britek, karena sponsor #9
  juga ada di FM4). Setiap run kini dicek lewat teks kartu Car Select.

Lawan AI dari paket juga muncul di Quick Race. Saat pemain memakai C-Class bawaan, posisi
pertama dipegang AI dengan "#008 Aston DBR9 (FM3)". Sebelumnya juga ada "GT500 SC430
(FM3)" di run A4. OCR hanya membaca satu-dua baris teratas klasemen.

### Thumbnail dan gambar Car Select pucat

Gambar mobil besar di Car Select bukan render 3D, melainkan tampilan 608×288 dari atlas
thumbnail. Buktinya: frame Car Select Corvette Z06 2006 bawaan dan Z06 dengan aset hasil
konversi FM3 identik piksel demi piksel (disc `ext-native` vs `ext-z06`), sedangkan
cockpit-nya di balapan berbeda. Thumbnail FM3 adalah render terang di atas latar putih,
sementara FM4 merender lebih gelap, lebih kontras dan lebih pekat. Karena converter
mempertahankan piksel FM3, mobil konversi tampil pucat di antara mobil FM4.

`ui_thumbnail.fm4_tone` kini memetakan warna piksel mobil ke gaya FM4. Pemetaannya diukur
dari 315 mobil yang punya thumbnail di kedua game
(`outputs/fm-car-converter/exterior-paint-v1/thumb_lcurve.py`):
- Kurva luminans linear: median pemetaan kuantil 30–99,5% piksel mobil (bayangan tanah
  FM4 dikecualikan), difit pada separuh mobil. Pada separuh lainnya, error kuantil
  luminans turun dari 85,8 ke 9,9 level sRGB.
- Rona dipertahankan, lalu chroma dikali 2,119 (median rasio saturasi FM4/FM3). Error
  saturasi pada mobil uji turun dari 0,144 ke 0,092.

Kurva per kanal RGB ditolak karena menggeser rona (kuning menjadi oranye). Tone map ini
tidak bisa menambahkan pantulan kilap dan bayangan tanah render FM4, jadi hasilnya sedikit
lebih kusam daripada thumbnail asli FM4. Di game (disc `fm3-only-v2`, run `v2-aveo` dan
`v2-granturismo`, keduanya tanpa crash), Aveo5 dan GranTurismo kini tampil sekelas dengan
mobil FM4 di sebelahnya, baik di gambar besar maupun di strip (frame
`exterior-paint-v1/carselect_before_after.png`).

Mobil di strip (tampilan kecil 288×160) sebelumnya juga terlalu besar: lebarnya 85% dan
tingginya 59% dari kotak, sedangkan median FM4 hanya 60% × 33%. FM4 memakai foto samping
yang panjang dan rendah. `fit_view` kini mengikuti ukuran mobil di 503 atlas FM4 sendiri
(`exterior-paint-v1/view_layout.py`): luas kotak mobil disamakan dengan median FM4 (besar
0,557, kecil 0,202), lebar dan tinggi dibatasi pada persentil-90 (besar 0,931/0,792,
kecil 0,656/0,406), dan jarak bawah memakai median (0,014/0,087). Foto depan-samping FM3
yang lebih tinggi bisa terkena batas tinggi, sehingga hatchback seperti Aveo5 tampil
sedikit lebih kecil. Sudah dicek di game pada disc `fm3-only-v3` (run `v3-aveo` dan
`v3-granturismo`, frame `exterior-paint-v1/carselect_v3.png`).

Eksperimen yang sama juga menunjukkan interior Z06 versi konversi lebih terang daripada
Z06 bawaan (setir abu muda vs hitam). Nilai PaintScale median terlalu terang untuk mobil
ini, padahal median memang berarti separuh port Turn 10 lebih gelap. Ini belum dikoreksi.

Total mobil paket yang sudah diuji di game: 20 dari 73. Sisanya, serta handling, suara,
upgrade, tune dan mode karier, belum diuji.

Header cockpit native juga memuat blok 0x104..0x153 berisi kotak mesh `mirrorMiddle`
(pusat, baris rotasi identitas, setengah ukuran; batas atas dimulai dari 0) dan word
0x150 = 0. Cockpit tanpa spion tengah (44 mobil balap native) berisi 1. Helper
`carbin-cpu` menulis nol/1, dan converter kini mengisinya (49 dari 73 cockpit). Fungsi
blok ini di game belum diketahui: run SRT4 dengan dan tanpa blok terlihat sama.

Masih terbuka: normal map cockpit FM3 (`*_nrm.xds`) berformat DXT1, sedangkan semua
261 normal map cockpit di `Media/Cars` FM4 (termasuk `Shared.zip`) berformat DXN. Pengaruhnya pada bump interior belum
diukur.

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
