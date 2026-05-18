#!/usr/bin/env python3
"""
Generate publication-quality figures for the preliminary literature phenotyping write-up.

Figure 1: PRISMA-style corpus flow diagram (text-based, rendered as figure)
Figure 2: Temporal publication trends by condition
Figure 3: Diagnostic terminology drift pre/post 2017
Figure 4: Symptom frequency heatmap across condition groups (hEDS, POTS, MCAS, Triad)
Figure 5: Pre-2017 vs Post-2017 symptom shift (butterfly/diverging bar chart)
Figure 6: Condition co-occurrence Euler/upset-style visualisation
Figure 7: Narrow vs broad POTS symptom comparison
"""

import json
import os
import re
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch
import seaborn as sns

# Style
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans"],
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "axes.spines.top": False,
    "axes.spines.right": False,
})

BASE_DIR = "/sessions/adoring-eager-allen/mnt/mphil/triad_phenotype_mining"
PROCESSED_DIR = os.path.join(BASE_DIR, "data/processed")
FIG_DIR = os.path.join(BASE_DIR, "outputs/paper_figures")
os.makedirs(FIG_DIR, exist_ok=True)

# Colour palette
C_EDS = "#E91E63"      # pink/magenta
C_POTS = "#1565C0"     # deep blue
C_MCAS = "#7B1FA2"     # purple
C_TRIAD = "#FF6F00"    # amber
C_DYSAUT = "#FF9800"   # orange
C_PRE = "#90CAF9"      # light blue
C_POST = "#1565C0"     # deep blue
C_NARROW = "#1565C0"
C_BROAD = "#FF9800"

SYMPTOM_LIST = [
    "joint_hypermobility", "subluxations_dislocations", "chronic_pain",
    "orthostatic_intolerance", "tachycardia", "syncope",
    "flushing", "urticaria", "anaphylaxis",
    "skin_hyperextensibility", "easy_bruising", "fatigue",
    "gi_symptoms", "headache_migraine", "neuropathy",
    "chiari", "brain_fog", "mitral_valve_prolapse",
    "palpitations", "medication_sensitivity"
]

SYMPTOM_LABELS = {
    "joint_hypermobility": "Joint hypermobility",
    "subluxations_dislocations": "Subluxations/dislocations",
    "chronic_pain": "Chronic pain",
    "orthostatic_intolerance": "Orthostatic intolerance",
    "tachycardia": "Tachycardia",
    "syncope": "Syncope/presyncope",
    "flushing": "Flushing",
    "urticaria": "Urticaria",
    "anaphylaxis": "Anaphylaxis",
    "skin_hyperextensibility": "Skin hyperextensibility",
    "easy_bruising": "Easy bruising",
    "fatigue": "Fatigue",
    "gi_symptoms": "GI symptoms",
    "headache_migraine": "Headache/migraine",
    "neuropathy": "Neuropathy",
    "chiari": "Chiari malformation",
    "brain_fog": "Brain fog",
    "mitral_valve_prolapse": "Mitral valve prolapse",
    "palpitations": "Palpitations",
    "medication_sensitivity": "Medication sensitivity",
}


def load_data():
    with open(os.path.join(PROCESSED_DIR, "unified_tiered_classification.json")) as f:
        tiers = json.load(f)
    with open(os.path.join(PROCESSED_DIR, "merged_extractions.json")) as f:
        extractions = json.load(f)
    ext_map = {e["pmcid"]: e for e in extractions}
    tier_map = {t["pmcid"]: t for t in tiers}

    articles = []
    for pmcid, t in tier_map.items():
        e = ext_map.get(pmcid, {})
        m = re.search(r"(\d{4})", e.get("pubdate", ""))
        yr = int(m.group(1)) if m else None
        articles.append({**e, **t, "pub_year": yr})
    return articles


def freq(subset, symptom):
    if not subset:
        return 0.0
    return sum(1 for a in subset if symptom in a.get("symptoms_detected", [])) / len(subset) * 100


