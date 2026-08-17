# Case Report Phenotyping Pipeline (`nlp_pipeline_v2`)

A disease-agnostic pipeline that turns a disease name into a structured,
patient-level dataset mined from published case reports. You give it one or
more disease names; it builds an extraction configuration from biomedical
ontologies, retrieves and downloads open-access case reports from
PubMed/PMC, extracts per-patient phenotype data with negation- and
section-aware rule-based extraction, and writes analysis-ready tables. A web UI
exposes the whole flow, and a built-in evaluation harness measures quality.

It is built for systematic-review-style phenotyping of rare and multisystem
conditions, where the evidence base is dominated by individual case reports
rather than trials.

---

## What "NLP" means here (scope and claims)

Stated up front, because the terminology is easy to overclaim in front of an
ML audience.

- **Extraction is rule-based, not a learned model.** There is no trained model
  anywhere in the pipeline: no transformer, BERT, NER model or classifier
  (verify with `grep -rE "torch|transformers|spacy|scispacy|sklearn"
  nlp_pipeline_v2/*.py`, which returns nothing). Findings are matched with
  dictionaries and regular expressions derived from ontology terms. "NLP" here
  denotes the linguistically-informed *techniques* layered on top of that
  matching, namely abbreviation-aware sentence segmentation, ConText negation
  detection (Harkema et al. 2009), and section/zone classification, not
  statistical or neural NLP. Describe it as a hybrid rule-based system.

- **The automated, novel contribution is the ontology-driven configuration**,
  not the extraction backend. Resolving a disease name to the correct MONDO
  term, pulling its HPO phenotype annotations, and generating the extraction
  schema automatically is the genuinely automated part. The extraction itself
  is enhanced, schema-driven regex with negation and section awareness. A title
  or abstract should foreground the ontology-driven pipeline; calling the
  extraction "NLP" without the rule-based qualifier reads as overclaiming.

- **Optional LLM enhancement is off by default and unvalidated.** A SPELL-style
  LLM gap-filling step exists (`llm_enhancer.py`) but is disabled unless an API
  key is supplied, and no LLM-based extraction has been validated here.

- **What is validated, and what is not.** The rule-based extraction has only
  preliminary, small-sample human validation (symptom F1 approximately 0.85,
  age accuracy approximately 0.80, on 10 stratified articles; see
  `logs/provenance_log.md`). The headline 97.8% figure below is *configuration
  pattern quality* (does each generated regex match its own ontology term and
  avoid others), not extraction accuracy against human labels. The section-aware
  v2 pipeline does not yet have an independent human-annotated gold standard;
  the bundled gold-standard file holds machine pre-annotations only. Claims
  should therefore separate three things: the auto-config is measured at the
  pattern level (strong), the rule-based extraction has small-sample human
  validation (preliminary), and the LLM mode is unvalidated.

---

## Pipeline, start to finish

The flow has six stages. Each writes a provenance log entry so a run is
reproducible.

### 1. Configuration from ontologies (`disease_config_generator.py`)

You provide disease name(s). The generator resolves each name to a MONDO term
via the EBI Ontology Lookup Service, ranks the candidate terms by label quality
and phenotype-data availability (so "systemic lupus erythematosus" resolves to
the disease, not a susceptibility locus), and pulls the disease's HPO (Human
Phenotype Ontology) annotations via the JAX API. Each HPO phenotype name is
converted into a regular expression, and MONDO synonyms become the condition
detectors and the search terms. The output is a complete `config.json`:
condition patterns, symptom patterns, a seed drug list, measurement patterns,
and negation triggers. No manual dictionary building is required, and the same
machinery works for any disease with HPO coverage. The seed drug list and the
comorbidity detectors are deliberately generic — at extraction time they are
augmented by corpus-driven discovery so the results adapt to the actual disease
(see Extraction).

### 2. Retrieval (`web_app.py` search route)

The topic query (auto-built from the resolved synonyms, or written by hand) is
searched in **PubMed**, restricted to the PMC open-access subset so every hit
has downloadable full text. Publication-type checkboxes (case reports, reviews,
systematic reviews, trials, etc.) map to NLM `[pt]` filters. PubMed is used
rather than PMC because publication-type and MeSH indexing are reliably
populated only on MEDLINE/PubMed records; the matching PMIDs are then mapped to
PMCIDs with the PMC ID Converter API.

