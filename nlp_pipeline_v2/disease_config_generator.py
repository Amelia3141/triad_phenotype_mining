"""
Automatic disease configuration generator.

Given one or more disease names, queries open ontology APIs to build
a complete extraction config: condition terms, symptom patterns,
comorbidity patterns, and search terms. Users only need to provide
disease name(s); the backend resolves everything.

Data sources:
- EBI OLS4 (Ontology Lookup Service): disease name -> MONDO ID -> OMIM/ORPHA cross-refs
- HPO (Human Phenotype Ontology) via JAX API: disease ID -> phenotype annotations
- MONDO synonyms: canonical names and abbreviations for condition detection

Usage:
    from nlp_pipeline_v2.disease_config_generator import generate_config
    config = generate_config(["Ehlers-Danlos syndrome", "POTS", "mast cell activation syndrome"])
"""

import json
import os
import re
import time
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, List, Optional, Tuple, Any

from .pipeline_log import PipelineLog


# ── API endpoints ─────────────────────────────────────────────────────

EBI_OLS_SEARCH = "https://www.ebi.ac.uk/ols4/api/search"
EBI_OLS_TERMS = "https://www.ebi.ac.uk/ols4/api/ontologies/mondo/terms"
HPO_ANNOTATION = "https://ontology.jax.org/api/network/annotation"

RATE_LIMIT = 0.3  # seconds between API calls


# ── HPO term name to regex conversion ─────────────────────────────────

# Words to drop from HPO term names when building regex (too generic)
STOPWORDS = {
    "abnormal", "abnormality", "of", "the", "a", "an", "in", "with",
    "and", "or", "by", "due", "to", "type", "unspecified", "other",
    "morphology", "increased", "decreased",
}

# HPO categories to skip (not useful for case report extraction)
SKIP_CATEGORIES = {"Inheritance", "Clinical course"}

# HPO terms that are too generic to be useful as regex patterns
SKIP_TERMS = {
    "HP:0000006",  # Autosomal dominant inheritance
    "HP:0000007",  # Autosomal recessive inheritance
    "HP:0001417",  # X-linked inheritance
    "HP:0001419",  # X-linked recessive inheritance
    "HP:0003621",  # Juvenile onset
    "HP:0003581",  # Adult onset
    "HP:0003577",  # Congenital onset
    "HP:0011463",  # Childhood onset
    "HP:0410280",  # Pediatric onset
}


def _fetch_json(url: str, retries: int = 2) -> Optional[dict]:
    """Fetch JSON from URL with retry logic."""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read().decode("utf-8")
                if not data.strip():
                    return None
                return json.loads(data)
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError, OSError) as e:
            if attempt < retries:
                time.sleep(1)
                continue
            return None
        finally:
            time.sleep(RATE_LIMIT)


