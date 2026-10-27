from pathlib import Path
import csv,json
OUT=Path(__file__).resolve().parent/'dlc'
data=json.loads((OUT/'evidence.json').read_text(encoding='utf-8'))
summary=json.loads((OUT/'summary.json').read_text(encoding='utf-8'))
for typ,key in [('cars','Id'),('tracks','id')]:
 rows=[{'Package':p['name'],'SourcePackage':p['path'],**r} for p in summary for r in p[typ]]
 with (OUT/(typ+'_catalog.csv')).open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
lines=['# FM4 DLC dan title update dari paket lokal','',
'Catatan repo: laporan dan source analisis disertakan. JSON/CSV/schema, hasil ekstraksi aset, disassembly dan binary yang disebut di bawah tetap lokal dan diabaikan Git; lihat [metode reproduksi](../METHODS.md).','',
'Riset statis offline, 20 Oktober 2026. Delapan paket DLC dan tiga title update dibaca dari `D:\\Data\\forza-motorsport-4`. Tidak ada instalasi, game, emulator, patch executable, atau SQL patch yang dijalankan. Sumber asli tetap dibaca saja. Nama di bawah berasal dari metadata STFS, bukan dugaan dari nama folder.','',
'DLC menyediakan database tambahan, geometri collision mobil, dan aset track dalam schema dasar FM4. Delapan paket lokal mengandung **112 ID mobil baru**, semuanya `IsDrivable=1`, serta **18 record track baru**. Dengan database dasar, union yang ditemukan menjadi **615 record mobil, 613 drivable**, dan **145 record track, 132 Active=1**. Ini union definisi yang tersedia di file, bukan hasil pemasangan atau hitungan pasti yang muncul di menu. Tidak berarti koleksi DLC ini lengkap mencakup semua DLC yang pernah dirilis.','',
'## Peta paket','',
'| Paket | Data_Car baru | Track records baru | MAXData mobil terdecode | Patch database |',
'|---|---:|---:|---:|---|']
for p,s in zip(data,summary):
 if p['category']!='DLC':continue
 patches=', '.join(Path(d['path']).name for z in p['zips'] for d in z['databases'])
 lines.append(f"| {s['name']} | {s['car_rows']} | {s['track_rows']} | {s['maxdata_xml_count']} | {patches} |")
lines += ['',
'Jumlah isi paket mengikuti file lokal: LCE berisi 31 record dan September berisi 11. Nama pemasaran paket tidak dipakai untuk menebak jumlah. `cars_catalog.csv` memetakan setiap ID/MediaName/parameter ke paket asal, dan `tracks_catalog.csv` memuat 18 layout record tambahan.','',
'## Bagaimana DLC masuk ke model handling','',
'Container STFS → `Media/DLCZips` → ZIP dengan priority pada nama/mount manifest → `media/db/patch/*_merge.slt` dan bila ada `*_execute.sql`. Mobil DLC memiliki `Data_Car`, `Data_CarBody`, mesin, part upgrades, suspensi, anti-roll, kurva torsi dan relasi ban. Collision XML berada di `media/cars/<MediaName>/physics/maxdata.xml`. Keseluruhan 112 XML ini berhasil didekode, panjang output cocok, CRC32 ZIP valid; ringkasan dimensi/bounding box/jumlah sphere dan SHA256 ada di `evidence.json`.','',
'Ketujuh patch database mobil membawa 60–69 tabel. Mereka memakai tabel/model data FM4 yang sama dengan base. Tidak ada redefinisi `List_TireCompound`, `List_TireFrictionCurve`, `List_TireFrictionMultiCurve`, atau `List_TireAffectCurve` di paket yang diperiksa. Nama March Pirelli Car Pack bukan bukti paket tersebut mengganti algoritme ban global. Tidak ditemukan `.xex`/`.xexp` pada kedelapan paket DLC; patch executable ditemukan di title update terpisah.','',
'Perbandingan memakai primary key dari database dasar bila tabel merge tidak mendeklarasikannya. Data patch tidak digabungkan ke sumber. Dengan demikian hasil memperlihatkan perubahan data yang diminta paket, sedangkan resolusi priority/merge/update versi yang efektif belum dibuktikan dari loader.','',
'### Koreksi data yang sudah disiapkan di base','',
'LCE mengubah enam baris `List_UpgradeCarBodyTireWidthRear`, ID 1353001–1353006, `CarBodyId=1353000`. Contoh ID1353001: `RearTireWidth 215→255`, `Price 1600→2300`, `MassDiff 0.54→1.08`. Field ini berpotensi memengaruhi build ban/berat ketika upgrade dipakai.','',
'Namun **mobilnya adalah `SHE_GT500428CJ_69`, Id1353, yang baru didefinisikan oleh LCE**. Base sudah memiliki sebagian baris upgrade tersebut tetapi belum memiliki `Data_Car.Id=1353` maupun relasi body-nya. Jadi ini koreksi data yang disiapkan lebih dulu untuk mobil DLC; bukan bukti handling mobil base yang sudah tersedia berubah. Tidak ada perubahan shared-key parameter fisika lain yang ditemukan oleh perbandingan patch terhadap base.','',
'### Track tambahan','',
'Launch Track Pack berisi `21000_merge.slt`: 16 record `MediaName=PhysicsTrack` (RibbonIndex 0–15, termasuk pasangan reverse yang berbagi aset) dan 2 record `Soccer`. Setiap record baru bertanda `Active=1`. Identitas internal dicatat apa adanya; `PhysicsTrack` tidak boleh ditafsirkan sebagai debug-only hanya dari namanya. Ada collision `.col`, per-ribbon objects/settings, dan ZIP asset tersendiri.','',
'Delapan belas record ini bukan delapan belas sirkuit unik. Agar dapat digunakan secara fisik dibutuhkan collision geometry, mapping material ke surface global, transform ribbon/reverse, spawn/layout, dan collision objects. Mesh render, thumbnail, serta panjang track tidak mencukupi. Struktur internal triangle/material `.col` belum direkonstruksi.','',
'### SQL pada Porsche Expansion','',
'`media/db/patch/100001_execute.sql` memuat 5 pembaruan banner CareerEventTypes dan 88 pembaruan Events (order/group mask). Skrip ini tidak mengubah parameter mesin/ban/suspensi. Data fisik 30 Porsche berada pada `34000_merge.slt` dan geometri mobil pada MAXData. Tidak ada dasar menyebut Porsche memakai solver terpisah.','',
'## Title update yang harus dipisahkan dari DLC','',
'Folder title update berada di samping sumber yang diminta; diperiksa karena revisi kode dapat mengubah hasil fisika walaupun tabel sama. Label folder v1/v4 dipertahankan sebagai identitas lokal, bukan urutan yang disimpulkan dari field version STFS.','',
'| Folder lokal | Media ID metadata | Version mentah | Isi penting |','|---|---|---|---|']
for p in data:
 if p['category']!='Title Update':continue
 label=Path(p['metadata']['path']).parents[1].name
 sqls=[s['path'] for z in p['zips'] for s in z['sql']]
 lines.append(f"| {label} | `{p['metadata']['media_id']}` | `{p['metadata']['version']}` | default.xexp, facade patches, Media ZIP, LeMans patch; {len(sqls)} SQL |")
