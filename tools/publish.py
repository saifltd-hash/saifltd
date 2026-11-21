#!/usr/bin/env python3
"""Validate the daily editions and rebuild the archive index.

Usage (from the repository root):
    python3 tools/publish.py

Checks every news-tech/data/YYYY-MM-DD.json against the schema described in
news-tech/README.md, then rewrites news-tech/data/index.json so that it lists
the editions of the last 62 days (two months), newest first.
Exits with status 1 and prints the problems if any edition is invalid;
in that case index.json is left untouched.
"""
import datetime
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / 'news-tech' / 'data'
ARCHIVE_DAYS = 62
CATEGORIES = {'ai', 'security', 'infra', 'saudi', 'business', 'hardware', 'devices', 'science', 'other'}
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]{2,79}$')
URL_RE = re.compile(r'^https?://[^\s]+$')
RIYADH = datetime.timezone(datetime.timedelta(hours=3))


def check_edition(path):
    errors = []
    try:
        edition = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeDecodeError) as exc:
        return None, ['%s: not valid UTF-8 JSON (%s)' % (path.name, exc)]

    def err(msg):
        errors.append('%s: %s' % (path.name, msg))

    date = edition.get('date')
    if date != path.stem:
        err('"date" must equal the file name (%s)' % path.stem)
    try:
        day = datetime.date.fromisoformat(path.stem)
    except ValueError:
        err('file name is not a real date')
        day = None

    items = edition.get('items')
    if not isinstance(items, list) or not 5 <= len(items) <= 40:
        err('"items" must be a list of 5 to 40 news items')
        return edition, errors

    seen = set()
    leads = 0
    tops = 0
    for n, item in enumerate(items, 1):
        where = 'item %d' % n
        if not isinstance(item, dict):
            err('%s is not an object' % where)
            continue
        ident = item.get('id', '')
        if not isinstance(ident, str) or not ID_RE.match(ident):
            err('%s: "id" must be a lowercase latin slug (a-z, 0-9, -), 3-80 chars' % where)
        elif ident in seen:
            err('%s: duplicate id "%s"' % (where, ident))
        seen.add(ident)
        if item.get('category') not in CATEGORIES:
            err('%s: "category" must be one of %s' % (where, ', '.join(sorted(CATEGORIES))))
        for field, low, high in (('title', 10, 170), ('summary', 60, 750), ('source', 1, 60)):
            value = item.get(field)
            if not isinstance(value, str) or not low <= len(value.strip()) <= high:
                err('%s: "%s" must be text of %d-%d characters' % (where, field, low, high))
        url = item.get('url')
        if not isinstance(url, str) or not URL_RE.match(url):
            err('%s: "url" must be an http(s) link to the source article' % where)
        published = item.get('published')
        if not isinstance(published, str) or not DATE_RE.match(published):
            err('%s: "published" must be YYYY-MM-DD' % where)
        elif day is not None:
            try:
                pub = datetime.date.fromisoformat(published)
                if pub > day:
                    err('%s: "published" is after the edition date' % where)
            except ValueError:
                err('%s: "published" is not a real date' % where)
        leads += 1 if item.get('lead') is True else 0
        tops += 1 if item.get('top') is True else 0
    if leads != 1:
        err('exactly one item must have "lead": true (found %d)' % leads)
    if tops > 3:
        err('at most three items may have "top": true (found %d)' % tops)
    return edition, errors


def main():
    files = sorted((p for p in DATA.glob('*.json') if DATE_RE.match(p.stem)), reverse=True)
    if not files:
        print('No editions found in', DATA)
        return 1
    problems = []
    editions = []
    for path in files:
        edition, errors = check_edition(path)
        problems.extend(errors)
        if edition is not None and not errors:
            lead = next(i for i in edition['items'] if i.get('lead') is True)
            editions.append({'date': path.stem, 'count': len(edition['items']), 'lead': lead['title']})
    if problems:
        print('Found %d problem(s):' % len(problems))
        for p in problems:
            print(' -', p)
        return 1

    newest = datetime.date.fromisoformat(editions[0]['date'])
    kept = [e for e in editions if (newest - datetime.date.fromisoformat(e['date'])).days <= ARCHIVE_DAYS]
    index = {
        'updated': datetime.datetime.now(RIYADH).replace(microsecond=0).isoformat(),
        'editions': kept,
    }
    (DATA / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('OK: %d edition(s) valid, %d listed in the two-month archive, newest %s (%d items)'
          % (len(editions), len(kept), kept[0]['date'], kept[0]['count']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
