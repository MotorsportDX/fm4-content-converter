# FM2 → FM4: mobil FM2-only

Jalur FM2 adalah adapter sumber kedua dalam [FM4 Content Converter](../README.md).
Cakupannya hanya mobil FM2 yang tidak ada di FM3 maupun FM4: 55 dari 349 definisi
mobil FM2, kebanyakan varian tuner dan livery balap. Mobil FM2 yang juga ada di FM3
diambil dari jalur [FM3 → FM4](fm3.md) karena aset FM3 lebih lengkap.

Source berada di [`src/fm4_converter/fm2`](../src/fm4_converter/fm2/). Riset lengkap,
pengukuran, dan hasil uji game ada di
[laporan riset FM2](../research/cars-fm2-2026-11-02/REPORT.md); nomor bagian di bawah
merujuk ke laporan itu. Perintah tidak menjalankan game, memasang DLC, atau mengubah
disc sumber.

## Kebutuhan

- Python dan dependensi `requirements.txt`, seperti [setup repository](../README.md#setup-python).
- Helper CPU `carbin-cpu.exe` yang sudah direview, dari
  [petunjuk build helper](../tools/carbin_cpu/README.md).
- Disc FM2 USA beserta Bonus Disc (DLC), FM3 USA Disc 1, dan FM4 Disc 1 lokal. Lokasi default ada
  di [`fm2/sources.py`](../src/fm4_converter/fm2/sources.py).
- Folder paket DLC FM4 terpasang (`--content-root`), agar kunci database, merek, dan
  velg DLC tidak bertabrakan.
- Inventory rute per mobil dari riset (`outputs/car-fm2-research-2026-11-02/inventory.json`).

## Menjalankan

Semua perintah dijalankan dari root repository dengan interpreter `.venv`.

```powershell
# 1. DLC FM2 dari Bonus Disc sebagai folder Media (outputs/car-fm2-dlc)
.\.venv\Scripts\python.exe -m fm4_converter.fm2.dlc

# 2. Studi kalibrasi fisika FM2 -> FM4 (study.json, hanya database disc)
.\.venv\Scripts\python.exe -m fm4_converter.fm2.physics

# 3. Paket overlay: semua mobil fm2_only, atau sebagian dengan --cars
.\.venv\Scripts\python.exe -m fm4_converter.fm2.package --out <paket-baru>
.\.venv\Scripts\python.exe -m fm4_converter.fm2.package --out <paket-baru> --cars JAG_XK_07

# Donor pilihan sendiri untuk satu mobil (boleh diulang)
.\.venv\Scripts\python.exe -m fm4_converter.fm2.package --out <paket-baru> `
    --cars MAZ_RX7_ReAmemiya_95 --donor MAZ_RX7_ReAmemiya_95=MAZ_Rx8Mazdaspeed_04

# Alat per tahap
.\.venv\Scripts\python.exe -m fm4_converter.fm2.models JAG_XK_07 --donor JAG_XKRS_09 --out <folder-baru>
.\.venv\Scripts\python.exe -m fm4_converter.fm2.transcode <fm2.carbin> <fm3-baru.carbin>
```

`--out` harus folder baru di luar disc. Model per pasangan mobil–donor disimpan di
`--models-root` dan dipakai ulang bila sudah ada. Untuk menguji di game, buat salinan
disc dengan `fm4_converter.fm3.test_disc` ([panduan FM3](fm3.md#uji-e2e-motorsport-dx-kelaspi-dan-nama-di-bawah-dlc--v9)).

## Alur per mobil

| Tahap | Modul | Isi |
|---|---|---|
| Dekode | `carbin` | `.carbin` FM2 (LOD1–5, UV fixed-point 16-bit). Bagian 5 |
| Transkode | `transcode` | Model FM2 ditulis dengan tata letak biner FM3. Bagian 7.2–7.3 |
| Model FM4 | `models` | `carbin-cpu convert` membuat model utama; `closeup` membuat `_lod0` dan `_cockpit` dari LOD1 dengan header donor; velg FM2 dikonversi dengan LOD0 dari LOD1. Bagian 7, 9 |
| Fisika | `physics` | Fisika stock FM2 dengan 46 aturan skala, `CMHeight` dari bounding box, PI model hinge, dan part aspirasi FM2 yang tidak dimiliki donor. Bagian 10–13 |
| Paket | `package` | Graf database stock donor dengan kunci baru, `Data_Car.Id` FM2, tekstur dan thumbnail FM2, nama "(FM2)", serta override audio. Bagian 8, 14 |

**Donor.** Mobil disc FM4 dengan `_lod0`, `_cockpit`, empat kaliper dan rotor, serta
header close-up yang terbaca. Kamera kokpit dan posisi driver ikut donor, sedangkan
geometri kokpit dari FM2 (bagian 14.5, 15.3). Pilihan otomatis (bagian 16):
1. sisi setir dan jenis penggerak sama;
2. donor balap hanya untuk mobil balap;
3. setir FM2 berada −0,25…+0,10 m (depan–belakang) dan maksimal 0,07 m (tinggi) dari
   setir donor, atau donor terdekat bila tidak ada;
4. merek sama, lalu massa dan tenaga terdekat.

`--donor` memakai pool dan aturan sisi setir yang sama, tanpa batas jendela. Donor di
luar pool atau dengan setir di sisi lain ditolak. `manifest.json` mencatat
`donor_choice` (`automatic` atau `manual`) dan `wheel_offset` (`dz`, `dy`, `in_window`).

**Yang tetap milik donor:** grup fisika yang tidak dipilih studi, baris `List_Wheels`
kecuali `MediaName`, `CarPartPositions`, `CameraOverrides`, `CarExceptions`,
`Combo_Colors`, kaliper dan rotor, header `_lod0`/`_cockpit`, audio `Data_Engine`,
CMT audio bila FM4 tidak punya, dan `MakeID` bila FM4 tidak punya merek FM2.

## Hasil saat ini

`package-v5` berisi 55 dari 55 mobil FM2-only (bagian 17). Empat mobil DLC FM2 dibaca dari
Bonus Disc (`fm2.dlc`), dan quad turbo `CHR_ME412_05` dipasang sebagai twin turbo seperti Veyron
di FM4. Daftar 55 mobil sudah diverifikasi terhadap 45 mobil FM2 yang ID-nya ada di FM4 dengan
nama lain (bagian 17.4).

Uji game di Motorsport DX (Quick Race Bernese Alps, AI menyetir):

- Balapan sampai finis: `JAG_XK_07`, `MAZ_RX7_ReAmemiya_95`, Lancer Evo IX GT, dan
  Tommy Kaira R34 (bagian 8, 10, 11, 14.4).
- Kamera kokpit, kap, bumper, dan chase pada **semua 55 mobil** dengan donor finalnya (bagian
  17.6), tanpa crash. Kokpit benar pada 50 mobil. #58 Viper GTS-R dan #77 Viper ACR sebagian
  besar benar. AB Flug Supra dan kedua VeilSide Supra menampilkan setir terlalu dekat.
- Kartu "CAR" sebelum balapan menampilkan thumbnail FM2 mobil sendiri.
- Fisika FM2 pada tiga mobil FM4 native: durasi balapan AI −1,5% sampai +0,8% dari
  fisika asli (bagian 12).

## Batas

- Kamera kokpit dan posisi driver ikut donor. Jendela posisi setir disimpulkan dari uji game,
  bukan dari posisi kamera donor (bagian 16). Donor manual di luar jendela dapat menaruh kamera
  di dalam atau di depan setir, atau di belakang kursi; periksa `wheel_offset` di manifest.
- Tiga Supra mk4 dan dua Viper balap tidak dapat diperbaiki lewat pilihan donor; posisi kamera
  kokpit di data FM4 belum ditemukan (bagian 17.6).
- Warna cat bawaan, suara mesin, dan merek mobil tanpa padanan FM4 ikut donor.
- Kecocokan kelas PI validation 25/37. Kelas belum tentu sama dengan mobil sebanding
  di FM4 (bagian 13).
- FM2 tidak menyimpan `_lod0`, kokpit, gauge, jarum, `a_pillar`, kaliper, dan rotor.
  Close-up dibuat dari LOD1, dan bagian lainnya milik donor atau tidak ada (bagian 6.4, 7.6).
- Override audio hanya terbukti tidak membuat crash; suara belum diperiksa.
- Livery editor, foto, replay, dan kerusakan belum diuji. Livery mask FM2 tidak dikirim.
- FM4 hanya membaca satu database. Overlay FM2 terpisah dari overlay FM3, jadi
  menggabungkannya memerlukan pengemasan bersama.
- Paket adalah overlay offline untuk uji, bukan DLC siap pasang.
