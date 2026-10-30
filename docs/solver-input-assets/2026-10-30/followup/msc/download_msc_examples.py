"""Download selected official MSC Nastran example inputs; never run a solver.

python download_msc_examples.py --output msc-examples
python download_msc_examples.py --output msc-examples --all-variants --guides

Default: the three complete SOL400 models discussed in README.md. Existing files
are preserved. Public access is not a grant to redistribute vendor content.
"""
from pathlib import Path
import argparse
import urllib.request

EXAMPLES = {
    'ch047': ['nug_47a.dat', 'nug_47ax.dat', 'nug_47b.dat', 'nug_47bx.dat'],
    'ch027': ['nug_27.dat', 'nug_27f.dat', 'nug_27a.dat', 'nug_27c.dat'],
    'ch010': ['nug_10.dat', 'nug_10_bolt.dat', 'nug_10_bolt1a.dat',
              'nug_10_bolt1b.dat', 'nug_10_bolt1c.dat', 'nug_10_bolt1d.dat'],
}
GUIDES = [
    'MSC_Nastran_2024.2_Linear_Static_Analysis_User_Guide',
    'MSC_Nastran_2024.2_Getting_Started_Guide',
    'MSC_Nastran_2024.2_SOL_400_Getting_Started_Guide',
]

def download(url, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        print(f'Preserved existing file: {destination}')
        return
    with urllib.request.urlopen(url, timeout=45) as response:
        data = response.read()
    destination.write_bytes(data)
    print(f'Downloaded: {destination}')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('msc-examples'))
    parser.add_argument('--all-variants', action='store_true')
    parser.add_argument('--guides', action='store_true')
    args = parser.parse_args()
    for chapter, names in EXAMPLES.items():
        for name in names if args.all_variants else names[:1]:
            url = f'https://www.mscsoftware.com/doc/nastran/mdug/input_files/{chapter}/{name}'
            download(url, args.output/chapter/name)
    if args.guides:
        for name in GUIDES:
            url = f'https://documentation-be.hexagon.com/bundle/{name}/raw/resource/enus/{name}.pdf'
            download(url, args.output/'guides'/(name+'.pdf'))

if __name__ == '__main__':
    main()
