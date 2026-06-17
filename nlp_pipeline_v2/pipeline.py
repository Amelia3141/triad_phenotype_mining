"""
Main NLP extraction pipeline.

Usage:
    python -m nlp_pipeline_v2.pipeline --input /path/to/fulltext/ --output /path/to/output.json
    python -m nlp_pipeline_v2.pipeline --single PMC12345678.xml  # single file test

Runs all extractors on each article and produces a structured JSON output.
"""

import argparse
import json
import os
import re
import sys
import datetime
from typing import Dict, List, Optional

from .text_processing import (
    parse_nxml_sections, get_clinical_text, get_case_sentences,
    get_patient_sentences, normalise_text, extract_publication_metadata,
)
from .extractors import (
    DrugExtractor, TemporalExtractor, MeasurementExtractor,
    OutcomeExtractor, FamilyHistoryExtractor, TreatmentResponseLinker,
    ComorbidityExtractor, load_config,
)
from .negation import NegationDetector
from .pipeline_log import PipelineLog
from .llm_enhancer import LLMEnhancer


class NLPExtractionPipeline:
    """Orchestrates all extractors on a single article."""

    def __init__(
        self,
        config: dict = None,
        log: Optional[PipelineLog] = None,
        llm_enhancer: Optional[LLMEnhancer] = None,
    ):
        self._using_default_config = config is None
        self.config = config if config is not None else load_config()
        self.log = log
        self.llm_enhancer = llm_enhancer
        self.drug_extractor = DrugExtractor(self.config)
        self.temporal_extractor = TemporalExtractor()
        self.measurement_extractor = MeasurementExtractor(self.config)
        self.outcome_extractor = OutcomeExtractor()
        self.family_history_extractor = FamilyHistoryExtractor()
        self.treatment_linker = TreatmentResponseLinker(self.config)
        self.comorbidity_extractor = ComorbidityExtractor(config=self.config)
        self.negation_detector = NegationDetector(
            pre_negation=self.config.get("negation_triggers", {}).get("pre"),
            post_negation=self.config.get("negation_triggers", {}).get("post"),
        )
        self.section_blacklist = self.config.get("section_blacklist", [])

        if self.log:
            self.log.section("Pipeline Initialisation")
            self.log.parameter(
                "schema_version",
                self.config.get("schema_version", "unknown"),
            )
            self.log.parameter(
                "source_diseases",
                self.config.get("source_diseases", []),
            )
            self.log.parameter(
                "symptom_categories",
                len(self.config.get("symptom_patterns", {})),
            )
            self.log.parameter(
                "comorbidity_categories",
                len(self.config.get("comorbidity_patterns", {})),
            )
            self.log.parameter(
                "drug_classes",
                len(self.config.get("drug_classes", {})),
            )
            self.log.parameter(
                "negation_pre_triggers",
                len(self.config.get("negation_triggers", {}).get("pre", [])),
            )
            if self.llm_enhancer:
                self.log.parameter("llm_provider", self.llm_enhancer.provider)
                self.log.parameter("llm_model", self.llm_enhancer.model)
            self._articles_processed = 0
            self._articles_failed = 0

    def extract_from_xml(self, xml_path: str) -> dict:
        """Run full extraction on a single XML file.

        Returns structured extraction dict.
        """
        pmcid = os.path.basename(xml_path).replace(".xml", "")

        with open(xml_path, "r", encoding="utf-8") as f:
            xml_data = f.read()

        return self.extract_from_xml_string(xml_data, pmcid)

    # Article types considered suitable for individual patient extraction
    CASE_REPORT_TYPES = {
        "case report", "case reports", "case-report", "case study",
        "case series", "case report and case series", "case presentation",
        "clinical case", "brief report", "brief communication",
        "images in", "letter", "correspondence",
    }

    def _is_case_report(self, pub_metadata: dict) -> bool:
        """Check if article is a case report or similar individual-patient article."""
        article_type = (pub_metadata.get("article_type") or "").lower().strip()
        article_type_attr = (pub_metadata.get("article_type_attr") or "").lower().strip()

        # Check the article-type attribute first (most reliable)
        if article_type_attr in ("case-report", "case-reports", "case-study"):
            return True

        # Check the subject heading
        for ct in self.CASE_REPORT_TYPES:
            if ct in article_type:
                return True

        # Some journals use generic "article" but the title might say "case report"
        title = (pub_metadata.get("title") or "").lower()
        if any(kw in title for kw in ["case report", "case study", "case series",
                                       "a case of", "a rare case"]):
            return True

        return False

    def extract_from_xml_string(self, xml_string: str, pmcid: str = "unknown") -> dict:
        """Run full extraction on XML string."""

        # ── Publication metadata (from front matter) ──
        pub_metadata = extract_publication_metadata(xml_string)

        # ── Article type filter: skip non-case-report articles ──
        if not self._is_case_report(pub_metadata):
            article_type = pub_metadata.get("article_type", "unknown")
            if self.log:
                self._articles_failed += 1
                self.log.warning(f"{pmcid}: skipped (type: {article_type})")
            return {
                "pmcid": pmcid,
                "error": "not_case_report",
                "article_type": article_type,
                "extraction_method": "nlp_v2",
                "publication_metadata": pub_metadata,
            }

        # Parse sections
        sections = parse_nxml_sections(xml_string)
        if not sections:
            if self.log:
                self._articles_failed += 1
                self.log.warning(f"{pmcid}: parse_failed")
            return {"pmcid": pmcid, "error": "parse_failed", "extraction_method": "nlp_v2",
                    "publication_metadata": pub_metadata}

        # Get clinical text and sentences (excluding references etc.)
        clinical_text, all_sentences = get_clinical_text(sections, self.section_blacklist)
        case_sentences = get_case_sentences(sections, self.section_blacklist)
        # Patient-specific sentences (abstract + case, literature filtered).
        # This is the correct scope for per-patient attributes and avoids
        # false positives from discussion/introduction sections.
        patient_sentences = get_patient_sentences(sections, self.section_blacklist)

        if not all_sentences:
            if self.log:
                self._articles_failed += 1
                self.log.warning(f"{pmcid}: no_text")
            return {"pmcid": pmcid, "error": "no_text", "extraction_method": "nlp_v2"}

        # Safety net: if zone/literature filtering removed everything, fall
        # back to all clinical sentences so recall does not collapse.
        if not patient_sentences:
            patient_sentences = all_sentences

        # ── Demographics (reuse existing age/sex regex, they work well) ──
        age_at_presentation = self._extract_age(case_sentences or patient_sentences)
        sex = self._extract_sex(case_sentences or patient_sentences, all_sentences)

        # ── Temporal extraction (NLP-enhanced) ──
        # Restricted to patient sentences: onset/delay statements about the
        # index patient, not durations quoted from the literature.
        temporal = self.temporal_extractor.extract_from_sentences(
            patient_sentences,
            age_at_presentation=age_at_presentation
        )

        # ── Drug extraction (dictionary NER) ──
        drugs = self.drug_extractor.extract_from_sentences(patient_sentences)
        affirmed_drugs = [d for d in drugs if not d["negated"]]
        negated_drugs = [d for d in drugs if d["negated"]]

        # ── Measurements ──
        measurements = self.measurement_extractor.extract_from_sentences(patient_sentences)

        # ── Outcomes ──
        outcomes = self.outcome_extractor.extract_from_sentences(patient_sentences)

        # ── Family history ──
        family_history = self.family_history_extractor.extract_from_sentences(patient_sentences)

        # ── Treatment-response linkage (NEW) ──
        treatment_responses = self.treatment_linker.link_from_sentences(patient_sentences)

        # ── Comorbidities (NEW, expanded beyond 20 symptom categories) ──
        comorbidities = self.comorbidity_extractor.extract_from_sentences(patient_sentences)

        # ── Condition detection ──
        # Intentionally uses ALL sentences: whether a condition is named
        # anywhere in the article (incl. discussion) is meaningful for
        # cohort definition, unlike per-patient findings.
        conditions = self._detect_conditions(all_sentences)

        # ── Symptom extraction with negation ──
        # Use patient sentences (abstract + case); fall back to all if empty.
        symptoms = self._extract_symptoms_with_negation(patient_sentences)
        if not symptoms:
            symptoms = self._extract_symptoms_with_negation(all_sentences)

        # ── Negative findings ──
        negative_findings = self._extract_negative_findings(patient_sentences)

        # ── Build result ──
        result = {
            "pmcid": pmcid,
            "extraction_method": "nlp_v2",
            "extraction_date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "sentence_count": len(all_sentences),
            "case_sentence_count": len(case_sentences),
            "patient_sentence_count": len(patient_sentences),

            # Publication metadata (NEW)
            "publication_metadata": pub_metadata,

            # Demographics
            "age_at_presentation": age_at_presentation,
            "sex": sex,

            # Temporal (NEW)
            "age_at_onset": temporal["age_at_onset"],
            "age_at_onset_qualitative": temporal["age_at_onset_qualitative"],
            "onset_evidence": temporal["onset_evidence"],
            "symptom_duration_years": temporal["symptom_duration_years"],
            "diagnostic_delay_years": temporal["diagnostic_delay_years"],
            "delay_evidence": temporal["delay_evidence"],
            "misdiagnoses": temporal["misdiagnoses"],
            "referral_pathway": temporal["referral_pathway"],

            # Drugs (NEW)
            "drugs_affirmed": affirmed_drugs,
            "drugs_negated": negated_drugs,
            "drug_count": len(affirmed_drugs),

            # Measurements (NEW)
            "measurements": {k: v for k, v in measurements.items() if v},

            # Outcomes (NEW)
            "outcomes": outcomes,

            # Family history (NEW)
            "family_history": family_history,

            # Treatment-response linkage (NEW)
            "treatment_responses": treatment_responses,

            # Comorbidities (NEW, expanded)
            "comorbidities": comorbidities,

            # Conditions
            "conditions": conditions,

            # Symptoms (with negation)
            "symptoms_affirmed": [s for s in symptoms if not s["negated"]],
            "symptoms_negated": [s for s in symptoms if s["negated"]],

            # Negative findings (NEW)
            "negative_findings": negative_findings,
        }

        # ── Completeness indicators ──
        result["completeness"] = self._compute_completeness(result)
        self._promote_completeness_summary(result)

        # ── Optional LLM enhancement (SPELL-style) ──
        if self.llm_enhancer:
            try:
                result = self.llm_enhancer.enhance_extraction(result, patient_sentences)
                # Recompute completeness after LLM may have filled gaps
                result["completeness"] = self._compute_completeness(result)
                self._promote_completeness_summary(result)
            except Exception as e:
                if self.log:
                    self.log.warning(f"{pmcid}: LLM enhancement failed: {e}")
                result["_llm_enhanced"] = False
                result["_llm_error"] = str(e)

        if self.log:
            self._articles_processed += 1
            summary = result["completeness"].get("_summary", {})
            llm_tag = " [+LLM]" if result.get("_llm_enhanced") else ""
            if self._articles_processed % 100 == 0 or self._articles_processed <= 5:
                self.log.detail(
                    f"{pmcid}{llm_tag}: {summary.get('reported', 0)} reported, "
                    f"{summary.get('absent', 0)} absent, "
                    f"{len(result.get('symptoms_affirmed', []))} symptoms, "
                    f"{len(result.get('drugs_affirmed', []))} drugs, "
                    f"{len(result.get('comorbidities', {}))} comorbidities"
                )

        return result

    def _compute_completeness(self, result: dict) -> dict:
        """Compute 3-way completeness status for each major field.

        Status is one of:
        - "reported": value was extracted (positive finding)
        - "absent": explicitly negated or denied
        - "not_mentioned": no information found either way

        This is critical for NSD: knowing what's missing vs what was
        looked for and not found.
        """
        completeness = {}

        # Demographics
        completeness["age"] = "reported" if result.get("age_at_presentation") is not None else "not_mentioned"
        completeness["sex"] = "reported" if result.get("sex") else "not_mentioned"

        # Temporal
        completeness["age_at_onset"] = (
            "reported" if result.get("age_at_onset") is not None else "not_mentioned"
        )
        completeness["symptom_duration"] = (
            "reported" if result.get("symptom_duration_years") is not None else "not_mentioned"
        )
        completeness["diagnostic_delay"] = (
            "reported" if result.get("diagnostic_delay_years") is not None else "not_mentioned"
        )

        # Conditions
        conditions = result.get("conditions", {})
        for cond_name, cond_data in conditions.items():
            completeness[f"condition_{cond_name}"] = (
                "reported" if cond_data.get("mentioned") else "not_mentioned"
            )

        # Symptoms: reported if affirmed, absent if only negated, not_mentioned otherwise
        affirmed_symptoms = {s["symptom"] for s in result.get("symptoms_affirmed", [])}
        negated_symptoms = {s["symptom"] for s in result.get("symptoms_negated", [])}
        # Get all possible symptom names from config (or from what was extracted)
        config_symptoms = self.config.get("symptom_patterns", {})
        known_symptoms = set(config_symptoms.keys()) if config_symptoms else (
            affirmed_symptoms | negated_symptoms
        )
        for sym in known_symptoms:
            if sym in affirmed_symptoms:
                completeness[f"symptom_{sym}"] = "reported"
            elif sym in negated_symptoms:
                completeness[f"symptom_{sym}"] = "absent"
            else:
                completeness[f"symptom_{sym}"] = "not_mentioned"

        # Drugs
        completeness["medications"] = (
            "reported" if result.get("drugs_affirmed") else "not_mentioned"
        )

        # Measurements
        measurements = result.get("measurements", {})
        for meas_name, meas_list in measurements.items():
            if meas_list:
                completeness[f"measurement_{meas_name}"] = "reported"
            else:
                completeness[f"measurement_{meas_name}"] = "not_mentioned"
        # Add all config measurements that might not have results
        for std_meas in self.config.get("measurement_patterns", {}).keys():
            if f"measurement_{std_meas}" not in completeness:
                completeness[f"measurement_{std_meas}"] = "not_mentioned"

        # Family history
        fh = result.get("family_history", {})
        if fh.get("has_family_history") is True:
            completeness["family_history"] = "reported"
        elif fh.get("has_family_history") is False:
            completeness["family_history"] = "absent"
        else:
            completeness["family_history"] = "not_mentioned"

        # Outcomes
        completeness["treatment_outcomes"] = (
            "reported" if result.get("outcomes") else "not_mentioned"
        )

        # Treatment-response
        completeness["treatment_response_linkage"] = (
            "reported" if result.get("treatment_responses") else "not_mentioned"
        )

        # Comorbidities
        comorbidities = result.get("comorbidities", {})
        for comorb_name, comorb_data in comorbidities.items():
            if comorb_data.get("negated"):
                completeness[f"comorbidity_{comorb_name}"] = "absent"
            else:
                completeness[f"comorbidity_{comorb_name}"] = "reported"

        # Summary counts
        reported = sum(1 for v in completeness.values() if v == "reported")
        absent = sum(1 for v in completeness.values() if v == "absent")
        not_mentioned = sum(1 for v in completeness.values() if v == "not_mentioned")
        total = len(completeness)
        completeness["_summary"] = {
            "total_fields": total,
            "reported": reported,
            "absent": absent,
            "not_mentioned": not_mentioned,
            "completeness_score": round(reported / total, 3) if total > 0 else 0,
            "coverage_score": round((reported + absent) / total, 3) if total > 0 else 0,
        }

        return completeness

    @staticmethod
    def _promote_completeness_summary(result: dict):
        """Copy completeness summary values to top-level keys for convenience."""
        summary = result.get("completeness", {}).get("_summary", {})
        result["_completeness_score"] = summary.get("completeness_score")
        result["_coverage_score"] = summary.get("coverage_score")
        result["_n_reported"] = summary.get("reported")
        result["_n_absent"] = summary.get("absent")
        result["_n_not_mentioned"] = summary.get("not_mentioned")

    def start_batch_log(self, total_articles: int):
        """Start a log section for a batch extraction run."""
        if self.log:
            self.log.section("Batch Extraction")
            self.log.parameter("total_articles", total_articles)
            self._articles_processed = 0
            self._articles_failed = 0

    def finalise_log(self):
        """Write summary stats and close the log."""
        if self.log:
            self.log.section("Extraction Summary")
            self.log.result(
                "Batch extraction complete",
                articles_processed=getattr(self, "_articles_processed", 0),
                articles_failed=getattr(self, "_articles_failed", 0),
            )
            if self.llm_enhancer:
                stats = self.llm_enhancer.get_stats()
                self.log.parameter("llm_total_calls", stats["total_calls"])
                self.log.parameter("llm_total_tokens", stats["total_tokens"])
            self.log.close()

    def _extract_age(self, sentences: List[str]) -> Optional[float]:
        """Extract age at presentation from case sentences."""
        patterns = [
            (r"(\d{1,3})[\s-]*year[\s-]*old", "years"),
            (r"age[d]?\s*(?:of\s*)?(\d{1,3})\b", "years"),
            (r"(\d{1,3})[\s-]*yo\b", "years"),
            (r"(\d{1,3})\s*years?\s*of\s*age", "years"),
            (r"(\d{1,3})[\s-]*month[\s-]*old", "months"),
            (r"(?:patient|woman|man|female|male|girl|boy),?\s*(?:aged?\s*)?(\d{1,3})", "years"),
        ]

        for sent in sentences[:10]:  # Age is usually in the first few sentences
            sent_lower = sent.lower()
            for pat, unit in patterns:
                m = re.search(pat, sent_lower)
                if m:
                    age = int(m.group(1))
                    if unit == "months":
                        age = round(age / 12, 1)
                    if 0 < age < 120:
                        return age

        return None

    def _extract_sex(self, case_sentences: List[str], all_sentences: List[str]) -> Optional[str]:
        """Extract sex from case sentences, with fallback to all sentences.

        Searches all case sentences (not just the first 10), using a cascade of
        patterns from most specific to most general.
        """
        female_terms = {"female", "woman", "girl", "lady", "mother", "daughter", "sister"}
        male_terms = {"male", "man", "boy", "gentleman", "father", "son", "brother"}

        for sentences in [case_sentences, all_sentences]:
            for sent in sentences:
                sent_lower = sent.lower()

                # Direct mention with age: "31-year-old man", "3-month-old girl"
                m = re.search(
                    r"\d+[\s-]*(?:year|month|week|day)[\s-]*old\s+"
                    r"(female|woman|girl|lady|male|man|boy|gentleman)",
                    sent_lower,
                )
                if m:
                    return "female" if m.group(1) in female_terms else "male"

                # "A/The male/female patient", "male/female, aged"
                m = re.search(
                    r"\b(female|male)\b\s*(?:patient|child|infant|neonate|adolescent|adult|,|aged|\d)",
                    sent_lower,
                )
                if m:
                    return "female" if m.group(1) == "female" else "male"

                # Shorthand: "(M)", "(F)", "sex: M", "gender: female"
                m = re.search(r"(?:sex|gender)\s*[:=]\s*(male|female|m|f)\b", sent_lower)
                if m:
                    return "female" if m.group(1) in ("female", "f") else "male"
                m = re.search(r"\(\s*([MF])\s*\)", sent)  # case-sensitive for M/F
                if m:
                    return "female" if m.group(1) == "F" else "male"

                # "woman/man/girl/boy with", "woman/man/girl/boy presented"
                m = re.search(
                    r"\b(woman|man|girl|boy|lady|gentleman)\b\s+"
                    r"(?:with|who|presented|was|had|diagnosed|aged|referred)",
                    sent_lower,
                )
                if m:
                    return "female" if m.group(1) in female_terms else "male"

                # Pronoun-based (broad verb set)
                if re.search(r"\bshe\s+(?:was|had|is|has|presented|reported|denied|complained|developed|underwent|received)", sent_lower):
                    return "female"
                if re.search(r"\bhe\s+(?:was|had|is|has|presented|reported|denied|complained|developed|underwent|received)", sent_lower):
                    return "male"
                if re.search(r"\bher\s+(?:past|medical|surgical|family|social|history|symptoms|condition|treatment|examination)", sent_lower):
                    return "female"
                if re.search(r"\bhis\s+(?:past|medical|surgical|family|social|history|symptoms|condition|treatment|examination)", sent_lower):
                    return "male"

        return None

    def _detect_conditions(self, sentences: List[str]) -> dict:
        """Detect conditions mentioned in the article."""
        conditions = {}
        condition_terms = self.config.get("condition_terms", {})

        for cond_name, cond_conf in condition_terms.items():
            patterns = cond_conf.get("patterns", [])
            found = False
            for sent in sentences:
                sent_lower = sent.lower()
                for pat in patterns:
                    if re.search(pat, sent_lower):
                        found = True
                        break
                if found:
                    break

            conditions[cond_name] = {"mentioned": found}

            # Check subtypes
            subtypes = cond_conf.get("subtypes", {})
            for sub_name, sub_patterns in subtypes.items():
                sub_found = False
                for sent in sentences:
                    sent_lower = sent.lower()
                    for pat in sub_patterns:
                        if re.search(pat, sent_lower):
                            sub_found = True
                            break
                    if sub_found:
                        break
                conditions[f"{cond_name}_{sub_name}"] = {"mentioned": sub_found}

        return conditions

    def _extract_symptoms_with_negation(self, sentences: List[str]) -> List[dict]:
        """Extract symptoms with negation awareness.

        Reads symptom patterns from config (schema v3: symptom_patterns dict
        with HPO-derived patterns) or falls back to legacy v2 patterns.
        """
        # Try config-driven symptom patterns first (schema v3.0)
        config_symptoms = self.config.get("symptom_patterns", {})

        if config_symptoms and any("patterns" in v for v in config_symptoms.values() if isinstance(v, dict)):
            # Schema v3: HPO-derived patterns
            symptom_patterns = {}
            for slug, spec in config_symptoms.items():
                if isinstance(spec, dict) and "patterns" in spec:
                    symptom_patterns[slug] = spec["patterns"]
                elif isinstance(spec, list):
                    symptom_patterns[slug] = spec
        elif self._using_default_config:
            # Legacy fallback: hardcoded v2 patterns for backward compat
            symptom_patterns = {
                "joint_hypermobility": [r"joint\s+hypermobil", r"hypermobil(?:e|ity)", r"beighton\s+score",
                                        r"generalised\s+(?:joint\s+)?laxity", r"double[\s-]?jointed"],
                "subluxations_dislocations": [r"subluxat", r"dislocat", r"joint\s+instabil"],
                "chronic_pain": [r"chronic\s+pain", r"widespread\s+pain", r"fibromyalg", r"myalgia", r"arthralgia"],
                "skin_hyperextensibility": [r"skin\s+hyperextensib", r"skin\s+elasticity", r"stretchy\s+skin",
                                            r"velvety\s+skin", r"skin\s+fragil", r"atrophic\s+scar"],
                "easy_bruising": [r"easy\s+bruis", r"bruising\s+easily", r"ecchymos"],
                "tachycardia": [r"tachycardi", r"heart\s+rate\s+(?:increase|elevation|rise)", r"rapid\s+heart"],
                "syncope": [r"syncop", r"presyncop", r"pre-syncop", r"faint", r"loss\s+of\s+consciousness"],
                "orthostatic_intolerance": [r"orthostatic\s+intolerance", r"orthostatic\s+hypotension",
                                            r"postural\s+(?:intolerance|hypotension)"],
                "palpitations": [r"palpitat"],
                "mitral_valve_prolapse": [r"mitral\s+valve\s+prolapse"],
                "flushing": [r"flush(?:ing|ed)", r"facial\s+flush"],
                "urticaria": [r"urticar", r"hives", r"wheal"],
                "anaphylaxis": [r"anaphyla"],
                "fatigue": [r"fatigu", r"exhausti", r"lethargy", r"malaise"],
                "gi_symptoms": [r"nausea", r"vomit", r"diarr", r"constipat", r"bloat", r"abdominal\s+pain",
                                r"gastropar", r"dysphagia", r"reflux"],
                "headache_migraine": [r"headache", r"migraine"],
                "neuropathy": [r"neuropath", r"small\s+fiber", r"small\s+fibre", r"paresthes", r"paraesthes",
                               r"numbness", r"tingling"],
                "brain_fog": [r"brain\s+fog", r"cognitive\s+(?:dysfunction|impairment)", r"difficulty\s+concentrat"],
                "medication_sensitivity": [r"medication\s+sensitiv", r"drug\s+(?:sensitiv|intoleran|reaction)",
                                           r"adverse\s+(?:drug|medication)\s+react"],
                "chiari": [r"chiari", r"arnold-chiari"],
            }
        else:
            # An explicit user-generated config can legitimately have no HPO
            # phenotypes (e.g. rare diseases without OMIM/ORPHA annotations, or
            # free-text diseases not present in MONDO). Do not silently fall
            # back to the repository's EDS/POTS/MCAS defaults, because that
            # produces inaccurate symptoms for unrelated disease inputs.
            symptom_patterns = {}

        neg = self.negation_detector
        results = []
        seen_symptoms = {}  # symptom -> best (affirmed > negated)

        for sent in sentences:
            sent_lower = sent.lower()
            for symptom_name, patterns in symptom_patterns.items():
                for pat in patterns:
                    m = re.search(pat, sent_lower)
                    if m:
                        is_neg, trigger = neg.is_negated(sent, m.start(), m.end())

                        # Keep affirmed over negated for same symptom
                        if symptom_name in seen_symptoms:
                            if seen_symptoms[symptom_name]["negated"] and not is_neg:
                                # Upgrade to affirmed
                                seen_symptoms[symptom_name] = {
                                    "symptom": symptom_name,
                                    "negated": is_neg,
                                    "trigger": trigger,
                                    "sentence": sent[:200],
                                }
                        else:
                            seen_symptoms[symptom_name] = {
                                "symptom": symptom_name,
                                "negated": is_neg,
                                "trigger": trigger,
                                "sentence": sent[:200],
                            }
                        break  # Only need one match per symptom per sentence

        return list(seen_symptoms.values())

    def _extract_negative_findings(self, sentences: List[str]) -> List[dict]:
        """Extract explicitly negative clinical findings.

        These are valuable for the dataset: knowing what was tested
        and found negative is as important as positive findings.
        """
        neg_patterns = [
            r"(no\s+evidence\s+of\s+)(.{5,60}?)(?:\.|,|;|$)",
            r"(negative\s+for\s+)(.{5,60}?)(?:\.|,|;|$)",
            r"(ruled\s+out\s+)(.{5,60}?)(?:\.|,|;|$)",
            r"(absence\s+of\s+)(.{5,60}?)(?:\.|,|;|$)",
            r"(no\s+signs?\s+of\s+)(.{5,60}?)(?:\.|,|;|$)",
            r"(normal\s+)(.{5,60}?)(?:\.|,|;|$)",
            r"(unremarkable\s+)(.{5,60}?)(?:\.|,|;|$)",
            r"(within\s+normal\s+limits:?\s*)(.{5,60}?)(?:\.|,|;|$)",
        ]

        # Filter out reference ranges and numeric-only findings
        def is_reference_range(finding: str) -> bool:
            """Reject findings that are just reference ranges or numbers."""
            # Pure numbers or ranges like "3.4-10.6" or "119-451 pg/ml"
            if re.match(r"^[\d.,\s\-/<>]+(?:\s*(?:pg|ng|mg|ug|ml|l|mmol|umol|g|iu|u|mmhg|bpm|%|/)[^\s]*)?$", finding, re.IGNORECASE):
                return True
            # Starts with a number or < > (likely a reference range context)
            if re.match(r"^[<>]?\d", finding) and len(finding) < 30:
                return True
            # Very short or meaningless
            if len(finding.strip()) < 5:
                return True
            return False

        results = []
        seen = set()

        for sent in sentences:
            sent_lower = sent.lower()
            for pat in neg_patterns:
                for m in re.finditer(pat, sent_lower):
                    finding = m.group(2).strip()
                    if finding and finding not in seen and len(finding) > 3 and not is_reference_range(finding):
                        seen.add(finding)
                        results.append({
                            "trigger": m.group(1).strip(),
                            "finding": finding,
                            "sentence": sent[:200],
                        })

        return results


