import csv, glob, json, os, subprocess, sys, time, urllib.request, urllib.parse
ROOT="/mnt/d/_workspace/cc/kuma"; B=ROOT+"/benchmark"
sys.path.insert(0,ROOT); sys.path.insert(0,B); os.chdir(B)
from al.kuro_real_bench import _load_multimut
from kuma_core.kuro.alphafold import fetch_ca_coords
DMS=B+"/data/DMS_substitutions/DMS_ProteinGym_substitutions"
OUT=B+"/results/qa/kuro_real/expanded"; os.makedirs(OUT,exist_ok=True)
LOG=B+"/results/qa/kuro_real/full_sweep.log"
PY=B+"/.venv-al/bin/python"
ENV=dict(os.environ); ENV["PYTHONPATH"]=ROOT
DONE9={"F7YBW8_MESOW_Aakre_2015","RASK_HUMAN_Weng_2022_abundance","GRB2_HUMAN_Faure_2021","GCN4_YEAST_Staller_2018","DLG4_HUMAN_Faure_2021","GFP_AEQVI_Sarkisyan_2016","PABP_YEAST_Melamed_2013","A4_HUMAN_Seuma_2022","HIS7_YEAST_Pokusaeva_2019"}
def log(m):
    open(LOG,"a").write(f"[{time.strftime('%H:%M:%S')}] {m}\n")
def resolve_acc(dms_id):
    t=dms_id.split("_"); entry=t[0]+"_"+t[1] if len(t)>=2 else t[0]
    for q in [f"(id:{entry}) AND (reviewed:true)", f"(id:{entry})", f"(accession:{t[0]})"]:
        try:
            u="https://rest.uniprot.org/uniprotkb/search?"+urllib.parse.urlencode({"query":q,"format":"tsv","fields":"accession","size":"1"})
            ln=urllib.request.urlopen(u,timeout=20).read().decode().splitlines()
            if len(ln)>=2 and ln[1].strip(): return ln[1].strip()
        except Exception: pass
    return None
def bench(name,acc,out):
    r=subprocess.run([PY,"-m","al.kuro_real_bench","--assay",f"{DMS}/{name}.csv","--accession",acc,"--seeds","50","--out",out],cwd=B,env=ENV,capture_output=True,text=True)
    return r.returncode, (r.stderr[-400:] if r.returncode else "")
open(LOG,"w").write(f"START {time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
# Step A: correct HIS7 (P06633)
log("A: re-run HIS7 with P06633")
rc,err=bench("HIS7_YEAST_Pokusaeva_2019","P06633",OUT+"/HIS7_YEAST_Pokusaeva_2019.json"); log(f"A HIS7 rc={rc} {err}")
# Step B: re-run trajectories (kuro_traj already fixed to P06633)
log("B: re-run trajectories")
rc=subprocess.run([PY,"-m","al.kuro_traj"],cwd=B,env=ENV,capture_output=True,text=True).returncode; log(f"B traj rc={rc}")
open(B+"/figures/structural_vs_topn/data/CORRECTIONS_DONE","w").write("his7+traj corrected\n")
# Step C: 60 remaining combinatorial assays
combo=[]
for f in sorted(glob.glob(DMS+"/*.csv")):
    n=nc=0
    try:
        for row in csv.DictReader(open(f)):
            n+=1
            if ":" in (row.get("mutant") or ""): nc+=1
            if n>30000: break
    except Exception: continue
    nm=os.path.basename(f)[:-4]
    if nc>=100 and nm not in DONE9: combo.append(nm)
log(f"C: {len(combo)} remaining combinatorial assays")
for i,nm in enumerate(combo):
    out=OUT+f"/{nm}.json"
    if os.path.exists(out): log(f"skip {nm} (exists)"); continue
    acc=resolve_acc(nm)
    if not acc: log(f"SKIP {nm} no-accession"); continue
    try:
        _,_,wt=_load_multimut(f"{DMS}/{nm}.csv"); ca=fetch_ca_coords(acc); caln=len(ca) if ca else 0
    except Exception as e:
        log(f"SKIP {nm} load-err {e}"); continue
    if caln==0 or abs(caln-len(wt))/max(len(wt),1)>0.05:
        log(f"SKIP {nm} struct-mismatch acc={acc} caLen={caln} WT={len(wt)}"); continue
    t0=time.time(); rc,err=bench(nm,acc,out)
    log(f"[{i+1}/{len(combo)}] {nm} acc={acc} caLen={caln} WT={len(wt)} rc={rc} {int(time.time()-t0)}s {err}")
log("ALL_DONE")
