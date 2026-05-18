#!/usr/bin/env python3
"""
Phase 2: Download full-text from PMC OA and extract structured phenotype data.

Uses PMC OA web service to get full text, then extracts structured data
using the extraction schema. This version uses direct text parsing with
structured prompts designed for later LLM extraction, but performs
rule-based extraction as a first pass.

For LLM-based extraction: the script outputs the text chunks that need
to be sent to an LLM API with the extraction prompt.

Provenance: Every article access and extraction is logged.
"""

import csv
import json
import os
import re
import time
import datetime
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from html import unescape

BASE_DIR = "/sessions/adoring-eager-allen/mnt/mphil/triad_phenotype_mining"
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
LOG_DIR = os.path.join(BASE_DIR, "logs")

PMC_OA_URL = "https://www.ncbi.nlm.nih.gov/pmc/oai/oai.cgi"
PMC_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

RATE_LIMIT = 0.4  # seconds between NCBI requests

os.makedirs(os.path.join(RAW_DIR, "fulltext"), exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

def log_access(pmcid, status, notes=""):
    """Log each article access attempt."""
    log_file = os.path.join(LOG_DIR, "fulltext_access_log.jsonl")
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "pmcid": pmcid,
        "status": status,
        "notes": notes
    }
    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


def fetch_pmc_fulltext(pmcid):
    """Fetch full text XML from PMC via efetch."""
    # Strip PMC prefix if present for the ID parameter
    uid = pmcid.replace("PMC", "")
    url = f"{PMC_EFETCH_URL}?db=pmc&id={uid}&rettype=xml&retmode=xml"

    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "TriadPhenotypeMining/1.0 (research; ghhercock@gmail.com)")
        with urllib.request.urlopen(req, timeout=30) as resp:
            xml_data = resp.read().decode("utf-8")
        return xml_data
    except urllib.error.HTTPError as e:
        return None
    except Exception as e:
        return None


def extract_text_from_nxml(xml_string):
    """Extract readable text sections from PMC NXML format."""
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError:
        return None

    article = root.find(".//article")
    if article is None:
        article = root

    sections = {}

    # Title
    title_el = article.find(".//article-title")
    if title_el is not None:
        sections["title"] = "".join(title_el.itertext()).strip()

    # Abstract
    abstract_el = article.find(".//abstract")
    if abstract_el is not None:
        sections["abstract"] = "".join(abstract_el.itertext()).strip()

    # Body sections
    body = article.find(".//body")
    if body is not None:
        for sec in body.findall(".//sec"):
            sec_title_el = sec.find("title")
            sec_title = "".join(sec_title_el.itertext()).strip() if sec_title_el is not None else "untitled"

            # Get all paragraph text in this section
            paragraphs = []
            for p in sec.findall(".//p"):
                text = "".join(p.itertext()).strip()
                if text:
                    paragraphs.append(text)

            if paragraphs:
                sections[sec_title.lower()] = "\n\n".join(paragraphs)

    # If no body sections found, try to get all text
    if len(sections) <= 2:  # only title and/or abstract
        if body is not None:
            all_text = "".join(body.itertext()).strip()
            if all_text:
                sections["body"] = all_text

    return sections


def build_extraction_prompt(sections, pmcid):
    """Build the text payload for extraction.
    Returns the concatenated clinical text ready for LLM processing."""

    # Prioritise sections most likely to contain patient data
    priority_keys = [
        "case", "case report", "case presentation", "case description",
        "clinical presentation", "patient", "history", "clinical features",
        "results", "findings", "abstract"
    ]

    clinical_text_parts = []

    # Add abstract first
    if "abstract" in sections:
        clinical_text_parts.append(f"[ABSTRACT]\n{sections['abstract']}")

    # Add case-relevant sections
    for key in priority_keys:
        for sec_name, sec_text in sections.items():
            if key in sec_name.lower() and sec_text not in [s.split("\n", 1)[-1] if "\n" in s else s for s in clinical_text_parts]:
                clinical_text_parts.append(f"[{sec_name.upper()}]\n{sec_text}")

    # Add discussion if present (may contain diagnostic reasoning)
    for sec_name, sec_text in sections.items():
        if "discussion" in sec_name.lower():
            clinical_text_parts.append(f"[{sec_name.upper()}]\n{sec_text}")
            break

    # If still very little text, include everything
    if len(clinical_text_parts) <= 1:
        for sec_name, sec_text in sections.items():
            tag = f"[{sec_name.upper()}]\n{sec_text}"
            if tag not in clinical_text_parts:
                clinical_text_parts.append(tag)

    return "\n\n---\n\n".join(clinical_text_parts)


