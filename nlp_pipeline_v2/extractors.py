"""
NLP-enhanced extractors for case report phenotyping.

Each extractor takes clinical sentences and returns structured data.
All extractors are context-aware (use sentences, not raw text) and
negation-aware.
"""

import re
import json
import os
from typing import Dict, List, Optional, Tuple, Any

from .negation import get_detector
from .text_processing import normalise_text


# ── Load config ────────────────────────────────────────────────────────

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


# ── Drug extraction ────────────────────────────────────────────────────

# ── Corpus-driven drug discovery ──
# Augments the dictionary lookup so disease-specific drugs that aren't in the
# config list (e.g. modafinil / methylphenidate / sodium oxybate for narcolepsy)
# are still detected from the papers, via generic drug-name morphology and
# treatment cues — not a hardcoded per-disease list.
_DRUG_STEM = (
    r"(?:mab|nib|sartan|pril|statin|azepam|zolam|prazole|tidine|caine|olol|"
    r"dipine|parin|gliptin|glitazone|floxacin|cycline|mycin|micin|cillin|navir|"
    r"ovir|setron|triptan|triptyline|oxetine|afil|dronate|tropium|terol|sone|"
    r"solone|onide|phylline|codone|morphone|done|azine|pramine|lukast|platin|"
    r"taxel|tecan|pitant|fenadine|tadine|phenidate|amphetamine|oxybate)"
)
_DRUG_STEM_RE = re.compile(r"\b([a-z][a-z]{3,}" + _DRUG_STEM + r")\b", re.I)
_DRUG_CUE_RE = re.compile(
    r"(?:treated with|treatment with|started on|commenced on|initiated on|"
    r"initiated|received|administered|prescribed|managed with|therapy with|"
    r"switched to|dose of|doses of)\s+"
    r"([a-z][a-z\-]{3,}(?:\s+[a-z][a-z\-]{3,}){0,2})", re.I)
# Words that look drug-like (or follow a treatment cue) but are not drugs.
_DRUG_NONDRUG = {
    "surgery", "surgical", "resection", "excision", "radiation", "radiotherapy",
    "chemotherapy", "physiotherapy", "therapy", "rehabilitation", "rest", "fluids",
    "fluid", "oxygen", "transfusion", "dialysis", "ventilation", "observation",
    "supportive", "care", "lifestyle", "diet", "exercise", "splinting", "bracing",
    "immobilization", "counseling", "counselling", "psychotherapy", "intervention",
    "management", "treatment", "medication", "medications", "drugs", "drug",
    "antibiotics", "steroids", "analgesia", "anticoagulation", "admission", "review",
    "monitoring", "support", "nutrition", "saline", "intravenous", "oral", "topical",
    "regular", "standard", "various", "multiple", "several", "noninvasive", "positive",
    "continuous", "mechanical", "conservative", "medical", "further", "combination",
    "good", "poor", "appropriate", "once", "twice", "daily", "with", "without",
    "airway", "airways", "cholesterol", "immediate-release", "extended-release",
    "sustained-release", "modified-release", "slow-release", "low-dose", "high-dose",
    "intranasal", "inhaled", "nasal", "this", "that", "both", "high", "low", "her",
    "his", "their", "the", "new",
}


class DrugExtractor:
    """Drug NER: a config dictionary lookup PLUS corpus-driven discovery.

    The dictionary (drug_classes from config) gives reliable recall and dosage
    extraction for listed drugs; discovery adds any other medications the papers
    actually mention so disease-specific drugs aren't missed. Discovery can be
    turned off with ``disable_drug_discovery`` in the config.
    """

    # Dosage pattern: captures number + unit (e.g., "100 mg", "0.1 mg/kg")
    DOSAGE_PAT = re.compile(
        r"(\d+(?:\.\d+)?)\s*(mg|mcg|ug|g|ml|units?|iu)(?:\s*/\s*(?:kg|day|dose|ml))?"
        r"(?:\s+(?:once|twice|three times|four times|daily|bid|tid|qid|qhs|prn|po|iv|im|sc|oral(?:ly)?))?"
        , re.IGNORECASE
    )

    # Route patterns
    ROUTE_PAT = re.compile(
        r"\b(oral(?:ly)?|intravenous(?:ly)?|iv|intramuscular(?:ly)?|im|"
        r"subcutaneous(?:ly)?|sc|sq|topical(?:ly)?|intranasal(?:ly)?|"
        r"sublingual(?:ly)?|transdermal|inhaled|nebulised|nebulized)\b",
        re.IGNORECASE
    )

    # Frequency patterns
    FREQ_PAT = re.compile(
        r"\b(once daily|twice daily|three times daily|four times daily|"
        r"daily|bid|tid|qid|qhs|prn|as needed|every \d+ hours?|"
        r"once weekly|twice weekly|weekly|monthly)\b",
        re.IGNORECASE
    )

    def __init__(self, config: dict = None):
        if config is None:
            config = load_config()

        # Build drug lookup: drug_name_lower -> class
        self.drug_lookup = {}
        for drug_class, drugs in config.get("drug_classes", {}).items():
            for drug in drugs:
                self.drug_lookup[drug.lower()] = drug_class

        # Build compiled patterns for each drug
        self.drug_patterns = []
        for drug_name in self.drug_lookup:
            # Escape and compile, word boundary
            pat = re.compile(r"\b" + re.escape(drug_name) + r"\b", re.IGNORECASE)
            self.drug_patterns.append((pat, drug_name))

        self._discovery = not config.get("disable_drug_discovery", False)

    def _discover_candidates(self, sent_lower: str):
        """Yield (drug_name, start, end) for drug mentions found via morphology
        and treatment cues that are NOT already in the config dictionary."""
        spans = []
        for m in _DRUG_STEM_RE.finditer(sent_lower):
            name = m.group(1)
            if name in _DRUG_NONDRUG or name in self.drug_lookup:
                continue
            spans.append((name, m.start(1), m.end(1)))
        for m in _DRUG_CUE_RE.finditer(sent_lower):
            toks = m.group(1).split()
            while toks and toks[0] in _DRUG_NONDRUG:
                toks = toks[1:]
            if not toks:
                continue
            name = " ".join(toks)
            head = toks[-1]
            if head in _DRUG_NONDRUG or len(head) < 4 or name in self.drug_lookup:
                continue
            # locate the cleaned phrase within the sentence for negation/dosage
            idx = sent_lower.find(name, m.start(1))
            if idx < 0:
                idx = m.start(1)
            spans.append((name, idx, idx + len(name)))
        return spans

    def extract_from_sentences(self, sentences: List[str]) -> List[dict]:
        """Extract drug mentions from clinical sentences.

        Returns list of {drug, drug_class, dosage, route, frequency,
                         sentence, negated, trigger}
        """
        neg = get_detector()
        results = []
        seen = set()  # Deduplicate (drug, dosage) pairs

        for sent in sentences:
            sent_lower = sent.lower()

            for pat, drug_name in self.drug_patterns:
                match = pat.search(sent)
                if not match:
                    continue

                # Check negation
                is_neg, trigger = neg.is_negated(sent, match.start(), match.end())

                # Extract dosage from nearby text (within same sentence)
                dosage = None
                dose_match = self.DOSAGE_PAT.search(sent_lower[max(0, match.start()-20):match.end()+80])
                if dose_match:
                    dosage = dose_match.group(0).strip()

                # Extract route
                route = None
                route_match = self.ROUTE_PAT.search(sent_lower)
                if route_match:
                    route = route_match.group(1).lower()

                # Extract frequency
                frequency = None
                freq_match = self.FREQ_PAT.search(sent_lower)
                if freq_match:
                    frequency = freq_match.group(1).lower()

                # Dedup: keep first mention of each drug per negation status
                # If same drug appears with and without dosage, keep the one with dosage
                key = (drug_name, is_neg)
                if key in seen:
                    # Update dosage if this mention has one and previous didn't
                    if dosage:
                        for prev in results:
                            if prev["drug"] == drug_name and prev["negated"] == is_neg and not prev["dosage"]:
                                prev["dosage"] = dosage
                                if route:
                                    prev["route"] = route
                                if frequency:
                                    prev["frequency"] = frequency
                    continue
                seen.add(key)

                results.append({
                    "drug": drug_name,
                    "drug_class": self.drug_lookup[drug_name],
                    "dosage": dosage,
                    "route": route,
                    "frequency": frequency,
                    "negated": is_neg,
                    "neg_trigger": trigger,
                    "sentence": sent[:200],
                })

            # ── Corpus discovery pass (drugs not in the config dictionary) ──
            if self._discovery:
                for drug_name, ds, de in self._discover_candidates(sent_lower):
                    is_neg, trigger = neg.is_negated(sent, ds, de)
                    key = (drug_name, is_neg)
                    if key in seen:
                        continue
                    dosage = None
                    dose_match = self.DOSAGE_PAT.search(sent_lower[max(0, ds - 20):de + 80])
                    if dose_match:
                        dosage = dose_match.group(0).strip()
                    route_match = self.ROUTE_PAT.search(sent_lower)
                    freq_match = self.FREQ_PAT.search(sent_lower)
                    seen.add(key)
                    results.append({
                        "drug": drug_name,
                        "drug_class": "discovered",
                        "dosage": dosage,
                        "route": route_match.group(1).lower() if route_match else None,
                        "frequency": freq_match.group(1).lower() if freq_match else None,
                        "negated": is_neg,
                        "neg_trigger": trigger,
                        "sentence": sent[:200],
                    })

        return results


