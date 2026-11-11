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
tidak punya probe SH), file AI dengan nama FM4 dan dipad 1,280 byte, file collision, crowd, dan
kamera FM2 apa adanya, audio FM2 dengan decision zones Infineon. Database FM2 tidak punya tabel
environment: setiap environment FM2 mendapat environment FM4 baru (nama dari converter, negara
dan gambar Road Atlanta sebagai pengganti). Grid start FM2 sama dengan FM3 (12 posisi dunia,
`fm3.track_grid`). Flying start FM2 mendapat ID baru karena FM4 memakai ID FM2 untuk track lain.
Nama layout dari `Tracks.str` FM2 per bahasa, pada halaman tabel FM4 (referensi FM2 ada di
halaman lain).

## Batas

- Material FM2 disederhanakan ke diffuse dan lightmap: peta specular, bump, dan refleksi FM2
  tidak dibawa; jalan memakai teknik diffuse biasa, bukan teknik jalan FM4.
- Draw tanpa lightmap memakai warna vertex abu-abu tetap.
- Langit FM2 terdiri dari lima draw (tutup dan empat panel); FM4 menggambar satu sebagai langit
  khusus dan semuanya sebagai objek biasa.
- 113 draw Test Track (vertex stride 24 dengan tata letak lain, dibaca shader dari dua stream)
  belum dikonversi.
- Logo, ribbon mini, dan gambar environment FM2 belum dikonversi; pengganti dari Road Atlanta.
