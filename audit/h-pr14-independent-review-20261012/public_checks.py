import sys,json,hashlib,urllib.request,datetime
from pathlib import Path
R=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(R/'source'))
from kuma_core.kuro.strict_spatial import exact_pdb_context,select_single_sites
from kuma_core.kuro.alphafold import _THREE_TO_ONE
results=[]
for acc in ['Q9AR86','P42212']:
 url=f'https://alphafold.ebi.ac.uk/files/AF-{acc}-F1-model_v6.pdb'
 try:
  data=urllib.request.urlopen(url,timeout=20).read(); text=data.decode(); (R/'fixtures'/f'AF-{acc}-F1-model_v6.pdb').write_bytes(data)
 except Exception as e:
  results.append({'accession':acc,'status':'SKIP','reason':'NETWORK','error':str(e),'url':url});print(results[-1],flush=True);continue
 try:
  seq=''.join(_THREE_TO_ONE[l[17:20].strip()] for l in text.splitlines() if l.startswith('ATOM  ') and l[12:16].strip()=='CA')
  c=exact_pdb_context(text,seq,acc);rows=[(f'{aa}{p}{"G" if aa!="G" else "A"}',float(len(seq)-p)) for p,aa in enumerate(seq,1) if p>1]
  s,r=select_single_sites(rows,seq,c,24);confidence={m['reference_position']:m['confidence'] for m in c['mapping']}
  assert all(confidence[p]>=50 for p in r['selected_positions']);assert r['coordinate_confidence']['source']=='alphafold_plddt'
  results.append({'accession':acc,'status':'PASS','url':url,'sha256':hashlib.sha256(data).hexdigest(),'residues':len(seq),'confidence':r['coordinate_confidence'],'selected':s,'note':'Synthetic descending position scores on public real coordinates, not assay benchmark'})
 except Exception as e:results.append({'accession':acc,'status':'FAIL','error':str(e)})
 print(results[-1],flush=True)
(R/'public-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
sys.exit(any(r['status']=='FAIL' for r in results))