def _hpo_name_to_patterns(hpo_name: str) -> List[str]:
    """Convert an HPO phenotype name into regex search patterns.

    E.g., "Joint hypermobility" -> [r"joint\\s+hypermobil"]
          "Bruising susceptibility" -> [r"bruis\\s+susceptib", r"easy\\s+bruis"]
    """
    patterns = []

    # Clean the name
    name = hpo_name.lower().strip()

    # Remove parenthetical qualifiers
    name = re.sub(r"\s*\([^)]+\)", "", name)

    # Split into meaningful words. Split on ANY non-alphanumeric run (not just
    # whitespace) so hyphen/slash compounds become separate words, e.g.
    # "cafe-au-lait", "Kayser-Fleischer", "Aplasia/Hypoplasia",
    # "angiotensin-converting". Whitespace-only splitting left these as single
    # tokens that the stem matcher could never match.
    words = [w for w in re.split(r"[^a-z0-9]+", name)
             if w and w not in STOPWORDS and len(w) > 2]

    if not words:
        return []

    # Strategy 1: full phrase as flexible regex.
    # Both stems must be present, but up to one intervening word is allowed
    # (e.g. "aortic regurgitation" AND "aortic valve regurgitation" both match
    # "aorti ... regurg"). This keeps the pattern specific to the phenotype
    # while tolerating common modifiers.
    if len(words) >= 2:
        stems = []
        for w in words[:4]:  # max 4 words
            if len(w) > 6:
                stem = re.escape(w[:6])
            elif len(w) > 4:
                stem = re.escape(w[:5])
            else:
                stem = re.escape(w)
            # Allow the rest of the word after the stem (morphological variants
            # and the truncated remainder): "mitra" -> "mitra\w*" so it matches
            # "mitral", "regurg" -> "regurg\w*" so it matches "regurgitation".
            # Without this, a truncated first stem followed by \s+ can never
            # match the full word (e.g. "mitra\s+" never matches "mitral ").
            stems.append(stem + r"\w*")
        # Join stems with a separator that matches whitespace, hyphen or slash,
        # plus up to two optional intervening words. The intervening-word slack
        # absorbs both dropped stopwords ("dilatation OF AN abdominal artery")
        # and hyphen-joined infixes ("cafe-AU-lait"), while still requiring the
        # first and last anchor stems to be present (keeps it specific).
        sep = r"[\s/\-]+(?:\w+[\s/\-]+){0,2}"
        pat = sep.join(stems)
        patterns.append(pat)

    # Strategy 2: bare stem of a SINGLE-word phenotype only.
    # Multi-word phenotypes (e.g. "aortic regurgitation", "mitral
    # regurgitation") must NOT contribute a bare process-word stem like
    # "regurgi" or "prolaps" or "aneurys": those are shared across many
    # distinct phenotypes and cause cross-category false positives. Only emit
    # a standalone stem when the phenotype name is itself one distinctive word
    # (e.g. "scoliosis" -> "scolios", "keratoconus" -> "keratoc").
    if len(words) == 1 and len(words[0]) >= 8:
        patterns.append(re.escape(words[0][:7]))

    # Strategy 3: common alternative phrasings
    name_lower = hpo_name.lower()
    alt_map = {
        "bruising susceptibility": [r"easy\s+bruis", r"bruising\s+easily"],
        "hyperextensible skin": [r"skin\s+hyperextensib", r"stretchy\s+skin"],
        "joint hypermobility": [r"joint\s+hypermobil", r"hypermobil(?:e|ity)", r"double[\s-]?jointed"],
        "mitral valve prolapse": [r"mitral\s+valve\s+prolapse", r"\bmvp\b"],
        "syncope": [r"syncop", r"faint", r"loss\s+of\s+consciousness"],
        "tachycardia": [r"tachycardi", r"rapid\s+heart"],
        "palpitations": [r"palpitat"],
        "fatigue": [r"fatigu", r"exhausti", r"lethargy"],
        "nausea": [r"nausea", r"vomit"],
        "diarrhea": [r"diarr"],
        "constipation": [r"constipat"],
        "headache": [r"headache", r"migraine", r"cephalalgia"],
        "chronic pain": [r"chronic\s+pain", r"widespread\s+pain"],
        "myalgia": [r"myalgia", r"muscle\s+pain"],
        "arthralgia": [r"arthralgia", r"joint\s+pain"],
        "paresthesia": [r"paresthes", r"paraesthes", r"numbness", r"tingling"],
        "keratoconus": [r"keratoconus"],
        "scoliosis": [r"scoliosis"],
        "pneumothorax": [r"pneumothorax"],
        "gastroparesis": [r"gastroparesis", r"delayed\s+gastric\s+emptying"],
        "anaphylaxis": [r"anaphyla"],
        "urticaria": [r"urticar", r"hives"],
        "flushing": [r"flush(?:ing|ed)"],
        "dyspnea": [r"dyspn[oe]a", r"shortness\s+of\s+breath", r"breathless"],
        "dysautonomia": [r"dysautonomia", r"autonomic\s+(?:dysfunction|neuropathy)"],
    }
    for key, alt_pats in alt_map.items():
        if key in name_lower:
            patterns.extend(alt_pats)

    # Deduplicate
    seen = set()
    unique = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    return unique


def _make_slug(name: str) -> str:
    """Convert a phenotype name to a config-friendly slug.

    E.g., "Joint hypermobility" -> "joint_hypermobility"
    """
    slug = name.lower().strip()
    slug = re.sub(r"\s*\([^)]+\)", "", slug)  # remove parentheticals
    slug = re.sub(r"[^a-z0-9\s]", "", slug)
    slug = re.sub(r"\s+", "_", slug.strip())
    return slug[:50]


