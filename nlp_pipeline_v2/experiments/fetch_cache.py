"""
Fetch and cache raw MONDO/HPO data for each experiment disease.

Separates the (slow, networked) ontology resolution from the (fast, offline)
selection + HPO-name->regex transform that is the code under test. The cache
stores, per disease, ALL candidate MONDO matches with their cross-references,
plus a global HPO-annotation cache keyed by disease id. This lets the
experiment re-run candidate selection and pattern generation entirely offline
each time the generator code is fixed.

Usage:
    python -m nlp_pipeline_v2.experiments.fetch_cache [START] [COUNT]
"""

import json
import os
import re
import sys

from ..disease_config_generator import (
    search_disease, get_disease_xrefs, get_hpo_phenotypes,
)

HERE = os.path.dirname(__file__)
CACHE_DIR = os.environ.get("DISEASE_CACHE", "/tmp/disease_cache")
HPO_CACHE = os.environ.get("HPO_CACHE", "/tmp/hpo_cache")
MAX_CANDIDATES = 4


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def load_diseases():
    path = os.path.join(HERE, "diseases.txt")
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                out.append(line)
    return out


def get_hpo_cached(disease_id):
    """Fetch HPO annotations for an id, caching globally on disk."""
    os.makedirs(HPO_CACHE, exist_ok=True)
    safe = disease_id.replace(":", "_")
    path = os.path.join(HPO_CACHE, f"{safe}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    data = get_hpo_phenotypes(disease_id, log=None)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


def fetch_one(name):
    """Resolve a disease to all candidate MONDO matches (with xrefs) and warm
    the global HPO cache for every candidate cross-reference."""
    candidates = search_disease(name, log=None)[:MAX_CANDIDATES]
    for cand in candidates:
        xrefs = get_disease_xrefs(cand["mondo_id"], log=None)
        cand["xrefs"] = xrefs
        cand["synonyms"] = cand.get("synonyms", []) + xrefs.get("synonyms", [])
        for xid in xrefs.get("omim", []) + xrefs.get("orpha", []):
            get_hpo_cached(xid)  # warm cache
    return {"name": name, "candidates": candidates}


def main():
    os.makedirs(CACHE_DIR, exist_ok=True)
    diseases = load_diseases()
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    count = int(sys.argv[2]) if len(sys.argv) > 2 else len(diseases)

    from concurrent.futures import ThreadPoolExecutor

    def work(i):
        name = diseases[i]
        path = os.path.join(CACHE_DIR, f"{i:02d}_{_slug(name)}.json")
        if os.path.exists(path):
            return f"[{i:02d}] cached: {name}"
        try:
            data = fetch_one(name)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            return f"[{i:02d}] fetched: {name}  (candidates={len(data['candidates'])})"
        except Exception as e:
            return f"[{i:02d}] ERROR {name}: {e!r}"

    idxs = list(range(start, min(start + count, len(diseases))))
    with ThreadPoolExecutor(max_workers=6) as ex:
        for msg in ex.map(work, idxs):
            print(msg, flush=True)


if __name__ == "__main__":
    main()
