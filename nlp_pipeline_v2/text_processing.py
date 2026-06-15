"""
Text processing utilities: sentence segmentation, section detection,
reference stripping, and publication metadata extraction.

These are the foundation for context-aware extraction.
"""

import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple, Optional, Any


# ── Unicode normalisation ──────────────────────────────────────────────

def normalise_text(text: str) -> str:
    """Normalise unicode dashes, quotes, whitespace."""
    # Dashes
    for cp in range(0x2010, 0x2016):
        text = text.replace(chr(cp), "-")
    text = text.replace("­", "-")  # soft hyphen
    text = text.replace("−", "-")  # minus sign
    # Quotes
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    # Whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ── XML parsing ────────────────────────────────────────────────────────

def _strip_oai_wrapper(xml_string: str) -> str:
    """Extract the <article>...</article> from OAI-PMH or efetch wrappers,
    and strip XML namespaces so ElementTree XPath queries work without
    namespace prefixes.

    PMC OAI returns XML wrapped in <OAI-PMH><GetRecord><record><metadata>
    and efetch wraps in <pmc-articleset>. The article element itself carries
    xmlns="https://jats.nlm.nih.gov/ns/archiving/1.4/" (or similar), which
    causes all unqualified XPath lookups to fail silently.
    """
    # Try to extract <article ...>...</article>
    m = re.search(r"(<article\b[^>]*>.*</article>)", xml_string, re.DOTALL)
    if m:
        xml_string = m.group(1)

    # Strip ALL xmlns declarations so XPath works without namespace prefixes
    xml_string = re.sub(r'\sxmlns(?::[a-zA-Z0-9_-]+)?="[^"]*"', '', xml_string)

    # Remove xsi: attributes entirely (schema validation, not needed)
    xml_string = re.sub(r'\sxsi:\w+="[^"]*"', '', xml_string)

    # Strip namespace prefixes from element tags: <ali:foo> -> <foo>, </ali:foo> -> </foo>
    xml_string = re.sub(r'<([a-zA-Z0-9_-]+):([a-zA-Z0-9_-]+)', r'<\2', xml_string)
    xml_string = re.sub(r'</([a-zA-Z0-9_-]+):([a-zA-Z0-9_-]+)', r'</\2', xml_string)

    # Strip namespace prefixes from attributes: xlink:href="..." -> href="..."
    xml_string = re.sub(r'(\s)[a-zA-Z0-9_-]+:([a-zA-Z0-9_-]+)=', r'\1\2=', xml_string)

    return xml_string


def parse_nxml_sections(xml_string: str) -> Dict[str, str]:
    """Parse PMC NXML into labelled sections.
    Returns dict of {section_name: text}.
    Sections are lowercased for matching.
    """
    # Strip OAI-PMH / efetch wrappers
    xml_string = _strip_oai_wrapper(xml_string)

    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError:
        # Try stripping XML namespaces as a fallback
        cleaned = re.sub(r'\sxmlns[^"]*"[^"]*"', '', xml_string)
        try:
            root = ET.fromstring(cleaned)
        except ET.ParseError:
            return {}

    article = root.find(".//article")
    if article is None:
        article = root

    sections = {}

    # Title
    title_el = article.find(".//article-title")
    if title_el is not None:
        sections["title"] = normalise_text("".join(title_el.itertext()))

    # Abstract
    abstract_el = article.find(".//abstract")
    if abstract_el is not None:
        sections["abstract"] = normalise_text("".join(abstract_el.itertext()))

    # Body sections with hierarchy
    body = article.find(".//body")
    if body is not None:
        for sec in body.findall(".//sec"):
            sec_title_el = sec.find("title")
            sec_title = normalise_text("".join(sec_title_el.itertext())) if sec_title_el is not None else "untitled"

            paragraphs = []
            for p in sec.findall(".//p"):
                text = normalise_text("".join(p.itertext()))
                if text:
                    paragraphs.append(text)

            if paragraphs:
                sections[sec_title.lower()] = "\n".join(paragraphs)

    # Fallback: if no sections found, grab all body text
    if len(sections) <= 2 and body is not None:
        all_text = normalise_text("".join(body.itertext()))
        if all_text:
            sections["body"] = all_text

    return sections