### 3. Download (`scripts`/web route)

Full-text JATS XML for the selected PMCIDs is fetched from PMC and cached
locally. Retrieval queries and access are logged.

### 4. Extraction (`pipeline.py`, `extractors.py`, `text_processing.py`, `negation.py`)

Each article is parsed into sections. Articles whose type is not an
individual-patient case report are skipped. For the rest, the pipeline extracts:
demographics (age, sex), temporal structure (age at onset, symptom duration,
diagnostic delay, misdiagnoses, referral pathway), drugs with dosage/route/
frequency, clinical measurements, symptoms/phenotypes, comorbidities, family
history, outcomes, and drug-to-response links. Two design choices drive
quality:

- **Section-aware attribution.** Per-patient fields are extracted only from the
  abstract and case sections, never the discussion or introduction, so general
  statements and literature claims are not misattributed to the index patient.
  A patient-action rescue re-admits discussion sentences that explicitly
  describe the patient.
- **Negation awareness.** A pure-Python implementation of the ConText algorithm
  classifies each finding as affirmed, negated, or not mentioned, so the dataset
  records what was tested and ruled out, not only positives.
- **Corpus-driven discovery with ontology validation.** Drugs and comorbidities
  are not limited to the config dictionaries — they are also mined directly from
  each paper. Drugs are found via generic drug-name morphology (INN stems such
  as `-mab`, `-statin`, `-azepam`) and treatment cues ("started on…", "treated
  with…"); comorbidities via disease morphology and relational cues ("history
  of…", "diagnosed with…"), with the primary disease excluded so it is never
  reported as its own comorbidity. Discovered candidates are then validated
  against authoritative ontologies — drugs against RxNorm (NIH RxNav),
  comorbidities against Mondo (EBI OLS4) — and anything that does not resolve is
  dropped (`ontology_validation.py`, cached, parallelised). This captures
  disease-specific medications and co-occurring conditions without a hand-built
  per-disease list, and is still rule-based + ontology lookup — **not** an LLM.
  It is on by default ("Ontology validation · max precision" in the UI) and can
  be disabled per run.

### 5. Dataset build (`dataset_builder.py`)

Raw extractions are assembled into analysis-ready outputs: a patient-level
table, a corpus-metadata table, a comorbidity matrix, a treatment-response
summary, an extraction-quality report, a machine-readable data dictionary, and
the raw `extractions.json`. A one-click "Download all" bundles them as a zip.

### 6. Review and correction (`web_app.py`, `correction_memory.py`)

Extractions are browsable per article in the UI, with evidence sentences, so a
human can spot errors and submit structured corrections that persist to disk.

### Optional: LLM enhancement (`llm_enhancer.py`)

A SPELL-style hybrid step can call an LLM to fill gaps the rules miss
(off by default). The rule-based core runs with no API keys, no cost, and
deterministic output; the LLM is additive, not load-bearing. See "Two
extraction modes" below for exactly what it does and does not touch.

---

## Two extraction modes: rule-based vs. optional LLM

Extraction has two layers. **Mode 1 always runs; Mode 2 is an optional refinement
on top of it.**

### Mode 1 — rule-based (default, no API key)

Deterministic regex/dictionary extraction over section- and negation-aware
sentences, plus the corpus-driven discovery + ontology validation described
above. No network is needed for extraction itself (only ontology validation
makes calls, and that is cacheable/skippable), output is reproducible, and there
is no cost. This is the load-bearing path and the one with (preliminary) human
validation.

### Mode 2 — LLM enhancement (opt-in: toggle + API key)

When enabled, the LLM does **not** re-extract everything and does **not** touch
symptoms, drugs, comorbidities, demographics or measurements. It is a *targeted
second pass* over only the three subtasks where regex is weakest:

1. **Temporal reasoning** — onset/diagnosis ages, diagnostic delay, duration,
   including arithmetic across sentences ("diagnosed 10 years after onset at age
   25" → onset 15).
2. **Family-history relations** — who is affected, with what, and the implied
   inheritance pattern.
3. **Multi-sentence treatment chains** — drug → response linked across sentences
   ("after failing metoprolol, switched to ivabradine" → metoprolol = no
   improvement).

How it works, and why it is safe to add:

- **Snippet-based, not whole-paper.** For each subtask the rule-based pass first
  selects the relevant sentences with a keyword regex, and *only those snippets*
  (≤15–20 sentences) are sent to the model. The LLM never sees the full article,
  which keeps calls cheap and shrinks the hallucination surface.
- **Rule-based wins; the LLM fills gaps.** Deterministic values take precedence.
  The LLM only supplies a value where the rules found none. If the LLM disagrees
  with a rule-based value it is recorded as `_<field>_llm_alternative` but the
  rule-based value is kept.
- **Full provenance.** Every field is tagged with its source — `rule_based`,
  `llm_only`, `llm_enhanced`, or `llm_confirmed` — and each extraction carries
  `_llm_enhanced`, `_llm_model`, `_llm_provider`, `_llm_calls`. You can always
  tell which method produced a value and compare the two.
- **Cost/shape.** Three API calls per article (one per subtask), `temperature=0`
  for reproducibility, `max_tokens=1024`, rate-limited. Works with Anthropic
  (Claude) or any OpenAI-compatible endpoint over raw HTTP — no SDK dependency.
- **Human-in-the-loop.** Corrections submitted in the Review tab are stored
  (`correction_memory.py`) and injected into the relevant subtask's system
  prompt on later runs, so the LLM pass improves from feedback.

The two modes are independent of the discovery/validation work: discovery and
RxNorm/Mondo validation are rule-based + ontology lookups and run in **both**
modes. The LLM toggle only changes the three subtasks above.

> Status: the LLM mode is unvalidated here (no LLM-based extraction has been
> measured against human labels). Treat it as an exploratory refinement, and
> report rule-based numbers as the system's validated performance.

### No fabricated data

The web UI never invents data. If the backend is unreachable it shows an
explicit "backend not reachable" state rather than placeholder/sample numbers,
so a demo view can never be mistaken for real extraction output.

---

## Current performance

These figures come from the repository's own evaluation code; reproduce them
with the commands in Quickstart.

**Configuration generator, across 50 diverse diseases** (genetic, metabolic,
haematological, rheumatological, neurological, cardiac, renal, endocrine,
dermatological). Accuracy here is an automated, disease-agnostic metric:
self-match recall (each phenotype's regex matches its own ontology name) plus
intra-config specificity (it does not match other phenotypes' names) plus
control specificity (it does not match generic, phenotype-free clinical text).

| Metric | Value |
|--------|-------|
| Mean accuracy (all 50) | **97.8%** |
| Mean accuracy (diseases with phenotype data) | **99.8%** |
| Mean self-match recall | **0.996** |
| Cross-phenotype contamination | **~0%** |
| Diseases with zero phenotypes (upstream HPO gap) | 1 / 50 |

The generator started at 75.4% mean accuracy; generalisable fixes (robust
candidate selection, stem matching that handles hyphens, slashes and
possessives, null-safe parsing) lifted it to 97.8%. Held-out check on a disease
outside the 50 (Gitelman syndrome, live APIs): 77 phenotypes, 99.98%.

**Extraction precision (section-awareness)**, measured on 657 case reports in
the working corpus, as the share of extracted items that came from
literature/discussion sentences rather than the patient:

| Field | Before | After |
|-------|--------|-------|
| Drugs (affirmed) | 5.0% literature-derived | **0.9%** |
| Comorbidities | 4.7% | **1.4%** |

**Retrieval precision.** On a polycystic-ovary-syndrome sample, routing the
search through PubMed's MeSH publication-type filter raised the share of
downloaded articles the pipeline accepts as genuine case reports from ~36%
(loose PMC full-text search) to ~92% (small sample, n=12), and removed
off-topic articles that merely mentioned the disease in passing.

**Functional tests.** A dependency-free gold-vignette suite covering negation,
drug recognition, temporal inference, symptom detection, the literature filter
and section precision passes 36/36.

**Throughput.** Rule-based extraction runs at roughly 35-40 articles/second on
a laptop; configuration generation takes about 2-7 seconds per disease
(network-bound on the ontology APIs).

---

## How this differs from existing tools

Systematic-review and clinical-NLP tooling tends to fall into a few buckets,
and this pipeline sits deliberately across the gaps between them.

**Screening tools (Rayyan, Covidence, Abstrackr, ASReview).** These accelerate
title/abstract inclusion-and-exclusion decisions, often with active learning.
They decide which papers enter a review; they do not extract structured data
from the papers. This pipeline starts where they stop, producing per-patient
variables.

**Trial-extraction tools (RobotReviewer, Trialstreamer, ExaCT).** These target
randomised controlled trials, extracting PICO elements and risk-of-bias. The
case-report literature, which dominates rare and multisystem disease evidence,
is a different genre with different structure (one patient, narrative course,
no arms), and is largely unaddressed by trial-oriented tools.

**General clinical NLP (MetaMap, cTAKES, scispaCy, MedCAT, CLAMP).** These
recognise and normalise concepts in clinical text against UMLS/SNOMED, and are
powerful but general-purpose. They are not configured per disease for a review
corpus, do not retrieve the corpus, and crucially do not separate findings
about the index patient from background literature inside a published case
report, which is the dominant precision problem here.

**HPO-extraction tools (Doc2HPO, ClinPhen, Monarch tooling).** Closest in
spirit: they map clinical text to HPO terms. This pipeline differs by being
auto-configured per disease from MONDO + HPO, by coupling extraction to
retrieval and to a full per-patient schema (drugs, temporal course,
comorbidities, outcomes, family history), and by its section-aware patient
attribution.

**LLM-based extraction.** Large language models can extract from papers
zero-shot, but at the cost of per-document API spend, non-determinism,
opacity, and hallucination risk, all of which are awkward for a systematic
review that must be reproducible and auditable (PROSPERO registration, PRISMA
reporting). This pipeline's core is deterministic and fully inspectable: every
match traces to a named regex and an evidence sentence, and every run emits a
provenance log. The LLM is offered only as an optional, clearly-tagged
enhancement layer over a transparent base.

**The combination is the contribution.** Individually, ontology lookup, regex
extraction, ConText negation and LLM assists are all established. What is
distinctive here is putting them together into a single, reproducible,
disease-agnostic route from a disease name to a patient-level case-report
dataset, with section-aware attribution to keep published-literature noise out
of per-patient fields, and a built-in metric so quality is measured rather than
asserted.

---

## Limitations (read before relying on it)

- **Heuristic, not true NER.** Extraction is dictionary- and regex-based with
  morphological stemming. It is transparent and fast but has a recall ceiling
  and cannot disambiguate by deep context the way a trained model can.
- **No human-gold extraction benchmark yet.** The metrics above measure config
  pattern quality, section precision, and vignette correctness. Precision and
  recall against a human-annotated extraction gold standard are not yet
  established; the review UI exists to build that set.
- **Case reports only.** Other article types are intentionally skipped at
  extraction.
- **Ontology coverage varies.** A disease with sparse or mis-linked HPO
  annotations (e.g. ankylosing spondylitis, whose MONDO term lacks a resolvable
  HPO cross-reference) yields few or no symptom patterns. This is an upstream
  data gap, handled gracefully rather than hidden.

---

## Quickstart

```bash
pip install -r nlp_pipeline_v2/requirements.txt

# Web UI (config -> search -> download -> extract -> review), http://localhost:8000
uvicorn nlp_pipeline_v2.web_app:app --reload --port 8000

# Or from the command line:
python -m nlp_pipeline_v2.disease_config_generator "Marfan syndrome" -o config.json
python -m nlp_pipeline_v2.pipeline --input data/raw/fulltext --output extractions.json --config config.json

# Tests and evaluation
python -m nlp_pipeline_v2.tests.run_eval                  # 36/36 vignette suite
python -m nlp_pipeline_v2.experiments.run_experiment      # 50-disease config accuracy
```

## Layout

```
nlp_pipeline_v2/
  disease_config_generator.py   # disease name -> config (MONDO + HPO)
  pipeline.py                   # orchestration, per-article extraction
  extractors.py                 # drugs, temporal, measurements, comorbidities, ...
  text_processing.py            # JATS parsing, sectioning, patient-sentence selection
  negation.py                   # ConText negation
  dataset_builder.py            # analysis-ready output tables
  llm_enhancer.py               # optional LLM gap-filling
  web_app.py / frontend.html    # UI and API
  tests/run_eval.py             # gold-vignette accuracy suite
  experiments/                  # 50-disease generalisation study (log + plot)
```

See `IMPROVEMENTS.md` for the change history and `experiments/EXPERIMENT_LOG.md`
for the generalisation study and accuracy-over-time plot.
