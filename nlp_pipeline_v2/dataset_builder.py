"""
Dataset builder: converts NLP extraction JSON into publication-ready
flat files for Nature Scientific Data.

Outputs:
1. patient_level_dataset.tsv    -- MACCR-style flat TSV, one row per article
2. data_dictionary.json         -- machine-readable field definitions
3. corpus_metadata.csv          -- publication metadata for all articles
4. comorbidity_matrix.csv       -- binary matrix of comorbidities x articles
5. treatment_response_summary.csv -- drug-outcome linkage table
6. extraction_quality_report.csv  -- completeness/coverage per article
"""

import csv
import json
import os
from typing import Dict, List, Any


# ── Data dictionary ───────────────────────────────────────────────────

DATA_DICTIONARY = {
    "pmcid": {
        "description": "PubMed Central identifier",
        "type": "string",
        "example": "PMC5778345",
        "source": "filename",
    },
    "doi": {
        "description": "Digital Object Identifier",
        "type": "string",
        "example": "10.1136/bcr-2017-221405",
        "source": "xml_front_matter",
    },
    "pmid": {
        "description": "PubMed identifier",
        "type": "string",
        "source": "xml_front_matter",
    },
    "title": {
        "description": "Article title",
        "type": "string",
        "source": "xml_front_matter",
    },
    "journal": {
        "description": "Journal name",
        "type": "string",
        "source": "xml_front_matter",
    },
    "pub_year": {
        "description": "Publication year",
        "type": "integer",
        "source": "xml_front_matter",
    },
    "pub_date": {
        "description": "Full publication date (YYYY-MM-DD)",
        "type": "date",
        "source": "xml_front_matter",
    },
    "article_type": {
        "description": "Article type from journal metadata",
        "type": "string",
        "source": "xml_front_matter",
    },
    "author_count": {
        "description": "Number of authors",
        "type": "integer",
        "source": "xml_front_matter",
    },
    "first_author": {
        "description": "First author name",
        "type": "string",
        "source": "xml_front_matter",
    },
    "countries": {
        "description": "Author affiliation countries (semicolon-separated)",
        "type": "string",
        "source": "xml_front_matter",
    },
    "departments": {
        "description": "Author departments/specialties (semicolon-separated)",
        "type": "string",
        "source": "xml_front_matter",
    },
    "keywords": {
        "description": "Article keywords (semicolon-separated)",
        "type": "string",
        "source": "xml_front_matter",
    },
    "license": {
        "description": "Article license type",
        "type": "string",
        "source": "xml_front_matter",
    },
    "age_at_presentation": {
        "description": "Patient age at presentation (years)",
        "type": "float",
        "source": "nlp_extraction",
    },
    "sex": {
        "description": "Patient sex (male/female)",
        "type": "string",
        "allowed_values": ["male", "female"],
        "source": "nlp_extraction",
    },
    "age_at_onset": {
        "description": "Age at symptom onset (years), may be inferred from duration",
        "type": "float",
        "source": "nlp_extraction",
    },
    "age_at_onset_qualitative": {
        "description": "Qualitative age at onset (childhood, adolescence, etc.)",
        "type": "string",
        "source": "nlp_extraction",
    },
    "symptom_duration_years": {
        "description": "Duration of symptoms before presentation (years)",
        "type": "float",
        "source": "nlp_extraction",
    },
    "diagnostic_delay_years": {
        "description": "Time from onset to diagnosis (years)",
        "type": "float",
        "source": "nlp_extraction",
    },
    "misdiagnoses": {
        "description": "Prior misdiagnoses (semicolon-separated)",
        "type": "string",
        "source": "nlp_extraction",
    },
    "referral_pathway": {
        "description": "Specialties seen (semicolon-separated)",
        "type": "string",
        "source": "nlp_extraction",
    },
    "eds_mentioned": {
        "description": "Ehlers-Danlos syndrome mentioned (boolean)",
        "type": "boolean",
        "source": "nlp_extraction",
    },
    "pots_mentioned": {
        "description": "POTS mentioned (boolean)",
        "type": "boolean",
        "source": "nlp_extraction",
    },
    "mcas_mentioned": {
        "description": "MCAS mentioned (boolean)",
        "type": "boolean",
        "source": "nlp_extraction",
    },
    "triad_present": {
        "description": "All three conditions (EDS + POTS + MCAS) mentioned",
        "type": "boolean",
        "source": "nlp_extraction",
    },
    "eds_subtype": {
        "description": "EDS subtype if specified",
        "type": "string",
        "source": "nlp_extraction",
    },
    "symptoms_affirmed": {
        "description": "Symptoms positively mentioned (semicolon-separated)",
        "type": "string",
        "source": "nlp_extraction",
    },
    "symptoms_negated": {
        "description": "Symptoms explicitly denied/absent (semicolon-separated)",
        "type": "string",
        "source": "nlp_extraction",
    },
    "symptom_count": {
        "description": "Number of distinct symptoms reported",
        "type": "integer",
        "source": "nlp_extraction",
    },
    "drugs_affirmed": {
        "description": "Medications mentioned as given/taken (semicolon-separated)",
        "type": "string",
        "source": "nlp_extraction",
    },
    "drugs_negated": {
        "description": "Medications explicitly denied/not given (semicolon-separated)",
        "type": "string",
        "source": "nlp_extraction",
    },
    "drug_count": {
        "description": "Number of distinct medications reported",
        "type": "integer",
        "source": "nlp_extraction",
    },
    "drug_classes": {
        "description": "Unique drug classes (semicolon-separated)",
        "type": "string",
        "source": "nlp_extraction",
    },
    "treatment_response_count": {
        "description": "Number of drug-outcome linkages found",
        "type": "integer",
        "source": "nlp_extraction",
    },
    "treatment_responses_improved": {
        "description": "Drugs with positive response (semicolon-separated)",
        "type": "string",
        "source": "nlp_extraction",
    },
    "treatment_responses_negative": {
        "description": "Drugs with negative/no response (semicolon-separated)",
        "type": "string",
        "source": "nlp_extraction",
    },
    "family_history": {
        "description": "Family history status (positive/negative/not_mentioned)",
        "type": "string",
        "allowed_values": ["positive", "negative", "not_mentioned"],
        "source": "nlp_extraction",
    },
    "comorbidities_affirmed": {
        "description": "Comorbidities found (semicolon-separated)",
        "type": "string",
        "source": "nlp_extraction",
    },
    "comorbidity_count": {
        "description": "Number of comorbidities detected",
        "type": "integer",
        "source": "nlp_extraction",
    },
    "negative_findings": {
        "description": "Explicitly negative clinical findings (semicolon-separated)",
        "type": "string",
        "source": "nlp_extraction",
    },
    "outcome_types": {
        "description": "Outcome categories detected (semicolon-separated)",
        "type": "string",
        "source": "nlp_extraction",
    },
    "completeness_score": {
        "description": "Proportion of fields with extracted values (0-1)",
        "type": "float",
        "source": "computed",
    },
    "coverage_score": {
        "description": "Proportion of fields either reported or explicitly absent (0-1)",
        "type": "float",
        "source": "computed",
    },
    "sentence_count": {
        "description": "Total clinical sentences analysed",
        "type": "integer",
        "source": "nlp_extraction",
    },
    "extraction_method": {
        "description": "Extraction pipeline version",
        "type": "string",
        "source": "system",
    },
    "extraction_date": {
        "description": "Date of extraction (ISO 8601)",
        "type": "datetime",
        "source": "system",
    },
}


