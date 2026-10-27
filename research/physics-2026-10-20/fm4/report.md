# FM4: peta fisika dari Disc 1 dan Disc 2

Catatan repo: laporan dan source analisis disertakan. JSON/CSV/schema, hasil ekstraksi aset, disassembly dan binary yang disebut di bawah tetap lokal dan diabaikan Git; lihat [metode reproduksi](../METHODS.md).

Riset 20 Oktober 2026. Seluruh pemeriksaan offline dan statis: SQLite dibuka `mode=ro`, XML/INI dibaca, ZIP/STFS diperiksa dengan parser data. Game dan emulator tidak dijalankan. Sumber di `D:\Data` tidak ditulis. DLC terpisah ditangani laporan induk; hasil di sini adalah baseline disc.

## Hasil utama

FM4 menyimpan sebagian besar parameter handling dalam database relasional, konfigurasi global, tabel kurva ban, dan metadata geometri/collision per mobil. Ini sudah cukup untuk memetakan input model secara rinci. Belum cukup untuk merekonstruksi persamaan solver, integrator, kombinasi slip, dan urutan modifier persis seperti executable.

- Database Disc 1 berisi 198 tabel, 503 baris `Data_Car`, 502 `Data_Engine`, dan 127 `Tracks`.
- 503 baris mobil terdiri dari **501 mobil drivable** dan **2 mobil Autovista-only** (`BUN_Warthog_10`, `BEN_8Litre_31`). Jumlah baris database bukan jumlah mobil balap.
- Tepat **313** mobil memiliki `physics/maxdata.xml` di Disc 1 dan **188** di Disc 2. Tidak ada overlap; gabungannya mencakup semua 501 mobil drivable di DB.
- Ban: **9 compound, 18 multikurva beban, 36 kurva friction dengan 100 sampel, 108 affect curves**. Data mendeskripsikan pengaruh beban, temperatur, tekanan, camber, wear, speed, dan aligning torque.
- `CarPhysicsUpdateHz 359` tertulis eksplisit dalam konfigurasi. Itu bukti nilai konfigurasi, bukan pengukuran frekuensi runtime dan bukan alasan membulatkannya menjadi 360 Hz.
- Data physics inti yang dibandingkan identik antara Japan/Asia dan USA; kedua `default.xex` berbeda hash. Kesamaan seluruh kode solver antarregion belum dibuktikan.

## Sumber dan kekuatan bukti

Alias sumber dalam laporan:

`JP1 = D:\Data\forza-motorsport-4\Forza Motorsport 4 (Japan, Asia) (Disc 1) (Play Disc)`

`US1 = D:\Data\forza-motorsport-4\USA\Forza Motorsport 4 (USA) (Disc 1) (Play Disc)`

`JP2 = D:\Data\forza-motorsport-4\Forza Motorsport 4 (Japan, Asia) (Disc 2) (Content Install Disc)`

| ID bukti | Sumber | Terbukti dari pembacaan |
|---|---|---|
| F4-01 | `JP1\Media\db\gamedb.slt` | SQLite valid; `PRAGMA integrity_check = ok`; schema/kolom, nilai dan join tersedia |
| F4-02 | `JP1\Media\physics\PhysicsSettings.ini` | Konfigurasi global handling, assists, timestep target, tuning, collision dan drafting |
| F4-03 | `JP1\Media\physics\surfaceTypes.xml` | 61 definisi surface, friction, bumpiness, material collision, springiness |
| F4-04 | `JP1\Media\physics\CollObjects.xml` | Collision spheres, mass distribution, SurfaceId objek |
| F4-05 | `JP1\Media\cars\ACU_NSX_97.zip::physics/maxdata.xml` | Geometri fisik mobil; seluruh 313 maxdata Disc 1 juga telah dibaca dengan CRC32 valid |
| F4-06 | `JP1\Media\Tracks\LagunaSeca\Ribbon_00\lagunaseca_track_00.col` dan file track terkait | Berkas collision biner hadir, header dan hash disimpan; format geometry lengkap belum didekode |
| F4-07 | `JP2\content\0000000000000000\4d530910\00000002\4d53091000000001` sampai `...04` | Empat container PIRS; inner ZIP diinventaris; metadata kecil dibaca dengan SHA1 per block dan CRC32 ZIP |
| F4-08 | `JP1\Media\ControllerFFB.ini` | Parameter output feedback controller terpisah dari parameter mobil |

