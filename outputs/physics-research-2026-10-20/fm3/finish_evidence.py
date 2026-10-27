from research import *
import csv,re,sys,struct,math
sys.path.insert(0,str(OUT.parent/'shared'))
from stfs_reader import STFS
from stfs_zip_io import STFSFile
import forza_zip
def main():
 assets=json.loads((OUT/'decoded_assets.json').read_text());zi=json.loads((OUT/'disc2_zip_inventory.json').read_text());zi={(x['disc'],x['package']):x for x in zi};dc=json.loads((OUT/'db_comparison.json').read_text());e=json.loads((OUT/'evidence.json').read_text())
 summary={'integrity':{},'db':{},'zip_disc2_common':[],'disc2_track_physics':[],'car_chain':{},'disc1_car_attrib_hashes':[],'cautions':[]}
 base={k:connect(k) for k in ['regular_d1','uc_d1']}
 for k,c in base.items():summary['integrity'][k]=c.execute('pragma quick_check').fetchone()[0]
 summary['db']['schema_pragma_identical_all_common']=all(v['columns']==e['databases']['uc_d1']['tables'][n]['columns'] for n,v in e['databases']['regular_d1']['tables'].items())
 summary['db']['torque_curve_max_abs_difference']=max(abs(z['regular']-z['uc']) for v in dc['List_TorqueCurve']['changes'] for z in v['changes'].values())
 summary['db']['torque_curve_float32_identical']=all(struct.pack('f',z['regular'])==struct.pack('f',z['uc']) for v in dc['List_TorqueCurve']['changes'] for z in v['changes'].values())
 summary['db']['deleted_torque_curve_ids_unreferenced']=all(not base['regular_d1'].execute('select 1 from List_UpgradeEngineCamshaft where TorqueCurveZeroThrottleID=? or TorqueCurveFullThrottleID=?',(v[0],v[0])).fetchone() for v in dc['List_TorqueCurve']['removed_keys'])
 for pkg in ['4D53084D0CCF0013','4D53084D0CCF0014','4D53084D0CCF0015','4D53084D0CCF0060']:
  a,b=[{v['path']:v for v in zi[k,pkg]['zips']} for k in ['regular_d2','uc_d2']]
  for n in a.keys()&b.keys():
   aa,bb=[{v['name']:v for v in d[n]['members']} for d in [a,b]]
   changes=[{'member':v,'regular':aa[v],'uc':bb[v]} for v in aa.keys()&bb.keys() if any(aa[v][x]!=bb[v][x] for x in ['size','crc32','compression'])]
   summary['zip_disc2_common'].append({'package':pkg,'zip':n,'changed_members':changes,'only_regular':list(aa.keys()-bb.keys()),'only_uc':list(bb.keys()-aa.keys())})
  pa,pb=[next((ROOTS[k]/'Content').rglob(pkg)) for k in ['regular_d2','uc_d2']]
  if pkg.endswith('0060'):
   with STFS(pa) as p,STFS(pb) as q:
    qe={x['name']:x for x in q.entries}
    for entry in p.entries:
     if entry['directory'] or Path(entry['name']).suffix.lower() not in ['.col','.geo','.irt','.seg','.pit']:continue
     a1,b1=p.read(entry),q.read(qe[entry['name']]);summary['disc2_track_physics'].append({'path':entry['name'],'regular_sha256':hashlib.sha256(a1).hexdigest(),'uc_sha256':hashlib.sha256(b1).hexdigest()})
 for path in (ROOTS['regular_d1']/'Media/Cars').glob('*.zip'):
  with zipfile.ZipFile(path) as z:
   m=next((x for x in z.infolist() if x.filename.lower()=='carattribs.xml'),None)
   if m:
    b=forza_zip.read(z,m);summary['disc1_car_attrib_hashes'].append({'archive':path.name,'member':m.filename,'sha256':hashlib.sha256(b).hexdigest(),'crc_verified':True,'xml_root':ET.fromstring(b.decode(errors='replace')).tag})
 c=base['regular_d1'];car=dict(c.execute('select * from Data_Car where Id=247').fetchone());chain={'Data_Car':car}
 for table in ['List_UpgradeCarBody','List_UpgradeEngine','List_UpgradeDrivetrain','List_UpgradeTireCompound','List_UpgradeSpringDamper','List_UpgradeBrakes','List_UpgradeAntiSwayFront','List_UpgradeAntiSwayRear']:
  chain[table]=dict(c.execute('select * from '+quote(table)+' where Ordinal=? and IsStock=1',(car['Id'],)).fetchone())
 ids={'Data_CarBody':('Id',chain['List_UpgradeCarBody']['CarBodyID']), 'List_UpgradeCarBodyWeight':('CarBodyId',chain['List_UpgradeCarBody']['CarBodyID']), 'Data_Engine':('EngineID',chain['List_UpgradeEngine']['EngineID']), 'List_UpgradeEngineCamshaft':('EngineID',chain['List_UpgradeEngine']['EngineID']), 'List_UpgradeDrivetrainTransmission':('DrivetrainID',chain['List_UpgradeDrivetrain']['DrivetrainID']), 'List_UpgradeDrivetrainDifferential':('DrivetrainID',chain['List_UpgradeDrivetrain']['DrivetrainID']), 'List_TireCompound':('TireCompoundID',chain['List_UpgradeTireCompound']['TireCompoundID'])}
 for table,(key,val) in ids.items():
  cols=[r['name'] for r in c.execute('pragma table_info('+quote(table)+')')];chain[table]=dict(c.execute('select * from '+quote(table)+' where '+quote(key)+'=?'+(' and IsStock=1' if 'IsStock' in cols else ''),(val,)).fetchone())
 for side in ['Front','Rear']:
  key=chain['List_UpgradeSpringDamper'][side+'SpringDamperPhysicsID'];chain['List_SpringDamperPhysics_'+side]=dict(c.execute('select * from List_SpringDamperPhysics where SpringDamperPhysicsID=?',(key,)).fetchone())
 summary['car_chain']=chain
 for category,table,cols in [('cars','Data_Car',['Id','Year','MediaName','ContentId','IsInstalled','IsPurchased','DriveTypeID','CurbWeight','WeightDistribution','PerformanceIndex','HandlingRating','GameTorqueScale','GameDragScale','SteerMaxAngle','SteerMaxAngleFiltered']),('tracks','Tracks',['id','MediaName','RibbonIndex','ReverseIndex','Length','Active','Renderable','ContentId','IsInstalled','IsPurchased','EnvironmentId'])]:
  rows=[]
  for key,c in base.items():
   for row in c.execute('select '+','.join(quote(x) for x in cols)+' from '+table+' order by '+quote(cols[0])):
    d={'edition':key,**dict(row)};packages=[]
    if category=='cars':
     for t,prefix,fields in [
       ('List_UpgradeEngine','StockEngine',['EngineID']),
       ('List_UpgradeDrivetrain','StockDrivetrain',['DrivetrainID']),
       ('List_UpgradeCarBody','StockBody',['CarBodyID']),
       ('List_UpgradeTireCompound','StockTire',['TireCompoundID']),
       ('List_UpgradeSpringDamper','StockSuspension',['FrontSpringDamperPhysicsID','RearSpringDamperPhysicsID'])]:
      v=c.execute('select * from '+quote(t)+' where Ordinal=? and IsStock=1',(row['Id'],)).fetchone()
      for f in fields:d[prefix+'_'+f]=v[f] if v else None
     cb=d['StockBody_CarBodyID'];wt=c.execute('select * from List_UpgradeCarBodyWeight where CarBodyId=? and IsStock=1',(cb,)).fetchone();body=c.execute('select * from Data_CarBody where Id=?',(cb,)).fetchone()
     for f in ['Mass','CMHeight','CMBackFront','CMLeftRight','BlockDimX','BlockDimY','BlockDimZ']:d['StockBody_'+f]=wt[f] if wt else None
     for f in ['ModelWheelbase','ModelFrontTrackOuter','ModelRearTrackOuter']:d[f]=body[f] if body else None
     cam=c.execute('select * from List_UpgradeEngineCamshaft where EngineID=? and IsStock=1',(d['StockEngine_EngineID'],)).fetchone()
     for f in ['RedlineRPM','StallRPM','TorqueCurveMaxRPM','TorqueCurveZeroThrottleID','TorqueCurveFullThrottleID']:d['StockEngine_'+f]=cam[f] if cam else None
     tr=c.execute('select * from List_UpgradeDrivetrainTransmission where DrivetrainID=? and IsStock=1',(d['StockDrivetrain_DrivetrainID'],)).fetchone()
     for f in ['FinalDriveRatio','NumGears','GearRatio0','GearRatio1','GearRatio2','GearRatio3','GearRatio4','GearRatio5','GearRatio6','GearRatio7','GearRatio8']:d['StockTransmission_'+f]=tr[f] if tr else None
     for side in ['Front','Rear']:
      sp=c.execute('select * from List_SpringDamperPhysics where SpringDamperPhysicsID=?',(d['StockSuspension_'+side+'SpringDamperPhysicsID'],)).fetchone()
      for f in ['DefRideHeight','DefSpringRate','DefDampenBumpRate','DefDampenReboundRate','StaticCamber','StaticToe','Caster']:d['Stock'+side+'_'+f]=sp[f] if sp else None
    for patch in assets['patches']:
     if patch['disc']!=key.replace('d1','d2') or not patch.get('text','').startswith('UPDATE '+table+' SET IsInstalled'):continue
     ids=list(map(int,re.search(r'IN \((.*?)\)',patch['text']).group(1).split(',')))
     if row[cols[0]] in ids:packages.append(patch['package'])
    d['Disc2ActivationPackages']=','.join(packages);rows.append(d)
  with (OUT/(category+'_map.csv')).open('w',newline='',encoding='utf-8-sig') as f:
   writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
 dump('summary_evidence.json',summary)
 e['research_scope']={'offline':True,'game_or_emulator_run':False,'source_files_modified':False,'date_local':'2026-10-20','unit_policy':'Only names with explicit units are assigned units; other values remain raw.'}
 e['derived_artifacts']=['report.md','cars_map.csv','tracks_map.csv','db_comparison.json','decoded_assets.json','summary_evidence.json','disc2_packages.json','disc2_zip_inventory.json','track_physics_file_comparison.json','ai_file_comparison.json','car_zip_comparison.json']
 e['verification_summary']=summary['db']|{'sqlite_quick_check':summary['integrity'],'disc2_common_track_files_sha256_compared':len(summary['disc2_track_physics']),'disc2_common_track_files_different':sum(x['regular_sha256']!=x['uc_sha256'] for x in summary['disc2_track_physics']),'disc1_car_attributes_decoded_crc_verified':len(summary['disc1_car_attrib_hashes'])}
 dump('evidence.json',e)
 print('INTEGRITY',summary['integrity']);print('DB',summary['db']);print('D2 common ZIP differences',[(v['package'],v['zip'],len(v['changed_members']),len(v['only_regular']),len(v['only_uc'])) for v in summary['zip_disc2_common']]);print('D2 physics files',len(summary['disc2_track_physics']),'different',sum(x['regular_sha256']!=x['uc_sha256'] for x in summary['disc2_track_physics']));print('CARATTR decoded',len(summary['disc1_car_attrib_hashes']))
if __name__=='__main__':main()