def classify_sections(sections: Dict[str, str], blacklist: List[str]) -> Dict[str, Dict]:
    """Classify sections into clinical vs non-clinical.
    Returns dict of {section_name: {"text": str, "zone": str}}
    where zone is one of: case, background, discussion, methods, excluded
    """
    classified = {}

    # Abstract is patient-specific in case reports, so it gets its own zone
    # (separate from the general "background"/introduction literature).
    abstract_keywords = ["abstract"]
    case_keywords = [
        "case", "presentation", "history", "clinical", "patient",
        "examination", "findings", "hospital course", "clinical course",
        "follow-up", "follow up", "hospital"
    ]
    background_keywords = ["introduction", "background"]
    discussion_keywords = ["discussion", "conclusion"]
    methods_keywords = ["method", "materials", "procedure"]

    for name, text in sections.items():
        low = name.lower()

        # Check blacklist first
        if any(bl in low for bl in blacklist):
            classified[name] = {"text": text, "zone": "excluded"}
            continue

        if any(kw in low for kw in abstract_keywords):
            classified[name] = {"text": text, "zone": "abstract"}
        elif any(kw in low for kw in case_keywords):
            classified[name] = {"text": text, "zone": "case"}
        elif any(kw in low for kw in background_keywords):
            classified[name] = {"text": text, "zone": "background"}
        elif any(kw in low for kw in discussion_keywords):
            classified[name] = {"text": text, "zone": "discussion"}
        elif any(kw in low for kw in methods_keywords):
            classified[name] = {"text": text, "zone": "methods"}
        elif low in ("title",):
            classified[name] = {"text": text, "zone": "title"}
        else:
            # Default to case zone for unrecognised sections (conservative)
            classified[name] = {"text": text, "zone": "case"}

    return classified


# ── Generic-literature sentence detection ─────────────────────────────

# Inline citation markers like "[38]", "[1,2]", "[3-5]"
_CITATION_RE = re.compile(r"\[\s*\d+(?:\s*[-,]\s*\d+)*\s*\]")

# Phrases that signal a sentence is stating general/published knowledge
# rather than describing THIS patient. These are the dominant source of
# false-positive drug/symptom/comorbidity extractions when discussion
# sections leak into per-patient fields.
_LITERATURE_MARKERS = re.compile(
    r"\bet\s+al\b"
    r"|\bin\s+the\s+literature\b"
    r"|(?:have|has)\s+been\s+(?:reported|described|documented|observed|"
    r"published|proposed|suggested|associated|linked|noted)"
    r"|(?:case\s+reports?|studies|authors|researchers|investigators)\s+"
    r"(?:have|report|reported|describe|described|suggest|suggested|"
    r"demonstrate|demonstrated|found|show|shown)"
    r"|previous(?:ly)?\s+(?:studies|reports|reported|described|published)"
    r"|review\s+of\s+the\s+literature"
    r"|it\s+(?:has|had)\s+been\s+(?:suggested|proposed|reported|hypothesi[sz]ed)"
    r"|(?:the\s+)?(?:prevalence|incidence|pathophysiology|aetiology|etiology|"
    r"mechanism)\s+of\b",
    re.IGNORECASE,
)

# Cues that a sentence really is about the index patient. If present, we keep
# the sentence even when it carries an inline citation (citations occasionally
# appear inside case descriptions).
_PATIENT_CUES = re.compile(
    r"\b(?:our\s+patient|the\s+patient|this\s+patient|she\s+|he\s+|her\s+|his\s+|"
    r"we\s+(?:report|present|describe|treated|administered|started|prescribed)|"
    r"year[\s-]*old|month[\s-]*old|presented\s+with|was\s+admitted|"
    r"was\s+started\s+on|was\s+treated\s+with|was\s+diagnosed|was\s+referred|"
    r"on\s+examination|physical\s+examination|complained\s+of|denied)\b",
    re.IGNORECASE,
)


# Explicit "this patient did/received X" cues. Used to rescue genuine
# patient findings that happen to sit in a discussion/conclusion section
# (e.g. "The patient was started on metoprolol, and symptoms resolved").
_PATIENT_ACTION = re.compile(
    r"\b(?:our|the|this|a)\s+patient\b"
    r"|\bwe\s+(?:started|treated|administered|prescribed|gave|managed|"
    r"initiated|commenced|switched|referred|diagnosed|presented|report|"
    r"describe|observed)\b"
    r"|\bwas\s+(?:started\s+on|treated\s+with|given|administered|prescribed|"
    r"commenced\s+on|initiated\s+on|switched\s+to|placed\s+on|referred|"
    r"diagnosed|admitted)\b"
    r"|\bshe\s+(?:was|received|underwent|reported|developed|complained)\b"
    r"|\bhe\s+(?:was|received|underwent|reported|developed|complained)\b",
    re.IGNORECASE,
)


