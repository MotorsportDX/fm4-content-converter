# FM2 — peta fisika dan handling dari Disc 1 + Bonus Disc

Catatan repo: laporan dan source analisis disertakan. JSON/CSV/schema, hasil ekstraksi aset, disassembly dan binary yang disebut di bawah tetap lokal dan diabaikan Git; lihat [metode reproduksi](../METHODS.md).

Riset statis offline, 20 Oktober 2026. Sumber dibaca dari `D:\Data\FM2\USA`; tidak ada game, emulator, installer, executable game, SQL patch game, atau koneksi jaringan yang dijalankan. Python hanya membaca file, SQLite dalam mode read-only, ZIP, metadata STFS, dan format array MLP. Hasil turunan disimpan di folder laporan ini. SHA-1 blok payload STFS yang dibaca diperiksa oleh parser lokal; ini bukan verifikasi tanda tangan Microsoft.

**Kesimpulan:** FM2 menyediakan sebagian besar parameter pembentuk handling sebagai data terbaca: massa/distribusi massa, mesin dan kurva torsi, transmisi/diferensial, suspensi, ban beserta kurva slip dan pengaruh beban/suhu/tekanan/camber/keausan, aerodinamika, bantuan pengemudi, filter input, collision mobil, dan material permukaan track. Parameter tersebut jauh lebih kaya daripada angka rating handling di UI. Solver integrasi, persamaan penggabungan gaya, dan implementasi collision tetap berada di kode game; membaca data saja belum merekonstruksi hasil simulasi persis.

Label bukti: **Terkonfirmasi** = byte, field, nilai, atau relasi yang dibaca langsung; **Inferensi** = penafsiran berdasarkan nama dan struktur data; **Belum diketahui** = perlu analisis kode lanjutan atau validasi yang belum dilakukan. “Terkonfirmasi” pada parameter tidak berarti eksekusi parameter tersebut di runtime sudah teruji.

## 1. Sumber dan cakupan

| Bagian | Lokasi relatif dari `D:\Data\FM2\USA` | File fisik | Ukuran byte | Isi penting |
|---|---|---:|---:|---|
| Disc 1 | `Forza Motorsport 2 (USA)` | 2.344 | 5.026.196.867 | `default.xex`, SQLite, INI/XML fisika, car ZIP, collision dan AI track |
| Bonus Disc | `Forza Motorsport 2 (USA) (Bonus Disc)` | 13 | 589.843.653 | Installer XEX, 8 paket PIRS/STFS, title update PIRS, INI installer |

`Media/DB/gamedb.slt` memiliki 169 tabel dan lolos `PRAGMA integrity_check = ok`. `Data_Car` memiliki 310 baris; 310 ZIP mobil masing-masing memiliki `Physics/MAXData.xml`. Ini hitungan definisi/aset, bukan jaminan 310 mobil tersedia langsung di menu: empat baris sudah bertanda `IsDLC=1`, dan `StockGarage` hanya memiliki 303 baris.

`Tracks` memiliki 50 baris, 47 berstatus `Active=1`, dalam 12 lingkungan: LagunaSeca, MapleValley, Mugello, NewYork, Nurburgring, RoadAtlanta, Sebring, Silverstone, SunsetInfield, Suzuka, TestTrackinfield, Tsukuba. Tiga baris tidak aktif ialah TuningTrack dan dua DebugTrack. Ada 32 file `.col`; beberapa layout/reverse memakai geometri bersama. Jangan menyamakan hitungan `.col`, lingkungan, dan layout.

Artefak pendamping:

- `evidence.json`: inventori, hash, semua schema/kolom, contoh nilai, parameter, metadata paket, hasil parsing.
- `schema.txt`: SQL schema dan jumlah baris semua tabel base.
- `cars_physics_map.csv`: 310 mobil, stock engine/compound/suspension/anti-sway, massa dan pusat massa.
- `tracks_map.csv`: 50 baris track base.
- `surfaces.csv`: 38 kategori material beserta parameter terpilih.
- `bonus_cars_map.csv`, `bonus_tracks_map.csv`: 39 car IDs baru dan 5 track IDs baru dalam bonus.
- `bonus_inventory.json`: seluruh entry STFS dan ZIP yang diperiksa, termasuk patch DB dan SQL.
- `track_geometry_summary.csv`: 47 file `.geo` base yang berhasil didekode dari header MLP.
- `bonus_metadata/`: hanya metadata SQL/SQLite/XML terpilih hasil ekstraksi; aset grafis/audio besar tidak disalin.