SHA256 `gamedb.slt` JP1/US1: `02216ecb4139b417f6d0922ef2aef3614fc79157e0001d3c0fd97e16a83f40fd` (6.500.352 byte). SHA256 PhysicsSettings: `f71196b763d204e83bca8cc1c4a03a719d98f17d20f250c2a8e52ae6cff6da76`. Seluruh hash yang diperiksa dan path absolut tersimpan dalam `evidence.json`. Hash sama berarti byte sama untuk pasangan yang diperiksa; bukan autentikasi terhadap master retail resmi.

## Susunan data mobil

`Data_Car.Id` adalah ordinal mobil. Stock dipilih dengan **`IsStock=1`**, bukan asumsi `Level=0`: misalnya stock camshaft dan spring/damper NSX 1997 justru Level 1.

| Sistem | Jalur relasi dan kolom yang perlu disimpan |
|---|---|
| Massa dan pusat massa | `Data_Car` → `List_UpgradeCarBody` melalui `Ordinal` → `List_UpgradeCarBodyWeight` melalui `CarBodyID`; `Mass`, `InitialMass`, `CMHeight`, `CMBackFront`, `CMLeftRight`, `BlockDimX/Y/Z` |
| Dimensi/chassis | `Data_CarBody`: wheelbase, track outer depan/belakang, stock ride height, bounding box, bottom-center; `CarPartPositions` menempatkan bagian mobil |
| Mesin | `List_UpgradeEngine` → `Data_Engine`; massa mesin, inertia, aspiration/boost, tank, konfigurasi; upgrade camshaft → redline, stall/start RPM, `TorqueCurveMaxRPM`, `TorqueCurveFullThrottleID` → `List_TorqueCurve` |
| Kurva torsi | `List_TorqueCurve.TorqueScale`, `NumTorqueValues`, `v0..v185`, `ZeroThrottleTorqueScale`; upgrade intake/fuel/exhaust/displacement dll memberi modifier |
| Transmisi | `List_UpgradeDrivetrain` → `Data_Drivetrain` dan `List_UpgradeDrivetrainTransmission`: gear ratios, reverse, final drive, shift time, inertia; clutch/driveline tabel tersendiri |
| Diferensial | `List_UpgradeDrivetrainDifferential`: front/rear/center LSD accel/decel, relative-velocity clamp, input torque, `RearToqueSplit` (ejaan asli DB) |
| Ban | `List_UpgradeTireCompound` → `List_TireCompound` → lateral/longitudinal multikurva → friction curves; affect curves terpisah; dimensi ban/rim dan upgrade width/rim; `TireMod_FrictionScale` memberi exception 10 mobil |
| Suspensi | `List_UpgradeSpringDamper` → dua `List_SpringDamperPhysics` (front/rear); spring, bump/rebound damping, min/max ride height, bumpstop, pivot, toe/camber/caster, camber gain, travel |
| Anti-roll bar | Upgrade front/rear → `List_AntiSwayPhysics`; stiffness, tuning range, damping |
| Aero | `Data_Car.BodyAero*` ditambah bumper/wing → `List_AeroPhysics`: drag/downforce pada slider 0/1, lateral drag, angle, torque distribution |
| Rem | `List_UpgradeBrakes`: torque/bias sliders, brake size/type/pistons, friction scale, ABS release points dan duration, damage link |
| Damage | `List_DamageModDef`, link damage pada parts, `DamageDiffSettings`, global engine/clutch/collision settings |
| Input dan assists | `Data_Car.Steer*`, `AssistsTCS*`, `AutoSteerOverrides`, `PhysicsSettings.ini`; FFB dalam INI tersendiri |
| Collision mobil | ZIP `physics/maxdata.xml`: bounding box yang dibevel, posisi/radius/flags sphere; terpisah dari visual `.carbin` dan tekstur |

Dengan demikian rating Handling/Braking/Acceleration, PI, `SimTimeTo60MPH`, dan angka performa katalog bukan pengganti parameter fisik di atas. Banyak field tersebut merupakan hasil/metadata performa tersimpan; prosedur pembentukannya belum dibuktikan.

### Contoh terhubung: Acura NSX 1997, ordinal 408

Seluruh baris dan upgrade relevan tersedia dalam `sample_cars.json` → `408`. Contoh lain: Toyota 2000GT 1969 (`247`) dan Mazda MX5 Superlight 2010 (`1233`).

