# Provenance Log: Triad Phenotype Mining from PMC Open Access Case Reports

## Project Overview
Systematic extraction of patient-level phenotype data from published case reports in PubMed Central Open Access subset, covering Ehlers-Danlos Syndrome (EDS/hEDS), Postural Orthostatic Tachycardia Syndrome (POTS), and Mast Cell Activation Syndrome (MCAS).

## Audit Trail

### Session Start
- **Date**: 2026-04-16
- **Analyst**: Claude (Anthropic) under direction of afd (ghhercock@gmail.com)
- **Data source**: NCBI PubMed Central E-utilities API
- **Base URL**: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/

---

## 1. Corpus Scoping Queries

### 1.1 Initial Count Queries (2026-04-16)

| Query | Database | Search Term | Count |
|-------|----------|-------------|-------|
| EDS | PMC | (ehlers-danlos OR hEDS) AND case reports[pt] | 3,082 |
| POTS | PMC | (postural orthostatic tachycardia syndrome OR POTS) AND case reports[pt] | 1,475 |
| MCAS | PMC | (mast cell activation syndrome OR MCAS) AND case reports[pt] | 4,837 |

**Note**: These are raw counts before OA filtering, deduplication, or relevance screening.

---

## 2. Methodology Papers Reviewed

| Paper | PMID/DOI | Key Finding | Relevance to This Project |
|-------|----------|-------------|--------------------------|
| RAG-HPO: Improving automated deep phenotyping through LLMs using retrieval-augmented generation | PMID 39677442; DOI 10.1186/s13073-025-01521-w | RAG + LLaMA-3.1 70B achieves P=0.81, R=0.76, F1=0.78 on HPO extraction from case reports. Only 1 hallucination (<1%) in 315 FPs. Validated on 112 case reports (BMJ/Oxford), 1,794 HPO terms. | Validates LLM-based phenotype extraction from case reports as methodologically sound. Provides benchmark F1 for comparison. Informs our validation strategy. |
| CaseReportBench: An LLM Benchmark Dataset for Dense Information Extraction in Clinical Case Reports | arXiv 2505.17265 | 14-category extraction schema from case reports. Category-specific prompting outperforms unified. Qwen2.5-7B outperformed GPT-4o. IAA: TSR 74.65%. 138 annotated case reports. | Directly validates our extraction approach. Category-specific prompting is the recommended strategy. Provides extraction schema template. |
| Can LLMs reliably extract human disease genes from full-text scientific literature? | bioRxiv 2025.07.27.667022 | GPT-4o best balanced performance. >90% of "incorrect" outputs were present in article but wrong salience. Claude-Opus high FP rate from permissive sampling. | Informs our choice of extraction model and temperature settings. Warns about salience errors vs hallucinations. |
| Comparison of rule- and LLM-based phenotype extraction for NF1 | JAMIA 2025; DOI 10.1093/jamia/ocae253 | LLM-based extraction comparable to rule-based for structured phenotype data from clinical notes. | Validates approach for specific disease phenotyping. |
| Ritelli et al. 2024: Looking back and beyond the 2017 hEDS diagnostic criteria | PMID 37774134; AJMG Part A | Only 43% of patients met age-adjusted Beighton score under 2017 criteria at Italian reference centre. | Directly relevant to diagnostic drift hypothesis. Quantifies the criteria-shift problem. |

---

## 3. Corpus Retrieval Log

| Step | Query | Parameters | Records Retrieved | Date |
|------|-------|------------|-------------------|------|
| 1 | EDS_hEDS | ("ehlers-danlos syndrome"[TiAb] OR "ehlers danlos"[TiAb] OR "hypermobile ehlers"[TiAb] OR "hEDS"[TiAb] OR "hypermobility syndrome"[TiAb]) AND "case reports"[pt] AND "open access"[Filter] | 336 | 2026-04-16 |
| 2 | POTS | ("postural orthostatic tachycardia syndrome"[TiAb] OR "postural tachycardia syndrome"[TiAb] OR "POTS"[TiAb]) AND "case reports"[pt] AND "open access"[Filter] | 144 | 2026-04-16 |
| 3 | MCAS | ("mast cell activation syndrome"[TiAb] OR "mast cell activation disease"[TiAb] OR "MCAS"[TiAb] OR "mastocytosis"[TiAb]) AND "case reports"[pt] AND "open access"[Filter] | 240 | 2026-04-16 |
| 4 | TRIAD | Co-occurrence of EDS + POTS + MCAS terms in TiAb, OA filter | 18 | 2026-04-16 |
| 5 | Combined | Union of above, deduplicated on PMCID | 717 unique (738 total, 21 overlaps) | 2026-04-16 |

### 3.1 Corpus Characteristics
- **Year range**: 2004-2026
- **Pre-2017 (before revised hEDS criteria)**: 106 articles
- **Post-2017**: 611 articles
- **Top journals**: Cureus (45), Clin Case Rep (30), J Med Case Rep (16), JACC Case Rep (15)
- **Cross-condition overlap**: EDS+POTS: 12, EDS+MCAS: 1, POTS+MCAS: 5, All three: 1

