# NLP pipeline v2: improvements

Summary of the code improvements made to `nlp_pipeline_v2/`. Everything below
is reproducible from the scripts in this package; nothing is hard-coded to a
specific disease.

## 1. Correctness bugs fixed

- `evaluate.py` imported a non-existent package (`nlp_extract`); the whole
  evaluation module was unimportable. Repointed to `nlp_pipeline_v2`.
- `evaluate.py` computed the misdiagnosis precision/recall against the wrong
  dictionary key (`nlp_misdiagnoses` vs the stored `nlp_misdiag`), silently
  returning zero. Fixed with an explicit field->key map.
- Deprecated `datetime.utcnow()` replaced with timezone-aware
  `datetime.now(timezone.utc)` across `pipeline.py`, `pipeline_log.py`,
  `web_app.py`.
- Stale `python -m nlp_extract.pipeline` references corrected.

## 2. Extraction precision: section-aware per-patient fields

The original pipeline ran the drug, measurement, comorbidity, outcome and
treatment-response extractors over **all** clinical sentences, including the
discussion and introduction. Those sections describe published knowledge, not
the index patient, so general statements leaked into per-patient fields (e.g.
"lidocaine and bupivacaine resistance has been described \[38]" became two
drugs the patient supposedly received).

Changes (`text_processing.py`, `pipeline.py`):

- Split the abstract into its own zone (it is patient-specific in case reports)
  separate from the general introduction.
- Added `get_patient_sentences` = abstract + case zones, with a generic-
  literature sentence filter (citation markers, "have been reported", "in the
  literature", etc.).
- Per-patient extractors now run on patient sentences; condition **detection**
  still runs over all sentences (presence anywhere is meaningful).
- A patient-action rescue (`is_patient_finding_sentence`) re-admits discussion
  sentences that explicitly describe the index patient ("the patient was
  started on metoprolol, symptoms resolved").

Measured on the 657 case reports in the corpus:

| Field | Original lit-derived false positives | After fix |
|-------|--------------------------------------|-----------|
| Drugs (affirmed) | 5.0% | **0.9%** |
| Comorbidities | 4.7% | **1.4%** |

A worked before/after on a synthetic case report: the original attributed
`atenolol, metoprolol, midodrine` (all discussion-only) to the patient; the
fixed pipeline returns only the patient's actual drugs `ivabradine, propranolol`.

## 3. Reproducible accuracy harness

`tests/run_eval.py` is a dependency-free, labelled gold-vignette suite covering
negation, drug NER, temporal onset/delay inference, symptom detection, the
literature filter, and section/zone precision. It exits non-zero below a 90%
threshold, so it doubles as a regression gate. Current: **36/36 (100%)**.

```
python -m nlp_pipeline_v2.tests.run_eval
```

(The repo previously shipped a 30-article "gold standard" with **no** human
labels filled in, so no accuracy could actually be computed from it.)

## 4. Disease config generator: generalisation across diseases

The generator turns disease name(s) into an extraction config via MONDO + HPO.
It was run over 50 diverse diseases; each issue found was fixed in a
generalisable way and re-evaluated. Mean config accuracy
(self-match recall + intra-config specificity + control specificity) rose from
**75.4% -> 97.8%** (99.8% among diseases with phenotype data), and diseases
that produced zero phenotypes dropped from **11 to 1**.

Headline fixes (full table and trajectory in `experiments/EXPERIMENT_LOG.md`,
plot in `experiments/accuracy_over_iterations.png`):

- Rank MONDO candidates by label quality + HPO-resolvability instead of taking
  the top text-relevance hit (which was often a susceptibility locus or the
  wrong subtype). This alone recovered 10 of 50 diseases.
- Removed shared process-word bare stems (`regurgi`, `prolaps`, `aneurys`) that
  caused cross-phenotype false positives; multi-word phenotypes use anchored
  joined stems instead.
- Fixed truncated-stem matching (`mitral` -> `mitra...`) with a `\w*` remainder.
- Tokenised phenotype names on any non-alphanumeric run and allowed
  hyphen/slash separators plus wider stop-gaps, recovering hyphenated names
  (`cafe-au-lait`, `Kayser-Fleischer`) and stop-word gaps
  (`dilatation of an abdominal artery`).
- Null-safe parsing of OLS/HPO responses (`obo_xref: null` previously crashed).

```
python -m nlp_pipeline_v2.experiments.fetch_cache       # once, networked
python -m nlp_pipeline_v2.experiments.run_experiment
python -m nlp_pipeline_v2.experiments.compare_versions
python -m nlp_pipeline_v2.experiments.make_plot
```

Verified end-to-end on a held-out disease not in the 50 (Gitelman syndrome,
live APIs): 77 phenotypes, 99.98% accuracy, no issues.

### Known limitation

Ankylosing spondylitis still yields 0 phenotypes: its MONDO term references only
`Orphanet:825` (which HPO/JAX 404s) and has no OMIM xref, so there is no
resolvable phenotype source upstream. Handled gracefully, not a code defect.