# ── Temporal extraction ────────────────────────────────────────────────

class TemporalExtractor:
    """Extract age at onset, diagnostic delay, and timeline events.

    Handles complex temporal inference:
    - "10-year history of X" + age 30 -> onset at 20
    - "symptoms began at age 15" -> onset at 15
    - "diagnosed 5 years after onset" -> 5yr delay
    - "first noticed symptoms in childhood" -> qualitative onset
    """

    # Age at presentation patterns (from the existing pipeline, refined)
    AGE_PRES_PATTERNS = [
        (r"(\d{1,3})[\s-]*year[\s-]*old", "years"),
        (r"age[d]?\s*(?:of\s*)?(\d{1,3})\b", "years"),
        (r"(\d{1,3})[\s-]*yo\b", "years"),
        (r"(\d{1,3})\s*years?\s*of\s*age", "years"),
        (r"(\d{1,3})[\s-]*month[\s-]*old", "months"),
        (r"(\d{1,3})[\s-]*week[\s-]*old", "weeks"),
        (r"(?:patient|woman|man|female|male|girl|boy),?\s*(?:aged?\s*)?(\d{1,3})", "years"),
        (r"in\s+(?:his|her)\s+(\d{1,2})0s", "decade"),  # "in her 30s" -> 35
    ]

    # Duration/history patterns (the key improvement over regex)
    DURATION_PATTERNS = [
        # "X-year history of Y"
        (r"(\d+)[\s-]*year[\s-]*history\s+of\b", "years"),
        # "Y for X years"
        (r"for\s+(?:the\s+(?:past|last|previous)\s+)?(\d+)\s*years?", "years"),
        # "X-month history of Y"
        (r"(\d+)[\s-]*month[\s-]*history\s+of\b", "months"),
        # "Y for X months"
        (r"for\s+(?:the\s+(?:past|last|previous)\s+)?(\d+)\s*months?", "months"),
        # "since age X" or "since the age of X"
        (r"since\s+(?:the\s+)?age\s+(?:of\s+)?(\d{1,3})", "since_age"),
        # "since childhood / adolescence / infancy"
        (r"since\s+(childhood|adolescence|infancy|birth|early\s+childhood|teenage\s+years)", "since_qual"),
        # "symptoms began X years ago"
        (r"(?:symptoms?|complaints?|problems?)\s+(?:began|started|commenced|developed|appeared)\s+(\d+)\s*years?\s+(?:ago|before|prior)", "years_ago"),
        # "first noticed at age X"
        (r"first\s+(?:noticed|experienced|developed|presented|diagnosed)\s+(?:at\s+)?(?:age\s+)?(\d{1,3})", "onset_age"),
        # "onset at age X" / "onset at X years"
        (r"onset\s+(?:at\s+)?(?:age\s+)?(\d{1,3})(?:\s+years?)?", "onset_age"),
        # "developed X at age Y"
        (r"developed\s+.{0,40}?\s+at\s+(?:age\s+)?(\d{1,3})", "onset_age"),
        # "symptoms dating back X years"
        (r"(?:symptoms?|complaints?)\s+(?:dating|going)\s+back\s+(\d+)\s*years?", "years"),
        # "lifelong history"
        (r"(lifelong|life[\s-]*long)\s+history", "lifelong"),
        # "X years of Y" (e.g., "20 years of joint pain")
        (r"(\d+)\s*years?\s+of\s+(?:progressive\s+|worsening\s+|chronic\s+|intermittent\s+)?(?:joint|pain|symptom|fatigue|hypermobi)", "years_of"),
    ]

    # Diagnostic delay patterns
    DELAY_PATTERNS = [
        # "diagnosed X years after onset/symptoms"
        (r"diagnos\w+\s+(\d+)\s*years?\s+(?:after|following)\s+(?:onset|symptom|initial|first)", "delay_explicit"),
        # "X-year diagnostic delay"
        (r"(\d+)[\s-]*year[\s-]*diagnostic[\s-]*delay", "delay_explicit"),
        # "X-year diagnostic odyssey/journey"
        (r"(\d+)[\s-]*year[\s-]*(?:diagnostic\s+)?(?:odyssey|journey|quest)", "delay_explicit"),
        # "waited X years for diagnosis"
        (r"(?:waited|took)\s+(\d+)\s*years?\s+(?:for|to\s+(?:get|receive|obtain))\s+(?:a\s+)?diagnos", "delay_explicit"),
        # "finally diagnosed after X years"
        (r"finally\s+diagnos\w+\s+(?:after\s+)?(\d+)\s*years?", "delay_explicit"),
        # "seen by X specialists / doctors before diagnosis"
        (r"seen\s+(?:by\s+)?(\d+)\s*(?:specialist|doctor|physician|clinician)", "specialists_seen"),
        # "multiple misdiagnoses"
        (r"(multiple|several|numerous|many)\s+(?:prior\s+)?misdiagnos", "misdiag_qual"),
        # "previously (mis)diagnosed with X"
        (r"previously\s+(?:mis)?diagnos\w+\s+(?:with|as)\s+(.{5,60}?)(?:\.|,|;|and\s)", "misdiag_specific"),
        # "misdiagnosed as/with X"
        (r"misdiagnos\w+\s+(?:as|with)\s+(.{5,60}?)(?:\.|,|;|and\s)", "misdiag_specific"),
        # "initially diagnosed with X" (implies reclassification)
        (r"initially\s+diagnos\w+\s+(?:with|as)\s+(.{5,60}?)(?:\.|,|;|and\s|but\s)", "initial_diag"),
    ]

    # Referral patterns
    REFERRAL_PATTERNS = [
        (r"referred\s+to\s+(?:a\s+|the\s+)?(\w+(?:\s+\w+)?)\s+(?:specialist|department|clinic|service|team|unit)", "referral"),
        (r"(?:seen|evaluated|assessed)\s+(?:by|at)\s+(?:a\s+|the\s+)?(\w+(?:\s+\w+)?)\s+(?:specialist|department|clinic)", "seen_by"),
        (r"(?:consult(?:ed|ation)\s+(?:with|by|from))\s+(?:a\s+|the\s+)?(\w+(?:\s+\w+)?)", "consult"),
    ]

    QUALITATIVE_AGE_MAP = {
        "childhood": (3, 12, "childhood"),
        "early childhood": (1, 5, "early childhood"),
        "infancy": (0, 1, "infancy"),
        "birth": (0, 0, "birth"),
        "adolescence": (12, 18, "adolescence"),
        "teenage years": (12, 18, "teenage years"),
    }

    def extract_from_sentences(self, sentences: List[str], age_at_presentation: float = None) -> dict:
        """Extract temporal information from clinical sentences.

        Args:
            sentences: Clinical sentences.
            age_at_presentation: Age at presentation if known (for onset inference).

        Returns:
            Dict with: age_at_onset, onset_evidence, diagnostic_delay,
                       delay_evidence, misdiagnoses, referral_pathway,
                       symptom_duration.
        """
        result = {
            "age_at_onset": None,
            "age_at_onset_qualitative": None,
            "onset_evidence": [],
            "symptom_duration_years": None,
            "diagnostic_delay_years": None,
            "delay_evidence": [],
            "misdiagnoses": [],
            "referral_pathway": [],
        }

        seen_onset_sents = set()  # Prevent duplicate evidence from same sentence

        for sent in sentences:
            sent_lower = sent.lower()

            # Extract duration/history (stop after first match per sentence)
            for pat_str, pat_type in self.DURATION_PATTERNS:
                m = re.search(pat_str, sent_lower)
                if not m:
                    continue

                if pat_type == "years":
                    duration = int(m.group(1))
                    result["symptom_duration_years"] = duration
                    if age_at_presentation is not None and duration > 0:
                        inferred_onset = age_at_presentation - duration
                        if 0 <= inferred_onset < age_at_presentation:
                            result["age_at_onset"] = inferred_onset
                            if sent[:100] not in seen_onset_sents:
                                seen_onset_sents.add(sent[:100])
                                result["onset_evidence"].append({
                                    "method": "inferred_from_duration",
                                    "duration_years": duration,
                                    "presentation_age": age_at_presentation,
                                    "sentence": sent[:200],
                                })
                    break  # One duration match per sentence

                elif pat_type == "months":
                    duration_months = int(m.group(1))
                    duration_years = duration_months / 12
                    if result["symptom_duration_years"] is None:
                        result["symptom_duration_years"] = round(duration_years, 1)
                    if age_at_presentation is not None:
                        inferred = age_at_presentation - duration_years
                        if 0 <= inferred < age_at_presentation:
                            result["age_at_onset"] = round(inferred, 1)
                            result["onset_evidence"].append({
                                "method": "inferred_from_duration_months",
                                "duration_months": duration_months,
                                "sentence": sent[:200],
                            })

                elif pat_type == "since_age":
                    onset_age = int(m.group(1))
                    if 0 <= onset_age <= 120:
                        result["age_at_onset"] = onset_age
                        result["onset_evidence"].append({
                            "method": "explicit_since_age",
                            "sentence": sent[:200],
                        })

                elif pat_type == "since_qual":
                    qual = m.group(1).lower().strip()
                    if qual in self.QUALITATIVE_AGE_MAP:
                        low, high, label = self.QUALITATIVE_AGE_MAP[qual]
                        result["age_at_onset_qualitative"] = label
                        result["age_at_onset"] = (low + high) / 2  # midpoint
                        result["onset_evidence"].append({
                            "method": "qualitative",
                            "label": label,
                            "sentence": sent[:200],
                        })

                elif pat_type in ("onset_age",):
                    onset_age = int(m.group(1))
                    if 0 <= onset_age <= 120:
                        result["age_at_onset"] = onset_age
                        result["onset_evidence"].append({
                            "method": "explicit_onset_age",
                            "sentence": sent[:200],
                        })

                elif pat_type == "years_ago" and age_at_presentation is not None:
                    years_ago = int(m.group(1))
                    inferred = age_at_presentation - years_ago
                    if 0 <= inferred < age_at_presentation:
                        result["age_at_onset"] = inferred
                        result["onset_evidence"].append({
                            "method": "inferred_from_years_ago",
                            "sentence": sent[:200],
                        })

                elif pat_type == "lifelong":
                    result["age_at_onset"] = 0
                    result["age_at_onset_qualitative"] = "lifelong"
                    result["onset_evidence"].append({
                        "method": "lifelong",
                        "sentence": sent[:200],
                    })

                elif pat_type == "years_of":
                    duration = int(m.group(1))
                    if result["symptom_duration_years"] is None:
                        result["symptom_duration_years"] = duration
                    if age_at_presentation is not None:
                        inferred = age_at_presentation - duration
                        if 0 <= inferred < age_at_presentation:
                            result["age_at_onset"] = inferred
                            result["onset_evidence"].append({
                                "method": "inferred_from_years_of",
                                "duration_years": duration,
                                "sentence": sent[:200],
                            })

            # Extract diagnostic delay
            for pat_str, pat_type in self.DELAY_PATTERNS:
                m = re.search(pat_str, sent_lower)
                if not m:
                    continue

                if pat_type == "delay_explicit":
                    years = int(m.group(1))
                    result["diagnostic_delay_years"] = years
                    result["delay_evidence"].append({
                        "method": "explicit_delay",
                        "years": years,
                        "sentence": sent[:200],
                    })

                elif pat_type == "specialists_seen":
                    n = int(m.group(1))
                    result["delay_evidence"].append({
                        "method": "specialists_count",
                        "count": n,
                        "sentence": sent[:200],
                    })

                elif pat_type in ("misdiag_specific", "initial_diag"):
                    misdiag = m.group(1).strip().rstrip(".")
                    if len(misdiag) > 3:
                        result["misdiagnoses"].append({
                            "condition": misdiag,
                            "sentence": sent[:200],
                        })

                elif pat_type == "misdiag_qual":
                    result["delay_evidence"].append({
                        "method": "multiple_misdiagnoses",
                        "sentence": sent[:200],
                    })

            # Extract referral pathway
            for pat_str, pat_type in self.REFERRAL_PATTERNS:
                m = re.search(pat_str, sent_lower)
                if m:
                    specialty = m.group(1).strip()
                    if len(specialty) > 2 and specialty not in ("a", "an", "the", "our", "their"):
                        result["referral_pathway"].append({
                            "specialty": specialty,
                            "type": pat_type,
                            "sentence": sent[:200],
                        })

        # Infer diagnostic delay from onset age + presentation age
        if (result["diagnostic_delay_years"] is None
                and result["age_at_onset"] is not None
                and age_at_presentation is not None):
            delay = age_at_presentation - result["age_at_onset"]
            if delay > 0:
                result["diagnostic_delay_years"] = round(delay, 1)
                result["delay_evidence"].append({
                    "method": "inferred_from_ages",
                    "onset_age": result["age_at_onset"],
                    "presentation_age": age_at_presentation,
                })

        return result


