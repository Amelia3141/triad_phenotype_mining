# Validation Report: Rule-Based Phenotype Extraction

## Methodology
Stratified random sample of 10 articles (3 EDS-only, 2 POTS, 2 MCAS, 3 triad) manually verified against source XML.

## Field-Level Accuracy

| Field | Correct | Incorrect | Missed | Accuracy |
|-------|---------|-----------|--------|----------|
| Age | 6 | 2 | 0 | 80% (8/10 including N/A) |
| Sex | 5 | 2 | 1 | 70% |
| EDS detection | 8 | 2 | 0 | 80% |
| POTS detection | 10 | 0 | 0 | 100% |
| MCAS detection | 8 | 2 | 0 | 80% |

## Symptom Extraction (case reports with individual patients only, n=7)

| Metric | Value |
|--------|-------|
| Precision | 89.3% (25/28) |
| Recall | 80.6% (25/31) |
| F1 Score | 84.7% |

## Systematic Errors Identified

1. **Article type misclassification**: 3/10 validation articles were not case reports (review, conference abstract, population study). PubMed "case reports" publication type filter is imperfect.

2. **EDS false positives from negation**: In PMC5778345, EDS was explicitly excluded ("no... hypermobile Ehlers-Danlos syndrome") but extraction flagged True. Rule-based system lacks negation handling.

3. **EDS subtype conflation**: Original query captured all EDS subtypes. 147/390 EDS articles were vascular EDS, irrelevant to triad hypothesis. Fixed in v3 by full-text subtype classification.

4. **Mastocytosis contamination**: 155 mastocytosis-only papers from MCAS query. Fixed in v2 by full-text condition reclassification.

5. **MCAS overclassification**: PMC10332885 had MCAS referral but no diagnosis; PMC12030918 was a breast cancer paper. The keyword "mast cell" triggers false positives in unrelated contexts.

6. **Multi-subject demographic confusion**: PMC12677986 has mother (31F) and infant (newborn M); extractor captured wrong subject.

7. **GI symptom false positives**: Acute surgical presentations (uterine torsion) misclassified as chronic GI symptoms.

8. **Criteria threshold age capture**: ">=18 years of age" (inclusion criterion) initially captured as patient age. Fixed in v2 with prefix negation check.

## Comparison to Published Benchmarks

Our rule-based extraction F1 of 84.7% for symptom detection is comparable to:
- RAG-HPO + LLaMA-3.1 70B: F1 = 78% (Genome Medicine, 2025)
- CaseReportBench best model: TSR = 56.4% (though different metric)

The higher F1 here reflects that our symptom categories are broader (e.g., "gi_symptoms" vs specific HPO terms), which inflates precision relative to fine-grained phenotyping.

## Impact of Corrections

| Dataset Version | Total Articles | Relevant Case Reports | Key Change |
|----------------|---------------|----------------------|------------|
| v1 (initial) | 717 | 376 | Raw corpus |
| v2 (mastocytosis excluded) | 560 | 274 | Removed 155 mastocytosis-only |
| v3 (EDS subtyped, final) | 343 | 143 | Removed 155 non-hEDS EDS + 62 EDS-excluded |