## 2. Aliran data handling

Peta relasi terkonfirmasi oleh schema, nilai ID, dan SQL resmi di dalam paket bonus:

```text
Data_Car.Id (= Ordinal pada tabel upgrade)
 ├─ List_UpgradeWeight[IsStock/upgrade] → Mass, CM*, BlockDim*
 ├─ List_UpgradeEngine → Data_Engine.EngineID
 │   └─ List_UpgradeEngineCamValves → List_TorqueCurve
 │       + Block/FuelSystem/Ignition/Exhaust/Intake/Turbo/CSC/DSC/Intercooler
 ├─ Transmission / Clutch / Flywheel / Driveline / Differential
 ├─ List_UpgradeSpringDamper → List_SpringDamperPhysics depan + belakang
 ├─ List_UpgradeAntiSway → List_AntiSwayPhysics depan + belakang
 ├─ List_UpgradeTireCompound → List_TireCompound
 │   ├─ lateral + longitudinal → List_TireFrictionMultiCurve → List_TireFrictionCurve
 │   └─ suhu/tekanan/camber/wear/speed/aligning torque → List_TireAffectCurve
 ├─ lebar ban / ukuran rim / brand-compound / TireMod_FrictionScale
 ├─ body aero + bumper/wing → List_AeroPhysics
 └─ MediaName → cars/<MediaName>.zip → Physics/MAXData.xml

Hasil konfigurasi tersebut + tuning tersimpan + assists/filter input
 + track collision/material + surfaceTypes.xml + PhysicsSettings.ini
 → dikonsumsi kode solver game.
```

Semua 310 `Data_Car.Id` berhasil dipetakan ke satu stock weight, stock engine, dan stock tire compound dalam CSV tanpa pasangan kosong. SQL `1000_execute.sql`/`1100_execute.sql` pada paket Special Edition/Pre-order secara eksplisit melakukan join `Data_Car.Id = List_Upgrade*.Ordinal`, memperkuat relasi ini; bukan sekadar dugaan dari kesamaan angka.

### Mobil: input yang diperlukan

| Domain | Data/kolom utama | Mengapa relevan terhadap handling |
|---|---|---|
| Massa dan distribusi | `List_UpgradeWeight` (887): `Mass`, `InitialMass`, `CMHeight`, `CMBackFront`, `CMLeftRight`, `BlockDimX/Y/Z`; `MassDiff` part | Inferensi: massa, pusat massa, dan representasi distribusi massa menentukan akselerasi, transfer beban, rotasi. Formula inertia dari block belum dibuktikan. |
| Geometri | `Data_Car`: `Length-m`, `Width-m`, `Height-m`, `Wheelbase-m`, `FrontTrack-m`, `RearTrack-m`; `MAXData.xml` | Jarak sumbu/track, titik referensi model, dimensi collision dan bola collision. Jangan pakai mesh tampilan sebagai satu-satunya input fisika. |
| Mesin | `Data_Engine` (321), `List_TorqueCurve` (1.650), `List_UpgradeEngineCamValves` (824) | Mesin punya inertia, konsumsi bahan bakar, torque steer; cam mempunyai RPM, dua curve ID untuk zero/full throttle, dan jumlah sampel. |
| Drivetrain | transmisi (876), differential (799), clutch, flywheel, driveline | Rasio gigi/final drive, inertia, waktu perpindahan, limited-slip accel/decel/clamp dan distribusi torsi. |
| Suspensi | spring/damper (1.452) dan anti-sway physics (1.452) | Ride height/travel, spring/bump/rebound, bump stop, pivot, camber gain, toe, caster, axle inertia. Ada tipe `INDEPENDANT` dan `SOLID` (ejaan asli). |
| Ban | compound (7), friction multicurve (16), friction curve (32), affect curve (96) | Slip lateral/longitudinal dipisah, ada dependensi load dan modifier termal/tekanan/camber/wear. |
| Rem | `List_UpgradeBrakes` (895) | Bias, torque slider, friction scale, ABS release threshold dan duration, handbrake, kerusakan. |
| Aero | `Data_Car.BodyAero*`, `List_AeroPhysics` (358) | Drag longitudinal/lateral/vertical, downforce depan/belakang, zero-downforce angle, slider drag/downforce. |
| Pengemudi/kontrol | `Data_Car.Steer*`, `AssistsTCS*`, `AssistsSTM*`; INI global | Batas steering, steering yang bergantung kecepatan, countersteer, TCS/STM, pemetaan input. Ini bagian penting “rasa handling”. |
| Gameplay/penyetelan | `GameTorqueScale`, `GameDragScale`, `TireMod_FrictionScale`, tuning per profil | Parameter produksi tidak seluruhnya sama dengan spesifikasi dunia nyata. Perlu menyimpan override dan tuning untuk reproduksi. |
| Kerusakan | `List_DamageModDef` (10), field damage IDs, `PhysicsSettings.ini` | Batas impact, modifier kondisi, probabilitas, serta parameter pengaruh kerusakan mesin/drivetrain/suspensi/aero. |

