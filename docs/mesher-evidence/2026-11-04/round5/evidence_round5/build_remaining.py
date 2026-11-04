from pathlib import Path
import subprocess, json, time, os
R=Path(__file__).resolve().parent
CM='/workspace/scratch/1d5c10ddf0e3/caelab_mesher_round3_20261104/extra_candidates/root_research/cmake331/cmake/data/bin/cmake'
COIN=Path('/workspace/scratch/1d5c10ddf0e3/caelab_mesher_round3_20261104/extra_candidates/root_research/coin_env')
def run(name,cmd,timeout=1200):
 t=time.monotonic()
 with (R/'logs'/f'{name}.log').open('w') as f:
  try:p=subprocess.run(list(map(str,cmd)),stdout=f,stderr=subprocess.STDOUT,timeout=timeout);rc=p.returncode;to=False
  except subprocess.TimeoutExpired:rc=None;to=True
 rec=dict(command=list(map(str,cmd)),seconds=time.monotonic()-t,returncode=rc,timeout=to)
 (R/'logs'/f'{name}.json').write_text(json.dumps(rec,indent=2));print(name,json.dumps(rec),flush=True)
 return rc==0
if __name__=='__main__':
 import sys
 if sys.argv[1]=='c4':
  eigen=R/'deps/eigen'
  ok=run('eigen_configure',[CM,'-S',R/'src/cinolib/external/eigen','-B',R/'build/eigen',f'-DCMAKE_INSTALL_PREFIX={eigen}','-DBUILD_TESTING=OFF','-DEIGEN_BUILD_DOC=OFF'])
  if ok:ok=run('eigen_install',[CM,'--install',R/'build/eigen'])
  configs=list(eigen.rglob('Eigen3Config.cmake'))
  if not ok or not configs:raise SystemExit(2)
  ok=run('c4_configure3',[CM,'-S',R/'src/C4HexMeshing','-B',R/'build/c4','-DCMAKE_BUILD_TYPE=Release','-DCMAKE_CXX_FLAGS_RELEASE=-O1 -DNDEBUG','-DMC3D_WITH_VIEWER=OFF','-DMC3D_BUILD_TESTS=OFF',f'-DCMAKE_PREFIX_PATH={COIN};{eigen}',f'-DCoinUtils_INCLUDE_DIR={COIN}/include/coin-or',f'-DCLP_INCLUDE_DIR={COIN}/include/coin-or',f'-DEigen3_DIR={configs[0].parent}','-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF','-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF'])
  if ok:run('c4_build',[CM,'--build',R/'build/c4','-j','2'],1800)
 elif sys.argv[1]=='hexgen':
  for stage in ['1-HBECVT','2-POLYCUBE','3-PARAMETRICMAPPING']:
   src=R/'src/HexGen_Hex2Spline/HexGen'/stage/'src'
   p=src/'cpp/RawMesh.cpp';s=p.read_text();marker='// Round5 POSIX string compatibility'
   if marker not in s:
    p.write_text(marker+'\n#include <cstring>\n#include <strings.h>\n#include <cctype>\n#define _strdup strdup\n#define _stricmp strcasecmp\nstatic char* _strupr(char* s) { for(char* p=s; *p; ++p) *p=static_cast<char>(std::toupper(static_cast<unsigned char>(*p))); return s; }\n'+s)
   p.write_text(p.read_text().replace('\ninline ', '\n'))
   run('hexgen_'+stage+'_portable4_build',[CM,'--build',R/'build'/('hexgen_'+stage),'-j','2'],600)
  patch=subprocess.check_output(['git','-C',str(R/'src/HexGen_Hex2Spline'),'diff'])
  (R/'logs/hexgen_portability.patch').write_bytes(patch)