def rule_based_extract(sections, pmcid):
    """First-pass rule-based extraction for key fields.
    This provides a baseline; LLM extraction will be more comprehensive."""

    full_text = " ".join(sections.values()).lower()
    # Normalise unicode dashes/hyphens to ASCII hyphen for pattern matching
    full_text_norm = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u00ad\u2212]", "-", full_text)

    result = {
        "pmcid": pmcid,
        "extraction_method": "rule_based_v2",
        "extraction_date": datetime.datetime.utcnow().isoformat(),
    }

    # Demographics - age (expanded patterns, using normalised text)
    age_patterns = [
        # "55-year-old", "55 year old", "55 year-old"
        r"(\d{1,3})[\s-]*year[\s-]*old",
        # "aged 55", "age 55", "age of 55"
        r"age[d]?\s*(?:of\s*)?(\d{1,3})\b",
        # "55-yo", "55 yo"
        r"(\d{1,3})[\s-]*yo\b",
        # "a 55-year-old" in various Unicode forms (already normalised)
        r"a\s+(\d{1,3})[\s-]*year",
        # "patient, 55," or "woman, 55," or "man, 55,"
        r"(?:patient|woman|man|female|male|girl|boy),?\s*(?:aged?\s*)?(\d{1,3})[,\s]",
        # "55 years of age"
        r"(\d{1,3})\s*years?\s*of\s*age",
        # "55-month-old" (for paediatric cases, convert later)
        r"(\d{1,3})[\s-]*month[\s-]*old",
        # "at age 55"
        r"at\s+(?:the\s+)?age\s+(?:of\s+)?(\d{1,3})",
    ]
    for pat in age_patterns:
        m = re.search(pat, full_text_norm)
        if m:
            age = int(m.group(1))
            if "month" in pat and 0 < age < 240:
                result["age_at_presentation"] = round(age / 12, 1)
                result["age_unit_original"] = "months"
                break
            elif 0 < age < 120:
                result["age_at_presentation"] = age
                break

    # Descriptive age ranges (when no numeric age found)
    if "age_at_presentation" not in result:
        descriptive_age_map = {
            r"\bneonat": "neonate",
            r"\binfant\b": "infant",
            r"\btoddler\b": "toddler",
            r"\bchild\b|\bpediatric\b|\bpaediatric\b": "child",
            r"\badolescent\b|\bteenager\b": "adolescent",
            r"\byoung adult\b": "young_adult",
            r"\bmiddle[\s-]*aged?\b": "middle_aged",
            r"\belderly\b|\bgeriatric\b": "elderly",
        }
        for pat, label in descriptive_age_map.items():
            if re.search(pat, full_text_norm):
                result["age_descriptive"] = label
                break

    # Demographics - sex (improved: prioritise case-presentation context)
    # Look in abstract and case presentation sections first
    case_text = ""
    for key in ["abstract", "case", "case report", "case presentation", "history"]:
        if key in sections:
            case_text += sections[key].lower() + " "
    case_text_norm = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u00ad\u2212]", "-", case_text) if case_text else full_text_norm

    sex_patterns = [
        (r"(\d+[\s-]*year[\s-]*old)\s*(female|woman|girl|male|man|boy)", None),
        (r"\b(female|woman|girl)\s*(?:patient|aged|,)", "female"),
        (r"\b(male|man|boy)\s*(?:patient|aged|,)", "male"),
        (r"\b(she|her)\s+(?:was|had|presented|reported)", "female"),
        (r"\b(he|his)\s+(?:was|had|presented|reported)", "male"),
    ]
    for pat, fixed_sex in sex_patterns:
        m = re.search(pat, case_text_norm)
        if m:
            if fixed_sex:
                result["sex"] = fixed_sex
            else:
                gender_word = m.group(2)
                result["sex"] = "female" if gender_word in ("female", "woman", "girl") else "male"
            break
    if "sex" not in result:
        if re.search(r"\b(female|woman|girl)\b", full_text_norm):
            result["sex"] = "female"
        elif re.search(r"\b(male|man|boy)\b", full_text_norm):
            result["sex"] = "male"

    # Article type classification (to flag non-case-reports)
    num_patients_mentioned = []
    for m in re.finditer(r"(\d+)\s*(?:patients|participants|subjects|individuals|cases)", full_text_norm):
        n = int(m.group(1))
        if n > 1:
            num_patients_mentioned.append(n)

    review_signals = [
        r"systematic\s+review", r"meta[\s-]*analysis", r"retrospective\s+(?:study|analysis|review)",
        r"prospective\s+(?:study|cohort)", r"cross[\s-]*sectional", r"cohort\s+study",
        r"randomized|randomised", r"we\s+(?:included|enrolled|recruited|studied)\s+\d+",
        r"animal\s+model|mouse|mice|murine|rat\b|knockout",
    ]
    is_likely_study = any(re.search(p, full_text_norm) for p in review_signals)
    is_likely_animal = bool(re.search(r"animal\s+model|mouse|mice|murine|rat\b|knockout|transgenic", full_text_norm))

    result["article_type_inferred"] = "case_report"
    if is_likely_animal:
        result["article_type_inferred"] = "animal_study"
    elif is_likely_study and num_patients_mentioned and max(num_patients_mentioned) > 20:
        result["article_type_inferred"] = "clinical_study"
    elif is_likely_study:
        result["article_type_inferred"] = "review_or_study"

    # Condition detection
    result["eds_mentioned"] = bool(re.search(r"ehlers[\s-]*danlos|heds|\beds\b.*hypermobil|hypermobility syndrome", full_text_norm))
    result["pots_mentioned"] = bool(re.search(r"postural.*tachycardia|orthostatic.*tachycardia|\bpots\b", full_text_norm))
    result["mcas_mentioned"] = bool(re.search(r"mast cell activation|mcas|mastocytosis", full_text_norm))
    result["triad_present"] = result["eds_mentioned"] and result["pots_mentioned"] and result["mcas_mentioned"]

    # Diagnostic criteria
    criteria_patterns = {
        "2017 international classification": r"2017.*international.*classif|2017.*eds.*criteria|malfait.*2017",
        "Villefranche": r"villefranche",
        "Brighton": r"brighton.*criteria",
        "Beighton": r"beighton.*score",
        "2015 POTS consensus": r"2015.*consensus|heart rhythm society.*pots",
        "MCAS consensus criteria": r"consensus.*mast cell|valent.*2012|akin.*2010",
    }
    cited_criteria = []
    for name, pat in criteria_patterns.items():
        if re.search(pat, full_text_norm):
            cited_criteria.append(name)
    result["diagnostic_criteria_cited"] = cited_criteria

    # Beighton score
    m = re.search(r"beighton.*?score.*?(\d)[/\s]*(?:of\s*)?9", full_text_norm)
    if m:
        result["beighton_score"] = int(m.group(1))

    # Key symptoms
    symptom_patterns = {
        "joint_hypermobility": r"joint.*hypermobil|hypermobile.*joint|generali[sz]ed.*hypermobil",
        "subluxations_dislocations": r"subluxat|dislocat",
        "chronic_pain": r"chronic.*pain|widespread.*pain|persistent.*pain",
        "orthostatic_intolerance": r"orthostatic.*intoleran|unable.*stand|standing.*intoleran",
        "tachycardia": r"tachycardia|heart rate.*increas|elevated.*heart rate",
        "syncope": r"syncop|faint|pre-syncop|presyncop",
        "flushing": r"flush",
        "urticaria": r"urticaria|hives",
        "anaphylaxis": r"anaphyla",
        "skin_hyperextensibility": r"skin.*hyperextens|hyperextens.*skin|stretchy.*skin|velvet.*skin",
        "easy_bruising": r"easy.*bruis|bruis.*easily",
        "fatigue": r"\bfatigue\b|chronic.*tired",
        "gi_symptoms": r"gastropar|dysmotil|nausea|vomit|abdominal.*pain|constipat|diarrh",
        "headache_migraine": r"headache|migraine|cephalgia",
        "neuropathy": r"neuropath|small.*fiber|small.*fibre",
        "chiari": r"chiari|arnold-chiari",
        "brain_fog": r"brain.*fog|cognitive.*difficult|concentrat.*difficult",
        "mitral_valve_prolapse": r"mitral.*valve.*prolap|mvp",
        "palpitations": r"palpitat",
        "medication_sensitivity": r"medication.*sensiti|drug.*sensiti|adverse.*react.*medic|multiple.*drug.*allerg",
    }

    symptoms_found = []
    for symptom_name, pat in symptom_patterns.items():
        if re.search(pat, full_text_norm):
            symptoms_found.append(symptom_name)
    result["symptoms_detected"] = symptoms_found

    # Terminology used (for diagnostic drift analysis)
    terminology_patterns = {
        "EDS type III": r"eds.*type\s*iii|type\s*iii.*eds",
        "EDS hypermobility type": r"eds.*hypermobility\s*type|hypermobility\s*type.*eds",
        "hEDS": r"\bheds\b",
        "hypermobile EDS": r"hypermobile.*ehlers|ehlers.*danlos.*hypermobile",
        "JHS": r"\bjhs\b|joint.*hypermobility.*syndrome",
        "HSD": r"\bhsd\b|hypermobility.*spectrum.*disorder",
        "POTS": r"\bpots\b",
        "postural tachycardia syndrome": r"postural.*tachycardia.*syndrome",
        "dysautonomia": r"dysautonomia",
        "MCAS": r"\bmcas\b",
        "MCAD": r"\bmcad\b|mast.*cell.*activation.*disease",
        "mast cell activation syndrome": r"mast\s+cell\s+activation\s+syndrome",
        "mastocytosis": r"mastocytosis",
    }
    terms_used = []
    for term_name, pat in terminology_patterns.items():
        if re.search(pat, full_text_norm):
            terms_used.append(term_name)
    result["terminology_used"] = terms_used

    # Number of patients (rough heuristic)
    if re.search(r"case\s*series|(\d+)\s*patients|(\d+)\s*cases", full_text_norm):
        m = re.search(r"(\d+)\s*(?:patients|cases|subjects)", full_text_norm)
        if m and int(m.group(1)) > 1:
            result["num_patients"] = int(m.group(1))
        else:
            result["num_patients"] = 1
    else:
        result["num_patients"] = 1

    return result


