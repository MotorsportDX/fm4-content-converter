# Peta fisika dan handling Forza Motorsport 2 3 dan 4

Riset statis offline atas koleksi lokal, 20 Oktober 2026. Cakupan: FM2 Disc 1 dan Bonus Disc; FM3 Disc 1 dan Disc 2; FM3 Ultimate Collection kedua disc; FM4 kedua disc dan delapan DLC yang tersedia. Title update yang berada bersama sumber ikut diperiksa sebagai faktor versi. Tidak ada game, emulator, installer, koneksi internet, atau SQL patch game yang dijalankan. Berkas sumber di `D:\Data` tidak diubah.

**Temuan utama:** ketiga generasi menyimpan model kendaraan yang sangat bergantung pada data: database komponen/upgrade, tabel respons ban, konfigurasi handling global, geometri collision mobil, serta material dan collision lintasan. Sebagian besar input fisika sudah bisa dipetakan langsung dari file. Persamaan solver, integrator, combined slip, konversi unit tertentu, dan pemetaan triangle collision ke material belum sepenuhnya dipulihkan. Jadi hasil ini adalah peta data dan perbedaan yang terukur, bukan klaim reproduksi simulasi persis atau penilaian subjektif rasa berkendara.

## Membaca hasil

**Dalam repo:** laporan dan source alat analisis. Evidence JSON/CSV, schema hasil ekstraksi, XML/SQLite aset, disassembly dan binary decoder tetap lokal serta diabaikan Git. Nama berkas evidence di laporan merujuk hasil lokal yang dapat dibuat dari data milik pengguna; berkas tersebut tidak tersedia hanya dengan clone.

| Dokumen | Isi |
|---|---|
| [FM2 dan Bonus Disc](fm2/report.md) | Relasi komponen, contoh mobil lengkap, model ban, 47 geometri jalur AI yang didekode, 8 paket bonus dan TU4 |
| [FM3 dan Ultimate Collection](fm3/report.md) | Peta kedua edisi, perbandingan parameter/aset yang sama, kedua Disc 2, tambahan UC dan perubahan khusus |
| [FM4 Disc 1 dan Disc 2](fm4/report.md) | Relasi seluruh 501 mobil drivable ke disc asal, 198 tabel, steering/ban, surface dan track |
| [FM4 DLC dan title update](dlc/report.md) | 8 DLC, 112 mobil baru, 18 track records, patch data, serta 3 TU lokal |
| [Skrip perbandingan lintas versi](cross_version.py) | Membentuk `cross_version.json` lokal: schema/count, INI beserta nomor baris, tabel ban dan perubahan nilai, contoh Toyota 2000GT |
| [Metode dan reproduksi](METHODS.md) | Sumber, parser, validasi, cara menjalankan analisis ulang tanpa game, batas bukti |

**Terkonfirmasi** berarti byte, field, nilai, atau relasi dibaca dari sumber. **Inferensi** berarti penafsiran fungsi fisik berdasarkan nama, relasi, dan pola data. **Belum diketahui** berarti belum ditelusuri cukup jauh di kode/format biner. Nilai konfigurasi yang terkonfirmasi belum membuktikan bagaimana atau seberapa sering dipakai saat runtime.

## Ringkasan setiap game

Hitungan berikut berasal dari **database dasar Disc 1**, sebelum overlay bonus/DLC/TU. Baris database, mobil yang dapat dikendarai, layout aktif, dan sirkuit unik adalah kategori berbeda.

| Ukuran | FM2 | FM3 | FM3 Ultimate | FM4 |
|---|---:|---:|---:|---:|
| Tabel SQLite | 169 | 176 | 177 | 198 |
| Record `Data_Car` | 310 | 415 | 510 | 503 |
| Record `Tracks` | 50 | 109 | 145 | 127 |
| Record track `Active=1` | 47 | 102 | 138 | 114 |
| Compound ban | 7 | 8 | 8 | 9 |
| Friction multikurva | 16 | 16 | 16 | 18 |
| Friction curves | 32 | 32 | 32 | 36 |
| Affect curves ban | 96 | 96 | 96 | 108 |
| `CarPhysicsUpdateHz` dalam INI | 239 | 359 | 359 | 359 |

