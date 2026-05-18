#!/usr/bin/env python3
"""
Build an ANNOTATED version of the lit review PDF showing where each of the
12 supervisor feedback items (24 April meeting) was addressed.

Each change is highlighted in yellow with a red numbered badge [1]-[12].
A legend page at the front maps numbers to feedback items.
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
OUT_PDF = os.path.join(BASE_DIR, "outputs/preliminary_literature_phenotyping_EDITS.pdf")

PAGE_W, PAGE_H = A4
MARGIN = 2.2 * cm
CONTENT_W = PAGE_W - 2 * MARGIN

# Colours
ACCENT = HexColor("#1565C0")
LIGHT_BG = HexColor("#F5F7FA")
RULE_COLOR = HexColor("#CCCCCC")
TABLE_HEADER_BG = HexColor("#E3F2FD")
TABLE_ALT_BG = HexColor("#F9FAFB")
HIGHLIGHT_BG = "#FFFFAA"  # yellow highlight
BADGE_COLOR = "#D32F2F"   # red badge


def badge(n):
    """Return an inline red numbered badge."""
    return f'<font color="{BADGE_COLOR}" size="11"><b>[{n}]</b></font> '


def hl(text, n=None):
    """Wrap text in yellow highlight, optionally with a numbered badge prefix."""
    prefix = badge(n) if n else ""
    return f'{prefix}<font backColor="{HIGHLIGHT_BG}">{text}</font>'


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
    styles["body_hl"] = ParagraphStyle(
        "BodyHL", parent=ss["Normal"],
        fontSize=9.5, leading=13, spaceAfter=6,
        alignment=TA_JUSTIFY, fontName="Helvetica",
        backColor=HexColor(HIGHLIGHT_BG),
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
    styles["table_caption_hl"] = ParagraphStyle(
        "TableCaptionHL", parent=ss["Normal"],
        fontSize=8.5, leading=11, spaceAfter=4, spaceBefore=8,
        alignment=TA_LEFT, fontName="Helvetica-Bold",
        textColor=HexColor("#333333"),
        backColor=HexColor(HIGHLIGHT_BG),
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
    styles["legend_item"] = ParagraphStyle(
        "LegendItem", parent=ss["Normal"],
        fontSize=10, leading=14, spaceAfter=8,
        alignment=TA_LEFT, fontName="Helvetica",
        leftIndent=24, firstLineIndent=-24,
    )
    styles["legend_title"] = ParagraphStyle(
        "LegendTitle", parent=ss["Title"],
        fontSize=14, leading=18, spaceAfter=12,
        textColor=HexColor("#111111"), alignment=TA_LEFT,
    )
    return styles


def hr():
    return HRFlowable(width="100%", thickness=0.5, color=RULE_COLOR, spaceAfter=6, spaceBefore=6)


def add_fig(filename, caption_text, styles, width_pct=0.92, max_height=None):
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


def make_table_highlighted(headers, rows, styles, col_widths=None):
    """Same as make_table but with yellow background on all data rows."""
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
    # Highlight all data rows yellow
    for i in range(1, len(data)):
        style_cmds.append(("BACKGROUND", (0, i), (-1, i), HexColor(HIGHLIGHT_BG)))
    t.setStyle(TableStyle(style_cmds))
    return t


def build_pdf():
    styles = make_styles()
    s = styles
    story = []

    def p(text, style="body"):
        story.append(Paragraph(text, s[style]))

    def p_hl(text, n, style="body_hl"):
        """Highlighted paragraph with numbered badge."""
        story.append(Paragraph(badge(n) + text, s[style]))

    # ══════════════════════════════════════════════════════
    # LEGEND PAGE
    # ══════════════════════════════════════════════════════
    p("Annotated Edits: Supervisor Feedback (24 April Meeting)", "legend_title")
    p("This document highlights where each of the 12 feedback items was addressed. "
      "Yellow-highlighted text with red numbered badges marks each change.", "body")
    story.append(Spacer(1, 12))

    legend_items = [
        ("[1] Add subtype background", "New paragraph in Rationale covering EDS subtypes, POTS subtypes, MCAS diagnostic boundaries, and their relevance to SuStaIn."),
        ("[2] Fix validation methodology", "Expanded validation section: stratified random sampling details, seed reproducibility, random baseline F1 computation."),
        ("[3] Address 2017 + 2020 + 2015 diagnostic criteria", "New paragraph detailing all three criteria changes: 2017 EDS reclassification, Valent 2020 MCAS update, Sheldon 2015 POTS consensus."),
        ("[4] Write up organ-specificity analysis", "New paragraphs explaining which symptoms are organ-specific vs systemic, with implications for SuStaIn feature selection."),
        ("[5] Add Objective 1.2 reference", "Triad profile paragraph now explicitly links to Objective 1.2 multi-system high-burden subtype hypothesis."),
        ("[6] Add co-occurrence references", "Co-occurrence discussion now cites Wang 2024 (31% POTS, 14% MCAS) and Kohn &amp; Chang 2019 (80% estimate)."),
        ("[7] Fix Table 5: all 20 symptoms, POTS framing", "Table 5 expanded from 11 to 20 symptoms with Domain column; framing clarifies POTS-specific vs broad-tier comparison."),
        ("[8] Clarify Table 2 / heatmap values are percentages", "Table 2 caption updated: explains values are percentages, gives worked example (7 = 6.9%). Heatmap caption also updated."),
        ("[9] Clarify POTS analysis framing", "Narrow vs broad results section rewritten to explain why only POTS comparison was feasible, not a choice."),
        ("[10] Add comorbidity background", "New paragraph in Rationale on clinical overlap: Wang 2024, Kohn &amp; Chang 2019, Demmler 2019 prevalence data."),
        ("[11] Clarify Figure 2 discussion", "Figure 2 text clarifies these are raw counts not regression; explains MCAS earlier inflection and POTS post-COVID acceleration."),
        ("[12] Frame code as reusable pipeline", "New section: 'Generalisability: A Reusable Pipeline for Rare Disease Comorbidity Research'."),
    ]
    for item in legend_items:
        story.append(Paragraph(
            f'<font color="{BADGE_COLOR}"><b>{item[0]}</b></font>  {item[1]}',
            s["legend_item"]
        ))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # MAIN DOCUMENT (with highlights)
    # ══════════════════════════════════════════════════════

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

    # [1] Subtype background
    p_hl("The conditions comprising this triad are each clinically heterogeneous. Ehlers-Danlos syndrome encompasses "
      "13 subtypes under the 2017 International Classification (Malfait et al., 2017), of which hypermobile EDS "
      "(hEDS) is the most common and the only subtype without a confirmed genetic basis; the remaining subtypes "
      "(vascular, classical, kyphoscoliotic, and others) involve identified mutations in collagen or related "
      "extracellular matrix genes (Byers, 2017; Malfait et al., 2017). POTS itself is increasingly recognised "
      "as a heterogeneous syndrome with neuropathic, hyperadrenergic, and hypovolaemic subtypes that may respond "
      "to different treatments (Fedorowski &amp; Sutton, 2023; Vernino et al., 2021). MCAS diagnostic boundaries "
      "remain actively debated, with consensus and proposed criteria differing on the mediator thresholds, symptom "
      "specificity, and response-to-treatment requirements needed for diagnosis (Valent et al., 2012; Weiler, "
      "2019; Afrin et al., 2017). Understanding whether these subtypes cluster differently within the triad is "
      "a primary objective of the SuStaIn modelling in Aim 1.", 1)

    # [10] Comorbidity background
    p_hl("The clinical overlap between these conditions has been documented in several cohort and registry studies. "
      "Wang et al. (2024) reported that 31% of EDS patients in the DICE Global Registry had concurrent POTS and "
      "14% had MCAS. Kohn and Chang (2019) reviewed proposed mechanistic links, including connective tissue "
      "laxity affecting vascular compliance (producing orthostatic intolerance) and mast cell degranulation "
      "triggered by mechanical tissue stress. Demmler et al. (2019) established population-level prevalence "
      "estimates for hEDS/HSD in Wales, finding substantially higher rates than previously assumed. These "
      "findings motivate the need for systematic characterisation of the phenotypic landscape across all three "
      "conditions simultaneously, rather than studying each in isolation.", 10)

    # Obsidian additions (not numbered - these are from the Obsidian integration, not the 12 feedback items)
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
    p("<b>Table 1.</b> Corpus retrieval queries.", "table_caption")
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

    # [2] Validation
    p("Validation", "h2")
    p_hl("Extraction accuracy was assessed by manual validation against full-text source documents. Ten articles "
      "were selected by stratified random sampling: three from hEDS case reports, two from POTS, two from MCAS, "
      "and three from triad case reports. Stratification ensured representation across all condition groups; "
      "within each stratum, articles were selected using Python's random.sample() with a fixed seed for "
      "reproducibility. For each sampled article, a human reviewer independently extracted all symptoms, "
      "demographics, and condition mentions from the full text, and these were compared against the pipeline's "
      "automated output.", 2)
    p_hl("Symptom extraction achieved precision of 89.3%, recall of 80.6%, and F1 of 84.7%. Age accuracy was 80% "
      "(8 of 10 articles correctly extracted). POTS detection was 100%; EDS and MCAS detection were each 80%, "
      "with misses attributable to negation handling limitations. To contextualise "
      "these figures, a random baseline was computed: given the marginal symptom prevalence across the corpus "
      "(mean ~15% per category), a classifier that randomly assigns symptoms at the corpus base rate would "
      "achieve an expected F1 of approximately 0.15, confirming that the pipeline's F1 of 84.7% reflects "
      "genuine extraction performance rather than artefact of class imbalance. These figures are comparable to "
      "the RAG-HPO benchmark (F1=0.78; Reese et al., 2025). "
      "The CaseReportBench framework (CaseReportBench, 2025) "
      "informed extraction schema design.", 2)

    # Figure 1
    story.append(PageBreak())
    story += add_fig("fig1_corpus_flow.png",
        "<b>Figure 1.</b> Corpus assembly and cleaning flow diagram.",
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

    # [11] Figure 2 clarification
    p_hl("Figure 2 shows raw publication counts per year (not a regression model); the coloured lines represent "
      "observed annual totals for each condition, and the grey bars show overall case report volume. The "
      "different temporal trajectories are notable: the hEDS inflection aligns with the 2017 criteria revision, "
      "while the MCAS growth curve is offset earlier (around 2014-2016, coinciding with increasing clinical "
      "interest following the Molderings et al. (2011) and Valent et al. (2012) proposed criteria) and POTS "
      "later (post-2020, possibly accelerated by COVID-19-associated POTS awareness; Fedorowski &amp; Sutton, "
      "2023). These different growth trajectories mean that studying each condition's literature in isolation "
      "would miss the broader pattern: the triad as a clinical concept has driven a simultaneous, coordinated "
      "increase in publications across all three conditions, particularly after 2017.", 11)
    p("The top contributing journals were Cureus (n=23), Clinical Case Reports (n=21), JACC Case Reports "
      "(n=12), and Journal of Medical Case Reports (n=11).")

    story += add_fig("fig2_temporal_trends.png",
        "<b>Figure 2.</b> Temporal publication trends for EDS-POTS-MCAS case reports, 2004-2026. "
        "This is not a regression model; lines connect raw annual counts.", s)

    # [6] Co-occurrence with references
    p_hl("Cross-condition co-occurrence within the case report corpus was sparse (Figure 3): 160 articles "
      "discussed EDS alone, 32 POTS alone, and 128 MCAS alone. Only 21 co-discussed EDS and POTS, "
      "4 EDS and MCAS, 11 POTS and MCAS, and 18 all three conditions. This pattern of low co-discussion "
      "contrasts sharply with clinical co-occurrence rates: Wang et al. (2024) found that 31% of EDS patients "
      "in the DICE Global Registry had concurrent POTS and 14% had MCAS, while Kohn and Chang (2019) estimated "
      "that up to 80% of hEDS patients may have POTS based on clinical series. The discrepancy reflects the "
      "siloed nature of case report publishing, where most reports are written by specialists within a single "
      "discipline. This silo effect is itself a form of ascertainment bias that directly motivates the use of "
      "multi-condition registry data such as the DICE cohort for subtype analysis.", 6)

    story += add_fig("fig6_co_occurrence.png",
        "<b>Figure 3.</b> Condition co-occurrence in original corpus case reports (n=376).", s)

    # Terminology drift
    p("Diagnostic Terminology Drift", "h2")
    p("Terminology usage shifted substantially across the 2017 criteria boundary (Figure 4). Among hEDS "
      "case reports, \"EDS type III\" appeared in 42% of pre-2017 articles (n=31) versus 23% post-2017 "
      "(n=163), while \"hEDS\" as a standalone abbreviation was absent pre-2017 and present in 18% of "
      "post-2017 articles. \"Hypermobile EDS\" increased from 19% to 26%, and \"joint hypermobility syndrome\" "
      "(JHS) increased from 26% to 33%. "
      "\"Hypermobility spectrum disorder\" (HSD) rose from 3% to 9%, consistent with the term's introduction "
      "in the 2017 framework.")

    story += add_fig("fig3_terminology_drift.png",
        "<b>Figure 4.</b> Diagnostic terminology drift in hEDS case reports across the 2017 criteria boundary.",
        s)

    p("Diagnostic criteria citation patterns reinforce this picture (Table 3).")

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
    p("Table 2 presents symptom frequencies across four mutually exclusive condition groups.")

    # [8] Table 2 caption - highlighted
    p(badge(8) + "<b>Table 2.</b> Symptom frequencies (%) across condition-specific case report subgroups. Groups are "
      "mutually exclusive: \"hEDS only\" excludes articles co-discussing POTS or MCAS; \"Triad\" includes all "
      "three. <font backColor=\"" + HIGHLIGHT_BG + "\">All values are percentages (proportion of case reports where the symptom was detected, multiplied "
      "by 100); for example, a value of 7 in a column with n=32 indicates that 6.9% of articles in that group "
      "(approximately 2 articles) contained the symptom.</font> Extraction F1=84.7%.", "table_caption")

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

    # [8] Heatmap caption also highlighted
    story += add_fig("fig4_symptom_heatmap.png",
        badge(8) + "<b>Figure 5.</b> Symptom frequency heatmap. "
        "<font backColor=\"" + HIGHLIGHT_BG + "\">Cell values are rounded percentages (e.g. a cell showing \"7\" indicates 6.9%); "
        "raw counts can be derived from the group denominators in Table 2.</font> "
        "The triad group (n=18) shows elevated frequencies across all domains.", s)

    # [4] Organ-specificity analysis
    p("The single-condition groups show expected domain-specific signatures: hEDS-only case reports are "
      "dominated by musculoskeletal features (joint hypermobility 56.2%, skin hyperextensibility 45.0%); "
      "POTS-only by cardiovascular/autonomic features (tachycardia 93.8%, orthostatic intolerance 62.5%, "
      "palpitations 59.4%, fatigue 59.4%); and MCAS-only by immune-mediated features (GI symptoms 57.0%, "
      "flushing 43.8%, urticaria 41.4%, anaphylaxis 41.4%).")

    p_hl("The pattern of symptom enrichment from single-condition to triad case reports is informative about "
      "which symptoms are organ-specific versus systemic. Symptoms that are highly prevalent in single-condition "
      "reports but do not increase substantially in the triad can be considered organ-specific markers (e.g. "
      "anaphylaxis, 41.4% in MCAS-only but only 16.7% in triad, suggesting it is specific to severe mast cell "
      "activation rather than a feature of the broader triad). Conversely, symptoms that are low in all "
      "single-condition groups but high in the triad, such as fatigue (6.2% in hEDS-only, 59.4% in POTS-only, "
      "18.0% in MCAS-only, but 88.9% in triad), may represent systemic features that emerge when multiple "
      "conditions co-occur. This distinction between organ-specific and cross-system symptoms is directly "
      "relevant to SuStaIn feature selection: organ-specific symptoms may define subtypes, while systemic "
      "symptoms may track staging or overall disease burden.", 4)

    p("Non-organ-specific symptoms deserve particular attention. Joint hypermobility is present in 83.3% of "
      "triad cases versus 56.2% of hEDS-only cases. Chronic pain similarly increases from 23.1% (hEDS-only) "
      "to 55.6% (triad). Brain fog, though infrequent across all groups, "
      "reaches 22.2% in the triad, suggesting it may be a multi-system phenomenon.")

    # [5] Triad with Objective 1.2
    p_hl("The triad group (n=18) is qualitatively distinct: the majority of symptom categories exceed 50% "
      "prevalence (10 of 20), with fatigue (88.9%), tachycardia (94.4%), and joint hypermobility (83.3%) "
      "approaching near-universal reporting. This profile is consistent with the hypothesised multi-system "
      "high-burden subtype described in Objective 1.2 of the main proposal, which predicts that ordinal SuStaIn "
      "will identify at least two subtypes: a connective-tissue-predominant subtype with primarily musculoskeletal "
      "features, and a multi-system high-burden subtype with elevated symptom counts across all domains. The "
      "triad case report profile, with its near-universal reporting across domains, is consistent with the "
      "latter. However, this must be interpreted with caution given the small sample size (n=18) and inherent "
      "publication bias toward unusual multi-system presentations (Nissen &amp; Wynn, 2014).", 5)

    # [3] Pre/post 2017 criteria background
    p("Pre-2017 versus Post-2017 Diagnostic Drift", "h2")
    p("The most informative finding from this analysis concerns the systematic shift in reported symptom "
      "profiles across diagnostic criteria boundaries.")
    p_hl("Three major criteria changes are relevant to this corpus. First, the 2017 International Classification "
      "of EDS (Malfait et al., 2017) replaced the earlier Villefranche nosology (Beighton et al., 1998) and "
      "Brighton criteria with stricter, more specific diagnostic requirements for hEDS, including age-adjusted "
      "Beighton scores, systemic features checklists, and exclusion of alternative diagnoses. This "
      "reclassification simultaneously introduced \"hypermobility spectrum disorder\" (HSD) as a category for "
      "patients with symptomatic hypermobility who do not meet full hEDS criteria (Castori et al., 2017). "
      "Second, MCAS diagnostic criteria have evolved through multiple iterations: the Molderings et al. (2011) "
      "proposed criteria, the Valent et al. (2012) consensus, and the 2019 AAAAI position statement (Weiler, "
      "2019) each set different thresholds. "
      "The 2020 consensus update by Valent et al. further refined the distinction between primary (clonal), "
      "secondary, and idiopathic MCAS, adding stricter requirements for tryptase elevation (Valent et al., "
      "2020). Third, the 2015 Heart Rhythm Society expert consensus on POTS (Sheldon et al., 2015) formalised "
      "the diagnostic threshold of sustained heart rate increase of 30 bpm within 10 minutes of standing, "
      "without orthostatic hypotension. These evolving criteria mean that patients diagnosed in different eras "
      "may represent systematically different clinical populations.", 3)

    p("hEDS: Pre-2017 (n=31) versus Post-2017 (n=163)", "h3")
    p("Post-2017 hEDS case reports showed increased reporting of fatigue (+15.0 percentage points), "
      "tachycardia (+13.9pp), skin hyperextensibility (+12.4pp), syncope (+12.0pp), subluxations/dislocations "
      "(+8.4pp), orthostatic intolerance (+8.4pp), and mitral valve prolapse (+8.3pp), with a decrease in "
      "easy bruising (-16.2pp) (Figure 6a; Table 4).")

    p("MCAS: Pre-2017 (n=33) versus Post-2017 (n=117)", "h3")
    p("MCAS showed the most striking shifts (Figure 6b; Table 4): joint hypermobility (+16.2pp, from 0.0% "
      "to 16.2%), orthostatic intolerance (+15.4pp, from 0.0% to 15.4%), tachycardia (+20.4pp), syncope "
      "(+20.4pp), anaphylaxis (+18.0pp), neuropathy (+14.9pp), and palpitations (+14.1pp), with a decrease "
      "in urticaria (-14.8pp).")

    p("<b>Table 4.</b> Symptom frequency shifts (pp) between pre-2017 and post-2017 case reports.", "table_caption")
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

    story += add_fig("fig5_diagnostic_drift.png",
        "<b>Figure 6.</b> Pre-2017 versus post-2017 symptom frequency shifts in (a) hEDS and (b) MCAS.", s)

    p("Implications for Registry Analysis", "h3")
    p("These findings have direct methodological implications for the DICE Registry analysis in Aims 1 and 2. "
      "Patients diagnosed with hEDS under post-2017 criteria may have systematically higher rates of documented "
      "autonomic and immune symptoms. "
      "SuStaIn subtyping on DICE data must account for this cohort effect.")
    story.append(hr())

    # ── SUPPLEMENTARY ──
    p("Supplementary Analysis: Narrow versus Broad Diagnostic Definitions", "h1")

    p("Adjacent Condition Corpus", "h2")
    p("Nine additional PMC queries for umbrella and adjacent conditions yielded 683 new PMCIDs not present "
      "in the original corpus, bringing the total to 1,400 articles (688 case reports).")

    p("Results", "h2")
    # [9] POTS framing
    p_hl("The narrow versus broad comparison was only feasible for POTS, and this is a consequence of analysis "
      "design rather than a choice to focus on POTS specifically. The ideal analysis would compare narrow versus "
      "broad tiers for all three conditions; in practice, the EDS and MCAS broad tiers yielded too few "
      "non-overlapping articles (5 and 3 respectively), because JHS, HSD, and histamine intolerance barely "
      "exist as standalone case report diagnoses in the PMC Open Access literature. The POTS comparison "
      "succeeded because dysautonomia and autonomic dysfunction have substantial independent literatures (610 "
      "non-overlapping articles, 284 case reports). This asymmetry is itself informative: it suggests that POTS "
      "sits within a broader ecosystem of autonomic conditions with distinct publication traditions, while hEDS "
      "and MCAS have largely absorbed their umbrella categories in the published literature.", 9)

    # [7] Table 5 - highlighted
    p(badge(7) + "<b>Table 5.</b> <font backColor=\"" + HIGHLIGHT_BG + "\">Symptom frequencies (%): POTS narrow versus dysautonomia/OI "
      "broad-only case reports. POTS narrow includes all case reports retrieved by POTS-specific search "
      "terms (n=119). Broad-only includes case reports retrieved by independent PMC queries for adjacent "
      "autonomic conditions that do not mention POTS (n=284). All 20 symptom categories shown; dashes "
      "indicate differences &lt;1pp.</font>", "table_caption")
    story.append(make_table_highlighted(
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

    story += add_fig("fig7_narrow_vs_broad.png",
        "<b>Figure 7.</b> Symptom frequency comparison: POTS narrow vs dysautonomia/OI broad-only.", s)

    p("POTS case reports report higher frequencies across nearly every symptom category. Neuropathy is the "
      "notable exception: essentially equivalent in both groups (47.1% vs 48.2%).")

    p("The dysautonomia broad-only group is heterogeneous by design. The large "
      "differences confirm that POTS carries a distinct multi-system phenotypic signature, "
      "supporting narrow diagnostic definitions in the DICE Registry analysis.")
    story.append(hr())

    # ── LIMITATIONS ──
    p("Limitations", "h1")
    for lim in [
        "<b>Publication bias.</b> Case reports over-represent unusual presentations (Nissen &amp; Wynn, 2014).",
        "<b>PMC Open Access subset.</b> Excludes paywalled articles, introducing geographic bias (Piwowar et al., 2018).",
        "<b>Rule-based extraction.</b> Symptom F1 of 84.7% implies ~15% error.",
        "<b>Small sample sizes.</b> Pre-2017 subgroups are underpowered. Reported shifts are hypothesis-generating.",
        "<b>Confounding.</b> Pre/post-2017 comparisons cannot distinguish genuine change from ascertainment bias.",
        "<b>Broad-tier limitations.</b> EDS and MCAS broad tiers too few for comparison.",
    ]:
        p(lim)
    story.append(hr())

    # [12] Reusable pipeline
    p_hl("Generalisability: A Reusable Pipeline for Rare Disease Comorbidity Research", 12, "h1")
    p_hl("The extraction and analysis pipeline developed for this work is designed to be condition-agnostic and "
      "reusable. The core workflow, comprising PMC Open Access query construction, full-text XML retrieval via "
      "E-utilities, rule-based symptom extraction with configurable regex patterns, article type classification, "
      "and tiered diagnostic reclassification, can be applied to any set of comorbid rare conditions where the "
      "research questions concern phenotypic overlap, diagnostic drift, and ascertainment bias. The pipeline "
      "requires only three inputs to adapt to a new condition triad (or dyad, or larger comorbidity cluster): "
      "a set of narrow diagnostic search terms, a set of broader umbrella/adjacent condition terms for "
      "non-circular comparisons, and a symptom extraction schema defining the phenotypic categories of interest.", 12)
    p_hl("The analysis framework is particularly suited to conditions where diagnostic criteria have evolved over "
      "time, where clinical awareness of comorbid associations is growing, and where the published literature "
      "is primarily case reports rather than large cohort studies. "
      "The adjacent-condition query design addresses a methodological gap in the existing "
      "literature phenotyping toolkit. "
      "The complete pipeline code is "
      "available as an open-source repository to enable replication and adaptation to other rare disease "
      "comorbidity clusters.", 12)
    story.append(hr())

    # ── SUMMARY ──
    p("Summary and Implications for DICE Registry Analysis", "h1")
    for para in [
        "This preliminary literature phenotyping establishes several empirical findings that directly inform "
        "the registry-based SuStaIn analysis.",
        "The published case report literature for the triad is growing rapidly but remains sparse for the "
        "triad itself (n=18 case reports).",
        "Diagnostic terminology has not converged following the 2017 reclassification.",
        "Post-2017 case reports show systematic increases in cross-domain symptom documentation.",
        "Triad case reports present a distinctive multi-system phenotype consistent with the hypothesised "
        "multi-system high-burden subtype in Objective 1.2.",
        "The narrow versus broad comparison confirms that POTS carries a distinct phenotypic signature.",
    ]:
        p(para)

    # ML framework paragraph (from Obsidian integration, not one of the 12)
    p("Beyond informing the SuStaIn subtyping, these findings have broader implications for the machine learning "
      "framework proposed in the main thesis. The organ-specificity analysis (Table 2) directly informs feature "
      "engineering for the hierarchical graph attention network architecture. "
      "The systematic ascertainment bias documented in Figures 5 and 6 provides empirical grounding for the "
      "fairness-aware design component. The "
      "causal discovery module, integrating Granger-causal attention mechanisms, is specifically designed to "
      "distinguish genuine mechanistic relationships from ascertainment-driven "
      "correlations. Finally, the diagnostic odyssey data motivates the "
      "contrastive learning approach to subgroup identification.")
    story.append(hr())

    # ── REFERENCES (abbreviated) ──
    story.append(PageBreak())
    p("References", "h1")
    p("<i>References identical to main document; see preliminary_literature_phenotyping.pdf for full list (31 references).</i>")

    # ── BUILD ──
    doc = SimpleDocTemplate(
        OUT_PDF, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title="Annotated Edits: Preliminary Literature Phenotyping",
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
