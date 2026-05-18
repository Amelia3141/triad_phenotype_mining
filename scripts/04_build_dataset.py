#!/usr/bin/env python3
"""
Phase 3: Build the provenance-tracked patient-level dataset.

Adds:
- Quoted original age text from the source article
- Age range mapping for descriptive ages
- Publication year extraction
- All fields flattened to tabular format
"""

import json
import csv
import os
import re
import xml.etree.ElementTree as ET
import datetime

BASE_DIR = "/sessions/adoring-eager-allen/mnt/mphil/triad_phenotype_mining"
RAW_DIR = os.path.join(BASE_DIR, "data/raw")
PROCESSED_DIR = os.path.join(BASE_DIR, "data/processed")

# Descriptive age to age range mapping (midpoint for analysis, range for transparency)
DESCRIPTIVE_AGE_MAP = {
    "neonate": {"range": "0-0.08", "midpoint": 0, "label": "0-28 days"},
    "infant": {"range": "0-1", "midpoint": 0.5, "label": "0-1 years"},
    "toddler": {"range": "1-3", "midpoint": 2, "label": "1-3 years"},
    "child": {"range": "3-12", "midpoint": 7.5, "label": "3-12 years"},
    "adolescent": {"range": "12-18", "midpoint": 15, "label": "12-18 years"},
    "young_adult": {"range": "18-30", "midpoint": 24, "label": "18-30 years"},
    "middle_aged": {"range": "40-60", "midpoint": 50, "label": "40-60 years"},
    "elderly": {"range": "65-90", "midpoint": 75, "label": "65+ years"},
}


def extract_age_quote(pmcid):
    """Extract the original quoted text containing age information from the XML."""
    xml_path = os.path.join(RAW_DIR, "fulltext", f"{pmcid}.xml")
    if not os.path.exists(xml_path):
        return ""

    with open(xml_path, "r", encoding="utf-8") as f:
        xml_data = f.read()

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError:
        return ""

    # Get text from abstract and body
    text_parts = []
    abstract = root.find(".//abstract")
    if abstract is not None:
        text_parts.append("".join(abstract.itertext()))
    body = root.find(".//body")
    if body is not None:
        # Get first few sections (case presentation area)
        for sec in list(body.findall(".//sec"))[:5]:
            text_parts.append("".join(sec.itertext()))
    if not text_parts and body is not None:
        text_parts.append("".join(body.itertext())[:3000])

    full_text = " ".join(text_parts)

    # Normalise unicode dashes
    full_text_norm = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u00ad\u2212]", "-", full_text)

    # Find age-containing sentences/phrases
    age_patterns = [
        r"[^.]*?\d{1,3}[\s-]*year[\s-]*old[^.]*?\.",
        r"[^.]*?age[d]?\s*(?:of\s*)?\d{1,3}[^.]*?\.",
        r"[^.]*?\d{1,3}[\s-]*yo\b[^.]*?\.",
        r"[^.]*?\d{1,3}\s*years?\s*of\s*age[^.]*?\.",
        r"[^.]*?\d{1,3}[\s-]*month[\s-]*old[^.]*?\.",
        r"[^.]*?(?:neonate|neonatal|infant|toddler|child|adolescent|young adult|middle[\s-]*aged|elderly)[^.]*?\.",
        r"[^.]*?(?:male|female|woman|man|boy|girl)\s*(?:in\s+(?:his|her)\s+\d+s)[^.]*?\.",
        r"[^.]*?(?:in\s+(?:his|her)\s+(?:\d+s|\w+ies|\w+ties))[^.]*?\.",
    ]

    for pat in age_patterns:
        m = re.search(pat, full_text_norm, re.IGNORECASE)
        if m:
            quote = m.group(0).strip()
            # Truncate very long matches
            if len(quote) > 300:
                quote = quote[:300] + "..."
            return quote

    return ""