Sumber: masing-masing `Media/DB/gamedb.slt` dan `Media/physics/PhysicsSettings.ini`, dicatat dalam `cross_version.json` (hasil lokal). Semua friction curve pada tabel tersebut mempunyai 100 ordinat. `Active=1` adalah flag data, bukan hitungan yang telah diuji di menu. Nilai Hz di atas tidak dibulatkan menjadi klaim runtime 240/360 Hz.

| Media | Peran yang terbukti |
|---|---|
| FM2 Disc 1 | Database, solver executable, 310 ZIP mobil dengan MAXData, track collision dan AI |
| FM2 Bonus Disc | 8 paket: 39 ID mobil baru, 5 layout baru, unlock 4 mobil yang sudah ada; juga TU4. Union definisi 349 mobil, 55 record track, 52 active candidates |
| FM3 Disc 1 | Database 415 mobil dan parameter fisika; aset sebagian mobil/track berada di Disc 2 |
| FM3 Disc 2 | 4 content packages; SQL yang diperiksa mengubah status installed/purchased, disertai aset mobil/track |
| FM3 Ultimate Disc 1 | Database sudah mencakup 95 mobil dan 36 track records lebih banyak daripada regular |
| FM3 Ultimate Disc 2 | 8 packages; paket tambahan memuat 28+40+27 mobil dan 36 track records. Definisi ini sudah tercakup dalam DB UC Disc 1, sehingga tidak dijumlahkan dua kali |
| FM4 Disc 1 | Database 503 record: 501 drivable + 2 Autovista-only. Aset fisik 313 mobil berada di Disc 1 |
| FM4 Disc 2 | Aset fisik 188 mobil (63+69+56) dan paket Autovista; database parameternya sudah ada di Disc 1. Tidak ditemukan DB/track di empat ZIP konten tersebut |
| FM4 DLC lokal | 112 ID mobil baru, semuanya drivable, dan 18 track records baru. Union base+DLC = 615 record mobil/613 drivable; 145 record track/132 active candidates |

Disc 2 merupakan distribusi konten, bukan bukti adanya mesin fisika kedua. Executable pada installer disc tidak boleh disamakan dengan solver balapan. Keberadaan data tidak menjamin kontennya otomatis aktif; lisensi, flags, pilihan part, priority mount, dan versi update tetap perlu dipertimbangkan.

## Bagaimana data membentuk handling

Alur konseptual yang didukung struktur data adalah sebagai berikut. Panah terakhir menyatakan hubungan sistem, bukan urutan instruksi solver yang sudah direkonstruksi.

```text
Identitas build + base database + patch konten/versi
                    ↓
Mobil → pilihan body / engine / drivetrain / parts → tuning
                    ↓
Massa/CM/inersia + geometri + torsi/transmisi + suspensi/rem/aero
                    +
Ban: slip/load curves + suhu/tekanan/camber/wear + overrides
                    +
Track: collision geometry + material/surface + collision objects
                    +
Input pengemudi + filter/assists + state ban/fuel/damage
                    ↓
Kode solver → gerakan kendaraan, kontak, rotasi roda, feedback
```

Model visual mobil dan track hanya satu bagian aset. Rating Handling, PI, angka horsepower puncak, berat katalog, serta waktu akselerasi tersimpan tidak menggantikan data komponen dan kurva yang dikonsumsi sistem fisika.

### Mobil dan komponen

