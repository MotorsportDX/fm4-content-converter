# FM2 → FM4: track FM2

Jalur ini mengonversi environment FM2 yang tidak ada di FM4: **New York** (layout 22 dan 24) dan
**Test Track** (`TestTrackinfield`, 18 layout, ID 49 sampai 66). Hasilnya paket mod `fm2-tracks`
(format 2, [format paket mod](mod-format.md)) yang dibangun di atas FM4 Disc 1 saja. Bila paket
`fm3-tracks` ikut dimainkan, `compose` memakai environment FM3 untuk New York dan Test Track
(identitasnya bertumpuk, game yang lebih baru menang), jadi FM2 tetap berdiri sendiri tanpa FM3.

Source: [`fm2/track_models.py`](../src/fm4_converter/fm2/track_models.py) (model dan PVS) dan
[`fm2/track_env.py`](../src/fm4_converter/fm2/track_env.py) (environment, database, file). Riset
format ada di [`research/tracks-fm2-2026-11-11`](../research/tracks-fm2-2026-11-11/) dan di dokumen
FM4-PC `docs/analysis/independent-mods.md`, bagian 5.

```powershell
python -m fm4_converter.cli convert --game fm2 --content tracks --disc <disc FM2> `
    --fm4 <folder FM4 Disc 1> --content-root <DLC FM4> --helper <carbin-cpu.exe> --out <paket-baru>