def fig1_corpus_flow(articles):
    """PRISMA-style flow diagram with proper spacing."""
    fig, ax = plt.subplots(figsize=(10, 16))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 20)
    ax.axis("off")

    def box(x, y, w, h, text, color="#E3F2FD", ec="#1565C0", fontsize=9):
        rect = FancyBboxPatch((x - w/2, y - h/2), w, h,
                              boxstyle="round,pad=0.15", facecolor=color, edgecolor=ec, linewidth=1.3)
        ax.add_patch(rect)
        ax.text(x, y, text, ha="center", va="center", fontsize=fontsize, wrap=True,
                multialignment="center", linespacing=1.4)

    def arrow(x1, y1, x2, y2):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                     arrowprops=dict(arrowstyle="-|>", color="#333", lw=1.3))

    # Centre column x
    cx = 5.0

    # ── Row 1: Queries (y=19) ──
    box(cx, 19, 8, 1.0,
        "PMC Open Access queries (2026-04-16)\n"
        "EDS/hEDS (n=336) | POTS (n=144) | MCAS (n=240) | Triad (n=18)",
        color="#E8EAF6", ec="#3F51B5", fontsize=9.5)

    arrow(cx, 18.5, cx, 17.6)

    # ── Row 2: Combined (y=17) ──
    box(cx, 17, 6, 0.9,
        "Combined corpus after deduplication\nn = 717 unique articles")

    arrow(cx, 16.55, cx, 15.6)

    # ── Row 3: Article type (y=15) ──
    box(cx, 15, 6, 0.9,
        "Article type classification\nCase reports: 376 | Clinical studies: 160\n"
        "Animal studies: 93 | Reviews: 88")

    # Exclusion box right of row 3
    box(9.5, 15, 2.8, 0.9,
        "Excluded from\nprimary analysis:\nn = 341 non-case reports",
        color="#FFEBEE", ec="#C62828", fontsize=8)
    ax.annotate("", xy=(8.1, 15), xytext=(7.0, 15),
                arrowprops=dict(arrowstyle="-|>", color="#C62828", lw=1))

    arrow(cx, 14.55, cx, 13.6)

    # ── Row 4: Condition reclassification (y=13) ──
    box(cx, 13, 6.5, 0.9,
        "Condition reclassification (full-text)\n"
        "EDS subtyping: hEDS/HSD=132, vascular=147, classical=10\n"
        "Mastocytosis-only identified | EDS negation detection")

    # Exclusion box right of row 4 - branch from reclassification box
    box(9.8, 12, 2.2, 1.1,
        "vEDS: 147\nClassical: 10\nOther: 3\nExcluded: 80\nMasto-only",
        color="#FFEBEE", ec="#C62828", fontsize=8)
    ax.annotate("", xy=(8.7, 12.4), xytext=(7.25, 12.7),
                arrowprops=dict(arrowstyle="-|>", color="#C62828", lw=1))

    arrow(cx, 12.55, cx, 11.6)

    # ── Row 5: Primary analytical dataset (y=11) ──
    box(cx, 11, 6.5, 0.9,
        "Primary analytical dataset (case reports)\n"
        "hEDS: 203 | POTS: 82 | MCAS: 161 | Triad: 18",
        color="#E8F5E9", ec="#2E7D32")

    arrow(cx, 10.55, cx, 9.6)

    # ── Row 6: Analyses (y=9) ──
    box(cx, 9, 6.5, 0.9,
        "Analyses: symptom extraction (20 categories, F1=84.7%)\n"
        "Diagnostic terminology drift | Pre/post 2017 comparison\n"
        "Criteria citation patterns | Co-occurrence mapping")

    arrow(cx, 8.55, cx, 7.6)

    # ── Row 7: Adjacent condition queries (y=7) ──
    box(cx, 7, 7.5, 0.9,
        "Adjacent condition queries (independent)\n"
        "Dysautonomia, OI, autonomic dysfunction, vasovagal syncope,\n"
        "JHS, HSD, histamine intolerance, HAT, idiopathic anaphylaxis",
        color="#FFF3E0", ec="#E65100")

    arrow(cx, 6.55, cx, 5.6)

    # ── Row 8: Expanded corpus (y=5) ──
    box(cx, 5, 6, 0.9,
        "Expanded corpus: 1,400 articles (688 case reports)\n"
        "Original: 717 + Adjacent: 683 new PMCIDs",
        color="#F3E5F5", ec="#7B1FA2")

    arrow(cx, 4.55, cx, 3.6)

    # ── Row 9: Narrow vs broad (y=3) ──
    box(cx, 3, 6, 0.8,
        "Narrow vs broad comparison\n"
        "POTS narrow (n=119) vs dysautonomia broad-only (n=284)",
        color="#F3E5F5", ec="#7B1FA2")

    fig.savefig(os.path.join(FIG_DIR, "fig1_corpus_flow.png"), bbox_inches="tight", pad_inches=0.3)
    plt.close()
    print("Saved fig1_corpus_flow.png")


