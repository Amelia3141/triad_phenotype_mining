"""
Reconstruct the accuracy trajectory across the generalisable fixes applied
during the 50-disease experiment, and write results for plotting.

Three faithfully-reconstructed code milestones, scored with the identical
disease-agnostic metric (eval_config.score_patterns):

  V0  baseline        : top-1 OLS selection + original HPO->regex transform
  V1  +robust select  : ranked candidate selection (HPO-resolvable exact match)
                        + original transform
  V2  +pattern quality: ranked selection + final transform (no shared bare
                        stems, word-remainder \\w*, hyphen/slash tokenisation,
                        wider stop-gap filler)

V0/V1 use the ORIGINAL generator (imported from a snapshot); V2 uses the
current generator. Run:

    python -m nlp_pipeline_v2.experiments.compare_versions [out.json]
"""

import json
import os
import sys
import glob

# Original (pre-fix) generator snapshot.
ORIG_PKG = os.environ.get("ORIG_PKG", "/tmp/orig_pkg")
if ORIG_PKG not in sys.path:
    sys.path.insert(0, ORIG_PKG)

from .eval_config import load_hpo, score_patterns
from ..disease_config_generator import (
    rank_candidates, build_symptom_config as final_build_symptom_config,
)
import nlp_pipeline_v2_orig.disease_config_generator as orig  # noqa: E402

CACHE_DIR = os.environ.get("DISEASE_CACHE", "/tmp/disease_cache")


def _hpo_for_candidate(c):
    xr = c.get("xrefs", {})
    return [g for g in (load_hpo(x) for x in xr.get("omim", []) + xr.get("orpha", [])) if g]


def _select_hpo(cache, mode):
    cands = cache.get("candidates", [])
    if not cands:
        return []
    if mode == "top1":
        # Original behaviour: take the single top OLS hit, no fallback.
        return _hpo_for_candidate(cands[0])
    # Ranked behaviour: best label + HPO resolvability, with alternate fallback.
    ranked = rank_candidates(
        cache["name"], cands, has_hpo_fn=lambda c: bool(_hpo_for_candidate(c))
    )
    for c in ranked:
        h = _hpo_for_candidate(c)
        if h:
            return h
    return []


def patterns_for_version(cache, version):
    if version == "V0":
        return orig.build_symptom_config(_select_hpo(cache, "top1"))
    if version == "V1":
        return orig.build_symptom_config(_select_hpo(cache, "ranked"))
    if version == "V2":
        return final_build_symptom_config(_select_hpo(cache, "ranked"))
    raise ValueError(version)


VERSIONS = ["V0", "V1", "V2"]


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else None
    files = sorted(glob.glob(os.path.join(CACHE_DIR, "*.json")))
    rows = []
    for i, fp in enumerate(files):
        cache = json.load(open(fp))
        row = {"index": i, "name": cache["name"]}
        for v in VERSIONS:
            sp = patterns_for_version(cache, v)
            sc = score_patterns(sp)
            row[v] = sc["accuracy"]
            row[f"{v}_n"] = sc["n_phenotypes"]
        rows.append(row)

    print(f"{'idx':>3}  {'V0':>6} {'V1':>6} {'V2':>6}  disease")
    print("-" * 60)
    for r in rows:
        print(f"{r['index']:>3}  {r['V0']:>6.1f} {r['V1']:>6.1f} {r['V2']:>6.1f}  {r['name']}")
    print("-" * 60)
    for v in VERSIONS:
        m = sum(r[v] for r in rows) / len(rows)
        mp = [r[v] for r in rows if r[f"{v}_n"] > 0]
        zeros = sum(1 for r in rows if r[f"{v}_n"] == 0)
        print(f"{v}: mean(all)={m:.2f}%  mean(with-pheno)={sum(mp)/len(mp):.2f}%  "
              f"zero-phenotype diseases={zeros}")

    if out_path:
        with open(out_path, "w") as f:
            json.dump(rows, f, indent=2)
        print(f"saved -> {out_path}")
    return rows


if __name__ == "__main__":
    main()
