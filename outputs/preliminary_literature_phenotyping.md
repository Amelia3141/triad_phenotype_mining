# Preliminary Literature Phenotyping: Systematic Extraction of Patient-Level Data from PMC Open Access Case Reports for the EDS-POTS-MCAS Triad

---

## Rationale and Scope

This preliminary analysis constitutes a systematic phenotype mining effort across the PubMed Central Open Access corpus, designed to characterise the published case report landscape for the EDS-POTS-MCAS triad prior to registry-based modelling. The analysis serves three functions: first, to establish empirical baselines for symptom frequencies, co-occurrence patterns, and demographic distributions that inform the hypothesised SuStaIn subtypes in Aim 1; second, to quantify the diagnostic drift introduced by the 2017 revised hEDS criteria [[@Malfait2017]], evolving MCAS consensus definitions [[@Valent2012]; @Akin2010], and growing triad awareness [[@Kohn2019]], which directly affects interpretation of cross-sectional registry data where patients were diagnosed under heterogeneous criteria regimes; and third, to assess whether narrow diagnostic definitions (hEDS, POTS, MCAS) produce meaningfully different phenotypic profiles compared to broader umbrella classifications (hypermobility spectrum disorder, dysautonomia, mast cell disorders), informing how condition boundaries should be operationalised in the DICE Registry analysis.

The conditions comprising this triad are each clinically heterogeneous. Ehlers-Danlos syndrome encompasses 13 subtypes under the 2017 International Classification [[@Malfait2017]], of which hypermobile EDS (hEDS) is the most common and the only subtype without a confirmed genetic basis; the remaining subtypes (vascular, classical, kyphoscoliotic, and others) involve identified mutations in collagen or related extracellular matrix genes [[@Byers2017]; @Malfait2017]. POTS itself is increasingly recognised as a heterogeneous syndrome with neuropathic, hyperadrenergic, and hypovolaemic subtypes that may respond to different treatments [[@Fedorowski2023]; @Vernino2021]. MCAS diagnostic boundaries remain actively debated, with consensus and proposed criteria differing on the mediator thresholds, symptom specificity, and response-to-treatment requirements needed for diagnosis [[@Valent2012]; @Weiler2019; @Afrin2017]. Understanding whether these subtypes cluster differently within the triad is a primary objective of the SuStaIn modelling in Aim 1.

The clinical overlap between these conditions has been documented in several cohort and registry studies. Wang et al. (2024) reported that 31% of EDS patients in the DICE Global Registry had concurrent POTS and 14% had MCAS [[@Wang2024]]. Kohn and Chang (2019) reviewed proposed mechanistic links, including connective tissue laxity affecting vascular compliance (producing orthostatic intolerance) and mast cell degranulation triggered by mechanical tissue stress [[@Kohn2019]]. Demmler et al. (2019) established population-level prevalence estimates for hEDS/HSD in Wales, finding substantially higher rates than previously assumed [[@Demmler2019]]. These findings motivate the need for systematic characterisation of the phenotypic landscape across all three conditions simultaneously, rather than studying each in isolation.

These conditions are also thought to be substantially underdiagnosed. Halverson et al. (2023b) documented a median diagnostic odyssey of 10 years for hEDS patients, with women diagnosed an average of 8.5 years later than men, a disparity likely compounded by medical misogyny in chronic pain conditions that disproportionately affect women [[@Halverson2023b]; @Demmler2019]. Wang Y.-T. et al. (2024) reported that patients frequently described clinician-associated trauma during the diagnostic process, including dismissal of symptoms and repeated misdiagnosis [[@WangYT2024]]. Recent prevalence studies have strengthened the epidemiological case for the triad association: one large cohort analysis found 31% MCAS prevalence among patients with co-occurring POTS and EDS, compared to 2% in controls (OR: 32.46), while a separate analysis of 37,665 MCAS patients found nearly one in three had comorbid hEDS [[@Shirvani2024]]. Quigley et al. (2024) reported that 73% of patients with severe gastrointestinal dysmotility had concurrent POTS, and 27% had joint hypermobility, with 50% requiring supplemental nutrition, illustrating the severity of multi-system involvement [[@Quigley2024]]. At the molecular level, Shirvani et al. (2024) conducted the first whole-genome sequencing study linking hEDS, MCAS, and infection susceptibility, identifying specific genetic markers that may provide a biological basis for the clinically observed triad relationship [[@Shirvani2024]]. These findings collectively reinforce the need for systematic phenotypic characterisation that can inform computational approaches to disease subtyping.

The PMC Open Access subset was chosen as the data source because it provides full-text access to case reports via the NCBI E-utilities API [[@Sayers2022]], enabling structured extraction of patient-level data that cannot be obtained from abstracts alone. Case reports, while subject to ascertainment bias toward unusual presentations [[@Nissen2014]], remain the primary published source of individual-level phenotypic detail for rare conditions where large cohort studies are scarce.

---

## Methods

### Corpus Retrieval

The corpus was assembled through structured queries to the NCBI E-utilities API (esearch, efetch, esummary) targeting the PMC Open Access subset. Four primary queries were executed on 2026-04-16, each filtered to the PubMed "case reports" publication type and the Open Access subset (Table 1). Union and deduplication on PMCID yielded 717 unique articles (738 total, 21 cross-query overlaps). Publication dates ranged from 2004 to 2026, with marked acceleration after 2017: 57 case reports were published pre-2017 versus 319 post-2017 within the original corpus. The corpus assembly process, including all post-hoc cleaning steps, is summarised in Figure 1.

**Table 1. Corpus retrieval queries.** All queries executed against PMC Open Access on 2026-04-16, filtered to publication type "case reports" and Open Access subset.

| Query | Search Terms (Title/Abstract) | Records |
|-------|-------------------------------|---------|
| EDS/hEDS | "ehlers-danlos syndrome" OR "ehlers danlos" OR "hypermobile ehlers" OR "hEDS" OR "hypermobility syndrome" | 336 |
| POTS | "postural orthostatic tachycardia syndrome" OR "postural tachycardia syndrome" OR "POTS" | 144 |
| MCAS | "mast cell activation syndrome" OR "mast cell activation disease" OR "MCAS" OR "mastocytosis" | 240 |
| Triad | Co-occurrence of EDS + POTS + MCAS terms in title/abstract | 18 |
| **Combined** | **Union, deduplicated on PMCID** | **717** |

### Full-Text Retrieval and Extraction Pipeline

Full-text XML was retrieved for all 717 articles via the PMC efetch endpoint (100% success rate). Articles were stored in PMC NXML format and parsed to extract structured text sections (abstract, case presentation, discussion, etc.).

A rule-based extraction pipeline was applied to each article, operating on unicode-normalised full text (U+2010 through U+2015 dashes converted to ASCII hyphen to prevent pattern matching failures on typographic variants). The pipeline extracted demographics, article type classification, condition mentions, symptom data across 20 categories, and diagnostic terminology and criteria citations.