# ── Main API functions ────────────────────────────────────────────────

def search_disease(query: str, log: Optional[PipelineLog] = None) -> List[dict]:
    """Search EBI OLS for a disease by name. Returns list of MONDO matches.

    Each result has: mondo_id, label, description, synonyms, xrefs (OMIM, ORPHA).
    """
    params = urllib.parse.urlencode({
        "q": query,
        "ontology": "mondo",
        "rows": 10,
    })
    url = f"{EBI_OLS_SEARCH}?{params}"

    if log:
        log.step("Search EBI OLS for disease", query=query, url=url)

    data = _fetch_json(url)
    if not data:
        if log:
            log.warning(f"No response from EBI OLS for query: {query}")
        return []

    results = []
    docs = (data.get("response") or {}).get("docs") or []

    for doc in docs:
        mondo_id = doc.get("obo_id") or ""
        if not mondo_id.startswith("MONDO:"):
            continue

        results.append({
            "mondo_id": mondo_id,
            "label": doc.get("label") or "",
            "description": (doc.get("description") or [""])[0],
            "synonyms": (doc.get("exact_synonyms") or []) + (doc.get("related_synonyms") or []),
        })

    if log:
        log.result(f"Found {len(results)} MONDO matches", matches=[r["label"] for r in results])

    return results


def get_disease_xrefs(mondo_id: str, log: Optional[PipelineLog] = None) -> dict:
    """Get cross-references (OMIM, ORPHA) for a MONDO disease ID."""
    iri = f"http://purl.obolibrary.org/obo/{mondo_id.replace(':', '_')}"
    encoded_iri = urllib.parse.quote(iri, safe="")
    url = f"{EBI_OLS_TERMS}?iri={encoded_iri}"

    if log:
        log.step("Fetch cross-references from EBI OLS", mondo_id=mondo_id)

    data = _fetch_json(url)
    if not data:
        return {"omim": [], "orpha": [], "synonyms": []}

    # NB: use `... or []` rather than `.get(k, [])`. OLS returns these fields
    # explicitly as JSON null for some terms (e.g. Cystic fibrosis), and
    # dict.get returns that None when the key is present-but-null, which would
    # crash iteration. `or []`/`or {}` is null-safe and generalises to any term.
    terms = (data.get("_embedded") or {}).get("terms") or []
    if not terms:
        return {"omim": [], "orpha": [], "synonyms": []}

    term = terms[0]

    # Extract cross-references
    omim_ids = []
    orpha_ids = []
    xrefs = term.get("obo_xref") or []
    for xref in xrefs:
        db = xref.get("database", "")
        xid = xref.get("id", "")
        if db == "OMIM" and xid:
            omim_ids.append(f"OMIM:{xid}")
        elif db == "Orphanet" and xid:
            orpha_ids.append(f"ORPHA:{xid}")

    # Also extract from annotation field
    annotations = term.get("annotation") or {}
    for dbxref in annotations.get("database_cross_reference") or []:
        if dbxref.startswith("OMIM:") and dbxref not in omim_ids:
            omim_ids.append(dbxref)
        elif dbxref.startswith("Orphanet:"):
            orpha_id = f"ORPHA:{dbxref.split(':')[1]}"
            if orpha_id not in orpha_ids:
                orpha_ids.append(orpha_id)

    # Synonyms
    synonyms = term.get("synonyms") or []

    result = {"omim": omim_ids, "orpha": orpha_ids, "synonyms": synonyms}

    if log:
        log.result(
            f"Cross-references for {mondo_id}",
            omim_ids=omim_ids, orpha_ids=orpha_ids,
            synonym_count=len(synonyms),
        )

    return result