| Data | Nilai native dan bukti |
|---|---|
| Body | `CarBodyID=408000`; `Mass=1360`, `CMHeight=0.4343`, `CMBackFront=0.42`, `CMLeftRight=0.5`; `ModelWheelbase=2.55124` |
| Dimensi ban | depan `215/45`, wheel `16 IN`; belakang `245/40`, wheel `17 IN`; width `MM` dan wheel `IN` eksplisit di kolom |
| Mesin | `EngineID=162`, `EngineMass-kg=190`, compression 10.2; `MomentInertia=0.1018` |
| Kurva | stock camshaft `162000`: redline 8000 RPM, curve max 9500 RPM, 96 entries; curve `162000`: scale 303.968, `v53=1`, `v95=-2.63`, zero-throttle scale 160.548 |
| Drivetrain | `DrivetrainID=161`; final drive 4.062; reverse −3.186; forward 3.067, 1.957, 1.429, 1.125, 0.914, 0.718; shift time 0.2 |
| Differential | rear LSD accel 850, decel 106.25; relative-velocity clamp 50. Front values juga ada meski DriveType=2/RWD; jangan otomatis terapkan semua field ke axle aktif |
| Suspensi | front ID 408001 / rear 408101; ride height 0.1431 / 0.1459; spring 40.404 / 55.796; bump damping 2.9129 / 4.0225; rebound 4.3693 / 6.0338; camber −0.5 / 0 |
| Ban stock | compound 5 `5_UltraHighPerformance`; lateral multikurva 9, longitudinal 10; curve 17/18 dan 19/20 |
| Aero body | longitudinal drag 159.0466; forward downforce front −15.95, rear −13.05; interpretasi gaya negatif dan referensi speed harus ditelusuri ke solver |
| Modifier game | `GameTorqueScale=0.875`; chassis stock memberi front lat/long scale 0.985, rear 0.9925 |
| Collision | maxdata berisi 42 sphere; wheelbase 2.551240 cocok dengan DB. `BottomCenterWheelbasePos.z` XML +0.057925 sedangkan DB −0.057925: ada konvensi sumbu/transform yang harus diperhitungkan |

**Satuan:** kolom berlabel `-kg`, `MM`, `IN`, `RPM`, `-mph`, `-sec`, serta konfigurasi `MetersSec`/`KG`/`DegSec` memberi bukti unit eksplisit. Dimensi body/CM/ride height sangat konsisten dengan meter dan mass body dengan kg, tetapi label unit tidak ada pada field tersebut; diperlakukan sebagai inferensi kuat. Unit spring, damping, torque, aero, suhu dan pressure perlu konfirmasi kode sebelum konversi resmi.

Peringatan terukur: `Data_Car.CurbWeight × 100 = stock List_UpgradeCarBodyWeight.Mass` untuk seluruh join yang tersedia (residu floating point maksimum sekitar 4.55e−13). NSX `CurbWeight=13.6`, bukan 13.6 kg. `SimPeakTorque=3.03968` juga tidak boleh dibaca langsung sebagai torsi N·m; curve scale bernilai 303.968. Simpan nilai mentah dan konvensi sumber.

### Bentuk model ban yang bisa dibuktikan

NSX compound 5 menunjuk lateral multicurve 9: `MaxSlip=49.5`, `MinLoadCurve=10.1972`, `MaxLoadCurve=1019.72`, `LoadClamp=5000`, curve 17 dan 18. Longitudinal multicurve 10 mempunyai `MaxSlip=1.1` dan curve 19/20. Curve memiliki `FrictionScale` dan 100 ordinat; ini bukti tabel respons slip yang bergantung beban. Sudut slip lateral versus slip ratio longitudinal adalah interpretasi kuat dari nama dan rentang, tetapi unit dan interpolasi tepat masih memerlukan kode.

Compound menyimpan thermal transfer udara/kecepatan/beban, friction heating/wear, perubahan pressure, sliding overheating, distribusi heat karena camber, dan kurva aligning torque. Misalnya RacingSlick `FrictionWear=0.00002`, DragTire `0.00025`; angka ini menunjukkan perbedaan koefisien tersimpan, bukan prediksi umur ban tanpa fungsi pembaruan.

Tidak ditemukan dasar untuk menyebut tabel ini implementasi Pacejka atau model brush tertentu. Nama model komersial, asal pengukuran ban, detail combined slip, contact patch, serta integrator tidak terungkap dari tabel saja. Field `Wet*` ada tetapi **tidak membuktikan hujan atau balapan basah tersedia**.

## Global handling, assists dan feedback

F4-02 menunjukkan lapisan pengaturan gameplay di atas parameter kendaraan:

