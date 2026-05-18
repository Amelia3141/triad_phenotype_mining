#!/usr/bin/env python3
"""
Phase 7: Merge original and adjacent corpora, rebuild tiered classification.

Creates a unified 1400-article corpus with:
- Tiered classification (narrow vs broad) for EDS, POTS, MCAS
- Source tracking (original query vs adjacent query)
- Article type, condition flags, symptom data
- Corpus membership flags for analysis subsets
"""

import json
import os
import re
import csv
import datetime

BASE_DIR = "/sessions/adoring-eager-allen/mnt/mphil/triad_phenotype_mining"
RAW_DIR = os.path.join(BASE_DIR, "data/raw")
PROCESSED_DIR = os.path.join(BASE_DIR, "data/processed")

def classify_tier(extraction, is_original=True, old_tier=None):
    """Classify an article into narrow/broad tiers for each condition."""

    terms = extraction.get("terminology_used", [])
    terms_lower = [t.lower() for t in terms]

    # EDS tiers
    eds_narrow_terms = {"heds", "hypermobile eds", "eds hypermobility type", "eds type iii"}
    eds_broad_terms = {"jhs", "hsd"}  # joint hypermobility syndrome, hypermobility spectrum disorder

    eds_narrow = any(t.lower() in eds_narrow_terms for t in terms) or extraction.get("eds_mentioned", False)
    eds_broad = eds_narrow or any(t.lower() in eds_broad_terms for t in terms) or \
                extraction.get("jhs_mentioned", False) or extraction.get("hsd_mentioned", False)

    # For original corpus, use existing subtype classification
    eds_subtype = ""
    has_non_heds_eds = False
    eds_excluded = False
    if old_tier:
        eds_subtype = old_tier.get("eds_subtype", "")
        has_non_heds_eds = old_tier.get("has_non_heds_eds", False)
        eds_excluded = old_tier.get("eds_excluded", False)

    # POTS tiers
    pots_narrow = extraction.get("pots_mentioned", False) or \
                  any(t.lower() in {"pots", "postural tachycardia syndrome"} for t in terms)
    pots_broad = pots_narrow or \
                 extraction.get("dysautonomia_mentioned", False) or \
                 extraction.get("orthostatic_intolerance_mentioned", False) or \
                 extraction.get("vasovagal_mentioned", False) or \
                 extraction.get("ist_mentioned", False) or \
                 any(t.lower() in {"dysautonomia", "orthostatic intolerance", "orthostatic hypotension",
                                    "vasovagal syncope", "autonomic dysfunction"} for t in terms)

    # MCAS tiers
    mcas_narrow = extraction.get("mcas_mentioned", False) or \
                  any(t.lower() in {"mcas", "mcad", "mast cell activation syndrome"} for t in terms)
    mcas_broad = mcas_narrow or \
                 extraction.get("histamine_intolerance_mentioned", False) or \
                 extraction.get("hat_mentioned", False) or \
                 extraction.get("mastocytosis_mentioned", False) or \
                 any(t.lower() in {"histamine intolerance", "mastocytosis"} for t in terms)

    has_mastocytosis_only = extraction.get("mastocytosis_mentioned", False) and not mcas_narrow

    # Triad
    triad_narrow = eds_narrow and pots_narrow and mcas_narrow
    triad_broad = eds_broad and pots_broad and mcas_broad

    return {
        "pmcid": extraction["pmcid"],
        "eds_narrow": eds_narrow,
        "eds_broad": eds_broad,
        "eds_subtype": eds_subtype,
        "has_non_heds_eds": has_non_heds_eds,
        "eds_excluded": eds_excluded,
        "pots_narrow": pots_narrow,
        "pots_broad": pots_broad,
        "mcas_narrow": mcas_narrow,
        "mcas_broad": mcas_broad,
        "has_mastocytosis_only": has_mastocytosis_only,
        "triad_narrow": triad_narrow,
        "triad_broad": triad_broad,
        "terms_used": terms,
        "article_type": extraction.get("article_type_inferred", ""),
        "corpus_source": "original" if is_original else "adjacent",
        "source_query": extraction.get("source_query", ""),
        # Adjacent condition flags
        "dysautonomia_mentioned": extraction.get("dysautonomia_mentioned", False),
        "orthostatic_intolerance_mentioned": extraction.get("orthostatic_intolerance_mentioned", False),
        "vasovagal_mentioned": extraction.get("vasovagal_mentioned", False),
        "ist_mentioned": extraction.get("ist_mentioned", False),
        "histamine_intolerance_mentioned": extraction.get("histamine_intolerance_mentioned", False),
        "hat_mentioned": extraction.get("hat_mentioned", False),
        "jhs_mentioned": extraction.get("jhs_mentioned", False),
        "hsd_mentioned": extraction.get("hsd_mentioned", False),
        "mastocytosis_mentioned": extraction.get("mastocytosis_mentioned", False),
    }


