"""
LLM enhancement layer for the NLP extraction pipeline.

SPELL-style hybrid architecture: the rule-based pipeline identifies
relevant sentences (snippets), and the LLM reasons over just those
snippets for three specific subtasks where regex is weakest:

1. Temporal reasoning (diagnostic delay, age computations)
2. Family history relations (who has what, relation to patient)
3. Multi-sentence treatment chains (drug -> outcome across sentences)

Every extraction is tagged with its method source:
- "rule_based": from the deterministic regex pipeline
- "llm_enhanced": rule-based found something, LLM refined it
- "llm_only": LLM found something the regex missed

Supports Anthropic (Claude) and OpenAI-compatible APIs via raw HTTP.
No SDK dependencies.
"""

import json
import re
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .correction_memory import CorrectionMemory


class LLMEnhancer:
    """Optional LLM pass for targeted extraction enhancement.

    Args:
        api_key: API key for the LLM provider.
        provider: "anthropic" or "openai" (also works with any
                  OpenAI-compatible endpoint).
        model: Model name. Defaults to claude-sonnet-4-20250514 (Anthropic)
               or gpt-4o (OpenAI).
        base_url: Override the API endpoint (for local/proxy setups).
        temperature: Sampling temperature. Default 0 for reproducibility.
        log_fn: Optional callable for logging (receives str messages).
    """

    ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
    OPENAI_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        provider: str = "anthropic",
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0,
        log_fn: Optional[callable] = None,
        correction_memory: Optional["CorrectionMemory"] = None,
    ):
        self.api_key = api_key
        self.provider = provider.lower()
        self.temperature = temperature
        self._log = log_fn or (lambda msg: None)
        self._call_count = 0
        self._total_tokens = 0
        self.correction_memory = correction_memory

        if self.provider == "anthropic":
            self.model = model or "claude-sonnet-4-20250514"
            self.base_url = base_url or self.ANTHROPIC_URL
        else:
            self.model = model or "gpt-4o"
            self.base_url = base_url or self.OPENAI_URL

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Make a single LLM API call. Returns the text response."""
        self._call_count += 1

        if self.provider == "anthropic":
            payload = {
                "model": self.model,
                "max_tokens": 1024,
                "temperature": self.temperature,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            }
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            }
        else:
            payload = {
                "model": self.model,
                "max_tokens": 1024,
                "temperature": self.temperature,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base_url, data=data, headers=headers, method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            self._log(f"LLM API error {e.code}: {error_body[:200]}")
            raise

        if self.provider == "anthropic":
            text = result.get("content", [{}])[0].get("text", "")
            usage = result.get("usage", {})
            self._total_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        else:
            text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = result.get("usage", {})
            self._total_tokens += usage.get("total_tokens", 0)

        return text.strip()

    def _parse_json_response(self, text: str) -> Optional[dict]:
        """Extract JSON from LLM response, handling markdown fences."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from code fence
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding first { ... }
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

        self._log(f"Failed to parse LLM JSON response: {text[:200]}")
        return None

    # ── Subtask 1: Temporal reasoning ──

    TEMPORAL_SYSTEM = """You are a clinical information extraction system. You extract temporal information from medical case report sentences.

Given sentences from a case report, extract:
1. age_at_onset: the age when symptoms first appeared (number or null)
2. age_at_diagnosis: the age when the condition was diagnosed (number or null)
3. diagnostic_delay_years: years between symptom onset and diagnosis (number or null)
4. symptom_duration_years: how long symptoms have been present (number or null)
5. year_of_diagnosis: calendar year of diagnosis (number or null)
6. temporal_reasoning: brief explanation of any computation you performed

If the text says "diagnosed 10 years after onset at age 25", compute: onset at 15, delay = 10 years.
If the text says "mother diagnosed in 2010, daughter 10 years later", compute: daughter diagnosed 2020.
If information is not present, use null.

Respond with ONLY a JSON object, no other text."""

    TEMPORAL_EXAMPLES = """Example input sentences:
"The patient, a 34-year-old woman, reported joint pain since childhood."
"She was eventually diagnosed with hEDS at age 28 after seeing 12 specialists over 15 years."

Example output:
{"age_at_onset": 13, "age_at_diagnosis": 28, "diagnostic_delay_years": 15, "symptom_duration_years": 21, "year_of_diagnosis": null, "temporal_reasoning": "Onset described as 'childhood' with current age 34 and 15-year diagnostic journey starting ~age 13. Diagnosis at 28. Duration = 34 - 13 = 21 years."}"""

    def enhance_temporal(
        self, sentences: List[str], rule_based: dict
    ) -> dict:
        """Enhance temporal extraction with LLM reasoning.

        Args:
            sentences: relevant sentences (case presentation, first 20).
            rule_based: the rule-based temporal extraction result.

        Returns:
            Enhanced temporal dict with method tags.
        """
        # Select relevant sentences (those mentioning time, age, duration, diagnosis)
        temporal_keywords = re.compile(
            r"\b(?:year|age|month|diagnos|onset|childhood|adolescen|since|"
            r"duration|delay|referred|first\s+(?:seen|present|notic)|"
            r"history\s+of|began|started|developed|\d{4})\b",
            re.IGNORECASE,
        )
        relevant = [s for s in sentences[:30] if temporal_keywords.search(s)]

        if not relevant:
            return {**rule_based, "_temporal_method": "rule_based"}

        snippet = "\n".join(f"- {s}" for s in relevant[:15])
        prompt = f"{self.TEMPORAL_EXAMPLES}\n\nNow extract from these sentences:\n{snippet}"

        # Inject corrections from memory
        system = self.TEMPORAL_SYSTEM
        if self.correction_memory:
            corrections_block = self.correction_memory.format_for_prompt("temporal")
            if corrections_block:
                system = system + "\n" + corrections_block

        self._log(f"LLM temporal: {len(relevant)} relevant sentences")
        try:
            response = self._call_llm(system, prompt)
            parsed = self._parse_json_response(response)
        except Exception as e:
            self._log(f"LLM temporal failed: {e}")
            return {**rule_based, "_temporal_method": "rule_based"}

        if not parsed:
            return {**rule_based, "_temporal_method": "rule_based"}

        # Merge: LLM fills gaps in rule-based, but rule-based takes precedence
        # where it has values (since it's deterministic)
        enhanced = dict(rule_based)
        changed = False

        for field in [
            "age_at_onset", "diagnostic_delay_years",
            "symptom_duration_years",
        ]:
            rb_val = rule_based.get(field)
            llm_val = parsed.get(field)
            if rb_val is None and llm_val is not None:
                enhanced[field] = llm_val
                enhanced[f"_{field}_method"] = "llm_only"
                changed = True
            elif rb_val is not None:
                enhanced[f"_{field}_method"] = "rule_based"
                # If LLM disagrees, note it but keep rule-based
                if llm_val is not None and llm_val != rb_val:
                    enhanced[f"_{field}_llm_alternative"] = llm_val

        if parsed.get("temporal_reasoning"):
            enhanced["_llm_temporal_reasoning"] = parsed["temporal_reasoning"]

        enhanced["_temporal_method"] = "llm_enhanced" if changed else "rule_based"
        return enhanced

    # ── Subtask 2: Family history relations ──

    FAMILY_SYSTEM = """You are a clinical information extraction system. You extract family history information from medical case report sentences.

Given sentences, extract:
1. has_family_history: true/false/null (null if not mentioned)
2. family_members: list of objects, each with:
   - relation: e.g. "mother", "father", "sister", "maternal aunt"
   - condition: what condition they have/had
   - details: any additional details (age at diagnosis, outcome, etc.)
3. inheritance_pattern: "autosomal dominant", "autosomal recessive", "X-linked", "maternal", "unknown", or null
4. family_history_reasoning: brief explanation

Handle implicit family history: "her mother was also hypermobile" means positive family history for hypermobility.
"No family history of connective tissue disease" means has_family_history: false.
If family history is simply not discussed, use has_family_history: null.

Respond with ONLY a JSON object, no other text."""

    FAMILY_EXAMPLES = """Example input:
"Her mother had been diagnosed with EDS 10 years before the patient's own diagnosis in 2020."
"The patient's maternal grandmother died of aortic rupture at age 52."
"Three of six siblings were similarly affected."

Example output:
{"has_family_history": true, "family_members": [{"relation": "mother", "condition": "EDS", "details": "diagnosed ~2010 (10 years before patient's 2020 diagnosis)"}, {"relation": "maternal grandmother", "condition": "aortic rupture", "details": "died at age 52"}, {"relation": "siblings", "condition": "similar presentation", "details": "3 of 6 affected"}], "inheritance_pattern": "autosomal dominant", "family_history_reasoning": "Multiple generations affected on maternal side with vertical transmission pattern suggests autosomal dominant inheritance."}"""

    def enhance_family_history(
        self, sentences: List[str], rule_based: dict
    ) -> dict:
        """Enhance family history extraction with LLM reasoning.

        Args:
            sentences: all article sentences.
            rule_based: the rule-based family_history extraction result.

        Returns:
            Enhanced family history dict with method tags.
        """
        family_keywords = re.compile(
            r"(?:family|familial|mother|father|parent|sibling|brother|sister|"
            r"son|daughter|aunt|uncle|cousin|grandm|grandf|grandp|"
            r"inherit|heredit|autosom|genetic|proband|pedigree|"
            r"first.degree|second.degree|affected\s+relative|"
            r"maternal|paternal|consanguineous)",
            re.IGNORECASE,
        )
        relevant = [s for s in sentences if family_keywords.search(s)]

        if not relevant:
            return {**rule_based, "_family_history_method": "rule_based"}

        snippet = "\n".join(f"- {s}" for s in relevant[:15])
        prompt = f"{self.FAMILY_EXAMPLES}\n\nNow extract from these sentences:\n{snippet}"

        # Inject corrections from memory
        system = self.FAMILY_SYSTEM
        if self.correction_memory:
            corrections_block = self.correction_memory.format_for_prompt("family_history")
            if corrections_block:
                system = system + "\n" + corrections_block

        self._log(f"LLM family history: {len(relevant)} relevant sentences")
        try:
            response = self._call_llm(system, prompt)
            parsed = self._parse_json_response(response)
        except Exception as e:
            self._log(f"LLM family history failed: {e}")
            return {**rule_based, "_family_history_method": "rule_based"}

        if not parsed:
            return {**rule_based, "_family_history_method": "rule_based"}

        enhanced = dict(rule_based)
        changed = False

        # LLM provides richer family member detail
        llm_has_fh = parsed.get("has_family_history")
        rb_has_fh = rule_based.get("has_family_history")

        if rb_has_fh is None and llm_has_fh is not None:
            enhanced["has_family_history"] = llm_has_fh
            enhanced["_has_family_history_method"] = "llm_only"
            changed = True
        elif rb_has_fh is not None:
            enhanced["_has_family_history_method"] = "rule_based"

        # LLM family members (always richer than rule-based)
        llm_members = parsed.get("family_members", [])
        rb_members = rule_based.get("affected_relatives", [])
        if llm_members and len(llm_members) > len(rb_members):
            enhanced["family_members_detailed"] = llm_members
            enhanced["_family_members_method"] = "llm_enhanced" if rb_members else "llm_only"
            changed = True

        if parsed.get("inheritance_pattern"):
            enhanced["inheritance_pattern"] = parsed["inheritance_pattern"]
            enhanced["_inheritance_pattern_method"] = "llm_only"
            changed = True

        if parsed.get("family_history_reasoning"):
            enhanced["_llm_family_reasoning"] = parsed["family_history_reasoning"]

        enhanced["_family_history_method"] = "llm_enhanced" if changed else "rule_based"
        return enhanced

    # ── Subtask 3: Multi-sentence treatment chains ──

    TREATMENT_SYSTEM = """You are a clinical information extraction system. You extract treatment-response relationships from medical case report sentences.

Given sentences, extract a list of treatment events, each with:
1. drug: medication name
2. response: "improved", "no_improvement", "worsened", "adverse_effect", "discontinued", "maintained"
3. details: specific outcomes, doses, timeline
4. confidence: "high" (explicitly stated) or "inferred" (requires reasoning across sentences)

Handle multi-sentence chains: "She tried three antihistamines without relief. Cromolyn was then added with significant improvement." means 3 unnamed antihistamines had no_improvement, cromolyn improved.
Handle implicit failures: "After failing metoprolol, she was switched to ivabradine" means metoprolol = no_improvement.
Handle temporal sequences: "Propranolol was started. At 6-month follow-up, her heart rate had normalised." means propranolol = improved.

Respond with ONLY a JSON object with key "treatments" containing the list, no other text."""

    TREATMENT_EXAMPLES = """Example input:
"Initial management included propranolol 20mg twice daily and increased fluid intake."
"Despite beta-blocker therapy, her symptoms persisted."
"Midodrine 5mg three times daily was added with marked improvement in orthostatic symptoms."
"She reported nausea as a side effect of midodrine but tolerated it with dose adjustment."

Example output:
{"treatments": [{"drug": "propranolol", "response": "no_improvement", "details": "20mg twice daily, symptoms persisted despite therapy", "confidence": "inferred"}, {"drug": "midodrine", "response": "improved", "details": "5mg TID, marked improvement in orthostatic symptoms", "confidence": "high"}, {"drug": "midodrine", "response": "adverse_effect", "details": "nausea, tolerated with dose adjustment", "confidence": "high"}]}"""

    def enhance_treatment_chains(
        self, sentences: List[str], rule_based: List[dict]
    ) -> List[dict]:
        """Enhance treatment-response linkage with LLM reasoning.

        Args:
            sentences: all article sentences.
            rule_based: the rule-based treatment_responses list.

        Returns:
            Enhanced treatment response list with method tags.
        """
        treatment_keywords = re.compile(
            r"\b(?:treat|therap|medicat|prescri|administ|started|initiated|"
            r"switched|failed|intoleran|improv|worsen|respon|refractory|"
            r"discontinu|adverse|side.effect|dose|mg|twice|daily|"
            r"follow.up|outcome|relief|symptom.*persist|trial|"
            r"manag|regimen)\b",
            re.IGNORECASE,
        )
        relevant = [s for s in sentences if treatment_keywords.search(s)]

        if not relevant:
            tagged = [{**r, "_method": "rule_based"} for r in rule_based]
            return tagged

        snippet = "\n".join(f"- {s}" for s in relevant[:20])
        prompt = f"{self.TREATMENT_EXAMPLES}\n\nNow extract from these sentences:\n{snippet}"

        # Inject corrections from memory
        system = self.TREATMENT_SYSTEM
        if self.correction_memory:
            corrections_block = self.correction_memory.format_for_prompt("treatment")
            if corrections_block:
                system = system + "\n" + corrections_block

        self._log(f"LLM treatment chains: {len(relevant)} relevant sentences")
        try:
            response = self._call_llm(system, prompt)
            parsed = self._parse_json_response(response)
        except Exception as e:
            self._log(f"LLM treatment chains failed: {e}")
            return [{**r, "_method": "rule_based"} for r in rule_based]

        if not parsed:
            return [{**r, "_method": "rule_based"} for r in rule_based]

        llm_treatments = parsed.get("treatments", [])

        # Merge: keep all rule-based, add LLM-only findings
        # Build a set of (drug_lower, response) from rule-based for dedup
        rb_pairs = set()
        merged = []
        for r in rule_based:
            rb_pairs.add((r.get("drug", "").lower(), r.get("direction", r.get("response", ""))))
            merged.append({**r, "_method": "rule_based"})

        for lt in llm_treatments:
            drug = lt.get("drug", "").lower()
            response = lt.get("response", "")
            pair = (drug, response)
            if pair not in rb_pairs:
                merged.append({
                    "drug": lt.get("drug", ""),
                    "direction": response,
                    "details": lt.get("details", ""),
                    "confidence": lt.get("confidence", "inferred"),
                    "_method": "llm_only",
                })
                rb_pairs.add(pair)
            else:
                # LLM confirmed a rule-based finding; upgrade details if richer
                for m in merged:
                    if (m.get("drug", "").lower() == drug
                            and m.get("direction", m.get("response", "")) == response
                            and m.get("_method") == "rule_based"):
                        if lt.get("details") and not m.get("details"):
                            m["details"] = lt["details"]
                        m["_method"] = "llm_confirmed"
                        break

        return merged

    # ── Main enhancement entry point ──

    def enhance_extraction(
        self, extraction: dict, sentences: List[str]
    ) -> dict:
        """Run LLM enhancement on a single article's extraction.

        Modifies and returns the extraction dict with LLM-enhanced
        fields and method tags.
        """
        pmcid = extraction.get("pmcid", "unknown")
        self._log(f"LLM enhancing {pmcid}...")

        # 1. Temporal
        temporal_fields = {
            "age_at_onset": extraction.get("age_at_onset"),
            "symptom_duration_years": extraction.get("symptom_duration_years"),
            "diagnostic_delay_years": extraction.get("diagnostic_delay_years"),
            "onset_evidence": extraction.get("onset_evidence"),
            "delay_evidence": extraction.get("delay_evidence"),
        }
        enhanced_temporal = self.enhance_temporal(sentences, temporal_fields)
        for k, v in enhanced_temporal.items():
            extraction[k] = v

        time.sleep(0.5)  # Rate limiting

        # 2. Family history
        fh = extraction.get("family_history", {})
        enhanced_fh = self.enhance_family_history(sentences, fh)
        extraction["family_history"] = enhanced_fh

        time.sleep(0.5)

        # 3. Treatment chains
        rb_treatments = extraction.get("treatment_responses", [])
        enhanced_treatments = self.enhance_treatment_chains(sentences, rb_treatments)
        extraction["treatment_responses"] = enhanced_treatments

        # Summary
        extraction["_llm_enhanced"] = True
        extraction["_llm_model"] = self.model
        extraction["_llm_provider"] = self.provider
        extraction["_llm_calls"] = self._call_count

        self._log(
            f"  {pmcid}: temporal={enhanced_temporal.get('_temporal_method', '?')}, "
            f"family={enhanced_fh.get('_family_history_method', '?')}, "
            f"treatments={sum(1 for t in enhanced_treatments if t.get('_method') != 'rule_based')} LLM additions"
        )

        return extraction

    def get_stats(self) -> dict:
        """Return usage statistics."""
        return {
            "total_calls": self._call_count,
            "total_tokens": self._total_tokens,
            "model": self.model,
            "provider": self.provider,
        }
