#!/usr/bin/env python3
"""
Phase 6: Download and extract full-text for adjacent-condition PMCIDs.

Takes the 683 new PMCIDs from adjacent condition queries (dysautonomia,
orthostatic intolerance, autonomic dysfunction, vasovagal syncope,
idiopathic anaphylaxis, HAT, histamine intolerance, JHS, HSD) and
runs the same extraction pipeline as 03_fulltext_extract.py.

Outputs:
- data/raw/fulltext/{PMCID}.xml for each new article
- data/processed/adjacent_extractions.json
- data/processed/adjacent_extraction_payloads.jsonl
"""

import csv
import json
import os
import re
import sys
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

PMC_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
RATE_LIMIT = 0.4

os.makedirs(os.path.join(RAW_DIR, "fulltext"), exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

# Import extraction functions from 03
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
from importlib import import_module
# We'll just duplicate the key functions to avoid import issues

def log_access(pmcid, status, notes=""):
    log_file = os.path.join(LOG_DIR, "fulltext_access_log.jsonl")
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "pmcid": pmcid,
        "status": status,
        "notes": notes,
        "batch": "adjacent_conditions"
    }
    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


def fetch_pmc_fulltext(pmcid):
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
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError:
        return None
    article = root.find(".//article")
    if article is None:
        article = root
    sections = {}
    title_el = article.find(".//article-title")
    if title_el is not None:
        sections["title"] = "".join(title_el.itertext()).strip()
    abstract_el = article.find(".//abstract")
    if abstract_el is not None:
        sections["abstract"] = "".join(abstract_el.itertext()).strip()
    body = article.find(".//body")
    if body is not None:
        for sec in body.findall(".//sec"):
            sec_title_el = sec.find("title")
            sec_title = "".join(sec_title_el.itertext()).strip() if sec_title_el is not None else "untitled"
            paragraphs = []
            for p in sec.findall(".//p"):
                text = "".join(p.itertext()).strip()
                if text:
                    paragraphs.append(text)
            if paragraphs:
                sections[sec_title.lower()] = "\n\n".join(paragraphs)
    if len(sections) <= 2:
        if body is not None:
            all_text = "".join(body.itertext()).strip()
            if all_text:
                sections["body"] = all_text
    return sections


def build_extraction_prompt(sections, pmcid):
    priority_keys = [
        "case", "case report", "case presentation", "case description",
        "clinical presentation", "patient", "history", "clinical features",
        "results", "findings", "abstract"
    ]
    clinical_text_parts = []
    if "abstract" in sections:
        clinical_text_parts.append(f"[ABSTRACT]\n{sections['abstract']}")
    for key in priority_keys:
        for sec_name, sec_text in sections.items():
            if key in sec_name.lower() and sec_text not in [s.split("\n", 1)[-1] if "\n" in s else s for s in clinical_text_parts]:
                clinical_text_parts.append(f"[{sec_name.upper()}]\n{sec_text}")
    for sec_name, sec_text in sections.items():
        if "discussion" in sec_name.lower():
            clinical_text_parts.append(f"[{sec_name.upper()}]\n{sec_text}")
            break
    if len(clinical_text_parts) <= 1:
        for sec_name, sec_text in sections.items():
            tag = f"[{sec_name.upper()}]\n{sec_text}"
            if tag not in clinical_text_parts:
                clinical_text_parts.append(tag)
    return "\n\n---\n\n".join(clinical_text_parts)


