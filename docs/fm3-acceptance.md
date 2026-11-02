# Kriteria penerimaan konten FM3 di FM4

Ditetapkan 2 November 2026. Dokumen ini menentukan kapan konten FM3 yang tidak ada di
FM4 dianggap **valid dan cocok** di FM4, dan mencatat statusnya. Pekerjaan konversi
berhenti setelah setiap item memenuhi kriteria atau tercatat di bagian *Batas*.
Kolom `accepted` paket tetap keputusan pemilik project.

## Cakupan

| Konten | Jumlah | Sumber |
|---|---|---|
| Mobil FM3-only | 81 | FM3 USA Disc 1/2, tidak ada di FM4 Disc 1 maupun DLC FM4 terpasang ([fm3.md](fm3.md#semua-mobil-fm3-only-dalam-satu-paket--fm3-only-v1)) |
| Layout track FM3-only | 34 | CrownJewel 170, LeMans 102, NewYork 22–25, Amalfi 120/122–126/128–131, TestTrackinfield 49–66 ([REPORT](../research/tracks-2026-11-02/REPORT.md)) |

Konten yang sudah ada di FM4 (disc atau DLC terpasang) tidak dikonversi ulang.

## Kriteria mobil

| Kode | Kriteria | Cara ukur |
|---|---|---|
| M1 | Terkemas tanpa melanggar aturan paket: tidak ada tabrakan ID/kunci, dependensi FM4 tersedia atau tercatat di `requires`, game asli tidak ditulis | `batch_package` (validasi bawaan) + suite tes |
| M2 | Bisa dipilih di Car Select dengan nama "(FM3)", kelas dan PI tampil | e2e Quick Race, teks kartu Car Select dicek OCR |
| M3 | Balapan Quick Race dengan AI berjalan ≥ 25 detik tanpa crash, kunci error runtime sama dengan baseline | `summary.json` e2e (`crashed` null, `race_started_s`), `top_errors` |
| M4 | Eksterior dan cockpit dirender: bodi tampak di kamera balap, cockpit tidak putih/hitam rata | frame e2e, diperiksa |

## Kriteria track (per layout)

| Kode | Kriteria | Cara ukur |
|---|---|---|
| T1 | Terkemas: baris DB, berkas baru lewat ZIP yang di-mount, tidak menimpa berkas FM4 | `track_package` + tes |
| T2 | Tampil di Track Select dan termuat; balapan AI 12 mobil ≥ 40 detik tanpa crash | e2e (`crashed` null, scene `_Race`) |
| T3 | Geometri track dirender di **tampilan utama** dan spion | `REX_DRAW_LIST_TRACE` + `track_cmdbuf.py draws`: draw shader track di pass utama (`ds=10400`) > 0 setiap frame balapan terekam; frame diperiksa (bukan abu-abu rata) |
| T4 | AI dan grid sesuai layout: mobil start di grid, AI menyelesaikan lap | e2e, frame start dan posisi |

## Uji kendali

Tsukuba dengan set biner FM3 lengkap (`bisect/tsukuba-fm3*`) adalah kendali pipeline
biner track: T3 harus lolos di sini sebelum layout FM3-only lain dikonversi, karena
layout tersebut memakai model FM3 yang sama formatnya.

## Paket

Satu overlay membawa semua konten FM3-only: satu `gamedb.slt`, satu `stringtables.zip`
dan satu `zipmanifest.xml`, karena FM4 hanya membaca satu dari masing-masing.

```powershell
python -m fm4_converter.fm3.batch_package --model-helper <carbin-cpu-v4>\carbin-cpu.exe --rules <rules.json> --pi-model <pi-model.json> --value-scales <rules.json> --content-root <...\4D530910\00000002> --out <paket-mobil>
python -m fm4_converter.fm3.track_env --base <paket-mobil> --content-root <...\4D530910\00000002> --out <paket-final>
```

`track_env` mengonversi environment NewYork, Amalfi, TestTrackinfield dan LeMansBugatti
(LeMans 102 sebagai environment sendiri). Isinya: PVS v27, RMB v5, AI dengan nama dan
padding yang dibaca FM4, `TrackSettings` FM4 sebagai donor pencahayaan, serta logo, mini
ribbon dan gambar FM3. Nama environment baru yang sudah dipakai FM4 diberi tanda
"(FM3)", sama seperti mobil.

## Status

| Item | M1/T1 | M2/T2 | M3 | M4/T3 | T4 | Catatan |
|---|---|---|---|---|---|---|
| 81 mobil FM3-only | ✔ 81/81 | 20 diuji | 20 diuji | 20 diuji | – | 8 yang dulu ditolak kini terkemas (XML sumber diperbaiki, berat stok IE, teknik tak dikenal seperti mobil FM4); 61 belum diuji di game |
| CrownJewel 170 | ✔ | ✔ | – | ✔ (geometri FM4) | ✔ | paket `track_package` terpisah |
| Kendali Tsukuba FM3 | – | ✔ | – | ✔ | – | `track_rmb.to_v5` (run `track-tsukuba-rmb5c`) |
| NewYork 22–25, Amalfi 10 layout, TestTrackinfield 18, LeMans 102 | ✔ 33/33 | sebagian | – | sebagian | – | lihat uji per layout di bawah |

## Batas

Bukan bagian kriteria ini, dan tidak diklaim: kesetaraan handling dengan FM3, suara mesin
yang dibandingkan, upgrade/tune non-stock, mode karier, multiplayer, dan kualitas
pencahayaan setara track buatan Turn 10 untuk FM4.