`NewProfile_Career_Garage` menyimpan pilihan part dan `Tuning_*` seperti tekanan depan/belakang, gear ratios, camber/toe/caster, spring/ride height/damping, downforce, brake balance/pressure, diff accel/decel, center torque. Tabel ini kosong pada master DB karena template; bukan data mobil pemain yang sudah terisi.

### Contoh nyata satu konfigurasi stock

Mobil `Data_Car.Id=247`, `MediaName=TOY_2000GT_69`:

- `Wheelbase-m=2.329`, front/rear track masing-masing `1.3`; `FrontWeight-pct=0.5`.
- `List_UpgradeWeight.Id=247000`: `Mass=1152.598022`, `CMHeight=0.3`, `CMBackFront=0.5`, `CMLeftRight=0.5`, `BlockDimX/Y/Z=1.76/0.7565/4.3838`.
- EngineID `1`, `EngineMass-kg=286`, `Disp_cc=1988`, `Bore-m=Stroke-m=0.075`, `MomentInertia=0.2176`.
- Stock cam: `RedlineRPM=7000`, `StallRPM=800`, `TorqueCurveMaxRPM=8500`, `NumRPMEntriesArray=86`, full-throttle curve `1`, zero-throttle curve `2`.
- TorqueCurve `1`: `TorqueScale=176.253998`, `NumTorqueValues=86`, `v0=0.5725`, `v50=1.0`, `v84=0.629647`, `v85=-2.63`. Titik terakhir negatif harus dipertahankan; tidak boleh diasumsikan kesalahan lalu dibuang. Makna engine limiter/overrun pada titik tersebut masih inferensi.
- Transmisi `247000`: `FinalDriveRatio=4.375`, `GearShiftTime=0.2082`, `GearRatio0=-3.631`, gear1 `3.143`, gear2 `1.636`, gear3 `1.179`, gear4 `1`, gear5 `0.844`, gear6/7 `-1`. `NumGears=6` **tidak otomatis berarti enam gigi maju**, karena ada reverse pada index 0 dan sentinel negatif.
- Suspensi depan ID `1`, belakang ID `5`: spring rate keduanya `41.9744`, bump `1.6197`, rebound `3.2394`; front ride height `0.1113`, rear `0.1513`; front static camber `-0.5`, rear `0`; caster `5`.
- `SteerMaxAngle=35`, `SteerMaxAngleFiltered=29`, `GameTorqueScale=0.83`, `GameDragScale=0.97`.

**Batas unit:** unit yang eksplisit di nama kolom (`-m`, `-mm`, `-in`, `-kg`, `RPM`) boleh dipakai. Kolom lain dicatat sebagai nilai mentah. `Data_Car.CurbWeight=11.52598` sedangkan stock `Mass=1152.598022`, berbeda sekitar faktor 100; jangan labeli `CurbWeight` langsung kilogram. `FrontWeight-pct=0.5` juga berupa fraksi, bukan angka `50`. Unit suhu, tekanan, spring rate, damping, inertia, serta aturan konversi runtime belum terbukti dari data yang dibaca.

## 3. Ban: bukti paling langsung tentang karakter handling

Nama compound yang tersedia ialah `L0_Classic`, `L0_Production`, `L0_ProductionLow`, `L1_DRY`, `L2_DRY`, `L3_DRY`, `L3_Race`. ID tidak berurutan: 1, 3, 4, 5, 6, 7, 8.