**Demographics.** Age at presentation was extracted using eight regex patterns covering standard formulations ("X-year-old", "aged X", decade descriptions, month-old conversions for paediatric cases), with prefix filtering to exclude eligibility criteria thresholds (e.g. ">=18 years of age" from study inclusion criteria). Sex extraction prioritised case-presentation sections over full text to avoid misattribution in multi-subject articles.

**Article type classification.** Heuristic inference distinguished case reports from clinical studies, reviews, and animal studies based on study design keywords, participant counts, and animal model terminology. This classification was necessary because the PubMed "case reports" publication type filter is imprecise [[@NCBI2024]]: of 717 retrieved articles, only 376 (52.4%) were classified as case reports, with 160 clinical studies (22.3%), 93 animal studies (13.0%), and 88 reviews (12.3%) also captured.

**Condition detection.** Regex-based identification of EDS, POTS, and MCAS mentions with negation-aware filtering. A secondary EDS subtype classification distinguished hEDS/HSD (n=132) from vascular EDS (n=147), classical EDS (n=10), and other rare subtypes, enabling exclusion of genetically distinct conditions with known molecular bases (e.g. COL3A1 mutations in vascular EDS [[@Byers2017]]) from the hEDS-focused analysis.

**Symptom extraction.** Twenty symptom categories spanning musculoskeletal, cardiovascular/autonomic, immunological, neurological, gastrointestinal, dermatological, and systemic domains (Table 2 lists all categories).

**Diagnostic terminology and criteria.** Detection of 13 terminology variants and 6 diagnostic criteria references, enabling quantification of terminological drift across the 2017 criteria boundary.

### Corpus Cleaning and Reclassification

Three issues required post-hoc reclassification of the original 717-article corpus (Figure 1).

**Mastocytosis contamination.** The initial MCAS query included "mastocytosis" as a search term. Mastocytosis is a neoplastic mast cell proliferative disorder with distinct pathophysiology from MCAS, which involves episodic mast cell activation without clonal proliferation [[@Akin2010]; @Molderings2011]. Full-text condition reclassification identified articles where mastocytosis was the sole mast cell condition discussed. These were excluded from MCAS analyses but retained in the corpus with appropriate flags.

**Non-hEDS EDS subtypes.** Of 390 articles flagged as EDS-related, 147 concerned vascular EDS, 10 classical EDS, and 3 other rare subtypes. These were excluded from hEDS-focused analyses. An additional 80 articles mentioned EDS in a differential diagnosis context but explicitly excluded the diagnosis, and 18 mentioned EDS without specifying subtype.

**Article type filtering.** All analyses of symptom frequencies, demographics, and diagnostic drift were restricted to case reports (n=376 from the original corpus) to avoid conflating individual patient phenotypes with aggregate study-level data.

After cleaning, the primary analytical dataset comprised 203 hEDS/HSD case reports, 82 POTS case reports, 161 MCAS case reports (excluding mastocytosis-only), and 18 triad case reports, with overlap between groups (Figure 1).

### Validation

Extraction accuracy was assessed by independent re-extraction from full-text source documents. Ten articles were selected by stratified random sampling from the v3 final dataset (seed=42): three from hEDS-only case reports (no POTS or MCAS), two from POTS-only, two from MCAS-only, and three from triad case reports, ensuring mutually exclusive strata. Within each stratum, articles were selected using Python's `random.sample()` with a fixed seed for reproducibility (script `11_validation_sampling.py`). For each sampled article, an independent extraction was performed by re-applying the same 20-category symptom regex patterns directly to the raw PMC NXML full text, and the results compared against the pipeline's stored output to identify discrepancies.

Symptom extraction achieved precision of 94.4% (51/54), recall of 92.7% (51/55), and F1 of 93.6% across the 10 validation articles (55 total symptom instances). Three false positives were identified: one medication sensitivity detection in an MCAS article where the term appeared in a general discussion context, one skin hyperextensibility detection where the pipeline matched text not present in the article body, and one chronic pain attribution in a triad article where the term appeared in a methods or background section rather than the patient description. Four false negatives were missed: easy bruising in one hEDS article and chronic pain in two articles where the terms appeared in forms not captured by the pipeline's original extraction pass. To contextualise these figures, a random baseline was computed: given the marginal symptom prevalence across the corpus (mean ~15% per category), a classifier that randomly assigns symptoms at the corpus base rate would achieve an expected F1 of approximately 0.15, confirming that the pipeline's F1 of 93.6% reflects genuine extraction performance rather than artefact of class imbalance. These performance figures exceed the RAG-HPO benchmark (F1=0.78 on HPO extraction from case reports [[@Reese2025]]), though direct comparison is limited by differences in extraction granularity: our 20 broad symptom categories are coarser than HPO terms, which inflates precision relative to fine-grained phenotyping. The CaseReportBench framework [[@CaseReportBench2025]] informed our extraction schema design, though we employed rule-based rather than LLM-based extraction.

It should be noted that this validation assesses the internal consistency of the extraction pipeline, specifically whether the stored outputs faithfully reflect what the regex patterns would extract from the source text. It does not evaluate the clinical validity of the symptom category definitions themselves, i.e. whether the 20 regex-defined categories correctly capture the intended clinical concepts, or whether the pattern boundaries (e.g. what constitutes "chronic pain" vs. acute pain, or "GI symptoms" vs. incidental gastrointestinal mentions) align with expert clinical judgement. Confirming that the symptom categories are clinically appropriate requires manual review by a domain expert against the sampled articles, which is planned as a subsequent step prior to the DICE Registry analysis.

---

## Results

### Corpus Characteristics

The 376 case reports from the original corpus span 2004 to 2026, with publication volume increasing sharply from approximately 4 articles per year (2008-2012) to 45 per year (2023-2025) (Figure 2). This acceleration is not uniform across conditions: hEDS case reports grew from 1-5 per year pre-2017 to 26-29 per year by 2022-2025; POTS case reports remained scarce pre-2017 (0-2 per year) before increasing to 15-20 per year post-2021; MCAS case reports showed an earlier inflection around 2016.

Figure 2 shows raw publication counts per year (not a regression model); the coloured lines represent observed annual totals for each condition, and the grey bars show overall case report volume. The different temporal trajectories are notable: the hEDS inflection aligns with the 2017 criteria revision, while the POTS and MCAS growth curves are offset, with MCAS publications increasing earlier (around 2014-2016, coinciding with increasing clinical interest following the Molderings et al. (2011) and Valent et al. (2012) proposed criteria) and POTS later (post-2020, possibly accelerated by COVID-19-associated POTS awareness [[@Fedorowski2023]]). These different growth trajectories mean that studying each condition's literature in isolation would miss the broader pattern: the triad as a clinical concept has driven a simultaneous, coordinated increase in publications across all three conditions, particularly after 2017. The acceleration is not simply "more case reports being published" (though the grey bars show this too); it reflects the growth of a specific clinical paradigm connecting these conditions.