FM2 menghubungkan banyak upgrade melalui `Data_Car.Id = Ordinal`. FM3/FM4 memisahkan body dan drivetrain lebih jelas: mobil → `List_UpgradeCarBody` → `Data_CarBody` dan upgrade body; mobil → `List_UpgradeDrivetrain` → `Data_Drivetrain` dan upgrade drivetrain. Engine dan ban juga memiliki hubungan tersendiri.

Stock harus dipilih dengan **`IsStock=1`**, bukan sekadar `Level=0`. Ada komponen stock pada level lain. Jangan membentuk semua foreign key dengan perkalian ID; ikuti field relasi yang sebenarnya. Contoh dan join terverifikasi ada di laporan per game.

| Kelompok input | Field/struktur yang ditemukan | Hubungan dengan handling |
|---|---|---|
| Massa dan distribusi | Mass, CMHeight, CMBackFront, CMLeftRight, BlockDim, MassDiff komponen | Inferensi fisik: respons akselerasi, transfer beban dan kecenderungan rotasi; formula inertia dari dimensi block belum terbukti |
| Geometri | Wheelbase, track width, ride height, reference position, bounding box, collision spheres | Jarak kontak roda dan bentuk benturan; transform sumbu antarformat perlu dipertahankan |
| Mesin | Inertia, RPM range, normalized torque samples + scale, zero/full throttle, aspiration dan upgrade modifiers | Kurva torsi di seluruh rentang, overrun/limiter dan inertia lebih informatif daripada peak power |
| Drivetrain | Gear/final-drive ratio, reverse, shift time, clutch, driveline inertia, differential front/rear/center | Traksi saat akselerasi/deselerasi dan pembagian torsi. Ada nilai sentinel dan field axle yang tidak selalu aktif |
| Suspensi | Spring, bump/rebound, bumpstop, travel, geometry pivots, camber gain, toe/caster; anti-roll | Pembentukan load roda dan perubahan orientasi roda. “Lebih keras” tidak cukup menjelaskan seluruh respons |
| Ban | Compound, width/rim, load/slip curves, affect curves, heat/pressure/wear coefficients, aligning torque | Grip bukan satu koefisien konstan; terhubung ke kondisi roda, ban, dan permukaan |
| Rem/aero | Bias/torque/ABS parameters, drag/downforce front/rear, upgrade sliders, drafting | Brake balance dan aero balance terpisah; modifier gameplay juga ada |
| Steering/assists | SteerMaxAngle, filtered/rate/speed-sensitive fields, TCS/STM/AutoSteer, controller mapping | Rasa kontrol dapat berubah meski massa atau mesin sama |
| Kondisi runtime | Tuning, ban/fuel/damage, input dan assists yang dipilih | Dibutuhkan untuk mereproduksi suatu kasus; master DB tidak berisi state sesi yang sedang berjalan |

Keterangan fungsi di kolom kanan adalah inferensi fisik yang dibatasi data. Nilai native, nama kolom dan relasinya tercatat sebagai bukti langsung. Urutan dan persamaan penggabungannya masih memerlukan analisis kode.

### Ban dan perubahan antar generasi

Ketiga game menggunakan struktur `List_TireCompound` → `List_TireFrictionMultiCurve` → `List_TireFrictionCurve`, dengan `List_TireAffectCurve` untuk modifier. Lateral dan longitudinal terpisah; multicurve menyimpan dua curve IDs, batas beban dan clamp. Affect curves mencakup suhu, tekanan, camber, wear, speed dan aligning torque. Data termal mencakup friction heating, transfer ke udara, sliding heat dan perubahan pressure.

Perbandingan nilai tabel, dengan ID yang sama:

| Perbandingan | Hasil langsung |
|---|---|
| FM2 → FM3 | Semua 32 friction-curve rows berbeda; 72 dari 96 affect-curve rows berubah; 16 multicurve rows tetap sama. Compound berubah dan satu ID compound bertambah |
| FM3 → FM3 Ultimate | Seluruh empat keluarga tabel ban identik nilainya |
| FM3 → FM4 | Semua 32 friction-curve rows bersama berbeda; 4 curve baru. Seluruh 16 multicurve bersama berubah pada batas/clamp load, plus 2 baru. 56 dari 96 affect curves bersama berubah, plus 12 baru |

