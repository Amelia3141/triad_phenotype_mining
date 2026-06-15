"""
Reproducible accuracy evaluation for the NLP extraction pipeline.

This is a self-contained, dependency-free gold-standard test set. Each case
has a known-correct expected output, so the pipeline's accuracy is measurable
and regressions are caught. Run:

    python -m nlp_pipeline_v2.tests.run_eval

Exits non-zero if overall accuracy drops below THRESHOLD, so it can be used
as a CI / pre-commit check.

Categories:
  - negation        : ConText negation on individual targets
  - drugs           : dictionary drug NER + negation
  - temporal        : age-at-onset / diagnostic-delay inference
  - symptoms        : symptom detection + negation (default config patterns)
  - zone_precision  : section-aware extraction (the headline fix) — drugs and
                      symptoms mentioned only in discussion/literature must NOT
                      be attributed to the patient, while case/abstract ones must.
  - lit_filter      : generic-literature sentence detection
"""

import sys

from ..negation import NegationDetector
from ..extractors import DrugExtractor, TemporalExtractor, load_config
from ..text_processing import is_generic_literature_sentence
from ..pipeline import NLPExtractionPipeline

THRESHOLD = 0.90  # required overall pass rate


# ── Gold data ──────────────────────────────────────────────────────────

# (sentence, target_substring, expected_negated)
NEGATION_CASES = [
    ("The patient denied any chest pain.", "chest pain", True),
    ("There was no evidence of mast cell activation.", "mast cell activation", True),
    ("She presented with joint hypermobility and chronic fatigue.", "joint hypermobility", False),
    ("No history of anaphylaxis was noted.", "anaphylaxis", True),
    ("The patient had palpitations but no syncope.", "syncope", True),
    ("The patient had palpitations but no syncope.", "palpitations", False),
    ("Tryptase was not elevated.", "elevated", True),
    ("Echocardiography showed mitral valve prolapse.", "mitral valve prolapse", False),
    ("Tilt-table testing was negative for orthostatic hypotension.", "orthostatic hypotension", True),
    ("He reported easy bruising since childhood.", "easy bruising", False),
]

# (list_of_sentences, expected_affirmed_drugs_set, expected_negated_drugs_set)
DRUG_CASES = [
    (["The patient was started on propranolol 40 mg twice daily."], {"propranolol"}, set()),
    (["She was treated with midodrine and fludrocortisone."], {"midodrine", "fludrocortisone"}, set()),
    (["He was not given any beta blockers such as metoprolol."], set(), {"metoprolol"}),
    (["Cromolyn and cetirizine controlled her symptoms."], {"cromolyn", "cetirizine"}, set()),
]

# (list_of_sentences, age_at_presentation, expected_onset, expected_delay)
# expected_* may be None to mean "not asserted"
TEMPORAL_CASES = [
    (["She had a 10-year history of joint pain."], 30, 20, None),
    (["The patient has had symptoms since the age of 14."], 30, 14, None),
    (["Her symptoms started 12 years ago."], 50, 38, None),
    (["She was finally diagnosed after 8 years."], None, None, 8),
    (["The patient experienced a 12-year diagnostic odyssey."], None, None, 12),
]

# (list_of_sentences, expected_affirmed_symptoms_subset, expected_negated_symptoms_subset)
SYMPTOM_CASES = [
    (["She had joint hypermobility, easy bruising, and frequent syncope."],
     {"joint_hypermobility", "easy_bruising", "syncope"}, set()),
    (["The patient denied any palpitations."], set(), {"palpitations"}),
    (["Examination revealed tachycardia and orthostatic intolerance."],
     {"tachycardia", "orthostatic_intolerance"}, set()),
]

# (sentence, expected_is_generic_literature)
LIT_FILTER_CASES = [
    ("Beta blockers such as metoprolol have been reported to help in POTS [5].", True),
    ("Midodrine has been described as effective in several case series.", True),
    ("The prevalence of MCAS in the general population is debated.", True),
    ("The patient was started on propranolol with good response.", False),
    ("On examination she had a Beighton score of 7/9.", False),
    ("We report a 28-year-old woman with POTS treated with ivabradine.", False),
]


def _nxml_case_report(abstract: str, case: str, discussion: str) -> str:
    """Build a minimal PMC-style NXML case report for integration tests."""
    return f"""<article article-type="case-report">
<front><article-meta>
<title-group><article-title>An illustrative case report</article-title></title-group>
<abstract><p>{abstract}</p></abstract>
</article-meta></front>
<body>
<sec><title>Case presentation</title><p>{case}</p></sec>
<sec><title>Discussion</title><p>{discussion}</p></sec>
</body>
</article>"""


# Headline zone-precision case: drugs/symptoms only in the discussion section
# must NOT be attributed to the patient; those in abstract/case must be.
ZONE_CASE = {
    "xml": _nxml_case_report(
        abstract="We report a 28-year-old woman with POTS who was treated with ivabradine.",
        case="On examination she had tachycardia and palpitations. "
             "She was started on propranolol with a good response.",
        discussion="Beta blockers such as metoprolol and atenolol have been used in POTS [5]. "
                   "Midodrine has also been reported to reduce orthostatic intolerance [6]. "
                   "Chronic fatigue is frequently described in these patients.",
    ),
    # Must be present (patient zones)
    "expect_drugs_present": {"ivabradine", "propranolol"},
    # Must be absent (discussion / literature only)
    "expect_drugs_absent": {"metoprolol", "atenolol", "midodrine"},
    "expect_symptoms_present": {"tachycardia", "palpitations"},
    # 'fatigue' appears only in the discussion as a general statement
    "expect_symptoms_absent": {"fatigue"},
}


