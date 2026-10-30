"""Extract factual R17 TOC names/locators and compare a pinned PyDYNA schema.

No solver execution and no deck generation. Requires local PDFs/text obtained from
the official URLs recorded in solvers/dyna.json. PDF/manual prose is not copied.
"""
from pathlib import Path
import argparse, ast, csv, json, re, collections

REV = '90270f787216c91a969d6b477aaf753d45556035'
VERSION = 'R17@e8334f9fb (06/11/26)'
URL = 'https://lsdyna.ansys.com/wp-content/uploads/2026/06/LS-DYNA_Manual_Vol_{}_R17.pdf'

def folios(pages):
    result = {}
    for i, page in enumerate(pages):
        lines = page.splitlines()
        for line in lines[:3] + lines[-5:]:
            if 'R17@' in line:
                for f in re.findall(r'\b\d+-\d+\b', line):
                    result[f] = i + 1
    return result

def write_csv(path, records):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(records[0]))
        w.writeheader()
        w.writerows(records)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', type=Path, default=Path('solver-input-research/tmp/dyna'))
    ap.add_argument('--output', type=Path, default=Path('solver-input-research/catalogues'))
    a = ap.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    schema = json.loads((a.input / 'pydyna/codegen/kwd.json').read_text())
    tree = ast.parse((a.input / 'pydyna/src/ansys/dyna/core/keywords/keyword_classes/type_mapping.py').read_text())
    mapping = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'TypeMapping' for t in n.targets))
    read_file = a.input / 'read-sections.json'
    read_ranges = json.loads(read_file.read_text()) if read_file.exists() else {}
    rows, aliases, reconciliations, all_toc = [], [], [], []
    for vi, volume in enumerate(['I', 'II', 'III'], 1):
        pages = (a.input / f'vol{vi}.txt').read_text().split('\f')
        if not pages[-1].strip(): pages = pages[:-1]
        fmap = folios(pages)
        toc_pages, star_lines, bad = [], [], []
        start_len = len(rows)
        for page_no, page in enumerate(pages, 1):
            if 'TABLE OF CONTENTS' not in page or not re.search(r'\.{3,}', page):
                continue
            toc_pages.append(page_no)
            for line in page.splitlines():
                am = re.match(r'^\s*(.+?)\s*\.{3,}\s*(\d+-\d+)\s*$', line)
                if am:
                    title, folio = am.groups()
                    all_toc.append({'entry_id':f'dyna-TOC{len(all_toc)+1:04d}',
                        'title':re.sub(r'\s+',' ',title).strip(), 'volume':volume,
                        'source_id':f'dyna-D0{vi+1}', 'toc_pdf_page':page_no,
                        'printed_page':folio, 'starred_keyword_entry':title.startswith('*'),
                        'kind':'starred-keyword-family-or-entry' if title.startswith('*') else 'heading-card-option-or-appendix-entry',
                        'official_url':URL.format(volume)+f'#page={page_no}',
                        'read_depth':'toc-only-not-all-option-fields-reviewed'})
                if not line.lstrip().startswith('*'):
                    continue
                star_lines.append((page_no, line))
                m = re.match(r'^(\s*)(\*.+?)\s*\.{3,}\s*(\d+-\d+)\s*$', line)
                if not m:
                    bad.append({'pdf_page':page_no, 'line':line})
                    continue
                indent, raw_name, printed = m.groups()
                name = re.sub(r'\s+', ' ', raw_name).strip()
                target = fmap.get(printed)
                resolution = 'printed-folio-extracted'
                toc_error = ''
                if target is not None and name not in '\n'.join(pages[target-1].splitlines()[:6]):
                    # Two R17 Vol I family headings have incorrect TOC folios.
                    # Preserve the source TOC folio, resolve the first actual
                    # family header separately, and record the discrepancy.
                    candidates = [i+1 for i,p in enumerate(pages)
                                  if name in '\n'.join(p.splitlines()[:5])]
                    if candidates:
                        original_target = target
                        target = candidates[0]
                        toc_error = f'TOC {printed} points to PDF {original_target}; exact family header first appears at PDF {target}'
                        resolution = 'TOC-folio-mismatch-exact-family-header'
                if target is None:
                    # Some database pages have no extractable printed footer.
                    # Anchor to a neighboring printed folio, then require the
                    # exact keyword in the candidate page's first five lines.
                    chapter, number = map(int, printed.split('-'))
                    anchors = [(abs(int(f.split('-')[1])-number), p-int(f.split('-')[1])+number)
                               for f,p in fmap.items() if int(f.split('-')[0]) == chapter]
                    for _, candidate in sorted(anchors):
                        if 0 < candidate <= len(pages) and name in '\n'.join(pages[candidate-1].splitlines()[:5]):
                            target = candidate
                            resolution = 'adjacent-folio-offset-and-exact-keyword-header'
                            break
                was_read = any(lo <= (target or -1) <= hi for lo, hi in read_ranges.get(f'vol{vi}', []))
                rows.append({
                    'entry_id':f'dyna-T{len(rows)+1:04d}', 'name':name,
                    'kind':'family-heading' if len(indent) <= 1 else 'keyword-or-option-entry',
                    'volume':volume, 'manual_version':VERSION, 'source_id':f'dyna-D0{vi+1}',
                    'toc_pdf_page':page_no, 'printed_page':printed, 'target_pdf_page':target,
                    'page_resolution':resolution if target else 'TOC-folio-only',
                    'toc_locator_discrepancy':toc_error,
                    'official_url':URL.format(volume) + (f'#page={target}' if target else ''),
                    'read_depth':'relevant-section' if was_read else 'index-only',
                    'pydyna_exact_schema_key':name[1:] if name[1:] in schema else '',
                    'pydyna_exact_class':mapping.get(name, ''),
                })
        reconciliations.append({'volume':volume, 'pdf_pages':len(pages), 'toc_pdf_pages':toc_pages,
            'toc_star_lines':len(star_lines), 'extracted_rows':len(rows)-start_len,
            'unparsed_star_lines':bad, 'unresolved_target_rows':sum(r['target_pdf_page'] is None for r in rows[start_len:])})
        if vi == 2:
            for page_no, page in enumerate(pages, 1):
                if 'ALPHABETIZED MATERIALS LIST' not in page:
                    continue
                for line in page.splitlines():
                    if not line.lstrip().startswith('*'):
                        continue
                    parts = re.split(r'\s{2,}', line.strip(), maxsplit=1)
                    aliases.append({'entry_id':f'dyna-A{len(aliases)+1:04d}', 'name':parts[0],
                        'numeric_alias_or_range':parts[1].strip() if len(parts)>1 else '',
                        'kind':'material/eos-alphabetic-row', 'source_id':'dyna-D03',
                        'pdf_page':page_no, 'official_url':URL.format('II')+f'#page={page_no}',
                        'read_depth':'index-only', 'solver_executed':False})
    write_csv(a.output/'dyna.csv', rows)
    write_csv(a.output/'dyna-toc-all.csv', all_toc)
    write_csv(a.output/'dyna-material-aliases.csv', aliases)
    differences = []
    for r in rows:
        if r['pydyna_exact_schema_key']:
            continue
        reason = ('family-heading-not-a-single-spec' if r['kind'] == 'family-heading' else
                  'generic-or-option-notation-not-expanded' if re.search(r'[{}<>]', r['name']) else
                  'exact-class-map-present-raw-schema-key-differs' if r['pydyna_exact_class'] else
                  'no-exact-name-match-requires-semantic-review')
        differences.append({**r, 'comparison_status':reason,
                            'unsupported_claim':False})
    write_csv(a.output/'dyna-toc-schema-differences.csv', differences)
    keys = [{'name':'*'+k, 'kind':'pydyna-raw-card-specification', 'source_id':'dyna-D09',
             'revision':REV, 'cards':len(v), 'fields':sum(len(c.get('fields', [])) for c in v),
             'class_name':mapping.get('*'+k,''), 'official_r17_match':'exact-TOC-name' if any(r['name']=='*'+k for r in rows) else 'not-an-exact-TOC-name',
             'read_depth':'schema-enumerated-not-all-field-reviewed', 'solver_executed':False}
            for k,v in schema.items()]
    write_csv(a.output/'dyna-pydyna-schema.csv', keys)
    stats = {'scope':'Complete starred TOC rows of official R17 Vol I-III; no inferred expansion of generic/options notation. This is not all keyword variants or full field verification.',
        'manual_version':VERSION, 'volumes':reconciliations, 'all_toc_rows':len(all_toc),
        'nonstar_toc_rows':sum(not r['starred_keyword_entry'] for r in all_toc), 'toc_rows':len(rows),
        'distinct_toc_names':len({r['name'] for r in rows}), 'family_heading_rows':sum(r['kind']=='family-heading' for r in rows),
        'duplicate_literal_name_rows':len(rows)-len({r['name'] for r in rows}),
        'material_alphabetic_rows':len(aliases), 'material_rows_with_numeric_alias':sum(bool(r['numeric_alias_or_range']) for r in aliases),
        'pydyna_raw_schema_keys':len(schema), 'pydyna_raw_cards':sum(len(v) for v in schema.values()),
        'pydyna_raw_fields':sum(len(c.get('fields',[])) for v in schema.values() for c in v),
        'pydyna_type_mapping_entries':len(mapping),
        'toc_exact_schema_match_rows':sum(bool(r['pydyna_exact_schema_key']) for r in rows),
        'toc_exact_class_match_rows':sum(bool(r['pydyna_exact_class']) for r in rows),
        'toc_exact_schema_mismatch_rows':sum(not r['pydyna_exact_schema_key'] for r in rows),
        'toc_locator_discrepancies':[{'entry_id':r['entry_id'], 'name':r['name'],
                                      'source_toc_folio':r['printed_page'],
                                      'resolved_pdf_page':r['target_pdf_page'],
                                      'reason':r['toc_locator_discrepancy']}
                                     for r in rows if r['toc_locator_discrepancy']],
        'mismatch_categories':dict(collections.Counter(r['comparison_status'] for r in differences)),
        'exact_match_is_semantic_coverage':False,
        'full_variant_expansion_complete':False, 'full_field_review_complete':False, 'runtime_verified':False}
    (a.output/'dyna-reconciliation.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(stats,ensure_ascii=False,indent=2))

if __name__ == '__main__': main()
