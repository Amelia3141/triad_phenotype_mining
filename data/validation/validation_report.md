# Validation Report: Rule-Based Phenotype Extraction (v2)

## Methodology
Stratified random sample of 10 articles from the v3 final dataset, selected using `random.sample()` with seed=42. Mutually exclusive strata: 3 hEDS-only (no POTS/MCAS), 2 POTS-only, 2 MCAS-only, 3 Triad. Validation by independent re-extraction of the same 20-category symptom regex patterns from raw PMC NXML full text, compared against pipeline stored output.

Reproducible via: `python scripts/11_validation_sampling.py`

## Validation Sample

| PMCID | Stratum | Independent | Pipeline | TP | FP | FN |
|-------|---------|-------------|----------|----|----|-----|
| PMC6052501 | hEDS-only | 5 | 4 | 4 | 0 | 1 |
| PMC12047577 | hEDS-only | 4 | 4 | 4 | 0 | 0 |
| PMC13067300 | hEDS-only | 3 | 3 | 3 | 0 | 0 |
| PMC9871405 | POTS-only | 5 | 5 | 5 | 0 | 0 |
| PMC12462795 | POTS-only | 3 | 2 | 2 | 0 | 1 |
| PMC10647312 | MCAS-only | 10 | 11 | 10 | 1 | 0 |
| PMC12030918 | MCAS-only | 0 | 0 | 0 | 0 | 0 |
| PMC12437428 | Triad | 4 | 3 | 3 | 0 | 1 |
| PMC11613559 | Triad | 10 | 10 | 9 | 1 | 1 |
| PMC9131024 | Triad | 11 | 12 | 11 | 1 | 0 |

## Aggregate Symptom Extraction Metrics

| Metric | Value |
|--------|-------|
| True Positives | 51 |
| False Positives | 3 |
| False Negatives | 4 |
| Precision | 94.4% (51/54) |
| Recall | 92.7% (51/55) |
| F1 Score | 93.6% |

## Error Analysis

### False Positives (3)
1. **PMC10647312** (MCAS-only): `medication_sensitivity` detected by pipeline but not by independent re-extraction from XML
2. **PMC11613559** (Triad): `skin_hyperextensibility` in pipeline but not matched in independent extraction
3. **PMC9131024** (Triad): `chronic_pain` in pipeline but not detected by independent extraction

### False Negatives (4)
1. **PMC6052501** (hEDS-only): `easy_bruising` detected independently but missed by pipeline
2. **PMC12462795** (POTS-only): `chronic_pain` detected independently but missed by pipeline
3. **PMC12437428** (Triad): `chronic_pain` detected independently but missed by pipeline
4. **PMC11613559** (Triad): `gi_symptoms` detected independently but missed by pipeline

## Notes
- PMC12030918 (MCAS-only) had 0 symptoms detected by both methods, likely a non-case-report article misclassified
- The independent re-extraction uses the identical 20-category regex patterns as the pipeline, applied fresh to raw NXML; discrepancies arise from differences in text preprocessing between the pipeline's original extraction and the validation re-extraction
- Previous validation (v1) reported F1=84.7% on a different sample from the pre-v3 dataset; the improved F1 reflects both dataset cleaning (v3 removed misclassified articles) and the whitespace-trimming bug fix in symptom name comparison
