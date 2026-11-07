# Konversi satu perintah dan format paket mod

`fm4_converter.cli` menjalankan seluruh jalur FM3 → FM4 atau FM2 → FM4 dari disc milik
pemain dan menghasilkan satu **paket mod**: berkas overlay untuk FM4 Disc 1 beserta
`mod.json` yang dibaca launcher, misalnya Motorsport DX. Paketnya berisi mobil FM3, mobil
FM2, atau track FM3 (`--content tracks`). Beberapa paket bisa dipasang bersamaan, seperti
pack DLC: setiap paket dibangun di atas disc yang sudah membawa paket sebelumnya (lihat
[Pemasangan bertumpuk](#pemasangan-bertumpuk)). Converter tidak memasang paket dan tidak
menjalankan game.

## Menjalankan

```powershell
python -m fm4_converter.cli convert --game fm3 `
    --disc "<FM3 Disc 1: folder atau .iso>" --disc2 "<FM3 Disc 2: folder atau .iso>" `
    --fm4 "<folder FM4 Disc 1>" --content-root "<...\4D530910\00000002>" `
    --helper "<carbin-cpu.exe>" --out "<folder paket baru>" --json

python -m fm4_converter.cli convert --game fm2 `
    --disc "<disc FM2>" --bonus-disc "<Bonus Disc FM2>" `
    --fm4 "<folder FM4 Disc 1>" --content-root "<...>" --helper "<carbin-cpu.exe>" --out "<folder baru>"

# Track FM3, dibangun di atas disc yang sudah membawa paket mobil FM3 dan FM2
python -m fm4_converter.cli convert --game fm3 --content tracks `
    --disc "<FM3 Disc 1>" --disc2 "<FM3 Disc 2>" --fm4 "<disc dengan kedua paket mobil>" `
    --base-package "<paket fm3-cars>" --base-package "<paket fm2-cars>" `
    --content-root "<...>" --helper "<carbin-cpu.exe>" --out "<folder baru>"

python -m fm4_converter.cli identify "<folder atau .iso>"   # game, nomor disc, peran
python -m fm4_converter.cli verify "<folder paket>"         # cek hash setiap berkas
```

Setelah `pip install -e .`, perintah yang sama tersedia sebagai `fm4-convert`.

| Argumen | Isi |
|---|---|
| `--content` | `cars` (bawaan) atau `tracks`. Track hanya untuk `--game fm3`; semua layout FM2 sudah ada di FM4 atau di versi FM3-nya (lihat [Track](#track)). |
| `--disc` | FM3 Disc 1 atau disc FM2. Folder hasil ekstrak (berisi `default.xex`), folder `Media`-nya, atau image `.iso` (Redump maupun hasil rebuild). |
| `--disc2` | FM3 Disc 2 (Content Install Disc), opsional. Tanpa disc ini, 26 mobil yang asetnya hanya ada di Disc 2 dilewati (`skipped`), begitu juga Amalfi pada `--content tracks`. |
| `--bonus-disc` | Bonus Disc FM2, opsional. Tanpa disc ini, empat mobil DLC FM2 dilewati. |
| `--fm4` | Folder FM4 Disc 1 yang sudah diekstrak, yaitu folder yang dimainkan launcher. Image FM4 ditolak. Untuk pemasangan bertumpuk: Disc 1 dengan paket di bawahnya sudah terpasang. |
| `--base-package` | Paket yang sudah dibawa folder `--fm4`, diulang untuk setiap paket menurut urutan pasangnya. Dicatat di `base_packages`. |
| `--content-root` | DLC FM4 yang terpasang. Kunci database dan tabel nama dari pack ini dihormati, jadi bangun paket terhadap DLC yang benar-benar dimiliki pemain. |
| `--helper` | `carbin-cpu.exe` hasil [build helper](../tools/carbin_cpu/README.md). Paket yang sudah diuji dibuat dengan `carbin-cpu-v9`. |
| `--cache` | Folder untuk berkas yang diekstrak dari `.iso`, DLC FM2 dan model FM2. Bila diberikan, folder ini disimpan supaya proses berikutnya bisa melanjutkan. Bila tidak, dipakai `<out>.cache` yang dihapus setelah berhasil. |
| `--cars` | Hanya MediaName tertentu. |
| `--json` | Progres sebagai JSON lines di stdout; log converter pindah ke stderr. |

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
  files/Media/...  Overlay dengan tata letak FM4 Disc 1
  manifest.json    Manifest lengkap converter (input, hash, keputusan per mobil)
  reports/         Laporan audit per mobil
```

## `mod.json`, versi 1

| Field | Isi |
|---|---|
| `format`, `format_version` | `"fm4-mod"`, `1` |
| `id`, `name`, `kind`, `source_game` | Misalnya `"fm3-cars"`, `"FM3 cars"`, `"car-overlay"`, `"FM3"`; untuk track `"fm3-tracks"`, `"FM3 tracks"`, `"track-overlay"` |
| `created`, `converter` | Waktu UTC, nama dan versi converter |
| `experimental` | Selalu `true` untuk sekarang |
| `files_root` | `"files"` |
| `files` | `{path: {sha256, size}}` untuk setiap berkas di `files/` |
| `replaces` | Path yang sudah ada di FM4 Disc 1 dan diganti (database gabungan, `zipmanifest.xml`) |
| `adds` | Path baru (ZIP mobil dan velg, `stringtables.zip`, `Thumbnails.zip`, audio) |
| `writes` | `replaces` + `adds`, untuk cek konflik |
| `cars` | `[{media, name, status, requires, error}]`, dengan status `packaged`, `failed` atau `skipped`; kosong pada `track-overlay` |
| `tracks` | Hanya pada `track-overlay`: `[{media, name, status, layouts, error}]` per environment (`layout_170` untuk CrownJewel 170) |
| `packaged`, `failed` | Jumlah mobil, atau environment pada `track-overlay` |
| `requires` | Pack DLC FM4 yang dibutuhkan sebagian mobil (misalnya Porsche Expansion) |
| `sources` | Disc yang dibaca: peran, path, folder atau iso, title ID, nomor disc, media ID |
| `built_against` | Disc yang dipakai saat membangun (media ID, hash `gamedb.slt` dan `zipmanifest.xml`; pada pemasangan bertumpuk, hash dari disc yang sudah membawa `base_packages`) dan daftar pack DLC (path relatif dan ukuran) |
| `base_packages` | `[{id, created}]` paket yang sudah dibawa disc itu, menurut urutan pasang; kosong untuk paket di atas FM4 Disc 1 saja |
| `notes` | Catatan untuk ditampilkan ke pemain |

## Aturan untuk launcher

1. Jalankan `verify` (atau cek `files` sendiri) sebelum memasang.
2. Pasang hanya bila disc di bawahnya dan pack DLC pemain sama dengan `built_against`:
   FM4 Disc 1 untuk paket tanpa `base_packages`, atau Disc 1 dengan `base_packages`
   terpasang. Bila berbeda, minta pemain membangun ulang paket: database dan tabel nama di
   paket adalah salinan gabungan dari keadaan saat dibangun.
3. Pasang tanpa menulis ke disc asli: salin atau hardlink disc, lalu ganti berkas di
   `writes` dengan salinan baru, seperti [`fm3.test_disc`](../src/fm4_converter/fm3/test_disc.py).
4. Paket yang dibangun sendiri-sendiri di atas FM4 Disc 1 tidak bisa dipasang bersamaan
   (`fm4_converter.mod.conflicts`): paket FM3 dan FM2 sama-sama mengganti `gamedb.slt`,
   `zipmanifest.xml`, `stringtables.zip` dan `Thumbnails.zip`. Paket bertumpuk bisa: pasang
   menurut urutan `base_packages`, dan berkas yang ditulis beberapa paket diambil dari paket
   terakhir.
5. Tampilkan `notes` dan status `failed`/`skipped` dari `cars` (atau `tracks`) kepada pemain.

## Pemasangan bertumpuk

FM4 hanya membaca satu `gamedb.slt`, satu `zipmanifest.xml` dan satu `stringtables.zip`.
Supaya paket mobil FM3, mobil FM2 dan track FM3 aktif bersamaan, setiap paket dibangun di
atas disc yang sudah membawa paket sebelumnya ([`stack`](../src/fm4_converter/stack.py)):

- `--fm4` menunjuk Disc 1 dengan paket di bawahnya terpasang (salinan atau hardlink), dan
  `--base-package` menyebut paket-paket itu.
- Database dan `zipmanifest.xml` disc itu menjadi dasar, jadi baris dan mount paket di
  bawahnya tetap ada. ID mobil FM3 dan FM2 tidak bertabrakan; kunci lain mengambil kunci
  bebas berikutnya.
- Arsip kumulatif (`Media/stringtables.zip`, `Media/UI/Textures/Thumbnails.zip`,
  `Media/audio/Cars.zip`) diperluas: isi paket di bawahnya disalin, anggota baru ditambahkan,
  dan mount di `zipmanifest.xml` diambil alih dengan prioritas yang sama.
- Mobil FM2 yang dipakai donor tidak diambil dari mobil yang ditambahkan paket di bawahnya.
- `built_against` mencatat hash disc bertumpuk itu, jadi launcher bisa menyusun urutan pasang
  dengan merangkai hash: paket berikutnya cocok dengan keadaan setelah paket sebelumnya
  terpasang.

Bila paket di bawah dibangun ulang, paket di atasnya harus dibangun ulang juga.

## Track

`--content tracks` menjalankan [`fm3.track_env`](../src/fm4_converter/fm3/track_env.py) dengan
disc pemain: environment NewYork (22–25), Amalfi (10 layout, dari Road Racing Track Pack di
FM3 Disc 2), LeMansBugatti (LeMans 102 sebagai environment sendiri) dan layout CrownJewel 170
(geometri FM4). TestTrackinfield (18 layout) butuh Disc 1 dan Disc 2 Ultimate Collection
(database dan Forza Ultimate Track Pack); tanpa keduanya environment ini dilewati
(`skipped`) dengan alasannya. Isi dan status uji ada di [fm3-acceptance.md](fm3-acceptance.md).

FM2 tidak punya track untuk dikonversi: semua 50 layout aktif FM2 sudah ada di FM4 atau di
versi FM3-nya. Satu-satunya yang tersisa, TuningTrack (ID 71), tidak aktif di database FM2
(`Active=0`) dan tidak punya berkas di disc.

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