def is_patient_finding_sentence(sentence: str) -> bool:
    """True if a sentence clearly describes an action/finding about the index
    patient (not general guidance). Used to recover patient sentences that
    appear outside the case/abstract zones."""
    if not sentence:
        return False
    return bool(_PATIENT_ACTION.search(sentence)) and not is_generic_literature_sentence(sentence)


def is_generic_literature_sentence(sentence: str) -> bool:
    """Return True if a sentence states published/general knowledge rather
    than a finding about the index patient.

    Used to keep discussion-style statements (e.g. "X has been reported to
    cause Y [12]") out of per-patient extraction fields. Conservative: a
    sentence with a clear patient cue is kept even if it carries a citation.
    """
    if not sentence:
        return False
    has_patient_cue = bool(_PATIENT_CUES.search(sentence))
    # Strong literature phrasing -> generic, unless it is clearly about the patient
    if _LITERATURE_MARKERS.search(sentence) and not has_patient_cue:
        return True
    # Bare inline citation with no patient cue -> treat as generic
    if _CITATION_RE.search(sentence) and not has_patient_cue:
        return True
    return False


# ── Publication metadata extraction ───────────────────────────────────

def extract_publication_metadata(xml_string: str) -> Dict[str, Any]:
    """Extract publication metadata from PMC NXML front matter.

    Returns dict with: title, journal, doi, pmcid, pub_year, pub_date,
    article_type, authors (list of dicts), affiliations (list),
    countries (list), departments (list), keywords (list),
    mesh_terms (list), funding_sources (list), acknowledgements.
    """
    # Strip OAI wrapper and namespaces (same as parse_nxml_sections)
    xml_string = _strip_oai_wrapper(xml_string)

    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError:
        return {}

    meta = {}

    # ── Article IDs ──
    doi_el = root.find('.//article-id[@pub-id-type="doi"]')
    meta["doi"] = doi_el.text.strip() if doi_el is not None and doi_el.text else ""

    pmcid_el = root.find('.//article-id[@pub-id-type="pmc"]')
    meta["pmcid_from_xml"] = ("PMC" + pmcid_el.text.strip()) if pmcid_el is not None and pmcid_el.text else ""

    pmid_el = root.find('.//article-id[@pub-id-type="pmid"]')
    meta["pmid"] = pmid_el.text.strip() if pmid_el is not None and pmid_el.text else ""

    # ── Journal ──
    jt = root.find('.//journal-title')
    meta["journal"] = normalise_text(jt.text) if jt is not None and jt.text else ""

    jid = root.find('.//journal-id[@journal-id-type="nlm-ta"]')
    meta["journal_abbrev"] = jid.text.strip() if jid is not None and jid.text else ""

    # ── Title ──
    title_el = root.find('.//article-title')
    meta["title"] = normalise_text("".join(title_el.itertext())) if title_el is not None else ""

    # ── Article type / subject ──
    subj = root.find('.//article-categories//subj-group/subject')
    meta["article_type"] = normalise_text(subj.text) if subj is not None and subj.text else ""

    article_el = root.find('.//article')
    if article_el is not None:
        meta["article_type_attr"] = article_el.get("article-type", "")

    # ── Publication date ──
    # Prefer epub, then ppub, then collection, then any
    pub_date = None
    for ptype in ["epub", "ppub", "pub", "collection"]:
        pd = root.find(f'.//pub-date[@pub-type="{ptype}"]')
        if pd is None:
            pd = root.find(f'.//pub-date[@date-type="{ptype}"]')
        if pd is not None:
            pub_date = pd
            break
    if pub_date is None:
        pub_date = root.find('.//pub-date')

    if pub_date is not None:
        y = pub_date.findtext("year", "")
        m = pub_date.findtext("month", "")
        d = pub_date.findtext("day", "")
        meta["pub_year"] = int(y) if y.isdigit() else None
        meta["pub_date"] = f"{y}-{m.zfill(2) if m else '00'}-{d.zfill(2) if d else '00'}"
    else:
        meta["pub_year"] = None
        meta["pub_date"] = ""

    # ── Authors and affiliations ──
    authors = []
    aff_map = {}  # id -> text

    # Build affiliation map first
    for aff_el in root.findall('.//aff'):
        aff_id = aff_el.get("id", "")
        aff_text = normalise_text("".join(aff_el.itertext()))
        # Strip leading label like "1" or "a"
        aff_text = re.sub(r"^\s*\d+\s*", "", aff_text).strip()
        if aff_id:
            aff_map[aff_id] = aff_text

    for contrib in root.findall('.//contrib[@contrib-type="author"]'):
        surname = contrib.findtext('.//surname', "")
        given = contrib.findtext('.//given-names', "")
        name = f"{given} {surname}".strip()

        # Get affiliated affiliation IDs
        author_affs = []
        for xref in contrib.findall('.//xref[@ref-type="aff"]'):
            rid = xref.get("rid", "")
            if rid in aff_map:
                author_affs.append(aff_map[rid])

        authors.append({"name": name, "affiliations": author_affs})

    meta["authors"] = authors
    meta["author_count"] = len(authors)

    # ── All affiliations as flat list ──
    all_affs = list(aff_map.values()) if aff_map else [
        normalise_text("".join(a.itertext())).strip()
        for a in root.findall('.//aff')
    ]
    meta["affiliations"] = all_affs

    # ── Countries ──
    countries = []
    for c in root.findall('.//aff//country'):
        if c.text and c.text.strip():
            countries.append(c.text.strip())
    # Fallback: parse from affiliation text
    if not countries:
        country_patterns = [
            r",\s*(USA|UK|United Kingdom|United States|Canada|Australia|Germany|"
            r"France|Italy|Spain|Japan|China|India|Brazil|Netherlands|Sweden|"
            r"Switzerland|South Korea|Turkey|Iran|Saudi Arabia|Egypt|Israel|"
            r"Belgium|Austria|Denmark|Norway|Finland|Poland|Portugal|Greece|"
            r"Ireland|New Zealand|Mexico|Argentina|Colombia|Chile|Thailand|"
            r"Malaysia|Singapore|Taiwan|Pakistan|Bangladesh|Nigeria|South Africa)\s*$"
        ]
        for aff_text in all_affs:
            for pat in country_patterns:
                m = re.search(pat, aff_text, re.IGNORECASE)
                if m:
                    countries.append(m.group(1).strip())
    meta["countries"] = sorted(set(countries))

    # ── Departments / specialties ──
    departments = []
    for aff_text in all_affs:
        # Look for "Department of X" or "Division of X"
        m = re.search(r"(?:department|division|section|unit)\s+of\s+([^,;.]+)", aff_text, re.IGNORECASE)
        if m:
            departments.append(m.group(1).strip())
    meta["departments"] = sorted(set(departments))

    # ── Keywords ──
    keywords = []
    for kwd in root.findall('.//kwd-group//kwd'):
        text = "".join(kwd.itertext()).strip()
        if text:
            keywords.append(text)
    meta["keywords"] = keywords

    # ── MeSH terms (if separate from keywords) ──
    mesh_terms = []
    for kg in root.findall('.//kwd-group[@kwd-group-type="MeSH"]//kwd'):
        text = "".join(kg.itertext()).strip()
        if text:
            mesh_terms.append(text)
    meta["mesh_terms"] = mesh_terms if mesh_terms else keywords  # fallback

    # ── Funding ──
    funding_sources = []
    for fs in root.findall('.//funding-group//funding-source'):
        text = "".join(fs.itertext()).strip()
        if text:
            funding_sources.append(text)
    # Also check award IDs
    for ag in root.findall('.//funding-group//award-group'):
        source = ag.find('.//funding-source')
        award = ag.find('.//award-id')
        entry = ""
        if source is not None:
            entry = "".join(source.itertext()).strip()
        if award is not None and award.text:
            entry += f" ({award.text.strip()})" if entry else award.text.strip()
        if entry:
            funding_sources.append(entry)
    meta["funding_sources"] = list(set(funding_sources))

    # ── Acknowledgements (often contains funding info) ──
    ack = root.find('.//ack')
    meta["acknowledgements"] = normalise_text("".join(ack.itertext())) if ack is not None else ""

    # ── License ──
    license_el = root.find('.//license')
    if license_el is not None:
        license_type = license_el.get("license-type", "")
        href = license_el.get("{http://www.w3.org/1999/xlink}href", "")
        meta["license"] = license_type or href or normalise_text("".join(license_el.itertext()))[:100]
    else:
        meta["license"] = ""

    return meta