`List_TireCompound` menghubungkan lateral dan longitudinal ke dua multicurve berbeda. Contoh compound `1` memakai multicurve `1` dan `2`. Multicurve `1` mempunyai `MaxSlip=49.5`; multicurve `2` mempunyai `MaxSlip=1.1`. Keduanya memiliki `MinLoadCurve=0`, `MaxLoadCurve=1000`, `LoadClamp=3950`, dan dua curve ID. **Terkonfirmasi:** data membedakan slip lateral/longitudinal dan menyediakan dua kurva terkait load. **Inferensi:** kode melakukan interpolasi atau pemilihan berdasarkan load. Algoritme persis, unit load, dan normalisasi slip belum terbukti.

Friction curve `1` mempunyai 100 sampel, `FrictionScale=1.2`, `v0=0`, `v16=1`, `v50=0.946141`, `v99=0.853448`. Bentuk data naik menuju puncak lalu berkurang setelah puncak. Ini mendukung interpretasi transisi grip ke sliding; tidak cukup untuk menyebutnya model Pacejka atau mengklaim formula tertentu.

Compound juga punya modifier yang bernama jelas: `AffectCurveTempAffectFrictionID`, `PressureAffectFrictionID`, `CamberAffectLatFrictionID`, `CamberAffectLongFrictionID`, `WearAffectFrictionID`, `SpeedAffectFrictionID`; aligning torque memiliki modifier slip angle, slip ratio, dan load. Nilai termal memuat `AirTempDiffHeatTransfer`, `OverheatedTemp`, `FrictionHeatTransfer`, `RollResistanceHeatTransfer`, `SlidingFrictionHeatTransfer`, `PressureChangeSpeed`, `FrictionWear`, dan pemanasan luar ban akibat camber.

Curve pengaruh suhu `AffectCurveID=1`: 11 titik pada input `0..300`, `OutputScale=1`, `v0=0.95`, `v5..v7=1`, `v10=0.95`. Ini bukti tabel sensitivitas suhu, bukan bukti satuan Celsius/Fahrenheit atau formula evolusi suhu.

Terdapat pula override per mobil: base `TireMod_FrictionScale` memiliki 9 baris; car `434` memakai front `0.925`, rear `0.95`. Bonus December menambah car `633` (`AUD_SportQuattro_DLC2`) dengan front `0.95`, rear `1`. Karena itu meniru spesifikasi ban umum saja akan melewatkan koreksi handling per mobil.

## 4. Global physics, steering, assists dan FFB

Sumber langsung: `Media/physics/PhysicsSettings.ini`.

| Parameter | Nilai | Penafsiran yang dibatasi |
|---|---:|---|
| `CarPhysicsUpdateHz` (baris 57) | 239 | Frekuensi yang dikonfigurasi, bukan pengukuran cadence runtime. Jangan dibulatkan menjadi bukti 240 Hz. |
| `Temp/Pressure/Wear/CamberAffectFrictionScale` | masing-masing 1 | Modifier tersebut disediakan/diaktifkan pada konfigurasi ini. |
| `CarGravityScale`, `AirbornGravityScale` | 1, 1 | Ada kontrol skala gravitasi. Nilai gravitasi absolut tidak tertulis di sini. |
| `PerTireOffGroundGravityScale` | 1.02 | Parameter koreksi kondisi roda terangkat; formula penerapannya belum diketahui. |
| `ABSOffBrakingFrictionScale` | 1.05 | Bantuan/konfigurasi pengereman dapat mengubah skala friction. |
| `TCSFullSteerSlipScaleRWD/FWD/AWD` | 1 / 1.16 / 0.91 | Kontrol slip berbeda menurut drivetrain. Versi AI memiliki angka terpisah. |
| `NormRearSlipAngleToCountersteer`, `SteerDefCountersteerRate` | 50, 200 | Ada pengolahan countersteer di layer kontrol. |
| `SlidingInstability\IsOn`, `WindInstability\IsOn` | true, true | Ada parameter tambahan instability; bukan bukti simulasi cuaca lengkap. |
| `BrakeInputScale` input→output | 0→0; 0.4→0.4; 0.999→0.57; 1→0.85 | Kurva input rem tidak identik dengan raw trigger. Interpolasi runtime belum dibuktikan. |
| `ControllerDelays` accel/brake/handbrake | 5 / 20 / 12 | Parameter smoothing/delay input, satuan belum terkonfirmasi. |