def get_hpo_phenotypes(disease_id: str, log: Optional[PipelineLog] = None) -> dict:
    """Fetch HPO phenotype annotations for a disease (OMIM or ORPHA ID).

    Returns dict with categories as keys, each containing list of phenotypes
    with HPO IDs, names, and frequency data.
    """
    url = f"{HPO_ANNOTATION}/{disease_id}"

    if log:
        log.step("Fetch HPO phenotype annotations", disease_id=disease_id, url=url)

    data = _fetch_json(url)
    if not data:
        if log:
            log.warning(f"No HPO data for {disease_id}")
        return {}

    categories = data.get("categories", {})
    disease_info = data.get("disease", {})
    genes = data.get("genes", [])

    if log:
        total_phenotypes = sum(len(v) for v in categories.values())
        log.result(
            f"HPO annotations for {disease_info.get('name', disease_id)}",
            total_phenotypes=total_phenotypes,
            categories=list(categories.keys()),
            genes=[g.get("name") for g in genes],
        )

    return {
        "disease": disease_info,
        "categories": categories,
        "genes": genes,
    }


def build_symptom_config(hpo_data_list: List[dict],
                         log: Optional[PipelineLog] = None) -> dict:
    """Convert HPO phenotype annotations into symptom pattern config.

    Merges phenotypes from multiple diseases, deduplicates by HPO ID,
    and generates regex patterns for each.
    """
    if log:
        log.section("Symptom Pattern Generation")
        log.step("Converting HPO phenotypes to regex patterns")

    # Merge all phenotypes, dedup by HPO ID
    all_phenotypes = {}  # hpo_id -> {name, category, sources, frequency}

    for hpo_data in hpo_data_list:
        categories = hpo_data.get("categories", {})
        disease_name = hpo_data.get("disease", {}).get("name", "unknown")

        for category, phenotypes in categories.items():
            if category in SKIP_CATEGORIES:
                continue

            for pheno in phenotypes:
                hpo_id = pheno.get("id", "")
                if hpo_id in SKIP_TERMS:
                    continue

                if hpo_id not in all_phenotypes:
                    all_phenotypes[hpo_id] = {
                        "name": pheno.get("name", ""),
                        "hpo_id": hpo_id,
                        "category": category,
                        "sources": [disease_name],
                        "frequency": pheno.get("metadata", {}).get("frequency", ""),
                    }
                else:
                    if disease_name not in all_phenotypes[hpo_id]["sources"]:
                        all_phenotypes[hpo_id]["sources"].append(disease_name)

    if log:
        log.result(
            f"Merged phenotypes from {len(hpo_data_list)} diseases",
            unique_phenotypes=len(all_phenotypes),
        )

    # Convert to symptom patterns grouped by category
    symptom_patterns = {}
    pattern_log_rows = []

    for hpo_id, pheno in sorted(all_phenotypes.items(), key=lambda x: x[1]["category"]):
        slug = _make_slug(pheno["name"])
        patterns = _hpo_name_to_patterns(pheno["name"])

        if not patterns:
            continue

        # Use category as grouping, but make the key unique
        if slug in symptom_patterns:
            slug = f"{slug}_{hpo_id.replace(':', '_').lower()}"

        symptom_patterns[slug] = {
            "hpo_id": hpo_id,
            "hpo_name": pheno["name"],
            "category": pheno["category"],
            "patterns": patterns,
            "source_diseases": pheno["sources"],
            "frequency": pheno["frequency"],
        }

        pattern_log_rows.append([slug, hpo_id, pheno["name"], len(patterns)])

    if log:
        log.result(
            f"Generated symptom patterns",
            symptom_categories=len(symptom_patterns),
            total_patterns=sum(len(v["patterns"]) for v in symptom_patterns.values()),
        )
        # Log a sample
        log.table(
            ["Slug", "HPO ID", "Name", "Patterns"],
            pattern_log_rows[:20],
        )
        if len(pattern_log_rows) > 20:
            log.detail(f"... and {len(pattern_log_rows) - 20} more")

    return symptom_patterns