# ── Sentence segmentation ─────────────────────────────────────────────

# Abbreviations that should NOT trigger sentence breaks
ABBREVIATIONS = {
    "dr", "mr", "mrs", "ms", "prof", "fig", "figs", "vs", "al",
    "etc", "approx", "ca", "dept", "est", "inc", "jr", "sr",
    "no", "vol", "ref", "refs", "ed", "eds", "rev",
    # Medical abbreviations
    "pt", "dx", "tx", "rx", "hx", "sx", "yr", "yrs", "mo", "mos",
    "wk", "wks", "hr", "hrs", "min", "mins", "sec", "mg", "ml",
    "kg", "cm", "mm", "mcg", "ng", "iu",
    "e.g", "i.e", "i.v", "p.o",
}


def segment_sentences(text: str) -> List[str]:
    """Split text into sentences, handling medical abbreviations.
    Much more robust than text.split('.').
    """
    # First, protect abbreviations by replacing their periods
    protected = text
    for abbr in ABBREVIATIONS:
        # Match abbreviation followed by period and space/end
        pattern = re.compile(r"\b" + re.escape(abbr) + r"\.", re.IGNORECASE)
        protected = pattern.sub(abbr.upper() + "•", protected)  # bullet as placeholder

    # Protect decimal numbers (e.g., "3.5 mg")
    protected = re.sub(r"(\d)\.\s*(\d)", r"\1•\2", protected)

    # Protect "et al."
    protected = re.sub(r"et\s+al\.", "et al•", protected)

    # Split on sentence-ending punctuation followed by space + uppercase or end
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\d([])", protected)

    # Restore placeholders
    sentences = []
    for part in parts:
        restored = part.replace("•", ".")
        restored = restored.strip()
        if restored and len(restored) > 5:  # skip tiny fragments
            sentences.append(restored)

    return sentences


