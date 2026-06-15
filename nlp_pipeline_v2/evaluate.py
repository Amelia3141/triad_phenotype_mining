"""
Evaluation framework for the NLP extraction pipeline.

Creates a gold-standard annotation set from stratified sampling,
runs both regex and NLP extractors, and computes per-field metrics.

The gold standard is generated automatically by the NLP pipeline
with evidence sentences, formatted for human review and correction.
"""

import json
import os
import re
import csv
import random
import sys
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from nlp_pipeline_v2.pipeline import NLPExtractionPipeline


def create_annotation_set(
    xml_dir: str,
    dataset_csv: str,
    output_dir: str,
    n_per_stratum: int = 5,
    seed: int = 42,
) -> List[dict]:
    """Create stratified annotation set with NLP pre-annotation.

    Strata:
    - EDS-only (no POTS, no MCAS)
    - POTS-only
    - MCAS-only
    - EDS+POTS
    - EDS+MCAS
    - POTS+MCAS
    - Triad (all three)

    Each article gets NLP extraction + evidence sentences formatted
    for human review.
    """
    import pandas as pd

    random.seed(seed)

    # Load dataset to determine strata
    df = pd.read_csv(dataset_csv)

    # Map PMCIDs to available XMLs
    available = set()
    for f in os.listdir(xml_dir):
        if f.endswith(".xml"):
            available.add(f.replace(".xml", ""))

    df = df[df["pmcid"].isin(available)]

    # Define strata based on condition columns
    # The v3_final dataset has has_eds, has_pots, has_mcas columns
    strata = {}

    if "has_eds" in df.columns:
        eds_col, pots_col, mcas_col = "has_eds", "has_pots", "has_mcas"
    elif "eds_mentioned" in df.columns:
        eds_col, pots_col, mcas_col = "eds_mentioned", "pots_mentioned", "mcas_mentioned"
    else:
        # Fall back to random sampling
        pool = list(df["pmcid"])
        random.shuffle(pool)
        selected = pool[:n_per_stratum * 5]
        return _annotate_articles(selected, xml_dir, output_dir)

    strata = {
        "EDS-only": df[(df[eds_col] == True) & (df[pots_col] == False) & (df[mcas_col] == False)]["pmcid"].tolist(),
        "POTS-only": df[(df[pots_col] == True) & (df[eds_col] == False) & (df[mcas_col] == False)]["pmcid"].tolist(),
        "MCAS-only": df[(df[mcas_col] == True) & (df[eds_col] == False) & (df[pots_col] == False)]["pmcid"].tolist(),
        "EDS+POTS": df[(df[eds_col] == True) & (df[pots_col] == True) & (df[mcas_col] == False)]["pmcid"].tolist(),
        "Triad": df[(df[eds_col] == True) & (df[pots_col] == True) & (df[mcas_col] == True)]["pmcid"].tolist(),
    }

    # Filter to available XMLs and sample
    selected = []
    for stratum_name, pool in strata.items():
        pool = [p for p in pool if p in available]
        if not pool:
            print(f"  Warning: no articles in stratum {stratum_name}")
            continue
        n = min(n_per_stratum, len(pool))
        sampled = random.sample(pool, n)
        for pmcid in sampled:
            selected.append((pmcid, stratum_name))
        print(f"  {stratum_name}: {n} sampled from {len(pool)}")

    return _annotate_articles(selected, xml_dir, output_dir)


