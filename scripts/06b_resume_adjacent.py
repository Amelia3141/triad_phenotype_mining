#!/usr/bin/env python3
"""Resume adjacent extraction from partial results."""

import json
import os
import sys

sys.path.insert(0, "/sessions/adoring-eager-allen/mnt/mphil/triad_phenotype_mining/scripts")
os.chdir("/sessions/adoring-eager-allen/mnt/mphil/triad_phenotype_mining")

from scripts_06_adjacent_extract_funcs import *

BASE_DIR = "/sessions/adoring-eager-allen/mnt/mphil/triad_phenotype_mining"
RAW_DIR = os.path.join(BASE_DIR, "data/raw")
PROCESSED_DIR = os.path.join(BASE_DIR, "data/processed")

import csv
import time
import datetime

# Load partial results
with open(os.path.join(PROCESSED_DIR, "adjacent_extractions_partial.json")) as f:
    existing = json.load(f)
done_pmcids = {e["pmcid"] for e in existing}
print(f"Loaded {len(existing)} existing extractions")

# Load all new PMCIDs and metadata
with open(os.path.join(RAW_DIR, "adjacent_new_pmcids.json")) as f:
    new_pmcids = json.load(f)

# Load combined metadata
metadata = {}
source_queries = {}
with open(os.path.join(RAW_DIR, "adjacent_combined_metadata.csv"), "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        pmcid = row.get("pmcid", "")
        metadata[pmcid] = row
        source_queries[pmcid] = row.get("source_query", "")

remaining = [p for p in new_pmcids if p not in done_pmcids]
print(f"Remaining: {len(remaining)}")

extractions = list(existing)
success = 0
fail = 0

for i, pmcid in enumerate(remaining):
    xml_path = os.path.join(RAW_DIR, "fulltext", f"{pmcid}.xml")

    if os.path.exists(xml_path):
        with open(xml_path, "r", encoding="utf-8") as f:
            xml_data = f.read()
    else:
        xml_data = fetch_pmc_fulltext(pmcid)
        time.sleep(0.4)
        if xml_data:
            with open(xml_path, "w", encoding="utf-8") as f:
                f.write(xml_data)
            log_access(pmcid, "success", f"Adjacent resume. Source: {source_queries.get(pmcid, '')}")
        else:
            log_access(pmcid, "failed", f"Adjacent resume. Source: {source_queries.get(pmcid, '')}")
            fail += 1
            continue

    sections = extract_text_from_nxml(xml_data)
    if not sections:
        fail += 1
        continue

    extraction = rule_based_extract(sections, pmcid)
    row = metadata.get(pmcid, {})
    extraction["title"] = row.get("title", "")
    extraction["journal"] = row.get("journal", "")
    extraction["pubdate"] = row.get("pubdate", "")
    extraction["doi"] = row.get("doi", "")
    extraction["source_query"] = source_queries.get(pmcid, "")
    extractions.append(extraction)
    success += 1

    if (i + 1) % 50 == 0:
        print(f"  Progress: {i+1}/{len(remaining)} ({success} ok, {fail} fail)")

# Save final
out_file = os.path.join(PROCESSED_DIR, "adjacent_extractions.json")
with open(out_file, "w", encoding="utf-8") as f:
    json.dump(extractions, f, indent=2, ensure_ascii=False)

print(f"\nDone. Total: {len(extractions)} extractions ({success} new, {fail} failed)")
print(f"Saved to {out_file}")

# Stats
eds_count = sum(1 for e in extractions if e.get("eds_mentioned"))
pots_count = sum(1 for e in extractions if e.get("pots_mentioned"))
mcas_count = sum(1 for e in extractions if e.get("mcas_mentioned"))
dysaut_count = sum(1 for e in extractions if e.get("dysautonomia_mentioned"))
oi_count = sum(1 for e in extractions if e.get("orthostatic_intolerance_mentioned"))
print(f"\nCondition mentions across all {len(extractions)} adjacent articles:")
print(f"  EDS: {eds_count}")
print(f"  POTS: {pots_count}")
print(f"  MCAS: {mcas_count}")
print(f"  Dysautonomia: {dysaut_count}")
print(f"  Orthostatic intolerance: {oi_count}")
print(f"  JHS: {sum(1 for e in extractions if e.get('jhs_mentioned'))}")
print(f"  HSD: {sum(1 for e in extractions if e.get('hsd_mentioned'))}")
print(f"  Vasovagal: {sum(1 for e in extractions if e.get('vasovagal_mentioned'))}")
print(f"  Histamine intolerance: {sum(1 for e in extractions if e.get('histamine_intolerance_mentioned'))}")
print(f"  HAT: {sum(1 for e in extractions if e.get('hat_mentioned'))}")
print(f"  Mastocytosis: {sum(1 for e in extractions if e.get('mastocytosis_mentioned'))}")