# ── Measurement extraction ─────────────────────────────────────────────

class MeasurementExtractor:
    """Extract clinical measurements with values and context.

    Heart rate, blood pressure, tryptase, Beighton score, tilt table results.
    """

    def __init__(self, config: dict = None):
        if config is None:
            config = load_config()

        self.measurement_config = config.get("measurement_patterns", {})

    def extract_from_sentences(self, sentences: List[str]) -> dict:
        """Extract measurements from clinical sentences.

        Returns dict of {measurement_name: [{value, unit, context, sentence}]}
        """
        neg = get_detector()
        results = {}

        for meas_name, meas_conf in self.measurement_config.items():
            # tilt_table_hr_increase needs the *increase* (delta), not the
            # absolute final HR, and must be gated to a postural context.
            if meas_name == "tilt_table_hr_increase":
                results[meas_name] = self._extract_tilt_increase(
                    sentences, neg, meas_conf.get("unit", "bpm"))
                continue

            results[meas_name] = []
            patterns = meas_conf.get("patterns", [])
            unit = meas_conf.get("unit", "")

            for sent in sentences:
                for pat_str in patterns:
                    for m in re.finditer(pat_str, sent, re.IGNORECASE):
                        # Check negation
                        is_neg, trigger = neg.is_negated(sent, m.start(), m.end())

                        # Extract value(s)
                        groups = m.groups()
                        if len(groups) == 2:
                            value = f"{groups[0]}/{groups[1]}"
                        elif len(groups) == 1:
                            value = groups[0]
                        else:
                            value = m.group(0)

                        # Determine context (supine, standing, baseline, etc.)
                        context = self._get_context(sent, m.start())

                        results[meas_name].append({
                            "value": value,
                            "unit": unit,
                            "context": context,
                            "negated": is_neg,
                            "sentence": sent[:200],
                        })

        return results

    # Postural cues that qualify a heart-rate change as orthostatic/tilt-table
    # (rather than exercise, ablation, ECG monitoring, etc.).
    _POSTURAL_CUES = (
        "stand", "upright", "tilt", "head-up", "head up", "orthostat",
        "active standing", "postural tachycardia", "autonomic function test",
        "-degree", "pots",
    )

    def _extract_tilt_increase(self, sentences: List[str], neg, unit: str) -> List[dict]:
        """Extract the orthostatic heart-rate *increase* (bpm).

        Handles both "increased by N" (N is the delta) and "increased from X to
        Y" (delta = Y - X), and only accepts sentences with a postural context.
        """
        by_pat = re.compile(
            r"(?:heart\s+rate|hr|pulse)\s+(?:increased?|rose|increment(?:ed)?|went\s+up|increase)\s+by\s+(\d{1,3})\s*(?:bpm|beats)",
            re.IGNORECASE)
        from_pat = re.compile(
            r"(?:heart\s+rate|hr|pulse)\s+(?:increased?|rose|increase|went\s+up)\s+from\s+(\d{1,3})\s+to\s+(\d{1,3})",
            re.IGNORECASE)
        out = []
        seen = set()

        def _add(delta, sent, start, end):
            key = (delta, sent[:120])
            if key in seen:
                return
            seen.add(key)
            out.append(self._tilt_entry(delta, sent, start, neg, end, unit))

        for sent in sentences:
            low = sent.lower()
            if not any(cue in low for cue in self._POSTURAL_CUES):
                continue
            for m in by_pat.finditer(sent):
                _add(int(m.group(1)), sent, m.start(), m.end())
            for m in from_pat.finditer(sent):
                x, y = int(m.group(1)), int(m.group(2))
                if y > x:
                    _add(y - x, sent, m.start(), m.end())
        return out

    def _tilt_entry(self, delta: int, sent: str, start: int, neg, end: int, unit: str) -> dict:
        is_neg, _ = neg.is_negated(sent, start, end)
        return {
            "value": str(delta),
            "unit": unit,
            "context": "standing",
            "negated": is_neg,
            "sentence": sent[:200],
        }

    def _get_context(self, sentence: str, match_start: int) -> str:
        """Determine measurement context (supine, standing, etc.)."""
        window = sentence[max(0, match_start-80):match_start].lower()

        context_terms = {
            "supine": ["supine", "lying", "resting", "baseline", "recumbent"],
            "standing": ["standing", "upright", "orthostatic", "tilt"],
            "exercise": ["exercise", "exertion", "stress test"],
            "admission": ["admission", "on arrival", "presenting", "initial"],
            "discharge": ["discharge", "upon release"],
            "peak": ["peak", "maximum", "highest"],
        }
        for ctx, terms in context_terms.items():
            if any(t in window for t in terms):
                return ctx

        return "unspecified"