def build_condition_terms(disease_results: List[dict],
                          log: Optional[PipelineLog] = None) -> dict:
    """Build condition_terms config from MONDO search results.

    Uses disease names and synonyms to build detection patterns.
    """
    if log:
        log.section("Condition Term Generation")

    condition_terms = {}

    for disease in disease_results:
        label = disease.get("label", "")
        mondo_id = disease.get("mondo_id", "")
        synonyms = disease.get("synonyms", [])
        xrefs = disease.get("xrefs", {})

        # Build patterns from name and synonyms
        patterns = []

        # Main name as flexible regex
        name_lower = label.lower()
        name_escaped = re.escape(name_lower)
        # Allow hyphen/space variation
        name_flex = name_escaped.replace(r"\ ", r"[\s-]*").replace(r"\-", r"[\s-]*")
        patterns.append(name_flex)

        # Add abbreviation synonyms as word-boundary patterns
        for syn in synonyms:
            syn_clean = syn.strip()
            if len(syn_clean) <= 6 and syn_clean.isupper():
                # Abbreviation: match as whole word
                patterns.append(r"\b" + re.escape(syn_clean.lower()) + r"\b")
            elif len(syn_clean) > 3:
                # Longer synonym: flexible match
                syn_escaped = re.escape(syn_clean.lower())
                syn_flex = syn_escaped.replace(r"\ ", r"[\s-]*").replace(r"\-", r"[\s-]*")
                patterns.append(syn_flex)

        # Deduplicate
        seen = set()
        unique_patterns = []
        for p in patterns:
            if p not in seen:
                seen.add(p)
                unique_patterns.append(p)

        slug = _make_slug(label)
        condition_terms[slug] = {
            "canonical": label,
            "mondo_id": mondo_id,
            "patterns": unique_patterns[:15],  # cap at 15 patterns
        }

        if log:
            log.step(
                f"Condition: {label}",
                mondo_id=mondo_id,
                patterns=unique_patterns[:10],
                synonym_count=len(synonyms),
            )

    return condition_terms


# ── Candidate selection ───────────────────────────────────────────────

# Generic MONDO-label qualifiers that indicate a term is NOT the main disease
# the user means (a gene locus, an animal form, a complication, a subtype).
# Disease-agnostic: these tokens carry the same meaning across all diseases.
_QUALIFIER_PENALTIES = {
    "susceptibility": 60, "modifier": 60, "somatic": 40,
    "resistance to": 40, "response to": 40, "complementation group": 50,
}
_SUBTYPE_TOKENS = {
    "juvenile", "neonatal", "infantile", "childhood", "adult", "familial",
    "atypical", "transient", "acquired", "isolated", "syndromic",
}
_ANIMAL_TOKENS = {
    "dog", "cat", "mouse", "rat", "canine", "feline", "bovine", "murine",
    "equine", "porcine",
}


