# Track FM3 → FM4: riset awal

Riset 2 November 2026. Semua pemeriksaan offline dan statis: SQLite dibuka
`mode=ro`, ZIP/STFS dibaca dengan pembaca arsip project, game dan emulator tidak
dijalankan. Hasil per layout ada di `outputs/track-research-2026-11-02/inventory.json`
(diabaikan Git) dan dapat dibuat ulang:

```powershell
.\.venv\Scripts\python.exe research/tracks-2026-11-02/inventory.py
```

Sumber: FM3 USA Disc 1/2 dan Ultimate Collection Disc 2, FM4 Japan/Asia Disc 1,
DLC FM4 *Launch Track Pack*. Path lengkap ada di konstanta script.

## Ringkasan

- FM3 punya 138 layout balap (tanpa track UI). **34 layout tidak ada di FM4**, dari
  lima `MediaName`. Semua ID track FM3 tersebut masih bebas di FM4 disc maupun
  Launch Track Pack; FM4 memakai ulang skema ID FM3 (contoh AmalfiGP 121/127,
  NurburgringF1 33/34, PhysicsTrack 190–219 sama di kedua game).
- Wadah berkas track kedua game sama (folder `Ribbon_NN`, `bin.zip`, CAFF, BIX,
  RMB, PVS, `.col`, `.crowd`), tetapi **versi beberapa format visual naik**: RMB
  4→6, BIX0→BIX1, FPVS 0x18→0x1B, event audio FEV 0x37→0x40, dan FM4 menambah
  berkas `<track>_ribbonNN.sh` per geometri ribbon.
- Analisis statis loader FM4 **tidak menemukan penolakan versi FM3**: FPVS 0x18
  masuk cabang lama (<26), RMB v4 punya cabang sendiri, BIX0 dan BIX1 diterima kode
  yang sama, CAFF memeriksa string versi tetapi FM3 dan FM4 memakai string yang
  sama, dan `.sh` opsional. Disc FM4 retail sendiri masih membawa PVS 0x18/0x19/0x1A
  (UIThumbnail, UIThumBig, dua ribbon Alps). Kemungkinan track FM3 dapat dimuat
  apa adanya; parse seluruh sub-objek RMB v4 dan hasil render belum terbukti.
- Data AI track FM3 dan FM4 **identik byte demi byte** untuk Tsukuba
  (`.geo/.irt/.seg/Level1-3/*.bin`), dan header `.col` sama.
- FM4 sudah punya templat paket DLC track: *Launch Track Pack* memasang
  `21000_merge.slt`, berkas track lepas, dan `<Track>_pri_65.zip` di
  `game:\Media\Tracks\<Track>\bin\`.
- Ada **pasangan port resmi Turn 10**: PhysicsTrack (Test Track Benchmark) versi
  FM3 Ultimate Track Pack dan versi FM4 Launch Track Pack, serta Nurburgring dan
  FujimiKaido dari Road Racing Track Pack FM3. Pasangan ini bisa menjadi rujukan
  konversi, seperti 309 pasangan mobil pada jalur mobil.
- **Uji game CrownJewel 170** (Motorsport DX, 2 November 2026): layout tampil di
  Track Select dan **dapat dibalap** (AI, 12 mobil, tanpa crash) setelah berkas
  barunya dikirim dalam ZIP yang di-mount `zipmanifest.xml`. Sebagai berkas lepas,
  `CrownJewel_19_r.geo` tidak ditemukan game: game mencarinya di root DLC lalu
  crash.

## Layout FM3 yang tidak ada di FM4

| MediaName | ID FM3 | Layout | Sumber aset FM3 | Catatan |
|---|---|---:|---|---|
| CrownJewel | 170 | 1 | Disc 1 | Ribbon 19 = arah balik ribbon 9 (6.952 m). Folder hanya berisi kamera/`CollObjs.xml`; geometri, `.col` dan `.pvs` memakai ribbon 9 yang sudah ada di FM4. AI `CrownJewel_19_R.*` tersedia |
| LeMans | 102 | 1 | Disc 1 | Sirkuit Bugatti (4.180 m). FM4 menghapus `Ribbon_00`; FM3 membawa `.col/.pvs/.crowd` dan AI. Isi `bin.zip` FM4 untuk area khusus Bugatti belum diperiksa |
| NewYork | 22–25 | 4 | Disc 1 (`bin.zip` 85 MB) | Environment baru (FM3 env ID 12, bebas di FM4) |
| Amalfi | 120, 122–126, 128–131 | 10 | Disc 2 FM3, `4D53084D0CCF0060` *Road Racing Track Pack* (`Amalfi_pri_65.zip` 226 MB) | Amalfi Coast penuh; FM4 hanya punya AmalfiGP |
| TestTrackinfield | 49–66 | 18 | Ultimate Collection Disc 2, `4D53084D0CCF0045` *Forza Ultimate Track Pack* (116 MB) | Baris DB hanya di gamedb Ultimate Collection |

Layout lain dari paket FM3 sudah ada di FM4: Nurburgring dan FujimiKaido di disc
FM4, NurburgringF1 ribbon 5/6 di disc FM4, PhysicsTrack di Launch Track Pack.

## Cara FM4 memasang track DLC

Launch Track Pack (PhysicsTrack dan Soccer) memberi struktur yang dapat ditiru:

```text
Media/DLCZips/zipmount.xml          mount <Track>_pri_65.zip -> game:\Media\Tracks\<Track>\bin\
Media/DLCZips/0015_pri_65.zip       media/db/patch/21000_merge.slt
                                    media/Tracks/<Track>/<track>_ribbonNN.sh, TrackSettings.xml,
                                    staticcarcubemap.xpr, Ribbon_NN/{.pvs,.crowd,CollObjs.xml,
                                    PreRaceCams.xml,TrackSegCams.xml}