Ini bukti perubahan kalibrasi/data ban. Kesamaan schema tidak membuktikan solver sama; perbedaan kalibrasi juga tidak sendirinya mengungkap formula solver. Belum ada dasar mengidentifikasi implementasi tersebut sebagai Pacejka, brush model tertentu, atau menyebut merek paket DLC sebagai sumber algoritme.

Contoh multicurve ID 1: FM2/FM3 `MinLoadCurve=0`, `MaxLoadCurve=1000`, `LoadClamp=3950`; FM4 `10.1972`, `1019.72`, `5000`. Unit load dan konversi runtime belum dibuktikan. `MaxSlip=49.5` pada lateral dan `1.1` pada longitudinal mendukung perbedaan domain slip, tetapi tidak dipakai sebagai bukti unit sudut/normalisasi final.

Field `Wet*` ada di data. Keberadaannya **tidak membuktikan mode hujan/balapan basah tersedia** atau aktif di game tersebut.

### Contoh mobil sama pada semua versi

`Data_Car.Id=247`, `MediaName=TOY_2000GT_69`. Nilai berikut dibaca langsung, tanpa konversi unit yang tidak terverifikasi.

| Parameter native | FM2 | FM3 | FM3 Ultimate | FM4 |
|---|---:|---:|---:|---:|
| Stock body `Mass` | 1152.598022 | 1156.661 | 1156.661 | 1156.661 |
| `CMHeight` | 0.3 | 0.2539 | 0.2539 | 0.4421 |
| `CMBackFront` | 0.5 | 0.51 | 0.51 | 0.51 |
| `SteerMaxAngle` | 35 | 35 | 35 | 42 |
| `SteerMaxAngleFiltered` | 29 | 29 | 29 | 29 |
| `GameTorqueScale` | 0.83 | 0.7625 | 0.7625 | 0.7625 |
| `GameDragScale` | 0.97 | 1 | 1 | 1 |
| `BodyAeroLongitudinalDrag` | 137.707794 | 150.8455 | 150.8455 | 150.8455 |

Nama model yang sama dan massa yang sama tidak menjamin handling sama: pusat massa, kemudi, compound/curve, assists dan executable dapat berbeda. Arah perubahan understeer/oversteer atau lap time tidak disimpulkan dari tabel ini saja.

`CurbWeight` juga bukan langsung kilogram. Contoh FM4 `11.56661` berpasangan dengan stock Mass `1156.661`. FM4 memvalidasi faktor 100 pada seluruh join stock yang tersedia; perbedaan FM2 hanya sekitar pembulatan float. Field dengan nama eksplisit `kg`, `MM`, `IN`, `RPM`, `MetersSec` dapat dipertahankan unitnya; field spring/damping/torque/load/suhu/pressure yang belum jelas disimpan sebagai nilai native.

## Track dan kebutuhan datanya

Satu “track” perlu dipisahkan menjadi environment, ribbon/layout, reverse, geometri kontak, material, objek, dan race logic. Layout reverse dapat berbagi collision mesh. Karena itu jumlah `.col`, record Tracks, dan lokasi sirkuit tidak sama.