def rule_based_extract(sections, pmcid):
    full_text = " ".join(sections.values()).lower()
    full_text_norm = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u00ad\u2212]", "-", full_text)

    result = {
        "pmcid": pmcid,
        "extraction_method": "rule_based_v2",
        "extraction_date": datetime.datetime.utcnow().isoformat(),
    }

    # Age extraction
    age_patterns = [
        r"(\d{1,3})[\s-]*year[\s-]*old",
        r"age[d]?\s*(?:of\s*)?(\d{1,3})\b",
        r"(\d{1,3})[\s-]*yo\b",
        r"a\s+(\d{1,3})[\s-]*year",
        r"(?:patient|woman|man|female|male|girl|boy),?\s*(?:aged?\s*)?(\d{1,3})[,\s]",
        r"(\d{1,3})\s*years?\s*of\s*age",
        r"(\d{1,3})[\s-]*month[\s-]*old",
        r"at\s+(?:the\s+)?age\s+(?:of\s+)?(\d{1,3})",
    ]
    for pat in age_patterns:
        m = re.search(pat, full_text_norm)
        if m:
            age = int(m.group(1))
            # Filter out criteria thresholds
            start = max(0, m.start() - 30)
            prefix = full_text_norm[start:m.start()]
            if re.search(r"[>≥<≤]|at least|minimum|threshold|eligib|criteria", prefix):
                continue
            if "month" in pat and 0 < age < 240:
                result["age_at_presentation"] = round(age / 12, 1)
                result["age_unit_original"] = "months"
                break
            elif 0 < age < 120:
                result["age_at_presentation"] = age
                break

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

    # Sex extraction
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

    # Article type
    num_patients_mentioned = []
    for m_iter in re.finditer(r"(\d+)\s*(?:patients|participants|subjects|individuals|cases)", full_text_norm):
        n = int(m_iter.group(1))
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

    # Adjacent condition detection (new for this batch)
    result["dysautonomia_mentioned"] = bool(re.search(r"dysautonomia|autonomic\s+dysfunction|autonomic\s+failure|autonomic\s+neuropathy", full_text_norm))
    result["orthostatic_intolerance_mentioned"] = bool(re.search(r"orthostatic\s+intolerance|orthostatic\s+hypotension", full_text_norm))
    result["vasovagal_mentioned"] = bool(re.search(r"vasovagal|neurocardiogenic\s+syncop", full_text_norm))
    result["ist_mentioned"] = bool(re.search(r"inappropriate\s+sinus\s+tachycardia", full_text_norm))
    result["histamine_intolerance_mentioned"] = bool(re.search(r"histamine\s+intolerance|diamine\s+oxidase|dao\s+deficiency", full_text_norm))
    result["hat_mentioned"] = bool(re.search(r"hereditary\s+alpha\s+tryptasemia|alpha\s+tryptasemia|\bhat\b.*tryptas", full_text_norm))
    result["jhs_mentioned"] = bool(re.search(r"\bjhs\b|joint\s+hypermobility\s+syndrome", full_text_norm))
    result["hsd_mentioned"] = bool(re.search(r"\bhsd\b|hypermobility\s+spectrum\s+disorder", full_text_norm))
    result["mastocytosis_mentioned"] = bool(re.search(r"mastocytosis|systemic\s+mastocytosis|cutaneous\s+mastocytosis", full_text_norm))

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

    # Symptoms
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

    # Terminology
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
        "orthostatic intolerance": r"orthostatic\s+intolerance",
        "orthostatic hypotension": r"orthostatic\s+hypotension",
        "vasovagal syncope": r"vasovagal\s+syncop",
        "autonomic dysfunction": r"autonomic\s+dysfunction",
        "histamine intolerance": r"histamine\s+intolerance",
    }
    terms_used = []
    for term_name, pat in terminology_patterns.items():
        if re.search(pat, full_text_norm):
            terms_used.append(term_name)
    result["terminology_used"] = terms_used

    # Number of patients
    if re.search(r"case\s*series|(\d+)\s*patients|(\d+)\s*cases", full_text_norm):
        m = re.search(r"(\d+)\s*(?:patients|cases|subjects)", full_text_norm)
        if m and int(m.group(1)) > 1:
            result["num_patients"] = int(m.group(1))
        else:
            result["num_patients"] = 1
    else:
        result["num_patients"] = 1

    return result