---

## 4. Adjacent Condition Queries (2026-04-16)

To avoid circular analysis (broad tier applied only to articles already retrieved by narrow queries), independent PMC queries were run for adjacent/umbrella conditions.

| Query | Search Term | PMC OA Count | New PMCIDs (not in original 717) |
|-------|-------------|-------------|----------------------------------|
| JHS | "joint hypermobility syndrome"[TiAb] AND case reports[pt] AND open access[Filter] | 10 | part of 683 |
| HSD | "hypermobility spectrum disorder"[TiAb] AND case reports[pt] AND open access[Filter] | 9 | part of 683 |
| Dysautonomia | "dysautonomia"[TiAb] AND case reports[pt] AND open access[Filter] | 187 | 163 |
| Orthostatic intolerance | "orthostatic intolerance"[TiAb] AND case reports[pt] AND open access[Filter] | 60 | part of 683 |
| Autonomic dysfunction | "autonomic dysfunction"[TiAb] AND case reports[pt] AND open access[Filter] | 481 | 448 |
| Vasovagal syncope | "vasovagal syncope"[TiAb] AND case reports[pt] AND open access[Filter] | 75 | part of 683 |
| Idiopathic anaphylaxis | "idiopathic anaphylaxis"[TiAb] AND case reports[pt] AND open access[Filter] | 12 | part of 683 |
| HAT | "hereditary alpha tryptasemia"[TiAb] AND case reports[pt] AND open access[Filter] | 7 | part of 683 |
| Histamine intolerance | "histamine intolerance"[TiAb] AND case reports[pt] AND open access[Filter] | 2 | part of 683 |
| **Total new** | Union of above, deduplicated, minus original 717 | -- | **683** |

### 4.1 Full-Text Retrieval

| Batch | PMCIDs | Success | Failed | Date |
|-------|--------|---------|--------|------|
| Original corpus | 717 | 717 (100%) | 0 | 2026-04-16 |
| Adjacent conditions | 683 | 683 (100%) | 0 | 2026-04-16 |
| **Total** | **1400** | **1400 (100%)** | **0** | |

All full-text XMLs stored at `data/raw/fulltext/{PMCID}.xml`.

---

## 5. Extraction Pipeline

### 5.1 Schema Version History

| Version | Date | Changes | Rationale |
|---------|------|---------|-----------|
| v1 | 2026-04-16 | Basic regex extraction | Initial pass |
| v2 | 2026-04-16 | Unicode normalisation, article type classification, improved age patterns, negation-aware sex extraction, criteria threshold filtering | Validation revealed missed ages from unicode hyphens, criteria thresholds captured as ages |
| v2+adjacent | 2026-04-16 | Added adjacent condition flags (dysautonomia, OI, vasovagal, IST, histamine intolerance, HAT, JHS, HSD, mastocytosis) | Required for broad-tier classification of adjacent corpus |

### 5.2 Extraction Method

Rule-based regex extraction from PMC NXML full text. Key features:
- Unicode dash normalisation (U+2010-U+2015 to ASCII hyphen)
- Section-prioritised sex extraction (abstract/case presentation first)
- Article type inference (case_report, clinical_study, review_or_study, animal_study)
- Negation prefix filtering for age (criteria thresholds) and conditions
- 20 symptom categories, 13 terminology terms, 6 diagnostic criteria patterns

---

## 6. Validation

### 6.1 Stratified Validation (Original Corpus)

10-article stratified sample (3 EDS, 2 POTS, 2 MCAS, 3 triad). See `data/validation/validation_report.md`.

| Metric | Value |
|--------|-------|
| Symptom Precision | 89.3% |
| Symptom Recall | 80.6% |
| Symptom F1 | 84.7% |
| Age accuracy | 80% |
| Sex accuracy | 70% |
| POTS detection | 100% |
| EDS detection | 80% |
| MCAS detection | 80% |

### 6.2 Known Systematic Errors

1. Article type misclassification (PubMed "case reports" filter imperfect)
2. EDS false positives from negation (rule-based lacks full negation handling)
3. Multi-subject demographic confusion (mother/infant pairs)
4. GI symptom false positives from acute surgical presentations
5. MCAS overclassification from keyword "mast cell" in unrelated contexts

---

## 7. Data Processing Steps