- Temperature/pressure/wear/camber affect-friction scale masing-masing 1; `UseVertexNormals TRUE`; `CarGravityScale=1`, `AirbornGravityScale=1.25`.
- `HighSpeedDragSpeed0MetersSec=119.3`, speed1=122.9, scale0=1, scale1=1.5. Ini parameter drag tambahan pada speed tinggi; kurva pemakaiannya belum dibuktikan.
- `RacingLineFricScale0=1.01`, scale1=1; ada parameter friction terkait racing line.
- TCS mempunyai konstanta berbeda RWD/FWD/AWD dan versi AI, serta slip-sensitive braking tanpa ABS. Input rem dipetakan lewat beberapa titik, bukan hanya angka pedal mentah.
- `FrictionTorqueMod` memiliki grup WithAssists, NoAssists dan SimulationSteering. SimulationSteering mengisi turn/straighten scales=1 dan clamps=10000, berbeda dari grup lain. Ini mendukung adanya perilaku steering berbeda; tidak membuktikan mode Simulation menonaktifkan seluruh modifier.
- Drafting memiliki kotak/fade spasial dan pengali front/body/rear drag serta downforce untuk mobil mengikuti dan memimpin.
- Damage, clutch wear, fuel burn, collision torque, rollover recovery, sidewall-to-slip scaling, sliding instability juga dikonfigurasi.
- F4-08: `DynFFBScale=1`, `DamperScale=0.1`, `SpringScale=0.5`, perubahan spring dengan speed dan rear slip. FFB perlu dipetakan tersendiri; perubahan rasa setir tidak otomatis sama dengan perubahan grip mobil.

## Data track yang diperlukan

127 record `Tracks` terdiri dari 114 active non-homespace, 6 inactive non-homespace installed, 1 inactive not-installed, dan 6 homespace. Maka 127 tidak boleh diklaim sebagai jumlah sirkuit unik. `MediaName`, `RibbonIndex`, `ReverseIndex`, environment dan flags penting untuk menghubungkan layout ke berkas.

| Lapisan | Data yang tersedia / batas |
|---|---|
| Geometri kontak | `Tracks/<MediaName>/Ribbon_nn/*_track_nn.col`; 83 berkas loose. Sangat kuat sebagai collision input berdasarkan penamaan/pasangan objek; struktur vertices/triangles/material binding belum diurai |
| Surface response | 61 surface dalam `surfaceTypes.xml`; friction, offroadness, tyre heat, speed-dependent friction/torque, procedural bumpiness, springiness, collision category pairs |
| Objek collision | global `CollObjects.xml`; per-ribbon `collobjs.xml`, `collobjsplacement1.xml`: physics type, position, orthogonal axes, graphics name; geometri sphere/box dan mass distribution global |
| Layout/race logic | DB `Tracks`, start grid/flying start, split/turn sections, pitting zones/profiles, starting merges, track-specific AI; ini diperlukan untuk race/AI, bukan pengganti contact surface |
| Visual | `bin.zip` berisi mesh/rendering bins, `.bix`, shaders; TrackSettings didominasi sky, lighting, fog, shadow, exposure, reflection; texture grip tidak bisa disimpulkan dari rupa aspal |
| Belum terklasifikasi | 76 file `.sh`, `.pvs` dan binary tertentu belum ditentukan struktur/semantiknya. Jangan menamai `.sh` sebagai spline AI atau data fisika tanpa bukti lebih lanjut |

Contoh Laguna Seca: `Tracks.id=0`, `MediaName=LagunaSeca`, ribbon0, reverse0, Length=3602 (meter merupakan inferensi kuat). Collision file 2.801.664 byte, SHA256 `1b5673328e8b07055146b288d229aa1f7125c21307746adc14c58c06512e5598`. `collobjs.xml` meletakkan `Barrel1` dan `BrakeMarker` dengan position serta orientation. Nilai wind dalam TrackSettings tidak cukup membuktikan gaya angin mobil; global `WindInstability\IsOn false` dan hubungan rendering/physics belum ditelusuri.

Contoh surface (nilai mentah F4-03):

| Surface | FrictionScale | OffRoadness | HeatTireScale | Bumpiness |
|---|---:|---:|---:|---|
| Asphalt | 1 | 0 | 1 | Simplex; frequency .07; scale −.009 |
| Grass | .8 | 1 | .1 | HeightGrid; frequency 1.5; scale .02 |
| Gravel | .8 | 1 | .1 | HeightGrid; frequency 2.4; scale .03; dry peak SA 30 |
| RumbleStrip | 1 | 0 | 1 | SinWave; frequency .73; scale .05; offset .01 |