def _norm_label(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def score_candidate(query: str, label: str) -> float:
    """Score how well a MONDO candidate label matches the queried disease.

    Higher is better. Rewards exact/substring/token overlap; penalises
    generic 'not the main disease' qualifiers (susceptibility loci, animal
    forms, named subtypes, trailing type/locus numerals). Disease-agnostic.
    """
    q = _norm_label(query)
    lab = _norm_label(label)
    if not lab:
        return -999.0
    qtok, ltok = set(q.split()), set(lab.split())

    score = 0.0
    if lab == q:
        score += 100
    elif q and (q in lab or lab in q):
        score += 45
    if qtok and ltok:
        score += 25 * len(qtok & ltok) / len(qtok | ltok)

    for tok, pen in _QUALIFIER_PENALTIES.items():
        if tok in lab:
            score -= pen
    for tok in _ANIMAL_TOKENS:
        if tok in ltok:
            score -= 80
    for tok in _SUBTYPE_TOKENS:
        if tok in ltok and tok not in qtok:
            score -= 20
    # trailing numerals (e.g. "..., type 3", "susceptibility to, 11") not asked for
    if re.search(r"\b\d+$", lab) and not re.search(r"\d", q):
        score -= 15
    # prefer the most canonical (fewest extra words) term
    score -= 1.5 * max(0, len(ltok) - len(qtok))
    return score


def rank_candidates(query: str, candidates: List[dict], has_hpo_fn=None) -> List[dict]:
    """Rank MONDO candidates best-first for a query.

    Primary signal is label quality (score_candidate). If has_hpo_fn is given,
    candidates whose cross-references actually resolve to HPO phenotype
    annotations are boosted, so a resolvable exact match is preferred over an
    equally-named term with no phenotype data.
    """
    scored = []
    for c in candidates:
        s = score_candidate(query, c.get("label", ""))
        if has_hpo_fn is not None:
            try:
                if has_hpo_fn(c):
                    s += 50
            except Exception:
                pass
        scored.append((s, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored]


# ── Main entry point ──────────────────────────────────────────────────

def _resolve_diseases_to_patterns(
    disease_names: List[str],
    log: Optional[PipelineLog] = None,
    label: str = "disease",
    max_candidates: int = 4,
) -> List[dict]:
    """Resolve a list of disease names through MONDO and return the best match
    per name.

    Each result has: mondo_id, label, synonyms, xrefs. Selection ranks the top
    candidates by label quality and HPO resolvability rather than blindly
    taking the top OLS text-relevance hit (which is frequently a susceptibility
    locus, animal form, or wrong subtype). Used by both the primary disease and
    comorbidity resolution paths.
    """
    results = []
    for name in disease_names:
        if log:
            log.step(f"Resolving {label}: {name}")
        matches = search_disease(name, log=log)
        if not matches:
            if log:
                log.warning(f"No MONDO match for '{name}'")
            continue

        candidates = matches[:max_candidates]
        # Rank by LABEL quality only. This alone resolves the common failure
        # cases (susceptibility loci, wrong subtypes, animal forms) via exact-
        # match bonus + qualifier penalties, and needs NO per-candidate network
        # calls, so config generation stays fast. HPO resolvability is handled
        # lazily as a fallback in generate_config (only if the best term has no
        # HPO annotations), rather than probing every candidate up front.
        ranked = rank_candidates(name, candidates)
        best = ranked[0]
        if "xrefs" not in best:
            best["xrefs"] = get_disease_xrefs(best["mondo_id"], log=log)
        # Alternates keep their lazily-fetched xrefs (fetched only if needed).
        best["_alternates"] = ranked[1:]
        best["_hpo_memo"] = {}
        if log:
            log.decision(
                f"Selected: {best['label']} ({best['mondo_id']})",
                reason=f"Best-ranked MONDO match for '{name}' "
                       f"(of {len(candidates)} candidates)",
            )
        best["synonyms"] = best.get("synonyms", []) + best["xrefs"].get("synonyms", [])
        results.append(best)
    return results


def generate_config(
    disease_names: List[str],
    comorbidity_names: Optional[List[str]] = None,
    output_path: Optional[str] = None,
    log_path: Optional[str] = None,
    include_drug_defaults: bool = True,
) -> dict:
    """Generate a complete extraction config from disease names.

    This is the main entry point. Users provide disease name(s) and
    get a complete config.json back.

    Args:
        disease_names: List of disease names (e.g., ["Ehlers-Danlos syndrome",
                       "postural orthostatic tachycardia syndrome"]).
        comorbidity_names: Optional list of known comorbidities to detect.
                           Each is resolved through MONDO for synonym coverage.
                           If None, comorbidity_patterns will be empty.
        output_path: Where to write config.json (optional).
        log_path: Where to write the reproducibility log (optional).
        include_drug_defaults: Include the default universal drug list.

    Returns:
        Complete config dict ready for the NLP pipeline.
    """
    # Set up logging
    log = None
    if log_path:
        log = PipelineLog(log_path, title=f"Config Generation: {', '.join(disease_names)}")

    if log:
        log.section("Disease Resolution")
        log.data_source(
            "EBI OLS4 (Ontology Lookup Service)",
            "https://www.ebi.ac.uk/ols4/",
            version="OLS4",
        )
        log.data_source(
            "HPO (Human Phenotype Ontology)",
            "https://hpo.jax.org",
        )

    # Step 1: Resolve primary diseases through MONDO
    all_disease_results = _resolve_diseases_to_patterns(
        disease_names, log=log, label="primary disease",
    )

    # Step 2: Fetch HPO phenotype annotations for each resolved disease.
    # If the selected (best-label) disease has no HPO annotations, fall back to
    # its ranked alternates so a resolvable sibling term still yields phenotypes.
    all_hpo_data = []
    fetched_ids = set()

    def _collect_hpo(disease) -> bool:
        # Alternates have xrefs fetched lazily (only when we actually fall back).
        if "xrefs" not in disease:
            disease["xrefs"] = get_disease_xrefs(disease["mondo_id"], log=log)
        memo = disease.get("_hpo_memo", {})
        xrefs = disease.get("xrefs", {})
        found = False
        for xid in xrefs.get("omim", []) + xrefs.get("orpha", []):
            if xid in fetched_ids:
                found = True
                continue
            hpo = memo.get(xid) or get_hpo_phenotypes(xid, log=log)
            if (hpo or {}).get("categories"):
                all_hpo_data.append(hpo)
                fetched_ids.add(xid)
                found = True
        return found

    for disease in all_disease_results:
        if _collect_hpo(disease):
            continue
        # No HPO for the chosen term: try ranked alternates.
        recovered = False
        for alt in disease.get("_alternates", []):
            if _collect_hpo(alt):
                if log:
                    log.decision(
                        f"HPO recovered from alternate: {alt.get('label', '?')} "
                        f"({alt.get('mondo_id', '?')})",
                        reason=f"Selected term '{disease.get('label','?')}' "
                               f"had no HPO annotations",
                    )
                recovered = True
                break
        if not recovered and log:
            log.warning(
                f"No HPO annotations found for {disease.get('label', '?')} "
                f"or its alternates"
            )

    # Step 3: Build condition terms from primary diseases
    condition_terms = build_condition_terms(all_disease_results, log=log)

    # Step 4: Build symptom patterns from HPO
    symptom_patterns = build_symptom_config(all_hpo_data, log=log)

    # Step 5: Build comorbidity patterns (if comorbidity names provided)
    comorbidity_patterns = {}
    if comorbidity_names:
        if log:
            log.section("Comorbidity Resolution")
            log.detail(
                f"Resolving {len(comorbidity_names)} comorbidities through MONDO"
            )
        comorb_results = _resolve_diseases_to_patterns(
            comorbidity_names, log=log, label="comorbidity",
        )
        # Reuse build_condition_terms to get synonym-based regex patterns
        comorbidity_patterns = build_condition_terms(comorb_results, log=log)
        if log:
            log.result(
                "Comorbidity patterns generated",
                comorbidities=len(comorbidity_patterns),
                total_patterns=sum(
                    len(v.get("patterns", []))
                    for v in comorbidity_patterns.values()
                ),
            )

    # Step 6: Assemble config
    if log:
        log.section("Config Assembly")

    # Build search terms from resolved disease names + synonyms
    search_terms = list(disease_names)  # start with user-provided names
    for disease in all_disease_results:
        label = disease.get("label", "")
        if label and label not in search_terms:
            search_terms.append(label)
        for syn in disease.get("synonyms", []):
            syn_clean = syn.strip()
            # Only include reasonably short synonyms (skip long descriptions)
            if syn_clean and len(syn_clean) < 60 and syn_clean not in search_terms:
                search_terms.append(syn_clean)

    config = {
        "schema_version": "3.0",
        "description": (
            f"Auto-generated extraction config for: {', '.join(disease_names)}. "
            f"Symptom patterns derived from HPO phenotype annotations. "
            f"Comorbidity patterns from MONDO synonyms. "
            f"Generated by disease_config_generator.py."
        ),
        "source_diseases": disease_names,
        "search_terms": search_terms,
        "condition_terms": condition_terms,
        "symptom_patterns": symptom_patterns,
        "comorbidity_patterns": comorbidity_patterns,
        "drug_classes": _get_default_drug_classes() if include_drug_defaults else {},
        "measurement_patterns": _get_default_measurement_patterns(),
        "negation_triggers": {
            "pre": [
                "no", "no evidence of", "denies", "denied", "negative for",
                "without", "absence of", "ruled out", "no signs of",
                "no history of", "not consistent with", "unlikely",
                "did not have", "does not have", "was not", "were not",
                "no significant", "unremarkable", "normal",
                "within normal limits", "failed to demonstrate",
                "no indication of", "not suggestive of",
            ],
            "post": [
                "was ruled out", "was negative", "was absent",
                "was not found", "was not detected", "was not identified",
                "was excluded", "were absent", "were negative",
            ],
        },
        "section_blacklist": [
            "references", "bibliography", "acknowledgements", "acknowledgments",
            "conflict of interest", "conflicts of interest", "funding",
            "author contributions", "supplementary", "ethics statement",
            "data availability", "competing interests",
        ],
    }

    if log:
        log.result(
            "Config assembled",
            conditions=len(config["condition_terms"]),
            symptom_categories=len(config["symptom_patterns"]),
            comorbidities=len(config["comorbidity_patterns"]),
            drug_classes=len(config["drug_classes"]),
            total_drugs=sum(len(v) for v in config["drug_classes"].values()),
        )

    # Write config
    if output_path:
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        if log:
            log.step(f"Config written to {output_path}")

    if log:
        log.close()

    return config


# ── Default drug classes (universal, not disease-specific) ────────────

def _get_default_drug_classes() -> dict:
    """Return a universal base drug list covering common medications.

    These are not disease-specific; they cover the most commonly
    prescribed drugs across multiple specialties. Users can extend
    via config if needed.
    """
    return {
        "beta_blockers": [
            "propranolol", "metoprolol", "atenolol", "bisoprolol",
            "nadolol", "carvedilol", "nebivolol", "labetalol", "ivabradine",
        ],
        "vasoconstrictors_volume": [
            "midodrine", "droxidopa", "fludrocortisone", "desmopressin",
            "octreotide",
        ],
        "mast_cell_stabilisers": [
            "cromolyn", "cromoglicate", "ketotifen", "sodium cromoglycate",
        ],
        "antihistamines": [
            "cetirizine", "loratadine", "fexofenadine", "diphenhydramine",
            "hydroxyzine", "ranitidine", "famotidine", "montelukast",
        ],
        "analgesics": [
            "paracetamol", "acetaminophen", "ibuprofen", "naproxen",
            "celecoxib", "pregabalin", "gabapentin", "duloxetine",
            "amitriptyline", "nortriptyline",
        ],
        "gi_drugs": [
            "omeprazole", "lansoprazole", "pantoprazole", "ondansetron",
            "domperidone", "metoclopramide", "loperamide",
        ],
        "autonomic": [
            "pyridostigmine", "clonidine", "methyldopa", "ephedrine",
        ],
        "corticosteroids": [
            "hydrocortisone", "methylprednisolone", "prednisone",
            "prednisolone", "dexamethasone",
        ],
        "emergency": [
            "epinephrine", "adrenaline",
        ],
        "supplements": [
            "salt tablets", "sodium chloride", "vitamin c", "vitamin d",
            "magnesium", "iron", "coenzyme q10",
        ],
        "anaesthetics": [
            "lidocaine", "bupivacaine", "ropivacaine", "propofol",
            "ketamine", "sevoflurane", "desflurane",
        ],
    }


def _get_default_measurement_patterns() -> dict:
    """Return universal clinical measurement patterns."""
    return {
        "heart_rate": {
            "patterns": [
                r"(?:heart\s+rate|hr|pulse)\s*(?:of\s*|was\s*|:|=)?\s*(\d{2,3})\s*(?:bpm|beats|/min)"
            ],
            "unit": "bpm",
        },
        "blood_pressure": {
            "patterns": [
                r"(?:blood\s+pressure|bp)\s*(?:of\s*|was\s*|:|=)?\s*(\d{2,3})\s*/\s*(\d{2,3})\s*(?:mmhg)?",
                r"(\d{2,3})\s*/\s*(\d{2,3})\s*mmhg",
            ],
            "unit": "mmHg",
        },
        "temperature": {
            "patterns": [
                r"(?:temperature|temp)\s*(?:of\s*|was\s*|:|=)?\s*(\d{2,3}(?:\.\d)?)\s*(?:c|f|celsius|fahrenheit|degrees)",
            ],
            "unit": "degrees",
        },
    }


# ── CLI entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate extraction config from disease names"
    )
    parser.add_argument(
        "diseases", nargs="+",
        help="Disease names (e.g., 'Ehlers-Danlos syndrome' 'POTS')",
    )
    parser.add_argument(
        "--output", "-o", default="config_generated.json",
        help="Output config JSON path",
    )
    parser.add_argument(
        "--log", "-l", default="config_generation_log.md",
        help="Reproducibility log path",
    )

    args = parser.parse_args()

    config = generate_config(
        args.diseases,
        output_path=args.output,
        log_path=args.log,
    )

    print(f"\nConfig generated: {len(config['condition_terms'])} conditions, "
          f"{len(config['symptom_patterns'])} symptom categories")