# ── Outcome extraction ─────────────────────────────────────────────────

class OutcomeExtractor:
    """Extract treatment outcomes and functional impact."""

    OUTCOME_PATTERNS = [
        # Positive outcomes
        (r"(?:symptom|condition|patient)\w*\s+(?:improved|resolved|remitted|stabilised|stabilized)", "improved"),
        (r"(?:significant|marked|notable|substantial)\s+improvement", "improved"),
        (r"(?:complete|partial|full)\s+(?:resolution|remission|recovery)", "improved"),
        (r"symptoms?\s+(?:abated|subsided|diminished|decreased)", "improved"),
        (r"(?:responded|response)\s+(?:well|favorably|favourably)\s+to", "improved"),
        (r"(?:good|excellent|favorable|favourable)\s+(?:outcome|response|result)", "improved"),

        # Negative outcomes
        (r"(?:symptom|condition|patient)\w*\s+(?:worsened|deteriorated|progressed|persisted)", "worsened"),
        (r"no\s+(?:significant\s+)?improvement", "no_improvement"),
        (r"(?:refractory|resistant|unresponsive)\s+to\s+(?:treatment|therapy|medication)", "refractory"),
        (r"(?:died|death|deceased|mortality|fatal)", "death"),

        # Stable
        (r"(?:stable|unchanged|maintained|sustained)", "stable"),

        # Functional
        (r"(?:returned|able)\s+to\s+(?:work|school|activities|normal)", "functional_recovery"),
        (r"(?:unable|difficulty|impaired)\s+(?:to\s+)?(?:work|walk|function|perform)", "functional_impairment"),
        (r"(?:wheelchair|bedbound|bed[\s-]?bound|housebound|house[\s-]?bound)", "severe_disability"),
        (r"(?:quality\s+of\s+life)\s+(?:improved|decreased|impaired)", "qol"),
    ]

    def extract_from_sentences(self, sentences: List[str]) -> List[dict]:
        """Extract outcome mentions."""
        neg = get_detector()
        results = []

        for sent in sentences:
            sent_lower = sent.lower()
            for pat_str, outcome_type in self.OUTCOME_PATTERNS:
                m = re.search(pat_str, sent_lower)
                if m:
                    is_neg, trigger = neg.is_negated(sent, m.start(), m.end())
                    results.append({
                        "outcome_type": outcome_type,
                        "negated": is_neg,
                        "sentence": sent[:200],
                    })

        return results