Media/DLCZips/0015_pri_65/Media/... .col, AI (.geo/.irt/.seg/LevelN), audio XML (berkas lepas)
Media/DLCZips/<Track>_pri_65.zip    isi bin.zip (CAFF/RMB/BIX/fxobj, VersionData.xml)
Media/DLCZips/StringTables_pri_N.zip, stringtables.xml
```

`21000_merge.slt` berisi baris `Tracks`, `Environments`, `EnvironmentTimeOfDay`,
`StartGridPositions`, `TrackStartingMerges`, `SplitPoints`, `GraffitiPoints`,
`PittingProfiles`, `ContentOffers` dan `ContentOffersMapping`. Paket FM3 memakai
pola yang sama (`4069_merge.slt`, ditambah `*_execute.sql`). Ribbon arah balik di
kedua game hanya membawa kamera dan `CollObjs.xml`; `.col/.pvs/.sh` dipakai bersama
dengan ribbon maju.

Mekanisme overlay yang sudah terbukti pada jalur mobil (salinan disc uji, satu
`gamedb.slt`, `stringtables.zip` berprioritas lebih tinggi) dapat dipakai lebih dulu
sebelum membuat paket STFS.

## Perbandingan format per berkas

Pembanding header: Tsukuba (ada di kedua disc) dan PhysicsTrack (port Turn 10).

| Berkas | FM3 | FM4 | Status |
|---|---|---|---|
| AI `*.geo/.irt/.seg`, `Level1-3/*.bin` | teks `MLPDataStart:` | sama | Tsukuba identik byte; FM4 menambah `SegmentProfiles/<t>_NN/default.bin` |
| AI `*.pit` | ada (65) | ada (82) | belum dibandingkan |
| `Ribbon_NN/*_track_NN.col` | `7/4` atau `0x1A/0x10` | sama | header sama; PhysicsTrack FM4 dibake ulang (ukuran beda) |
| `Ribbon_NN/*.pvs` | `FPVS` 0x18 | `FPVS` 0x1B | versi naik |
| `Ribbon_NN/*.crowd` | v2 | v2 | sama versi; PhysicsTrack FM4 dikosongkan (12 byte) |
| `<t>_ribbonNN.sh` | tidak ada | `4/4`, satu per ribbon geometri | baru di FM4; fungsi belum diketahui |
| `staticCarCubemap.xpr` | XPR2 | XPR2 | isi beda |
| `TrackSettings.xml`, kamera, `CollObjs.xml` | XML | XML | FM4 menambah elemen; `collobjsplacement2.xml` baru |
| `bin.zip` `*.stx.bin`, `_0x*.bin` | `CAFF21.11.05.0034` | sama | wadah sama; isi bagian belum dibandingkan |
| `bin.zip` `*.rmb.bin` | versi 4 | versi 6 | versi naik; layout awal (bbox + matriks) serupa |
| `bin.zip` `_0x*.bix` + `_B.bix` | `BIX0` | `BIX1` | versi naik; field lebar/tinggi/mip/format D3D tampak serupa |
| `bin.zip` `*.fxobj` | `00000101` | sama | shader track dikompilasi ulang |
| `bin.zip` `VersionData.xml`, `buildnumber.txt` | tidak ada | ada | metadata build FM4 |
| Audio `<t>.fev` / `.fsb` | FEV1 0x00370000 / FSB4 | FEV1 0x00400000 / FSB4 | event perlu dibuat ulang atau dipinjam; bank FSB4 mungkin dipakai ulang |

Nama `_0x########` adalah indeks build, bukan identitas aset: `_0x00000004.bix`
Tsukuba FM3 dan FM4 adalah tekstur berbeda. Pada port PhysicsTrack, **tidak ada
satu pun** dari 2.851 member `bin.zip` bernama sama yang identik; Turn 10 membangun
ulang seluruh track dengan pipeline FM4.

## Database

Kolom `Tracks` FM4 menambah `IsRealWorld`, `IsReverse`, `IsHomespace`,
`CarsPerUniverse`, `QuickRaceLapCountKinect`, `SatImageName` dan menghapus antara
lain `TrackType`, `RegionGroup`, `LayoutType`, `TargetUsage`. FM4 juga punya
`TurnSections` dan `KinectSplitscreenTracks`.

`StartGridPositions` berubah bentuk: FM3 menyimpan 12 posisi dunia (x, y, z,
heading) per baris; FM4 menyimpan per slot `MetersBackFromStartLine`,
`MetersRightOfCenterLine` dan `Yaw`. Pada Tsukuba, Laguna Seca, Silverstone, Motegi
dan CrownJewel, jarak antar-slot FM3 yang diproyeksikan ke heading slot 0 cocok
dengan selisih FM4 dalam ±0,18 m (kecuali satu slot terakhir CrownJewel). Konversi
membutuhkan dua offset per layout: jarak slot 0 ke garis start dan offset lateral
ke garis tengah. Keduanya kemungkinan dapat diturunkan dari garis tengah AI `.geo`;
belum dibuktikan. Arti `Yaw` FM4 belum jelas (nilainya tidak monoton antar-slot).

## Analisis loader

Analisis statis `default.xex` FM4 (basis 0x82000000) memakai katalog dan
disassembly FM4-re; tidak ada kode yang dieksekusi. Rutin muat utama
`CTrackPresentation::fn_82922C70` membuka `stx.bin`, memanggil pemuat `.sh`, mem-parse
PVS, lalu cubemap, stx dan rmb.

| Berkas | Pemeriksaan di loader | Versi FM3 |
|---|---|---|
| `.pvs` | `82884198` membaca magic tanpa membandingkan; versi disimpan global. Cabang `cmplwi 27` (`82884224`), `cmplwi 26` (`8288EC44`, cabang lama <26), 21/22/23. File opsional (null → dilewati) | 0x18 masuk cabang lama; disc FM4 sendiri membawa 0x18–0x1A |
| `*.rmb.bin` | `CTrackModel::vf0` (`828826F0`) membaca versi (maks 6) tanpa cek rentang dan bercabang di 3/4/5 (`828827B0`..`82882800`). Sub-objek (TBaseModel, NumLODs, CMesh, CSimpleMesh) juga punya cabang versi lama | v4 punya jalur kode sendiri |
| Nama rmb | PVS <26 → `…\bin\%s%s.rmb.bin` dengan sufiks `.sky`; PVS ≥26 → `%s.%05d.rmb.bin` (`8291B744`) | FM3 Tsukuba punya `tsukubaout.sky.rmb.bin`, FM4 Tsukuba tidak; FM4 UIThumbnail punya |
| `.bix` | `82861220`: `BIX0` (`828612C0`) dan `BIX1` (`828612D0`) diterima, lainnya gagal | diterima. Satu dword +16 berbeda pada sampel; dugaan field fetch constant yang ditimpa saat runtime, belum terbukti |
| CAFF (`stx.bin`, `_0x*.bin`) | `82935BF8` ketat: magic, string `21.11.05.0034`, checksum header 400 byte | string identik di FM3 → lolos |
| `.col` | header 84 byte + tabel entri 24 byte, tanpa magic/versi; gagal buka → dilewati | UIThumbnail `.col` FM3 = FM4 byte demi byte |
| `.crowd` | `82879E98`: v1 dikonversi, versi lain dibaca mentah | v2 sama |
| `.sh` | `CTrackPresentation::vf73` (`829265A8`); gagal buka → 0 dan diabaikan | tidak ada di FM3; FM4 HomeSpace/UI juga tanpa `.sh` |

Isi `.sh` (dari pembacaan field): N ≤ 4 koefisien, rekaman berisi entri {f32,
3·N f32}. Ini sangat mungkin probe pencahayaan spherical harmonics RGB per ribbon
(inferensi, belum terbukti). Tanpa `.sh` loader tidak gagal, tetapi pengaruhnya
pada pencahayaan mobil belum ditelusuri.

Template path loader (berguna untuk daftar berkas wajib):

```text
game:\Media\tracks\%s\bin\%s.stx.bin
game:\Media\tracks\%s\bin\%s.%05d.rmb.bin | %s%s.rmb.bin (.sky)
game:\Media\tracks\%s\bin\_0x%08x.bix | .bin
game:\Media\tracks\%s\Ribbon_%02d\%s_%02d.pvs
game:\media\Tracks\%s\Ribbon_%02d\%s_track_%02d.col   (+ CollObjs.xml, collobjsplacement%d.xml,
                                                        TrackSegCams[2].xml, PreRaceCams.xml)
game:\media\tracks\%s\Ribbon_%02d\%s_track_%02d.crowd
game:\Media\tracks\%s\%s_ribbon%02d.sh
game:\media\Tracks\%s\Ribbon_%02d\TrackSettings%d.xml → TrackSettings.xml
staticCarCubemap%d.xpr → staticCarCubemap.xpr → game:\Media\tracks\staticCarCubemap.xpr
StaticTrackLightmap.xpr → game:\Media\tracks\StaticTrackLightmap.xpr
```

Tidak ditemukan referensi loader ke `VersionData.xml`/`buildnumber.txt`; pencarian
belum menyeluruh. Yang belum terbukti: parse seluruh sub-objek RMB v4 (shader,
format vertex, nama `.fxobj` yang dirujuk material), dampak dword +16 BIX, dan
render tanpa data SH. Satu uji muat track FM3 di game akan menjawab ketiganya.

## Paket uji CrownJewel 170

`track_package.py` membuat overlay untuk layout FM3 yang memakai geometri ribbon
yang masih ada di FM4 (`Tracks.ReverseIndex`). Ternyata DB FM4 masih menyimpan semua
baris turunan layout 170 (start grid 170 dalam format FM4, `TrackStartingMerges`,
`TrackPittingZones`, 10 `SplitPoints`, 27 `GraffitiPoints`, semuanya sama dengan
FM3) dan audio `ribbon_19`; yang dihapus hanya baris `Tracks`, folder `Ribbon_19`,
AI, dan dua string nama. Modul menolak layout yang baris turunannya tidak ada di FM4.

```powershell
.\.venv\Scripts\python.exe -m fm4_converter.fm3.track_package --layout 170 --content-root "<user-data>\0000000000000000\4D530910\00000002" --out <paket-baru>
.\.venv\Scripts\python.exe -m fm4_converter.fm3.test_disc --disc "<FM4 Disc 1>" --package <paket-baru> --out <dir-uji>\disc
```

Isi paket `outputs/track-research-2026-11-02/crownjewel-170-v1` (14 berkas):

- `gamedb.slt` FM4 + satu baris `Tracks` 170. Kolom identitas/layout (`id`, nama,
  ribbon 19, `ReverseIndex` 9, panjang 6.952 m, grid 170, flying start 6,
  `MPSortOrder` 307, `WinningsScalar`, lap) dari FM3; logo, environment,
  `SatImageName` dan kolom baru FM4 dari layout maju 160; `IsReverse = 1`. Dua nilai
  berbeda dari FM3: `MiniRibbonPath` memakai `RIB_OldCourse10` (FM4 tidak punya
  gambar mini ribbon untuk layout ini; nama `RIB_GrandPrix5` FM3 di FM4 adalah layout
  lain) dan `RichPresence` 70 milik layout 160 (FM4 menomori ulang nilai ini dan
  memakai nilai yang sama untuk beberapa layout). `TurnSections` tidak ditambahkan;
  14 layout aktif FM4 juga tidak memilikinya.
- `Ribbon_19`: `CollObjs.xml` dan `TrackSegCams.xml` FM3 apa adanya (skema
  `CollObjs` sama; FM4 retail juga membawa satu kamera tanpa atribut `Version`,
  `Infin/Ribbon_02/tracksegcams.xml`). `PreRaceCams.xml` FM3 ribbon 19 identik byte
  dengan ribbon 9, jadi dipakai versi FM4 ribbon 9.
- AI `CrownJewel_19_R` (`.geo/.irt/.pit/.seg`, Level1–3, `SegmentProfiles`) FM3 apa
  adanya; untuk ribbon 10/18 FM4 menyimpan berkas yang identik dengan FM3.
- `Media/stringtables.zip` (prioritas 172, di atas `Tracks.str` Launch Track Pack
  171) berisi 18 `Tracks.str` pemenang + `IDS_DisplayName_170` "Extreme Circuit
  Reverse" dan `IDS_ShortDisplayName_170` "Camino Viejo Extreme - R" (teks bahasa
  FM3 bila ada, selain itu Inggris), serta `zipmanifest.xml` dengan mount tersebut.

Override nama ini terikat pada set konten uji dan tidak dapat digabung apa adanya
dengan `stringtables.zip` paket mobil. Disc uji dibuat dengan hardlink; disc asli
tidak berubah.

Paket v3 (`crownjewel-170-v3`) menambah dua hal setelah uji v1:

- **`CollObjs.xml` dengan indeks FM4.** `GraphicsName="#N"` menunjuk objek model
  track, dan FM4 menomorinya ulang: objek yang hanya dipakai layout FM3 yang
  dihapus ikut dibuang (FM3 `#36` = FM4 `#35` pada koordinat yang sama). Pasangan
  indeks diambil dari ribbon CrownJewel yang ada di kedua game, dengan tipe dan
  koordinat identik byte demi byte. Hasilnya 259 pasangan, unik dan urutannya
  terjaga. Dari 101 objek ribbon 19, 79 dipetakan. 22 cone dibuang: 17 jatuh di
  celah yang tidak punya slot di FM4, dan 5 posisinya ambigu.
- **Audio `crownjewelribbon_19decisionzones.xml`.** FM4 menambahkan berkas zona
  musik ini ke setiap ribbon yang bisa dibalap, tetapi `ribbon_19` hanya berisi dua
  berkas sisa FM3. Paket menyalin berkas dari ribbon geometri 09. FM4 sendiri
  memakai zona ribbon geometri apa adanya untuk beberapa layout reverse
  (Nurburgring 2–4, FujimiKaido 1–4, 10, 11).

## Uji Motorsport DX 2 November 2026: dari crash sampai dapat dibalap

Harness `e2e.py` (FM4-PC) dijalankan dengan BuildRoot `I:\FM4-build-usa`,
`--profile copy --native`, `FM4_GAME_CMDLINE=engageaionstart`, dan
`game_data_root` disc uji. Langkahnya rute cepat Quick Race: mobil default,
Right sekali di Environment Select (Camino Viejo), lalu Right di Track Select
sampai OCR membaca persis "Extreme Circuit Reverse". Hasil run ada di
`I:\FM4-build-usa\e2e\track-cj170-*` dan tidak masuk Git.

Catatan harness: OCR server gagal mem-parse layar Environment Select Camino Viejo
(`JSONDecodeError`), sehingga langkah lokasi dibuat tanpa pemeriksaan OCR.

- **Menu.** Track Select Camino Viejo menampilkan "Extreme Circuit Reverse" setelah
  "Extreme Circuit (Sunset)", dengan 1 lap. Nama dari override `Tracks.str` terbaca.
- **Memuat (berkas lepas).** Semua run 170 v1–v3 keluar dengan `0xC0000005` sekitar 1 detik
  setelah `17_DYNAMIC_LOADING_FREEPLAY`. Log mencatat `Unhandled guest access violation: read
  of guest 0x00000000` dan `rip` selalu sama, di `sub_82A9DE98`. Pembanding
  "Extreme Circuit" (160) di disc yang sama sampai balapan dan menu pause.

Bisect dilakukan dari paket v3; setiap varian memakai disc uji tersendiri:

| Varian | Perubahan | Hasil |
|---|---|---|
| `z-ribbon18` | baris 170: `RibbonIndex` 18, `ReverseIndex` 8 (semua aset ribbon 18 native) | balapan berjalan |
| `r18-g9` | baris 170: `RibbonIndex` 18, `ReverseIndex` 9 | balapan berjalan |
| `x-native-xml` | XML `Ribbon_19` = XML FM4 ribbon 09 | crash |
| `a-ai18` | AI `19_R` = AI FM4 `18_R` | crash |
| `u-audio09` | audio `ribbon_19` = audio FM4 ribbon 09 | crash |
| `all-native` | ketiganya sekaligus | crash |

Isi baris DB (grid 170, nama, `MPSortOrder`, `RichPresence`, dll.) dan geometri
ribbon 9 sebagai reverse diterima. Kedua varian ribbon 18 berhasil karena memakai
berkas AI `CrownJewel_18_r` yang memang ada di disc, bukan karena indeks 18.

**Penyebab: berkas lepas baru tidak ditemukan game.** Unwind x64 dari minidump
handler crash, memakai `.pdata` `fm4_rex.exe` dan `fm4_rex.map`, memberi rantai
yang bersih:

```text
sub_82940500 → sub_826D4D18 → sub_826D5A58 ("game:\media\AI\Tracks\")
  → sub_82A9E668 (sprintf "%s%s.geo" / "%s%s.seg") → sub_82A9DE98
```

`sub_82A9DE98` membuka `.geo` (teks `MLPDataStart`) dan langsung membaca properti
`iCRC` lewat pointer yang tetap 0 bila berkas tidak terbuka (`0x82A9DFC0`), tanpa
pemeriksaan. Nama berkas dibentuk `sub_826DB438` dengan `"%s_%02d%s"`: nama media,
indeks ribbon, dan sufiks `_r` untuk reverse.

Log `log_level=debug` memperlihatkan perbedaannya. Untuk ribbon 19, game mencari
`media\AI\Tracks\CrownJewel_19_r.geo` di 12 root DLC lalu crash, padahal berkasnya
ada lepas di disc uji. Untuk varian ribbon 18 tidak ada pencarian DLC sama sekali.
Jadi game menentukan sendiri apakah suatu berkas ada di disc; berkas lepas yang
tidak dikenalnya diperlakukan sebagai konten DLC. Sumber daftarnya diduga
`hash.manifest` di root disc (36.904 byte; header 0x80 lalu entri 8 byte), tetapi
belum dibuktikan. VFS runtime (`HostPathDevice`, pencocokan nama tanpa membedakan
huruf besar/kecil) tidak menjadi masalah.

**Perbaikan: berkas baru dikirim dalam ZIP yang di-mount `zipmanifest.xml`.**
Mekanismenya sama dengan `stringtables.zip`. `track_package.py` kini membuat:

- `Media/AI/Tracks.zip` (8 berkas AI), di-mount di `media\ai\tracks\`;
- `Media/tracks/CrownJewel/Ribbon_19.zip` (3 XML);
- `Media/audio/tracks/CrownJewel/ribbon_19.zip` (`decisionzones`).

Semuanya berprioritas 80 dan tidak ada berkas lepas baru.

| Run | Paket | Hasil |
|---|---|---|
| `track-cj170-zip-1` | v3 dengan berkas dalam ZIP, log debug | balapan berjalan, tidak ada pencarian AI di DLC |
| `track-cj170-v4-1` | v4 (pipeline baru), balapan 90 detik | balapan berjalan, tanpa crash |

Hasil yang terlihat di run v4:

- Mobil pemain dikendarai AI (`engageaionstart`) dan mengikuti lintasan, naik dari
  posisi 7 ke posisi 1 dalam 1:36.
- Garis bantu balap dari berkas AI tampil, dan 12 mobil melaju searah.
- Penghitung lap berperilaku sama dengan layout native 160.
- Menu pause menampilkan klasemen.
- Kunci error runtime sama dengan baseline: `update:\media.zip`, satu pesan XAM, dan
  dua `BaseHeap::Release`.

Run `track-cj170-v4-finish` (v4, balapan penuh 1 lap, lalu dibiarkan di menu
post-race):

- **Pre-race.** Layar loading menampilkan "Extreme Circuit Reverse" dan 4,32 mi
  (= `Length` 6.952 m FM3). Kamera pemandangan di menu pre-race dan kamera intro
  mobil di grid tampil (`PreRaceCams` ribbon 9 FM4).
- **Grid.** Baris `StartGridPositions` 170 yang dipertahankan FM4 menempatkan mobil
  7,8 m di belakang garis start dengan selang-seling ±2 m, polanya sama dengan 160
  dan 179. Mobil mulai di lintasan, menghadap arah balapan.
- **Balapan.** Mobil pemain dikendarai AI dan finis di posisi 1 dari 12 dengan waktu
  sekitar 3:56,5. Selisih dengan mobil di belakangnya +21,7 detik satu lap sebelum
  finis. Event `pop 12-Car_Race` dan `924_POST_RACE` muncul 242 detik setelah start.
- **Post-race.** Menu CONTINUE / RESTART / VIEW REPLAY / SAVE REPLAY / LEADERBOARDS
  / RACE RESULTS tampil. Saat dibiarkan, replay berjalan dengan kamera lintasan
  (`TrackSegCams` FM3). Cone tampak di tikungan menjelang finis.
- **Error.** Tanpa crash; kunci error runtime sama dengan baseline.

Yang belum dibuktikan: setiap cone hasil remap berada di posisi FM3 (yang terlihat
hanya bahwa cone ada), pencahayaan dibanding layout 160, dan nama di bahasa selain
Inggris. `manifest.json` paket tetap ditulis `runtime_tested=false` dan
`accepted=false` oleh generator; penerimaan menunggu keputusan pengguna.

## Prototipe NewYork 22–25 (2 November 2026): memuat sampai model track

NewYork adalah layout dengan geometri sendiri, sehingga seluruh track FM3 dibawa apa
adanya. Prototipe: `newyork_proto.py` (paket `outputs/track-research-2026-11-02/
newyork-proto-2`, disc uji `D:\Data\FM3-to-FM4-tests\newyork-proto-*`).

**Database.** DB FM4 masih menyimpan 44 `GraffitiPoints`, 4 `TrackPittingZones` dan 4
`TrackStartingMerges` NewYork. Yang hilang, dan ditambahkan oleh prototipe:

- `Environments` 12 dengan kolom baru FM4 (`Description` = kunci `Location`,
  `ShowOnMap` 0) dan satu `EnvironmentTimeOfDay` (salinan indeks 0 environment 4);
- `Tracks` 22–25: kolom FM3, ditambah `IsRealWorld` 0, `IsReverse`,
  `CarsPerUniverse` 0, `QuickRaceLapCountKinect` 1 dan `SatImageName`;
- `StartGridPositions` 22 dan 24 (16 slot) hasil `grid_conversion.py`;
- `SplitPoints` (empat baris FM3, ID baru).

String: `Tracks.str` (8 entri) dan `Environments.str` (3 entri) ada di
`stringtables.zip` berprioritas 172.

**Konversi grid.** `grid_conversion.py` memproyeksikan 12 posisi dunia FM3 ke garis
tengah AI `.geo`:

- Waypoint 0 adalah garis start, dan sumbu horizontal `.geo` adalah X,Y (Z = tinggi).
- `Yaw` FM4 adalah derajat relatif terhadap arah lintasan.
- Pada 29 dari 78 layout yang ada di kedua game, `MetersBack` dan `MetersRight` cocok
  dengan FM4 dalam 0,35 m di semua 12 slot. Offset lateralnya identik.
- Layout lainnya adalah layout yang grid-nya diubah Turn 10 (Laguna Seca bergeser
  10 m; CrownJewel slot 8 ke atas dibuat ulang) atau track berliku tempat proyeksi
  melompat ke bagian lintasan lain.
- Slot 12–15 mengikuti pola FM4 Motegi (slot k−4 + (slot 11 − slot 7)).
- Untuk NewYork, semua slot berjarak 3,5–5,5 m dari garis tengah, dengan
  `MetersBack` naik dari 14 m sampai 88 m.

**Hasil uji di Motorsport DX** (Quick Race, layout pertama = 23, ribbon 01):

| Run | Paket | Hasil |
|---|---|---|
| `track-ny-proto-1` | proto-1 | Environment Select menampilkan "New York Circuit", "New York, USA", 4 layout dan deskripsi |
| `track-ny-proto-2` | proto-1 | crash di `RacingAI::CreateAIDriver` → `CAIDrivatar` → `sub_82A99EA8`: pointer array `iStart` `.seg` pada objek data AI (+324) kosong |
| `track-ny-aiswap3` | isi AI `newyork_01` = berkas CrownJewel 19_R | lolos pembuatan AI; trap `0x80000003` setelah `NtCreateFile` gagal untuk `game:\media\audio\tracks\newyork\newyork.fev` |
| `track-ny-aiswap4` | + audio sebagai berkas lepas | `.fev` FEV 0x37 FM3 dibuka tanpa error; crash di `CTrackPresentation::vf74` → `CSkinnedModelResourceType` → `D3D::GetTextureDescInternal` dengan tekstur null |

Temuan:

1. **Audio harus berupa berkas lepas.** FMOD membuka `.fev` lewat `NtCreateFile`
   langsung, sehingga mount ZIP tidak dipakai; berkas lepas baru terlihat lewat jalur
   ini. Isi audio dan `decisionzones` pinjaman (Infin ribbon 00) belum terdengar atau
   terbukti.
2. **Isi AI NewYork FM3 tidak cocok untuk pengemudi AI FM4.** Format berkasnya sama
   (field `.geo/.seg/.irt/.pit`, jumlah `SegmentProfiles` = jumlah segmen), dan
   `CrownJewel_19_R` FM3 bekerja di FM4. Penyebab array kosong belum ditemukan;
   kandidatnya isi `.irt`/`Level1-3` (`trackName`) atau jalur pemuatan lain.
3. **Model track FM3 (RMB v4/BIX0) tidak termuat apa adanya.** Model skinned dari
   `bin.zip` FM3 merujuk tekstur yang tidak ada. Ini batas format visual: tahap
   berikutnya adalah konversi RMB v4 → v6 dan BIX0 → BIX1 dengan rujukan pasangan
   port Turn 10 (PhysicsTrack, Nurburgring, FujimiKaido), atau menelusuri tekstur yang
   dicari `CSkinnedModelResourceType` (kemungkinan model langit
   `newyorkout.sky.rmb.bin` atau objek animasi).

### Lanjutan: penyebab crash model track

Rantai crash `track-ny-aiswap4`, hasil unwind x64 dan katalog FM4-re:

```text
CTrackPresentation::vf74 (82956C00) → helper_82911E10 (state machine, +260)
  → 8290FB20 (state 4) → 8290F4E8 → D3D::GetTextureDescInternal(tekstur target null)
```

Di rentang fungsi yang sama ada `AsyncFunctionWrapper4<CRoadDetailTextureArray>` dan
`CompressRoadDetailTextures`. String shader-nya `RoadDetailRotateAndBlurRGB/Specular`,
dan pembacaan `TrackSettings` mencakup `DetailBlur*` serta `DetailBlurMPHForMaxBlur`.
Jadi state machine ini membangun array tekstur road detail yang di-blur.

- Sumber teksturnya ada di `+308`. Jika sumber itu null, langkah ini dilewati.
- Tekstur target dibuat di state 2 dengan ukuran dari struct `+308`.
- Untuk NewYork, salah satu tekstur target null.

Uji pengecualian, semuanya tetap crash di titik yang sama:

| Varian | Perubahan |
|---|---|
| `newyork-proto-nocube` | tanpa `staticCarCubemap.xpr` FM3 (fallback ke cubemap global FM4) |
| `newyork-proto-sh` | dengan `NewYork_ribbon00/01.sh` pinjaman Tsukuba |
| `newyork-proto-ts` | `TrackSettings.xml` FM3 + 39 elemen/atribut khusus FM4 dari Tsukuba (IBL, `SkyboxIndex`, `DetailBlur*` dll.) |

**Uji kendali Tsukuba.** Disc FM4 native digabung dengan `bin.zip` Tsukuba FM3 saja
(DB, AI, ribbon, audio tetap FM4):

| Run | Paket | Hasil |
|---|---|---|
| `track-tsukuba-fm3bin-2` | `bin.zip` FM3 | macet di layar loading; `4_C_INI_PRERACE` tidak muncul dalam 90 detik, tanpa crash |
| `track-tsukuba-fm4sh-3` | + 31 dari 38 shader `shaders/track/*.fxobj` diganti versi FM4 bernama sama (ZIP di `bin\shaders\track\`, prioritas 81) | tetap macet |

Shader track FM3 tidak satu pun identik byte dengan versi FM4 (pustaka 235 shader dari
semua `bin.zip` FM4). Cakupan nama: Tsukuba 31/38, NewYork 28/40.

Kesimpulan: **`bin.zip` FM3 tidak dapat dipakai FM4**, juga untuk track yang ada di kedua
game. Tsukuba macet dan NewYork crash pada pembangunan tekstur road detail. Masalahnya
bukan berkas pendamping (cubemap, `.sh`, `TrackSettings`) dan bukan hanya shader. Selain
tekstur, model, dan shader, beda nama member hanya `*.sky.rmb.bin` (khusus FM3) serta
`buildnumber.txt`/`VersionData.xml` (metadata FM4). Jalan berikutnya adalah konverter
biner track (`stx.bin` CAFF, RMB v4 → v6, BIX0 → BIX1) dengan pasangan Tsukuba FM3/FM4
sebagai rujukan: track sama, keduanya dibangun Turn 10.

### Konverter biner track, tahap 1 (2 November 2026)

**Kontainer tekstur.** `caff.py` membaca CAFF sesuai layout di FM4-PC
`docs/analysis/texture-replacement.md`. Daftar chunk dimulai di
`blob + 4 + 4·N + ukuran_nama + 4`, karena ukuran blob hanya menghitung string nama.

- `stx.bin` dan `_0x*.bin` di kedua game hanya berisi record `texture` versi
  `04.05.05.0032`: Tsukuba FM3 605 + 191, FM4 614 + 246.
- FM4 menambah satu chunk bernama "texture pairs" (4 byte, berisi 0).
- Ukuran dan isi header record sama. Dua perbedaan yang konsisten:
  - `D3DFORMAT`: FM3 `0x1A2001xx`, FM4 `0x1A207Fxx`. Bit sign X/Y/Z bernilai 3
    (gamma), jadi FM4 mengambil sampel tekstur track sebagai sRGB.
  - Offset base/mip (+0x28/+0x2c): FM3 selalu 0/`0xFFFFFFFF`, sedangkan FM4 punya 224
    offset berbeda di data GPU kontainer.
- `.bix`: header `BIX0`/`BIX1` sama (lebar, tinggi, mip, `D3DFORMAT`), dengan perbedaan
  bit gamma yang sama.

**Pencarian penyebab macet.** `live_stacks.py` menelusuri stack setiap thread game yang
sedang berjalan (dbghelp `StackWalk64` + `fm4_rex.map`). Pada Tsukuba dengan `bin.zip`
FM3 (run `track-tsukuba-hang4`, tiga sampel identik):

- thread render menunggu fence GPU yang tidak pernah selesai:
  `CRenderThread::Present → Swap → Resource::WaitForFence → D3D::CheckGpuHang`;
- worker road detail menunggu di `CSkinnedModelResourceType::fn_8290FA68` ←
  `fn_82910600`.

Pada NewYork, subsistem yang sama menghasilkan tekstur target null. Asal subsistem ini:

- `CTrackPresentation::ModelFixupHandler::vf0` (`8295A900`) memetakan setiap slot
  tekstur model ke tabel tekstur track `CTrackPresentation+6336` (entri 200 byte).
- Metadata tekstur ada di `+2348` (entri 28 byte). Nilai `+24 & 0xF0 == 16` menandai
  road detail.
- `vf74` (`82956C00`) membangun `CRoadDetailTextureArray` untuk entri tipe 16: 64
  langkah, target 32×512, parameter `DetailBlur*` dari `TrackSettings`.
- Record tekstur CAFF tidak membawa tipe (+0x20 selalu 0), jadi tanda road detail
  berasal dari material model RMB.

Target berikutnya adalah format material RMB v4 dan v6:

1. temukan field material yang menghasilkan tipe 16;
2. coba matikan road detail pada model FM3 untuk melihat apakah data visual FM3 lainnya
   termuat;
3. baru konversi struktur RMB.

### Konverter biner track, tahap 2: set FM3 lengkap termuat (2 November 2026)

**Koreksi uji kendali.** Membaca memori game yang macet (pindaian vtable
`ModelFixupHandler` `0x8215779C` → `CTrackPresentation` = alamat − 5284) menunjukkan
bahwa tabel tekstur track (`+6336`, objek `CTrackTexture_Unified` 200 byte; metadata
`+2348`, 28 byte) Tsukuba sama persis antara disc native dan disc dengan `bin.zip` FM3:
1476 entri, satu tekstur road detail (ID 571, tipe `0x14`).

Tabel itu dibangun dari berkas lepas ribbon (`.pvs`/`.col`/`.crowd`), bukan dari
`bin.zip`. Penomoran tekstur dan model berbeda total antara build FM3 dan FM4: ID 571
FM4 adalah DXT1 6 level ber-BIX, sedangkan ID yang sama di FM3 adalah DXT5A 5 level
tanpa BIX. Jadi uji `bin.zip` FM3 saja tidak valid, karena mencampur `bin.zip` FM3
dengan ribbon FM4.

**Set FM3 lengkap.** Varian `bisect/tsukuba-fm3full` mengganti seluruh folder Tsukuba
dengan versi FM3: `bin.zip`, `Ribbon_00/01` (`.pvs`, `.col`, `.crowd`, XML),
`TrackSettings.xml`, cubemap, dan `smoke.dds`. Empat berkas baru `co_*cone.bin`
dikirim dalam ZIP di `media\tracks\tsukuba\`. DB dan AI tetap FM4.

| Run | Varian | Hasil |
|---|---|---|
| `track-tsukuba-fm3full` | set FM3 lengkap | **balapan berjalan** (12 mobil, AI, 3 lap, menu pause); tampilan utama hampir hitam, spion menampilkan track FM3 dengan benar |
| `track-tsukuba-fm3full-ts4` | + `TrackSettings.xml` FM4 Tsukuba | exposure benar (mobil dan kokpit terang); lintasan dan langit tetap tidak tampil di tampilan utama (abu-abu rata, garis balap AI tampak), spion tetap benar |
| `track-tsukuba-fm3full-ts4-sh` | + 31 shader FM4 bernama sama | crash saat memuat (lokasi belum terekam) |

Data biner track FM3 (model RMB v4, tekstur BIX0, PVS 0x18, `.col`) **dapat dimuat dan
dirender FM4**: spion menampilkan track FM3 dan simulasi balapan berjalan. Yang tersisa
adalah render tampilan utama. Shader track FM3 jalan di jalur spion, tetapi tidak
menghasilkan apa pun di jalur utama FM4. Shader FM4 juga tidak bisa langsung dipasang
pada material FM3.

**Road detail NewYork.** Tabel NewYork (3308 entri, dibaca sebelum crash) punya satu
tekstur bertipe `0x14`, yaitu ID `0x594`: DXT5, 5 level, ada `_0x00000594.bix`.

- Mengganti isi `RDDET_DIFF_SPEC_OPAC_2.fxobj` dengan `DIFF_SPEC_OPAC_2` milik NewYork
  (ZIP prioritas 81 di `bin\shaders\track\`) tidak mencegah crash.
- Kode game tidak memuat string `rddet`.
- Jadi tipe road detail datang dari data material/ribbon FM3, bukan dari berkas shader.
  Field-nya belum ditemukan.
- Tsukuba FM3 tidak punya material road detail, sehingga tidak crash.

Langkah berikutnya:

1. **Tampilan utama hitam:** bandingkan jalur render utama dan spion, misalnya technique
   atau pass yang dipanggil per material (prepass, shadow, IBL), untuk shader FM3 vs
   FM4 pada Tsukuba.
2. **Road detail:** temukan field material/ribbon FM3 yang memberi tipe `0x14`
   (mulai dari referensi `0x594` di `.pvs`/RMB NewYork), lalu hapus flag-nya.

### Konverter biner track, tahap 3: tampilan utama dan PVS (2 November 2026)

**Bukan efek runtime.** Run `track-tsukuba-fm3-orig` (`--look original`, tanpa mod
render Motorsport DX) memberi hasil sama: tampilan utama abu-abu, spion menampilkan
track FM3.

**Jalur PVS lama.** Di FM4 retail, PVS < 26 hanya dipakai `UIThumbnail` (v24) dan
`UIThumBig` (v25), yaitu scene UI satu model. Semua ribbon track balap memakai v27
(Alps 03/04 v26). PVS FM3 adalah v24.

Kode yang bercabang menurut versi PVS (global `0x82DFE4E0`):

- `CTrackPresentation::vf64` (`8291B718`): untuk < 26, memuat satu model
  `game:\Media\tracks\%s\bin\%s%s.rmb.bin`; untuk ≥ 26, memuat model per indeks.
- `helper_8288EAE8`: cabang terpisah untuk < 26.
- `helper_82883E38`: membandingkan versi dengan 22.

Kesimpulan: track FM3 diperlakukan sebagai scene UI, dan tampilan utama tidak menerima
model track.

**Header PVS.**

| Versi | Isi header |
|---|---|
| v24 | `FPVS`, versi, w2, (ribbon<<16 \| 0x19), jumlah, n, lalu data uint16 |
| v27 | sama, dengan satu word tambahan w3 setelah w2 |

Pembaca header (`82884198`) memang hanya membaca word tambahan untuk versi ≥ 27. Nilai
w3 di FM4: `0x401FB8` (Tsukuba), `0x801F88` (Alps, AmalfiGP), `0x1001FB8` (Autopark),
`0x1001FA8` (Catalunya). Kemungkinan ini bitfield konfigurasi; artinya belum diketahui.

**Uji PVS v27.** PVS FM3 Tsukuba diubah menjadi `0x1B` dengan w3 dari PVS FM4 Tsukuba
(run `track-tsukuba-pvs27b`). Game masuk jalur track normal, lalu crash saat memuat
(sebelum menu pre-race). Tiga thread worker membaca `0x28` (null + 0x28) di
`CPhysicsWorld::fn_8282A0A8`, dipanggil dari `CPhysicsWorld::vf15`. Jalur ≥ 26 memakai
data tabrakan atau zona dengan cara lain dari jalur lama.

Penyempitan crash fisika pada jalur v27:

| Run | Perubahan dari PVS v27 | Hasil |
|---|---|---|
| `track-tsukuba-pvs27-nocoll` | `CollObjs.xml` FM3 dikosongkan | crash sama (`0x28`) |
| `track-tsukuba-pvs27-noplace` | `collobjsplacement2.xml` FM4, yang masih tertinggal di disc (512 cone Free Play), dikosongkan | crash sama |
| `track-tsukuba-pvs27-w0` | w3 = 0 | crash sama |
| `track-tsukuba-pvs27-probe2` | `phys_probe` membaca `CPhysicsWorld` di memori setiap detik | lihat di bawah |

- Register crash: `r13` = `0x8282A3F8`, alamat balik setelah panggilan virtual slot 10
  di loop daftar `+64`.
- Snapshot terakhir sebelum crash: `CPhysicsWorld` sehat; daftar `+64` berisi 12 objek
  mobil (vtable `0x8200314C`) dan daftar `+80` 18 objek (`0x82002BC4`), semua valid.
- Crash berikutnya membaca `0xC`, bukan `0x28`. Offset yang berubah menandakan pointer
  sampah dari data, bukan objek yang belum dibuat.
- Jadi crash terjadi saat mobil diperbarui di awal balapan, kemungkinan pada query ke
  tabrakan/zona track. Jalur ≥ 26 menafsirkan payload PVS (atau tabel turunannya)
  dengan semantik baru, sedangkan payload v24 FM3 hanya headernya yang disamakan.

### Konverter biner track, tahap 4: format PVS terurai (2 November 2026)

`pvs.py` membaca dan menulis `FPVS` mengikuti parser FM4 `helper_8288EAE8`.

Stream big-endian (`IOSys::CBinaryStream`):

| Slot | Isi |
|---|---|
| 160/124/136 | 4 byte |
| 164 | u16 |
| 128/152/168 | 1 byte |
| 104 | vektor 4 float |
| 108 | matriks 16 float |
| 116 | string (u32 panjang + byte) |

Urutan file:

1. Header: `FPVS`, versi, w2, w3 (≥ 27).
2. Dua u16.
3. `l4`: per elemen dua daftar u16, satu daftar u32, satu daftar u8.
4. `l20`: u32, u32, 4 float, u32. Ini tabel tekstur track; di FM4 Tsukuba berisi 1476
   entri, sama dengan tabel di memori, dan flag road detail `0x14` ada di sini.
5. `l172`: string.
6. `l36`: sel (`82883E38`).
7. `l52`: objek (daftar u32, daftar u32, matriks, vektor).
8. Versi ≥ 26: `a84`, `a100`, `a116` (daftar u16). Versi < 26: satu sel dan satu objek
   ekstra, yang kemudian dipakai game untuk menyintesis ketiga array.
9. `l68`: sel.
10. string, dua bool, `l200` (string), `l192` (daftar u16).

Sel versi < 25 menyimpan satu float di `+16`; versi ≥ 25 menyimpan vektor 4 float.

Validasi: 141 berkas PVS FM4 dan FM3 terbaca sampai EOF, dan ditulis ulang identik byte
demi byte.

`to_v27` mengonversi v24 → v27:

- vektor sel = (f, 0, 0, 0), sesuai konstanta FM4 di `0x82000F40` = 0.0 dan FM4 Tsukuba
  (14.0, 0, 0, 0);
- sel dan objek ekstra ditambahkan ke daftar; sel menunjuk objek (`u0`) dengan flag
  `0x50000204` seperti sel istimewa FM4;
- `a84 = [65535, sel]`, `a100 = [65535, objek]`, `a116 = [objek]`, mengikuti bentuk FM4
  Tsukuba.

Uji kendali sebelumnya (hanya header yang diubah) ternyata membaca sel dengan offset
bergeser, sehingga crash fisika di sana adalah artefak.

Run `track-tsukuba-pvsconv` (set FM3 lengkap, `TrackSettings` FM4, PVS hasil
`to_v27`): **tidak crash**, balapan berjalan sampai menu pause melalui jalur track ≥ 26.
Tampilan utama tetap abu-abu dan spion tetap menampilkan track FM3.

Jadi jalur PVS lama bukan penyebab tampilan kosong. Kandidat berikutnya adalah shader.
Vertex shader FM4 punya tiga varian per technique (`Default_identity`,
`RealtimeCubemap_identity`, `lightmap_identity`) dan input `tangent`/`binormal`/`color`;
shader FM3 hanya punya satu vertex shader. Kemungkinan lain adalah depth prepass FM4
dengan shader generik yang tidak cocok dengan format vertex FM3.

### Konverter biner track, tahap 5: tampilan utama butuh command buffer pass 5 (2 November 2026)

**Draw yang dikirim.** Run `track-tsukuba-fm3-trace` (set FM3 lengkap, PVS `to_v27`) dan
`track-tsukuba-native-trace` (Tsukuba FM4) memakai `REX_DRAW_LIST_TRACE` (setiap 300
frame). `track_cmdbuf.py hashes/draws` mencocokkan pixel shader setiap draw dengan hash
ucode shader `bin.zip` FM3/FM4. Per frame balapan:

| Pass (render target, depth target) | Native FM4 | Set FM3 |
|---|---|---|
| spion (`rt=0`, `ds=10040`) | 35 draw shader track | 34–75 draw shader track |
| tampilan utama (`rt=30000`/`c0000`, `ds=10400`) | 196 + 9 draw shader track | **0** |

Jadi tampilan utama tidak abu-abu karena shading atau depth: draw track FM3 memang tidak
pernah dikirim ke GPU.

**Titik keputusan.** `CTrackPresentation::RenderPass` memanggil `DrawObject` (`82314BC8`)
dengan flag command buffer. Dengan flag aktif, objek hanya digambar jika
`pass*3 + varian < model+64` (jumlah slot) dan dword pertama entri 128 byte
`model+68[indeks]` tidak nol; selain itu draw dilewati tanpa pesan. Isi tabel ini dibaca
dari berkas model:

- `CTrackModel::vf0` (`828826F0`): versi RMB 3/4/5 memberi jumlah slot 12/15/18. Versi 6
  memakai nilai konstruktor, yaitu 21 (`82890C60`: `li r4,21`), = 7 pass × 3 varian.
- Serializer dasar `8286C080` (`OrderedSubModels`, `SubModel`, `MaterialSets`,
  `FxFileNames`, `MeshNames`, `CommandBufferGroup`) membaca array `CommandBufferGroup`
  sebanyak jumlah slot (`8287EBE8`):
  - header: `SharedHeaderSize`, `SharedPhysicalSize`, `SharedInitializationSize`,
    `SharedStaticFixupSize`, `SharedDynamicFixupSize`;
  - per entri (`8287E878`): `StaticFixups`, `DynamicFixups`, `HeaderSize`,
    `PhysicalSize`, `InitializationSize`.
- Isinya command buffer PM4 Xenos yang sudah direkam offline. Di berkas tampak
  bersama microcode shader dan paket `c0 02 2f 00`.

**Tabel di memori** (`track_cmdbuf.py models`, saat balapan, 15 detik setelah start):

| Run | Model | Slot | Pola entri berisi yang paling umum |
|---|---|---|---|
| `track-tsukuba-fm3-probe` | 1857 | 15 | indeks 3, 6, 9, 12 (597 model hanya 9, 12) |
| `track-tsukuba-native-probe` | 1803 | 21 | indeks 3, 6, 9, 12, **15** (384 model 9, 12, 15) |

Polanya sama, ditambah satu pass: setiap model FM4 punya entri pass 5 (indeks 15, kadang
16/17) yang tidak ada di model FM3. Contoh berkas `*.00000.rmb.bin`: FM3 berisi 4 command
buffer PM4, FM4 berisi 5. Pass yang hanya ada di FM4 inilah yang dipakai tampilan utama.
Spion memakai pass lama (≤ 4), karena itu track FM3 tampil di sana.

**Konsekuensi untuk konverter.** RMB track v4 harus dinaikkan ke v5 (18 slot) atau v6
(21 slot), dengan entri pass 5 untuk setiap model. Calon paling dekat adalah salinan
command buffer pass 4 model yang sama (indeks 12–14), dengan fixup dan ukuran pool bersama
disesuaikan. Prasyaratnya parser `CommandBufferGroup` yang lengkap. Pencarian header grup
dengan asumsi entri berurutan plus tiga pool di akhir berkas belum cocok dengan berkas
nyata. Data entri tampak berselang-seling dengan microcode shader, jadi batas setiap
record perlu dipetakan dulu dari serializer `8287EBE8`/`8287E878`/`828723C0`.

### Konverter biner track, tahap 6: RMB v4 → v5, tampilan utama tampil (2 November 2026)

Format `CommandBufferGroup` terurai lengkap di `fm4_converter.fm3.track_rmb`. Setiap
`beginVer` di `CBinaryVersionedStream` (`8295E3D8`) adalah u32, dan `endVer` tidak membaca
apa pun. Fixup versi 2 berupa `u32 n` + `n × 8` byte mentah (`82871600`/`8286C450`). Grup
berakhir tepat di EOF. Hasil uji:

- 1087 model FM3 Tsukuba dan 1088 model FM4 Tsukuba terurai dan ditulis ulang identik.
- Pada model FM4 (sampel setiap 37 model), pass 5 = pass 4 dengan `RB_SURFACE_INFO`
  (`0x2000`) tanpa bit MSAA, `PA_SC_AA_CONFIG` (`0x2301`) = 0, dan window/scissor
  1280×720 tanpa tiling. Prolog/epilog predicated tiling (`SET_BIN_SELECT`,
  `SET_BIN_MASK`, `SET_CONSTANT` window per tile) dibuang.
- Pass 4 FM3 berbentuk sama dengan pass 4 FM4 (MSAA 4x, tiga tile).

`to_v5` menaikkan versi model ke 5 (18 slot), lalu menyalin slot 12–14 ke 15–17 dengan
perubahan yang sama. Paket yang dibuang diganti NOP type-2, sehingga offset fixup tetap
berlaku.

| Run | Isi | Draw shader track di pass utama | Hasil |
|---|---|---|---|
| `track-tsukuba-rmb5` | salinan pass 4 apa adanya | 214 | hanya pita bawah tergambar (MSAA dan offset tile terakhir) |
| `track-tsukuba-rmb5b` | + single-sample | 213 | sama |
| `track-tsukuba-rmb5c` | + tanpa tiling | 223 | **track FM3 tampil penuh di tampilan utama** (lintasan, dinding, bangunan, langit), tanpa crash |

Kriteria T3 ([fm3-acceptance.md](../../docs/fm3-acceptance.md)) terpenuhi untuk kendali
Tsukuba FM3.

### Tahap 7: NewYork 23 dapat dibalap dengan data FM3 sendiri (2 November 2026)

`newyork_proto.py --convert` (PVS v27, RMB v5, nama AI kanonik, AI tanpa donor), run
`track-ny-conv-8`: **balapan berjalan sampai menu pause, tanpa crash**, dan kota NewYork
FM3 tampil di tampilan utama. Gambarnya masih gelap karena `TrackSettings.xml` FM3 tidak
punya parameter pencahayaan FM4 (gejala yang sama dengan `tsukuba-fm3full`).

Tiga penyebab yang dibuktikan dengan `crash_stack.py` (debugger yang mencetak stack,
register guest r0..r31 dari konteks recompile di `rdi`, dan memori guest):

1. **Sel istimewa PVS.** `CullPass3` membaca zona di luar `l4`. Ini terjadi dengan donor AI
   CrownJewel (zona 136–138, sedangkan NewYork punya 59). Di FM4 sendiri, ribbon tanpa
   sel `l68` (AmalfiGP 01) menaruh sel istimewa di slot 0 `a84`/`a100`, bukan slot 1.
   `pvs.to_v27` kini mengikuti bentuk ribbon v27 FM4: `u4` = `0x4FFF0044`,
   `a116 = [objek]`, slot 0 bila `l68` kosong.
2. **Berkas MLP AI pendek di ZIP.** Pembaca MLP (`82CF42E0`) selalu membaca 1280 byte
   pertama dalam satu panggilan. Dari ZIP yang di-mount, anggota yang lebih pendek gagal,
   sehingga `.seg` NewYork_01 (973 byte) tidak termuat. Dump objek data AI menunjukkan
   `.geo` lengkap (1454 waypoint, CRC cocok) tetapi `iNumSegments` 0 dan `iStart` null,
   lalu `CMLPMatrix` crash. Tsukuba lolos karena AI-nya berkas lepas di disc, dan
   CrownJewel 19_R karena semua berkasnya ≥ 1280 byte. Perbaikan: padding nol sampai
   1280 byte (offset data MLP tidak berubah).
3. Hipotesis `hash.manifest` diuji dan **gugur**: `.seg` FM4 Tsukuba yang satu bitnya
   diubah tetap termuat (`track-tsukuba-seg-tamper2`).

**Pencahayaan.** FM4 menyetel ulang `TrackSettings` setiap track (cahaya, ambient,
specular, SH, tone map). Pada pasangan Tsukuba/AmalfiGP/Catalunya/Suzuka, 47–75 nilai
bersama berbeda tanpa rumus tunggal, misalnya `LightColor` 1,7 → 0,85 dan
`GlobalSpecularLevel` 1 → 5. Run `track-ny-conv-9` (`--settings-donor Tsukuba`, yaitu
`TrackSettings.xml` FM4 utuh): NewYork terang dan wajar (gedung, kerumunan, pembatas, papan
iklan), tanpa crash.

Bisect AI (run `track-ny-bis-a..d`): donor `.geo/.irt/.seg/.pit` lolos dari pembuatan AI,
donor `.seg` saja mengubah crash, dan donor `.irt` saja tidak. Itu yang mengarah ke `.seg`.

### Tahap 8: converter environment dan paket gabungan (3 November 2026)

`fm4_converter.fm3.track_env` mengemas NewYork, Amalfi, TestTrackinfield dan LeMans 102
di atas paket mobil (`--base`), menjadi satu overlay. Temuan selama uji game:

| Gejala | Penyebab | Perbaikan |
|---|---|---|
| Grid Amalfi gagal dikonversi | layout point-to-point mulai di `Tracks.StartLine` (fraksi panjang garis AI 2D; selisih dengan start FM4 0,3–17 m); jalan yang melintas dekat dirinya; grid FM3 8 mobil; grid dua lajur LeMans | `track_grid`: start fraksional, proyeksi minimum lokal terdekat ke garis start, grid diperpanjang per baris empat, toleransi pasangan 2 m |
| Layout reverse salah | `ReverseIndex` = ribbon geometri, bukan tanda reverse | reverse = ada berkas AI `<media>_NN_R` (cocok 116/116 layout FM4) |
| NewYork crash di road detail (`8290F4E8`) pada setiap layout dengan paket penuh | tekstur road detail FM3 | tipe tekstur road detail `0x14` → `0x04` di `l20`; jalan tetap bertekstur |
| Amalfi tidak tampil di menu lokasi | (1) `ContentId` 96 paket DLC FM3, `IsInstalled` 0; (2) menu lokasi FM4 hanya memuat 30 environment | `ContentId` 0, `IsInstalled` 1; layout Amalfi dan LeMans 102 bergabung dengan environment FM4 AmalfiGP dan LeMans (lokasi yang sama), nama layout yang bentrok diberi " (FM3)" |
| LeMans Bugatti trap saat memuat audio | FMOD dibuka sebagai `Audio\Tracks\LeMansBugatti\lemans.fev` | nama berkas audio asli dipertahankan |
| Langit abu-abu | langit = objek istimewa `a84[SkyboxIndex]`: model `<track>out.{i:05d}.rmb.bin`, `ids` = shader `sky_diff_1` di `l172`. FM3 menyimpan langit di `.sky.rmb.bin`, dan objek legacy tanpa shader | model langit disalin ke indeks objek, shader diisi, slot = `SkyboxIndex` `TrackSettings` |

Uji: Sidewinder Layout A, Bugatti Circuit, NewYork Old Circuit dan Amalfi Stage A berjalan
tanpa crash, dengan 365–1019 draw shader track di pass utama dan langit tampil.

Uji lengkap paket v3 (`fm3-content-v3`, 3 November 2026): **33/33 layout** (NewYork 4,
Bugatti 1, Amalfi 10, Sidewinder 18) dipilih lewat menu Quick Race (teks layout dicek
OCR, kecuali layout pertama daftar yang tidak perlu dipilih), balapan AI 12 mobil
berjalan ≥ 45 detik tanpa crash, dan pass utama merekam 132–1022 draw shader track.
Frame jeda layout dengan draw paling sedikit (Sidewinder E, I Reverse) menampilkan
track dan langit, dan urutan AI berubah selama balapan.

Paket v4 (v3 + CrownJewel 170): Extreme Circuit Reverse dan NewYork Old Circuit
berjalan tanpa crash. Judul lokasi Camino Viejo tidak terbaca OCR, jadi uji memilihnya
dengan satu tekan Right dari Bernese Alps.

Catatan konvensi: `dirsize` entri `zipmanifest.xml` FM4 = ukuran direktori pusat +
22. `integration.extend_zip_manifest` menulis tanpa +22, dan mount itu tetap bekerja
(paket mobil, `stringtables.zip`).

## Rencana tahap berikut

1. **Tidak ada layout lain dengan pola CrownJewel 170.** `plan_row` menolak 33
   layout FM3-only lainnya:
   - geometri sendiri: NewYork 22/23, LeMans 102, Amalfi 120;
   - reverse dari ribbon yang layout majunya juga hilang di FM4: NewYork 24/25,
     Amalfi 122–126 dan 128–131;
   - tidak ada di DB Disc 1 FM3 karena berasal dari Ultimate Track Pack:
     TestTrackinfield 49–66.

   Semua layout itu memerlukan geometri atau aset dari FM3/DLC (tahap 2–4). Berkas
   baru tetap dikirim lewat ZIP mount.
2. **Konverter biner track FM3 → FM4** (prasyarat NewYork, LeMans 102, Amalfi). Bandingkan
   `stx.bin` (bagian CAFF), RMB v4/v6 dan BIX0/BIX1 pada pasangan Tsukuba FM3/FM4,
   telusuri struct road detail `+308` (sumber, ukuran, jumlah), lalu ukur kemajuan
   dengan uji kendali Tsukuba (`bin.zip` FM3 di disc FM4) sampai dapat dibalap.
   Setelah itu NewYork: isi AI (temuan 2) dan UI (logo, mini ribbon, gambar
   environment dari `Textures.zip` FM3).
3. **LeMans 102**: periksa apakah `bin.zip` FM4 masih memuat geometri khusus Bugatti.
4. **NewYork**, lalu Amalfi dan TestTrackinfield (aset besar dari paket Disc 2/DLC).
5. UI: logo, mini ribbon, `SatImageName`, nama layout/environment di string table.

## Batas bukti

Kesamaan header dan wadah tidak membuktikan isi berkas kompatibel. Identitas AI
hanya diperiksa pada Tsukuba. Kecocokan start grid diukur pada lima layout dengan
pasangan; offset garis start belum diturunkan. Satu-satunya uji game adalah
CrownJewel 170 di Motorsport DX (lihat di atas). Paket v4 dapat dibalap; berkas
lepas baru tidak ditemukan game. Tidak ada aset yang dipasang ke profil.
