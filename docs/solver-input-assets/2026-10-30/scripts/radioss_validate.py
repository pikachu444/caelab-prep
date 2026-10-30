"""Validate acquired research records and hashes; never execute upstream code."""
from pathlib import Path
import ast, collections, csv, hashlib, json, zipfile

ROOT = Path(__file__).resolve().parents[1]
def digest(b): return hashlib.sha256(b).hexdigest()
d = json.loads((ROOT/'solvers/radioss.json').read_text())
errors=[];checks={}
def check(name, condition):
    checks[name]=bool(condition)
    if not condition:errors.append(name)
sids={s['id'] for s in d['sources']}
check('source_ids_unique',len(sids)==len(d['sources']))
for group in ['rules','examples','code_assets']:
    check(group+'_source_refs',all(s in sids for x in d[group] for s in x['source_ids']))
rids={x['id'] for x in d['rules']}
check('Q01_Q12_present',{x['question_id'] for x in d['coverage']}=={f'Q{i:02}' for i in range(1,13)})
check('coverage_rule_refs',all(r in rids for x in d['coverage'] for r in x['rule_ids']))
check('runtime_false',d['runtime_verified'] is False and d['versions']['binary_tested'] is None and all(x['solver_executed'] is False for x in d['examples']) and all(x['executed'] is False for x in d['code_assets']))
check('full_field_review_false',d['catalogue']['full_field_review_complete'] is False)
for s in d['sources']:
    if s.get('local_file'):
        p=ROOT/s['local_file']
        check('source_hash_'+s['id'],p.is_file() and digest(p.read_bytes())==s['sha256'] and p.stat().st_size==s['size_bytes'])
rows=list(csv.DictReader((ROOT/'catalogues/radioss.csv').open()))
check('catalogue_825',len(rows)==825)
check('catalogue_stage_counts',collections.Counter(x['stage'] for x in rows)=={'starter':590,'engine':235})
check('catalogue_pair_unique',len({(x['stage'],x['name'],x['official_url']) for x in rows})==825)
check('catalogue_refs',all(x['source_id'] in sids for x in rows))
check('catalogue_no_support_claim',all(x['solver_support']=='not-verified' for x in rows))
check('catalogue_ftfile_raw',any(x['name']=='FTFILE' and x['official_url'].endswith('/atfile_engine_r.htm') for x in rows))
manifest=json.loads((ROOT/'catalogues/radioss-detail-acquisition.json').read_text())
check('detail804',len(manifest['results'])==804 and all(x['status']=='downloaded' for x in manifest['results']))
check('detail_hashes',all((ROOT/x['file']).is_file() and digest((ROOT/x['file']).read_bytes())==x['sha256'] and (ROOT/x['file']).stat().st_size==x['size_bytes'] for x in manifest['results']))
check('detail_read_depth35_769',collections.Counter(x['read_depth'] for x in manifest['results'])=={'relevant-sections':35,'not-read':769})
check('catalogue_review35_790',collections.Counter(x['detail_review'] for x in rows)=={'relevant-sections':35,'index-only':790})
archive=zipfile.ZipFile(ROOT/'tmp/radioss/oc-source-archive.zip')
rootname=archive.namelist()[0].split('/')[0]+'/'
for key,field in [('cfg','files'),('qa','entries')]:
    inv=json.loads((ROOT/f'catalogues/radioss-{key}-inventory.json').read_text())
    items=inv[field]
    check(key+'_inventory_archive_hashes',all(digest(archive.read(rootname+x['path']))==x['sha256'] and len(archive.read(rootname+x['path']))==x['size_bytes'] for x in items))
for x in d['examples']:
    if x.get('members'):
        check('example_hashes_'+x['id'],all(digest((ROOT/m['internal_file']).read_bytes())==m['sha256'] for m in x['members']))
    check('example_no_deck_redistribution_'+x['id'],x['file'] is None and x['redistribution']=='locator-only')
code=json.loads((ROOT/'examples/radioss/code-manifest.json').read_text())
check('code_manifest_hashes',all(digest((ROOT/x['file']).read_bytes())==x['sha256'] for x in code['files']))
for local,path in [('radiossblk.cxx','reader/source/io/model_readers/radioss/radiossblk/radiossblk.cxx'),('mec_data_writer.cpp','reader/source/cfgio/MODEL_IO/mec_data_writer.cpp'),('mec_single_file_writer.cpp','reader/source/cfgio/MODEL_IO/mec_single_file_writer.cpp'),('verify_results.py','qa-tests/qa_tools/verify_results.py')]:
    check('unmodified_upstream_'+local,(ROOT/'examples/radioss/code'/local).read_bytes()==archive.read(rootname+path))
converter=(ROOT/'examples/radioss/code/inp2rad.py').read_bytes()
blob=hashlib.sha1(b'blob '+str(len(converter)).encode()+b'\0'+converter).hexdigest()
check('converter_original_git_blob',blob=='21a69847111357c3e7e1d47dcee0b2eb41a736ba')
check('converter_AST85_functions',len([x for x in ast.walk(ast.parse(converter)) if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))])==85)
check('NOTICE_and_notes_exist',(ROOT/'examples/radioss/NOTICE.md').is_file() and (ROOT/'notes/radioss.md').is_file())
report={'checks':checks,'check_count':len(checks),'errors':errors,'error_count':len(errors),'summary':{'sources':len(d['sources']),'rules':len(d['rules']),'examples':len(d['examples']),'code_assets':len(d['code_assets']),'index_rows':len(rows),'detail_pages':804,'detail_bytes':sum(x['size_bytes'] for x in manifest['results']),'relevant_detail_pages':35,'detail_not_read':769,'full_field_review_complete':False,'runtime_verified':False},'limits':'Research structural/hash checks only. No converter, solver, upstream tests, or numerical validation executed.'}
(ROOT/'catalogues/radioss-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'check_count':len(checks),'error_count':len(errors),'errors':errors,'summary':report['summary']},ensure_ascii=False))
raise SystemExit(bool(errors))