lines += ['',
'Japan v1 dan USA v1 membawa patch visual/visibility LeMans serta patch executable. USA folder v4 juga membawa `23500_execute.sql` (26 UPDATE Data_Car atas PI dan beberapa ClassID), `900_execute.sql` (VipDiscounts/CarPIOverrides), serta `950_execute.sql` (level pemain). Perubahan PI/class adalah metadata klasifikasi yang perlu dilacak; itu belum membuktikan gaya ban/mesin diubah.','',
'`default.xexp` dan facade patches **belum dianalisis semantik**. Karena itu kesamaan parameter data tidak membuktikan solver sebelum/sesudah title update identik. Belum dibentuk image hasil patch atau ditentukan kombinasi TU–DLC efektif. Tidak ada patch yang diterapkan pada data asli.','',
'## Bukti dan cara membaca hasil','',
'- `evidence.json`: SHA256 seluruh 11 paket, metadata header, file table STFS, ZIP central-directory, schema/count patch DB, perbandingan key/value, SQL terpilih dan ringkasan collision XML.',
'- `summary.json`: ringkasan paket, full Data_Car/Tracks records, perubahan shared-key dan SQL.',
'- `cars_catalog.csv`, `tracks_catalog.csv`: indeks paket→ID→MediaName dan field native.',
'- `../research_dlc.py`: analisis berulang menggunakan pembacaan read-only, SQLite in-memory untuk payload patch, tanpa eksekusi SQL game.',
'- `../shared/stfs_reader.py`, `stfs_zip_io.py`, `forza_zip.py`: pembacaan container/ZIP dan decoder LZX dari libmspack lokal.','',
'Semua delapan merge DB lolos SQLite `quick_check=ok`; seluruh XML mobil terpilih di DLC lolos decode/CRC dan semua error list kosong. SHA1 blok STFS yang diakses diperiksa terhadap hash entry di paket. Directory/hash-tree ancestry dan signature Microsoft tidak diverifikasi; pemeriksaan ini mendukung ketepatan pembacaan data, bukan autentikasi paket. Membaca central-directory belum memvalidasi semua payload grafis/audio.','',
'Unit field mengikuti nama eksplisit bila ada. Nilai mentah yang tidak berunit, termasuk spring/damping/thermal/load, tidak diberi konversi yang belum terbukti. Gunakan build hash, region/media ID, base DB, ordered patches, pilihan part/tuning, dan state simulasi sebagai satu manifest saat melanjutkan penelitian.','']
(OUT/'report.md').write_text('\n'.join(lines),encoding='utf-8')
print('DLC report/catalogs written')
