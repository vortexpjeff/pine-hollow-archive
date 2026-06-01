#!/usr/bin/env python3
"""Fetch common names from Wikipedia — serial, rate-limited, reliable."""
import json, csv, time, sys
from pathlib import Path
import requests

CACHE = Path("/mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive/common_names.json")
LABELS = Path.home() / ".cache/kagglehub/models/google/bird-vocalization-classifier/tensorFlow2/perch_v2_cpu/1/assets/labels.csv"
HEADERS = {"User-Agent": "PineHollow/1.0 (solaris@pinehollow.bio)"}

with open(LABELS) as f:
    reader = csv.reader(f)
    all_species = [r[0].strip() for r in reader][1:]

cache = {}
if CACHE.exists():
    with open(CACHE) as f:
        cache = json.load(f)

# Species not yet looked up
to_fetch = [s for s in all_species if s not in cache and " " in s and s[0].isupper()]
print(f"Need to fetch: {len(to_fetch)}")

t0 = time.time()
found = 0
for i, species in enumerate(to_fetch):
    try:
        r = requests.get("https://en.wikipedia.org/w/api.php", params={
            "action": "query", "format": "json", "titles": species,
            "redirects": 1, "prop": "pageprops",
        }, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            for pid, page in r.json().get("query", {}).get("pages", {}).items():
                if pid != "-1":
                    title = page.get("title", "")
                    if title and title.lower() != species.lower():
                        cache[species] = title
                        found += 1
    except Exception as e:
        print(f"  Error at {species}: {e}", file=sys.stderr)
    
    if (i + 1) % 50 == 0:
        elapsed = time.time() - t0
        rate = (i + 1) / elapsed if elapsed > 0 else 0
        print(f"  {i+1}/{len(to_fetch)} ({found} found, {rate:.1f}/s)")
        with open(CACHE, "w") as f:
            json.dump(cache, f, indent=2, sort_keys=True)
    
    # Polite delay: 20 req/s
    if (i + 1) % 20 == 0:
        time.sleep(0.5)

with open(CACHE, "w") as f:
    json.dump(cache, f, indent=2, sort_keys=True)

elapsed = time.time() - t0
print(f"\nDone! {len(cache)} names ({found} new) in {elapsed:.0f}s")