Drafting memiliki jarak/fade dan skala drag/downforce. Contoh “following formula result 1”: drag front/body/rear `0.72`, front downforce `0.47`, rear downforce `0.61`; leading drag `0.96`, leading front/rear downforce `0.99/0.95`. Ini menunjukkan data slipstream memengaruhi drag dan aero balance, bukan hanya bonus kecepatan tunggal.

`Media/ControllerFFB.ini`: `DynFFBScale=1`, `DynFFBMaxForce=1`, `SpringScale=0.5`, `DamperScale=0.1`, `InertiaScale=0`, `FrictionScale=0`, plus scaling berdasarkan speed/rear slip. Surface XML juga mempunyai `SteerTorque`. **Inferensi:** rasa wheel merupakan gabungan feedback dinamis, spring/damper, dan permukaan. Tidak ada pengujian wheel atau latency hardware.

`AISkills`, `AIRubberbands`, dan `TrackSpecificAI` menyimpan torque boost/cut dan assist/skill AI. Variabel ini penting bila membandingkan lap time AI; tidak boleh dicampur dengan model fisika pemain tanpa memeriksa konsumennya di kode.

## 5. Track: data yang diperlukan dan yang berhasil dibuka

| Lapisan | Sumber | Yang terbaca / status |
|---|---|---|
| Identitas/layout | `Tracks` | MediaName, RibbonIndex, ReverseIndex, Length, grid/flying start IDs, content/status |
| Road/world collision | `Media/tracks/<track>/Ribbon_XX/*.col` | 32 file base; header/hash/ukuran dicatat. Mesh topology, triangle material, acceleration tree belum didekode. |
| Material fisika | `Media/physics/surfaceTypes.xml` | 38 kategori; friction, heating, bumpiness, restitution, springiness, steering torque, damage, penalty |
| Objek movable | `CollObjs.xml` + `physics/CollObjects.ini` | PhysicsType, GraphicsName, posisi/orientasi; bola collision dan sphere/block mass per tipe |
| Jalur/ribbon AI | `Media/AI/Tracks/*.geo` | Header MLP memberikan field typed/offset; 47 file didekode big-endian dan batas array diperiksa |
| Segmentasi tikungan | `.seg` | Start/apex/end, segment length, peak curvature, turn type |
| Pilihan garis | `.irt`, Level*/`.bin`, SegmentProfiles | Metadata dan array terbaca; interpretasi polynomial/line format detail belum direkonstruksi |
| Pit/grid/race | `.pit`, `TrackPittingZones`, `StartGridPositions`, `FlyingStartPositions`, `SplitPoints` | Spline/point pit, grid position/heading, merge waypoints dan speed limit |
| Tampilan | TrackSettings, bin.zip, pvs, crowd, cameras | Kebanyakan render/lighting/visibility. `TrackSettings` mengandung wind untuk tampilan; hubungan ke force angin fisik tidak dibuktikan. |

Contoh Laguna Seca:

- DB track ID `0`, `RibbonIndex=0`, `ReverseIndex=0`, `Length=3589` (unit tidak ditulis pada schema).
- `lagunaseca_track_00.col`: 2.738.176 byte; header awal `000000090000000b...`.
- `.geo`: `iLength=1807`, `iType=0`; 1.807 sampel `fWaypointX/Y/Z`, `fNormalX/Y/Z`, `fLeftWallChi`, `fRightWallChi`, `fChiOptimal`, `fLeftCurbChi`, `fRightCurbChi`.
- Di `.geo`, `fWaypointX` mulai offset 513, Y 7741, Z 14969. Titik awal `(-354.727600, 271.715057, 1.602596)`. Panjang polyline terbuka yang dihitung = `3611.115006` unit koordinat; rata-rata jarak titik `1.999510`; penutup titik terakhir-ke-awal `1.999734`.
- `.seg`: 29 segmen, `iTrackLength=1807`. **iTrackLength di file ini adalah hitungan waypoint yang sama dengan .geo, bukan panjang DB 3589.**
- `.irt`: `trackName=lagunaseca_00`, `m_iColumns=5`, arrays line_int/line_float.
- `.pit`: field `pitentrancespline`, `pitexitspline`, `pitin`, `pitout`, `pitabort`, 12 pitparkin dan 12 pitparkout. Susunan koordinat `.pit` tampak berbeda dari `.geo`; jangan menggabungkan tanpa transformasi sumbu yang diverifikasi.

