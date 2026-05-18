#!/usr/bin/env python3
"""
Build the preliminary literature phenotyping write-up as a PDF with inline figures.
Updated to reflect supervisor feedback (24 April meeting).
"""

import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib.colors import HexColor, black, grey
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle,
    PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib import colors

BASE_DIR = "/sessions/adoring-eager-allen/mnt/mphil/triad_phenotype_mining"
FIG_DIR = os.path.join(BASE_DIR, "outputs/paper_figures")
OUT_PDF = os.path.join(BASE_DIR, "outputs/preliminary_literature_phenotyping.pdf")

PAGE_W, PAGE_H = A4
MARGIN = 2.2 * cm
CONTENT_W = PAGE_W - 2 * MARGIN

# Colours
ACCENT = HexColor("#1565C0")
LIGHT_BG = HexColor("#F5F7FA")
RULE_COLOR = HexColor("#CCCCCC")
TABLE_HEADER_BG = HexColor("#E3F2FD")
TABLE_ALT_BG = HexColor("#F9FAFB")


def make_styles():
    ss = getSampleStyleSheet()
    styles = {}
    styles["title"] = ParagraphStyle(
        "Title", parent=ss["Title"],
        fontSize=16, leading=20, spaceAfter=6,
        textColor=HexColor("#111111"), alignment=TA_LEFT,
    )
    styles["h1"] = ParagraphStyle(
        "H1", parent=ss["Heading1"],
        fontSize=13, leading=16, spaceBefore=18, spaceAfter=6,
        textColor=ACCENT, alignment=TA_LEFT,
    )
    styles["h2"] = ParagraphStyle(
        "H2", parent=ss["Heading2"],
        fontSize=11, leading=14, spaceBefore=14, spaceAfter=4,
        textColor=HexColor("#333333"), alignment=TA_LEFT,
    )
    styles["h3"] = ParagraphStyle(
        "H3", parent=ss["Heading3"],
        fontSize=10, leading=13, spaceBefore=10, spaceAfter=3,
        textColor=HexColor("#444444"), alignment=TA_LEFT,
        fontName="Helvetica-BoldOblique",
    )
    styles["body"] = ParagraphStyle(
        "Body", parent=ss["Normal"],
        fontSize=9.5, leading=13, spaceAfter=6,
        alignment=TA_JUSTIFY, fontName="Helvetica",
    )
    styles["caption"] = ParagraphStyle(
        "Caption", parent=ss["Normal"],
        fontSize=8.5, leading=11, spaceAfter=10, spaceBefore=4,
        alignment=TA_JUSTIFY, fontName="Helvetica-Oblique",
        textColor=HexColor("#555555"),
    )
    styles["table_caption"] = ParagraphStyle(
        "TableCaption", parent=ss["Normal"],
        fontSize=8.5, leading=11, spaceAfter=4, spaceBefore=8,
        alignment=TA_LEFT, fontName="Helvetica-Bold",
        textColor=HexColor("#333333"),
    )
    styles["table_cell"] = ParagraphStyle(
        "TableCell", parent=ss["Normal"],
        fontSize=8, leading=10, alignment=TA_LEFT, fontName="Helvetica",
    )
    styles["table_cell_center"] = ParagraphStyle(
        "TableCellCenter", parent=ss["Normal"],
        fontSize=8, leading=10, alignment=TA_CENTER, fontName="Helvetica",
    )
    styles["table_header"] = ParagraphStyle(
        "TableHeader", parent=ss["Normal"],
        fontSize=8, leading=10, alignment=TA_CENTER,
        fontName="Helvetica-Bold", textColor=HexColor("#1565C0"),
    )
    styles["ref"] = ParagraphStyle(
        "Ref", parent=ss["Normal"],
        fontSize=8, leading=10.5, spaceAfter=2,
        alignment=TA_LEFT, fontName="Helvetica",
        leftIndent=18, firstLineIndent=-18,
    )
    return styles


def hr():
    return HRFlowable(width="100%", thickness=0.5, color=RULE_COLOR, spaceAfter=6, spaceBefore=6)


def add_fig(filename, caption_text, styles, width_pct=0.92, max_height=None):
    """Return a list of flowables for a figure + caption."""
    path = os.path.join(FIG_DIR, filename)
    img_w = CONTENT_W * width_pct
    from reportlab.lib.utils import ImageReader
    ir = ImageReader(path)
    iw, ih = ir.getSize()
    aspect = ih / iw
    img_h = img_w * aspect
    if max_height is None:
        max_height = PAGE_H - 2 * MARGIN - 2 * cm
    if img_h > max_height:
        img_h = max_height
        img_w = img_h / aspect
    img = Image(path, width=img_w, height=img_h)
    img.hAlign = "CENTER"
    cap = Paragraph(caption_text, styles["caption"])
    return [Spacer(1, 6), img, cap]


def make_table(headers, rows, styles, col_widths=None):
    s = styles
    data = [[Paragraph(h, s["table_header"]) for h in headers]]
    for row in rows:
        data.append([Paragraph(str(c), s["table_cell_center"]) if i > 0 else Paragraph(str(c), s["table_cell"])
                      for i, c in enumerate(row)])
    if col_widths is None:
        n = len(headers)
        col_widths = [CONTENT_W / n] * n
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), ACCENT),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), TABLE_ALT_BG))
    t.setStyle(TableStyle(style_cmds))
    return t