def merge_corpora():
    """Merge original and adjacent extractions, build unified tiered classification."""

    # Load original extractions
    with open(os.path.join(PROCESSED_DIR, "rule_based_extractions.json")) as f:
        original = json.load(f)
    print(f"Original corpus: {len(original)} articles")

    # Load adjacent extractions
    with open(os.path.join(PROCESSED_DIR, "adjacent_extractions.json")) as f:
        adjacent = json.load(f)
    print(f"Adjacent corpus: {len(adjacent)} articles")

    # Load old tiered classification for EDS subtype info
    old_tiers = {}
    tc_path = os.path.join(PROCESSED_DIR, "tiered_classification.json")
    if os.path.exists(tc_path):
        with open(tc_path) as f:
            tc = json.load(f)
        if isinstance(tc, dict):
            old_tiers = tc
        elif isinstance(tc, list):
            old_tiers = {item["pmcid"]: item for item in tc}

    # Load EDS subtype classification
    eds_subtypes = {}
    eds_path = os.path.join(PROCESSED_DIR, "eds_subtype_classification.json")
    if os.path.exists(eds_path):
        with open(eds_path) as f:
            eds_data = json.load(f)
        if isinstance(eds_data, dict):
            eds_subtypes = eds_data
        elif isinstance(eds_data, list):
            eds_subtypes = {item["pmcid"]: item for item in eds_data}

    # Also need to run adjacent condition detection on original corpus
    # (original extractions don't have dysautonomia_mentioned etc.)
    # Re-extract those flags from full text for original articles
    print("\nAdding adjacent condition flags to original corpus...")
    import xml.etree.ElementTree as ET

    adjacent_flags_added = 0
    for ext in original:
        pmcid = ext["pmcid"]
        xml_path = os.path.join(RAW_DIR, "fulltext", f"{pmcid}.xml")
        if not os.path.exists(xml_path):
            continue

        with open(xml_path, "r", encoding="utf-8") as f:
            xml_data = f.read()

        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError:
            continue

        article = root.find(".//article")
        if article is None:
            article = root

        # Build full text
        text_parts = []
        for el in [article.find(".//abstract"), article.find(".//body")]:
            if el is not None:
                text_parts.append("".join(el.itertext()))
        full_text = " ".join(text_parts).lower()
        full_text_norm = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u00ad\u2212]", "-", full_text)

        ext["dysautonomia_mentioned"] = bool(re.search(r"dysautonomia|autonomic\s+dysfunction|autonomic\s+failure|autonomic\s+neuropathy", full_text_norm))
        ext["orthostatic_intolerance_mentioned"] = bool(re.search(r"orthostatic\s+intolerance|orthostatic\s+hypotension", full_text_norm))
        ext["vasovagal_mentioned"] = bool(re.search(r"vasovagal|neurocardiogenic\s+syncop", full_text_norm))
        ext["ist_mentioned"] = bool(re.search(r"inappropriate\s+sinus\s+tachycardia", full_text_norm))
        ext["histamine_intolerance_mentioned"] = bool(re.search(r"histamine\s+intolerance|diamine\s+oxidase|dao\s+deficiency", full_text_norm))
        ext["hat_mentioned"] = bool(re.search(r"hereditary\s+alpha\s+tryptasemia|alpha\s+tryptasemia|\bhat\b.*tryptas", full_text_norm))
        ext["jhs_mentioned"] = bool(re.search(r"\bjhs\b|joint\s+hypermobility\s+syndrome", full_text_norm))
        ext["hsd_mentioned"] = bool(re.search(r"\bhsd\b|hypermobility\s+spectrum\s+disorder", full_text_norm))
        ext["mastocytosis_mentioned"] = bool(re.search(r"mastocytosis|systemic\s+mastocytosis|cutaneous\s+mastocytosis", full_text_norm))
        adjacent_flags_added += 1

    print(f"  Added adjacent flags to {adjacent_flags_added} original articles")

    # Build unified tiered classification
    unified_tiers = []

    # Original corpus
    for ext in original:
        pmcid = ext["pmcid"]
        old_tier = old_tiers.get(pmcid, {})

        # Enrich old_tier with EDS subtype if available
        if pmcid in eds_subtypes:
            eds_info = eds_subtypes[pmcid]
            if isinstance(eds_info, dict):
                old_tier["eds_subtype"] = eds_info.get("subtype", eds_info.get("eds_subtype", ""))
                old_tier["has_non_heds_eds"] = eds_info.get("has_non_heds_eds", False)
                old_tier["eds_excluded"] = eds_info.get("eds_excluded", eds_info.get("excluded", False))

        tier = classify_tier(ext, is_original=True, old_tier=old_tier)
        unified_tiers.append(tier)

    # Adjacent corpus
    for ext in adjacent:
        tier = classify_tier(ext, is_original=False)
        unified_tiers.append(tier)

    # Deduplicate (shouldn't have overlaps but just in case)
    seen = set()
    deduped = []
    for t in unified_tiers:
        if t["pmcid"] not in seen:
            seen.add(t["pmcid"])
            deduped.append(t)

    print(f"\nUnified corpus: {len(deduped)} articles ({len(deduped) - len(adjacent)} original + {len(adjacent)} adjacent, {len(unified_tiers) - len(deduped)} duplicates removed)")

    # Save unified tiered classification
    unified_path = os.path.join(PROCESSED_DIR, "unified_tiered_classification.json")
    with open(unified_path, "w", encoding="utf-8") as f:
        json.dump(deduped, f, indent=2, ensure_ascii=False)
    print(f"Saved: {unified_path}")

    # Also merge all extractions into one file
    all_extractions = []
    seen_ext = set()
    for ext in original + adjacent:
        if ext["pmcid"] not in seen_ext:
            seen_ext.add(ext["pmcid"])
            all_extractions.append(ext)

    merged_path = os.path.join(PROCESSED_DIR, "merged_extractions.json")
    with open(merged_path, "w", encoding="utf-8") as f:
        json.dump(all_extractions, f, indent=2, ensure_ascii=False)
    print(f"Saved merged extractions: {merged_path} ({len(all_extractions)} articles)")

    # Print summary statistics
    print(f"\n{'='*60}")
    print(f"UNIFIED TIERED CLASSIFICATION SUMMARY")
    print(f"{'='*60}")

    for condition, narrow_key, broad_key in [
        ("EDS/hEDS", "eds_narrow", "eds_broad"),
        ("POTS", "pots_narrow", "pots_broad"),
        ("MCAS", "mcas_narrow", "mcas_broad"),
        ("Triad", "triad_narrow", "triad_broad"),
    ]:
        narrow = sum(1 for t in deduped if t[narrow_key])
        broad = sum(1 for t in deduped if t[broad_key])
        broad_only = sum(1 for t in deduped if t[broad_key] and not t[narrow_key])
        print(f"\n  {condition}:")
        print(f"    Narrow: {narrow}")
        print(f"    Broad: {broad}")
        print(f"    Broad-only (not narrow): {broad_only}")

    # Source breakdown
    orig_count = sum(1 for t in deduped if t["corpus_source"] == "original")
    adj_count = sum(1 for t in deduped if t["corpus_source"] == "adjacent")
    print(f"\n  Source breakdown:")
    print(f"    Original corpus: {orig_count}")
    print(f"    Adjacent corpus: {adj_count}")

    # Article types
    types = {}
    for t in deduped:
        at = t.get("article_type", "unknown")
        types[at] = types.get(at, 0) + 1
    print(f"\n  Article types:")
    for at, count in sorted(types.items(), key=lambda x: -x[1]):
        print(f"    {at}: {count}")

    # Cross-condition co-occurrence in adjacent corpus
    print(f"\n  Adjacent articles with triad-condition mentions:")
    adj_articles = [t for t in deduped if t["corpus_source"] == "adjacent"]
    print(f"    Mention EDS: {sum(1 for t in adj_articles if t['eds_narrow'])}")
    print(f"    Mention POTS: {sum(1 for t in adj_articles if t['pots_narrow'])}")
    print(f"    Mention MCAS: {sum(1 for t in adj_articles if t['mcas_narrow'])}")
    print(f"    Mention dysautonomia: {sum(1 for t in adj_articles if t.get('dysautonomia_mentioned'))}")
    print(f"    Mention OI: {sum(1 for t in adj_articles if t.get('orthostatic_intolerance_mentioned'))}")
    print(f"    Mention vasovagal: {sum(1 for t in adj_articles if t.get('vasovagal_mentioned'))}")

    return deduped


if __name__ == "__main__":
    merge_corpora()