def build_dataset():
    """Build the full tabular dataset."""

    # Load extractions
    with open(os.path.join(PROCESSED_DIR, "rule_based_extractions.json")) as f:
        extractions = json.load(f)

    # Load original metadata for additional fields
    metadata = {}
    with open(os.path.join(RAW_DIR, "combined_corpus_metadata.csv"), "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            metadata[row["pmcid"]] = row

    rows = []
    for ext in extractions:
        pmcid = ext["pmcid"]
        meta = metadata.get(pmcid, {})

        # Extract publication year
        pubdate = ext.get("pubdate", meta.get("pubdate", ""))
        pub_year = None
        m = re.search(r"(\d{4})", pubdate)
        if m:
            pub_year = int(m.group(1))

        # Get age quote from original text
        age_quote = extract_age_quote(pmcid)

        # Build age fields
        age_numeric = ext.get("age_at_presentation")
        age_descriptive = ext.get("age_descriptive", "")
        age_range = ""
        age_midpoint = age_numeric  # Use numeric if available

        if age_descriptive and age_descriptive in DESCRIPTIVE_AGE_MAP:
            mapping = DESCRIPTIVE_AGE_MAP[age_descriptive]
            age_range = mapping["label"]
            if age_midpoint is None:
                age_midpoint = mapping["midpoint"]

        # Age group binning (for analysis)
        age_group = ""
        if age_midpoint is not None:
            if age_midpoint < 1:
                age_group = "infant (<1)"
            elif age_midpoint < 5:
                age_group = "early childhood (1-4)"
            elif age_midpoint < 12:
                age_group = "childhood (5-11)"
            elif age_midpoint < 18:
                age_group = "adolescent (12-17)"
            elif age_midpoint < 30:
                age_group = "young adult (18-29)"
            elif age_midpoint < 45:
                age_group = "adult (30-44)"
            elif age_midpoint < 60:
                age_group = "middle aged (45-59)"
            elif age_midpoint < 75:
                age_group = "older adult (60-74)"
            else:
                age_group = "elderly (75+)"

        # Criteria era classification
        criteria_era = ""
        if pub_year:
            if pub_year < 2017:
                criteria_era = "pre-2017 (Villefranche/Brighton era)"
            elif pub_year == 2017:
                criteria_era = "2017 (transition year)"
            else:
                criteria_era = "post-2017 (2017 international classification)"

        row = {
            "pmcid": pmcid,
            "doi": ext.get("doi", meta.get("doi", "")),
            "title": ext.get("title", meta.get("title", "")),
            "journal": ext.get("journal", meta.get("journal", "")),
            "pubdate": pubdate,
            "pub_year": pub_year,
            "criteria_era": criteria_era,
            "article_type_inferred": ext.get("article_type_inferred", ""),
            "num_patients": ext.get("num_patients", ""),
            "age_numeric": age_numeric if age_numeric is not None else "",
            "age_descriptive": age_descriptive,
            "age_original_quote": age_quote,
            "age_range_mapped": age_range,
            "age_midpoint_for_analysis": age_midpoint if age_midpoint is not None else "",
            "age_group": age_group,
            "age_unit_original": ext.get("age_unit_original", "years"),
            "sex": ext.get("sex", ""),
            "eds_mentioned": ext.get("eds_mentioned", False),
            "pots_mentioned": ext.get("pots_mentioned", False),
            "mcas_mentioned": ext.get("mcas_mentioned", False),
            "triad_present": ext.get("triad_present", False),
            "diagnostic_criteria_cited": "; ".join(ext.get("diagnostic_criteria_cited", [])),
            "beighton_score": ext.get("beighton_score", ""),
            "symptoms_detected": "; ".join(ext.get("symptoms_detected", [])),
            "terminology_used": "; ".join(ext.get("terminology_used", [])),
            "extraction_method": ext.get("extraction_method", ""),
            "extraction_date": ext.get("extraction_date", ""),
        }
        rows.append(row)

    # Sort by publication year descending
    rows.sort(key=lambda r: r.get("pub_year") or 0, reverse=True)

    # Save as CSV
    fieldnames = list(rows[0].keys())
    csv_path = os.path.join(PROCESSED_DIR, "triad_phenotype_dataset.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Dataset saved: {csv_path}")
    print(f"Total records: {len(rows)}")

    # Stats
    with_age = sum(1 for r in rows if r["age_numeric"] or r["age_descriptive"])
    with_quote = sum(1 for r in rows if r["age_original_quote"])
    case_reports = [r for r in rows if r["article_type_inferred"] == "case_report"]

    print(f"\n--- Dataset Summary ---")
    print(f"Total articles: {len(rows)}")
    print(f"With any age info: {with_age} ({with_age/len(rows)*100:.1f}%)")
    print(f"With age quote: {with_quote} ({with_quote/len(rows)*100:.1f}%)")
    print(f"Case reports: {len(case_reports)}")
    print(f"Clinical studies: {sum(1 for r in rows if r['article_type_inferred'] == 'clinical_study')}")
    print(f"Reviews/other: {sum(1 for r in rows if r['article_type_inferred'] in ('review_or_study', 'animal_study'))}")

    # Age group distribution for case reports
    print(f"\n--- Age Groups (case reports only, n={len(case_reports)}) ---")
    age_groups = [r["age_group"] for r in case_reports if r["age_group"]]
    for g in sorted(set(age_groups)):
        print(f"  {g}: {age_groups.count(g)}")

    return csv_path


if __name__ == "__main__":
    build_dataset()
