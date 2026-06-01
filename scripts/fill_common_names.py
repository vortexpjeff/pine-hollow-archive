#!/usr/bin/env python3
"""Fill common name cache gaps for species appearing in our archive."""
import json, sqlite3, asyncio
from pathlib import Path
import aiohttp

ARCHIVE = Path("/mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive")
CACHE = ARCHIVE / "common_names.json"
HEADERS = {"User-Agent": "PineHollowBioacoustics/2.0 (solaris@pinehollow.bio)"}
CONCURRENT = 8

# Load existing
cache = json.load(open(CACHE)) if CACHE.exists() else {}

# Get species from archive
conn = sqlite3.connect(str(ARCHIVE / "archive.db"))
conn.row_factory = sqlite3.Row
species = set()
for row in conn.execute("SELECT perch_top10 FROM clips WHERE perch_top10 IS NOT NULL"):
    try:
        for entry in json.loads(row["perch_top10"]):
            sp = entry.get("species", "")
            if sp and " " in sp:
                species.add(sp)
    except: pass
for row in conn.execute("SELECT source_label FROM clips WHERE source='public'"):
    sp = row["source_label"] or ""
    sp = sp.replace("_", " ").strip()
    if sp and " " in sp:
        species.add(sp)
conn.close()

missing = sorted(s for s in species if s not in cache)
print(f"Species in archive: {len(species)}, have common names: {len(species & set(cache.keys()))}, missing: {len(missing)}")

async def fetch_one(session, species, sem):
    async with sem:
        try:
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{species.replace(' ', '_')}"
            async with session.get(url, headers=HEADERS, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    title = data.get("title", "").replace("_", " ")
                    # Title IS the common name if it differs from the scientific name
                    if title.lower() != species.lower():
                        return species, title
                    # Check for vernacular name in description
                    desc = data.get("extract", "")
                    if "commonly known as" in desc.lower():
                        import re
                        m = re.search(r'commonly known as\s+(?:the\s+)?["\']?([^"\'.,]+)', desc, re.I)
                        if m:
                            return species, m.group(1)
                elif resp.status == 404:
                    return species, None
            return None
        except Exception:
            return None

async def main():
    sem = asyncio.Semaphore(CONCURRENT)
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_one(session, sp, sem) for sp in missing]
        results = await asyncio.gather(*tasks)
    
    new = 0
    for result in results:
        if result:
            sp, name = result
            if name:
                cache[sp] = name
                new += 1
    
    with open(CACHE, 'w') as f:
        json.dump(cache, f, indent=2)
    
    print(f"Added {new} common names. Cache now has {len(cache)} entries.")

asyncio.run(main())