def _annotate_articles(selected, xml_dir, output_dir):
    """Run NLP extraction and format for human annotation."""
    os.makedirs(output_dir, exist_ok=True)

    pipeline = NLPExtractionPipeline()
    annotations = []

    for item in selected:
        if isinstance(item, tuple):
            pmcid, stratum = item
        else:
            pmcid, stratum = item, "random"

        xml_path = os.path.join(xml_dir, f"{pmcid}.xml")
        if not os.path.exists(xml_path):
            continue

        # Run NLP extraction
        extraction = pipeline.extract_from_xml(xml_path)

        # Format for human review
        annotation = {
            "pmcid": pmcid,
            "stratum": stratum,
            "nlp_extraction": extraction,
            "human_review": {
                "age_at_presentation": {
                    "nlp_value": extraction.get("age_at_presentation"),
                    "correct": None,  # Human fills: True/False
                    "corrected_value": None,  # If incorrect, human provides correct value
                },
                "sex": {
                    "nlp_value": extraction.get("sex"),
                    "correct": None,
                    "corrected_value": None,
                },
                "age_at_onset": {
                    "nlp_value": extraction.get("age_at_onset"),
                    "evidence": extraction.get("onset_evidence", []),
                    "correct": None,
                    "corrected_value": None,
                    "notes": "",
                },
                "diagnostic_delay_years": {
                    "nlp_value": extraction.get("diagnostic_delay_years"),
                    "evidence": extraction.get("delay_evidence", []),
                    "correct": None,
                    "corrected_value": None,
                },
                "drugs": {
                    "nlp_drugs": [d["drug"] for d in extraction.get("drugs_affirmed", [])],
                    "missed_drugs": [],  # Human adds any drugs NLP missed
                    "false_positives": [],  # Human marks any incorrectly extracted drugs
                },
                "symptoms_affirmed": {
                    "nlp_symptoms": [s["symptom"] for s in extraction.get("symptoms_affirmed", [])],
                    "missed": [],
                    "false_positives": [],
                },
                "symptoms_negated": {
                    "nlp_symptoms": [s["symptom"] for s in extraction.get("symptoms_negated", [])],
                    "missed": [],
                    "false_positives": [],
                },
                "misdiagnoses": {
                    "nlp_misdiag": [m["condition"] for m in extraction.get("misdiagnoses", [])],
                    "missed": [],
                    "false_positives": [],
                },
                "overall_quality": None,  # 1-5 rating
                "notes": "",
            },
        }
        annotations.append(annotation)

    # Save as JSON for programmatic use
    json_path = os.path.join(output_dir, "gold_standard_annotations.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(annotations, f, indent=2, ensure_ascii=False)

    # Save as human-readable TSV for quick review
    tsv_path = os.path.join(output_dir, "gold_standard_review.tsv")
    with open(tsv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow([
            "pmcid", "stratum",
            "age_pres", "sex", "age_onset", "onset_evidence",
            "delay_years", "drugs", "symptoms_affirmed",
            "symptoms_negated", "misdiagnoses",
            "correct_age?", "correct_sex?", "correct_onset?",
            "correct_delay?", "missed_drugs", "FP_drugs",
            "missed_symptoms", "FP_symptoms", "notes"
        ])
        for ann in annotations:
            ext = ann["nlp_extraction"]
            writer.writerow([
                ann["pmcid"], ann["stratum"],
                ext.get("age_at_presentation", ""),
                ext.get("sex", ""),
                ext.get("age_at_onset", ""),
                "; ".join(e.get("sentence", "")[:80] for e in ext.get("onset_evidence", [])),
                ext.get("diagnostic_delay_years", ""),
                "; ".join(d["drug"] for d in ext.get("drugs_affirmed", [])),
                "; ".join(s["symptom"] for s in ext.get("symptoms_affirmed", [])),
                "; ".join(s["symptom"] for s in ext.get("symptoms_negated", [])),
                "; ".join(m["condition"] for m in ext.get("misdiagnoses", [])),
                "", "", "", "", "", "", "", "", "",  # Human fills these
            ])

    print(f"\nAnnotation set saved:")
    print(f"  JSON: {json_path}")
    print(f"  TSV:  {tsv_path}")
    print(f"  Articles: {len(annotations)}")

    return annotations


def compute_metrics(annotations_path: str) -> dict:
    """Compute precision, recall, F1 from reviewed annotations.

    Expects the gold_standard_annotations.json with human_review filled in.
    """
    with open(annotations_path) as f:
        annotations = json.load(f)

    metrics = {}

    # Per-field accuracy for scalar fields
    for field in ["age_at_presentation", "sex", "age_at_onset", "diagnostic_delay_years"]:
        reviewed = [a for a in annotations if a["human_review"][field]["correct"] is not None]
        if not reviewed:
            continue

        correct = sum(1 for a in reviewed if a["human_review"][field]["correct"])
        total = len(reviewed)
        metrics[field] = {
            "accuracy": correct / total if total > 0 else 0,
            "correct": correct,
            "total": total,
        }

    # Per-field P/R/F1 for list fields.
    # Map each field to the key under which the NLP items are stored in the
    # human_review block (these are NOT a simple prefix of the field name).
    nlp_item_keys = {
        "drugs": "nlp_drugs",
        "symptoms_affirmed": "nlp_symptoms",
        "symptoms_negated": "nlp_symptoms",
        "misdiagnoses": "nlp_misdiag",
    }
    for field in ["drugs", "symptoms_affirmed", "symptoms_negated", "misdiagnoses"]:
        reviewed = [a for a in annotations if a["human_review"].get(field)]
        if not reviewed:
            continue

        total_tp = 0
        total_fp = 0
        total_fn = 0

        for a in reviewed:
            review = a["human_review"][field]
            nlp_items = set(review.get(nlp_item_keys[field], []))
            fps = set(review.get("false_positives", []))
            missed = set(review.get("missed", []))

            tp = len(nlp_items - fps)
            fp = len(fps)
            fn = len(missed)

            total_tp += tp
            total_fp += fp
            total_fn += fn

        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
        recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        metrics[field] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "tp": total_tp,
            "fp": total_fp,
            "fn": total_fn,
        }

    return metrics


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--create", action="store_true", help="Create annotation set")
    parser.add_argument("--evaluate", help="Compute metrics from reviewed annotations JSON")
    parser.add_argument("--xml-dir", default="../data/raw/fulltext")
    parser.add_argument("--dataset", default="../data/processed/triad_phenotype_dataset_v3_final.csv")
    parser.add_argument("--output-dir", default="../data/validation/gold_standard")
    parser.add_argument("--n", type=int, default=5, help="Articles per stratum")
    parser.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()

    if args.create:
        create_annotation_set(args.xml_dir, args.dataset, args.output_dir, args.n, args.seed)
    elif args.evaluate:
        metrics = compute_metrics(args.evaluate)
        print(json.dumps(metrics, indent=2))
    else:
        parser.print_help()