def process_corpus(max_articles=None):
    """Process the full corpus: download, extract text, run rule-based extraction."""

    # Load corpus metadata
    corpus_file = os.path.join(RAW_DIR, "combined_corpus_metadata.csv")
    df_rows = []
    with open(corpus_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            df_rows.append(row)

    if max_articles:
        df_rows = df_rows[:max_articles]

    print(f"Processing {len(df_rows)} articles...")

    extractions = []
    text_payloads = []  # For later LLM extraction
    success_count = 0
    fail_count = 0

    for i, row in enumerate(df_rows):
        pmcid = row["pmcid"]

        # Check if already downloaded
        xml_path = os.path.join(RAW_DIR, "fulltext", f"{pmcid}.xml")

        if os.path.exists(xml_path):
            with open(xml_path, "r", encoding="utf-8") as f:
                xml_data = f.read()
        else:
            print(f"  [{i+1}/{len(df_rows)}] Fetching {pmcid}...")
            xml_data = fetch_pmc_fulltext(pmcid)
            time.sleep(RATE_LIMIT)

            if xml_data:
                with open(xml_path, "w", encoding="utf-8") as f:
                    f.write(xml_data)
                log_access(pmcid, "success", f"Saved to {xml_path}")
            else:
                log_access(pmcid, "failed", "HTTP error or timeout")
                fail_count += 1
                continue

        # Extract text sections
        sections = extract_text_from_nxml(xml_data)
        if not sections:
            log_access(pmcid, "parse_error", "Could not parse XML")
            fail_count += 1
            continue

        # Rule-based extraction
        extraction = rule_based_extract(sections, pmcid)
        extraction["title"] = row.get("title", "")
        extraction["journal"] = row.get("journal", "")
        extraction["pubdate"] = row.get("pubdate", "")
        extraction["doi"] = row.get("doi", "")
        extractions.append(extraction)

        # Build text payload for LLM extraction
        clinical_text = build_extraction_prompt(sections, pmcid)
        text_payloads.append({
            "pmcid": pmcid,
            "title": row.get("title", ""),
            "journal": row.get("journal", ""),
            "pubdate": row.get("pubdate", ""),
            "clinical_text": clinical_text,
            "text_length": len(clinical_text)
        })

        success_count += 1

        if (i + 1) % 50 == 0:
            print(f"  Progress: {i+1}/{len(df_rows)} ({success_count} success, {fail_count} failed)")

    # Save rule-based extractions
    out_file = os.path.join(PROCESSED_DIR, "rule_based_extractions.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(extractions, f, indent=2, ensure_ascii=False)
    print(f"\nSaved {len(extractions)} rule-based extractions to {out_file}")

    # Save text payloads for LLM processing
    payload_file = os.path.join(PROCESSED_DIR, "llm_extraction_payloads.jsonl")
    with open(payload_file, "w", encoding="utf-8") as f:
        for payload in text_payloads:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(f"Saved {len(text_payloads)} text payloads to {payload_file}")

    # Summary statistics
    summary = {
        "processing_date": datetime.datetime.utcnow().isoformat(),
        "total_attempted": len(df_rows),
        "successful_extractions": success_count,
        "failed": fail_count,
        "success_rate": success_count / len(df_rows) if df_rows else 0,
    }
    with open(os.path.join(PROCESSED_DIR, "extraction_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*60}")
    print(f"EXTRACTION SUMMARY")
    print(f"{'='*60}")
    print(f"  Attempted: {len(df_rows)}")
    print(f"  Success: {success_count}")
    print(f"  Failed: {fail_count}")
    print(f"  Success rate: {summary['success_rate']:.1%}")

    return extractions


if __name__ == "__main__":
    import sys
    max_n = int(sys.argv[1]) if len(sys.argv) > 1 else None
    process_corpus(max_articles=max_n)