def get_clinical_text(sections: Dict[str, str], blacklist: List[str]) -> Tuple[str, List[str]]:
    """Get clinical text (case + abstract + discussion) and clinical sentences.
    Excludes references and other non-clinical sections.
    Returns (full_clinical_text, list_of_sentences).
    """
    classified = classify_sections(sections, blacklist)

    # Priority ordering: abstract > case > background > discussion
    clinical_parts = []
    for zone in ["abstract", "background", "case", "discussion"]:
        for name, info in classified.items():
            if info["zone"] == zone:
                clinical_parts.append(info["text"])

    clinical_text = " ".join(clinical_parts)
    sentences = segment_sentences(clinical_text)

    return clinical_text, sentences


def get_patient_sentences(sections: Dict[str, str], blacklist: List[str]) -> List[str]:
    """Get sentences describing the index patient (abstract + case zones),
    with generic-literature sentences removed.

    This is the correct sentence set for per-patient extraction (drugs the
    patient received, the patient's symptoms/comorbidities/measurements/
    outcomes). It deliberately excludes the discussion/introduction/methods
    zones, which describe published knowledge rather than this patient and
    are the main source of false positives.

    Falls back to all clinical sentences (literature-filtered) if no
    abstract/case content is found, so single-section articles still work.
    """
    classified = classify_sections(sections, blacklist)

    parts = []
    for zone in ["abstract", "case"]:
        for name, info in classified.items():
            if info["zone"] == zone:
                parts.append(info["text"])

    text = " ".join(parts)
    sentences = [
        s for s in segment_sentences(text)
        if not is_generic_literature_sentence(s)
    ]

    # Recover genuine patient findings that sit in discussion/conclusion or
    # introduction zones (e.g. "The patient was started on X, symptoms
    # resolved"). Only sentences with an explicit patient-action cue are
    # admitted, so general treatment guidance stays out.
    seen = set(sentences)
    for name, info in classified.items():
        if info["zone"] in ("discussion", "background"):
            for s in segment_sentences(info["text"]):
                if s not in seen and is_patient_finding_sentence(s):
                    sentences.append(s)
                    seen.add(s)

    if not sentences:
        # Fallback: use all clinical sentences but still drop literature ones.
        _, all_sentences = get_clinical_text(sections, blacklist)
        sentences = [
            s for s in all_sentences
            if not is_generic_literature_sentence(s)
        ]

    return sentences


def get_case_sentences(sections: Dict[str, str], blacklist: List[str]) -> List[str]:
    """Get only case-presentation sentences (highest confidence for patient data)."""
    classified = classify_sections(sections, blacklist)

    case_parts = []
    for name, info in classified.items():
        if info["zone"] == "case":
            case_parts.append(info["text"])

    if not case_parts:
        # Fallback: use abstract
        for name, info in classified.items():
            if info["zone"] == "background":
                case_parts.append(info["text"])

    case_text = " ".join(case_parts)
    return segment_sentences(case_text)