def process_single(xml_path: str, config: dict = None) -> dict:
    """Process a single XML file and return extraction."""
    pipeline = NLPExtractionPipeline(config)
    return pipeline.extract_from_xml(xml_path)


def process_corpus(xml_dir: str, output_path: str, config: dict = None, max_articles: int = None):
    """Process all XMLs in a directory."""
    pipeline = NLPExtractionPipeline(config)

    xml_files = sorted([f for f in os.listdir(xml_dir) if f.endswith(".xml")])
    if max_articles:
        xml_files = xml_files[:max_articles]

    print(f"Processing {len(xml_files)} articles...")

    results = []
    errors = 0

    for i, fname in enumerate(xml_files):
        xml_path = os.path.join(xml_dir, fname)
        try:
            extraction = pipeline.extract_from_xml(xml_path)
            results.append(extraction)
            if extraction.get("error"):
                errors += 1
        except Exception as e:
            results.append({
                "pmcid": fname.replace(".xml", ""),
                "error": str(e),
                "extraction_method": "nlp_v2",
            })
            errors += 1

        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(xml_files)} processed ({errors} errors)")

    # Save results
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nDone. {len(results)} articles processed, {errors} errors.")
    print(f"Saved to {output_path}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NLP extraction pipeline for case reports")
    parser.add_argument("--input", help="Directory of XML files")
    parser.add_argument("--output", help="Output JSON path")
    parser.add_argument("--single", help="Process single XML file")
    parser.add_argument("--max", type=int, help="Max articles to process")
    parser.add_argument("--config", help="Config JSON path")

    args = parser.parse_args()

    config = None
    if args.config:
        with open(args.config) as f:
            config = json.load(f)

    if args.single:
        result = process_single(args.single, config)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.input and args.output:
        process_corpus(args.input, args.output, config, args.max)
    else:
        parser.print_help()
