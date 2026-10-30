"""Extract factual document locators from the acquired official v17 index only."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin
import csv

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://code-aster.org/doc/v17/manuals/man_u/other_pages/commands/index.html'

class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.active = False; self.anchor = None; self.rows = []
    def handle_starttag(self, tag, attrs):
        if tag == 'article': self.active = True
        if self.active and tag == 'a': self.anchor = [dict(attrs).get('href'), []]
    def handle_data(self, data):
        if self.anchor is not None: self.anchor[1].append(data)
    def handle_endtag(self, tag):
        if tag == 'a' and self.anchor is not None:
            href, parts = self.anchor
            if 'index.html' in str(href):
                self.rows.append(dict(title=''.join(parts).strip(), url=urljoin(URL, href), kind='manual document (not necessarily one command)', source_id='aster-D02', read_depth='index parsed; detailed review only in separately listed sources'))
            self.anchor = None
        if tag == 'article': self.active = False

if __name__ == '__main__':
    parser = Links(); parser.feed((ROOT/'tmp/aster/manual-command-index.html').read_text())
    assert len(parser.rows) == 270 and len({row['url'] for row in parser.rows}) == 270
    with (ROOT/'catalogues/aster-manual-index.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(parser.rows[0])); writer.writeheader(); writer.writerows(parser.rows)
    print('270 unique official v17 document locators; not 270 distinct commands')
