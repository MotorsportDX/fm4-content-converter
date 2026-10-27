# FM3 dan FM3 Ultimate Collection — riset fisika statis offline

Catatan repo: laporan dan source analisis disertakan. JSON/CSV/schema, hasil ekstraksi aset, disassembly dan binary yang disebut di bawah tetap lokal dan diabaikan Git; lihat [metode reproduksi](../METHODS.md).

Tanggal: 20 Oktober 2026. Semua pembacaan dilakukan lokal, tanpa jaringan, menjalankan game/emulator, memasang content, atau mengubah sumber. SQL dari paket dibaca sebagai teks; tidak dieksekusi. SQLite sumber dibuka `mode=ro`. Dekompresi ZIP method 21 dilakukan oleh decoder LZX lokal, bukan dengan menjalankan executable game.

## Kesimpulan utama

**Terbukti:** kedua edisi menggunakan susunan data fisika yang sama: database SQLite untuk mobil/part/kurva ban; `PhysicsSettings.ini` untuk pengaturan global/assist; `surfaceTypes.xml` untuk perilaku permukaan; aset collision track `.col`; data ribbon/AI `.geo`, `.seg`, `.irt`, `.pit`; serta executable yang menerapkan model tersebut. Data yang ditemukan cukup untuk memetakan input dan hubungan komponen secara rinci. Persamaan solver dan urutan integrasi belum dibuktikan.

**Terbukti:** UC sangat dominan menambah content. Semua 415 baris `Data_Car` lama identik; 415 `Data_CarBody` lama identik; data lama suspension, antiroll, aero, compound ban dan seluruh kurva ban identik. Empat file inti `Media/Physics`, FFB, rumble, dan game option presets identik byte demi byte. Tetapi executable berbeda; temuan ini **tidak membuktikan solver kedua executable identik**.

**Terbukti:** UC juga memuat perubahan pendukung: layout controller ID 10 menukar `LeftTrigger/RightTrigger` dari Gas/Brake menjadi Brake/Gas, perubahan kamera, grid/pitting Nürburgring F1, metadata, serta perbedaan sangat kecil hasil ekspor angka kurva torsi. Jadi tidak tepat menyebut seluruh UC hanya salinan identik dengan mobil tambahan.

**Batas penting:** angka jumlah di bawah adalah entri database atau file yang teramati, bukan jaminan semua content muncul pada menu atau dapat dipakai dalam setiap mode. Tabel track mencakup layout terbalik, segmen, drag, dan tujuh track UI yang `Active=0`.

## Sumber dan pembagian disc

Singkatan path yang digunakan:

- **R1**: `D:\Data\FM3\USA\Forza Motorsport 3 (USA) (Disc 1) (Play Disc)`
- **R2**: `D:\Data\FM3\USA\Forza Motorsport 3 (USA) (Disc 2) (Content Install Disc) (1)`
- **U1**: `D:\Data\FM3\USA Ultimate Collection\Forza Motorsport 3 - Ultimate Collection (USA) (Disc 1) (Play Disc)`
- **U2**: `D:\Data\FM3\USA Ultimate Collection\Forza Motorsport 3 - Ultimate Collection (USA) (Disc 2) (Content Install Disc)`

| Lapisan | FM3 reguler | FM3 Ultimate Collection | Makna |
|---|---:|---:|---|
| File Disc 1 | 3.053 | 3.057 | Inventaris filesystem; bukan hitungan mobil |
| File Disc 2 luar paket | 44 | 53 | Termasuk installer, UI dan container |
| Tabel `gamedb.slt` | 176 | 177 | UC menambah `TrialLoadingImages` |
| `Data_Car` | 415 | 510 | UC menambah 95 ID, tidak menghapus 415 lama |
| `Data_CarBody` | 415 | 510 | Geometri/bounding box mobil |
| `Data_Engine` | 431 | 525 | Termasuk mesin swap; bukan jumlah mobil |
| `List_TireCompound` | 8 | 8 | Seluruh nilainya identik |
| `List_TireFrictionMultiCurve` | 16 | 16 | Dua arah per compound |
| `List_TireFrictionCurve` | 32 | 32 | Sampel bentuk kurva |
| `List_TireAffectCurve` | 96 | 96 | Temperatur/tekanan/camber/wear/dll. |
| `List_SpringDamperPhysics` | 2.036 | 2.512 | Berbagai mobil/axle/level upgrade |
| `List_AntiSwayPhysics` | 1.839 | 2.301 | Berbagai mobil/axle/upgrade |
| `List_AeroPhysics` | 364 | 467 | Termasuk body kit/wing |
| `Tracks` | 109 | 145 | 102 vs 138 `Active=1`; tujuh UI tidak aktif |
| `Environments` | 33 | 36 | Database lingkungan, bukan jumlah sirkuit playable |
| Paket STFS Disc 2 | 4 | 8 | Dibaca dari header dan file table |

