"""Extract factual names/locators from Bulk, I/O, Subcase and PARAM indexes.

Usage: python scripts/opti_catalogue.py ROOT
ROOT contains tmp/opti-nastran downloaded HTML and catalogues/.
No solver execution and no generation of a solver deck.
"""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin
import csv, json, sys

class ChildLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.strong = 0
        self.href = None
        self.text = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == 'strong':
            self.strong += 1
        if tag == 'a' and self.strong:
            self.href = dict(attrs).get('href')
            self.text = []

    def handle_data(self, data):
        if self.href is not None:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.href is not None:
            self.rows.append((''.join(self.text).strip(), self.href))
            self.href = None
        if tag == 'strong' and self.strong:
            self.strong -= 1

def extract(root):
    acq = json.loads((root/'tmp/opti-nastran/acquisition.json').read_text())
    by_key = {row['key']: row for row in acq}
    all_rows, sections = [], []
    for key, section, sid in [('opti-bulk','bulk','optistruct-D01'),
                               ('opti-io','io','optistruct-D02'),
                               ('opti-subcase','subcase','optistruct-D03'),
                               ('opti-param_bulk_r','param-option','optistruct-D04')]:
        text = (root/'tmp/opti-nastran'/f'{key}.html').read_text()
        # DITA puts child links after </main>; restricting to main loses all rows.
        start = text.index('<ul class="ullinks"')
        end = text.index('</nav>', start)
        child = text[start:end]
        parser = ChildLinks()
        parser.feed(child)
        assert len(parser.rows) == child.count('<strong>')
        assert len(set(parser.rows)) == len(parser.rows)
        rows = parser.rows
        if section == 'param-option':
            rows = [row for row in rows if row[0].startswith('PARAM,')]
            assert len(parser.rows) - len(rows) == 1  # Parameters by Function
        sections.append({'section':section,'entries':len(rows),
                         'source_id':sid,'first':rows[0][0],
                         'last':rows[-1][0]})
        for name, link in rows:
            all_rows.append({'name':name,'kind':section,
                'url':urljoin(by_key[key]['url'],link),'source_id':sid,
                'read_depth':'index-only','implementation_verified':'false',
                'solver_executed':'false'})
    with (root/'catalogues/optistruct.csv').open('w',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    (root/'tmp/opti-nastran/opti-index-summary.json').write_text(json.dumps(sections,indent=2))
    return sections

if __name__ == '__main__':
    print(json.dumps(extract(Path(sys.argv[1] if len(sys.argv)>1 else '.')),indent=2))
