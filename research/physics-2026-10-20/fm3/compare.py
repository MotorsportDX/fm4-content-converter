from research import *
def main():
 e=json.loads((OUT/'evidence.json').read_text(encoding='utf8')); a,b=connect('regular_d1'),connect('uc_d1'); diffs={}
 ta,tb=[e['databases'][k]['tables'] for k in ['regular_d1','uc_d1']]
 for name in ta.keys()|tb.keys():
  if name not in ta or name not in tb: diffs[name]={'only': 'regular' if name in ta else 'uc'};continue
  cols=[c['name'] for c in ta[name]['columns']]; cols2=[c['name'] for c in tb[name]['columns']]
  ka=[c['name'] for c in ta[name]['columns'] if c['pk']]
  if cols!=cols2: diffs[name]={'schema_difference': True};continue
  ra=[dict(r) for r in a.execute('select * from '+quote(name))];rb=[dict(r) for r in b.execute('select * from '+quote(name))]
  if ka:
   ra={tuple(r[c] for c in ka):r for r in ra};rb={tuple(r[c] for c in ka):r for r in rb}
   changes=[]
   for k in ra.keys()&rb.keys():
    changed={c:{'regular':ra[k][c],'uc':rb[k][c]} for c in cols if ra[k][c]!=rb[k][c]}
    if changed:changes.append({'key':k,'changes':changed})
   diffs[name]={'pk':ka,'schema_identical':ta[name]['schema']==tb[name]['schema'],'regular_rows':len(ra),'uc_rows':len(rb),'added_keys':list(rb.keys()-ra.keys()),'removed_keys':list(ra.keys()-rb.keys()),'changed_rows':len(changes),'changes':changes}
  else:
   rsa={tuple(r.values()) for r in ra};rsb={tuple(r.values()) for r in rb};diffs[name]={'no_primary_key':True,'regular_rows':len(ra),'uc_rows':len(rb),'added_unique_rows':len(rsb-rsa),'removed_unique_rows':len(rsa-rsb),'rows_identical':rsa==rsb}
 dump('db_comparison.json',diffs)
 paths=[];za={};zb={}
 for key,z in [('regular_d1',za),('uc_d1',zb)]:
  root=ROOTS[key]
  for p in (root/'Media/Cars').glob('*.zip'):
   with zipfile.ZipFile(p) as f: z[p.name]={i.filename:(i.CRC,i.file_size,i.compress_type) for i in f.infolist()}
 zcomp={'method':'central_directory_CRC_size_method_only','regular_archives':len(za),'uc_archives':len(zb),'added_archives':list(zb.keys()-za.keys()),'removed_archives':list(za.keys()-zb.keys()),'different_archives':{k:{'regular_members':len(za[k]),'uc_members':len(zb[k]),'differing_members':[n for n in za[k].keys()|zb[k].keys() if za[k].get(n)!=zb[k].get(n)]} for k in za.keys()&zb.keys() if za[k]!=zb[k]}}
 dump('car_zip_comparison.json',zcomp)
 for p in (ROOTS['regular_d1']/'Media/Tracks').rglob('*'):
  if p.is_file() and p.suffix.lower() in ['.col','.xml','.geo','.irt','.seg','.pit']:
   rel=p.relative_to(ROOTS['regular_d1']);q=ROOTS['uc_d1']/rel
   paths.append({'path':str(rel),'regular_size':p.stat().st_size,'regular_sha256':sha(p),'uc_sha256':sha(q) if q.exists() else None})
 dump('track_physics_file_comparison.json',paths)
 ai=[]
 for p in (ROOTS['regular_d1']/'Media/AI').rglob('*'):
  if p.is_file():
   rel=p.relative_to(ROOTS['regular_d1']);q=ROOTS['uc_d1']/rel
   ai.append({'path':str(rel),'regular_sha256':sha(p),'uc_sha256':sha(q) if q.exists() else None})
 dump('ai_file_comparison.json',ai)
 print(json.dumps({'table_changes':{k:{x:v[x] for x in v if x!='changes'} for k,v in diffs.items() if v.get('changed_rows',0) or v.get('schema_difference') or v.get('only')},'car_zip_comparison':zcomp,'track_files_compared':len(paths),'different_track_files':[p for p in paths if p['regular_sha256']!=p['uc_sha256']]},indent=2))
if __name__=='__main__':main()