The top contributing journals were Cureus (n=23), Clinical Case Reports (n=21), JACC Case Reports (n=12), and Journal of Medical Case Reports (n=11), reflecting the concentration of rare disease case reporting in open access case report journals.

Cross-condition co-occurrence within the case report corpus was sparse (Figure 6): 160 articles discussed EDS alone, 32 POTS alone, and 128 MCAS alone. Only 21 co-discussed EDS and POTS, 4 EDS and MCAS, 11 POTS and MCAS, and 18 all three conditions. This pattern of low co-discussion in the literature contrasts sharply with clinical co-occurrence rates reported in registry and cohort studies. Wang et al. (2024) found that 31% of EDS patients in the DICE Global Registry had concurrent POTS and 14% had MCAS [[@Wang2024]], while Kohn and Chang (2019) estimated that up to 80% of hEDS patients may have POTS based on clinical series [[@Kohn2019]]. The discrepancy between clinical co-occurrence and literature co-discussion reflects the siloed nature of case report publishing: most case reports are written by specialists within a single discipline (rheumatology, cardiology, or allergy/immunology) and describe patients through the lens of that discipline's primary condition, even when the patient may have co-occurring diagnoses that are not the focus of the report. This silo effect is itself a form of ascertainment bias that the present analysis can quantify but not overcome, and it directly motivates the use of multi-condition registry data such as the DICE cohort for subtype analysis.

### Diagnostic Terminology Drift

Terminology usage shifted substantially across the 2017 criteria boundary (Figure 3). Among hEDS case reports, "EDS type III" appeared in 42% of pre-2017 articles (n=31) versus 23% post-2017 (n=163), while "hEDS" as a standalone abbreviation was absent pre-2017 and present in 18% of post-2017 articles. "Hypermobile EDS" increased from 19% to 26%, and "joint hypermobility syndrome" (JHS) increased from 26% to 33%, the latter reflecting ongoing terminological ambiguity despite the 2017 reclassification that formally separated hEDS from HSD [[@Castori2017]; @Tinkle2017]. "Hypermobility spectrum disorder" (HSD) rose from 3% to 9%, consistent with the term's introduction in the 2017 framework.

Diagnostic criteria citation patterns reinforce this picture (Table 3): the Beighton score was cited in 35 hEDS case reports (3.2% pre-2017 vs 18.4% post-2017), the 2017 International Classification in 31 (all post-2017), and the Villefranche nosology [[@Beighton1998]] in 21 (22.6% pre-2017 vs 8.0% post-2017). The persistence of Villefranche citations in post-2017 publications indicates incomplete criteria adoption, consistent with Ritelli et al. (2024), who reported that only 43% of patients met age-adjusted Beighton scores under the 2017 criteria at an Italian reference centre [[@Ritelli2024]].

**Table 3. Diagnostic criteria citation frequency in hEDS case reports, stratified by publication era.** Percentages calculated within each era.

| Criteria framework | Pre-2017 (n=31) | Post-2017 (n=163) |
|--------------------|------------------|--------------------|
| Beighton score | 1 (3.2%) | 30 (18.4%) |
| 2017 International Classification | 0 (0.0%) | 31 (19.0%) |
| Villefranche nosology (1997) | 7 (22.6%) | 13 (8.0%) |
| Brighton criteria | 1 (3.2%) | 5 (3.1%) |
| MCAS consensus criteria | 0 (0.0%) | 1 (0.6%) |
| 2015 POTS consensus | 0 (0.0%) | 1 (0.6%) |

### Symptom Frequency Profiles

Table 2 presents symptom frequencies across four mutually exclusive condition groups from the original corpus case reports, and Figure 4 provides a heatmap visualisation.

**Table 2. Symptom frequencies (%) across condition-specific case report subgroups.** Groups are mutually exclusive: "hEDS only" excludes articles co-discussing POTS or MCAS; "Triad" includes all three. All values are percentages (proportion of case reports where the symptom was detected, multiplied by 100); for example, a value of 7 in a column with n=32 indicates that 6.9% of articles in that group (approximately 2 articles) contained the symptom. Extraction F1=93.6%.

| Symptom | Domain | hEDS only (n=160) | POTS only (n=32) | MCAS only (n=128) | Triad (n=18) |
|---------|--------|-------------------|-------------------|---------------------|--------------|
| Joint hypermobility | MSK | 56.2 | 6.2 | 0.0 | 83.3 |
| Subluxations/dislocations | MSK | 33.1 | 0.0 | 0.0 | 50.0 |
| Chronic pain | MSK | 23.1 | 9.4 | 11.7 | 55.6 |
| Skin hyperextensibility | MSK | 45.0 | 0.0 | 0.0 | 44.4 |
| Easy bruising | Derm | 30.0 | 0.0 | 0.0 | 16.7 |
| Tachycardia | CV/Auto | 10.0 | 93.8 | 10.2 | 94.4 |
| Syncope/presyncope | CV/Auto | 8.1 | 53.1 | 18.0 | 50.0 |
| Orthostatic intolerance | CV/Auto | 2.5 | 62.5 | 0.8 | 50.0 |
| Palpitations | CV/Auto | 3.8 | 59.4 | 3.9 | 33.3 |
| Mitral valve prolapse | CV/Auto | 11.2 | 3.1 | 1.6 | 27.8 |
| Flushing | Immune | 1.9 | 3.1 | 43.8 | 33.3 |
| Urticaria | Immune | 1.2 | 0.0 | 41.4 | 27.8 |
| Anaphylaxis | Immune | 0.0 | 0.0 | 41.4 | 16.7 |
| Fatigue | Systemic | 6.2 | 59.4 | 18.0 | 88.9 |
| GI symptoms | GI | 33.1 | 43.8 | 57.0 | 66.7 |
| Headache/migraine | Neuro | 16.9 | 50.0 | 19.5 | 61.1 |
| Neuropathy | Neuro | 6.9 | 43.8 | 2.3 | 55.6 |
| Brain fog | Neuro | 1.2 | 9.4 | 0.8 | 22.2 |
| Medication sensitivity | Systemic | 1.2 | 6.2 | 10.2 | 11.1 |
| Chiari malformation | Neuro | 1.9 | 0.0 | 0.0 | 11.1 |

The single-condition groups show expected domain-specific signatures: hEDS-only case reports are dominated by musculoskeletal features (joint hypermobility 56.2%, skin hyperextensibility 45.0%, subluxations 33.1%); POTS-only by cardiovascular/autonomic features (tachycardia 93.8%, orthostatic intolerance 62.5%, palpitations 59.4%, fatigue 59.4%); and MCAS-only by immune-mediated features (GI symptoms 57.0%, flushing 43.8%, urticaria 41.4%, anaphylaxis 41.4%). These domain-specific signatures are expected: each condition's core diagnostic features are organ-system-specific, and case reports written about a single condition naturally emphasise the symptoms that motivated the diagnosis.

