import subprocess, os, time
ROOT="/mnt/d/_workspace/cc/kuma"; B=ROOT+"/benchmark"
DMS=B+"/data/DMS_substitutions/DMS_ProteinGym_substitutions"
OUT=B+"/results/qa/kuro_real/sweetspot_150M"; os.makedirs(OUT,exist_ok=True)
LOG=B+"/results/qa/kuro_real/sweetspot_150M.log"; PY=B+"/.venv-al/bin/python"
ENV=dict(os.environ); ENV["PYTHONPATH"]=ROOT
MODEL="esm2_t30_150M_UR50D"
ASSAYS=[("F7YBW8_MESOW_Aakre_2015","F7YBW8"),("RASK_HUMAN_Weng_2022_abundance","P01116"),("GRB2_HUMAN_Faure_2021","P62993"),("HIS7_YEAST_Pokusaeva_2019","P06633"),("GFP_AEQVI_Sarkisyan_2016","P42212"),("GCN4_YEAST_Staller_2018","P03069"),("PABP_YEAST_Melamed_2013","P04147"),("DLG4_HUMAN_Faure_2021","P78352"),("A4_HUMAN_Seuma_2022","P05067")]
def log(m): open(LOG,"a").write(f"[{time.strftime(chr(37)+'H:'+chr(37)+'M:'+chr(37)+'S')}] {m}\n")
open(LOG,"w").write("START 150M sweep\n")
for i,(nm,acc) in enumerate(ASSAYS):
    out=OUT+f"/{nm}.json"
    if os.path.exists(out): log(f"skip {nm}"); continue
    t0=time.time()
    r=subprocess.run([PY,"-m","al.kuro_real_bench","--assay",f"{DMS}/{nm}.csv","--accession",acc,"--model",MODEL,"--seeds","50","--out",out],cwd=B,env=ENV,capture_output=True,text=True)
    log(f"[{i+1}/9] {nm} acc={acc} rc={r.returncode} {int(time.time()-t0)}s {r.stderr[-200:] if r.returncode else chr(39)+chr(39)}")
log("ALL_DONE")