Kolom `fNormal*` tidak boleh langsung dianggap unit surface-normal. Nilai awal `(3.610886,-2.760620,0.003923)` mempunyai besar lebih dari 1; mungkin vektor basis/ribbon berskala. Semantik `Chi` juga memerlukan pembacaan kode. Sumber ini berguna untuk jalur/layout, tetapi belum menggantikan road collision `.col` yang dibutuhkan untuk wheel contact dan detail permukaan.

Contoh material terkonfirmasi (angka mentah, bukan koefisien hasil gaya final):

| Surface | FrictionScale | HeatTireScale | Bump amplitude | Frequency |
|---|---:|---:|---:|---:|
| Asphalt | 1 | 1 | 0 | 0 |
| Dirt | 0.8 | 0.1 | 0.04 | 3.5 |
| Grass | 0.8 | 0.1 | 0.04 | 3.5 |
| RumbleStrip | 1 | 1 | 0.04 | 2 |
| Gravel | 0.8 | 0.1 | 0.06 | 3 |
| SlowAsphault | 0.6 | 1 | 0 | 0 |
| ConcreteNoPenalty | 1.015 | 1 | 0 | 0 |

Nama `Asphault` dieja demikian dalam file asli. Ada parameter wet friction dan wet peak slip dalam file. **Keberadaan field “Wet” tidak membuktikan mode hujan/track basah dimainkan dalam FM2.**

`CollObjs.xml` LagunaSeca memakai `PhysicsType="BrakeMarker"`, misalnya Obj0 di `(-457.431152,4.383246,6.248043)` plus 3 axis orientasi. XML ini mengandung koma di antara atribut (`y="...", z="..."`), sehingga tidak valid untuk parser XML standar tanpa normalisasi eksplisit. Jangan menganggap parse failure berarti tidak ada data collision. `CollObjects.ini` punya contoh Cone: 7 collision spheres, 5 sphere masses, `Misc\SurfaceId=12`; mapping indeks material ke urutan XML masih perlu konfirmasi kode.

## 6. Bonus Disc: paket, patch, serta perbedaan dari base

Semua delapan paket berada di `Forza Motorsport 2 (USA) (Bonus Disc)/content/0000000000000000/FFED2000/FFFFFFFF/`. Identitas berikut dibaca dari header STFS, bukan ditebak dari nama file hash.

| Nama metadata | Awal nama file | Konten riset |
|---|---|---|
| Pre-order car | `02DE6F0E...` | ZIP `PreOrder_pri_150.zip`; SQL unlock Id592 Nissan Fairlady Z Custom yang sudah ada di base |
| Limited Edition Cars | `101F7B0B...` | `SpecialEdition_pri_150.zip`; unlock Id297 Ferrari 360 Challenge, Id435 Mustang Saleen, Id586 Subaru S204 yang sudah ada |
| Nissan and Peugeot Car Pack | `D8341201...` | `10000_merge.slt`: 4 Data_Car baru, 4 engines, 26 torque curves |
| September Car Pack | `2309C821...` | `20000_merge.slt`: 11 Data_Car baru, 19 engines, 106 torque curves |
| December Car Pack | `FF35A769...` | `30000_merge.slt`: 11 Data_Car baru, 14 engines, 76 torque curves; override tire scale Id633 |
| Motegi Pack | `DF5F06FF...` | `40000_merge.slt`: track IDs 43/44/45/46 (Ribbon0..3), length mentah 4800/1770/3030/2410; AI + 4 `.col` |
| Road America Pack | `0AD1F749...` | `50000_merge.slt`: track ID3, Ribbon0, length mentah 6437; AI + `.col` 2.617.344 byte |
| March Car Pack | `59C9301E...` | `70000_merge.slt`: 13 Data_Car baru, 17 engines, 94 torque curves |

Keempat merge DB mobil membawa part, spring/damper, anti-sway, aero, mesin, dan torque curves dalam schema yang sama dengan base. Seluruh 39 ID mobil tambahan tidak bertabrakan dengan base; lima ID track juga tidak bertabrakan. Maka **union definisi yang ditemukan = 349 Data_Car IDs dan 55 Tracks IDs**, dengan **52 active layout candidates** jika kelima layout tambahan digabung. Ini tidak sama dengan hitungan menu mobil/track yang pasti tersedia; lisensi, IsPurchased, unlock dan merge order tetap berpengaruh. Tiga special edition + satu pre-order jangan dihitung dua kali.