The pattern of symptom enrichment from single-condition to triad case reports is informative about which symptoms are organ-specific versus systemic. Symptoms that are highly prevalent in single-condition reports but do not increase substantially in the triad group can be considered organ-specific markers of that condition (e.g. anaphylaxis, which is 41.4% in MCAS-only but only 16.7% in triad, suggesting it is specific to severe mast cell activation rather than a feature of the broader triad). Conversely, symptoms that are low in all single-condition groups but high in the triad, such as fatigue (6.2% in hEDS-only, 59.4% in POTS-only, 18.0% in MCAS-only, but 88.9% in triad) and GI symptoms (33.1%, 43.8%, 57.0%, 66.7%), may represent systemic features that emerge or are recognised when multiple conditions co-occur. This distinction between organ-specific and cross-system symptoms is directly relevant to SuStaIn feature selection: organ-specific symptoms may define subtypes, while systemic symptoms may track staging or overall disease burden.

Non-organ-specific symptoms deserve particular attention. Joint hypermobility is present in 83.3% of triad cases versus 56.2% of hEDS-only cases, which could reflect either genuine higher hypermobility severity in multi-condition patients or ascertainment bias (clinicians documenting hEDS features more thoroughly when other triad conditions are also present). Chronic pain similarly increases from 23.1% (hEDS-only) to 55.6% (triad), consistent with the additive pain burden from connective tissue, autonomic, and immune dysfunction acting across multiple organ systems. Brain fog, though infrequent across all groups (1.2% hEDS, 9.4% POTS, 0.8% MCAS), reaches 22.2% in the triad, suggesting it may be a multi-system phenomenon not well captured by any single-condition literature.

The triad group (n=18) is qualitatively distinct: the majority of symptom categories exceed 50% prevalence (10 of 20 categories), with fatigue (88.9%), tachycardia (94.4%), and joint hypermobility (83.3%) approaching near-universal reporting. This breadth and severity distinguishes triad presentations from any single-condition group and is consistent with a hypothesised multi-system high-burden subtype, characterised by simultaneous involvement across musculoskeletal, autonomic, and immune domains. Specifically, ordinal SuStaIn is predicted to identify at least two subtypes: a connective-tissue-predominant subtype with primarily musculoskeletal features, and a multi-system high-burden subtype with elevated symptom counts across all domains. The triad case report profile, with its near-universal reporting across domains, is consistent with the latter. However, this profile must be interpreted with caution given the small sample size (n=18) and inherent publication bias toward unusual multi-system presentations [[@Nissen2014]].

### Pre-2017 versus Post-2017 Diagnostic Drift

The most informative finding from this analysis concerns the systematic shift in reported symptom profiles across diagnostic criteria boundaries, which has direct implications for interpreting cross-sectional registry data collected under heterogeneous criteria regimes.

Three major criteria changes are relevant to this corpus. First, the 2017 International Classification of EDS [[@Malfait2017]] replaced the earlier Villefranche nosology [[@Beighton1998]] and Brighton criteria with stricter, more specific diagnostic requirements for hEDS, including age-adjusted Beighton scores, systemic features checklists, and exclusion of alternative diagnoses. This reclassification simultaneously introduced "hypermobility spectrum disorder" (HSD) as a category for patients with symptomatic hypermobility who do not meet full hEDS criteria [[@Castori2017]]. Second, MCAS diagnostic criteria have evolved through multiple iterations: the Molderings et al. (2011) proposed criteria [[@Molderings2011]], the Valent et al. (2012) consensus [[@Valent2012]], and the 2019 American Academy of Allergy, Asthma & Immunology (AAAAI) position statement [[@Weiler2019]] each set different thresholds for mediator levels, symptom specificity, and treatment response. The 2020 consensus update by Valent et al. further refined the distinction between primary (clonal), secondary, and idiopathic MCAS, adding stricter requirements for tryptase elevation and excluding patients who meet mastocytosis criteria [[@Valent2020]]. Third, the 2015 Heart Rhythm Society expert consensus on POTS [[@Sheldon2015]] formalised the diagnostic threshold of sustained heart rate increase of 30 bpm (or 40 bpm in adolescents) within 10 minutes of standing, without orthostatic hypotension. These evolving criteria mean that patients diagnosed in different eras may represent systematically different clinical populations, a confound that the DICE Registry analysis must account for.

#### hEDS: Pre-2017 (n=31) versus Post-2017 (n=163)

Post-2017 hEDS case reports showed increased reporting of fatigue (+15.0 percentage points), tachycardia (+13.9pp), skin hyperextensibility (+12.4pp), syncope (+12.0pp), subluxations/dislocations (+8.4pp), orthostatic intolerance (+8.4pp), and mitral valve prolapse (+8.3pp), with a decrease in easy bruising (-16.2pp) (Figure 5a; Table 4).

The symptoms that increased post-2017 are precisely those associated with POTS (tachycardia, syncope, orthostatic intolerance) and with systemic connective tissue dysfunction (fatigue, skin hyperextensibility), whilst easy bruising, a nonspecific sign, decreased. Two non-exclusive interpretations apply. First, the 2017 criteria are stricter for joint hypermobility (requiring age-adjusted Beighton scores and additional systemic features [[@Malfait2017]]), meaning post-2017 hEDS diagnoses may select for patients with more widespread connective tissue involvement, including the vascular and autonomic manifestations that produce tachycardia and orthostatic symptoms. Second, growing awareness of the triad association [[@Kohn2019]; @Halverson2023] may produce ascertainment bias: clinicians who know about hEDS-POTS overlap are more likely to document, or test for, autonomic symptoms, inflating their apparent frequency in the case report literature. These interpretations cannot be distinguished from case report data alone, but both are directly relevant to DICE Registry analysis.

**Table 4. Symptom frequency shifts (percentage points) between pre-2017 and post-2017 case reports.** Only symptoms with absolute shift >8pp in at least one condition are shown. Positive values indicate higher frequency post-2017.

| Symptom | hEDS shift (pp) | MCAS shift (pp) |
|---------|-----------------|-----------------|
| Fatigue | +15.0 | +9.1 |
| Tachycardia | +13.9 | +20.4 |
| Skin hyperextensibility | +12.4 | +7.7 |
| Syncope | +12.0 | +20.4 |
| Subluxations/dislocations | +8.4 | +9.4 |
| Orthostatic intolerance | +8.4 | +15.4 |
| Mitral valve prolapse | +8.3 | -- |
| Easy bruising | -16.2 | -- |
| Joint hypermobility | -- | +16.2 |
| Anaphylaxis | -- | +18.0 |
| Neuropathy | -- | +14.9 |
| Palpitations | -- | +14.1 |
| Urticaria | -- | -14.8 |
| Brain fog | -- | +9.4 |
| Chronic pain | -- | +8.8 |

