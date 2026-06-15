"""
Run the disease-generalisation experiment over all cached diseases.

Evaluates each disease config with the current generator code, prints a per-
disease accuracy table, aggregates issue classes, and writes results JSON.

Usage:
    python -m nlp_pipeline_v2.experiments.run_experiment [out.json]
"""

import json
import os
import sys
import glob
import collections

from .eval_config import evaluate

CACHE_DIR = os.environ.get("DISEASE_CACHE", "/tmp/disease_cache")


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else None
    files = sorted(glob.glob(os.path.join(CACHE_DIR, "*.json")))
    results = []
    issue_counts = collections.Counter()

    print(f"{'idx':>3}  {'acc%':>6} {'pheno':>5} {'rec':>5} {'xspec':>6} {'cspec':>6}  disease")
    print("-" * 78)
    for i, fp in enumerate(files):
        cache = json.load(open(fp))
        r = evaluate(cache)
        r["index"] = i
        results.append(r)
        for iss in r["issues"]:
            issue_counts[iss] += 1
        print(f"{i:>3}  {r['accuracy']:>6.2f} {r['n_phenotypes']:>5} "
              f"{r['recall']:>5.2f} {r['spec_cross']:>6.3f} {r['spec_control']:>6.3f}  {r['name']}")

    accs = [r["accuracy"] for r in results]
    with_pheno = [r["accuracy"] for r in results if r["n_phenotypes"] > 0]
    print("-" * 78)
    print(f"diseases: {len(results)}  |  mean accuracy (all): {sum(accs)/len(accs):.2f}%  "
          f"|  mean (with phenotypes): {sum(with_pheno)/len(with_pheno):.2f}%"
          if with_pheno else "no configs with phenotypes")
    print(f"diseases with 0 phenotypes: {sum(1 for r in results if r['n_phenotypes']==0)}")
    print("issue counts:", dict(issue_counts))

    if out_path:
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"saved -> {out_path}")
    return results


if __name__ == "__main__":
    main()