# ── Runners ────────────────────────────────────────────────────────────

def run_negation():
    det = NegationDetector()
    passed = failed = 0
    fails = []
    for sent, target, expected in NEGATION_CASES:
        low = sent.lower()
        idx = low.find(target.lower())
        assert idx >= 0, f"target not in sentence: {target!r}"
        neg, trigger = det.is_negated(sent, idx, idx + len(target))
        if neg == expected:
            passed += 1
        else:
            failed += 1
            fails.append(f"    [{target!r}] got negated={neg} expected={expected}: {sent!r}")
    return passed, failed, fails


def run_drugs():
    ex = DrugExtractor(load_config())
    passed = failed = 0
    fails = []
    for sents, exp_aff, exp_neg in DRUG_CASES:
        res = ex.extract_from_sentences(sents)
        aff = {d["drug"] for d in res if not d["negated"]}
        neg = {d["drug"] for d in res if d["negated"]}
        if exp_aff <= aff and exp_neg <= neg and not (exp_aff & neg):
            passed += 1
        else:
            failed += 1
            fails.append(f"    affirmed={sorted(aff)} negated={sorted(neg)} "
                         f"expected_aff={sorted(exp_aff)} expected_neg={sorted(exp_neg)}: {sents}")
    return passed, failed, fails


def run_temporal():
    ex = TemporalExtractor()
    passed = failed = 0
    fails = []
    for sents, age, exp_onset, exp_delay in TEMPORAL_CASES:
        res = ex.extract_from_sentences(sents, age_at_presentation=age)
        ok = True
        if exp_onset is not None and res.get("age_at_onset") != exp_onset:
            ok = False
        if exp_delay is not None and res.get("diagnostic_delay_years") != exp_delay:
            ok = False
        if ok:
            passed += 1
        else:
            failed += 1
            fails.append(f"    onset={res.get('age_at_onset')} delay={res.get('diagnostic_delay_years')} "
                         f"expected_onset={exp_onset} expected_delay={exp_delay}: {sents}")
    return passed, failed, fails


def run_symptoms():
    pipe = NLPExtractionPipeline()
    passed = failed = 0
    fails = []
    for sents, exp_aff, exp_neg in SYMPTOM_CASES:
        syms = pipe._extract_symptoms_with_negation(sents)
        aff = {s["symptom"] for s in syms if not s["negated"]}
        neg = {s["symptom"] for s in syms if s["negated"]}
        if exp_aff <= aff and exp_neg <= neg and not (exp_aff & neg):
            passed += 1
        else:
            failed += 1
            fails.append(f"    affirmed={sorted(aff)} negated={sorted(neg)} "
                         f"expected_aff={sorted(exp_aff)} expected_neg={sorted(exp_neg)}: {sents}")
    return passed, failed, fails


def run_lit_filter():
    passed = failed = 0
    fails = []
    for sent, expected in LIT_FILTER_CASES:
        got = is_generic_literature_sentence(sent)
        if got == expected:
            passed += 1
        else:
            failed += 1
            fails.append(f"    got={got} expected={expected}: {sent!r}")
    return passed, failed, fails


def run_zone_precision():
    pipe = NLPExtractionPipeline()
    res = pipe.extract_from_xml_string(ZONE_CASE["xml"], "TESTCASE")
    fails = []
    checks = 0
    ok = 0

    drugs_aff = {d["drug"] for d in res.get("drugs_affirmed", [])}
    syms_aff = {s["symptom"] for s in res.get("symptoms_affirmed", [])}

    for d in ZONE_CASE["expect_drugs_present"]:
        checks += 1
        if d in drugs_aff:
            ok += 1
        else:
            fails.append(f"    MISSING patient drug: {d} (got {sorted(drugs_aff)})")
    for d in ZONE_CASE["expect_drugs_absent"]:
        checks += 1
        if d not in drugs_aff:
            ok += 1
        else:
            fails.append(f"    LEAKED discussion drug: {d} (got {sorted(drugs_aff)})")
    for s in ZONE_CASE["expect_symptoms_present"]:
        checks += 1
        if s in syms_aff:
            ok += 1
        else:
            fails.append(f"    MISSING patient symptom: {s} (got {sorted(syms_aff)})")
    for s in ZONE_CASE["expect_symptoms_absent"]:
        checks += 1
        if s not in syms_aff:
            ok += 1
        else:
            fails.append(f"    LEAKED discussion symptom: {s} (got {sorted(syms_aff)})")

    return ok, checks - ok, fails


def main():
    categories = [
        ("negation", run_negation),
        ("drugs", run_drugs),
        ("temporal", run_temporal),
        ("symptoms", run_symptoms),
        ("lit_filter", run_lit_filter),
        ("zone_precision", run_zone_precision),
    ]

    total_pass = total = 0
    print("=" * 64)
    print("NLP pipeline accuracy evaluation")
    print("=" * 64)
    for name, fn in categories:
        p, f, fails = fn()
        n = p + f
        total_pass += p
        total += n
        rate = p / n if n else 0
        status = "PASS" if f == 0 else "FAIL"
        print(f"  {name:16s} {p:3d}/{n:<3d}  {rate:6.1%}  [{status}]")
        for line in fails:
            print(line)

    overall = total_pass / total if total else 0
    print("-" * 64)
    print(f"  {'OVERALL':16s} {total_pass:3d}/{total:<3d}  {overall:6.1%}")
    print("=" * 64)

    if overall < THRESHOLD:
        print(f"FAILED: overall {overall:.1%} < threshold {THRESHOLD:.0%}")
        return 1
    print(f"OK: overall {overall:.1%} >= threshold {THRESHOLD:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