# ── Family history extraction ──────────────────────────────────────────

class FamilyHistoryExtractor:
    """Extract family history details beyond boolean yes/no."""

    FAMILY_PATTERNS = [
        (r"(?:family\s+history\s+(?:of|positive\s+for|significant\s+for|notable\s+for|includes?))\s+(.{5,80}?)(?:\.|,|;|$)", "fh_positive"),
        (r"(?:family\s+history\s+(?:was|is)\s+(?:positive|significant|notable))\s+(?:for\s+)?(.{5,80}?)(?:\.|,|;|$)", "fh_positive"),
        (r"(?:mother|father|sister|brother|sibling|parent|daughter|son|aunt|uncle|grandmother|grandfather|cousin)"
         r"\s+(?:with|had|has|diagnosed|affected|suffered|also\s+had|who\s+had|who\s+has)\s+(.{5,80}?)(?:\.|,|;|$)", "relative_affected"),
        (r"(?:mother|father|sister|brother|sibling|parent|daughter|son|aunt|uncle|grandmother|grandfather|cousin)"
         r"\s+(?:was|were|is)\s+(?:also\s+)?(?:diagnosed|affected)", "relative_affected_short"),
        (r"(\d+)\s+(?:family\s+members?|relatives?)\s+(?:with|affected|diagnosed)", "relative_count"),
        (r"(?:autosomal\s+dominant|autosomal\s+recessive|x[\s-]?linked|inherited|hereditary|runs?\s+in\s+(?:the\s+)?family)", "inheritance_pattern"),
        (r"(?:no|negative|unremarkable|non[\s-]?contributory)\s+family\s+history", "fh_negative"),
        (r"family\s+history\s+(?:was\s+)?(?:negative|unremarkable|non[\s-]?contributory|not\s+significant)", "fh_negative"),
    ]

    RELATIVE_TERMS = {
        "mother", "father", "sister", "brother", "sibling", "parent",
        "daughter", "son", "aunt", "uncle", "grandmother", "grandfather",
        "cousin", "niece", "nephew", "maternal", "paternal",
    }

    def extract_from_sentences(self, sentences: List[str]) -> dict:
        """Extract family history information.

        Returns dict with: has_family_history, relatives_affected,
        conditions_in_family, details.
        """
        neg = get_detector()
        result = {
            "has_family_history": None,
            "relatives_affected": [],
            "conditions_in_family": [],
            "details": [],
        }

        for sent in sentences:
            sent_lower = sent.lower()

            # Check if sentence mentions family
            has_family_mention = (
                "family" in sent_lower
                or any(rel in sent_lower for rel in self.RELATIVE_TERMS)
            )
            if not has_family_mention:
                continue

            for pat_str, pat_type in self.FAMILY_PATTERNS:
                m = re.search(pat_str, sent_lower)
                if not m:
                    continue

                if pat_type == "fh_negative":
                    result["has_family_history"] = False
                    result["details"].append({
                        "type": "negative",
                        "sentence": sent[:200],
                    })

                elif pat_type == "fh_positive":
                    result["has_family_history"] = True
                    condition = m.group(1).strip()
                    if condition:
                        result["conditions_in_family"].append(condition)
                    result["details"].append({
                        "type": "positive",
                        "condition": condition,
                        "sentence": sent[:200],
                    })

                elif pat_type in ("relative_affected", "relative_affected_short"):
                    result["has_family_history"] = True
                    # Find which relative
                    for rel in self.RELATIVE_TERMS:
                        if rel in sent_lower:
                            condition = m.group(1).strip() if m.lastindex and m.lastindex >= 1 else ""
                            result["relatives_affected"].append({
                                "relative": rel,
                                "condition": condition,
                            })
                            if condition:
                                result["conditions_in_family"].append(condition)
                            break

                elif pat_type == "inheritance_pattern":
                    result["details"].append({
                        "type": "inheritance",
                        "sentence": sent[:200],
                    })

        # Deduplicate conditions
        result["conditions_in_family"] = list(set(result["conditions_in_family"]))

        return result