def fig2_temporal_trends(articles):
    """Publication trends by condition and year."""
    orig_cr = [a for a in articles if a.get("corpus_source") == "original"
               and a.get("article_type") == "case_report" and a.get("pub_year")]

    years = sorted(set(a["pub_year"] for a in orig_cr if 2004 <= a["pub_year"] <= 2026))

    eds_vals, pots_vals, mcas_vals, total_vals = [], [], [], []
    for y in years:
        yr_a = [a for a in orig_cr if a["pub_year"] == y]
        eds_vals.append(sum(1 for a in yr_a if a.get("eds_narrow") and not a.get("has_non_heds_eds") and not a.get("eds_excluded")))
        pots_vals.append(sum(1 for a in yr_a if a.get("pots_narrow")))
        mcas_vals.append(sum(1 for a in yr_a if a.get("mcas_narrow") and not a.get("has_mastocytosis_only")))
        total_vals.append(len(yr_a))

    fig, ax = plt.subplots(figsize=(10, 5))

    ax.plot(years, eds_vals, "o-", color=C_EDS, label="hEDS/HSD", linewidth=2, markersize=4)
    ax.plot(years, pots_vals, "s-", color=C_POTS, label="POTS", linewidth=2, markersize=4)
    ax.plot(years, mcas_vals, "^-", color=C_MCAS, label="MCAS", linewidth=2, markersize=4)
    ax.bar(years, total_vals, color="#E0E0E0", alpha=0.4, width=0.8, zorder=0, label="All case reports")

    ax.axvline(x=2017, color="#C62828", linestyle="--", alpha=0.6, linewidth=1)
    ax.text(2017.2, max(total_vals) * 0.92, "2017 hEDS\ncriteria", fontsize=8, color="#C62828", va="top")

    ax.set_xlabel("Publication year")
    ax.set_ylabel("Number of case reports")
    ax.legend(loc="upper left", frameon=True, framealpha=0.9)
    ax.set_xlim(2003.5, 2026.5)
    ax.grid(axis="y", alpha=0.2)

    fig.savefig(os.path.join(FIG_DIR, "fig2_temporal_trends.png"))
    plt.close()
    print("Saved fig2_temporal_trends.png")


