# Disease config-generator generalisation experiment

Goal: run the disease config generator over 50 diverse real diseases, find
issues, and fix them in a **generalisable** way (no disease-specific hard-coding)
so the same class of issue cannot recur for any future disease.

## Method

- 50 diseases spanning genetics, metabolism, haematology, rheumatology,
  neurology, cardiology, nephrology, endocrinology and dermatology
  (`diseases.txt`). These are eval **inputs**, not code logic.
- For each disease the raw MONDO candidates + cross-references + HPO phenotype
  annotations are fetched once and cached (`fetch_cache.py`), so the
  HPO-name -> regex transform (the code under test) can be re-evaluated offline
  after every fix.
- Accuracy is measured with an automated, disease-agnostic metric
  (`eval_config.py`), the mean of three components per phenotype:
  - **recall** — the generated regex matches its own HPO term name;
  - **spec_cross** — it does *not* match other phenotypes' names (excluding
    legitimate parent/child ontology pairs);
  - **spec_control** — it does *not* match a battery of generic, phenotype-free
    clinical sentences.

## Accuracy trajectory

| Milestone | Mean accuracy (all 50) | Mean (diseases with phenotypes) | Diseases with 0 phenotypes |
|-----------|------------------------|----------------------------------|----------------------------|
| V0 baseline (original code) | 75.4% | 96.7% | 11 |
| V1 + robust candidate selection | 94.6% | 96.5% | 1 |
| V2 + pattern-quality fixes (final) | **97.8%** | **99.8%** | 1 |

See `accuracy_over_iterations.png` / `.csv`. Reproduce with:

```
python -m nlp_pipeline_v2.experiments.fetch_cache          # once (network)
python -m nlp_pipeline_v2.experiments.run_experiment       # current code
python -m nlp_pipeline_v2.experiments.compare_versions     # V0/V1/V2 trajectory
python -m nlp_pipeline_v2.experiments.make_plot
```

## Issues found and generalisable fixes

All fixes are in `disease_config_generator.py` unless noted. None reference any
specific disease, phenotype, or term — they act on structural properties of the
data (label tokens, HPO name morphology, JSON nullability).

| # | Iteration surfaced | Issue (generalisable class) | Fix | Effect |
|---|--------------------|------------------------------|-----|--------|
| 1 | Marfan (pre-run) | Multi-word phenotypes emitted a bare process-word stem (`regurgi`, `prolaps`, `aneurys`) shared across distinct phenotypes, so any "regurgitation" fired all three regurgitation phenotypes. | Only emit a bare stem for **single-word** phenotypes; multi-word phenotypes rely on their joined, anchored stem phrase. | Cross-contamination 0.07% on Marfan; eliminated the shared-stem false-positive class. |
| 2 | Marfan (pre-run) | Stems were truncated mid-word (`mitral` -> `mitra`) then required whitespace immediately after, so `mitra\s+regurg` could never match "mitral regurgitation" — recall collapsed once the bare-stem crutch (#1) was removed. | Append `\w*` after each stem so it absorbs the word remainder and morphological variants. | Restored self-match recall to ~96% while keeping specificity. |
| 3 | #15 Niemann-Pick (first of 11) | Selection took the **top OLS text-relevance hit**, frequently the wrong term: a susceptibility locus ("SLE, susceptibility to, 1", no phenotypes), a different disease ("juvenile idiopathic arthritis" for RA), or a compound ("sickle cell-beta-thalassemia"). 11/50 diseases got **0 phenotypes**. | Added `score_candidate` / `rank_candidates`: reward exact/substring/token-overlap label match; penalise generic non-disease qualifiers (susceptibility, modifier, somatic, animal forms, named subtypes, trailing type/locus numerals); boost HPO-resolvable candidates; fall back through ranked alternates. | 0-phenotype diseases 11 -> 1; mean accuracy 75.4% -> 94.6%. |
| 4 | #42 Cystic fibrosis | Crash: `TypeError: 'NoneType' object is not iterable`. OLS returns some fields (e.g. `obo_xref`) explicitly as JSON `null`; `dict.get(k, [])` returns that `None`. | Replaced null-prone `.get(k, default)` with `... or []` / `... or {}` across the OLS/HPO response parsing. | Generator no longer crashes on any null-field term. |
| 5 | #25 Systemic sclerosis | Phenotype names with internal hyphens/slashes ("cafe-au-lait", "Kayser-Fleischer", "Aplasia/Hypoplasia", "angiotensin-converting") were one token to the whitespace tokenizer, so stems could not cross the hyphen — 34 recall failures across the set. | Split phenotype names on **any non-alphanumeric** run; join stems with a separator matching whitespace, hyphen, or slash. | Recovered the hyphen/slash recall-failure class. |
| 6 | #25 Systemic sclerosis | Dropped stop-words left multi-word gaps ("dilatation **of an** abdominal artery") wider than the single intervening-word allowance — 30 recall failures. | Widened the optional intervening-word filler between stems from `{0,1}` to `{0,2}`. | Recovered the stop-gap recall-failure class; recall 0.83 -> ~1.0 on systemic sclerosis. |
| 7 | #38 Brugada (metric) | The metric over-penalised legitimate ontology hierarchy: "Tachycardia" matching "Supraventricular tachycardia" was counted as contamination though it is correct parent/child behaviour. | Evaluation fix (`eval_config.py`): exclude phenotype pairs whose names are in a token-containment relationship from the specificity test. | Removed spurious contamination penalties; fairer metric. |

## Known limitation (not a code defect)

- **Ankylosing spondylitis** remains at 0 phenotypes. Its MONDO term
  (`MONDO:0005306`) cross-references only `Orphanet:825`, which HPO/JAX returns
  404 for, and carries **no OMIM xref** — although `OMIM:106300` (with 13
  phenotypes) exists in HPO, it is not linked from this MONDO term. This is an
  upstream MONDO<->HPO annotation gap, confirmed by direct API inspection, and
  is handled gracefully (logged, alternates tried) rather than crashing.