def _safe_join(items: list, sep: str = "; ") -> str:
    """Safely join a list of strings, handling None and dicts."""
    if not items:
        return ""
    parts = []
    for item in items:
        if isinstance(item, dict):
            # Extract the most useful field
            parts.append(item.get("condition", item.get("drug", item.get("specialty", str(item)))))
        elif item is not None:
            parts.append(str(item))
    return sep.join(parts)


def flatten_extraction(ext: dict) -> dict:
    """Convert a nested NLP extraction dict into a flat row for TSV."""
    pub = ext.get("publication_metadata", {})
    conditions = ext.get("conditions", {})
    completeness = ext.get("completeness", {})
    summary = completeness.get("_summary", {})
    fh = ext.get("family_history", {})

    # EDS subtype
    eds_subtype = ""
    for sub in ["hEDS", "vEDS", "cEDS", "HSD", "JHS"]:
        key = f"EDS_{sub}"
        if conditions.get(key, {}).get("mentioned"):
            eds_subtype = sub
            break

    # Treatment responses
    tr = ext.get("treatment_responses", [])
    positive_dirs = {"improved", "tolerated", "maintained", "functional_recovery"}
    negative_dirs = {"no_improvement", "worsened", "refractory", "discontinued",
                     "adverse_effect", "intolerant"}

    tr_improved = list({r["drug"] for r in tr if r["response_direction"] in positive_dirs})
    tr_negative = list({r["drug"] for r in tr if r["response_direction"] in negative_dirs})

    # Comorbidities
    comorbs = ext.get("comorbidities", {})
    comorbs_affirmed = [name for name, data in comorbs.items() if not data.get("negated")]

    row = {
        "pmcid": ext.get("pmcid", ""),
        "doi": pub.get("doi", ""),
        "pmid": pub.get("pmid", ""),
        "title": pub.get("title", ""),
        "journal": pub.get("journal", ""),
        "pub_year": pub.get("pub_year", ""),
        "pub_date": pub.get("pub_date", ""),
        "article_type": pub.get("article_type", ""),
        "author_count": pub.get("author_count", ""),
        "first_author": pub.get("authors", [{}])[0].get("name", "") if pub.get("authors") else "",
        "countries": "; ".join(pub.get("countries", [])),
        "departments": "; ".join(pub.get("departments", [])),
        "keywords": "; ".join(pub.get("keywords", [])),
        "license": pub.get("license", ""),

        "age_at_presentation": ext.get("age_at_presentation", ""),
        "sex": ext.get("sex", ""),
        "age_at_onset": ext.get("age_at_onset", ""),
        "age_at_onset_qualitative": ext.get("age_at_onset_qualitative", ""),
        "symptom_duration_years": ext.get("symptom_duration_years", ""),
        "diagnostic_delay_years": ext.get("diagnostic_delay_years", ""),
        "misdiagnoses": _safe_join(ext.get("misdiagnoses", [])),
        "referral_pathway": _safe_join(ext.get("referral_pathway", [])),

        "eds_mentioned": conditions.get("EDS", {}).get("mentioned", False),
        "pots_mentioned": conditions.get("POTS", {}).get("mentioned", False),
        "mcas_mentioned": conditions.get("MCAS", {}).get("mentioned", False),
        "triad_present": (
            conditions.get("EDS", {}).get("mentioned", False)
            and conditions.get("POTS", {}).get("mentioned", False)
            and conditions.get("MCAS", {}).get("mentioned", False)
        ),
        "eds_subtype": eds_subtype,

        "symptoms_affirmed": "; ".join(s["symptom"] for s in ext.get("symptoms_affirmed", [])),
        "symptoms_negated": "; ".join(s["symptom"] for s in ext.get("symptoms_negated", [])),
        "symptom_count": len(ext.get("symptoms_affirmed", [])),

        "drugs_affirmed": "; ".join(d["drug"] for d in ext.get("drugs_affirmed", [])),
        "drugs_negated": "; ".join(d["drug"] for d in ext.get("drugs_negated", [])),
        "drug_count": ext.get("drug_count", 0),
        "drug_classes": "; ".join(sorted(set(d["drug_class"] for d in ext.get("drugs_affirmed", [])))),

        "treatment_response_count": len(tr),
        "treatment_responses_improved": "; ".join(sorted(tr_improved)),
        "treatment_responses_negative": "; ".join(sorted(tr_negative)),

        "family_history": (
            "positive" if fh.get("has_family_history") is True
            else "negative" if fh.get("has_family_history") is False
            else "not_mentioned"
        ),

        "comorbidities_affirmed": "; ".join(sorted(comorbs_affirmed)),
        "comorbidity_count": len(comorbs_affirmed),

        "negative_findings": "; ".join(nf["finding"] for nf in ext.get("negative_findings", [])[:10]),
        "outcome_types": "; ".join(sorted(set(o["outcome_type"] for o in ext.get("outcomes", [])))),

        "completeness_score": summary.get("completeness_score", ""),
        "coverage_score": summary.get("coverage_score", ""),
        "sentence_count": ext.get("sentence_count", ""),
        "extraction_method": ext.get("extraction_method", ""),
        "extraction_date": ext.get("extraction_date", ""),
    }

    # Replace None with empty string for TSV
    return {k: ("" if v is None else v) for k, v in row.items()}