| Input track | FM2 | FM3 / Ultimate | FM4 | Status |
|---|---|---|---|---|
| Identitas/layout | `Tracks`, MediaName/Ribbon/Reverse | Sama secara konsep | `IsHomespace`, `Active`, `IsInstalled`, `Renderable` | Record dan flags terbaca |
| Road collision | Per-ribbon `.col` | `.col`, termasuk aset Disc 2 | `.col` loose/per-paket | File/hash/header diketahui; vertices/triangles/material binding belum lengkap |
| Respons material | `surfaceTypes.xml` | `surfaceTypes.xml` | `surfaceTypes.xml`, NatalSurfaceTypes terpisah | Friction, tyre heating, bumpiness dan collision properties terbaca |
| Collision objek | Global type + CollObjs placement | Global type + placement | `CollObjects.xml` + per-ribbon placement | Posisi/orientasi dan bentuk sphere/block tersedia |
| AI/ribbon guidance | `.geo/.seg/.irt/.pit` format MLP | Keluarga MLP yang sama; common assets dibandingkan | Struktur `.sh` belum terklasifikasi | FM2/FM3 typed arrays dapat didekode; jangan menebak `.sh` FM4 sebagai AI |
| Race logic | Grid, splits, pit, start/finish | Sama, ditambah konfigurasi layout | DB grid/pit/sections/AI | Terbaca, tetapi bukan pengganti geometri wheel contact |
| Render/visual | Mesh, texture, visibility, cameras | ZIP bin dan setting visual | ZIP bin, lighting, shader/render data | Jangan mengubah visual asphalt menjadi koefisien grip tanpa surface binding |

Surface perlu ikut dipindahkan ketika meneliti/mereproduksi sebuah track. Contoh FM4: `FrictionScale=1` untuk Asphalt, `0.8` untuk Grass, dan `0.8` untuk Gravel; bumpiness mereka berbeda. RumbleStrip mempunyai respons gelombang tersendiri. Angka ini multiplier/parameter native, bukan koefisien grip final setelah semua modifier.

Pada FM2 Laguna Seca, `.geo` berisi 1.807 waypoint dan `.seg` 29 segmen. `iTrackLength=1807` pada `.seg` cocok dengan **jumlah waypoint**, sedangkan `Tracks.Length=3589`. Ini contoh bahwa label “length” belum tentu meter. Vektor `fNormal*` juga tidak selalu unit vector. Data AI berguna untuk arah/jalur, tetapi tidak menggantikan permukaan kontak dan detail curb pada `.col`.

## Perbedaan yang perlu dijaga saat memakai hasil

### FM3 biasa dan Ultimate

Semua 415 `Data_Car` yang sama serta parameter `Data_CarBody` yang sama cocok nilainya. Tabel ban, empat file dalam Media/Physics, ControllerFFB.ini, dan ControllerRumble.xml identik. Perbedaan yang ditemukan mencakup 95 mobil tambahan, 36 track records, throttle/brake mapping pada controller layout ID 10, serta speed limit pada `TrackPittingZones.Tracks_id=33/34` dari 60 menjadi 20. Keduanya terkait Nürburgring F1, yang record Tracks-nya baru muncul di UC meskipun data pendukung pit/grid sudah ada di reguler; ini bukan bukti rebalance track reguler yang sebelumnya playable. Beberapa sampel torque berbeda sangat kecil, sekitar presisi floating point 1e−15, bukan bukti perubahan kalibrasi yang bermakna.

Shared car archive member CRC/size/method dan banyak file track/AI juga cocok, sebagaimana dirinci dalam laporan FM3. Namun executable berbeda. Kesimpulan yang didukung adalah **parameter fisik konten lama sebagian besar sama dan UC memperluas konten**; bukan “seluruh kode fisika UC pasti identik”.

### FM4 region dan DLC

Database, PhysicsSettings, surface/collision types, ControllerFFB dan sampel aset yang dibandingkan Japan/Asia–USA identik byte. `default.xex` berbeda hash. Ini membatasi kesimpulan pada file yang diperiksa, bukan semua region/revisi retail.

LCE menimpa enam baris upgrade rear tire width yang sudah ada di base. Baris tersebut terkait Shelby `SHE_GT500428CJ_69`, mobil baru dari LCE; definisi mobilnya belum ada di base. Ini koreksi data yang disiapkan untuk DLC, **bukan bukti perubahan handling mobil dasar yang telah tersedia**. Contoh perubahan dan identitas row ada di laporan DLC.