| Step | Input | Output | Script | Records In | Records Out | Notes |
|------|-------|--------|--------|-----------|-------------|-------|
| 1 | PMC E-utilities | Corpus metadata CSVs | 01_corpus_retrieval.py | N/A | 717 unique PMCIDs | 4 queries (EDS, POTS, MCAS, triad), OA filter applied |
| 2 | 717 PMCIDs | Full-text XMLs + rule-based extractions | 03_fulltext_extract.py | 717 | 717 (100% success) | v2 extraction with unicode normalisation, article type classification |
| 3 | Extractions | Condition reclassification | inline analysis | 717 | 717 | Full-text condition detection: 155 mastocytosis-only excluded |
| 4 | Reclassified extractions | Dataset v2 (CSV) | 04_build_dataset.py / inline | 717 | 560 included | Improved age extraction (92.3% for case reports), quoted age text, age range mapping |
| 5 | EDS articles | EDS subtype classification | inline | 390 | 390 classified | hEDS/HSD: 132, vascular: 147, classical: 10, other: 3, excluded: 80, unspecified: 18 |
| 6 | Dataset v2 | Dataset v3 final | inline | 560 | 343 included | Removed 155 non-hEDS subtypes + 62 EDS-mentioned-but-excluded (no POTS/MCAS co-mention) |
| 7 | Validation | Validation report | manual + inline | 10 sample | 10 validated | Symptom F1=84.7%, Age accuracy=80%, POTS detection=100% |
| 8 | Adjacent PMC queries | Adjacent metadata CSVs | inline | N/A | 683 new PMCIDs | 9 queries for umbrella/adjacent conditions |
| 9 | 683 new PMCIDs | Full-text XMLs + extractions | 06_adjacent_extract.py | 683 | 683 (100% success) | Same v2 extraction + adjacent condition flags |
| 10 | Original + adjacent | Unified tiered classification | 07_merge_and_reclassify.py | 1400 | 1400 | Merged corpora, rebuilt narrow/broad tiers, added adjacent flags to original corpus |
| 11 | Unified corpus | Expanded analysis | 08_expanded_analysis.py | 1400 | 688 case reports analysed | Narrow vs broad, pre/post 2017, co-occurrence, temporal trends |

---

## 8. Unified Corpus Summary (v4)

| Metric | Value |
|--------|-------|
| Total articles | 1400 |
| Original corpus | 717 |
| Adjacent corpus | 683 |
| Case reports | 688 |
| Clinical studies | 326 |
| Reviews/other | 175 |
| Animal studies | 211 |

### 8.1 Tiered Classification

| Condition | Narrow | Broad | Broad-only |
|-----------|--------|-------|------------|
| EDS/hEDS | 404 | 409 | 5 |
| POTS | 293 | 903 | 610 |
| MCAS | 333 | 336 | 3 |
| Triad | 60 | 69 | 9 |

The POTS broad tier gained 610 genuine non-overlapping articles (primarily dysautonomia/autonomic dysfunction). EDS and MCAS broad tiers gained few (5 and 3) because JHS/HSD and histamine intolerance have very small PMC OA literatures (10 and 2 articles respectively).

### 8.2 Key Findings

**Narrow vs Broad (POTS focus, case reports only):**
- POTS narrow (n=119) vs dysautonomia/OI broad-only (n=284) show large symptom profile differences
- POTS-specific: tachycardia (+61%), fatigue (+47%), orthostatic intolerance (+46%), palpitations (+43%), headache (+31%), syncope (+30%), joint hypermobility (+27%), chronic pain (+17%)
- These are not just severity differences; POTS case reports systematically report more multi-system symptoms

**Pre-2017 vs Post-2017 Diagnostic Drift:**
- hEDS: fatigue +17%, skin hyperextensibility +12%, tachycardia +12%, easy bruising -16%
- POTS: fatigue +38%, orthostatic intolerance +20%, neuropathy +15%, flushing +14%
- MCAS: tachycardia +22%, syncope +19%, anaphylaxis +19%, joint hypermobility +16%, orthostatic intolerance +16%, neuropathy +16%

**Adjacent Condition Profiles (exclusive groups, case reports):**
- Dysautonomia-only (n=232): dominated by neuropathy (56%), GI (47%), tachycardia (32%)
- POTS-only (n=63): tachycardia (94%), syncope (56%), palpitations (51%), neuropathy (51%), fatigue (49%)
- hEDS-only (n=162): joint hypermobility (56%), GI (33%), chronic pain (24%)
- MCAS-only (n=132): GI (58%), flushing (44%), anaphylaxis (43%), urticaria (38%)
- Triad (n=18): fatigue (89%), tachycardia (94%), joint hypermobility (83%), GI (67%), headache (61%)

---

## 9. Known Limitations and Caveats

1. Case reports are a biased sample (unusual presentations over-represented)
2. PMC OA subset is not the full literature (OA mandate coverage varies by journal/funder)
3. Rule-based extraction has error rates (symptom F1 = 84.7%); no LLM extraction performed
4. Cannot infer population prevalence from case report frequencies
5. Geographic bias: English-language and OA-mandate countries over-represented
6. EDS and MCAS broad tiers have too few broad-only articles for meaningful narrow vs broad comparison (5 and 3 respectively); the adjacent literature for JHS/HSD and histamine intolerance is genuinely sparse in PMC OA
7. Pre-2017 sample sizes are small (e.g. POTS narrow pre-2017: n=12), limiting statistical power for drift comparisons
8. Triad articles (n=18 narrow case reports) are too few for robust subgroup analysis
9. "Broad-only" dysautonomia articles may include conditions unrelated to the triad (e.g. diabetic autonomic neuropathy, familial dysautonomia), diluting the comparison
10. Article type classification is heuristic; some misclassification is expected
