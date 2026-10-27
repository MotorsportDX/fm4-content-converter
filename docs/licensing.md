# Lisensi project

Lisensi utama FM4 Content Converter adalah **GNU General Public License v3.0
only**, dengan identifier SPDX **`GPL-3.0-only`**. Teks lisensi lengkap tersedia
di [LICENSE](../LICENSE); identifier yang sama dicantumkan pada metadata package
di `pyproject.toml`.

## Alasan pemilihan

Adapter C# dan beberapa modul audit sudah mempunyai header `GPL-3.0-only`.
Helper tersebut menautkan source ForzaEditor yang berlisensi GPL v3. Memakai
GPL v3 sebagai lisensi utama mempertahankan ketentuan source turunan tersebut
dan memberikan ketentuan yang jelas untuk pengembangan converter selanjutnya.

Project memilih versi **3 saja**; tidak menambahkan izin penggunaan versi GPL
masa depan pada kode turunan yang sekarang ditandai `GPL-3.0-only`.

## Cakupan

- Kontribusi asli project pada kode Python, tes, helper, dan dokumentasi
  disediakan di bawah GPL-3.0-only, kecuali file atau bagiannya menyatakan
  ketentuan lain secara eksplisit.
- File dan bagian pihak ketiga mempertahankan copyright, notice dan lisensi
  masing-masing, termasuk BSD, MIT, LGPL dan Ms-PL. Salinan teks di
  `third_party/` serta `tools/carbin_cpu/` dipertahankan sesuai notice upstream.
- Hak atas database, aset, executable game, nama merek, DLL proprietary dan
  input/output yang memuat materi pihak ketiga tidak diberikan oleh lisensi
  source converter ini. GPL tidak otomatis mengganti lisensi data yang
  diproses oleh program.

Pengguna boleh menjalankan, mempelajari, memodifikasi serta mendistribusikan
program, termasuk secara komersial, dengan memenuhi GPL v3. Ketika
mendistribusikan karya turunan atau bentuk binary yang tercakup GPL,
pertahankan pemberitahuan yang relevan dan berikan corresponding source sesuai
ketentuan lisensi. Perubahan pribadi tidak harus dipublikasikan hanya karena
program dipakai sendiri. Program disediakan tanpa garansi sebagaimana tertulis
pada GPL.

## Helper dan dependency eksternal

Pemilihan lisensi source project tidak menyatakan bahwa semua kombinasi binary
dependency eksternal sudah siap didistribusikan.

Helper model yang ada menggunakan **MonoGame 3.6.0.1625**, dengan notice
**Ms-PL** dan bagian **MIT Mono.Xna** yang tercantum pada
[notice versi terpin](../tools/carbin_cpu/MonoGame-LICENSE.txt). Ms-PL mempunyai
ketentuan sendiri atas distribusi source dan object code. Sebelum membuat
rilis binary helper gabungan, kesesuaian ketentuan tersebut dengan source GPL
yang ditautkan perlu diselesaikan; keputusan GPL-3.0-only untuk repo tidak
dianggap sebagai izin redistribusi kombinasi tersebut. Pemeriksaan ini belum
ditutup oleh project.

Decoder XMem dan Granny disediakan lokal dengan ketentuan pemiliknya dan tidak
dibundel. Begitu juga source/binary tool riset eksternal. Detail pemakaian
dicatat pada [CREDITS.md](../CREDITS.md) dan
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## Kontribusi berikutnya

Kontribusi asli yang dimaksudkan menjadi bagian project mengikuti
GPL-3.0-only. Kontributor mempertahankan hak cipta atas karyanya. Saat membawa
kode pihak ketiga, pertahankan lisensi asal dan catat asal, revisi, penggunaan
serta notice yang relevan sebelum menggabungkannya.

## Referensi

- [GNU GPL v3 — teks resmi](https://www.gnu.org/licenses/gpl-3.0.html).
- [GNU GPL FAQ](https://www.gnu.org/licenses/gpl-faq.en.html), termasuk penjelasan
  penggunaan pribadi, distribusi dan corresponding source.
- [PyPA: metadata license dan license-files](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/#license-and-license-files).

Ringkasan di atas membantu membaca cakupan project; ketentuan lengkap tetap
berada pada teks lisensi masing-masing.
