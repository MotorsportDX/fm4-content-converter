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

## Status

| Item | M1/T1 | M2/T2 | M3 | M4/T3 | T4 | Catatan |
|---|---|---|---|---|---|---|
| 73 mobil terkemas | ✔ | 20 diuji | 20 diuji | 20 diuji | – | 53 belum diuji di game |
| 8 mobil ditolak | ✘ | – | – | – | – | material tanpa preseden, XML rusak, massa stock |
| CrownJewel 170 | ✔ | ✔ | – | ✔ (geometri FM4) | ✔ | |
| Kendali Tsukuba FM3 | – | ✔ | – | ✔ | – | `track_rmb.to_v5` (run `track-tsukuba-rmb5c`) |
| 33 layout lain | ✘ | – | – | – | – | butuh pipeline biner track |

## Batas

Bukan bagian kriteria ini, dan tidak diklaim: kesetaraan handling dengan FM3, suara mesin
yang dibandingkan, upgrade/tune non-stock, mode karier, multiplayer, dan kualitas
pencahayaan setara track buatan Turn 10 untuk FM4.