def fig3_terminology_drift(articles):
    """Stacked bar showing terminology usage pre vs post 2017."""
    orig_cr = [a for a in articles if a.get("corpus_source") == "original"
               and a.get("article_type") == "case_report"
               and a.get("eds_narrow")
               and not a.get("has_non_heds_eds") and not a.get("eds_excluded")]

    pre = [a for a in orig_cr if a.get("pub_year") and a["pub_year"] < 2017]
    post = [a for a in orig_cr if a.get("pub_year") and a["pub_year"] > 2017]

    terms = ["EDS type III", "EDS hypermobility type", "hypermobile EDS", "hEDS", "JHS", "HSD"]
    term_labels = ["EDS type III", "EDS hypermobility\ntype", "Hypermobile\nEDS", "hEDS", "JHS", "HSD"]

    pre_pcts = []
    post_pcts = []
    for t in terms:
        pre_pcts.append(sum(1 for a in pre if t in a.get("terminology_used", [])) / len(pre) * 100 if pre else 0)
        post_pcts.append(sum(1 for a in post if t in a.get("terminology_used", [])) / len(post) * 100 if post else 0)

    x = np.arange(len(terms))
    width = 0.35

    fig, ax = plt.subplots(figsize=(9, 5))
    bars1 = ax.bar(x - width/2, pre_pcts, width, label=f"Pre-2017 (n={len(pre)})", color=C_PRE, edgecolor="white")
    bars2 = ax.bar(x + width/2, post_pcts, width, label=f"Post-2017 (n={len(post)})", color=C_POST, edgecolor="white")

    # Value labels
    for bar in bars1:
        if bar.get_height() > 2:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                    f"{bar.get_height():.0f}%", ha="center", va="bottom", fontsize=8, color="#555")
    for bar in bars2:
        if bar.get_height() > 2:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                    f"{bar.get_height():.0f}%", ha="center", va="bottom", fontsize=8, color="#555")

    ax.set_xticks(x)
    ax.set_xticklabels(term_labels, fontsize=9)
    ax.set_ylabel("Proportion of hEDS case reports (%)")
    ax.legend(frameon=True, framealpha=0.9)
    ax.grid(axis="y", alpha=0.2)

    fig.savefig(os.path.join(FIG_DIR, "fig3_terminology_drift.png"))
    plt.close()
    print("Saved fig3_terminology_drift.png")


def fig4_symptom_heatmap(articles):
    """Heatmap of symptom frequencies across condition groups."""
    orig_cr = [a for a in articles if a.get("corpus_source") == "original"
               and a.get("article_type") == "case_report"]

    groups = {
        "hEDS only\n(n={n})": [a for a in orig_cr if a.get("eds_narrow") and not a.get("has_non_heds_eds")
                                and not a.get("eds_excluded") and not a.get("pots_narrow") and not a.get("mcas_narrow")],
        "POTS only\n(n={n})": [a for a in orig_cr if a.get("pots_narrow") and not a.get("eds_narrow") and not a.get("mcas_narrow")],
        "MCAS only\n(n={n})": [a for a in orig_cr if a.get("mcas_narrow") and not a.get("has_mastocytosis_only")
                                and not a.get("eds_narrow") and not a.get("pots_narrow")],
        "Triad\n(n={n})": [a for a in orig_cr if a.get("triad_narrow")],
    }

    # Fill in n
    group_labels = []
    group_data = []
    for label_tmpl, grp in groups.items():
        label = label_tmpl.format(n=len(grp))
        group_labels.append(label)
        group_data.append(grp)

    # Symptom subset (drop low-information ones)
    symp_subset = [
        "joint_hypermobility", "subluxations_dislocations", "chronic_pain",
        "skin_hyperextensibility", "easy_bruising",
        "tachycardia", "syncope", "orthostatic_intolerance", "palpitations",
        "flushing", "urticaria", "anaphylaxis",
        "fatigue", "gi_symptoms", "headache_migraine", "neuropathy",
        "brain_fog", "mitral_valve_prolapse", "medication_sensitivity",
    ]

    matrix = np.zeros((len(group_data), len(symp_subset)))
    for i, grp in enumerate(group_data):
        for j, s in enumerate(symp_subset):
            matrix[i, j] = freq(grp, s)

    fig, ax = plt.subplots(figsize=(14, 5))
    im = ax.imshow(matrix, aspect="auto", cmap="YlOrRd", vmin=0, vmax=100)

    ax.set_xticks(range(len(symp_subset)))
    ax.set_xticklabels([SYMPTOM_LABELS.get(s, s) for s in symp_subset], rotation=50, ha="right", fontsize=8.5)
    ax.set_yticks(range(len(group_labels)))
    ax.set_yticklabels(group_labels, fontsize=9)

    for i in range(len(group_labels)):
        for j in range(len(symp_subset)):
            val = matrix[i, j]
            color = "white" if val > 55 else "black"
            ax.text(j, i, f"{val:.0f}", ha="center", va="center", fontsize=7.5, color=color)

    cbar = plt.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.set_label("Frequency (%)", fontsize=9)

    fig.savefig(os.path.join(FIG_DIR, "fig4_symptom_heatmap.png"))
    plt.close()
    print("Saved fig4_symptom_heatmap.png")