def build_patient_level_dataset(extractions: List[dict], output_path: str):
    """Build MACCR-style flat TSV, one row per article."""
    if not extractions:
        return

    rows = [flatten_extraction(ext) for ext in extractions if not ext.get("error")]
    fieldnames = list(DATA_DICTIONARY.keys())

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Patient-level dataset: {len(rows)} rows -> {output_path}")


def build_corpus_metadata(extractions: List[dict], output_path: str):
    """Build corpus metadata CSV (publication info only)."""
    rows = []
    for ext in extractions:
        if ext.get("error"):
            continue
        pub = ext.get("publication_metadata", {})
        authors = pub.get("authors", [])

        rows.append({
            "pmcid": ext.get("pmcid", ""),
            "doi": pub.get("doi", ""),
            "pmid": pub.get("pmid", ""),
            "title": pub.get("title", ""),
            "journal": pub.get("journal", ""),
            "journal_abbrev": pub.get("journal_abbrev", ""),
            "pub_year": pub.get("pub_year", ""),
            "pub_date": pub.get("pub_date", ""),
            "article_type": pub.get("article_type", ""),
            "article_type_attr": pub.get("article_type_attr", ""),
            "author_count": pub.get("author_count", ""),
            "first_author": authors[0].get("name", "") if authors else "",
            "last_author": authors[-1].get("name", "") if authors else "",
            "all_authors": "; ".join(a["name"] for a in authors),
            "countries": "; ".join(pub.get("countries", [])),
            "departments": "; ".join(pub.get("departments", [])),
            "keywords": "; ".join(pub.get("keywords", [])),
            "mesh_terms": "; ".join(pub.get("mesh_terms", [])),
            "funding_sources": "; ".join(pub.get("funding_sources", [])),
            "license": pub.get("license", ""),
        })

    if not rows:
        return

    fieldnames = list(rows[0].keys())
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Corpus metadata: {len(rows)} rows -> {output_path}")