Seluruh 176 schema bersama mempunyai hasil `PRAGMA table_info` identik. Teks `CREATE TABLE` berbeda whitespace; flag `schema_identical=false` di `db_comparison.json` membandingkan teks mentah, bukan bentuk kolom. `summary_evidence.json` memberi pemeriksaan schema struktural yang benar. Kedua `PRAGMA quick_check` menghasilkan `ok`.

### Disc 2 reguler

Paket berada di `Content\0000000000000000\4D53084D\00000002\`:

| ID paket | Nama pada header STFS | Isi/aktivasi yang terbukti |
|---|---|---|
| `4D53084D0CCF0013` | Asian Car Pack | 37 ID mobil; `0013_pri_65.zip`; SQL `19000_execute.sql` |
| `4D53084D0CCF0014` | European Car Pack | 39 ID mobil; `0014_pri_65.zip`; SQL `20000_execute.sql` |
| `4D53084D0CCF0015` | American Car Pack | 28 ID mobil; `0015_pri_65.zip`; SQL `21000_execute.sql` |
| `4D53084D0CCF0060` | Road Racing Track Pack | 29 ID layout; Amalfi, FujimiKaido, Nurburgring; SQL `96000_execute.sql` |

Keempat SQL reguler hanya mengubah `IsInstalled=1, IsPurchased=1` untuk daftar ID. **Parameter fisika untuk mobil/track Disc 2 reguler sudah ada pada DB Disc 1.** Disc 2 menyediakan aset dan aktivasi. Misalnya Toyota 2000GT `Id=247, MediaName=TOY_2000GT_69, ContentId=19` sudah mempunyai semua data di R1 tetapi `IsInstalled=0`; SQL paket Asian Car Pack menyebut ID 247 secara eksplisit.

R1 memiliki 306 entri mobil `ContentId=0`, lima `ContentId=16`, serta 104 entri tiga car pack di atas. Angka 415 tidak boleh langsung ditulis sebagai 415 aset mobil pada Disc 1. Ada 311 ZIP dalam `Media/Cars`; 300 mempunyai `carattribs.xml` yang berhasil didekompresi dan CRC diverifikasi.

### Tambahan Disc 2 UC

U2 mempunyai empat paket yang sama serta empat paket berikut:

| ID paket | Nama header | Patch dan konten |
|---|---|---|
| `...0030` | Forza Ultimate Car Pack 1 | `4048_merge.slt` (491.520 byte), 28 mobil; SQL aktivasi `48005_execute.sql` |
| `...0035` | Forza Ultimate Car Pack 2 | `4053_merge.slt` (611.328 byte), 40 mobil; SQL aktivasi `53005_execute.sql` |
| `...0040` | Forza Ultimate Car Pack 3 | `4064_merge.slt` (515.072 byte), 27 mobil; SQL aktivasi `64005_execute.sql` |
| `...0045` | Forza Ultimate Track Pack | `4069_merge.slt` (48.128 byte), 36 layout; SQL aktivasi `69005_execute.sql` |

Lokasi patch adalah member `media/db/patch/...` dalam ZIP `Media/DLCZips/00xx_pri_65.zip` di dalam container STFS. Seluruh empat merge DB telah didekompresi dan CRC diverifikasi. Tabel patch tidak mendeklarasikan primary key; perbandingan memakai primary key dari schema DB utama. Semua baris bersama yang memiliki key tersebut sama dengan U1 untuk parameter fisika, dengan perbedaan pada flag instalasi/pembelian: car pack 1/2 `IsInstalled`, car pack 3 `IsInstalled` dan `IsPurchased`, track pack `IsInstalled`. SQL aktivasi kemudian menyetel kedua flag menjadi 1. Tidak ada alasan untuk menjumlah 95 baris merge sekali lagi ke 510: 95 ID itu sudah tercantum pada U1.

Track pack UC memuat `NurburgringF1` (2 layout, `ContentId=45`), `PhysicsTrack` (16, `ContentId=6`), dan `TestTrackinfield` (18, `ContentId=5`). Nama folder internal dipertahankan karena tidak semua display name string telah dilokalisasi. `PhysicsTrack` adalah nama aset; nama itu sendiri bukan bukti adanya solver terpisah.

Car pack biasa UC mengganti nama patch `19000/20000/21000` menjadi `19005/20005/21005`; isi SQL sama. ZIP menambah thumbnail/string table. Pada common car asset members, CRC, ukuran, dan metode kompresi tidak berubah. Track rendering ZIP Amalfi/FujimiKaido/Nurburgring seluruh member metadata identik. Tiga perubahan member pada `0060_pri_65.zip` semuanya file kamera Amalfi, ditambah thumbnail baru; 101 file `.col/.geo/.irt/.seg/.pit` loose di paket track bersama identik SHA-256.

## Peta input fisika mobil

`Media/DB/gamedb.slt` adalah pusat parameter. `Data_Car.Id` menjadi ordinal mobil; tabel upgrade memilih part stock atau upgrade dan menunjuk objek fisika. Jangan menganggap nama model/engine sama dengan ID atau menggabungkan tabel hanya lewat urutan baris.

| Komponen | Tabel/kunci | Data yang ditemukan | Implikasi untuk rekonstruksi |
|---|---|---|---|
| Identitas dan kendali | `Data_Car.Id` | `MediaName`, drive type, steering rates, speed-sensitive steer, TCS/STM, drag/downforce, `GameTorqueScale`, `GameDragScale` | Spesifikasi mobil riil saja tidak cukup; ada parameter penalaan game |
| Body terpilih | `List_UpgradeCarBody.Ordinal -> CarBodyID` | Hubungan mobil/body dan `MassDiff` | Harus memilih stock/upgrade yang tepat |
| Geometri | `Data_CarBody.Id` | Wheelbase, lebar track depan/belakang, ride height model, bounding box, pusat wheelbase | Dibutuhkan untuk kontak dan dimensi/inersia; rumus pemakaiannya belum dibuktikan |
| Massa/CG | `List_UpgradeCarBodyWeight.CarBodyId` | `Mass`, `InitialMass`, `CMHeight`, `CMBackFront`, `CMLeftRight`, `BlockDimX/Y/Z` | Ada massa, pusat massa dan dimensi blok; formula tensor inersia belum dipulihkan |
| Mesin terpilih | `List_UpgradeEngine.Ordinal -> EngineID` | Massa/distribusi/drag akibat swap | Mesin dapat berbeda dari stock |
| Mesin dasar | `Data_Engine.EngineID` | `EngineMass-kg`, `MomentInertia`, `StockBoost-bar`, tangki, konsumsi, torque steer | Sebagian unit eksplisit pada nama field |
| RPM/torsi | `List_UpgradeEngineCamshaft.EngineID` -> `List_TorqueCurve` | Redline/stall/start RPM, max RPM, dua kurva zero/full throttle, `TorqueScale`, sampel `v0..v150` | Bentuk torsi dan engine braking berbasis data; interpolasi runtime belum dibuktikan |
| Part mesin | Tabel `List_UpgradeEngine*` | Displacement, intake, exhaust, turbo, supercharger, fuel, ignition, flywheel, intercooler, dan lainnya | Hasil fisika harus menggabungkan pilihan part, bukan hanya peak horsepower |
| Drivetrain | `List_UpgradeDrivetrain.Ordinal -> DrivetrainID` | Drive type, massa, distribusi | Hubungan drive layout/konversi |
| Transmisi | `List_UpgradeDrivetrainTransmission.DrivetrainID` | Final drive, `GearRatio0..8`, shift time, inertia | Gear reverse/unused mempunyai nilai khusus; jangan tafsir `NumGears` tanpa membaca rasio |
| Differential | `List_UpgradeDrivetrainDifferential` | Front/rear/center limited slip accel/decel, relative-velocity clamp, `RearToqueSplit` | Model mempunyai distribusi torsi dan penguncian berbeda menurut keadaan |
| Suspensi | `List_UpgradeSpringDamper.Ordinal` -> dua ID `List_SpringDamperPhysics` | Spring, bump/rebound, stops, ride travel, pivot, perubahan camber, toe/caster | Front/rear terpisah, stock/default serta rentang tuning |
| Antiroll | `List_UpgradeAntiSwayFront/Rear` -> `List_AntiSwayPhysics` | Stiffness min/default/max, damping | Sambungan antara axle dan roll response |
| Aero | `Data_Car` dan `List_AeroPhysics` melalui bumper/wing | Longitudinal/lateral/vertical drag, front/rear downforce, slider, zero-downforce angle | Body, kit dan wing harus disatukan; bukan satu koefisien Cd saja |
| Rem/ABS | `List_UpgradeBrakes.Ordinal` | Brake torque/bias slider, handbrake, ABS release/duration menurut steer depan/belakang | Control layer dapat memengaruhi stopping/handling |
| Roda/ban | Ukuran `Data_Car`, upgrade width/rim, `List_Wheels`, `List_UpgradeTireCompound` | Ukuran/compound/inertia/modifikasi massa | Radius dan grip harus terkait part aktual |
| Kerusakan | `List_DamageModDef` + ID damage pada part | Impact min/max, peluang, efek pada komponen | Game memuat parameter kerusakan mekanis; state runtime belum diketahui |

### Ban: model data yang dapat dibuktikan

Delapan compound bernama `1_Touring` sampai `8_RacingSlick`. Masing-masing merujuk `FrictionMultiCurveLateralID` dan `FrictionMultiCurveLongitudinalID`. Setiap multi-curve memiliki `MaxSlip`, `MinLoadCurve`, `MaxLoadCurve`, `LoadClamp`, serta dua `TireFrictionCurveID`; setiap kurva menyediakan `NumCurveValues`, `FrictionScale`, dan 100 kolom sampel `v0..v99`.

Ini bukti kuat bahwa model menggunakan bentuk kurva grip lateral/longitudinal dengan ketergantungan beban yang disediakan sebagai data. Ini **belum membuktikan** formula Pacejka, brush model, persamaan combined-slip tertentu, interpolasi linear, atau kondisi contact patch yang dipakai executable.

`List_TireCompound` juga mempunyai pemindahan panas akibat temperatur udara/kecepatan/beban/slip/rolling resistance, overheating, sliding heat, wear, perubahan pressure, dan referensi affect curves untuk temperatur, pressure, wear, speed, camber, slip angle/ratio, serta aligning torque. `PhysicsSettings.ini` menetapkan empat skala `TempAffectFrictionScale`, `PressureAffectFrictionScale`, `WearAffectFrictionScale`, `CamberAffectFrictionScale` semuanya 1. Kolom wet-friction ditemukan; keberadaannya **bukan bukti** weather/rain mode aktif.

Contoh `TireCompoundID=5` (`5_UltraHighPerformance`): lateral curve set 9 dan longitudinal 10. Set 9: `MaxSlip=49.5`, curve IDs 17/18; set 10: `MaxSlip=1.1`, curve IDs 19/20. Keduanya mempunyai `MinLoadCurve=0`, `MaxLoadCurve=1000`, `LoadClamp=3950`. Unit slip/load ini tidak dinyatakan pada schema, sehingga disimpan mentah. Jangan otomatis mengubah 49.5 menjadi derajat atau 1000 menjadi newton tanpa bukti loader.

Ada pula `TireMod_FrictionScale` dengan 10 pengecualian per mobil. Misalnya ordinal 434: front 0.925, rear 0.95. Ini input tambahan yang mudah hilang jika hanya mengekspor compound generik.

### Contoh rantai mobil nyata dalam database: Toyota 2000GT 1969

R1/U1 `Data_Car.Id=247, MediaName=TOY_2000GT_69`:

- `List_UpgradeCarBody.Id=247000`, `CarBodyID=247000`; weight row `Mass=1156.661`, `CMHeight=0.2539`, `CMBackFront=0.51`, `CMLeftRight=0.5`.
- `Data_Car.CurbWeight=11.56661`, berbeda faktor 100 dari `Mass`. Ini bukti praktis bahwa angka DB tidak mempunyai satu sistem unit seragam yang boleh diasumsikan.
- `Data_CarBody.ModelWheelbase=2.339183`, model front/rear track outer 1.515155/1.567897. Nilai raw; satuan belum dibuktikan melalui loader.
- Engine upgrade stock menunjuk `EngineID=1`, `EngineMass-kg=161`, `MomentInertia=0.1149`. Camshaft stock `RedlineRPM=7000`, `TorqueCurveMaxRPM=8500`, `NumRPMEntriesArray=86`, full-throttle curve ID 1, zero-throttle ID 2. Kurva 1 `TorqueScale=176.254`, `NumTorqueValues=86`; field torque scale sendiri tidak berlabel unit.
- Transmisi stock `FinalDriveRatio=4.38`, `GearRatio0=-3.168`, rasio 1–5 = 3.41, 1.64, 1.18, 1.0, 0.84. `NumGears=6` pada tabel transmisi sementara `Data_Car.NumGears=5`; ini konsisten dengan reverse dihitung dalam data transmisi, namun konvensi loader belum diverifikasi.
- Suspensi front/rear IDs 247000/247100: `DefSpringRate=37.2555/35.7945`, bump 1.9726/1.8953, rebound 3.9453/3.7905, ride height 0.1531/0.1531. `StaticCamber=-0.5/0`.
- Compound stock ID 5. `SteerMaxAngle=35`, filtered 29, turning/straighten rates 70/140; `GameTorqueScale=0.7625`, `GameDragScale=1`.

Rantai lengkap disimpan di `summary_evidence.json -> car_chain`, sehingga contoh dapat direproduksi dan tidak bergantung pada klaim nama kolom saja.

## Handling: lapisan pengemudi, assist dan modifikasi game

Pada kedua edisi, `Media/Physics/PhysicsSettings.ini` berisi nilai berikut secara identik:

| Parameter persis | Nilai file | Batas interpretasi |
|---|---:|---|
| `CarPhysicsUpdateHz` | 359 | Nilai konfigurasi; bukan pengukuran tick runtime |
| `CarGravityScale` / `AirbornGravityScale` | 1 / 1.25 | Faktor berbeda ketika airborne; rumus penggunaan tidak dibuktikan |
| `UseVertexNormals` | TRUE | Flag; bukan pembuktian format `.col` |
| `ABSOffBrakingFrictionScale` | 1.05 | Modifikasi grip rem saat ABS off menurut nama field |
| `FuelConsumptionScale` | 0.6 | Skala konsumsi global |
| `SlidingInstability\IsOn` | true | Parameter instabilitas sliding ada dan diaktifkan di file |
| `WindInstability\IsOn` | false | Submodel ini dinonaktifkan dalam file |
| `SteeringWheelFilter\ControlScale0/1` | 1.5 / 3 | Ada filter steering wheel menurut speed |
| `GimbalLock\GimbalLockOn` | true | Koreksi orientasi tambahan tersedia |
| `ControllerDelays\AccelDelaySpeed` / `BrakeDelaySpeed` | 5 / 20 | Rate/delay input raw; unit belum dipastikan |
| `HighSpeedDragSpeed0MetersSec` / `HighSpeedDragSpeed1MetersSec` | 114 / 122.9 | Nama field eksplisit meters/sec |
| `HighSpeedDragScale0/1` | 1 / 1.5 | Modifikasi drag kecepatan tinggi |

Selain itu ada `FrictionTorqueMod` dengan kurva berbeda `WithAssists`/`NoAssists`, countersteer rates, pembatas/penemuan peak steer, TCS berdasarkan drive type, torque scale tabrakan yaw/pitch/roll, pengaruh engine torque terhadap body roll, rollover recovery, serta drafting yang menurunkan drag/downforce dengan parameter berbeda untuk kendaraan depan/belakang.

**Inferensi yang kuat:** handling efektif merupakan hasil parameter kendaraan, ban, track, pilihan tune dan control/assist layer sekaligus. Menggunakan berat, horsepower dan tire width dunia nyata saja tidak menghasilkan replika handling FM3.

`ControllerFFB.ini`: inertia/friction scale 0; damper 0.1; spring 0.5; `DynFFBScale=1`; ada pengurangan spring menurut rear slip. FFB dan controller rumble harus diperlakukan sebagai keluaran/input filter terkait handling, bukan koefisien grip ban itu sendiri.

## Peta input track

| Lapisan | Lokasi | Bukti/fungsi |
|---|---|---|
| Katalog layout | DB `Tracks` | `MediaName`, `RibbonIndex`, `ReverseIndex`, `Length`, start/finish, drift scalar, environment, flags |
| Contact/collision world | `Media/Tracks/<track>/Ribbon_xx/*_track_xx.col` | Binary collision files, mis. LagunaSeca 2.742.272 byte; layout internal belum didekode |
| Permukaan global | `Media/Physics/surfaceTypes.xml` | 53 surface types, collision category pairs, friction, bump, spring, penalty, FFB/noise |
| Objek collision | `Media/Physics/CollObjects.xml` dan `Tracks/.../CollObjs.xml` | Definisi benda dan penempatan per ribbon |
| Ribbon/AI geometry | `Media/AI/Tracks/*.geo` | Self-describing MLP: waypoint XYZ, normal XYZ, left/right wall/curb Chi, optimal Chi |
| Segment/curvature | `.seg` | Start, apex, end, length, peak curvature, turn type |
| Line AI | `.irt` | Track name, columns, segment state, line int/float arrays; semantik internal belum lengkap |
| Pit paths | `.pit` serta `TrackPittingZones`, `PittingProfiles`, `StartGridPositions` | Pit spline, masuk/keluar/abort/parking, merge waypoint, limit speed |
| Grafik/atmosfer | `TrackSettings.xml`, track `bin.zip`, `.pvs`, textures | Mayoritas setting render, lighting, wind visual dan visibility; jangan otomatis disamakan dengan grip surface |

Untuk Laguna Seca, `Tracks.id=0`: `MediaName=LagunaSeca`, `RibbonIndex=0`, `ReverseIndex=0`, `Length=3602`, `NumberOfTurns=11`. `Length` tidak berlabel unit pada schema. File `Media/AI/Tracks/lagunaseca_00.geo` menyatakan 1.807 waypoint dan daftar offset. Contoh:

- `iLength:int32:1:1` offset 508, big endian, hasil 1807.
- `fWaypointX/Y/Z` masing-masing 1807 float, offsets 513/7741/14969.
- Waypoint pertama = (-354.7276001, 271.7150574, 1.6025959).
- `fNormalX/Y/Z`, `fLeftWallChi`, `fRightWallChi`, `fChiOptimal`, `fLeftCurbChi`, `fRightCurbChi` semuanya array 1807 float.
- `.seg` mempunyai 29 segment. Angka 1807 pada `iTrackLength` berkorespondensi dengan waypoint count, sehingga tidak boleh dianggap otomatis panjang meter.

Nilai `fNormalX/Y` dapat melebihi 1; jangan menganggap nama `Normal` selalu unit surface normal. Koordinat dan frame AI juga belum dibuktikan identik dengan frame model/collision.

Contoh permukaan dari XML, nilai mentah:

| Surface | FrictionScale | OffRoadness | Bumpiness | Penalty |
|---|---:|---:|---|---|
| Asphalt | 1 | 0 | NoiseType None | true |
| Grass | 0.8 | 1 | HeightGrid, Frequency 1.5, Scale 0.02 | true |
| Dirt | 0.8 | 1 | HeightGrid | true |
| RumbleStrip | 1 | 0 | SinWave, Frequency 0.73, Scale 0.05, Offset 0.01 | false |
| SlowGrass | 0.75 | 1 | HeightGrid, Scale 0.015 | true |

Kolom Penalty menyalin `IsPenaltySurface` mentah. `Asphalt=true` tidak berarti seluruh aspal sirkuit otomatis mendapat penalti; kondisi pemakaian flag dalam executable belum dipastikan. Selain skala grip, tiap permukaan dapat memiliki `HeatTireScale`, off-road peak slip, gesekan bergantung velocity, spring response, rumble/steer torque, damage scale, dan collision noise. Collision pasangan Car–HardWorld misalnya `FrictionCoefficient=0.7`, `Elasticity=0.05`; itu berbeda lapisan dengan `Asphalt/FrictionScale=1`. Nilai negative `Elasticity` pada beberapa pasangan harus diperlakukan sebagai konstanta engine, bukan langsung koefisien restitusi buku fisika.

**Yang masih belum diketahui:** pemetaan ID material/triangle pada `.col` ke surface XML, skala dan endian semua subbagian `.col`, algoritma query/penetration/friction/normal, deformasi tyre, serta mesh detail yang benar-benar digunakan tiap mode.

## Apa yang benar-benar berbeda pada UC

Pemeriksaan menggunakan semua baris tabel bersama, bukan hanya dua sampel:

1. Seluruh `Data_Car`, `Data_CarBody`, `Data_Engine`, `Data_Drivetrain` untuk key lama tidak berubah. Seluruh existing suspension/antiroll/aero/tire curves tidak berubah. UC menambah rows untuk content baru.
2. `List_TorqueCurve`: 17 nilai pada 17 row berubah dengan maksimum beda absolut `9.992007221626409e-16`; semuanya menjadi float32 yang sama. Ini konsisten dengan artefak presisi ekspor, bukan bukti rebalance. UC juga menghapus 16 curve ID lama yang tidak direferensikan oleh `List_UpgradeEngineCamshaft` reguler. Asumsi mengenai tipe numerik runtime tetap belum dibuktikan.
3. Sebelas camshaft rows berubah hanya `ManufacturerID` 81→409, bukan curve/RPM. `List_Wheels` mempunyai perubahan nama kosong→literal `NULL` pada 396 rows dan pembersihan ID metadata.
4. `ControllerLayouts` ID 10 Gas/Brake ditukar. Kamera mobil ID 1128 berubah. Layout Nürburgring F1 ID 33/34 baru pada `Tracks` UC, tetapi data pendukung pitting/grid sudah ada pada DB reguler: `TrackPittingZones.SpeedLimit` 60→20, serta merge waypoint berubah dari -1 ke nilai konkret. Unit SpeedLimit belum ditetapkan. UC patch secara eksplisit menghapus lalu memasok ulang row pitting/grid/split tertentu untuk ID itu.
5. Tiga file kamera Amalfi berubah di common Disc2 track ZIP, dengan tambahan thumbnail. Geometri track/common AI tetap sama menurut pembandingan yang dilakukan.
6. 307 XML/`.col` di `Media/Tracks` Disc1 dan semua 634 file dalam `Media/AI` Disc1 identik SHA-256. 311 common car ZIP Disc1 identik pada daftar member, CRC, ukuran dan compression type. Perbandingan CRC ini dibedakan dari hashing penuh ZIP.

Karena `default.xex` tidak identik dan tidak didisassembly sampai persamaan solver, kesimpulan paling kuat adalah **parameter handling dasar existing cars/ban/permukaan hampir seluruhnya dipertahankan, UC menambah content dan koreksi pendukung; perubahan internal solver belum diketahui**.

## Hash identifikasi penting

SHA-256 lengkap tercatat pada `evidence.json -> core_comparison`:

| File | Reguler | UC |
|---|---|---|
| `default.xex` | `076acb4e89fa8dbeec632e435fccc50ec7e22460f70778ceeb373aab59a8bac9` | `aa15372c13bc4c899b5ef90a1cfb5634d389b0a3620cc9715f6023d61a9b8742` |
| `Media/DB/gamedb.slt` | `b6c8210596d71d542b75230b65f525277a9c709ad515baef35a0d06412eff5c3` | `c6baa231cb655dc24459dfd39da1a620c5a50f600cdd0ea4fd1969a4c548a48e` |
| `PhysicsSettings.ini` | `c185179bde991fd2336a29c5ce0ba7b364f56e64e3a1c8f76df4b3cc6d159d1c` | Sama |
| `surfaceTypes.xml` | `27b7387c368d65d98451983b53a1e76afbd8515303a26354ac4b6099227114de` | Sama |

`default.xex` R1/U1 masing-masing berukuran 13.152.256 / 13.250.560 byte. Hash mengidentifikasi file yang diteliti, bukan mengautentikasi rilis atau membuktikan title-update state. STFS block SHA-1 diperiksa untuk blok yang dibaca; signature Microsoft dan seluruh blok paket tidak diaudit.

## Unit, kepastian, dan data yang masih dibutuhkan

**Terbukti langsung:** keberadaan file/kolom/row, nilai yang disebut, relasi ID yang dapat diikuti, file equality, XML/SQL terdecode dengan CRC valid, MLP field/type/offset yang eksplisit.

**Inferensi:** fungsi suatu parameter dari namanya, struktur load-dependent tyre curves, mass-block untuk inersia, kurva zero throttle untuk engine braking, dan unit yang hanya terlihat masuk akal secara numerik. Inferensi ini tidak dipromosikan menjadi fakta solver.

**Belum diketahui:** integrator/time-step aktual, frekuensi runtime, persamaan combined slip/load transfer/damping, urutan assist, normalisasi unit internal, rule merge/runtime override lengkap, kode collision, serta respons subjektif atau waktu putaran. Tidak ada game dijalankan untuk mengujinya.

Untuk merekonstruksi handling, diperlukan set part/tune aktual, kendaraan lengkap termasuk engine/drivetrain swap, kurva ban/temperatur/wear/pressure state, globals/assist/control mode, geometri collision berikut surface IDs dan objects, keadaan awal/massa fuel/damage, dan implementasi solver. Rating `HandlingRating`, `PerformanceIndex`, `SimLatGees` dan `SimTopSpeed` adalah kolom hasil/penilaian yang patut dibedakan dari input model. `PI.xml` sendiri berisi lintasan sintetis 15 segment dengan straight length/radius/angle; tidak boleh dipakai menggantikan geometri track sebenarnya.

## Berkas hasil dan reproduksi

- `cars_map.csv`: seluruh 925 baris gabungan regular/UC, identitas internal, content IDs, flags, paket Disc2 yang mengaktifkan ID berdasarkan SQL, serta stock engine/body/drivetrain/tire/suspension IDs, massa/CG/geometri, RPM/curve IDs, gear ratios, spring/damper/alignment depan dan belakang.
- `tracks_map.csv`: seluruh 254 baris gabungan regular/UC, nama internal/layout/reverse, flags dan aktivasi Disc2.
- `evidence.json`: inventaris sumber, semua schema/table counts/two-row samples, hash file inti.
- `db_comparison.json`: per-key row changes/additions/removals semua tabel.
- `decoded_assets.json`: carattribs contoh, seluruh SQL dan isi empat merge DB, header/offset/nilai MLP, seluruh parameter permukaan.
- `summary_evidence.json`: integrity checks, comparison summary, contoh rantai Toyota, hash carattribs terdecode, dan common Disc2 track hashes.
- `disc2_packages.json` dan `disc2_zip_inventory.json`: metadata STFS yang dikoreksi, daftar nested files dan ZIP central-directory. Ukurannya adalah metadata inventaris, bukan dump aset.
- `track_physics_file_comparison.json`, `ai_file_comparison.json`, `car_zip_comparison.json`: cakupan equality yang dapat diaudit.

Script lokal: `research.py`, `compare.py`, `package_zip.py`, `decode_assets.py`, `finish_evidence.py`. Decoder/helper bersama berada di `../shared/`. Penamaan script penelitian tidak mengubah fakta bahwa game/executable guest sama sekali tidak dijalankan. Tidak ada klaim yang memerlukan hasil benchmark atau akses internet.