def fig5_diagnostic_drift(articles):
    """Butterfly chart: pre vs post 2017 symptom shifts for hEDS and MCAS."""
    orig_cr = [a for a in articles if a.get("corpus_source") == "original"
               and a.get("article_type") == "case_report"]

    conditions = [
        ("hEDS", [a for a in orig_cr if a.get("eds_narrow") and not a.get("has_non_heds_eds") and not a.get("eds_excluded")]),
        ("MCAS", [a for a in orig_cr if a.get("mcas_narrow") and not a.get("has_mastocytosis_only")]),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(14, 7), sharey=True)

    symp_subset = [
        "fatigue", "tachycardia", "skin_hyperextensibility", "syncope",
        "subluxations_dislocations", "orthostatic_intolerance", "mitral_valve_prolapse",
        "chronic_pain", "gi_symptoms", "headache_migraine", "joint_hypermobility",
        "neuropathy", "palpitations", "flushing", "anaphylaxis",
        "brain_fog", "urticaria", "easy_bruising",
    ]

    for idx, (cond_name, subset) in enumerate(conditions):
        ax = axes[idx]
        pre = [a for a in subset if a.get("pub_year") and a["pub_year"] < 2017]
        post = [a for a in subset if a.get("pub_year") and a["pub_year"] > 2017]

        diffs = []
        for s in symp_subset:
            pre_f = freq(pre, s)
            post_f = freq(post, s)
            diffs.append((s, post_f - pre_f, pre_f, post_f))

        # Sort by absolute difference
        diffs.sort(key=lambda x: abs(x[1]), reverse=True)

        labels = [SYMPTOM_LABELS.get(d[0], d[0]) for d in diffs]
        values = [d[1] for d in diffs]
        colors = [C_POST if v > 0 else "#E57373" for v in values]

        y = np.arange(len(diffs))
        ax.barh(y, values, color=colors, alpha=0.85, height=0.7)
        ax.set_yticks(y)
        if idx == 0:
            ax.set_yticklabels(labels, fontsize=8.5)
        ax.axvline(x=0, color="black", linewidth=0.5)
        ax.set_xlabel("Change (percentage points)")
        ax.set_title(f"{cond_name}\npre-2017 (n={len(pre)}) vs post-2017 (n={len(post)})", fontsize=10)
        ax.invert_yaxis()
        ax.grid(axis="x", alpha=0.2)

        # Annotate largest shifts
        for i, (s, diff, pre_f, post_f) in enumerate(diffs):
            if abs(diff) > 8:
                side = "left" if diff < 0 else "right"
                offset = -1.5 if diff < 0 else 1.5
                ax.text(diff + offset, i, f"{diff:+.0f}pp", va="center",
                        ha=side, fontsize=7, color="#333")

    plt.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "fig5_diagnostic_drift.png"))
    plt.close()
    print("Saved fig5_diagnostic_drift.png")


