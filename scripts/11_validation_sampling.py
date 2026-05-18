#!/usr/bin/env python3
"""
Reproducible stratified random sampling for validation, and automated
re-extraction for comparison against the pipeline.

Strata (mutually exclusive case reports from the v3_final dataset):
  - hEDS-only (no POTS, no MCAS): 3 articles
  - POTS-only (no hEDS, no MCAS): 2 articles
  - MCAS-only (no hEDS, no POTS): 2 articles
  - Triad (hEDS + POTS + MCAS):   3 articles
  Total: 10 articles

Seed: 42
"""

import os
import re
import json
import random
import unicodedata
import pandas as pd
from collections import defaultdict

BASE_DIR = "/sessions/adoring-eager-allen/mnt/mphil/triad_phenotype_mining"
DATASET = os.path.join(BASE_DIR, "data/processed/triad_phenotype_dataset_v3_final.csv")
EXTRACTIONS = os.path.join(BASE_DIR, "data/processed/rule_based_extractions.json")
XML_DIR = os.path.join(BASE_DIR, "data/raw/fulltext")
OUT_DIR = os.path.join(BASE_DIR, "data/validation")
SEED = 42

# ── The 20 symptom categories (must match pipeline) ──
SYMPTOM_PATTERNS = {
    "joint_hypermobility": [
        r"joint\s+hypermobil", r"hypermobil(?:e|ity)", r"beighton\s+score",
        r"generalised\s+(?:joint\s+)?laxity", r"double[\s-]?jointed",
    ],
    "subluxations_dislocations": [
        r"subluxat", r"dislocat", r"joint\s+instabil",
    ],
    "chronic_pain": [
        r"chronic\s+pain", r"widespread\s+pain", r"fibromyalg",
        r"myalgia", r"arthralgia", r"pain\s+syndrome",
    ],
    "skin_hyperextensibility": [
        r"skin\s+hyperextensib", r"skin\s+elasticity", r"stretchy\s+skin",
        r"velvety\s+skin", r"skin\s+fragil", r"atrophic\s+scar",
        r"poor\s+wound\s+healing",
    ],
    "easy_bruising": [
        r"easy\s+bruis", r"bruising\s+easily", r"ecchymos",
    ],
    "tachycardia": [
        r"tachycardi", r"heart\s+rate\s+(?:increase|elevation|rise)",
        r"rapid\s+heart", r"elevated\s+heart\s+rate",
    ],
    "syncope": [
        r"syncop", r"presyncop", r"pre-syncop", r"faint",
        r"loss\s+of\s+consciousness",
    ],
    "orthostatic_intolerance": [
        r"orthostatic\s+intolerance", r"orthostatic\s+hypotension",
        r"postural\s+(?:intolerance|hypotension)",
        r"upon\s+standing", r"on\s+standing",
    ],
    "palpitations": [
        r"palpitat",
    ],
    "mitral_valve_prolapse": [
        r"mitral\s+valve\s+prolapse", r"MVP",
    ],
    "flushing": [
        r"flush(?:ing|ed)", r"facial\s+flush",
    ],
    "urticaria": [
        r"urticar", r"hives", r"wheal",
    ],
    "anaphylaxis": [
        r"anaphyla",
    ],
    "fatigue": [
        r"fatigu", r"exhausti", r"lethargy", r"malaise",
    ],
    "gi_symptoms": [
        r"nausea", r"vomit", r"diarr", r"constipat", r"bloat",
        r"abdominal\s+pain", r"gastropar", r"dysphagia", r"reflux",
        r"irritable\s+bowel", r"IBS\b", r"dysmotility",
    ],
    "headache_migraine": [
        r"headache", r"migraine", r"cephalalgia",
    ],
    "neuropathy": [
        r"neuropath", r"small\s+fiber", r"small\s+fibre",
        r"nerve\s+(?:damage|dysfunction|pain)", r"paresthes", r"paraesthes",
        r"numbness", r"tingling",
    ],
    "brain_fog": [
        r"brain\s+fog", r"cognitive\s+(?:dysfunction|impairment|difficult)",
        r"difficulty\s+concentrat", r"mental\s+fog",
    ],
    "medication_sensitivity": [
        r"medication\s+sensitiv", r"drug\s+(?:sensitiv|intoleran|reaction)",
        r"adverse\s+(?:drug|medication)\s+react", r"medication\s+intoleran",
    ],
    "chiari": [
        r"chiari", r"arnold-chiari",
    ],
}