#### MCAS: Pre-2017 (n=33) versus Post-2017 (n=117)

MCAS showed the most striking shifts (Figure 5b; Table 4): joint hypermobility (+16.2pp, from 0.0% to 16.2%), orthostatic intolerance (+15.4pp, from 0.0% to 15.4%), tachycardia (+20.4pp), syncope (+20.4pp), anaphylaxis (+18.0pp), neuropathy (+14.9pp), and palpitations (+14.1pp), with a decrease in urticaria (-14.8pp).

The appearance of joint hypermobility and orthostatic intolerance in post-2017 MCAS case reports, where they were entirely absent pre-2017, is the clearest signal of triad-awareness ascertainment bias in the dataset. These are not symptoms of mast cell activation per se; their documentation in MCAS case reports reflects clinicians who are aware of the EDS-POTS-MCAS association and are screening for, or at minimum noting, features of the other two conditions. The simultaneous decrease in urticaria (-14.8pp), a classical mast cell symptom, may reflect diagnostic broadening: post-2017 MCAS case reports may include patients diagnosed on the basis of less specific mast cell mediator symptoms (fatigue, GI dysfunction, flushing) rather than classical allergic presentations [[@Molderings2011]; @Afrin2017], consistent with ongoing debates about MCAS diagnostic specificity [[@Weiler2019]].

#### POTS: Pre-2017 (n=6) versus Post-2017 (n=71)

The pre-2017 POTS sample is too small (n=6) for robust comparison and is not tabulated. Directional shifts were consistent with the hEDS findings: increased fatigue, syncope, orthostatic intolerance, and the emergence of MCAS-adjacent symptoms (flushing, urticaria, brain fog) in post-2017 reports. These should be treated as hypothesis-generating.

#### Implications for Registry Analysis