def fig6_co_occurrence(articles):
    """Co-occurrence bar chart for original case reports."""
    orig_cr = [a for a in articles if a.get("corpus_source") == "original"
               and a.get("article_type") == "case_report"]

    categories = [
        ("EDS only", sum(1 for a in orig_cr if a.get("eds_narrow") and not a.get("pots_narrow") and not a.get("mcas_narrow"))),
        ("POTS only", sum(1 for a in orig_cr if a.get("pots_narrow") and not a.get("eds_narrow") and not a.get("mcas_narrow"))),
        ("MCAS only", sum(1 for a in orig_cr if a.get("mcas_narrow") and not a.get("eds_narrow") and not a.get("pots_narrow"))),
        ("EDS + POTS", sum(1 for a in orig_cr if a.get("eds_narrow") and a.get("pots_narrow") and not a.get("mcas_narrow"))),
        ("POTS + MCAS", sum(1 for a in orig_cr if a.get("pots_narrow") and a.get("mcas_narrow") and not a.get("eds_narrow"))),
        ("EDS + MCAS", sum(1 for a in orig_cr if a.get("eds_narrow") and a.get("mcas_narrow") and not a.get("pots_narrow"))),
        ("Triad", sum(1 for a in orig_cr if a.get("triad_narrow"))),
    ]

    labels = [c[0] for c in categories]
    values = [c[1] for c in categories]
    colors = [C_EDS, C_POTS, C_MCAS, "#5C6BC0", "#AB47BC", "#EC407A", C_TRIAD]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.bar(labels, values, color=colors, edgecolor="white", width=0.65)

    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2,
                str(val), ha="center", va="bottom", fontsize=9, fontweight="bold")

    ax.set_ylabel("Number of case reports")
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9)
    ax.grid(axis="y", alpha=0.2)

    fig.savefig(os.path.join(FIG_DIR, "fig6_co_occurrence.png"))
    plt.close()
    print("Saved fig6_co_occurrence.png")


def fig7_narrow_vs_broad(articles):
    """Paired bar chart: POTS narrow vs dysautonomia broad-only."""
    all_cr = [a for a in articles if a.get("article_type") == "case_report"]
    pots_narrow = [a for a in all_cr if a["pots_narrow"]]
    broad_only = [a for a in all_cr if a["pots_broad"] and not a["pots_narrow"]]

    symp_subset = [
        "tachycardia", "fatigue", "orthostatic_intolerance", "palpitations",
        "syncope", "headache_migraine", "joint_hypermobility", "chronic_pain",
        "gi_symptoms", "neuropathy", "flushing", "brain_fog",
        "skin_hyperextensibility", "easy_bruising", "anaphylaxis",
    ]

    narrow_f = [freq(pots_narrow, s) for s in symp_subset]
    broad_f = [freq(broad_only, s) for s in symp_subset]
    labels = [SYMPTOM_LABELS.get(s, s) for s in symp_subset]

    # Sort by difference
    order = sorted(range(len(symp_subset)), key=lambda i: narrow_f[i] - broad_f[i], reverse=True)
    narrow_f = [narrow_f[i] for i in order]
    broad_f = [broad_f[i] for i in order]
    labels = [labels[i] for i in order]

    y = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(y - width/2, narrow_f, width, label=f"POTS narrow (n={len(pots_narrow)})",
            color=C_NARROW, alpha=0.85)
    ax.barh(y + width/2, broad_f, width, label=f"Dysautonomia/OI broad-only (n={len(broad_only)})",
            color=C_BROAD, alpha=0.85)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Frequency (%)")
    ax.legend(loc="lower right", frameon=True, framealpha=0.9)
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.2)

    fig.savefig(os.path.join(FIG_DIR, "fig7_narrow_vs_broad.png"))
    plt.close()
    print("Saved fig7_narrow_vs_broad.png")


def main():
    print("Loading data...")
    articles = load_data()
    print(f"Loaded {len(articles)} articles")

    fig1_corpus_flow(articles)
    fig2_temporal_trends(articles)
    fig3_terminology_drift(articles)
    fig4_symptom_heatmap(articles)
    fig5_diagnostic_drift(articles)
    fig6_co_occurrence(articles)
    fig7_narrow_vs_broad(articles)

    print("\nAll figures saved to", FIG_DIR)


if __name__ == "__main__":
    main()