Paket menempatkan data di `Media/DLCZips`, memakai `zipmount.xml` dan nama arsip dengan suffix `_pri_...`; database berada di `media/db/patch/<nomor>_merge.slt` serta `_execute.sql`. Penomoran dan priority memberi petunjuk urutan, tetapi aturan loader runtime belum dibedah. Tidak ada SQL patch yang dieksekusi pada sumber atau database hasil riset; isinya hanya dibaca. Contoh SQL track melakukan penghapusan SplitPoints sebelum merge, sehingga penjumlahan tabel secara buta tidak menggambarkan seluruh proses install.

Semua enam SQLite merge DB lolos integrity check. Nilai global tire friction curves/compound/affect curves **tidak didefinisikan ulang** oleh enam merge DB ini; car packs merujuk keluarga model ban base serta parameter per-car. Itu bukti penggunaan schema/model data yang sama, bukan bukti kode solver tidak berubah.

### Title Update di Bonus Disc

`ExpansionInstaller.ini` mencatat `TitleId=0x4d5307ea`, `BaseVersion=0x00000002`, `UpdateVersion=0x00000402`. `title_update.bin` teridentifikasi PIRS `Forza Motorsport 2 Title Update #4`, content type `000B0000`; berisi `default.xexp` 1.034.240 byte dan `Media.zip` 261.211 byte.

Di Media.zip, patch `DB/Patch/1001_execute.sql` menambah CarExceptions dan mengubah urutan event/track; `1002_execute.sql` mengubah `PerformanceIndex` Id330 (`LOT_ElanSprint_72`) dari base `0.03965` menjadi `0.097882`, pada Data_Car dan StockGarage. Tidak ada perubahan tabel spring/tire/engine di dua skrip ini. **Tetapi `default.xexp` adalah patch executable yang belum dianalisis secara semantik; perubahan solver/handling oleh title update belum bisa dikesampingkan.** Jangan membandingkan FM2 “base” dan “bonus installed” seolah revision executable sama.

## 7. Yang dapat dan belum dapat direkonstruksi offline

**Dapat dilakukan dari hasil sekarang:** katalog mobil→stock parts/physics, matriks surface, katalog track/layout, decode data AI waypoint/segment, membaca torque/slip/affect curves sebagai tabel, melacak input tuning dan override per mobil, membedakan konten base/unlock/add-on/title-update, serta menyiapkan dataset reproduksi.

**Belum diketahui:** solver timestepping/integrator dan constraint; rumus combined slip lateral-longitudinal; interpolation/clamp tepat; thermal/pressure evolution equation; mapping `.col` triangle→surface ID; algoritme contacts/collision response; sistem unit lengkap dan axis transforms; penerapan damage/assists/hidden overrides dalam runtime; detail perbedaan kode sebelum/sesudah TU4. Tidak ada dasar untuk klaim “model ban Pacejka”, “fisika identik dengan FM3”, atau peringkat subjektif handling dari pembacaan ini.

Untuk mereproduksi satu mobil pada satu track dibutuhkan manifest build (hash XEX + TU), database base + patch efektif, pilihan parts dan tuning, state ban/fuel/damage, input dan assists, collision geometry + surface assignments, global physics/controller constants, dan implementasi solver. Mesh mobil, horsepower puncak, berat katalog, atau panjang track saja tidak cukup.

## 8. Hash sumber penting (SHA-256)

| File base/bonus | SHA-256 |
|---|---|
| Base `default.xex` | `95008eb3166cc2720f763e26152c4bc0b7938379e8b5aff962c994db91731e7c` |
| Base `Media/DB/gamedb.slt` | `ec486b72bd16437015f18009f57b1c6511f3ff2c6af76d8eb095e494a0a001c2` |
| Base `Media/physics/PhysicsSettings.ini` | `d4e077df6971e13b9814356c66c647145b8bcb563fcd69945a5d38fac25ba078` |
| Base `Media/physics/surfaceTypes.xml` | `9a532cf0aef8bdbe10f7cd4bc49565b1638c97257e8058ae3690d852a8a6189c` |
| Bonus `title_update.bin` | `281b1ed1eb62a8d3392c482afaba1c44aed4742f9539e8f0cde6771b12e218fd` |

Hash penuh semua paket, beberapa file collision/AI, dan payload metadata terpilih ada di evidence.json. Ini mengikat temuan ke dump lokal yang diperiksa; tidak mengklaim kecocokan dengan seluruh revisi retail FM2.
