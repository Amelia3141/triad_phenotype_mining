"""
Offline evaluation of a generated disease config.

Given the cached candidates + global HPO cache, this rebuilds a config using
the LIVE generator code (candidate selection + HPO->regex transform) and scores
its accuracy with an automated, disease-agnostic metric:

  recall      : each phenotype's regex matches its own HPO term name
  spec_cross  : a phenotype's regex does NOT match OTHER phenotypes' names
  spec_control: a phenotype's regex does NOT match generic non-phenotype text

  accuracy = mean(recall, spec_cross, spec_control) * 100

It also surfaces machine-detectable issue classes (no_phenotypes, regex_error,
low_recall, high_contamination, generic_pattern) used to drive fixes.
"""

import json
import os
import re

from ..disease_config_generator import (
    rank_candidates, build_condition_terms, build_symptom_config,
)

HPO_CACHE = os.environ.get("HPO_CACHE", "/tmp/hpo_cache")

# Generic clinical sentences containing NO specific phenotype. A well-formed
# phenotype pattern should match none of these.
CONTROL_SENTENCES = [
    "the patient was admitted to hospital",
    "laboratory investigations were performed",
    "he was discharged in stable condition",
    "written informed consent was obtained",
    "the study was approved by the ethics committee",
    "follow up was arranged after three months",
    "physical examination was carried out",
    "the results are summarised in the table",
    "she was referred to our department",
    "treatment was initiated without delay",
    "a multidisciplinary team was involved in care",
    "magnetic resonance imaging was requested",
    "the family declined further intervention",
    "vital signs were recorded on admission",
]


def load_hpo(xid):
    path = os.path.join(HPO_CACHE, xid.replace(":", "_") + ".json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        d = json.load(f)
    return d if d.get("categories") else None


def build_config_from_cache(disease_cache):
    """Rebuild a config for one disease from cached candidates (live code)."""
    name = disease_cache["name"]
    cands = disease_cache["candidates"]

    def has_hpo(c):
        xr = c.get("xrefs", {})
        return any(load_hpo(x) for x in xr.get("omim", []) + xr.get("orpha", []))

    ranked = rank_candidates(name, cands, has_hpo_fn=has_hpo)

    hpo_list = []
    chosen = ranked[0] if ranked else None
    for c in ranked:
        xr = c.get("xrefs", {})
        got = [load_hpo(x) for x in xr.get("omim", []) + xr.get("orpha", [])]
        got = [g for g in got if g]
        if got:
            chosen = c
            hpo_list = got
            break

    condition_terms = build_condition_terms([ranked[0]]) if ranked else {}
    symptom_patterns = build_symptom_config(hpo_list)
    return {
        "name": name,
        "chosen_label": chosen["label"] if chosen else None,
        "chosen_mondo": chosen["mondo_id"] if chosen else None,
        "condition_terms": condition_terms,
        "symptom_patterns": symptom_patterns,
    }


def score_patterns(sp):
    """Score a symptom_patterns dict with the disease-agnostic accuracy metric.

    Returns a dict with accuracy, recall, spec_cross, spec_control, issues.
    Identical scoring is applied to every code version so comparisons are fair.
    """
    issues = []
    if not sp:
        return {
            "n_phenotypes": 0, "accuracy": 0.0,
            "recall": 0.0, "spec_cross": 0.0, "spec_control": 0.0,
            "issues": ["no_phenotypes"],
            "low_recall_examples": [], "contaminating_examples": [],
            "generic_examples": [],
        }

    # Compile patterns; flag regex errors.
    compiled = {}
    for slug, spec in sp.items():
        pats = []
        for p in spec.get("patterns", []):
            try:
                pats.append(re.compile(p, re.IGNORECASE))
            except re.error:
                issues.append("regex_error")
        compiled[slug] = pats

    names = {slug: (spec.get("hpo_name") or slug).lower() for slug, spec in sp.items()}
    slugs = list(sp.keys())
    n = len(slugs)

    # Recall: pattern matches own name
    recall_hits = 0
    low_recall_slugs = []
    for slug in slugs:
        own = names[slug]
        if any(p.search(own) for p in compiled[slug]):
            recall_hits += 1
        else:
            low_recall_slugs.append(slug)
    recall = recall_hits / n

    # Cross-contamination: pattern matches another phenotype's name.
    # Exclude pairs whose names are in a parent/child (token-containment)
    # relationship, e.g. "Tachycardia" vs "Supraventricular tachycardia":
    # a parent term legitimately matching its more-specific child is correct
    # ontology behaviour, not a false positive.
    def _content_tokens(name):
        return {w for w in re.split(r"[^a-z0-9]+", name) if len(w) > 2}

    toks = {slug: _content_tokens(names[slug]) for slug in slugs}
    cross_total = 0
    cross_bad = 0
    contaminating = set()
    for slug in slugs:
        pats = compiled[slug]
        for other in slugs:
            if other == slug:
                continue
            tp, to = toks[slug], toks[other]
            if tp and to and (tp <= to or to <= tp):
                continue  # hierarchical overlap, not a specificity test
            cross_total += 1
            if any(p.search(names[other]) for p in pats):
                cross_bad += 1
                contaminating.add(slug)
    spec_cross = 1 - (cross_bad / cross_total) if cross_total else 1.0

    # Control specificity: pattern matches generic non-phenotype text
    ctrl_total = n * len(CONTROL_SENTENCES)
    ctrl_bad = 0
    generic_slugs = set()
    for slug in slugs:
        pats = compiled[slug]
        for sent in CONTROL_SENTENCES:
            if any(p.search(sent) for p in pats):
                ctrl_bad += 1
                generic_slugs.add(slug)
    spec_control = 1 - (ctrl_bad / ctrl_total) if ctrl_total else 1.0

    accuracy = 100 * (recall + spec_cross + spec_control) / 3

    if recall < 0.85:
        issues.append("low_recall")
    if spec_cross < 0.98:
        issues.append("high_contamination")
    if generic_slugs:
        issues.append("generic_pattern")

    return {
        "n_phenotypes": n, "accuracy": round(accuracy, 2),
        "recall": round(recall, 4), "spec_cross": round(spec_cross, 5),
        "spec_control": round(spec_control, 5),
        "issues": sorted(set(issues)),
        "low_recall_examples": low_recall_slugs[:8],
        "contaminating_examples": sorted(contaminating)[:8],
        "generic_examples": sorted(generic_slugs)[:8],
    }


def evaluate(disease_cache):
    """Build a config for one disease (live code) and score it."""
    cfg = build_config_from_cache(disease_cache)
    out = score_patterns(cfg["symptom_patterns"])
    out["name"] = cfg["name"]
    out["chosen_label"] = cfg["chosen_label"]
    return out


if __name__ == "__main__":
    import sys
    cache = json.load(open(sys.argv[1]))
    print(json.dumps(evaluate(cache), indent=2))
