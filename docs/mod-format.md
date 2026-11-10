# Konversi satu perintah dan format paket mod

`fm4_converter.cli` menjalankan seluruh jalur FM3 → FM4 atau FM2 → FM4 dari disc milik
pemain dan menghasilkan satu **paket mod** (format 2): item-item yang ditambahkan paket ke FM4
Disc 1 beserta `mod.json` yang dibaca launcher, misalnya Motorsport DX. Paketnya berisi mobil
FM3, mobil FM2, atau track FM3 (`--content tracks`). Setiap paket dibangun di atas FM4 Disc 1
saja, jadi paket mana pun bisa dimainkan sendiri atau bersama paket lain:
[`compose`](#komposisi) menggabungkannya saat dimainkan. Converter tidak menjalankan game.

## Menjalankan

```powershell
python -m fm4_converter.cli convert --game fm3 `
    --disc "<FM3 Disc 1: folder atau .iso>" --disc2 "<FM3 Disc 2: folder atau .iso>" `
    --fm4 "<folder FM4 Disc 1>" --content-root "<...\4D530910\00000002>" `
    --helper "<carbin-cpu.exe>" --out "<folder paket baru>" --json

python -m fm4_converter.cli convert --game fm2 `
    --disc "<disc FM2>" --bonus-disc "<Bonus Disc FM2>" `
    --fm4 "<folder FM4 Disc 1>" --content-root "<...>" --helper "<carbin-cpu.exe>" --out "<folder baru>"

python -m fm4_converter.cli convert --game fm3 --content tracks `
    --disc "<FM3 Disc 1>" --disc2 "<FM3 Disc 2>" --fm4 "<folder FM4 Disc 1>" `
    --content-root "<...>" --helper "<carbin-cpu.exe>" --out "<folder baru>"

# Disc mod: paket-paket di atas FM4 Disc 1, mobil atau track game yang lebih baru menang
python -m fm4_converter.compose --fm4 "<folder FM4 Disc 1>" --content-root "<...>" `
    --out "<folder overlay baru>" "<paket fm2-cars>" "<paket fm3-cars>" "<paket fm3-tracks>"

python -m fm4_converter.cli identify "<folder atau .iso>"   # game, nomor disc, peran
python -m fm4_converter.cli verify "<folder paket>"         # cek hash setiap berkas
```

Setelah `pip install -e .`, perintah yang sama tersedia sebagai `fm4-convert`.

| Argumen | Isi |
|---|---|
| `--content` | `cars` (bawaan) atau `tracks`. Track hanya untuk `--game fm3`; track FM2 (New York dan Test Track) sedang dikerjakan (lihat [Track](#track)). |
| `--disc` | FM3 Disc 1 (rilis asli atau Ultimate Collection) atau disc FM2. Folder hasil ekstrak (berisi `default.xex`), folder `Media`-nya, atau image `.iso` (Redump maupun hasil rebuild). Edisi FM3 (`fm3` atau `fm3-uc`) dibaca dari database disc: hanya database Ultimate Collection yang punya Test Track. |
| `--disc2` | FM3 Disc 2 (Content Install Disc), opsional. Tanpa disc ini, mobil yang asetnya hanya ada di Disc 2 dilewati (`skipped`), begitu juga Amalfi pada `--content tracks`. |
| `--bonus-disc` | Bonus Disc FM2, opsional. Tanpa disc ini, mobil DLC FM2 dilewati. |
| `--fm4` | Folder FM4 Disc 1 yang sudah diekstrak, yaitu folder yang dimainkan launcher. Image FM4 ditolak. |
| `--content-root` | DLC FM4 yang terpasang. Converter mengambil merek dan velg yang hanya ada di pack ini (mobil itu lalu mencatat pack-nya di `requires`); kunci dan tabel nama pack diurus `compose` saat dimainkan. |
| `--helper` | `carbin-cpu.exe` hasil [build helper](../tools/carbin_cpu/README.md). |
| `--cache` | Folder untuk berkas yang diekstrak dari `.iso`, DLC FM2, model FM2, dan disc kerja builder (`stage-<game>-<content>`). Bila diberikan, folder ini disimpan supaya proses berikutnya bisa melanjutkan. Bila tidak, dipakai `<out>.cache` yang dihapus setelah berhasil. |
| `--cars` | Hanya MediaName tertentu. |
| `--json` | Progres sebagai JSON lines di stdout; log converter pindah ke stderr. |

Mobil yang dikonversi: semua mobil game sumber yang ID-nya tidak ada di FM4 Disc 1, termasuk
mobil yang juga ada di pack DLC FM4 (`compose` meninggalkannya selama pack itu terpasang).
Untuk FM2 itu 119 mobil disc dan Bonus Disc, 64 di antaranya juga ada di FM3.

Setiap disc dicek dari `default.xex` (title ID dan nomor disc) sebelum konversi dimulai,
sehingga disc yang salah ditolak dengan pesan yang jelas. Dari image, hanya folder yang
dibutuhkan yang diekstrak: database, mobil, velg, tabel nama dan thumbnail; untuk Disc 2 dan
Bonus Disc, paket kontennya.

Kalibrasi diambil dari data beku di [`src/fm4_converter/data`](../src/fm4_converter/data/__init__.py),
yaitu aturan yang dipakai paket `fm3-only-v3` dan FM2 `package-v5`. Setiap berkas dicek
dengan SHA-256 saat dibaca.

## Event progres (`--json`)

Satu objek JSON per baris:

```json
{"event": "stage", "stage": "check", "message": "Checking the discs"}
{"event": "extract", "role": "fm3-disc1", "file": "Media/Cars/X.zip", "done": 123, "total": 456}
{"event": "stage", "stage": "package", "message": "Converting 81 FM3 cars"}
{"event": "car", "index": 1, "total": 81, "car": "CHE_Cobalt_05", "status": "packaged", "error": null}
{"event": "track", "index": 1, "total": 3, "track": "NewYork", "status": "packaged", "error": null}
{"event": "done", "package": "...", "mod": "...\\mod.json", "packaged": 81, "failed": 0, "skipped": 0}
{"event": "error", "message": "DiscError: ..."}
```

`stage` bernilai `check`, `extract`, `dlc` (khusus FM2), `package`, lalu `describe`. Event
`extract` dikirim paling sering dua kali per detik. `--content tracks` mengirim `track`
(satu per environment) sebagai ganti `car`. Kode keluar 0 berarti paket selesai dan
lolos `verify`; 1 berarti ada event `error`. Mobil yang gagal tidak menghentikan mobil lain;
paket tetap ditulis selama minimal satu mobil berhasil.

## Isi paket

```text
<paket>/
  mod.json         Dibaca launcher
  items.json       Item paket: baris database, nama, berkas, member arsip bersama
  files/Media/...  Berkas utuh item (ZIP mobil, velg, track, audio lepas) dengan tata letak FM4 Disc 1
  files/<arsip>/<member>   Member arsip bersama milik item (thumbnail, audio CMT, AI track, UI)
```

Builder menulis overlay lengkap (termasuk database kerja) ke `stage-<game>-<content>` di folder
cache; paket hanya mengambil berkas dan member yang disebut item-itemnya
([`items`](../src/fm4_converter/items.py)).

## `mod.json`, versi 2

| Field | Isi |
|---|---|
| `format`, `format_version` | `"fm4-mod"`, `2` |
| `id`, `name`, `kind`, `source_game` | Misalnya `"fm3-cars"`, `"FM3 cars"`, `"car-overlay"`, `"FM3"`; untuk track `"fm3-tracks"`, `"FM3 tracks"`, `"track-overlay"` |
| `edition` | `fm2`, `fm3` (rilis asli) atau `fm3-uc` (Ultimate Collection) |
| `priority` | FM2 20, FM3 30: item paket berprioritas lebih tinggi menang |
| `created`, `converter` | Waktu UTC, nama dan versi converter |
| `experimental` | Selalu `true` untuk sekarang |
| `files_root`, `files` | `"files"`; `{path: {sha256, size}}` untuk setiap berkas di `files/` |
| `items_file`, `items_sha256` | `"items.json"` dan hash-nya |
| `archives` | `{arsip bersama: {priority, root}}`: arsip yang member-nya disimpan per item |
| `cars`, `tracks` | Ringkasan item: `{key, media, name, status, requires, identity, error}`; status `packaged`, `failed` atau `skipped` |
| `packaged`, `failed`, `skipped` | Jumlah item |
| `requires` | Pack DLC FM4 yang dibutuhkan sebagian item (misalnya Porsche Expansion) |
| `sources` | Disc yang dibaca: peran, path, folder atau iso, title ID, nomor disc, media ID |
| `built_against` | FM4 Disc 1 (media ID, hash `gamedb.slt` dan `zipmanifest.xml`) dan daftar pack DLC saat konversi; untuk catatan, `compose` tidak memeriksanya |
| `notes` | Catatan untuk ditampilkan ke pemain |

## `items.json`

Satu objek per mobil (`car:<Id>`), environment track (`environment:<MediaName>`) atau layout di
geometri FM4 (`layout:<id>`):

| Field | Isi |
|---|---|
| `identity` | ID mobil (`cars`) dan MediaName-nya (`car_media`), ID track (`tracks`), MediaName environment (`environments`). Dua item dengan identitas yang sama adalah mobil atau track yang sama. |
| `rows`, `updates` | Baris yang disisipkan item dan baris Disc 1 yang diubahnya, `{table, row}`. Dicatat dengan trigger SQLite sementara saat builder menulis database kerja (`items.Recorder`). |
| `renumber` | Kunci yang boleh dipindah `compose`: `{table, column, rows, refs}`, dengan `rows` indeks baris pemegang kunci dan `refs` pasangan `[indeks baris, kolom]` yang merujuknya (sisi graf stok mobil, atau `EnvironmentId` dan `DefaultStartGridPositionsId` track). `block` (misalnya 100 untuk `Tracks.MPSortOrder`) memindah nilai sekelompok. |
| `strings` | Nama: `{table, key, page, symbol, texts, refs, reuse}`; `texts` per kode bahasa atau `"*"`; `refs` pasangan `[indeks baris, kolom]` yang memegang referensinya; `reuse` berarti kunci yang sudah dipakai FM4 adalah nama FM4 untuk hal yang sama |
| `files` | `{path: prioritas mount, atau null untuk berkas lepas}` |
| `members` | `{arsip bersama: [nama member]}` |
| `requires`, `status`, `error` | Pack yang dibutuhkan; status dan alasannya |

## Komposisi

FM4 hanya membaca satu `gamedb.slt`, satu `zipmanifest.xml` dan satu `stringtables.zip`.
[`compose`](../src/fm4_converter/compose.py) menulis overlay itu dari FM4 Disc 1 dan paket-paket
yang dipilih:

1. **Item.** Item paket berprioritas lebih tinggi menggantikan item paket lain yang berbagi
   identitas (FM3 atas FM2). Item yang mobil atau track-nya ada di pack DLC terpasang
   ditinggalkan, dan item yang butuh pack yang tidak terpasang ditinggalkan sebelum paket
   dibandingkan, sehingga item game yang lebih lama bisa menggantikannya.
2. **Database.** Salinan database Disc 1 dengan baris dan perubahan item pemenang. Kunci di
   `renumber` yang sudah dipegang baris lain atau pack DLC dipindah ke kunci bebas berikutnya,
   di baris pemegang dan baris perujuknya. Kunci lain yang bentrok menghentikan komposisi.
3. **Nama.** Per tabel (`Data_Car.str`, `Tracks.str`, `Environments.str`), nama pemenang memakai
   kuncinya sendiri bila bebas, selain itu kunci bebas tertinggi, dan referensinya ditulis ke
   baris itemnya. `Media/stringtables.zip` membawa tabel yang dibaca game sekarang (Disc 1, Disc
   2, DLC terpasang) dengan nama tambahan, satu prioritas di atasnya.
4. **Arsip.** Arsip bersama disusun dari member pemenang (di atas member Disc 1 bila Disc 1
   punya arsip itu); berkas utuh pemenang di-hardlink; `zipmanifest.xml` me-mount semuanya
   dengan konvensi FM4 sendiri (`dirsize` termasuk 22 byte rekaman akhir ZIP).

`compose.json` di overlay mencatat pemenang, item yang ditinggalkan beserta alasannya, dan asal
setiap berkas. Launcher menaruh berkas Disc 1 lainnya di sampingnya.

## Track

`--content tracks` menjalankan [`fm3.track_env`](../src/fm4_converter/fm3/track_env.py) dengan
disc pemain: environment NewYork (22–25), Amalfi (10 layout, dari Road Racing Track Pack di
FM3 Disc 2), LeMansBugatti (LeMans 102 sebagai environment sendiri) dan layout CrownJewel 170
(geometri FM4). TestTrackinfield (18 layout) butuh Disc 1 dan Disc 2 Ultimate Collection
(database dan Forza Ultimate Track Pack); tanpa keduanya environment ini dilewati
(`skipped`) dengan alasannya. Isi dan status uji ada di [fm3-acceptance.md](fm3-acceptance.md).

Pencahayaan setiap environment berasal dari track FM4 donor: `TrackSettings.xml` dan
`staticCarCubemap.xpr` (NewYork dari Tsukuba, Amalfi dari AmalfiGP, LeMansBugatti dari
LeMans). Cube FM3 tidak dipakai: formatnya LDR, sedangkan FM4 memakai cube HDR yang diskalakan.
Beberapa nilai `TrackSettings.xml` diubah: SHTop dibatasi 0,07, karena track FM3 tidak punya probe
SH (`<track>_ribbonNN.sh`) yang menjadi pasangan nilai itu di FM4; `CockpitDirectionalScalar`
(matahari langsung di kokpit) dibatasi 1,5, karena nilai FM4 5 membuat dasbor, setir dan sarung
tangan hampir putih di ruas NewYork yang terkena matahari; angkatan exposure kamera kokpit di
pemandangan gelap (`Exp_ExtraDark` di `ToneMapCockpitExposure`) dibatasi 0,75 dan bloom
dibatasi cutoff 2 dan skala 2, karena jalan FM3 gelap dalam satuan FM4 sehingga lampu, papan
reklame dan langit NewYork terpotong menjadi kabut putih; dan `ShadowLightDirection` diambil
dari FM3. Tanpa itu kokpit menjadi putih (REPORT tahap 9–11,
[tracks-2026-11-02/REPORT.md](../research/tracks-2026-11-02/REPORT.md)).

Track FM2 yang tidak ada di FM4 adalah New York (layout 22 dan 24) dan Test Track (49 sampai 66);
FM3 dan Ultimate Collection punya keduanya dengan ID dan panjang yang sama. Formatnya dua
generasi lebih tua dari FM3: PVS versi 11, dan model track berupa kontainer CAFF berisi record
`rendergraph` 30.06.06.0036 (buffer vertex dan indeks, material dengan shader microcode-nya
sendiri) tanpa command buffer. Konverternya sedang dikerjakan.

Catatan: verifikasi di bawah ini dibuat dengan format 1 (paket bertumpuk); format 2 menggantikannya
pada 11 November 2026.

## Verifikasi 5 November 2026

Dijalankan dari folder disc USA (FM3 Disc 1 + 2, FM2 + Bonus Disc), FM4 Japan/Asia Disc 1
dan content root uji Motorsport DX, dengan `carbin-cpu-v9`:

| Jalur | Hasil | Dibanding paket teruji |
|---|---|---|
| FM3 | 81 dari 81 mobil, 8,5 menit | 119 dari 119 berkas identik dengan `fm3-only-v3` |
| FM2 | 55 dari 55 mobil, 3,7 menit (DLC sudah di cache) | 80 dari 103 berkas identik dengan `package-v5`; donor sama untuk 55 mobil |

Ke-23 berkas FM2 yang berbeda adalah ZIP mobil (dan `zipmanifest.xml`, yang mencatat
ukurannya). Di setiap ZIP hanya `_cockpit.carbin` yang berbeda. `package-v5` memakai ulang
model kokpit dari cache `models/` yang dibuat 4 November pukul 14:03, sebelum
`models.cockpit_renames` diubah dari nama material saja menjadi pasangan bagian/material
(commit `00b4be9`). CLI membangun model baru dengan aturan sekarang. Kokpit ke-23 mobil itu
belum diuji di game dengan aturan baru; mobil yang terdampak antara lain JAG_XK_07, Lancer
Evo VI–IX, RX-7 (INGS, AB Flug, RE Amemiya), Lotus Elise/Exige, dan Celica APR.

Pembacaan `.iso` diuji pada image FM4 USA Disc 1 dan Disc 2 (partisi XGD3): `gamedb.slt`
hasil baca identik dengan folder ekstrak. Image FM2 dan FM3 belum tersedia untuk diuji;
tes memakai image XDVDFS sintetis pada offset partisi 0 dan XGD3.

Konversi 7 November 2026 (FM4 USA Disc 1 dan pack DLC uji Motorsport DX, disc FM3 dan FM2 USA,
`carbin-cpu-v9`):

| Paket | Di atas | Hasil |
|---|---|---|
| FM2 | `fm3-cars` | 55 dari 55 mobil; database berisi semua mobil FM3 dan FM2 tanpa ID ganda; 136 nama terbaca di 18 bahasa; ZIP mobil dan velg FM2 identik dengan build tanpa tumpukan |
| Track FM3 | `fm3-cars`, `fm2-cars` | 3 environment dan CrownJewel 170 (16 layout baru, 1 environment baru); 639 mobil tetap ada; tidak ada entri nama mobil yang hilang; 1035 mount lama tetap dengan prioritas yang sama. TestTrackinfield dilewati (tanpa disc Ultimate Collection) |
| FM3 dari disc Ultimate Collection (USA) | FM4 Disc 1 | 91 mobil FM3-only (database UC berisi 510 mobil; disc biasa 415, dengan 81 mobil FM3-only), 36 di antaranya dari 8 paket Disc 2. 90 dari 91 jadi. AUD_R15Ultimate_09 gagal karena teknik `chrome2` (krom kedua FM3 di bodi dan pilar A kokpit) tidak ada di efek mobil FM4; kini `chrome2` diterima seperti `Material__1` (`appearance_audit.NATIVE_UNKNOWN_TECHNIQUES`), dan mobil itu jadi |

Di Motorsport DX, ketiga paket pertama dimainkan bersama dari satu disc mod: Quick Race dengan
XK coupe (FM2) di Bugatti Circuit dan SRT4 (FM3) di New York Circuit, dengan mobil FM3 dan FM2
di antara lawan AI, dibalap AI sampai memimpin tanpa crash. Forza Ultimate R15 (FM3) dibalap di
Le Mans tanpa crash dan tampil utuh di kamera kokpit dan chase.

## Batas

- Converter tetap butuh Python 3.11+, NumPy, Pillow, `carbin-cpu.exe`, dan decoder LZX
  `lzx_bridge.dll` ([`tools/lzx_bridge`](../tools/lzx_bridge/lzx_bridge.c) dengan `lzxd.c`
  libmspack). Variabel lingkungan `FM4_LZX_BRIDGE` menunjuk DLL itu; tanpa variabel ini
  dipakai build riset di `outputs/`. Launcher menyiapkan semuanya di komputer pemain.
- Audit animasi driver membaca empat berkas GR2 `Driver.zip` milik FM4 dengan DLL proprietary
  XMem dan Granny, yang hanya ada lokal dan tidak pernah dibundel. Tanpa keduanya, audit itu
  dilewati dan dicatat di `appearance_validation.json` (`driver_animation_validation.skipped`).
  Konversi penuh tanpa keduanya menghasilkan berkas yang sama: FM3 119 dari 119 dan FM2 103 dari
  103, dibanding hasil dengan keduanya.
- Image FM4 tidak diterima. Launcher sudah punya FM4 Disc 1 yang diekstrak.
- Data kalibrasi beku hanya mewakili rilis disc yang diuji: FM3 USA, FM2 USA, dan FM4
  USA atau Japan/Asia (database identik).
