import subprocess, os, time
ROOT="/mnt/d/_workspace/cc/kuma"; B=ROOT+"/benchmark"
DMS=B+"/data/DMS_substitutions/DMS_ProteinGym_substitutions"
OUT=B+"/results/qa/kuro_real/poolsweep"; os.makedirs(OUT,exist_ok=True)
LOG=B+"/results/qa/kuro_real/poolsweep.log"; PY=B+"/.venv-al/bin/python"
ENV=dict(os.environ); ENV["PYTHONPATH"]=ROOT
REPS=[("F7YBW8_MESOW_Aakre_2015","F7YBW8"),("RASK_HUMAN_Weng_2022_abundance","P01116"),("A4_HUMAN_Seuma_2022","P05067")]
POOLS=[1000,2000]
def log(m): open(LOG,"a").write("["+time.strftime("%H:%M:%S")+"] "+m+"\n")
open(LOG,"w").write("START poolsweep\n")
# small assay (F7YBW8) first, then RASK, then A4 (largest) -- and smaller pool before larger
for pool in POOLS:
    for nm,acc in REPS:
        out=OUT+"/"+nm+"_p"+str(pool)+".json"
        if os.path.exists(out): log("skip "+nm+" p"+str(pool)); continue
        t0=time.time()
        r=subprocess.run([PY,"-m","al.kuro_real_bench","--assay",DMS+"/"+nm+".csv","--accession",acc,"--pool",str(pool),"--n-seed","15","--batch","20","--rounds","4","--seeds","50","--out",out],cwd=B,env=ENV,capture_output=True,text=True)
        log(nm+" p"+str(pool)+" rc="+str(r.returncode)+" "+str(int(time.time()-t0))+"s "+(r.stderr[-150:] if r.returncode else ""))
log("ALL_DONE")
