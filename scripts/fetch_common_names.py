#!/usr/bin/env python3
"""Fetch common names for species in our archive via async Wikipedia API."""
import json, sqlite3, csv, asyncio, time
from pathlib import Path
import aiohttp

ARCHIVE = Path("/mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive")
DB = ARCHIVE / "archive.db"
CACHE = ARCHIVE / "common_names.json"
HEADERS = {"User-Agent": "PineHollowBioacoustics/2.0 (solaris@pinehollow.bio)"}

conn = sqlite3.connect(str(DB))
rows = conn.execute("SELECT perch_top10, perch_top50 FROM clips WHERE perch_embedding IS NOT NULL").fetchall()
conn.close()

species = set()
for r in rows:
    for field in [r[0], r[1]]:
        if field:
            for entry in json.loads(field):
                s = entry.get("species", "")
                if s and " " in s and s[0].isupper():
                    species.add(s)

cache = {}
if CACHE.exists():
    with open(CACHE) as f:
        cache = json.load(f)

to_fetch = [s for s in sorted(species) if s not in cache]
print(f"Already cached: {len(cache)}")
print(f"Need to fetch: {len(to_fetch)}", flush=True)

async def fetch_one(session, species, sem):
    async with sem:
        try:
            params = {"action": "query", "format": "json", "titles": species,
                      "redirects": 1, "prop": "pageprops"}
            async with session.get("https://en.wikipedia.org/w/api.php", params=params,
                                   timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                for pid, page in data.get("query", {}).get("pages", {}).items():
                    if pid != "-1":
                        title = page.get("title", "")
                        if title and title.lower() != species.lower():
                            return (species, title)
                return None
        except:
            return None

async def main():
    sem = asyncio.Semaphore(8)
    connector = aiohttp.TCPConnector(limit=10)
    
    async with aiohttp.ClientSession(connector=connector, headers=HEADERS) as session:
        tasks = [fetch_one(session, s, sem) for s in to_fetch]
        
        t0 = time.time()
        done = 0
        found = 0
        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result:
                cache[result[0]] = result[1]
                found += 1
            done += 1
            
            if done % 50 == 0:
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                print(f"  {done}/{len(to_fetch)} ({found} found, {rate:.0f}/s)", flush=True)
            
            # Save every 100 results or every 500 species
            if found % 100 == 0 and found > 0:
                with open(CACHE, "w") as f:
                    json.dump(cache, f, indent=2, sort_keys=True)
                print(f"  ** Saved ({found} common names)", flush=True)
    
    with open(CACHE, "w") as f:
        json.dump(cache, f, indent=2, sort_keys=True)
    
    elapsed = time.time() - t0
    print(f"\nDone! {len(cache)} names cached ({found} new) in {elapsed:.0f}s", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
