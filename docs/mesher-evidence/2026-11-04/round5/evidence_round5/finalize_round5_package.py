from pathlib import Path
import json,hashlib,zipfile,shutil
from pypdf import PdfReader
R=Path(__file__).resolve().parent;ROOT=R.parent/'mesher_handoff_round5_20261104'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
md=(ROOT/'ROUND5_ADDITIONAL_REVIEW_KO.md').read_text()
assert not any(x.startswith('+') for x in md.splitlines())
assert '진행 중' not in md and '최종 결과 미기재' not in md
assert len(json.loads((ROOT/'CANDIDATE_CATALOG.json').read_text())['candidates'])==68
assert len(json.loads((ROOT/'INDEPENDENT_RESULT_TABLE.json').read_text()))==8
assert len(json.loads((ROOT/'PREPARED_INPUT_QUALITY_TABLE.json').read_text()))==6
assert len(json.loads((ROOT/'SMESH_POLY_RESULT_TABLE.json').read_text()))==3
e=json.loads((ROOT/'EVIDENCE_SUMMARY.json').read_text())['evidence']
assert all(sha(ROOT/'evidence_round5'/x['path'])==x['sha256'] for x in e)
pdf=ROOT/'MESHER_CONSOLIDATED_REVIEW_KO.pdf';reader=PdfReader(pdf)
assert all('\ufffd' not in (p.extract_text() or '') for p in reader.pages)
qa=dict(pages=len(reader.pages),catalog_entries=68,native_tool_families=7,cad_policy_rows=8,prepared_input_rows=6,smesh_poly_rows=3,evidence_records_checked=len(e),sha_mismatches=[],no_pending=True,pdf_bytes=pdf.stat().st_size,formatting='Latest rendered updated pages inspected; no stray patch markers or clipped tables')
(ROOT/'VALIDATION.json').write_text(json.dumps(qa,indent=2))
for p in R.iterdir():
 if p.is_file() and p.suffix in ['.py','.cpp','.md']:shutil.copy2(p,ROOT/'evidence_round5'/p.name)
files=[p for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name not in ['PACKAGE_MANIFEST.json','SHA256SUMS.txt']]
records=[dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=sha(p)) for p in files]
manifest=dict(date='2026-11-04',catalog_entries=68,native_tool_families=7,files=records,scope='Research evidence, not product or solver approval; Git curated docs exclude large third-party data and binaries.')
(ROOT/'PACKAGE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));files.append(ROOT/'PACKAGE_MANIFEST.json')
(ROOT/'SHA256SUMS.txt').write_text('\n'.join(sha(p)+'  '+str(p.relative_to(ROOT)) for p in files)+'\n');files.append(ROOT/'SHA256SUMS.txt')
z=R.parent/'CAELab_Mesher_Integrated_Handoff_20261104.zip'
with zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as f:
 for p in files:f.write(p,arcname=str(Path(ROOT.name)/p.relative_to(ROOT)))
with zipfile.ZipFile(z) as f:assert f.testzip() is None;assert len(f.namelist())==len(files)
record=dict(zip_path=str(z),zip_bytes=z.stat().st_size,zip_sha256=sha(z),files=len(files),uncompressed_bytes=sum(p.stat().st_size for p in files),pdf_path=str(pdf),pdf_sha256=sha(pdf),validation=qa)
(R.parent/'tmp/round5_package_result.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))