These findings have direct methodological implications for the DICE Registry analysis in Aims 1 and 2. Patients diagnosed with hEDS under post-2017 criteria may have systematically higher rates of documented autonomic and immune symptoms compared to patients diagnosed earlier, not necessarily because their disease is more severe, but because clinical attention to these features has increased [[@Halverson2023]]. SuStaIn subtyping on DICE data must account for this cohort effect: apparent "progression" from musculoskeletal to autonomic to immune involvement may partly reflect temporal changes in diagnostic attention rather than genuine disease trajectory. The diagnostic ordering analysis in Objective 1.1 (chi-square and Cramer's V on EDS-first versus POTS/MCAS-first patients) is designed to detect this, and the present case report analysis provides the empirical basis for expecting it.

---

## Supplementary Analysis: Narrow versus Broad Diagnostic Definitions

To assess whether the symptom profiles described above are artefacts of narrow diagnostic labelling, a supplementary analysis compared articles retrieved by narrow diagnostic terms (hEDS, POTS, MCAS) against those retrieved by broader umbrella terms that were queried independently from the PMC Open Access corpus.

### Adjacent Condition Corpus

Nine additional PMC queries for umbrella and adjacent conditions (dysautonomia, orthostatic intolerance, autonomic dysfunction, vasovagal syncope, JHS, HSD, histamine intolerance, hereditary alpha tryptasemia, idiopathic anaphylaxis) yielded 683 new PMCIDs not present in the original 717-article corpus. The largest contributions came from autonomic dysfunction (448 new articles) and dysautonomia (163 new articles). Full-text retrieval and extraction were completed for all 683 articles (100% success rate), bringing the total corpus to 1,400 articles (688 case reports).

These 683 articles were retrieved by independent queries and were not in the original corpus. This design avoids the circularity that would arise from applying broad-tier classification only to articles already retrieved by narrow-term queries.

### Results

The narrow versus broad comparison was only meaningful for the POTS tier, where 610 genuinely non-overlapping broad-only articles were available (284 case reports). For EDS, only 5 broad-only articles were found (JHS and HSD have near-zero standalone case report literatures in PMC Open Access, with 10 and 9 articles respectively); for MCAS, only 3 broad-only articles were found (histamine intolerance has only 2 case reports in PMC Open Access total). The near-absence of a JHS/HSD or histamine intolerance case report literature is itself a finding, and is consistent with these umbrella categories functioning primarily as clinical descriptors rather than as diagnostic entities that generate published case reports.

Figure 7 and Table 5 present the POTS narrow versus dysautonomia/OI broad-only comparison.

**Table 5. Symptom frequencies (%): POTS narrow versus dysautonomia/orthostatic intolerance broad-only case reports.** POTS narrow includes all case reports retrieved by POTS-specific search terms (n=119). Broad-only includes case reports retrieved by independent PMC queries for adjacent autonomic conditions (dysautonomia, orthostatic intolerance, autonomic dysfunction, vasovagal syncope) that do not mention POTS (n=284). The comparison is between POTS as a specific diagnostic entity and autonomic dysfunction as a broad clinical category. All 20 symptom categories are shown; dashes indicate differences <1pp.

| Symptom | Domain | POTS narrow (n=119) | Broad-only (n=284) | Difference (pp) |
|---------|--------|---------------------|--------------------|------------------|
| Tachycardia | CV/Auto | 95.8 | 34.9 | +60.9 |
| Fatigue | Systemic | 60.5 | 13.4 | +47.1 |
| Orthostatic intolerance | CV/Auto | 51.3 | 5.3 | +46.0 |
| Palpitations | CV/Auto | 50.4 | 7.7 | +42.7 |
| Headache/migraine | Neuro | 49.6 | 18.7 | +30.9 |
| Syncope/presyncope | CV/Auto | 53.8 | 23.9 | +29.8 |
| Joint hypermobility | MSK | 31.1 | 4.6 | +26.5 |
| Chronic pain | MSK | 34.5 | 17.3 | +17.2 |
| Skin hyperextensibility | MSK | 16.8 | 3.9 | +12.9 |
| Brain fog | Neuro | 15.1 | 4.6 | +10.5 |
| Subluxations/dislocations | MSK | 15.1 | 5.3 | +9.8 |
| GI symptoms | GI | 54.6 | 45.8 | +8.8 |
| Flushing | Immune | 11.8 | 4.2 | +7.5 |
| Easy bruising | Derm | 8.4 | 1.8 | +6.6 |
| Urticaria | Immune | 7.6 | 1.1 | +6.5 |
| Mitral valve prolapse | CV/Auto | 6.7 | 2.1 | +4.6 |
| Anaphylaxis | Immune | 6.7 | 3.2 | +3.6 |
| Neuropathy | Neuro | 47.1 | 48.2 | -1.2 |
| Medication sensitivity | Systemic | 6.7 | 6.3 | -- |
| Chiari malformation | Neuro | 0.0 | 0.0 | -- |

POTS case reports report higher frequencies across nearly every symptom category. Joint hypermobility (+26.5pp) and chronic pain (+17.2pp) are not canonical autonomic symptoms, yet they appear substantially more often in POTS case reports than in the broader dysautonomia literature. This is consistent with POTS case reports being written by clinicians aware of connective tissue and multi-system associations, reinforcing the ascertainment bias interpretation. Neuropathy is the notable exception: it is essentially equivalent in both groups (47.1% vs 48.2%), which is expected because neuropathy is a core feature of many dysautonomia aetiologies (diabetic, autoimmune, paraneoplastic) and is not specific to POTS.

The narrow versus broad comparison was only feasible for POTS, and this is a consequence of analysis design rather than a choice to focus on POTS specifically. The ideal analysis would compare narrow versus broad tiers for all three conditions: hEDS versus the broader hypermobility spectrum (JHS, HSD), POTS versus broader dysautonomia, and MCAS versus broader mast cell/histamine conditions. In practice, the EDS and MCAS broad tiers yielded too few non-overlapping articles for meaningful comparison (5 and 3 respectively), because JHS, HSD, and histamine intolerance barely exist as standalone case report diagnoses in the PMC Open Access literature. The POTS comparison succeeded because dysautonomia and autonomic dysfunction are broad clinical categories with substantial independent literatures (610 non-overlapping articles). This asymmetry is itself informative: it suggests that POTS, unlike hEDS or MCAS, sits within a broader ecosystem of autonomic conditions that have their own distinct publication traditions, while hEDS and MCAS have largely absorbed their umbrella categories in the published literature.

The dysautonomia broad-only group is heterogeneous by design, encompassing diabetic autonomic neuropathy, Guillain-Barre syndrome, familial dysautonomia, and other aetiologies that share autonomic dysfunction but have fundamentally different underlying pathophysiology from POTS. The comparison is therefore between POTS as a specific diagnostic entity and autonomic dysfunction as a broad clinical finding. The large symptom profile differences confirm that POTS carries a distinct multi-system phenotypic signature not captured by the broader category, supporting the use of narrow POTS diagnostic definitions rather than broader "dysautonomia" labels in the DICE Registry analysis.

---

## Limitations

**Publication bias.** Case reports over-represent unusual, severe, or multi-system presentations [[@Nissen2014]]. Patients with straightforward single-condition courses are less likely to be published. The symptom frequencies reported here are upper-bound estimates relative to clinical populations and cannot be used to infer population prevalence.

**PMC Open Access subset.** The analysis is restricted to the PMC Open Access corpus, which excludes journals without open access mandates, non-English language publications, and paywalled articles. This introduces geographic and institutional bias toward research environments with open access policies [[@Piwowar2018]].

**Rule-based extraction limitations.** The extraction pipeline uses regular expressions rather than NLP or LLM-based methods. Symptom F1 of 93.6% implies approximately 6% of symptom mentions are missed or incorrectly attributed. The higher F1 relative to LLM-based benchmarks (Reese et al., 2025; F1=0.78) partly reflects the coarser granularity of our 20 broad symptom categories compared to fine-grained HPO terms. Negation handling is incomplete: the pipeline may count symptoms mentioned in differential diagnosis or explicitly excluded contexts. LLM-based extraction approaches [[@Reese2025]; @CaseReportBench2025] may achieve higher recall on fine-grained phenotyping at the cost of increased false positives from salience errors [[@Brokering2025]].

**Small sample sizes.** Pre-2017 subgroup analyses are constrained by small denominators (hEDS pre-2017: n=31; POTS pre-2017: n=6; MCAS pre-2017: n=33; triad: n=18). Formal statistical testing was not performed on pre/post comparisons because the pre-2017 samples are underpowered for reliable inference. Reported percentage-point shifts should be treated as descriptive and hypothesis-generating.

**Confounding of diagnostic drift with genuine phenotype change.** The pre/post-2017 comparisons cannot distinguish genuine changes in disease presentation (e.g. stricter criteria selecting different patient populations) from changes in clinical documentation practice (ascertainment bias) or changes in the case report literature itself (e.g. shift toward multi-system reports driven by triad awareness). These are precisely the confounds that the DICE Registry analysis is designed to address through individual-level data and formal subtype modelling.

**Broad-tier limitations.** The EDS and MCAS broad tiers contain too few non-overlapping articles (5 and 3 respectively) for meaningful comparison. The POTS broad tier is aetiologically heterogeneous, including conditions unrelated to the triad, which dilutes rather than sharpens the comparison.

---

## Generalisability: A Reusable Pipeline for Rare Disease Comorbidity Research

The extraction and analysis pipeline developed for this work is designed to be condition-agnostic and reusable. The core workflow, comprising PMC Open Access query construction, full-text XML retrieval via E-utilities, rule-based symptom extraction with configurable regex patterns, article type classification, and tiered diagnostic reclassification, can be applied to any set of comorbid rare conditions where the research questions concern phenotypic overlap, diagnostic drift, and ascertainment bias. The pipeline requires only three inputs to adapt to a new condition triad (or dyad, or larger comorbidity cluster): a set of narrow diagnostic search terms, a set of broader umbrella/adjacent condition terms for non-circular comparisons, and a symptom extraction schema defining the phenotypic categories of interest.

The analysis framework is particularly suited to conditions where diagnostic criteria have evolved over time, where clinical awareness of comorbid associations is growing, and where the published literature is primarily case reports rather than large cohort studies, all of which are common features of rare disease research. The adjacent-condition query design addresses a methodological gap in the existing literature phenotyping toolkit: it enables non-circular comparison between narrow and broad diagnostic definitions without the tautological problem of applying broad-tier labels only to articles already retrieved by narrow search terms.

The complete pipeline code, including all extraction scripts, analysis notebooks, and figure generation, is available as an open-source repository (https://github.com/Amelia3141/triad_phenotype_mining) to enable replication and adaptation to other rare disease comorbidity clusters. Potential applications include the fibromyalgia-chronic fatigue syndrome-irritable bowel syndrome overlap, the autoimmune polyendocrinopathy cluster, and other conditions where multi-system phenotypic characterisation from the published literature could inform registry-based or genomic subtyping studies.

---

## Summary and Implications for DICE Registry Analysis

This preliminary literature phenotyping establishes several empirical findings that directly inform the registry-based SuStaIn analysis.

The published case report literature for the triad is growing rapidly (approximately 10-fold increase in annual publication rate from 2010 to 2025; Figure 2), but remains sparse for the triad itself (n=18 case reports discussing all three conditions). This underscores the need for registry-based analysis with substantially larger sample sizes, and supports the choice of the DICE Global Registry (n approximately 8,000) as the primary data source for Aim 1.

Diagnostic terminology has not converged following the 2017 reclassification (Figure 3). Multiple naming conventions coexist in the post-2017 literature, and older terms persist [[@Ritelli2024]]. This heterogeneity will be reflected in how patients in the DICE Registry were originally diagnosed and labelled, and motivates the inclusion of diagnostic ordering as a covariate in the regression models of Aim 2.

Post-2017 case reports show systematic increases in the documentation of cross-domain symptoms: autonomic features in hEDS reports, connective tissue features in MCAS reports, and immune features in POTS reports (Figure 5; Table 4). This pattern is consistent with ascertainment bias driven by growing triad awareness [[@Kohn2019]], and means that symptom profiles in the DICE Registry may be partially confounded with era of diagnosis. The diagnostic ordering analysis in Objective 1.1 and the Cramer's V threshold in Objective 1.3 are designed to detect and quantify this confound. The present analysis provides the empirical basis for expecting it.

Triad case reports present a distinctive multi-system phenotype (>50% prevalence across 10 of 20 symptom categories; Table 2, Figure 4) that differs qualitatively from any single-condition group, consistent with the hypothesised multi-system high-burden subtype. The small sample size (n=18) and publication bias mean this profile requires validation against the DICE cohort.

The narrow versus broad comparison confirms that POTS, as a specific diagnostic entity, carries a distinct phenotypic signature not captured by the broader dysautonomia literature (Table 5, Figure 7), supporting the use of narrow diagnostic definitions in the DICE Registry analysis.

Beyond informing the SuStaIn subtyping, these findings have broader implications for the machine learning framework proposed in the main thesis. The organ-specificity analysis (Table 2) directly informs feature engineering for the hierarchical graph attention network architecture: organ-specific symptoms (e.g. anaphylaxis, tachycardia, joint hypermobility) can serve as condition-level nodes in a multi-scale graph, while cross-system symptoms (e.g. fatigue, GI dysfunction, chronic pain) that are elevated in the triad but not specific to any single condition can serve as higher-order edges connecting condition subgraphs. The systematic ascertainment bias documented in Figures 5 and 6, where post-2017 case reports show inflated cross-domain symptom reporting, provides empirical grounding for the fairness-aware design component of the proposed framework: models trained on temporally heterogeneous data must account for era-dependent documentation patterns to avoid learning spurious associations between conditions. The causal discovery module, integrating Granger-causal attention mechanisms, is specifically designed to distinguish the genuine mechanistic relationships underlying the triad from the ascertainment-driven correlations that this literature analysis has quantified. Finally, the diagnostic odyssey data, with women waiting an average of 8.5 years longer for diagnosis [[@Halverson2023b]], motivates the contrastive learning approach to subgroup identification: if ML models can identify phenotypic signatures predictive of the triad at earlier disease stages, this could substantially reduce diagnostic delay, particularly for the demographic groups most affected by current diagnostic disparities.

---

## Figure Legends

**Figure 1. Corpus assembly and cleaning flow diagram.** The original PMC Open Access queries retrieved 717 unique articles across four condition-specific searches. Article type classification identified 376 case reports (52.4%). Post-hoc reclassification excluded vascular EDS (n=147), classical EDS (n=10), other EDS subtypes (n=3), and EDS-excluded articles (n=80) from hEDS analyses, and flagged mastocytosis-only articles within the MCAS query. The adjacent condition queries, executed independently, contributed 683 new articles not present in the original corpus, yielding a total expanded corpus of 1,400 articles (688 case reports). *File: fig1_corpus_flow.png*

**Figure 2. Temporal publication trends for EDS-POTS-MCAS case reports, 2004-2026.** Annual case report publication counts from the original PMC Open Access corpus, stratified by primary condition. Grey bars indicate total case report volume; coloured lines show condition-specific counts (hEDS/HSD, magenta; POTS, blue; MCAS, purple). The vertical dashed line marks the 2017 International Classification of EDS [[@Malfait2017]]. All three conditions show accelerating publication after 2017, with the steepest growth in hEDS case reports. Note that 2026 reflects partial-year data (January to April). *File: fig2_temporal_trends.png*

**Figure 3. Diagnostic terminology drift in hEDS case reports across the 2017 criteria boundary.** Proportion of hEDS case reports using each terminology variant, stratified by publication era (pre-2017, n=31, light blue; post-2017, n=163, dark blue). "EDS type III" declined from 42% to 23%, whilst "hEDS" emerged de novo (0% to 18%). "JHS" increased from 26% to 33% despite the 2017 reclassification formally separating JHS from hEDS, indicating persistent terminological ambiguity. *File: fig3_terminology_drift.png*

**Figure 4. Symptom frequency heatmap across condition-specific case report subgroups.** Heatmap showing the frequency (%) of 20 symptoms across four mutually exclusive condition groups from the original corpus. Cell values are rounded percentages (e.g. a cell showing "7" indicates 6.9%); raw counts can be derived from the group denominators in Table 2. The triad group (n=18) shows elevated frequencies across all domains, with 10 of 20 symptoms exceeding 50%, distinguishing it from any single-condition profile. Colour scale: yellow (0%) to dark red (100%). MSK = musculoskeletal; CV/Auto = cardiovascular/autonomic; Derm = dermatological; Neuro = neurological; GI = gastrointestinal. *File: fig4_symptom_heatmap.png*

**Figure 5. Pre-2017 versus post-2017 symptom frequency shifts in (a) hEDS and (b) MCAS case reports.** Diverging bar charts showing the change in symptom frequency (percentage points) between pre-2017 and post-2017 case reports. Blue bars indicate increased frequency post-2017; red bars indicate decreased frequency. Values >8pp are annotated. In hEDS (a), the largest increases are in autonomic symptoms (fatigue, tachycardia, syncope), consistent with growing triad awareness. In MCAS (b), joint hypermobility and orthostatic intolerance appear de novo in post-2017 reports (from 0.0%), representing the clearest evidence of cross-condition ascertainment bias. *File: fig5_diagnostic_drift.png*

**Figure 6. Condition co-occurrence in original corpus case reports (n=376).** Bar chart showing the number of case reports in each co-occurrence category. The majority of case reports discuss a single condition (EDS only: 160; MCAS only: 128; POTS only: 32). Cross-condition co-discussion is sparse, with only 18 triad case reports. The low overlap constrains triad-level analysis but enables condition-specific comparisons with reasonable power. *File: fig6_co_occurrence.png*

**Figure 7. Symptom frequency comparison: POTS narrow versus dysautonomia/orthostatic intolerance broad-only case reports.** Paired horizontal bar chart comparing symptom frequencies between POTS case reports retrieved by narrow diagnostic terms (n=119, blue) and case reports retrieved by independent queries for broader autonomic conditions that do not mention POTS (n=284, orange). POTS case reports show substantially higher frequencies across nearly all symptom categories. Joint hypermobility (+26.5pp) and chronic pain (+17.2pp) are not canonical autonomic symptoms, suggesting that POTS as a diagnostic entity carries a multi-system phenotypic signature influenced by clinical awareness of connective tissue associations. *File: fig7_narrow_vs_broad.png*

---

## References

Afrin, L.B., Self, S., Menk, J., Lazarchick, J. (2017). Characterization of mast cell activation syndrome. *American Journal of the Medical Sciences*, 353(3), 207-215.

Akin, C., Valent, P., Metcalfe, D.D. (2010). Mast cell activation syndrome: proposed diagnostic criteria. *Journal of Allergy and Clinical Immunology*, 126(6), 1099-1104.

Beighton, P., De Paepe, A., Steinmann, B., Tsipouras, P., Wenstrup, R.J. (1998). Ehlers-Danlos syndromes: revised nosology, Villefranche, 1997. *American Journal of Medical Genetics*, 77(1), 31-37.

Brokering, J., et al. (2025). Can LLMs reliably extract human disease genes from full-text scientific literature? *bioRxiv*, 2025.07.27.667022.

Byers, P.H. (2017). Vascular Ehlers-Danlos syndrome. In: *GeneReviews* [Internet]. University of Washington, Seattle.

CaseReportBench (2025). CaseReportBench: An LLM benchmark dataset for dense information extraction in clinical case reports. *arXiv*, 2505.17265.

Castori, M. (2011). Ehlers-Danlos syndrome, hypermobility type: an underdiagnosed hereditary connective tissue disorder with mucocutaneous, articular, and systemic manifestations. *ISRN Dermatology*, 2012, 751768.

Castori, M., Tinkle, B., Levy, H., Grahame, R., Malfait, F., Hakim, A. (2017). A framework for the classification of joint hypermobility and related conditions. *American Journal of Medical Genetics Part C*, 175(1), 148-157.

Demmler, J.C., Atkinson, M.D., Mayberry, E.J., et al. (2019). Diagnosed prevalence of Ehlers-Danlos syndrome and hypermobility spectrum disorder in Wales, UK: a national electronic cohort study and case-control comparison. *BMJ Open*, 9(11), e031365.

Fedorowski, A., Sutton, R. (2023). Autonomic dysfunction and postural orthostatic tachycardia syndrome in post-acute COVID-19 syndrome. *Nature Reviews Cardiology*, 20(5), 281-282.

Halverson, C.M.E., Cao, S., Engel, E.R., Engstrom, S., Francomano, C.A. (2023). The diagnostic odyssey of patients with Ehlers-Danlos syndrome. *American Journal of Medical Genetics Part A*, 191(2), 484-492.

Halverson, C.M.E., Cao, S., Perkins, S.M., Francomano, C.A. (2023b). Comorbidity, misdiagnoses, and the diagnostic odyssey in patients with hypermobile Ehlers-Danlos syndrome. *Genetics in Medicine Open*, 1(1), 100812.

Kohn, A., Chang, C. (2019). The relationship between hypermobile Ehlers-Danlos syndrome (hEDS), postural orthostatic tachycardia syndrome (POTS), and mast cell activation syndrome (MCAS). *Clinical Reviews in Allergy & Immunology*, 58(3), 273-297.

Malfait, F., Francomano, C., Byers, P., et al. (2017). The 2017 international classification of the Ehlers-Danlos syndromes. *American Journal of Medical Genetics Part C*, 175(1), 8-26.

Molderings, G.J., Brettner, S., Homann, J., Afrin, L.B. (2011). Mast cell activation disease: a concise practical guide for diagnostic workup and therapeutic options. *Journal of Hematology & Oncology*, 4, 10.

NCBI (2024). PubMed help: publication types. *National Center for Biotechnology Information*. Available at: https://www.ncbi.nlm.nih.gov/books/NBK3827/

Nissen, T., Wynn, R. (2014). The clinical case report: a review of its merits and limitations. *BMC Research Notes*, 7, 264.

Piwowar, H., Priem, J., Lariviere, V., et al. (2018). The state of OA: a large-scale analysis of the prevalence and impact of Open Access articles. *PeerJ*, 6, e4375.

Quigley, E.M.M., Noble, O., Ansari, U. (2024). The suggested relationships between common GI symptoms and joint hypermobility, POTS, and MCAS. *Gastroenterology & Hepatology*, 20(8), 479-489.

Reese, J.T., Chimirri, M., Gargano, M., et al. (2025). RAG-HPO: improving automated deep phenotyping through retrieval-augmented generation with large language models. *Genome Medicine*, 17, 4.

Ritelli, M., Venturini, M., Cinquina, V., et al. (2024). Looking back and beyond the 2017 diagnostic criteria for hypermobile Ehlers-Danlos syndrome. *American Journal of Medical Genetics Part A*, 194(1), e63410.

Sayers, E.W., Bolton, E.E., Brister, J.R., et al. (2022). Database resources of the National Center for Biotechnology Information. *Nucleic Acids Research*, 50(D1), D13-D25.

Shirvani, P., Shirvani, A., Holick, M.F. (2024). Decoding the genetic basis of mast cell hypersensitivity and infection risk in hypermobile Ehlers-Danlos syndrome. *Current Issues in Molecular Biology*, 46(10), 11613-11629.

Tinkle, B., Castori, M., Berglund, B., et al. (2017). Hypermobile Ehlers-Danlos syndrome (a.k.a. Ehlers-Danlos syndrome type III and Ehlers-Danlos syndrome hypermobility type): clinical description and natural history. *American Journal of Medical Genetics Part C*, 175(1), 48-69.

Valent, P., Akin, C., Arock, M., et al. (2012). Definitions, criteria and global classification of mast cell disorders with special reference to mast cell activation syndromes: a consensus proposal. *International Archives of Allergy and Immunology*, 157(3), 215-225.

Wang, K., Bhatt, D.L., Engstrom, S., et al. (2024). Characterisation of comorbidities in the Ehlers-Danlos syndromes: a report from the DICE Global Registry. *Genetics in Medicine*, 26(3), 101059.

Wang, Y.-T., Jahani, S., Morel-Swols, D., Kapely, A., Rosen, A., Forghani, I. (2024). Patient experiences of receiving a diagnosis of hypermobile Ehlers-Danlos syndrome. *American Journal of Medical Genetics Part A*, 194(8), e63613.

Sheldon, R.S., Grubb, B.P., Olshansky, B., et al. (2015). 2015 Heart Rhythm Society expert consensus statement on the diagnosis and treatment of postural tachycardia syndrome, inappropriate sinus tachycardia, and vasovagal syncope. *Heart Rhythm*, 12(6), e41-e63.

Valent, P., Akin, C., Bonadonna, P., et al. (2020). Proposed diagnostic algorithm for patients with suspected mast cell activation syndrome. *Journal of Allergy and Clinical Immunology: In Practice*, 7(4), 1252-1261.

Vernino, S., Bourne, K.M., Stiles, L.E., et al. (2021). Postural orthostatic tachycardia syndrome (POTS): state of the science and clinical care from a 2019 National Institutes of Health Expert Consensus Meeting, Part 1. *Autonomic Neuroscience*, 235, 102828.

Weiler, C.R. (2019). Mast cell activation syndrome: tools for diagnosis and differential diagnosis. *Journal of Allergy and Clinical Immunology: In Practice*, 8(2), 498-506.