```

## Kenapa model FM2 ditulis ulang

Track FM2 dua generasi lebih tua dari FM4: model FM2 adalah render graph (`CAFF21.11.05.0034`)
dengan program gambar, buffer GPU, dan microcode shader FM2 sendiri, sedangkan FM4 menggambar
model track lewat command buffer yang direkam untuk shader FM4 (RMB v5/v6). PVS FM2 versi 11,
FM4 versi 27. Tidak ada pemetaan field per field, jadi setiap **draw** FM2 menjadi satu model FM4
satu-mesh yang ditulis dari model FM4 Disc 1 sebagai template:

| Jenis draw FM2 | Template FM4 | Teknik |
| --- | --- | --- |
| lightmap, satu sisi | Indianapolis `indiout.00034` | `diff_1_nocube` (24 byte) |
| lightmap, dua sisi (`D3DRS_CULLMODE` none) | Catalunya `Catalunyaout.01771` | `diff_spec_1_2sd_nocube` (24 byte) |
| lightmap, alpha test | Alps `alpsout.00065` | `diff_opac_2_2sd_nocube` (24 byte) |
| tanpa lightmap | Le Mans `LeMansout.00189` | `diff_nolm_vclr_1` (20 byte) |
| tanpa lightmap, alpha test | Autopark `autoparkout.01075` | `diff_opac_nolm_vclr_1` (20 byte) |
| campuran dua tekstur warna oleh mask, dan material tanpa tekstur warna | Alps `alpsout.00699` | `shldr_blnd_spec_3` (36 byte) |
| langit (`<media>out.sky.rmb.bin`) | Tsukuba `Tsukubaout.00006` | `sky_diff_1` (16 byte) |

Teknik selain campuran hanya membaca tekstur diffuse (sampler 0) dan lightmap (sampler 7, tekstur
kedua model PVS), menurut tabel konstanta shader `.fxobj` (`fm3.effect_audit`). Teknik campuran
membaca Blend_A dan Blend_B (dua tekstur warna yang di-tile), Blend_Value (mask satu kanal) dan
lightmap: `lerp(A * c0, B * c2, value)`; tint dan tiling template dijadikan 1. Vertex 24 byte FM4
(posisi float3, normal `2_10_10_10`, UV0 dan UV lightmap `16_16`) sama dengan vertex FM2 yang
paling umum, jadi posisi dan normal dibawa apa adanya. Command buffer, material, dan file shader
template dipertahankan; yang diganti hanya geometri, jumlah indeks dan tipe primitif `DRAW_INDX`,
dan konstanta vertex shader `c0` (`UVOffsetScale`, ditemukan satu kali per slot).

## Data per draw

- **Program gambar** (`.stream`): op 1 menggambar (primitif, jumlah indeks, objek index buffer),
  op `0x2d` tipe 0 dan 2 mengikat tekstur PVS ke sampler (indeks daftar model, sampler << 16;
  tipe 2 juga mengikat shadow map), op `0x0c` render state (`0x38` cull mode, `0x60` alpha test,
  `0x48` SRCBLEND, `0x150` alpha-to-mask), op `0x2e` dan `0x2` memasang shader, op `0x5`
  memuat konstanta vertex shader, op `0x16` dan `0x19` bercabang. Ikatan sampler terbawa dari
  draw sebelumnya.
- **Buffer**: tabel resource di ujung render graph; satu draw memakai vertex buffer terakhir yang
  mulai sebelum index buffer-nya. Stride dipilih dari instruksi `vfetch` shader (posisi float3 di
  offset 0), tata letak dari datanya: kata setelah posisi adalah normal bila hampir semuanya
  vektor satuan, selain itu koordinat tekstur. Tanpa normal, normal dihitung dari segitiga.
- **Koordinat tekstur** dibaca dari shader FM2 draw itu sendiri
  ([`fm2/track_shader.py`](../src/fm4_converter/fm2/track_shader.py)). Vertex shader FM2 mengambil
  kata koordinat sebagai integer mentah lalu meneruskannya dikali literal (`1/32767` untuk
  lightmap dan mask) atau lewat matriks `c_place2d_N_Mtx` dari op `0x5` (tiling tekstur warna,
  1 sampai 8,192 kali); pixel shader membaca tiap tekstur di salah satu interpolator itu,
  lightmap setelah transformasi atlas `c_uvAtlas`. Converter mengevaluasi microcode kedua shader
  sebagai fungsi affine dari kata vertex, jadi tiap sampler mendapat kata dan petanya sendiri.
  Program FM2 bercabang antar-pass dengan shader berbeda: dipilih pasangan VS/PS yang paling
  banyak membaca tekstur terikat, lalu PS terpanjang (material lengkap). Tekstur yang tidak
  dibaca PS dilepas dari draw. Bila shader tidak bisa diikuti, tata letak vertex lama dipakai
  (fixed point 1.14). UV0 ditulis sebagai pecahan rentangnya sendiri dengan rentang itu sebagai
  `UVOffsetScale` mesh; UV lightmap sebagai pecahan 0 sampai 1.
- **Tekstur**: lightmap adalah tekstur terikat dengan flag lightmap (`0x8`) di tabel tekstur;
  diffuse adalah tekstur warna (`0x4`) terikat pada sampler terendah, bukan mask satu kanal
  (`DXT5A`). Tekstur dan BIX FM2 dibawa apa adanya selain tanda gamma (format `stx.bin` sama
  dengan FM3, yang sudah dibaca FM4). Skala-u atlas lightmap FM2 negatif di semua entri: pixel
  shader FM2 membaca `ou + su * u` dengan u 0 sampai 1, jadi tile berada di kiri offset. Entri
  atlas dibawa apa adanya.
- **Material tanpa padanan langsung**: campuran rumput dan tanah Test Track (mask satu kanal per
  objek, lalu tekstur warna yang di-tile) memakai teknik campuran. Material tanpa tekstur warna
  (jalan Test Track, `Road32`: detail aspal satu kanal yang di-tile dikali konstanta) memakai
  teknik campuran dengan A = B = detail itu dan tint abu 0.3. Draw yang di-alpha-blend dengan
  alfa di tekstur tersendiri (tepi rumput `Road_Edge` Test Track, garis jalan New York) dibuang,
  karena template FM4 tidak bisa membaca alfa terpisah dari warna; yang alfanya ada di tekstur
  warna `DXT5` menjadi alpha test, begitu pula draw dengan alpha-to-mask (kartu pohon).

## PVS versi 27

Satu model PVS dan satu instance per objek (draw). Posisi FM2 sudah di ruang dunia, jadi
instance-nya identitas dengan bentuk instance unik FM4 (`u12` -1, lightmap dari model PVS),
flag instance disalin dari instance template. Kotak batas objek: matriks identitas dengan pusat,
dan setengah ukuran. Zona dan tabel tekstur FM2 dipakai apa adanya; daftar instance zona adalah
objek semua model zona itu, ditambah objek langit di setiap zona. Daftar visibilitas zona diisi
0. Objek langit pertama juga menjadi sel langit khusus FM4 pada slot `SkyboxIndex` dari
`TrackSettings.xml` donor.

## File lain dan database

Seperti track FM3 ([`fm3/track_env.py`](../src/fm4_converter/fm3/track_env.py)): pencahayaan dari
`TrackSettings.xml` dan `staticCarCubemap.xpr` Tsukuba dengan batas yang sama (track FM2 juga
tidak punya probe SH), file collision dan crowd FM2 apa adanya. Database FM2 tidak punya tabel
environment: setiap environment FM2 mendapat environment FM4 baru (nama dari converter, negara
dan gambar environment Road Atlanta sebagai pengganti). Grid start FM2 sama dengan FM3 (12 posisi
dunia, `fm3.track_grid`). Flying start FM2 mendapat ID baru karena FM4 memakai ID FM2 untuk track
lain. Nama layout dari `Tracks.str` FM2 per bahasa, pada halaman tabel FM4 (referensi FM2 ada di
halaman lain). Logo dan ribbon mini FM2 (`.xds` di `UI/Textures.zip`, header Xenos yang sama
dengan FM3 dan FM4) dibawa di folder UI FM2 sendiri.

Yang ditemukan lewat uji game (setiap butir membuat FM4 crash sampai ditangani):

- **AI per level.** Selain file garis AI (`.geo`, `.irt`, `.seg`, `.pit`, dengan nama FM4 dan
  dipad 1,280 byte), FM4 memuat `AI\Tracks\Level1..3\<track>.bin` dan
  `AI\Tracks\SegmentProfiles\<track>` saat driver AI dibuat; tanpa itu FM4 membaca level null
  (`sub_82A94158`, layar pre-race). FM2 punya ketiganya; semua dibawa.
- **Audio.** Bank FMOD FM2 (FEV versi 0x21 dan FSB3) lebih tua dari yang dibaca FMOD FM4 (FEV
  0x40), dan XML ribbon-nya memakai nama atribut huruf kecil. Bank Tsukuba (donor yang sama)
  dipakai; emitter kerumunan dan pantulan FM2 ditaruh di posisi FM2 dengan event bersama FM4
  (`SharedDynamicAudio`, `SharedStaticAudio`); suara kota khas FM2 (sirene, subway) tidak punya
  padanan dan dibuang. Decision zones dari Infineon seperti track FM3.
- **Kamera siaran** (`TrackSegCams.xml`, replay dan pasca-balapan): format FM2 lebih tua (root
  `TrackSegCams`, key di bawah `Keys`, tanpa `NumCams`); FM4 membaca kamera null di layar
  pasca-balapan (`sub_8268D4F8`). Kamera animasi FM2 ditulis ulang dalam format FM4 dengan
  bingkai kamera Tsukuba; potongan bumper, kap, dan roda dibuang.
- **Kamera pre-race**: FM2 tidak punya; `preracecams.xml` Alps (semua relatif terhadap mobil).
- **Gamma tekstur.** Tekstur track FM2 linear (`D3DFORMAT` `0x1A200152`), sedangkan tekstur warna dan
  lightmap FM4 dibaca lewat gamma perangkat keras (`0x1A207F52`, sign X, Y, Z = 3). Shader FM4
  membaca tekstur FM2 linear terlalu terang: aspal New York tampak putih keabuan. Tanda gamma
  dipasang di record tekstur warna, lightmap, dan langit di `stx.bin`, di file tekstur tunggal
  `_0x%08X.bin`, dan di header `BIX0` (+0x10) file `.bix`, tekstur ukuran penuh yang dimuat
  bertahap (tanpa mengubah ukuran). Mask satu kanal tetap linear.

## Hasil, 11 November 2026

FM4 USA Disc 1, disc FM2 USA, BuildRoot `I:\FM4-build-usa`, mod `fm2-cars`, `fm2-tracks`,
`fm2-career` (karier 307 hari; dengan `fm2-tracks` hari pertamanya di Test Track):

| Environment | Objek | Uji game |
| --- | --- | --- |
| New York | 4,645 (2,295 opaque, 1,040 dua sisi, 922 alpha test, 383 tanpa lightmap, 5 langit) | run `fm2ny9`: event karier di layout 22 sampai selesai (AI, 3 lap), layar pasca-balapan, lalu tawaran hari berikutnya |
| Test Track | 2,918 dari 3,031 draw | run `fm2tt2`: hari pertama karier FM2 (layout 53) sampai selesai, lalu tawaran layout 50 |

## Batas

- Material FM2 disederhanakan ke diffuse, campuran, dan lightmap: peta specular, bump, dan
  refleksi FM2 tidak dibawa; jalan memakai teknik diffuse atau campuran, bukan teknik jalan FM4.
  Warna jalan Test Track adalah tint tetap, bukan rumus pixel shader FM2.
- Tepi rumput Test Track dan garis jalan New York yang di-alpha-blend tidak ada (lihat di atas).
- Draw tanpa lightmap memakai warna vertex abu-abu tetap.
- Langit FM2 terdiri dari beberapa draw (New York: tutup dan empat panel; Test Track: kilau
  matahari, kubah, panorama, dan cincin kabut berwarna tetap). Kilau matahari dan draw tanpa
  tekstur dibuang; draw tertinggi (panorama) menjadi langit khusus FM4 dan semuanya juga objek
  biasa.
- 113 draw Test Track (quad kecil dua segitiga, vertex stride 24 dengan tata letak lain, dibaca
  shader dari dua stream) belum dikonversi.
- FM2 tidak punya gambar environment; gambar Road Atlanta dipakai sebagai pengganti.
- Suara penyiar dan suara kota FM2 tidak ada; hanya kerumunan, pantulan, angin, dan ambience balap.
- Baru satu layout tiap environment yang dibalap sampai selesai; layout lain berbagi file yang sama.