# ── Treatment-response linkage ────────────────────────────────────────

class TreatmentResponseLinker:
    """Link drug mentions to outcome mentions at sentence level.

    Inspired by PKPDAI model: for each drug, find the closest outcome
    mention in the same sentence or adjacent sentences, producing
    (drug, outcome, response_direction, evidence) tuples.
    """

    # Outcome signal patterns with direction
    RESPONSE_PATTERNS = [
        # Positive responses
        (r"(?:improved|resolved|remitted|stabilised|stabilized|controlled|effective|helpful|beneficial)", "improved"),
        (r"(?:significant|marked|notable|dramatic|substantial)\s+(?:improvement|reduction|relief|response)", "improved"),
        (r"(?:complete|partial|full|good)\s+(?:resolution|remission|recovery|response|relief)", "improved"),
        (r"(?:symptoms?\s+)?(?:resolved|abated|subsided|diminished|decreased|improved)", "improved"),
        (r"(?:responded|response)\s+(?:well|favorably|favourably|positively)", "improved"),
        (r"(?:tolerated)\s+(?:well)", "tolerated"),
        (r"(?:reduction|decrease|drop)\s+(?:in|of)\s+(?:symptoms?|episodes?|frequency|severity|pain)", "improved"),
        (r"no\s+(?:further|more|recurrence|relapse)", "improved"),

        # Negative responses
        (r"(?:no\s+)?(?:improvement|response|benefit|effect|relief)", "no_improvement"),
        (r"(?:worsened|deteriorated|exacerbated|aggravated|intolerant)", "worsened"),
        (r"(?:refractory|resistant|unresponsive|failed|failure)\s+(?:to)?", "refractory"),
        (r"(?:discontinued|stopped|switched|changed)\s+(?:due to|because|owing)", "discontinued"),
        (r"(?:adverse|side)\s+(?:effect|reaction)", "adverse_effect"),
        (r"(?:intolerance|intolerant|could not tolerate|unable to tolerate)", "intolerant"),

        # Neutral / ongoing
        (r"(?:maintained|maintained on|continued on|stable on|stabilised on)", "maintained"),
        (r"(?:started|initiated|commenced|begun|prescribed|placed on)", "initiated"),
    ]

    # Treatment verbs that signal a drug-response relationship
    TREATMENT_VERBS = re.compile(
        r"\b(?:treated|started|initiated|commenced|prescribed|given|administered|"
        r"received|placed\s+on|switched\s+to|changed\s+to|trialled?|tried|"
        r"responded\s+to|failed|discontinued|stopped|tapered|uptitrated|"
        r"tolerating|tolerated|maintained\s+on)\b",
        re.IGNORECASE,
    )

    def __init__(self, config: dict = None):
        if config is None:
            config = load_config()
        # Build drug lookup for matching
        self.drug_lookup = {}
        for drug_class, drugs in config.get("drug_classes", {}).items():
            for drug in drugs:
                self.drug_lookup[drug.lower()] = drug_class
        self.drug_patterns = []
        for drug_name in self.drug_lookup:
            pat = re.compile(r"\b" + re.escape(drug_name) + r"\b", re.IGNORECASE)
            self.drug_patterns.append((pat, drug_name))

    def link_from_sentences(self, sentences: List[str]) -> List[dict]:
        """Find treatment-response pairs across sentences.

        Strategy:
        1. For each sentence, find all drug mentions and all outcome signals.
        2. If a sentence has both a drug and an outcome, link them directly.
        3. If a sentence has a drug but no outcome, check the next sentence
           for an outcome (common pattern: "Patient was started on X.
           Symptoms improved over the following weeks.").
        4. If a sentence has an outcome but no drug, check the previous
           sentence for a drug mention.

        Returns list of {drug, drug_class, response, response_direction,
                         evidence_sentence, context_sentence}.
        """
        # Pre-scan: for each sentence, find drugs and outcomes
        sent_drugs = []  # list of list of (drug_name, drug_class)
        sent_outcomes = []  # list of list of (match_text, direction)

        for sent in sentences:
            # Find drugs in this sentence
            drugs_here = []
            for pat, drug_name in self.drug_patterns:
                if pat.search(sent):
                    drugs_here.append((drug_name, self.drug_lookup[drug_name]))
            sent_drugs.append(drugs_here)

            # Find outcomes in this sentence
            outcomes_here = []
            sent_lower = sent.lower()
            for pat_str, direction in self.RESPONSE_PATTERNS:
                m = re.search(pat_str, sent_lower)
                if m:
                    outcomes_here.append((m.group(0), direction))
            sent_outcomes.append(outcomes_here)

        # Now link drugs to outcomes
        results = []
        seen = set()  # (drug, direction) dedup

        for i, sent in enumerate(sentences):
            drugs_here = sent_drugs[i]
            outcomes_here = sent_outcomes[i]

            if not drugs_here and not outcomes_here:
                continue

            # Also require a treatment verb in the vicinity for higher precision
            has_treatment_verb = bool(self.TREATMENT_VERBS.search(sent))
            if i + 1 < len(sentences):
                has_treatment_verb = has_treatment_verb or bool(
                    self.TREATMENT_VERBS.search(sentences[i + 1])
                )

            # Case 1: same sentence has both drug and outcome
            if drugs_here and outcomes_here:
                for drug_name, drug_class in drugs_here:
                    for outcome_text, direction in outcomes_here:
                        key = (drug_name, direction)
                        if key not in seen:
                            seen.add(key)
                            results.append({
                                "drug": drug_name,
                                "drug_class": drug_class,
                                "response": outcome_text,
                                "response_direction": direction,
                                "linkage": "same_sentence",
                                "evidence_sentence": sent[:200],
                            })

            # Case 2: drug here, outcome in next sentence
            elif drugs_here and not outcomes_here and i + 1 < len(sentences):
                next_outcomes = sent_outcomes[i + 1]
                if next_outcomes and has_treatment_verb:
                    for drug_name, drug_class in drugs_here:
                        for outcome_text, direction in next_outcomes:
                            key = (drug_name, direction)
                            if key not in seen:
                                seen.add(key)
                                results.append({
                                    "drug": drug_name,
                                    "drug_class": drug_class,
                                    "response": outcome_text,
                                    "response_direction": direction,
                                    "linkage": "adjacent_sentence",
                                    "evidence_sentence": sent[:200],
                                    "context_sentence": sentences[i + 1][:200],
                                })

            # Case 3: outcome here, drug in previous sentence
            elif outcomes_here and not drugs_here and i > 0:
                prev_drugs = sent_drugs[i - 1]
                if prev_drugs and has_treatment_verb:
                    for drug_name, drug_class in prev_drugs:
                        for outcome_text, direction in outcomes_here:
                            key = (drug_name, direction)
                            if key not in seen:
                                seen.add(key)
                                results.append({
                                    "drug": drug_name,
                                    "drug_class": drug_class,
                                    "response": outcome_text,
                                    "response_direction": direction,
                                    "linkage": "adjacent_sentence",
                                    "evidence_sentence": sentences[i - 1][:200],
                                    "context_sentence": sent[:200],
                                })

        return results