Surface juga mencakup slow grass/asphalt, quicksand, several bump strengths, high-friction concrete, speed bump, drag VHT dan invisible border. Jadi karakter track membutuhkan mesh kontak **dan** ID material **dan** parameter respons/procedural bumps, bukan mesh visual saja. Binding surface ID di `.col` belum dipulihkan.

## Disc 2 dan hubungan dengan Disc 1

| Container suffix | Nama dari header PIRS | Mobil dengan maxdata | Isi tambahan |
|---|---|---:|---|
| 00000001 | 1950–2000 Model Year Car Pack | 63 | 2.935 inner ZIP entries, audio, strings |
| 00000002 | 2001–2005 Model Year Car Pack | 69 | 3.337 inner ZIP entries, audio, strings |
| 00000003 | 2006–Current Model Year Car Pack | 56 | 2.571 inner ZIP entries, audio, strings |
| 00000004 | Autovista Car Pack | 0 | 21 folder mobil SLOD, 2.722 ZIP entries, presentation/media |

Keempat content ZIP tidak memiliki `.slt` atau track. Stock parameter seluruh 188 mobil tambahan sudah terdapat di gamedb Disc 1; Disc 2 menyuplai asset mobil dan geometri collision. Ini mendukung satu sistem fisika dengan populasi asset yang dipisahkan media. Tidak ada bukti solver physics berbeda untuk Disc 2. `default.xex` Disc 2 merupakan executable lain pada installer disc, bukan dasar menyimpulkan model handling kedua.

## Artefak dan kelanjutan riset

- `car_catalog.csv`: 503 mobil, sumber Disc1/Disc2, ID stock components, dimensi, massa/CM, aero dan modifier penting.
- `track_catalog.csv`: 127 record layout, flags, lokasi collision.
- `schema.json`: seluruh 198 tabel, row count, tipe kolom dan SQL schema.
- `sample_cars.json`: tiga mobil dengan chain stock dan pilihan upgrade; seluruh nilai kurva tersimpan.
- `global_physics_tables.json`, `physics_files.json`, `surface_summary.json`: data global terstruktur.
- `maxdata_disc1_summary.json`: 313 hasil decoder dengan SHA256, geometry scalar dan jumlah collision sphere; `disc2_inventory.json`: metadata/container/ZIP dan contoh yang diverifikasi.
- `evidence.json`: path dan hash sumber; `inspect_fm4.py`, `inspect_disc2.py`, `catalog_fm4.py`: langkah reproduksi.

Langkah statis berikut yang paling bernilai: decode `.col` dan binding material; petakan unit internal melalui data-flow loader; telusuri sampling/interpolation kurva dan combined slip; tentukan transform geometri XML/DB; cari urutan modifier assists, damage, tire, aero, dan timestep di executable yang provenance-nya diverifikasi. Sampai itu selesai, laporan ini memisahkan parameter yang benar-benar terbaca dari dugaan tentang algoritme pemakaiannya.

### Tambahan cross-reference kode statis

Image yang sudah ada di workspace `work/fm4/loaded-image.bin` dibaca dan didisassembly sebagai data; tidak dieksekusi. Tool disassembly yang dipakai mempunyai source lokal `work/fm4/disassemble.cpp` yang dibaca terlebih dahulu. Provenance image belum dicocokkan ulang dengan salah satu XEX retail, sehingga hasil tambahan ini tidak menggantikan bukti disc.

Dengan image base 0x82000000 dari section list lokal, `CarPhysicsUpdateHz` berada di 0x8214668C. Analisis rentang 0x828962F0–0x828962FC menemukan pasangan alamat key dan field, serta referensi ke helper 0x828B25C0. Instruksi/disassembly asli tidak disertakan dalam repo. Ini bukti referensi kode yang memasangkan key dengan sebuah field; penggunaan field di loop physics dan waktu update aktual belum ditelusuri.

String query `SELECT * FROM List_TireFrictionCurve WHERE FrictionCurveID=` juga mempunyai referensi pada 0x828A2200, `MinLoadCurve` pada 0x828A2144, dan template path `.col` pada 0x826DBD80. Hasil scan, hash image dan disassembly berada di `static_xrefs.json`/`static_xrefs_disassembly.txt`; `static_xrefs.py` mereproduksi kandidat cross-reference.