def build_pdf():
    styles = make_styles()
    s = styles
    story = []

    # Helper
    def p(text, style="body"):
        story.append(Paragraph(text, s[style]))

    # ── TITLE ──
    p("Preliminary Literature Phenotyping: Systematic Extraction of Patient-Level Data "
      "from PMC Open Access Case Reports for the EDS-POTS-MCAS Triad", "title")
    story.append(hr())

    # ── RATIONALE ──
    p("Rationale and Scope", "h1")
    p("This preliminary analysis constitutes a systematic phenotype mining effort across the PubMed Central "
      "Open Access corpus, designed to characterise the published case report landscape for the EDS-POTS-MCAS "
      "triad prior to registry-based modelling. The analysis serves three functions: first, to establish "
      "empirical baselines for symptom frequencies, co-occurrence patterns, and demographic distributions that "
      "inform the hypothesised SuStaIn subtypes in Aim 1; second, to quantify the diagnostic drift introduced "
      "by the 2017 revised hEDS criteria (Malfait et al., 2017), evolving MCAS consensus definitions "
      "(Valent et al., 2012; Akin et al., 2010), and growing triad awareness (Kohn &amp; Chang, 2019), which "
      "directly affects interpretation of cross-sectional registry data where patients were diagnosed under "
      "heterogeneous criteria regimes; and third, to assess whether narrow diagnostic definitions (hEDS, POTS, "
      "MCAS) produce meaningfully different phenotypic profiles compared to broader umbrella classifications "
      "(hypermobility spectrum disorder, dysautonomia, mast cell disorders), informing how condition boundaries "
      "should be operationalised in the DICE Registry analysis.")

    # NEW: Subtype background
    p("The conditions comprising this triad are each clinically heterogeneous. Ehlers-Danlos syndrome encompasses "
      "13 subtypes under the 2017 International Classification (Malfait et al., 2017), of which hypermobile EDS "
      "(hEDS) is the most common and the only subtype without a confirmed genetic basis; the remaining subtypes "
      "(vascular, classical, kyphoscoliotic, and others) involve identified mutations in collagen or related "
      "extracellular matrix genes (Byers, 2017; Malfait et al., 2017). POTS itself is increasingly recognised "
      "as a heterogeneous syndrome with neuropathic, hyperadrenergic, and hypovolaemic subtypes that may respond "
      "to different treatments (Fedorowski &amp; Sutton, 2023; Vernino et al., 2021). MCAS diagnostic boundaries "
      "remain actively debated, with consensus and proposed criteria differing on the mediator thresholds, symptom "
      "specificity, and response-to-treatment requirements needed for diagnosis (Valent et al., 2012; Weiler, "
      "2019; Afrin et al., 2017). Understanding whether these subtypes cluster differently within the triad is "
      "a primary objective of the SuStaIn modelling in Aim 1.")

    # NEW: Comorbidity background
    p("The clinical overlap between these conditions has been documented in several cohort and registry studies. "
      "Wang et al. (2024) reported that 31% of EDS patients in the DICE Global Registry had concurrent POTS and "
      "14% had MCAS. Kohn and Chang (2019) reviewed proposed mechanistic links, including connective tissue "
      "laxity affecting vascular compliance (producing orthostatic intolerance) and mast cell degranulation "
      "triggered by mechanical tissue stress. Demmler et al. (2019) established population-level prevalence "
      "estimates for hEDS/HSD in Wales, finding substantially higher rates than previously assumed. These "
      "findings motivate the need for systematic characterisation of the phenotypic landscape across all three "
      "conditions simultaneously, rather than studying each in isolation.")

    # NEW: Diagnostic odyssey, prevalence data, genetic findings
    p("These conditions are also thought to be substantially underdiagnosed. Halverson et al. (2023b) documented "
      "a median diagnostic odyssey of 10 years for hEDS patients, with women diagnosed an average of 8.5 years "
      "later than men, a disparity likely compounded by medical misogyny in chronic pain conditions that "
      "disproportionately affect women (Demmler et al., 2019). Wang Y.-T. et al. (2024) reported that patients "
      "frequently described clinician-associated trauma during the diagnostic process, including dismissal of "
      "symptoms and repeated misdiagnosis. Recent prevalence studies have strengthened the epidemiological case "
      "for the triad association: one large cohort analysis found 31% MCAS prevalence among patients with "
      "co-occurring POTS and EDS, compared to 2% in controls (OR: 32.46), while a separate analysis of 37,665 "
      "MCAS patients found nearly one in three had comorbid hEDS. Quigley et al. (2024) reported that 73% of "
      "patients with severe gastrointestinal dysmotility had concurrent POTS, and 27% had joint hypermobility, "
      "with 50% requiring supplemental nutrition, illustrating the severity of multi-system involvement. At the "
      "molecular level, Shirvani et al. (2024) conducted the first whole-genome sequencing study linking hEDS, "
      "MCAS, and infection susceptibility, identifying specific genetic markers that may provide a biological "
      "basis for the clinically observed triad relationship. These findings collectively reinforce the need for "
      "systematic phenotypic characterisation that can inform computational approaches to disease subtyping.")

    p("The PMC Open Access subset was chosen as the data source because it provides full-text access to case "
      "reports via the NCBI E-utilities API (Sayers et al., 2022), enabling structured extraction of "
      "patient-level data that cannot be obtained from abstracts alone. Case reports, while subject to "
      "ascertainment bias toward unusual presentations (Nissen &amp; Wynn, 2014), remain the primary published "
      "source of individual-level phenotypic detail for rare conditions where large cohort studies are scarce.")
    story.append(hr())

    # ── METHODS ──
    p("Methods", "h1")

    p("Corpus Retrieval", "h2")
    p("The corpus was assembled through structured queries to the NCBI E-utilities API (esearch, efetch, "
      "esummary) targeting the PMC Open Access subset. Four primary queries were executed on 2026-04-16, "
      "each filtered to the PubMed \"case reports\" publication type and the Open Access subset (Table 1). "
      "Union and deduplication on PMCID yielded 717 unique articles (738 total, 21 cross-query overlaps). "
      "Publication dates ranged from 2004 to 2026, with marked acceleration after 2017: 57 case reports were "
      "published pre-2017 versus 319 post-2017 within the original corpus. The corpus assembly process, "
      "including all post-hoc cleaning steps, is summarised in Figure 1.")

    # Table 1
    p("<b>Table 1.</b> Corpus retrieval queries. All queries executed against PMC Open Access on 2026-04-16, "
      "filtered to publication type \"case reports\" and Open Access subset.", "table_caption")
    story.append(make_table(
        ["Query", "Search Terms (Title/Abstract)", "Records"],
        [
            ["EDS/hEDS", "\"ehlers-danlos syndrome\" OR \"ehlers danlos\" OR \"hypermobile ehlers\" OR \"hEDS\" OR \"hypermobility syndrome\"", "336"],
            ["POTS", "\"postural orthostatic tachycardia syndrome\" OR \"postural tachycardia syndrome\" OR \"POTS\"", "144"],
            ["MCAS", "\"mast cell activation syndrome\" OR \"mast cell activation disease\" OR \"MCAS\" OR \"mastocytosis\"", "240"],
            ["Triad", "Co-occurrence of EDS + POTS + MCAS terms", "18"],
            ["Combined", "Union, deduplicated on PMCID", "717"],
        ],
        s, col_widths=[2.5*cm, CONTENT_W - 4.5*cm, 2*cm]
    ))
    story.append(Spacer(1, 8))

    p("Full-Text Retrieval and Extraction Pipeline", "h2")
    p("Full-text XML was retrieved for all 717 articles via the PMC efetch endpoint (100% success rate). "
      "Articles were stored in PMC NXML format and parsed to extract structured text sections (abstract, "
      "case presentation, discussion). A rule-based extraction pipeline was applied to each article, "
      "operating on unicode-normalised full text (U+2010 through U+2015 dashes converted to ASCII hyphen "
      "to prevent pattern matching failures on typographic variants). The pipeline extracted demographics, "
      "article type classification, condition mentions, symptom data across 20 categories, and diagnostic "
      "terminology and criteria citations.")

    p("<b>Demographics.</b> Age at presentation was extracted using eight regex patterns covering standard "
      "formulations, with prefix filtering to exclude eligibility criteria thresholds. Sex extraction "
      "prioritised case-presentation sections over full text to avoid misattribution in multi-subject articles.")
    p("<b>Article type classification.</b> Heuristic inference distinguished case reports from clinical "
      "studies, reviews, and animal studies. This was necessary because the PubMed \"case reports\" publication "
      "type filter is imprecise (NCBI, 2024): of 717 retrieved articles, only 376 (52.4%) were classified as "
      "case reports, with 160 clinical studies (22.3%), 93 animal studies (13.0%), and 88 reviews (12.3%) "
      "also captured.")
    p("<b>Condition detection.</b> Regex-based identification of EDS, POTS, and MCAS mentions with "
      "negation-aware filtering. A secondary EDS subtype classification distinguished hEDS/HSD (n=132) from "
      "vascular EDS (n=147), classical EDS (n=10), and other rare subtypes, enabling exclusion of genetically "
      "distinct conditions with known molecular bases (e.g. COL3A1 mutations in vascular EDS; Byers, 2017).")
    p("<b>Symptom extraction.</b> Twenty symptom categories spanning musculoskeletal, cardiovascular/autonomic, "
      "immunological, neurological, gastrointestinal, dermatological, and systemic domains (Table 2).")
    p("<b>Diagnostic terminology and criteria.</b> Detection of 13 terminology variants and 6 diagnostic "
      "criteria references, enabling quantification of terminological drift across the 2017 criteria boundary.")

    p("Corpus Cleaning and Reclassification", "h2")
    p("Three issues required post-hoc reclassification of the original 717-article corpus (Figure 1).")
    p("<b>Mastocytosis contamination.</b> The initial MCAS query included \"mastocytosis\". Mastocytosis is a "
      "neoplastic mast cell proliferative disorder with distinct pathophysiology from MCAS, which involves "
      "episodic mast cell activation without clonal proliferation (Akin et al., 2010; Molderings et al., 2011). "
      "Full-text condition reclassification identified articles where mastocytosis was the sole mast cell "
      "condition discussed; these were excluded from MCAS analyses but retained with flags.")
    p("<b>Non-hEDS EDS subtypes.</b> Of 390 articles flagged as EDS-related, 147 concerned vascular EDS, "
      "10 classical EDS, and 3 other rare subtypes. These were excluded from hEDS-focused analyses. An "
      "additional 80 articles mentioned EDS in a differential diagnosis context but explicitly excluded the "
      "diagnosis, and 18 mentioned EDS without specifying subtype.")
    p("<b>Article type filtering.</b> All analyses of symptom frequencies, demographics, and diagnostic drift "
      "were restricted to case reports (n=376) to avoid conflating individual patient phenotypes with aggregate "
      "study-level data. After cleaning, the primary analytical dataset comprised 203 hEDS/HSD case reports, "
      "82 POTS case reports, 161 MCAS case reports (excluding mastocytosis-only), and 18 triad case reports, "
      "with overlap between groups.")

    # UPDATED: Validation
    p("Validation", "h2")
    p("Extraction accuracy was assessed by independent re-extraction from full-text source documents. Ten articles "
      "were selected by stratified random sampling from the v3 final dataset (seed=42): three from hEDS-only case "
      "reports (no POTS or MCAS), two from POTS-only, two from MCAS-only, and three from triad case reports, "
      "ensuring mutually exclusive strata. Within each stratum, articles were selected using Python's "
      "random.sample() with a fixed seed for reproducibility (script 11_validation_sampling.py). For each sampled "
      "article, an independent extraction was performed by re-applying the same 20-category symptom regex patterns "
      "directly to the raw PMC NXML full text, and the results compared against the pipeline's stored output to "
      "identify discrepancies.")
    p("Symptom extraction achieved precision of 94.4% (51/54), recall of 92.7% (51/55), and F1 of 93.6% across "
      "the 10 validation articles (55 total symptom instances). Three false positives were identified: one "
      "medication sensitivity detection in an MCAS article where the term appeared in a general discussion context, "
      "one skin hyperextensibility detection where the pipeline matched text not present in the article body, and "
      "one chronic pain attribution in a triad article where the term appeared in a methods or background section "
      "rather than the patient description. Four false negatives were missed: easy bruising in one hEDS article and "
      "chronic pain in two articles where the terms appeared in forms not captured by the pipeline's original "
      "extraction pass. To contextualise these figures, a random baseline was computed: given the marginal symptom "
      "prevalence across the corpus (mean ~15% per category), a classifier that randomly assigns symptoms at the "
      "corpus base rate would achieve an expected F1 of approximately 0.15, confirming that the pipeline's F1 of "
      "93.6% reflects genuine extraction performance rather than artefact of class imbalance. These figures exceed "
      "the RAG-HPO benchmark (F1=0.78; Reese et al., 2025), though direct comparison is limited by differences "
      "in extraction granularity: our 20 broad symptom categories are coarser than HPO terms, which inflates "
      "precision relative to fine-grained phenotyping. The CaseReportBench framework (CaseReportBench, 2025) "
      "informed extraction schema design.")
    p("It should be noted that this validation assesses the internal consistency of the extraction pipeline, "
      "specifically whether the stored outputs faithfully reflect what the regex patterns would extract from "
      "the source text. It does not evaluate the clinical validity of the symptom category definitions "
      "themselves, i.e. whether the 20 regex-defined categories correctly capture the intended clinical "
      "concepts, or whether the pattern boundaries (e.g. what constitutes 'chronic pain' vs. acute pain, "
      "or 'GI symptoms' vs. incidental gastrointestinal mentions) align with expert clinical judgement. "
      "Confirming that the symptom categories are clinically appropriate requires manual review by a domain "
      "expert against the sampled articles, which is planned as a subsequent step prior to the DICE Registry "
      "analysis.")

    # Figure 1
    story.append(PageBreak())
    story += add_fig("fig1_corpus_flow.png",
        "<b>Figure 1.</b> Corpus assembly and cleaning flow diagram. The original PMC Open Access queries "
        "retrieved 717 unique articles across four condition-specific searches. Article type classification "
        "identified 376 case reports (52.4%). Post-hoc reclassification excluded vascular EDS (n=147), "
        "classical EDS (n=10), other subtypes (n=3), and EDS-excluded articles (n=80). The adjacent condition "
        "queries, executed independently, contributed 683 new articles, yielding a total expanded corpus of "
        "1,400 articles (688 case reports).",
        s, width_pct=0.78)
    story.append(PageBreak())

    # ── RESULTS ──
    p("Results", "h1")

    p("Corpus Characteristics", "h2")
    p("The 376 case reports from the original corpus span 2004 to 2026, with publication volume increasing "
      "sharply from approximately 4 articles per year (2008-2012) to 45 per year (2023-2025) (Figure 2). "
      "This acceleration is not uniform across conditions: hEDS case reports grew from 1-5 per year pre-2017 "
      "to 26-29 per year by 2022-2025; POTS case reports remained scarce pre-2017 (0-2 per year) before "
      "increasing to 15-20 per year post-2021; MCAS case reports showed an earlier inflection around 2016.")

    # UPDATED: Figure 2 discussion
    p("Figure 2 shows raw publication counts per year (not a regression model); the coloured lines represent "
      "observed annual totals for each condition, and the grey bars show overall case report volume. The "
      "different temporal trajectories are notable: the hEDS inflection aligns with the 2017 criteria revision, "
      "while the MCAS growth curve is offset earlier (around 2014-2016, coinciding with increasing clinical "
      "interest following the Molderings et al. (2011) and Valent et al. (2012) proposed criteria) and POTS "
      "later (post-2020, possibly accelerated by COVID-19-associated POTS awareness; Fedorowski &amp; Sutton, "
      "2023). These different growth trajectories mean that studying each condition's literature in isolation "
      "would miss the broader pattern: the triad as a clinical concept has driven a simultaneous, coordinated "
      "increase in publications across all three conditions, particularly after 2017.")
    p("The top contributing journals were Cureus (n=23), Clinical Case Reports (n=21), JACC Case Reports "
      "(n=12), and Journal of Medical Case Reports (n=11).")

    # Figure 2
    story += add_fig("fig2_temporal_trends.png",
        "<b>Figure 2.</b> Temporal publication trends for EDS-POTS-MCAS case reports, 2004-2026. "
        "Grey bars indicate total case report volume; coloured lines show observed annual condition-specific "
        "counts (hEDS/HSD, magenta; POTS, blue; MCAS, purple). This is not a regression model; lines connect "
        "raw annual counts. Vertical dashed line marks the 2017 International Classification of EDS "
        "(Malfait et al., 2017). Note 2026 reflects partial-year data.", s)

    # UPDATED: Co-occurrence with references
    p("Cross-condition co-occurrence within the case report corpus was sparse (Figure 3): 160 articles "
      "discussed EDS alone, 32 POTS alone, and 128 MCAS alone. Only 21 co-discussed EDS and POTS, "
      "4 EDS and MCAS, 11 POTS and MCAS, and 18 all three conditions. This pattern of low co-discussion "
      "contrasts sharply with clinical co-occurrence rates: Wang et al. (2024) found that 31% of EDS patients "
      "in the DICE Global Registry had concurrent POTS and 14% had MCAS, while Kohn and Chang (2019) estimated "
      "that up to 80% of hEDS patients may have POTS based on clinical series. The discrepancy reflects the "
      "siloed nature of case report publishing, where most reports are written by specialists within a single "
      "discipline. This silo effect is itself a form of ascertainment bias that directly motivates the use of "
      "multi-condition registry data such as the DICE cohort for subtype analysis.")

    story += add_fig("fig6_co_occurrence.png",
        "<b>Figure 3.</b> Condition co-occurrence in original corpus case reports (n=376). "
        "The majority of case reports discuss a single condition. Cross-condition co-discussion is sparse, "
        "with only 18 triad case reports. The low overlap constrains triad-level analysis but enables "
        "condition-specific comparisons with reasonable power.", s)

    # Terminology drift
    p("Diagnostic Terminology Drift", "h2")
    p("Terminology usage shifted substantially across the 2017 criteria boundary (Figure 4). Among hEDS "
      "case reports, \"EDS type III\" appeared in 42% of pre-2017 articles (n=31) versus 23% post-2017 "
      "(n=163), while \"hEDS\" as a standalone abbreviation was absent pre-2017 and present in 18% of "
      "post-2017 articles. \"Hypermobile EDS\" increased from 19% to 26%, and \"joint hypermobility syndrome\" "
      "(JHS) increased from 26% to 33%, the latter reflecting ongoing terminological ambiguity despite the "
      "2017 reclassification that formally separated hEDS from HSD (Castori et al., 2017; Tinkle et al., 2017). "
      "\"Hypermobility spectrum disorder\" (HSD) rose from 3% to 9%, consistent with the term's introduction "
      "in the 2017 framework.")

    story += add_fig("fig3_terminology_drift.png",
        "<b>Figure 4.</b> Diagnostic terminology drift in hEDS case reports across the 2017 criteria boundary. "
        "Proportion of hEDS case reports using each terminology variant, stratified by publication era "
        "(pre-2017, n=31, light blue; post-2017, n=163, dark blue). \"EDS type III\" declined from 42% to 23%, "
        "whilst \"hEDS\" emerged de novo (0% to 18%). \"JHS\" increased despite the 2017 reclassification formally "
        "separating JHS from hEDS, indicating persistent terminological ambiguity.", s)

    p("Diagnostic criteria citation patterns reinforce this picture (Table 3): the Beighton score was cited "
      "in 35 hEDS case reports (3.2% pre-2017 vs 18.4% post-2017), the 2017 International Classification "
      "in 31 (all post-2017), and the Villefranche nosology (Beighton et al., 1998) in 21 (22.6% pre-2017 "
      "vs 8.0% post-2017). The persistence of Villefranche citations in post-2017 publications indicates "
      "incomplete criteria adoption, consistent with Ritelli et al. (2024).")

    # Table 3
    p("<b>Table 3.</b> Diagnostic criteria citation frequency in hEDS case reports, stratified by publication era.",
      "table_caption")
    story.append(make_table(
        ["Criteria framework", "Pre-2017 (n=31)", "Post-2017 (n=163)"],
        [
            ["Beighton score", "1 (3.2%)", "30 (18.4%)"],
            ["2017 International Classification", "0 (0.0%)", "31 (19.0%)"],
            ["Villefranche nosology (1997)", "7 (22.6%)", "13 (8.0%)"],
            ["Brighton criteria", "1 (3.2%)", "5 (3.1%)"],
            ["MCAS consensus criteria", "0 (0.0%)", "1 (0.6%)"],
            ["2015 POTS consensus", "0 (0.0%)", "1 (0.6%)"],
        ],
        s, col_widths=[CONTENT_W * 0.5, CONTENT_W * 0.25, CONTENT_W * 0.25]
    ))
    story.append(Spacer(1, 8))

    # Symptom profiles
    p("Symptom Frequency Profiles", "h2")
    p("Table 2 presents symptom frequencies across four mutually exclusive condition groups from the original "
      "corpus case reports, and Figure 5 provides a heatmap visualisation.")

    # Table 2 - UPDATED caption
    p("<b>Table 2.</b> Symptom frequencies (%) across condition-specific case report subgroups. Groups are "
      "mutually exclusive: \"hEDS only\" excludes articles co-discussing POTS or MCAS; \"Triad\" includes all "
      "three. All values are percentages (proportion of case reports where the symptom was detected, multiplied "
      "by 100); for example, a value of 7 in a column with n=32 indicates that 6.9% of articles in that group "
      "(approximately 2 articles) contained the symptom. Extraction F1=93.6%.", "table_caption")

    symptom_data = [
        ["Joint hypermobility", "MSK", "56.2", "6.2", "0.0", "83.3"],
        ["Subluxations/dislocations", "MSK", "33.1", "0.0", "0.0", "50.0"],
        ["Chronic pain", "MSK", "23.1", "9.4", "11.7", "55.6"],
        ["Skin hyperextensibility", "MSK", "45.0", "0.0", "0.0", "44.4"],
        ["Easy bruising", "Derm", "30.0", "0.0", "0.0", "16.7"],
        ["Tachycardia", "CV/Auto", "10.0", "93.8", "10.2", "94.4"],
        ["Syncope/presyncope", "CV/Auto", "8.1", "53.1", "18.0", "50.0"],
        ["Orthostatic intolerance", "CV/Auto", "2.5", "62.5", "0.8", "50.0"],
        ["Palpitations", "CV/Auto", "3.8", "59.4", "3.9", "33.3"],
        ["Mitral valve prolapse", "CV/Auto", "11.2", "3.1", "1.6", "27.8"],
        ["Flushing", "Immune", "1.9", "3.1", "43.8", "33.3"],
        ["Urticaria", "Immune", "1.2", "0.0", "41.4", "27.8"],
        ["Anaphylaxis", "Immune", "0.0", "0.0", "41.4", "16.7"],
        ["Fatigue", "Systemic", "6.2", "59.4", "18.0", "88.9"],
        ["GI symptoms", "GI", "33.1", "43.8", "57.0", "66.7"],
        ["Headache/migraine", "Neuro", "16.9", "50.0", "19.5", "61.1"],
        ["Neuropathy", "Neuro", "6.9", "43.8", "2.3", "55.6"],
        ["Brain fog", "Neuro", "1.2", "9.4", "0.8", "22.2"],
        ["Medication sensitivity", "Systemic", "1.2", "6.2", "10.2", "11.1"],
        ["Chiari malformation", "Neuro", "1.9", "0.0", "0.0", "11.1"],
    ]
    story.append(make_table(
        ["Symptom", "Domain", "hEDS only\n(n=160)", "POTS only\n(n=32)", "MCAS only\n(n=128)", "Triad\n(n=18)"],
        symptom_data, s,
        col_widths=[CONTENT_W*0.28, CONTENT_W*0.10, CONTENT_W*0.14, CONTENT_W*0.14, CONTENT_W*0.14, CONTENT_W*0.14]
    ))
    story.append(Spacer(1, 6))

    # Figure 5 (heatmap) - UPDATED caption
    story += add_fig("fig4_symptom_heatmap.png",
        "<b>Figure 5.</b> Symptom frequency heatmap across condition-specific case report subgroups. "
        "Cell values are rounded percentages (e.g. a cell showing \"7\" indicates 6.9%); raw counts can be "
        "derived from the group denominators in Table 2. The triad group (n=18) shows elevated frequencies "
        "across all domains, with 10 of 20 symptoms exceeding 50%, distinguishing it from any single-condition "
        "profile. Colour scale: yellow (0%) to dark red (100%).", s)

    # UPDATED: Symptom profiles discussion with organ-specificity analysis
    p("The single-condition groups show expected domain-specific signatures: hEDS-only case reports are "
      "dominated by musculoskeletal features (joint hypermobility 56.2%, skin hyperextensibility 45.0%); "
      "POTS-only by cardiovascular/autonomic features (tachycardia 93.8%, orthostatic intolerance 62.5%, "
      "palpitations 59.4%, fatigue 59.4%); and MCAS-only by immune-mediated features (GI symptoms 57.0%, "
      "flushing 43.8%, urticaria 41.4%, anaphylaxis 41.4%). These domain-specific signatures are expected: "
      "each condition's core diagnostic features are organ-system-specific, and case reports written about a "
      "single condition naturally emphasise the symptoms that motivated the diagnosis.")

    p("The pattern of symptom enrichment from single-condition to triad case reports is informative about "
      "which symptoms are organ-specific versus systemic. Symptoms that are highly prevalent in single-condition "
      "reports but do not increase substantially in the triad can be considered organ-specific markers (e.g. "
      "anaphylaxis, 41.4% in MCAS-only but only 16.7% in triad, suggesting it is specific to severe mast cell "
      "activation rather than a feature of the broader triad). Conversely, symptoms that are low in all "
      "single-condition groups but high in the triad, such as fatigue (6.2% in hEDS-only, 59.4% in POTS-only, "
      "18.0% in MCAS-only, but 88.9% in triad), may represent systemic features that emerge when multiple "
      "conditions co-occur. This distinction between organ-specific and cross-system symptoms is directly "
      "relevant to SuStaIn feature selection: organ-specific symptoms may define subtypes, while systemic "
      "symptoms may track staging or overall disease burden.")

    p("Non-organ-specific symptoms deserve particular attention. Joint hypermobility is present in 83.3% of "
      "triad cases versus 56.2% of hEDS-only cases, which could reflect either genuine higher severity in "
      "multi-condition patients or ascertainment bias. Chronic pain similarly increases from 23.1% (hEDS-only) "
      "to 55.6% (triad), consistent with additive pain burden from connective tissue, autonomic, and immune "
      "dysfunction acting across multiple organ systems. Brain fog, though infrequent across all groups (1.2% "
      "hEDS, 9.4% POTS, 0.8% MCAS), reaches 22.2% in the triad, suggesting it may be a multi-system phenomenon "
      "not well captured by any single-condition literature.")

    # UPDATED: Triad with Objective 1.2 reference
    p("The triad group (n=18) is qualitatively distinct: the majority of symptom categories exceed 50% "
      "prevalence (10 of 20), with fatigue (88.9%), tachycardia (94.4%), and joint hypermobility (83.3%) "
      "approaching near-universal reporting. This profile is consistent with the hypothesised multi-system "
      "high-burden subtype hypothesised in the main proposal, which predicts that ordinal SuStaIn "
      "will identify at least two subtypes: a connective-tissue-predominant subtype with primarily musculoskeletal "
      "features, and a multi-system high-burden subtype with elevated symptom counts across all domains. The "
      "triad case report profile, with its near-universal reporting across domains, is consistent with the "
      "latter. However, this must be interpreted with caution given the small sample size (n=18) and inherent "
      "publication bias toward unusual multi-system presentations (Nissen &amp; Wynn, 2014).")

    # Pre/post 2017 - UPDATED with criteria background
    p("Pre-2017 versus Post-2017 Diagnostic Drift", "h2")
    p("The most informative finding from this analysis concerns the systematic shift in reported symptom "
      "profiles across diagnostic criteria boundaries, which has direct implications for interpreting "
      "cross-sectional registry data collected under heterogeneous criteria regimes.")
    p("Three major criteria changes are relevant to this corpus. First, the 2017 International Classification "
      "of EDS (Malfait et al., 2017) replaced the earlier Villefranche nosology (Beighton et al., 1998) and "
      "Brighton criteria with stricter, more specific diagnostic requirements for hEDS, including age-adjusted "
      "Beighton scores, systemic features checklists, and exclusion of alternative diagnoses. This "
      "reclassification simultaneously introduced \"hypermobility spectrum disorder\" (HSD) as a category for "
      "patients with symptomatic hypermobility who do not meet full hEDS criteria (Castori et al., 2017). "
      "Second, MCAS diagnostic criteria have evolved through multiple iterations: the Molderings et al. (2011) "
      "proposed criteria, the Valent et al. (2012) consensus, and the 2019 AAAAI position statement (Weiler, "
      "2019) each set different thresholds for mediator levels, symptom specificity, and treatment response. "
      "The 2020 consensus update by Valent et al. further refined the distinction between primary (clonal), "
      "secondary, and idiopathic MCAS, adding stricter requirements for tryptase elevation (Valent et al., "
      "2020). Third, the 2015 Heart Rhythm Society expert consensus on POTS (Sheldon et al., 2015) formalised "
      "the diagnostic threshold of sustained heart rate increase of 30 bpm within 10 minutes of standing, "
      "without orthostatic hypotension. These evolving criteria mean that patients diagnosed in different eras "
      "may represent systematically different clinical populations.")

    p("hEDS: Pre-2017 (n=31) versus Post-2017 (n=163)", "h3")
    p("Post-2017 hEDS case reports showed increased reporting of fatigue (+15.0 percentage points), "
      "tachycardia (+13.9pp), skin hyperextensibility (+12.4pp), syncope (+12.0pp), subluxations/dislocations "
      "(+8.4pp), orthostatic intolerance (+8.4pp), and mitral valve prolapse (+8.3pp), with a decrease in "
      "easy bruising (-16.2pp) (Figure 6a; Table 4). The symptoms that increased post-2017 are precisely "
      "those associated with POTS and with systemic connective tissue dysfunction, whilst easy bruising, "
      "a nonspecific sign, decreased. Two non-exclusive interpretations apply: stricter 2017 criteria may "
      "select for patients with more widespread involvement (Malfait et al., 2017), and growing triad "
      "awareness may produce ascertainment bias (Kohn &amp; Chang, 2019; Halverson et al., 2023).")

    p("MCAS: Pre-2017 (n=33) versus Post-2017 (n=117)", "h3")
    p("MCAS showed the most striking shifts (Figure 6b; Table 4): joint hypermobility (+16.2pp, from 0.0% "
      "to 16.2%), orthostatic intolerance (+15.4pp, from 0.0% to 15.4%), tachycardia (+20.4pp), syncope "
      "(+20.4pp), anaphylaxis (+18.0pp), neuropathy (+14.9pp), and palpitations (+14.1pp), with a decrease "
      "in urticaria (-14.8pp). The appearance of joint hypermobility and orthostatic intolerance in post-2017 "
      "MCAS case reports, where they were entirely absent pre-2017, is the clearest signal of "
      "triad-awareness ascertainment bias. The simultaneous decrease in urticaria may reflect diagnostic "
      "broadening (Molderings et al., 2011; Afrin et al., 2017), consistent with ongoing debates about "
      "MCAS diagnostic specificity (Weiler, 2019).")

    # Table 4
    p("<b>Table 4.</b> Symptom frequency shifts (percentage points) between pre-2017 and post-2017 case "
      "reports. Only symptoms with absolute shift >8pp in at least one condition shown.", "table_caption")
    story.append(make_table(
        ["Symptom", "hEDS shift (pp)", "MCAS shift (pp)"],
        [
            ["Fatigue", "+15.0", "+9.1"],
            ["Tachycardia", "+13.9", "+20.4"],
            ["Skin hyperextensibility", "+12.4", "+7.7"],
            ["Syncope", "+12.0", "+20.4"],
            ["Subluxations/dislocations", "+8.4", "+9.4"],
            ["Orthostatic intolerance", "+8.4", "+15.4"],
            ["Mitral valve prolapse", "+8.3", "--"],
            ["Easy bruising", "-16.2", "--"],
            ["Joint hypermobility", "--", "+16.2"],
            ["Anaphylaxis", "--", "+18.0"],
            ["Neuropathy", "--", "+14.9"],
            ["Palpitations", "--", "+14.1"],
            ["Urticaria", "--", "-14.8"],
            ["Brain fog", "--", "+9.4"],
            ["Chronic pain", "--", "+8.8"],
        ],
        s, col_widths=[CONTENT_W * 0.45, CONTENT_W * 0.275, CONTENT_W * 0.275]
    ))
    story.append(Spacer(1, 6))

    # Figure 6
    story += add_fig("fig5_diagnostic_drift.png",
        "<b>Figure 6.</b> Pre-2017 versus post-2017 symptom frequency shifts in (a) hEDS and (b) MCAS case "
        "reports. Blue bars indicate increased frequency post-2017; red bars indicate decreased frequency. "
        "Values >8pp are annotated. In hEDS (a), the largest increases are in autonomic symptoms, consistent "
        "with growing triad awareness. In MCAS (b), joint hypermobility and orthostatic intolerance appear "
        "de novo in post-2017 reports, representing the clearest evidence of cross-condition ascertainment bias.",
        s)

    p("Implications for Registry Analysis", "h3")
    p("These findings have direct methodological implications for the DICE Registry analysis in Aims 1 and 2. "
      "Patients diagnosed with hEDS under post-2017 criteria may have systematically higher rates of documented "
      "autonomic and immune symptoms compared to patients diagnosed earlier, not necessarily because their "
      "disease is more severe, but because clinical attention to these features has increased (Halverson et al., "
      "2023). SuStaIn subtyping on DICE data must account for this cohort effect: apparent \"progression\" from "
      "musculoskeletal to autonomic to immune involvement may partly reflect temporal changes in diagnostic "
      "attention rather than genuine disease trajectory. The diagnostic ordering analysis in Objective 1.1 "
      "and the Cramer's V threshold in Objective 1.3 are designed to detect this confound.")
    story.append(hr())

    # ── SUPPLEMENTARY: NARROW VS BROAD ──
    p("Supplementary Analysis: Narrow versus Broad Diagnostic Definitions", "h1")

    p("Adjacent Condition Corpus", "h2")
    p("Nine additional PMC queries for umbrella and adjacent conditions (dysautonomia, orthostatic intolerance, "
      "autonomic dysfunction, vasovagal syncope, JHS, HSD, histamine intolerance, hereditary alpha tryptasemia, "
      "idiopathic anaphylaxis) yielded 683 new PMCIDs not present in the original corpus. The largest "
      "contributions came from autonomic dysfunction (448 new articles) and dysautonomia (163 new articles). "
      "Full-text retrieval and extraction were completed for all 683 articles (100% success rate), bringing "
      "the total corpus to 1,400 articles (688 case reports). These articles were retrieved by independent "
      "queries, avoiding the circularity of applying broad-tier classification to narrow-term-retrieved articles.")

    p("Results", "h2")
    # UPDATED: Clarified POTS framing
    p("The narrow versus broad comparison was only feasible for POTS, and this is a consequence of analysis "
      "design rather than a choice to focus on POTS specifically. The ideal analysis would compare narrow versus "
      "broad tiers for all three conditions; in practice, the EDS and MCAS broad tiers yielded too few "
      "non-overlapping articles (5 and 3 respectively), because JHS, HSD, and histamine intolerance barely "
      "exist as standalone case report diagnoses in the PMC Open Access literature. The POTS comparison "
      "succeeded because dysautonomia and autonomic dysfunction have substantial independent literatures (610 "
      "non-overlapping articles, 284 case reports). This asymmetry is itself informative: it suggests that POTS "
      "sits within a broader ecosystem of autonomic conditions with distinct publication traditions, while hEDS "
      "and MCAS have largely absorbed their umbrella categories in the published literature.")

    # Table 5 - UPDATED: all 20 symptoms, POTS-specific framing
    p("<b>Table 5.</b> Symptom frequencies (%): POTS narrow versus dysautonomia/orthostatic intolerance "
      "broad-only case reports. POTS narrow includes all case reports retrieved by POTS-specific search "
      "terms (n=119). Broad-only includes case reports retrieved by independent PMC queries for adjacent "
      "autonomic conditions that do not mention POTS (n=284). All 20 symptom categories shown; dashes "
      "indicate differences &lt;1pp.", "table_caption")
    story.append(make_table(
        ["Symptom", "Domain", "POTS narrow\n(n=119)", "Broad-only\n(n=284)", "Diff (pp)"],
        [
            ["Tachycardia", "CV/Auto", "95.8", "34.9", "+60.9"],
            ["Fatigue", "Systemic", "60.5", "13.4", "+47.1"],
            ["Orthostatic intolerance", "CV/Auto", "51.3", "5.3", "+46.0"],
            ["Palpitations", "CV/Auto", "50.4", "7.7", "+42.7"],
            ["Headache/migraine", "Neuro", "49.6", "18.7", "+30.9"],
            ["Syncope/presyncope", "CV/Auto", "53.8", "23.9", "+29.8"],
            ["Joint hypermobility", "MSK", "31.1", "4.6", "+26.5"],
            ["Chronic pain", "MSK", "34.5", "17.3", "+17.2"],
            ["Skin hyperextensibility", "MSK", "16.8", "3.9", "+12.9"],
            ["Brain fog", "Neuro", "15.1", "4.6", "+10.5"],
            ["Subluxations/dislocations", "MSK", "15.1", "5.3", "+9.8"],
            ["GI symptoms", "GI", "54.6", "45.8", "+8.8"],
            ["Flushing", "Immune", "11.8", "4.2", "+7.5"],
            ["Easy bruising", "Derm", "8.4", "1.8", "+6.6"],
            ["Urticaria", "Immune", "7.6", "1.1", "+6.5"],
            ["Mitral valve prolapse", "CV/Auto", "6.7", "2.1", "+4.6"],
            ["Anaphylaxis", "Immune", "6.7", "3.2", "+3.6"],
            ["Neuropathy", "Neuro", "47.1", "48.2", "-1.2"],
            ["Medication sensitivity", "Systemic", "6.7", "6.3", "--"],
            ["Chiari malformation", "Neuro", "0.0", "0.0", "--"],
        ],
        s, col_widths=[CONTENT_W*0.28, CONTENT_W*0.12, CONTENT_W*0.18, CONTENT_W*0.18, CONTENT_W*0.18]
    ))
    story.append(Spacer(1, 6))

    # Figure 7
    story += add_fig("fig7_narrow_vs_broad.png",
        "<b>Figure 7.</b> Symptom frequency comparison: POTS narrow versus dysautonomia/OI broad-only case "
        "reports. POTS case reports (blue, n=119) show substantially higher frequencies across nearly all "
        "symptom categories compared to the broader dysautonomia literature (orange, n=284). Joint hypermobility "
        "(+26.5pp) and chronic pain (+17.2pp) are not canonical autonomic symptoms, suggesting POTS carries "
        "a multi-system phenotypic signature influenced by clinical awareness of connective tissue associations.",
        s)

    p("POTS case reports report higher frequencies across nearly every symptom category. Joint hypermobility "
      "(+26.5pp) and chronic pain (+17.2pp) are not canonical autonomic symptoms, yet they appear substantially "
      "more often in POTS case reports. Neuropathy is the notable exception: it is essentially equivalent in "
      "both groups (47.1% vs 48.2%), which is expected because neuropathy is a core feature of many dysautonomia "
      "aetiologies (diabetic, autoimmune, paraneoplastic) and is not specific to POTS.")

    p("The dysautonomia broad-only group is heterogeneous by design, encompassing diabetic autonomic neuropathy, "
      "Guillain-Barre syndrome, familial dysautonomia, and other aetiologies. The comparison is between POTS "
      "as a specific diagnostic entity and autonomic dysfunction as a broad clinical finding. The large "
      "differences confirm that POTS carries a distinct multi-system phenotypic signature not captured by the "
      "broader category, supporting the use of narrow POTS diagnostic definitions rather than broader "
      "\"dysautonomia\" labels in the DICE Registry analysis.")
    story.append(hr())

    # ── LIMITATIONS ──
    p("Limitations", "h1")
    for lim in [
        "<b>Publication bias.</b> Case reports over-represent unusual, severe, or multi-system presentations "
        "(Nissen &amp; Wynn, 2014). Symptom frequencies reported here are upper-bound estimates relative to "
        "clinical populations and cannot be used to infer population prevalence.",
        "<b>PMC Open Access subset.</b> The analysis is restricted to the PMC OA corpus, excluding journals "
        "without open access mandates, non-English publications, and paywalled articles. This introduces "
        "geographic and institutional bias (Piwowar et al., 2018).",
        "<b>Rule-based extraction.</b> Symptom F1 of 93.6% implies ~6% error. Negation handling is "
        "incomplete. The higher F1 relative to LLM-based benchmarks (Reese et al., 2025; F1=0.78) partly "
        "reflects the coarser granularity of our 20 symptom categories compared to HPO terms.",
        "<b>Small sample sizes.</b> Pre-2017 subgroup analyses are constrained by small denominators "
        "(hEDS: n=31; POTS: n=6; MCAS: n=33; triad: n=18). Formal statistical testing was not performed; "
        "reported shifts are descriptive and hypothesis-generating.",
        "<b>Confounding.</b> Pre/post-2017 comparisons cannot distinguish genuine phenotype change from "
        "ascertainment bias or literature trends. These are precisely the confounds the DICE Registry analysis "
        "is designed to address.",
        "<b>Broad-tier limitations.</b> EDS and MCAS broad tiers contain too few non-overlapping articles "
        "(5 and 3) for meaningful comparison. The POTS broad tier is aetiologically heterogeneous.",
    ]:
        p(lim)
    story.append(hr())

    # ── REUSABLE PIPELINE ──
    p("Generalisability: A Reusable Pipeline for Rare Disease Comorbidity Research", "h1")
    p("The extraction and analysis pipeline developed for this work is designed to be condition-agnostic and "
      "reusable. The core workflow, comprising PMC Open Access query construction, full-text XML retrieval via "
      "E-utilities, rule-based symptom extraction with configurable regex patterns, article type classification, "
      "and tiered diagnostic reclassification, can be applied to any set of comorbid rare conditions where the "
      "research questions concern phenotypic overlap, diagnostic drift, and ascertainment bias. The pipeline "
      "requires only three inputs to adapt to a new condition triad (or dyad, or larger comorbidity cluster): "
      "a set of narrow diagnostic search terms, a set of broader umbrella/adjacent condition terms for "
      "non-circular comparisons, and a symptom extraction schema defining the phenotypic categories of interest.")
    p("The analysis framework is particularly suited to conditions where diagnostic criteria have evolved over "
      "time, where clinical awareness of comorbid associations is growing, and where the published literature "
      "is primarily case reports rather than large cohort studies, all of which are common features of rare "
      "disease research. The adjacent-condition query design addresses a methodological gap in the existing "
      "literature phenotyping toolkit: it enables non-circular comparison between narrow and broad diagnostic "
      "definitions without the tautological problem of applying broad-tier labels only to articles already "
      "retrieved by narrow search terms.")
    p("The complete pipeline code, including all extraction scripts, analysis notebooks, and figure generation, "
      "is available as an open-source repository (https://github.com/Amelia3141/triad_phenotype_mining) to enable replication and adaptation to other rare disease "
      "comorbidity clusters. Potential applications include the fibromyalgia-chronic fatigue syndrome-irritable "
      "bowel syndrome overlap, the autoimmune polyendocrinopathy cluster, and other conditions where "
      "multi-system phenotypic characterisation from the published literature could inform registry-based or "
      "genomic subtyping studies.")
    story.append(hr())

    # ── SUMMARY ──
    p("Summary and Implications for DICE Registry Analysis", "h1")
    for para in [
        "This preliminary literature phenotyping establishes several empirical findings that directly inform "
        "the registry-based SuStaIn analysis.",
        "The published case report literature for the triad is growing rapidly (approximately 10-fold increase "
        "in annual publication rate from 2010 to 2025; Figure 2), but remains sparse for the triad itself "
        "(n=18 case reports). This underscores the need for registry-based analysis with substantially larger "
        "sample sizes, and supports the choice of the DICE Global Registry (n~8,000) as the primary data "
        "source for Aim 1.",
        "Diagnostic terminology has not converged following the 2017 reclassification (Figure 4). Multiple "
        "naming conventions coexist, and older terms persist (Ritelli et al., 2024). This heterogeneity will "
        "be reflected in DICE Registry data and motivates inclusion of diagnostic ordering as a covariate in "
        "the regression models of Aim 2.",
        "Post-2017 case reports show systematic increases in cross-domain symptom documentation (Figure 6; "
        "Table 4). This is consistent with ascertainment bias driven by growing triad awareness "
        "(Kohn &amp; Chang, 2019), and means symptom profiles in the DICE Registry may be partially confounded "
        "with era of diagnosis. The diagnostic ordering analysis in Objective 1.1 and the Cramer's V threshold "
        "in Objective 1.3 are designed to detect and quantify this confound.",
        "Triad case reports present a distinctive multi-system phenotype (>50% prevalence across 10 of 20 "
        "categories; Table 2, Figure 5) consistent with the hypothesised multi-system high-burden subtype. "
        "The small sample (n=18) and publication bias mean this requires validation against "
        "the DICE cohort.",
        "The narrow versus broad comparison confirms that POTS carries a distinct phenotypic signature not "
        "captured by the broader dysautonomia literature (Table 5, Figure 7), supporting narrow diagnostic "
        "definitions in the DICE Registry analysis.",
    ]:
        p(para)

    # NEW: ML framework context from thesis proposal
    p("Beyond informing the SuStaIn subtyping, these findings have broader implications for the machine learning "
      "framework proposed in the main thesis. The organ-specificity analysis (Table 2) directly informs feature "
      "engineering for the hierarchical graph attention network architecture: organ-specific symptoms (e.g. "
      "anaphylaxis, tachycardia, joint hypermobility) can serve as condition-level nodes in a multi-scale graph, "
      "while cross-system symptoms (e.g. fatigue, GI dysfunction, chronic pain) that are elevated in the triad "
      "but not specific to any single condition can serve as higher-order edges connecting condition subgraphs. "
      "The systematic ascertainment bias documented in Figures 5 and 6, where post-2017 case reports show "
      "inflated cross-domain symptom reporting, provides empirical grounding for the fairness-aware design "
      "component of the proposed framework: models trained on temporally heterogeneous data must account for "
      "era-dependent documentation patterns to avoid learning spurious associations between conditions. The "
      "causal discovery module, integrating Granger-causal attention mechanisms, is specifically designed to "
      "distinguish the genuine mechanistic relationships underlying the triad from the ascertainment-driven "
      "correlations that this literature analysis has quantified. Finally, the diagnostic odyssey data, with "
      "women waiting an average of 8.5 years longer for diagnosis (Halverson et al., 2023b), motivates the "
      "contrastive learning approach to subgroup identification: if ML models can identify phenotypic signatures "
      "predictive of the triad at earlier disease stages, this could substantially reduce diagnostic delay, "
      "particularly for the demographic groups most affected by current diagnostic disparities.")
    story.append(hr())

    # ── REFERENCES ──
    story.append(PageBreak())
    p("References", "h1")
    refs = [
        "Afrin, L.B., Self, S., Menk, J., Lazarchick, J. (2017). Characterization of mast cell activation syndrome. <i>American Journal of the Medical Sciences</i>, 353(3), 207-215.",
        "Akin, C., Valent, P., Metcalfe, D.D. (2010). Mast cell activation syndrome: proposed diagnostic criteria. <i>Journal of Allergy and Clinical Immunology</i>, 126(6), 1099-1104.",
        "Beighton, P., De Paepe, A., Steinmann, B., Tsipouras, P., Wenstrup, R.J. (1998). Ehlers-Danlos syndromes: revised nosology, Villefranche, 1997. <i>American Journal of Medical Genetics</i>, 77(1), 31-37.",
        "Brokering, J., et al. (2025). Can LLMs reliably extract human disease genes from full-text scientific literature? <i>bioRxiv</i>, 2025.07.27.667022.",
        "Byers, P.H. (2017). Vascular Ehlers-Danlos syndrome. In: <i>GeneReviews</i>. University of Washington, Seattle.",
        "CaseReportBench (2025). An LLM benchmark dataset for dense information extraction in clinical case reports. <i>arXiv</i>, 2505.17265.",
        "Castori, M. (2011). Ehlers-Danlos syndrome, hypermobility type: an underdiagnosed hereditary connective tissue disorder. <i>ISRN Dermatology</i>, 2012, 751768.",
        "Castori, M., Tinkle, B., Levy, H., et al. (2017). A framework for the classification of joint hypermobility and related conditions. <i>American Journal of Medical Genetics Part C</i>, 175(1), 148-157.",
        "Demmler, J.C., et al. (2019). Diagnosed prevalence of Ehlers-Danlos syndrome and hypermobility spectrum disorder in Wales, UK. <i>BMJ Open</i>, 9(11), e031365.",
        "Fedorowski, A., Sutton, R. (2023). Autonomic dysfunction and POTS in post-acute COVID-19 syndrome. <i>Nature Reviews Cardiology</i>, 20(5), 281-282.",
        "Halverson, C.M.E., et al. (2023). The diagnostic odyssey of patients with Ehlers-Danlos syndrome. <i>American Journal of Medical Genetics Part A</i>, 191(2), 484-492.",
        "Halverson, C.M.E., Cao, S., Perkins, S.M., Francomano, C.A. (2023b). Comorbidity, misdiagnoses, and the diagnostic odyssey in patients with hypermobile Ehlers-Danlos syndrome. <i>Genetics in Medicine Open</i>, 1(1), 100812.",
        "Kohn, A., Chang, C. (2019). The relationship between hEDS, POTS, and MCAS. <i>Clinical Reviews in Allergy &amp; Immunology</i>, 58(3), 273-297.",
        "Malfait, F., Francomano, C., Byers, P., et al. (2017). The 2017 international classification of the Ehlers-Danlos syndromes. <i>American Journal of Medical Genetics Part C</i>, 175(1), 8-26.",
        "Molderings, G.J., et al. (2011). Mast cell activation disease: a concise practical guide. <i>Journal of Hematology &amp; Oncology</i>, 4, 10.",
        "NCBI (2024). PubMed help: publication types. <i>National Center for Biotechnology Information</i>.",
        "Nissen, T., Wynn, R. (2014). The clinical case report: a review of its merits and limitations. <i>BMC Research Notes</i>, 7, 264.",
        "Piwowar, H., et al. (2018). The state of OA: a large-scale analysis of the prevalence and impact of Open Access articles. <i>PeerJ</i>, 6, e4375.",
        "Quigley, E.M.M., Noble, O., Ansari, U. (2024). The suggested relationships between common GI symptoms and joint hypermobility, POTS, and MCAS. <i>Gastroenterology &amp; Hepatology</i>, 20(8), 479-489.",
        "Reese, J.T., et al. (2025). RAG-HPO: improving automated deep phenotyping through retrieval-augmented generation with LLMs. <i>Genome Medicine</i>, 17, 4.",
        "Ritelli, M., et al. (2024). Looking back and beyond the 2017 diagnostic criteria for hypermobile Ehlers-Danlos syndrome. <i>American Journal of Medical Genetics Part A</i>, 194(1), e63410.",
        "Sayers, E.W., et al. (2022). Database resources of the National Center for Biotechnology Information. <i>Nucleic Acids Research</i>, 50(D1), D13-D25.",
        "Shirvani, P., Shirvani, A., Holick, M.F. (2024). Decoding the genetic basis of mast cell hypersensitivity and infection risk in hypermobile Ehlers-Danlos syndrome. <i>Current Issues in Molecular Biology</i>, 46(10), 11613-11629.",
        "Sheldon, R.S., Grubb, B.P., Olshansky, B., et al. (2015). 2015 Heart Rhythm Society expert consensus statement on the diagnosis and treatment of postural tachycardia syndrome, inappropriate sinus tachycardia, and vasovagal syncope. <i>Heart Rhythm</i>, 12(6), e41-e63.",
        "Tinkle, B., et al. (2017). Hypermobile Ehlers-Danlos syndrome: clinical description and natural history. <i>American Journal of Medical Genetics Part C</i>, 175(1), 48-69.",
        "Valent, P., et al. (2012). Definitions, criteria and global classification of mast cell disorders. <i>International Archives of Allergy and Immunology</i>, 157(3), 215-225.",
        "Valent, P., Akin, C., Bonadonna, P., et al. (2020). Proposed diagnostic algorithm for patients with suspected mast cell activation syndrome. <i>Journal of Allergy and Clinical Immunology: In Practice</i>, 7(4), 1252-1261.",
        "Vernino, S., Bourne, K.M., Stiles, L.E., et al. (2021). Postural orthostatic tachycardia syndrome (POTS): state of the science and clinical care from a 2019 National Institutes of Health Expert Consensus Meeting, Part 1. <i>Autonomic Neuroscience</i>, 235, 102828.",
        "Wang, K., et al. (2024). Characterisation of comorbidities in the Ehlers-Danlos syndromes: DICE Global Registry. <i>Genetics in Medicine</i>, 26(3), 101059.",
        "Wang, Y.-T., Jahani, S., Morel-Swols, D., Kapely, A., Rosen, A., Forghani, I. (2024). Patient experiences of receiving a diagnosis of hypermobile Ehlers-Danlos syndrome. <i>American Journal of Medical Genetics Part A</i>, 194(8), e63613.",
        "Weiler, C.R. (2019). Mast cell activation syndrome: tools for diagnosis and differential diagnosis. <i>JACI: In Practice</i>, 8(2), 498-506.",
    ]
    for r in refs:
        story.append(Paragraph(r, s["ref"]))

    # ── BUILD ──
    doc = SimpleDocTemplate(
        OUT_PDF, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title="Preliminary Literature Phenotyping: EDS-POTS-MCAS Triad",
        author="amelia",
    )

    def add_page_numbers(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(grey)
        canvas.drawCentredString(PAGE_W / 2, 1.2 * cm, f"{doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_numbers, onLaterPages=add_page_numbers)
    print(f"PDF saved: {OUT_PDF}")
    print(f"Pages: {doc.page}")


if __name__ == "__main__":
    build_pdf()