# ── Comorbidity extraction ────────────────────────────────────────────

# Generic disease-mention recognisers for corpus-driven comorbidity discovery.
# These are morphological / relational — NOT tied to any specific disease — so
# they surface whatever other conditions the papers actually mention.
_CMRB_HEAD = (
    r"syndrome|disease|disorder|deficiency|insufficiency|failure|neuropathy|"
    r"myopathy|cardiomyopathy|nephropathy|retinopathy|malformation|hypertension|"
    r"hypotension|diabetes|asthma|epilepsy|migraine|depression|anxiety|apn[oe]a|"
    r"arthritis|colitis|dermatitis|hepatitis|carcinoma|lymphoma|leukaemia|leukemia|"
    r"anaemia|anemia|cancer|tumou?r|obesity|hypothyroidism|hyperthyroidism|"
    r"osteoporosis|fibromyalgia|psoriasis|psychosis|seizures?|encephalitis|"
    r"encephalopathy|myocarditis|pneumonia|thrombocytopenia|hypersomnia"
)
_CMRB_HEAD_RE = re.compile(r"\b((?:[a-z][a-z\-]+\s+){0,3}(?:" + _CMRB_HEAD + r"))\b", re.I)
_CMRB_SUFFIX_RE = re.compile(
    r"\b([a-z][a-z\-]{3,}(?:itis|aemia|emia|opathy|plasia|sclerosis|fibrosis|"
    r"stenosis|thrombosis|embolism))\b", re.I)
_CMRB_CUE_RE = re.compile(
    r"(?:history of|h/o|known|pre-?existing|underlying|comorbid|co-?morbid|"
    r"coexisting|concurrent|concomitant|background of|complicated by|secondary to|"
    r"diagnosed with|diagnosis of|suffer(?:ed|ing)? from)\s+"
    r"((?:[a-z0-9][a-z0-9\-]+\s+){0,4}[a-z0-9][a-z0-9\-]+)", re.I)
# Words that are not diseases even though they may match the patterns above.
_CMRB_STOP = {
    "disease", "disorder", "syndrome", "condition", "symptoms", "symptom", "history",
    "illness", "surgery", "trauma", "injury", "infection", "fever", "pain", "smoking",
    "alcohol", "pregnancy", "treatment", "therapy", "medication", "family", "episodes",
    "problems", "abnormality", "abnormalities", "findings", "diagnosis", "prognosis",
    "diagnoses", "process", "complaint", "complaints", "disease process",
}
# Leading filler stripped from a candidate phrase (determiners, severity, conjunctions).
_CMRB_LEAD = re.compile(
    r"^(?:a|an|the|his|her|their|its|chronic|acute|severe|mild|moderate|recurrent|"
    r"known|possible|suspected|presumed|probable|underlying|significant|multiple|"
    r"other|some|this|that|new|recent|and|or|with|of|both|including|namely|no|prior|"
    r"past|longstanding|long-standing|bilateral|left|right)\s+", re.I)