def build_adjacent_metadata():
    """Combine all adjacent metadata CSVs and filter to new PMCIDs only."""
    with open(os.path.join(RAW_DIR, "adjacent_new_pmcids.json")) as f:
        new_pmcids = set(json.load(f))

    adjacent_files = [
        ("dysautonomia", "adjacent_dysautonomia_metadata.csv"),
        ("orthostatic_intolerance", "adjacent_orthostatic_intolerance_metadata.csv"),
        ("autonomic_dysfunction", "adjacent_autonomic_dysfunction_metadata.csv"),
        ("vasovagal_syncope", "adjacent_vasovagal_syncope_metadata.csv"),
        ("idiopathic_anaphylaxis", "adjacent_idiopathic_anaphylaxis_metadata.csv"),
        ("HAT", "adjacent_HAT_metadata.csv"),
        ("histamine_intolerance", "adjacent_histamine_intolerance_metadata.csv"),
        ("JHS", "adjacent_JHS_metadata.csv"),
        ("HSD", "adjacent_HSD_metadata.csv"),
    ]

    all_rows = {}
    source_queries = {}  # Track which query each PMCID came from

    for query_name, filename in adjacent_files:
        filepath = os.path.join(RAW_DIR, filename)
        if not os.path.exists(filepath):
            print(f"  Warning: {filename} not found, skipping")
            continue
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pmcid = row.get("pmcid", "")
                if pmcid in new_pmcids and pmcid not in all_rows:
                    all_rows[pmcid] = row
                    source_queries[pmcid] = query_name
                elif pmcid in new_pmcids and pmcid in source_queries:
                    # Track multiple source queries
                    source_queries[pmcid] += f"; {query_name}"

    print(f"Adjacent metadata: {len(all_rows)} new PMCIDs matched from {len(new_pmcids)} expected")

    # Save combined adjacent metadata
    combined_path = os.path.join(RAW_DIR, "adjacent_combined_metadata.csv")
    if all_rows:
        fieldnames = list(list(all_rows.values())[0].keys()) + ["source_query"]
        with open(combined_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for pmcid, row in all_rows.items():
                row["source_query"] = source_queries.get(pmcid, "")
                writer.writerow(row)
        print(f"Saved combined adjacent metadata: {combined_path}")

    return all_rows, source_queries


def process_adjacent_corpus(max_articles=None, resume_from=0):
    """Download and extract adjacent condition articles."""

    all_rows, source_queries = build_adjacent_metadata()

    items = list(all_rows.items())
    if resume_from > 0:
        items = items[resume_from:]
    if max_articles:
        items = items[:max_articles]

    print(f"\nProcessing {len(items)} adjacent articles (starting from index {resume_from})...")

    extractions = []
    text_payloads = []
    success_count = 0
    fail_count = 0
    skip_count = 0

    for i, (pmcid, row) in enumerate(items):
        xml_path = os.path.join(RAW_DIR, "fulltext", f"{pmcid}.xml")

        if os.path.exists(xml_path):
            with open(xml_path, "r", encoding="utf-8") as f:
                xml_data = f.read()
            skip_count += 1
        else:
            if (i + 1) % 50 == 0 or i == 0:
                print(f"  [{resume_from + i + 1}/{resume_from + len(items)}] Fetching {pmcid}...")
            xml_data = fetch_pmc_fulltext(pmcid)
            time.sleep(RATE_LIMIT)

            if xml_data:
                with open(xml_path, "w", encoding="utf-8") as f:
                    f.write(xml_data)
                log_access(pmcid, "success", f"Adjacent batch. Source: {source_queries.get(pmcid, '')}")
            else:
                log_access(pmcid, "failed", f"Adjacent batch. Source: {source_queries.get(pmcid, '')}")
                fail_count += 1
                continue

        sections = extract_text_from_nxml(xml_data)
        if not sections:
            log_access(pmcid, "parse_error", "Could not parse XML")
            fail_count += 1
            continue

        extraction = rule_based_extract(sections, pmcid)
        extraction["title"] = row.get("title", "")
        extraction["journal"] = row.get("journal", "")
        extraction["pubdate"] = row.get("pubdate", "")
        extraction["doi"] = row.get("doi", "")
        extraction["source_query"] = source_queries.get(pmcid, "")
        extractions.append(extraction)

        clinical_text = build_extraction_prompt(sections, pmcid)
        text_payloads.append({
            "pmcid": pmcid,
            "title": row.get("title", ""),
            "journal": row.get("journal", ""),
            "pubdate": row.get("pubdate", ""),
            "clinical_text": clinical_text,
            "text_length": len(clinical_text),
            "source_query": source_queries.get(pmcid, "")
        })

        success_count += 1

        if (i + 1) % 100 == 0:
            print(f"  Progress: {resume_from + i + 1}/{resume_from + len(items)} ({success_count} success, {fail_count} failed, {skip_count} cached)")
            # Save intermediate results
            _save_results(extractions, text_payloads, suffix="_partial")

    _save_results(extractions, text_payloads, suffix="")

    print(f"\n{'='*60}")
    print(f"ADJACENT EXTRACTION SUMMARY")
    print(f"{'='*60}")
    print(f"  Attempted: {len(items)}")
    print(f"  Success: {success_count}")
    print(f"  Failed: {fail_count}")
    print(f"  From cache: {skip_count}")
    print(f"  Success rate: {success_count / len(items) * 100:.1f}%" if items else "  N/A")

    # Quick stats
    if extractions:
        eds_count = sum(1 for e in extractions if e.get("eds_mentioned"))
        pots_count = sum(1 for e in extractions if e.get("pots_mentioned"))
        mcas_count = sum(1 for e in extractions if e.get("mcas_mentioned"))
        dysaut_count = sum(1 for e in extractions if e.get("dysautonomia_mentioned"))
        oi_count = sum(1 for e in extractions if e.get("orthostatic_intolerance_mentioned"))
        print(f"\n  Condition mentions in adjacent articles:")
        print(f"    EDS: {eds_count}")
        print(f"    POTS: {pots_count}")
        print(f"    MCAS: {mcas_count}")
        print(f"    Dysautonomia: {dysaut_count}")
        print(f"    Orthostatic intolerance: {oi_count}")

    return extractions


def _save_results(extractions, text_payloads, suffix=""):
    out_file = os.path.join(PROCESSED_DIR, f"adjacent_extractions{suffix}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(extractions, f, indent=2, ensure_ascii=False)

    payload_file = os.path.join(PROCESSED_DIR, f"adjacent_extraction_payloads{suffix}.jsonl")
    with open(payload_file, "w", encoding="utf-8") as f:
        for payload in text_payloads:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    if not suffix:
        print(f"\nSaved {len(extractions)} extractions to {out_file}")
        print(f"Saved {len(text_payloads)} text payloads to {payload_file}")


if __name__ == "__main__":
    max_n = int(sys.argv[1]) if len(sys.argv) > 1 else None
    resume = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    process_adjacent_corpus(max_articles=max_n, resume_from=resume)
