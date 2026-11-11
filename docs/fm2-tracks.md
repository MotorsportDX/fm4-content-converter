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
| langit (`<media>out.sky.rmb.bin`) | Tsukuba `Tsukubaout.00006` | `sky_diff_1` (16 byte) |

Semua teknik ini hanya membaca tekstur diffuse (sampler 0) dan lightmap (sampler 7, tekstur kedua
model PVS), menurut tabel konstanta shader `.fxobj` (`fm3.effect_audit`). Vertex 24 byte FM4
(posisi float3, normal `2_10_10_10`, UV0 dan UV lightmap `16_16`) sama dengan vertex FM2 yang
paling umum, jadi posisi dan normal dibawa apa adanya. Command buffer, material, dan file shader
template dipertahankan; yang diganti hanya geometri, jumlah indeks dan tipe primitif `DRAW_INDX`,
dan konstanta vertex shader `c0` (`UVOffsetScale`, ditemukan satu kali per slot).

## Data per draw

- **Program gambar** (`.stream`): op 1 menggambar (primitif, jumlah indeks, objek index buffer),
  op `0x2d` tipe 0 mengikat tekstur PVS ke sampler (indeks daftar model, sampler << 16), op
  `0x0c` render state (`0x38` cull mode, `0x60` alpha test).
- **Buffer**: tabel resource di ujung render graph; satu draw memakai vertex buffer terakhir yang
  mulai sebelum index buffer-nya. Stride dipilih dari instruksi `vfetch` shader (posisi float3 di
  offset 0), tata letak dari datanya: kata setelah posisi adalah normal bila hampir semuanya
  vektor satuan, selain itu koordinat tekstur. Tanpa normal, normal dihitung dari segitiga.
- **Koordinat tekstur** FM2 fixed point bertanda 1.14. UV0 ditulis sebagai pecahan rentangnya
  sendiri dengan rentang itu sebagai `UVOffsetScale` mesh; UV lightmap sebagai pecahan 0 sampai 1.
- **Tekstur**: lightmap adalah tekstur terikat dengan flag lightmap (`0x8`) di tabel tekstur;
  diffuse adalah tekstur warna (`0x4`) terikat pada sampler terendah. Tekstur dan BIX FM2 dibawa
  apa adanya (format `stx.bin` sama dengan FM3, yang sudah dibaca FM4). Skala-u atlas lightmap
  FM2 negatif di semua entri (FM3 dan FM4 positif dengan offset yang sama); nilai absolutnya
  dipakai.

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
  dipasang di record tekstur warna, lightmap, dan langit di `stx.bin` dan file tekstur tunggal
  `_0x%08X.bin` (tanpa mengubah ukuran); aspal, gedung, dan langit lalu tampil dengan kontras
  track FM4 (run `fm2ny2xc`, 2x).

## Hasil, 11 November 2026

FM4 USA Disc 1, disc FM2 USA, BuildRoot `I:\FM4-build-usa`, mod `fm2-cars`, `fm2-tracks`,
`fm2-career` (karier 307 hari; dengan `fm2-tracks` hari pertamanya di Test Track):

| Environment | Objek | Uji game |
| --- | --- | --- |
| New York | 4,645 (2,295 opaque, 1,040 dua sisi, 922 alpha test, 383 tanpa lightmap, 5 langit) | run `fm2ny9`: event karier di layout 22 sampai selesai (AI, 3 lap), layar pasca-balapan, lalu tawaran hari berikutnya |
| Test Track | 2,918 dari 3,031 draw | run `fm2tt2`: hari pertama karier FM2 (layout 53) sampai selesai, lalu tawaran layout 50 |

## Batas

- Material FM2 disederhanakan ke diffuse dan lightmap: peta specular, bump, dan refleksi FM2
  tidak dibawa; jalan memakai teknik diffuse biasa, bukan teknik jalan FM4.
- Draw tanpa lightmap memakai warna vertex abu-abu tetap.
- Langit FM2 terdiri dari lima draw (tutup dan empat panel); FM4 menggambar satu sebagai langit
  khusus dan semuanya sebagai objek biasa.
- 113 draw Test Track (vertex stride 24 dengan tata letak lain, dibaca shader dari dua stream)
  belum dikonversi.
- FM2 tidak punya gambar environment; gambar Road Atlanta dipakai sebagai pengganti.
- Suara penyiar dan suara kota FM2 tidak ada; hanya kerumunan, pantulan, angin, dan ambience balap.
- Baru satu layout tiap environment yang dibalap sampai selesai; layout lain berbagi file yang sama.