class ComorbidityExtractor:
    """Extract comorbidities from case reports.

    Three modes, chosen in __init__:
      * Configured: use comorbidity_patterns supplied in the config (when the
        user named specific comorbidities to detect).
      * Discovery (default when none are supplied): mine *other* diseases
        actually mentioned in the papers via morphological + relational cues,
        excluding the primary condition(s). This replaces the old behaviour of
        falling back to a hardcoded EDS/POTS/MCAS triad list.
      * Legacy triad list: only when config sets
        ``use_legacy_comorbidity_patterns`` true (kept for the original project).
    """

    # Legacy hardcoded patterns (fallback when config has no comorbidity_patterns)
    _LEGACY_PATTERNS = {
        # Craniocervical
        "chiari_malformation": [
            r"chiari\s*(?:malformation|type\s*[i1])", r"arnold[\s-]?chiari",
            r"cerebellar\s+(?:tonsillar?\s+)?(?:ectopia|herniation|descent)",
        ],
        "craniocervical_instability": [
            r"craniocervical\s+instability", r"\bcci\b",
            r"atlantoaxial\s+instability", r"\baai\b",
            r"basilar\s+(?:invagination|impression)",
        ],
        "tethered_cord": [
            r"tethered\s+(?:spinal\s+)?cord", r"filum\s+terminale",
        ],
        # Vascular compressions
        "median_arcuate_ligament_syndrome": [
            r"median\s+arcuate\s+ligament", r"\bmals\b",
            r"celiac\s+(?:artery\s+)?compression",
        ],
        "nutcracker_syndrome": [
            r"nutcracker\s+syndrome", r"\bncs\b(?!.*newcastle)",
            r"renal\s+vein\s+(?:compression|entrapment)",
        ],
        "superior_mesenteric_artery_syndrome": [
            r"superior\s+mesenteric\s+artery\s+syndrome", r"\bsmas\b",
        ],
        "may_thurner_syndrome": [
            r"may[\s-]?thurner", r"iliac\s+vein\s+compression",
        ],
        "thoracic_outlet_syndrome": [
            r"thoracic\s+outlet\s+syndrome", r"\btos\b(?=.*(?:thoracic|nerve|vascular))",
        ],
        # GI / motility
        "gastroparesis": [
            r"gastroparesis", r"delayed\s+gastric\s+emptying",
        ],
        # Gynaecological
        "endometriosis": [
            r"endometriosis", r"endometriotic",
        ],
        # Neurological
        "small_fibre_neuropathy": [
            r"small\s+fib(?:re|er)\s+neuropathy", r"\bsfn\b",
            r"intraepidermal\s+nerve\s+fiber\s+density",
        ],
        "dysautonomia": [
            r"dysautonomia", r"autonomic\s+(?:dysfunction|neuropathy|failure)",
        ],
        # Sleep
        "sleep_disorder": [
            r"sleep\s+apn[oe]a", r"insomnia", r"sleep\s+disorder",
            r"restless\s+leg", r"narcolepsy",
        ],
        # Immunological
        "immunodeficiency": [
            r"immunodeficiency", r"immunoglobulin\s+deficiency",
            r"low\s+(?:igg|iga|igm)", r"hypogammaglobulin",
        ],
        # TMJ
        "tmj_dysfunction": [
            r"temporomandibular\s+(?:joint\s+)?(?:dysfunction|disorder)",
            r"\btmj\b", r"\btmd\b",
        ],
    }

    def __init__(self, config: Optional[dict] = None):
        """Initialise with optional config dict.

        Picks configured patterns if present, the legacy triad list only when
        explicitly requested, otherwise corpus-driven discovery (the default).
        """
        self._patterns = {}
        self._discovery = False
        self._primary_re = None
        config = config or {}

        if config.get("comorbidity_patterns"):
            cp = config["comorbidity_patterns"]
            for slug, entry in cp.items():
                if isinstance(entry, dict) and "patterns" in entry:
                    # Schema v3: {canonical, mondo_id, patterns}
                    self._patterns[slug] = entry["patterns"]
                elif isinstance(entry, list):
                    # Simple list of patterns
                    self._patterns[slug] = entry
        elif config.get("use_legacy_comorbidity_patterns"):
            self._patterns = dict(self._LEGACY_PATTERNS)
        else:
            # Discovery mode: detect other diseases mentioned in the papers,
            # excluding the primary condition(s) so the disease under study is
            # never reported as its own comorbidity.
            self._discovery = True
            prim = []
            for slug, entry in (config.get("condition_terms") or {}).items():
                prim.extend((entry or {}).get("patterns", []) or [])
                canon = (entry or {}).get("canonical")
                if canon:
                    prim.append(re.escape(canon.lower()))
                prim.append(re.escape(slug.lower().replace("_", " ")))
            if prim:
                try:
                    self._primary_re = re.compile("|".join(p for p in prim if p), re.I)
                except re.error:
                    self._primary_re = None

    def _clean_candidate(self, phrase: str) -> Optional[str]:
        """Normalise a discovered disease phrase; return None if it's not a
        plausible, non-primary disease mention."""
        p = re.sub(r"\s+", " ", (phrase or "").strip().lower())
        prev = None
        while prev != p:                       # strip leading filler repeatedly
            prev = p
            p = _CMRB_LEAD.sub("", p)
        # If a relational cue word slipped in, keep only the tail after it.
        if "history" in p.split():
            p = p.split("history")[-1].lstrip(" of")
        p = p.strip(" ,.;:")
        toks = p.split()
        if not toks or len(toks) > 5 or len(p) < 4:
            return None
        if p in _CMRB_STOP or toks[-1] in _CMRB_STOP:
            return None
        if self._primary_re and self._primary_re.search(p):
            return None
        return p

    def _discover(self, sentences: List[str]) -> dict:
        """Mine disease mentions from the corpus text (one article's sentences)."""
        neg = get_detector()
        results = {}
        for sent in sentences:
            low = sent.lower()
            for rx in (_CMRB_CUE_RE, _CMRB_HEAD_RE, _CMRB_SUFFIX_RE):
                for m in rx.finditer(low):
                    name = self._clean_candidate(m.group(1))
                    if not name:
                        continue
                    neg_status, _ = neg.is_negated(sent, m.start(1), m.end(1))
                    prev = results.get(name)
                    if prev is None or (prev["negated"] and not neg_status):
                        results[name] = {
                            "mentioned": True,
                            "negated": neg_status,
                            "sentence": sent[:200],
                        }
        return results

    def extract_from_sentences(self, sentences: List[str]) -> dict:
        """Extract comorbidity mentions with negation awareness.

        Returns dict of {comorbidity_name: {mentioned: bool, negated: bool,
                         sentence: str}}.
        """
        if self._discovery:
            return self._discover(sentences)

        neg = get_detector()
        results = {}

        for comorb_name, patterns in self._patterns.items():
            found = False
            is_negated = False
            evidence_sent = ""

            for sent in sentences:
                sent_lower = sent.lower()
                for pat in patterns:
                    m = re.search(pat, sent_lower)
                    if m:
                        neg_status, trigger = neg.is_negated(sent, m.start(), m.end())
                        if not found or (found and is_negated and not neg_status):
                            # Prefer affirmed over negated
                            found = True
                            is_negated = neg_status
                            evidence_sent = sent[:200]
                        break
                if found and not is_negated:
                    break  # Found affirmed mention, no need to keep looking

            if found:
                results[comorb_name] = {
                    "mentioned": True,
                    "negated": is_negated,
                    "sentence": evidence_sent,
                }

        return results
