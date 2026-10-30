#!/usr/bin/env python3
"""Generate novel Genesis-28 candidate families (translations NOT previously tested:
asv, darby, dra, bbe, almeida, clementine, rccv) with many serializations,
plus verse-index readings for the "6 3 18" key."""
import json, pickle, re, sys

texts = pickle.load(open('/home/sudosudo/.openclaw/workspace/gen28_texts.pkl','rb'))
# also fetch verses individually
import urllib.request

def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())

cands = set()

def serialize_verse(v, tr):
    """All serializations of a single verse string."""
    out = set()
    # collapse whitespace
    s = re.sub(r'\s+', ' ', v).strip()
    if not s: return out
    out.add(s)                              # original punctuation/case
    out.add(s.lower())
    out.add(s.upper())
    # words, punctuation removed, spaces kept
    w = re.sub(r'[^A-Za-z0-9\' ]', '', s)
    w = re.sub(r'\s+', ' ', w).strip()
    out.add(w); out.add(w.lower())
    # words joined no spaces
    j = w.replace(' ', '')
    out.add(j); out.add(j.lower()); out.add(j.capitalize())
    # joined with initial caps
    words = w.split()
    out.add(''.join(x.capitalize() for x in words))
    out.add(' '.join(x.capitalize() for x in words))
    # first 20 chars
    out.add(s[:20]); out.add(w[:20]); out.add(j[:20]); out.add(j.lower()[:20])
    # first 20 words joined
    out.add(''.join(words[:20]))
    return out

for tr, full in texts.items():
    if not full.strip():
        continue
    # full chapter
    cands |= serialize_verse(full, tr)
    # individual verses via API
    try:
        d = get(f"https://bible-api.com/genesis+28?translation={tr}")
        for v in d.get('verses', []):
            cands |= serialize_verse(v.get('text',''), tr)
    except Exception as e:
        print(f"verse fetch {tr}: {e}", file=sys.stderr)

# verse-index readings from the "6 3 18" key: verses 6, 3, 18 (and other orders)
try:
    d = get("https://bible-api.com/genesis+28?translation=kjv")
    verses = {v['verse']: v['text'] for v in d.get('verses', [])}
    for combo in [(6,3,18),(18,3,6),(6,18,3),(3,6,18),(3,18,6),(18,6,3)]:
        parts = [verses.get(n,'') for n in combo]
        joined = ' '.join(parts)
        cands |= serialize_verse(joined, 'kjv')
except Exception as e:
    print("verseidx:", e, file=sys.stderr)

# Genesis 6:3, 6:18, 3:18 etc (the "6 3 18" as chapter:verse)
for ref in ["genesis+6:3","genesis+6:18","genesis+3:18","genesis+28:6","genesis+28:3","genesis+28:18"]:
    for tr in ['kjv','web']:
        try:
            d = get(f"https://bible-api.com/{ref}?translation={tr}")
            cands |= serialize_verse(d.get('text',''), tr)
        except Exception:
            pass

cands = sorted(c for c in cands if c)
with open('/home/sudosudo/.openclaw/workspace/gen28_cands.txt','w') as f:
    f.write('\n'.join(cands))
print("generated", len(cands), "candidates")
