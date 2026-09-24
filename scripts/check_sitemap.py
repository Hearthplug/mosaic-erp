"""Sitemap sanity for the public Pages site (docs/): every public page is
listed, every URL has a valid lastmod. Pair with the CI step that fails a PR
which touches docs/*.html without touching docs/sitemap.xml, so lastmod moves
on every deploy that changes the site."""
import re, sys, os, datetime

DOCS = os.path.join(os.path.dirname(__file__), '..', 'docs')

def main():
    xml = open(os.path.join(DOCS, 'sitemap.xml'), encoding='utf-8').read()
    locs = set(re.findall(r'<loc>(.*?)</loc>', xml))
    mods = re.findall(r'<lastmod>(.*?)</lastmod>', xml)
    if len(mods) != len(locs):
        sys.exit('sitemap: every url needs a lastmod')
    for m in mods:
        try:
            datetime.date.fromisoformat(m)
        except ValueError:
            sys.exit(f'sitemap: bad lastmod {m!r}')
    missing = []
    for f in sorted(os.listdir(DOCS)):
        if not f.endswith('.html') or f.startswith('google'):
            continue
        path = '/' if f == 'index.html' else '/' + f
        if f'https://mosaic-erp.pages.dev{path}' not in locs:
            missing.append(f)
    if missing:
        sys.exit('sitemap: public pages not listed: ' + ', '.join(missing))
    print(f'sitemap OK: {len(locs)} urls')

if __name__ == '__main__':
    main()
