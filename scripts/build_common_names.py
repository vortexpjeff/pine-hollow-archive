#!/usr/bin/env python3
"""
Build a scientific→common name mapping for all 14,795 Perch 2.0 species.
Uses the iNaturalist API to fetch common names, caches to a JSON file.

Run once as background task: python3 build_common_names.py
The review app reads from the output file for instant lookups.
"""
import os, sys, csv, json, time, requests
from pathlib import Path

PERCH_LABELS = Path.home() / ".cache/kagglehub/models/google/bird-vocalization-classifier/tensorFlow2/perch_v2_cpu/1/assets/labels.csv"
OUTPUT = Path("/mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive/common_names.json")

# iNaturalist API — batch lookup by scientific name
INAT_URL = "https://api.inaturalist.org/v1/taxa"

def load_existing():
    if OUTPUT.exists():
        with open(OUTPUT) as f:
            return json.load(f)
    return {}

def fetch_common_names(species_list, existing):
    """Batch-fetch common names from iNaturalist API."""
    results = dict(existing)
    batch_size = 50  # iNat allows up to 50 per request
    
    # Skip already-looked-up species
    to_lookup = [s for s in species_list if s not in results]
    print(f"Total species: {len(species_list)}")
    print(f"Already cached: {len(results)}")
    print(f"To look up: {len(to_lookup)}")
    
    for i in range(0, len(to_lookup), batch_size):
        batch = to_lookup[i:i+batch_size]
        params = {"q": ",".join(batch[:30]), "rank": "species", "per_page": 30}
        # iNat API limits q to ~30 names, so we do smaller batches
        
        try:
            r = requests.get(INAT_URL, params=params, timeout=15)
            if r.status_code != 200:
                print(f"  API error at batch {i}: {r.status_code}")
                continue
            
            data = r.json()
            for taxon in data.get("results", []):
                sci = taxon.get("name", "")
                # Get preferred common name
                pren = taxon.get("preferred_common_name")
                if sci and pren:
                    results[sci] = pren
            
            # Save progress every 10 batches
            if i % 500 == 0 and i > 0:
                with open(OUTPUT, "w") as f:
                    json.dump(results, f, indent=2)
                print(f"  Progress: {i}/{len(to_lookup)} — {len(results)} cached")
        
        except Exception as e:
            print(f"  Error at batch {i}: {e}")
        
        time.sleep(0.5)  # Rate limiting
    
    return results

def main():
    # Load Perch species
    with open(PERCH_LABELS) as f:
        reader = csv.reader(f)
        species_list = [row[0] for row in reader][1:]  # skip header
    
    print(f"Loaded {len(species_list)} species from Perch labels")
    
    existing = load_existing()
    results = fetch_common_names(species_list, existing)
    
    # Final save
    with open(OUTPUT, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nDone! {len(results)} common names cached")
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
