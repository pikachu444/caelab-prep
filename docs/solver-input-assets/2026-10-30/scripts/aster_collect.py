"""Offline reconciliation of pinned Code_Aster source; no solver execution.

This script reads acquired published source and extracts factual AST metadata.
Upstream GPLv3+ source is kept with its LICENSE and provenance manifest.
"""
from pathlib import Path
import json, hashlib, ast, csv

ROOT = Path(__file__).resolve().parents[1]
REV = 'c1f5c46ef795e0bf6d82a29dc20da30d281535ce'
BASE = 'https://gitlab.com/api/v4/projects/32737231/repository/'
TMP = ROOT/'tmp/aster'
UP = ROOT/'examples/aster/upstream'
CAT = ROOT/'catalogues'
for p in [TMP,UP,CAT]: p.mkdir(parents=True,exist_ok=True)

# Offline reconciliation of the pinned source snapshot; never import Cata or libaster.
# Acquisition: official Git sparse clone, tag 17.5.8, exact REV above.
# Entire Cata and run_aster source plus the sslv139a public testcase were copied
# with upstream LICENSE and file headers. This is not a standalone solver install.
paths=[str(p.relative_to(UP)) for p in sorted((UP/'code_aster/Cata/Commands').glob('*.py'))]
assert len(paths)==270
manifest=[]
for p in sorted(UP.rglob('*')):
    if p.is_file():
        b=p.read_bytes(); path=str(p.relative_to(UP))
        manifest.append({'path':path,'file':str(p.relative_to(ROOT)),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'url':'https://gitlab.com/codeaster/src/-/blob/'+REV+'/'+path,'revision':REV,'status':'downloaded'})
(TMP/'source-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
commands=[]; factors=[]; issues=[]
for path in paths[:270]:
    f=UP/path
    if not f.is_file():issues.append({'path':path,'problem':'missing'});continue
    try: tree=ast.parse(f.read_text())
    except Exception as e:issues.append({'path':path,'problem':str(e)});continue
    for node in tree.body:
        if not isinstance(node,ast.Assign) or not isinstance(node.value,ast.Call):continue
        call=node.value; fun=call.func.id if isinstance(call.func,ast.Name) else ''
        if fun not in ['OPER','MACRO','PROC','FIN_PROC','FORM','VariableSupport']:continue
        kwargs={k.arg:k.value for k in call.keywords if k.arg}
        nom=kwargs.get('nom')
        name=ast.literal_eval(nom) if isinstance(nom,ast.Constant) else ','.join(ast.unparse(t) for t in node.targets)
        commands.append({'name':name,'kind':fun,'source_id':'aster-D01','source_path':path,'line':node.lineno,'url':'https://gitlab.com/codeaster/src/-/blob/'+REV+'/'+path+'#L'+str(node.lineno),'depth':'schema-source-acquired; AST structure extracted; not all fields semantically reviewed','file':str(f.relative_to(ROOT))})
        for sub in ast.walk(call):
            if fun!='VariableSupport' and isinstance(sub,ast.Call) and isinstance(sub.func,ast.Name) and sub.func.id in ['SIMP','FACT','BLOC']:
                factors.append({'command':name,'kind':sub.func.id,'path':path,'line':sub.lineno})

names=[v['name'] for v in commands]
assert len(names)==len(set(names)), 'duplicate declared command name'
with (CAT/'aster.csv').open('w',newline='') as out:
    w=csv.DictWriter(out,fieldnames=list(commands[0]));w.writeheader();w.writerows(commands)
(CAT/'aster-structure.json').write_text(json.dumps({'revision':REV,'file_count':270,'catalogue_entries':len(commands),'actual_command_definitions':sum(v['kind']!='VariableSupport' for v in commands),'special_helpers':sum(v['kind']=='VariableSupport' for v in commands),'types':{k:sum(v['kind']==k for v in commands) for k in ['OPER','MACRO','PROC','FIN_PROC','FORM','VariableSupport']},'lexical_nested_syntax_nodes':{k:sum(v['kind']==k for v in factors) for k in ['SIMP','FACT','BLOC']},'files_without_command':[p for p in paths[:270] if p not in {v['source_path'] for v in commands}],'parse_issues':issues,'unique_entry_names':len(set(names)),'manual_index_document_rows':270,'manual_index_unique_locators':270,'interpretation':'FIN_PROC is a special procedural Command; VARIABLE is not a Command. Counts are lexical SIMP/FACT/BLOC calls within top-level Command declaration call subtrees only, excluding file-local helper factory/function definitions and expanded Commons factories. They are not unique or semantically validated keyword parameters. Manual index counts are reconciled separately in aster-manual-index.csv.','full_parameter_review_complete':False,'runtime_verified':False},ensure_ascii=False,indent=2)+'\n')
print((CAT/'aster-structure.json').read_text(),flush=True)