def build_comorbidity_matrix(extractions: List[dict], output_path: str):
    """Build binary comorbidity matrix (articles x comorbidities).

    Columns: pmcid, then one column per comorbidity (1=affirmed, -1=negated, 0=not mentioned).
    Also includes the 20 symptom categories.
    """
    # Collect all comorbidity and symptom names
    all_comorbs = set()
    all_symptoms = set()

    for ext in extractions:
        if ext.get("error"):
            continue
        for name in ext.get("comorbidities", {}):
            all_comorbs.add(name)
        for s in ext.get("symptoms_affirmed", []):
            all_symptoms.add(s["symptom"])
        for s in ext.get("symptoms_negated", []):
            all_symptoms.add(s["symptom"])

    all_comorbs = sorted(all_comorbs)
    all_symptoms = sorted(all_symptoms)
    all_cols = all_symptoms + all_comorbs

    rows = []
    for ext in extractions:
        if ext.get("error"):
            continue

        row = {"pmcid": ext.get("pmcid", "")}

        # Symptoms
        affirmed = {s["symptom"] for s in ext.get("symptoms_affirmed", [])}
        negated = {s["symptom"] for s in ext.get("symptoms_negated", [])}
        for sym in all_symptoms:
            if sym in affirmed:
                row[sym] = 1
            elif sym in negated:
                row[sym] = -1
            else:
                row[sym] = 0

        # Comorbidities
        comorbs = ext.get("comorbidities", {})
        for comorb in all_comorbs:
            if comorb in comorbs:
                row[comorb] = -1 if comorbs[comorb].get("negated") else 1
            else:
                row[comorb] = 0

        rows.append(row)

    if not rows:
        return

    fieldnames = ["pmcid"] + all_cols
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Comorbidity matrix: {len(rows)} rows x {len(all_cols)} conditions -> {output_path}")