Launch Track Pack menyediakan 16 record internal `PhysicsTrack` dan 2 `Soccer`. Jangan menyimpulkan track internal ini debug-only atau menghitungnya sebagai 18 sirkuit. Porsche Expansion menyediakan 30 mobil dengan data fisik biasa; SQL tambahannya mengatur event/banner, bukan model ban khusus.

### Title update

FM2 Bonus membawa TU4. FM4 memiliki tiga paket TU lokal untuk media/region tertentu. Ada patch executable `.xexp` yang belum dianalisis secara semantik; perubahan solver tidak bisa dikesampingkan hanya karena SQL yang terlihat mengubah PI, class, event, atau level pemain. Penelitian berikutnya harus menyebut hash XEX/TU dan manifest patch yang dipakai.

## Dataset minimum untuk mereproduksi kasus fisika

| Bagian | Wajib disimpan | Sudah tersedia dari riset ini |
|---|---|---|
| Build | Game/edition, region/media ID, XEX hash, TU dan DLC ordered manifest | Identitas sumber, banyak hash dan daftar paket; effective loader precedence belum direkonstruksi |
| Mobil | Car/Body/Engine/Drivetrain IDs, part terpilih, nilai stock dan overrides | Schema, katalog, contoh join dan parameter; pilihan upgrade pemain harus diberikan terpisah |
| Kurva | Torque, lateral/longitudinal friction, load ranges, affect curves, interpolation metadata | Nilai dan relasi tersedia; algoritme sampling/interpolation runtime belum lengkap |
| Tuning | Pressure, alignment, gearing, spring/damper, ARB, diff, aero/brake | Field/schema tersedia; konfigurasi kasus harus ditentukan |
| Geometri | Wheelbase/track/contact reference, body collision, track collision, transform sumbu | MAXData FM2/FM4 terdecode; geometri body FM3 tersedia di DB. `.col` topology dan transform lintasformat belum lengkap |
| Surface | ID binding, friction/thermal/bump/collision response, track objects | Respons dan placement tersedia; binding triangle/material belum lengkap |
| State | Pose/velocity, wheel speed, fuel, tyre temp/pressure/wear, damage, race conditions | Perlu input awal eksplisit; tidak tersedia sebagai state berjalan dari master data |
| Kontrol | Input stream, assists mode, steering filters, device mapping/FFB | Konfigurasi global terbaca; stream dan pilihan kasus belum ada |
| Solver | Integrator/timestep, contact constraints, combined slip, modifier order | Belum dipulihkan secara lengkap |

Dengan data sekarang, penelitian dapat menghasilkan katalog fisika, membandingkan kalibrasi, memetakan dependensi dan menyiapkan format pertukaran data. Untuk simulator yang menyamai game persis, langkah bernilai berikutnya tetap bisa dilakukan offline: decode `.col` dan material binding; telusuri loader/unit conversion; pulihkan curve interpolation/combined slip; analisis integrator/assists dan patch executable. Tidak perlu menjalankan game untuk memperdalam tahapan statis ini.

## Batas kesimpulan

Tidak ada pengukuran gaya, lap time, cadence update, input latency atau FFB hardware. Tidak ditentukan game mana paling realistis, paling grip, atau paling sulit dikendarai. Detail bentuk contact patch, model ban bernama tertentu, integrator, dan persamaan final masih terbuka. Temuan mengikat pada dump lokal dan bagian yang diperiksa; folder `mods` FM4 tidak digunakan sebagai baseline.

Semua angka perbandingan utama dapat ditelusuri ke file sumber, schema/rows dan hash pada evidence masing-masing game. Katalog CSV dan JSON adalah data penelitian lokal; tidak ada perubahan yang diterapkan pada instalasi game.