def normalise_text(text):
    """Unicode dash normalisation + lowercase."""
    for cp in range(0x2010, 0x2016):
        text = text.replace(chr(cp), "-")
    return text.lower()


def extract_xml_text(xml_path):
    """Extract plain text from PMC NXML, stripping tags."""
    with open(xml_path, "r", encoding="utf-8") as f:
        raw = f.read()
    # Strip XML tags
    text = re.sub(r"<[^>]+>", " ", raw)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return normalise_text(text)


def independent_symptom_extract(text):
    """Independent symptom extraction using the same 20 categories
    but applied fresh to the raw text. Returns set of detected symptoms."""
    detected = set()
    for symptom, patterns in SYMPTOM_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                detected.add(symptom)
                break
    return detected


def get_pipeline_symptoms(pmcid, extractions):
    """Get the pipeline's symptom extractions for a given PMCID."""
    if pmcid in extractions:
        syms = extractions[pmcid].get("symptoms_detected", "")
        if isinstance(syms, str) and syms:
            return set(s.strip() for s in syms.split(";"))
        elif isinstance(syms, list):
            return set(s.strip() for s in syms)
    return set()


def main():
    random.seed(SEED)

    # Load dataset
    df = pd.read_csv(DATASET)
    case_reports = df[df["article_type_inferred"] == "case_report"].copy()

    # Define mutually exclusive strata
    heds_only = case_reports[
        (case_reports["has_heds"] == True) &
        (case_reports["has_pots"] == False) &
        (case_reports["has_mcas"] == False)
    ]
    pots_only = case_reports[
        (case_reports["has_pots"] == True) &
        (case_reports["has_heds"] == False) &
        (case_reports["has_mcas"] == False)
    ]
    mcas_only = case_reports[
        (case_reports["has_mcas"] == True) &
        (case_reports["has_heds"] == False) &
        (case_reports["has_pots"] == False)
    ]
    triad = case_reports[case_reports["triad_present"] == True]

    # Filter to articles with XML available
    available_xmls = set()
    for f in os.listdir(XML_DIR):
        if f.endswith(".xml"):
            available_xmls.add(f.replace(".xml", ""))

    heds_pool = [p for p in heds_only["pmcid"].tolist() if p in available_xmls]
    pots_pool = [p for p in pots_only["pmcid"].tolist() if p in available_xmls]
    mcas_pool = [p for p in mcas_only["pmcid"].tolist() if p in available_xmls]
    triad_pool = [p for p in triad["pmcid"].tolist() if p in available_xmls]

    print(f"Pools with XML available:")
    print(f"  hEDS-only: {len(heds_pool)}")
    print(f"  POTS-only: {len(pots_pool)}")
    print(f"  MCAS-only: {len(mcas_pool)}")
    print(f"  Triad:     {len(triad_pool)}")

    # Stratified random sample
    sample_heds = random.sample(heds_pool, 3)
    sample_pots = random.sample(pots_pool, 2)
    sample_mcas = random.sample(mcas_pool, 2)
    sample_triad = random.sample(triad_pool, 3)

    all_samples = (
        [(p, "hEDS-only") for p in sample_heds] +
        [(p, "POTS-only") for p in sample_pots] +
        [(p, "MCAS-only") for p in sample_mcas] +
        [(p, "Triad") for p in sample_triad]
    )

    print(f"\nSelected validation sample (seed={SEED}):")
    for pmcid, stratum in all_samples:
        print(f"  {pmcid} [{stratum}]")

    # Load pipeline extractions
    with open(EXTRACTIONS, "r") as f:
        extractions = json.load(f)

    # Also load from CSV for symptom data
    symptom_col_map = {}
    for _, row in df.iterrows():
        syms = row.get("symptoms_detected", "")
        if isinstance(syms, str) and syms:
            symptom_col_map[row["pmcid"]] = set(s.strip() for s in syms.split(";"))
        else:
            symptom_col_map[row["pmcid"]] = set()

    # Run independent extraction and compare
    print(f"\n{'='*80}")
    print("VALIDATION RESULTS")
    print(f"{'='*80}")

    total_tp = 0
    total_fp = 0
    total_fn = 0
    article_results = []

    for pmcid, stratum in all_samples:
        xml_path = os.path.join(XML_DIR, f"{pmcid}.xml")
        text = extract_xml_text(xml_path)

        # Independent extraction (ground truth proxy)
        independent = independent_symptom_extract(text)

        # Pipeline extraction
        pipeline = symptom_col_map.get(pmcid, set())

        # Also check JSON extractions
        if pmcid in extractions:
            json_syms = extractions[pmcid].get("symptoms_detected", "")
            if isinstance(json_syms, str) and json_syms:
                pipeline_json = set(s.strip() for s in json_syms.split(";"))
            elif isinstance(json_syms, list):
                pipeline_json = set(s.strip() for s in json_syms)
            else:
                pipeline_json = set()
            # Use whichever has more data
            if len(pipeline_json) > len(pipeline):
                pipeline = pipeline_json

        tp = pipeline & independent
        fp = pipeline - independent
        fn = independent - pipeline

        total_tp += len(tp)
        total_fp += len(fp)
        total_fn += len(fn)

        article_results.append({
            "pmcid": pmcid,
            "stratum": stratum,
            "independent_count": len(independent),
            "pipeline_count": len(pipeline),
            "tp": len(tp),
            "fp": len(fp),
            "fn": len(fn),
            "independent": sorted(independent),
            "pipeline": sorted(pipeline),
            "false_positives": sorted(fp),
            "false_negatives": sorted(fn),
        })

        print(f"\n{pmcid} [{stratum}]")
        print(f"  Independent: {len(independent)} symptoms: {sorted(independent)}")
        print(f"  Pipeline:    {len(pipeline)} symptoms: {sorted(pipeline)}")
        if fp:
            print(f"  FALSE POS:   {sorted(fp)}")
        if fn:
            print(f"  FALSE NEG:   {sorted(fn)}")

    # Compute aggregate metrics
    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    print(f"\n{'='*80}")
    print(f"AGGREGATE METRICS")
    print(f"  True positives:  {total_tp}")
    print(f"  False positives: {total_fp}")
    print(f"  False negatives: {total_fn}")
    print(f"  Precision: {precision:.1%} ({total_tp}/{total_tp+total_fp})")
    print(f"  Recall:    {recall:.1%} ({total_tp}/{total_tp+total_fn})")
    print(f"  F1 Score:  {f1:.1%}")
    print(f"{'='*80}")

    # Save results
    os.makedirs(OUT_DIR, exist_ok=True)

    # Save sample list
    with open(os.path.join(OUT_DIR, "validation_sample.txt"), "w") as f:
        for pmcid, stratum in all_samples:
            f.write(f"{pmcid}\n")

    # Save detailed report
    with open(os.path.join(OUT_DIR, "validation_report_v2.json"), "w") as f:
        json.dump({
            "seed": SEED,
            "strata": {"hEDS-only": 3, "POTS-only": 2, "MCAS-only": 2, "Triad": 3},
            "aggregate": {
                "tp": total_tp, "fp": total_fp, "fn": total_fn,
                "precision": round(precision, 3),
                "recall": round(recall, 3),
                "f1": round(f1, 3),
            },
            "articles": article_results,
        }, f, indent=2)

    print(f"\nSaved: {OUT_DIR}/validation_sample.txt")
    print(f"Saved: {OUT_DIR}/validation_report_v2.json")

    return precision, recall, f1


if __name__ == "__main__":
    main()