def build_treatment_response_summary(extractions: List[dict], output_path: str):
    """Build treatment-response summary table.

    One row per drug-outcome linkage across all articles.
    """
    rows = []
    for ext in extractions:
        if ext.get("error"):
            continue
        pmcid = ext.get("pmcid", "")
        for tr in ext.get("treatment_responses", []):
            rows.append({
                "pmcid": pmcid,
                "drug": tr.get("drug", ""),
                "drug_class": tr.get("drug_class", ""),
                "response_direction": tr.get("response_direction", ""),
                "response_text": tr.get("response", ""),
                "linkage_type": tr.get("linkage", ""),
                "evidence_sentence": tr.get("evidence_sentence", ""),
                "context_sentence": tr.get("context_sentence", ""),
            })

    if not rows:
        return

    fieldnames = list(rows[0].keys())
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Treatment-response summary: {len(rows)} linkages -> {output_path}")


def build_extraction_quality_report(extractions: List[dict], output_path: str):
    """Build extraction quality report (completeness per article)."""
    rows = []
    for ext in extractions:
        if ext.get("error"):
            rows.append({
                "pmcid": ext.get("pmcid", ""),
                "error": ext.get("error", ""),
                "completeness_score": 0,
                "coverage_score": 0,
                "fields_reported": 0,
                "fields_absent": 0,
                "fields_not_mentioned": 0,
                "total_fields": 0,
                "sentence_count": 0,
            })
            continue

        comp = ext.get("completeness", {})
        summary = comp.get("_summary", {})

        rows.append({
            "pmcid": ext.get("pmcid", ""),
            "error": "",
            "completeness_score": summary.get("completeness_score", 0),
            "coverage_score": summary.get("coverage_score", 0),
            "fields_reported": summary.get("reported", 0),
            "fields_absent": summary.get("absent", 0),
            "fields_not_mentioned": summary.get("not_mentioned", 0),
            "total_fields": summary.get("total_fields", 0),
            "sentence_count": ext.get("sentence_count", 0),
            "case_sentence_count": ext.get("case_sentence_count", 0),
            "symptom_count": len(ext.get("symptoms_affirmed", [])),
            "drug_count": ext.get("drug_count", 0),
            "treatment_response_count": len(ext.get("treatment_responses", [])),
            "comorbidity_count": len([c for c in ext.get("comorbidities", {}).values()
                                      if not c.get("negated")]),
        })

    if not rows:
        return

    # Sort by completeness score descending
    rows.sort(key=lambda r: r.get("completeness_score", 0), reverse=True)

    fieldnames = list(rows[0].keys())
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Summary stats
    scores = [r["completeness_score"] for r in rows if r["completeness_score"] > 0]
    if scores:
        avg = sum(scores) / len(scores)
        median = sorted(scores)[len(scores) // 2]
        print(f"Quality report: {len(rows)} articles -> {output_path}")
        print(f"  Mean completeness: {avg:.3f}, Median: {median:.3f}")
        print(f"  Range: {min(scores):.3f} - {max(scores):.3f}")


def build_data_dictionary(output_path: str):
    """Write the data dictionary as JSON."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(DATA_DICTIONARY, f, indent=2, ensure_ascii=False)
    print(f"Data dictionary: {len(DATA_DICTIONARY)} fields -> {output_path}")


def build_all_outputs(extractions: List[dict], output_dir: str):
    """Build all NSD output files from extraction results."""
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"Building NSD dataset outputs ({len(extractions)} articles)")
    print(f"{'='*60}\n")

    build_patient_level_dataset(
        extractions,
        os.path.join(output_dir, "patient_level_dataset.tsv"),
    )
    build_corpus_metadata(
        extractions,
        os.path.join(output_dir, "corpus_metadata.csv"),
    )
    build_comorbidity_matrix(
        extractions,
        os.path.join(output_dir, "comorbidity_matrix.csv"),
    )
    build_treatment_response_summary(
        extractions,
        os.path.join(output_dir, "treatment_response_summary.csv"),
    )
    build_extraction_quality_report(
        extractions,
        os.path.join(output_dir, "extraction_quality_report.csv"),
    )
    build_data_dictionary(
        os.path.join(output_dir, "data_dictionary.json"),
    )

    print(f"\nAll outputs saved to {output_dir}/")
