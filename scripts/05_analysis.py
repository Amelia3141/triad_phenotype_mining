#!/usr/bin/env python3
"""
Phase 4: Analyse temporal patterns, diagnostic drift, phenotypic clustering.

Analyses:
1. Temporal trends in case report publication
2. Diagnostic terminology drift (pre/post 2017 criteria)
3. Symptom frequency distributions
4. Co-occurrence patterns (triad analysis)
5. Age/sex distributions by condition
6. Criteria citation patterns over time
"""

import csv
import json
import os
import re
from collections import Counter, defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

BASE_DIR = "/sessions/adoring-eager-allen/mnt/mphil/triad_phenotype_mining"
PROCESSED_DIR = os.path.join(BASE_DIR, "data/processed")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
FIG_DIR = os.path.join(OUTPUT_DIR, "figures")
TABLE_DIR = os.path.join(OUTPUT_DIR, "tables")

os.makedirs(FIG_DIR, exist_ok=True)
os.makedirs(TABLE_DIR, exist_ok=True)

# Load included dataset
with open(os.path.join(PROCESSED_DIR, "triad_phenotype_dataset_v2_included.csv"), "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    all_data = list(reader)

# Filter to case reports and clinical studies with human patients
case_reports = [r for r in all_data if r["article_type_inferred"] == "case_report"]
human_studies = [r for r in all_data if r["article_type_inferred"] in ("case_report", "clinical_study", "review_or_study")]

print(f"Total included: {len(all_data)}")
print(f"Case reports: {len(case_reports)}")
print(f"Human studies (incl. clinical): {len(human_studies)}")


def save_table(data, headers, filename):
    """Save a table as CSV."""
    path = os.path.join(TABLE_DIR, filename)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(data)
    print(f"  Saved: {path}")


# ============================================================
# 1. TEMPORAL TRENDS
# ============================================================
print("\n" + "="*60)
print("1. TEMPORAL TRENDS")
print("="*60)

year_counts = Counter()
year_by_condition = defaultdict(lambda: {"EDS": 0, "POTS": 0, "MCAS": 0, "triad": 0})

for r in human_studies:
    y = r.get("pub_year")
    if y and y.isdigit():
        y = int(y)
        year_counts[y] += 1
        if r["has_eds"] == "True": year_by_condition[y]["EDS"] += 1
        if r["has_pots"] == "True": year_by_condition[y]["POTS"] += 1
        if r["has_mcas"] == "True": year_by_condition[y]["MCAS"] += 1
        if r["triad_present"] == "True": year_by_condition[y]["triad"] += 1

years = sorted(year_counts.keys())
print(f"Year range: {min(years)}-{max(years)}")

# Figure 1: Publication trends
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))

# Panel A: Total publications
ax1.bar(years, [year_counts[y] for y in years], color="#4C72B0", alpha=0.8)
ax1.axvline(x=2017, color="red", linestyle="--", alpha=0.7, label="2017 hEDS criteria")
ax1.axvline(x=2011, color="orange", linestyle="--", alpha=0.7, label="2011 POTS consensus")
ax1.set_xlabel("Year")
ax1.set_ylabel("Number of case reports/studies")
ax1.set_title("A. Publication volume over time (PMC OA subset)")
ax1.legend()

# Panel B: By condition
for cond, color in [("EDS", "#4C72B0"), ("POTS", "#DD8452"), ("MCAS", "#55A868"), ("triad", "#C44E52")]:
    vals = [year_by_condition[y][cond] for y in years]
    ax2.plot(years, vals, "o-", color=color, label=cond, markersize=4)

ax2.axvline(x=2017, color="red", linestyle="--", alpha=0.5)
ax2.axvline(x=2011, color="orange", linestyle="--", alpha=0.5)
ax2.set_xlabel("Year")
ax2.set_ylabel("Number of publications")
ax2.set_title("B. Publications by condition")
ax2.legend()

plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "fig1_temporal_trends.png"), dpi=150, bbox_inches="tight")
plt.close()
print("  Fig 1 saved.")


# ============================================================
# 2. DIAGNOSTIC TERMINOLOGY DRIFT
# ============================================================
print("\n" + "="*60)
print("2. DIAGNOSTIC TERMINOLOGY DRIFT")
print("="*60)

# Track terminology over time
term_by_year = defaultdict(lambda: Counter())
eds_terms = ["EDS type III", "EDS hypermobility type", "hEDS", "hypermobile EDS", "JHS", "HSD"]
pots_terms = ["POTS", "postural tachycardia syndrome", "dysautonomia"]
mcas_terms = ["MCAS", "MCAD", "mast cell activation syndrome"]

for r in human_studies:
    y = r.get("pub_year")
    if not y or not y.isdigit():
        continue
    y = int(y)
    terms = r.get("terminology_used", "").split("; ")
    for t in terms:
        t = t.strip()
        if t:
            term_by_year[y][t] += 1

# Pre vs post 2017 for EDS terminology
pre_2017_eds = Counter()
post_2017_eds = Counter()
for y, counts in term_by_year.items():
    for term in eds_terms:
        if y < 2017:
            pre_2017_eds[term] += counts.get(term, 0)
        else:
            post_2017_eds[term] += counts.get(term, 0)

print("\nEDS terminology shift:")
print(f"  {'Term':<30} {'Pre-2017':>10} {'Post-2017':>10} {'Shift':>10}")
drift_table = []
for term in eds_terms:
    pre = pre_2017_eds.get(term, 0)
    post = post_2017_eds.get(term, 0)
    shift = "+" if post > pre else "-" if post < pre else "="
    print(f"  {term:<30} {pre:>10} {post:>10} {shift:>10}")
    drift_table.append([term, pre, post, shift])

save_table(drift_table, ["Term", "Pre-2017 count", "Post-2017 count", "Direction"], "terminology_drift_eds.csv")

# Figure 2: Terminology drift
fig, axes = plt.subplots(1, 3, figsize=(18, 6))

# EDS terms over time
for term, color in zip(eds_terms, plt.cm.tab10.colors):
    vals = [term_by_year[y].get(term, 0) for y in years]
    if sum(vals) > 2:  # Only plot if used more than twice
        axes[0].plot(years, vals, "o-", label=term, markersize=3, color=color)
axes[0].axvline(x=2017, color="red", linestyle="--", alpha=0.5)
axes[0].set_title("EDS terminology over time")
axes[0].set_xlabel("Year")
axes[0].set_ylabel("Frequency")
axes[0].legend(fontsize=8)

# POTS terms
for term, color in zip(pots_terms, ["#DD8452", "#8172B3", "#937860"]):
    vals = [term_by_year[y].get(term, 0) for y in years]
    if sum(vals) > 2:
        axes[1].plot(years, vals, "o-", label=term, markersize=3, color=color)
axes[1].axvline(x=2011, color="orange", linestyle="--", alpha=0.5)
axes[1].set_title("POTS terminology over time")
axes[1].set_xlabel("Year")
axes[1].legend(fontsize=8)

# MCAS terms
for term, color in zip(mcas_terms, ["#55A868", "#C44E52", "#8C8C8C"]):
    vals = [term_by_year[y].get(term, 0) for y in years]
    if sum(vals) > 2:
        axes[2].plot(years, vals, "o-", label=term, markersize=3, color=color)
axes[2].set_title("MCAS terminology over time")
axes[2].set_xlabel("Year")
axes[2].legend(fontsize=8)

plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "fig2_terminology_drift.png"), dpi=150, bbox_inches="tight")
plt.close()
print("  Fig 2 saved.")


# ============================================================
# 3. SYMPTOM FREQUENCY DISTRIBUTIONS
# ============================================================
print("\n" + "="*60)
print("3. SYMPTOM FREQUENCY DISTRIBUTIONS")
print("="*60)

# Overall symptom frequencies
symptom_counts = Counter()
symptom_by_condition = {"EDS": Counter(), "POTS": Counter(), "MCAS": Counter(), "triad": Counter()}

for r in case_reports:
    symptoms = [s.strip() for s in r.get("symptoms_detected", "").split(";") if s.strip()]
    for s in symptoms:
        symptom_counts[s] += 1
        if r["has_eds"] == "True": symptom_by_condition["EDS"][s] += 1
        if r["has_pots"] == "True": symptom_by_condition["POTS"][s] += 1
        if r["has_mcas"] == "True": symptom_by_condition["MCAS"][s] += 1
        if r["triad_present"] == "True": symptom_by_condition["triad"][s] += 1

# Normalise to proportions
n_eds_cr = sum(1 for r in case_reports if r["has_eds"] == "True")
n_pots_cr = sum(1 for r in case_reports if r["has_pots"] == "True")
n_mcas_cr = sum(1 for r in case_reports if r["has_mcas"] == "True")
n_triad_cr = sum(1 for r in case_reports if r["triad_present"] == "True")

print(f"\nCase reports by condition: EDS={n_eds_cr}, POTS={n_pots_cr}, MCAS={n_mcas_cr}, triad={n_triad_cr}")

top_symptoms = symptom_counts.most_common(20)
print(f"\nTop 20 symptoms (case reports, n={len(case_reports)}):")
symptom_table = []
for s, c in top_symptoms:
    pct = c / len(case_reports) * 100
    eds_pct = symptom_by_condition["EDS"][s] / n_eds_cr * 100 if n_eds_cr else 0
    pots_pct = symptom_by_condition["POTS"][s] / n_pots_cr * 100 if n_pots_cr else 0
    mcas_pct = symptom_by_condition["MCAS"][s] / n_mcas_cr * 100 if n_mcas_cr else 0
    print(f"  {s:<35} {c:>4} ({pct:5.1f}%)  EDS:{eds_pct:5.1f}%  POTS:{pots_pct:5.1f}%  MCAS:{mcas_pct:5.1f}%")
    symptom_table.append([s, c, f"{pct:.1f}", f"{eds_pct:.1f}", f"{pots_pct:.1f}", f"{mcas_pct:.1f}"])

save_table(symptom_table,
           ["Symptom", "Total count", "Overall %", "EDS %", "POTS %", "MCAS %"],
           "symptom_frequencies.csv")

# Figure 3: Symptom frequency heatmap
fig, ax = plt.subplots(figsize=(14, 10))

symptoms_for_heatmap = [s for s, _ in top_symptoms[:18]]
conditions = ["EDS", "POTS", "MCAS", "triad"]
n_by_cond = {"EDS": n_eds_cr, "POTS": n_pots_cr, "MCAS": n_mcas_cr, "triad": n_triad_cr}

heatmap_data = []
for s in symptoms_for_heatmap:
    row = []
    for c in conditions:
        n = n_by_cond[c]
        pct = symptom_by_condition[c][s] / n * 100 if n else 0
        row.append(pct)
    heatmap_data.append(row)

heatmap_array = np.array(heatmap_data)
im = ax.imshow(heatmap_array, cmap="YlOrRd", aspect="auto")

ax.set_xticks(range(len(conditions)))
ax.set_xticklabels([f"{c}\n(n={n_by_cond[c]})" for c in conditions])
ax.set_yticks(range(len(symptoms_for_heatmap)))
ax.set_yticklabels([s.replace("_", " ") for s in symptoms_for_heatmap])

# Add text annotations
for i in range(len(symptoms_for_heatmap)):
    for j in range(len(conditions)):
        val = heatmap_array[i, j]
        color = "white" if val > 40 else "black"
        ax.text(j, i, f"{val:.0f}%", ha="center", va="center", color=color, fontsize=9)

plt.colorbar(im, label="Frequency (%)")
ax.set_title("Symptom frequency by condition (case reports)")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "fig3_symptom_heatmap.png"), dpi=150, bbox_inches="tight")
plt.close()
print("  Fig 3 saved.")


# ============================================================
# 4. CO-OCCURRENCE PATTERNS
# ============================================================
print("\n" + "="*60)
print("4. CO-OCCURRENCE PATTERNS")
print("="*60)

# Venn-diagram data
eds_only = sum(1 for r in human_studies if r["has_eds"]=="True" and r["has_pots"]!="True" and r["has_mcas"]!="True")
pots_only = sum(1 for r in human_studies if r["has_pots"]=="True" and r["has_eds"]!="True" and r["has_mcas"]!="True")
mcas_only = sum(1 for r in human_studies if r["has_mcas"]=="True" and r["has_eds"]!="True" and r["has_pots"]!="True")
eds_pots = sum(1 for r in human_studies if r["has_eds"]=="True" and r["has_pots"]=="True" and r["has_mcas"]!="True")
eds_mcas = sum(1 for r in human_studies if r["has_eds"]=="True" and r["has_mcas"]=="True" and r["has_pots"]!="True")
pots_mcas = sum(1 for r in human_studies if r["has_pots"]=="True" and r["has_mcas"]=="True" and r["has_eds"]!="True")
all_three = sum(1 for r in human_studies if r["triad_present"]=="True")

print(f"  EDS only: {eds_only}")
print(f"  POTS only: {pots_only}")
print(f"  MCAS only: {mcas_only}")
print(f"  EDS+POTS: {eds_pots}")
print(f"  EDS+MCAS: {eds_mcas}")
print(f"  POTS+MCAS: {pots_mcas}")
print(f"  All three (triad): {all_three}")

# Temporal trend of triad recognition
triad_by_year = Counter()
for r in human_studies:
    if r["triad_present"] == "True":
        y = r.get("pub_year", "")
        if y.isdigit():
            triad_by_year[int(y)] += 1

print(f"\nTriad publications by year:")
for y in sorted(triad_by_year.keys()):
    print(f"  {y}: {triad_by_year[y]}")


# ============================================================
# 5. AGE/SEX DISTRIBUTIONS
# ============================================================
print("\n" + "="*60)
print("5. AGE/SEX DISTRIBUTIONS")
print("="*60)

# Age distribution by condition
ages_by_condition = {"EDS": [], "POTS": [], "MCAS": [], "All": []}
for r in case_reports:
    age = r.get("age_midpoint_for_analysis", "")
    if age:
        try:
            age = float(age)
        except:
            continue
        ages_by_condition["All"].append(age)
        if r["has_eds"] == "True": ages_by_condition["EDS"].append(age)
        if r["has_pots"] == "True": ages_by_condition["POTS"].append(age)
        if r["has_mcas"] == "True": ages_by_condition["MCAS"].append(age)

print(f"\nAge statistics (case reports):")
for cond, ages in ages_by_condition.items():
    if ages:
        ages_arr = np.array(ages)
        print(f"  {cond} (n={len(ages)}): mean={ages_arr.mean():.1f}, median={np.median(ages_arr):.1f}, "
              f"IQR=[{np.percentile(ages_arr, 25):.0f}-{np.percentile(ages_arr, 75):.0f}]")

# Sex distribution
sex_by_condition = defaultdict(Counter)
for r in case_reports:
    sex = r.get("sex", "")
    if sex:
        sex_by_condition["All"][sex] += 1
        if r["has_eds"] == "True": sex_by_condition["EDS"][sex] += 1
        if r["has_pots"] == "True": sex_by_condition["POTS"][sex] += 1
        if r["has_mcas"] == "True": sex_by_condition["MCAS"][sex] += 1

print(f"\nSex distribution (case reports):")
for cond in ["All", "EDS", "POTS", "MCAS"]:
    total = sum(sex_by_condition[cond].values())
    f_pct = sex_by_condition[cond].get("female", 0) / total * 100 if total else 0
    m_pct = sex_by_condition[cond].get("male", 0) / total * 100 if total else 0
    print(f"  {cond}: female={f_pct:.1f}%, male={m_pct:.1f}% (n={total})")

# Figure 4: Age and sex distributions
fig, axes = plt.subplots(1, 3, figsize=(16, 5))

# Age histograms by condition
for cond, color in [("EDS", "#4C72B0"), ("POTS", "#DD8452"), ("MCAS", "#55A868")]:
    if ages_by_condition[cond]:
        axes[0].hist(ages_by_condition[cond], bins=range(0, 95, 5), alpha=0.5, label=f"{cond} (n={len(ages_by_condition[cond])})", color=color)
axes[0].set_xlabel("Age at presentation")
axes[0].set_ylabel("Count")
axes[0].set_title("Age distribution by condition")
axes[0].legend()

# Sex distribution
conds = ["EDS", "POTS", "MCAS"]
f_pcts = [sex_by_condition[c].get("female", 0) / max(sum(sex_by_condition[c].values()), 1) * 100 for c in conds]
m_pcts = [sex_by_condition[c].get("male", 0) / max(sum(sex_by_condition[c].values()), 1) * 100 for c in conds]

x = np.arange(len(conds))
axes[1].bar(x - 0.2, f_pcts, 0.4, label="Female", color="#E377C2")
axes[1].bar(x + 0.2, m_pcts, 0.4, label="Male", color="#7F7F7F")
axes[1].set_xticks(x)
axes[1].set_xticklabels(conds)
axes[1].set_ylabel("Percentage")
axes[1].set_title("Sex distribution by condition")
axes[1].legend()

# Age groups stacked
age_groups_ordered = ["infant (<1)", "early childhood (1-4)", "childhood (5-11)", "adolescent (12-17)",
                      "young adult (18-29)", "adult (30-44)", "middle aged (45-59)",
                      "older adult (60-74)", "elderly (75+)"]
group_counts = {c: Counter() for c in conds}
for r in case_reports:
    ag = r.get("age_group", "")
    if ag:
        for c in conds:
            if r[f"has_{c.lower()}"] == "True":
                group_counts[c][ag] += 1

bottom = np.zeros(len(conds))
colors = plt.cm.viridis(np.linspace(0, 1, len(age_groups_ordered)))
for i, ag in enumerate(age_groups_ordered):
    vals = [group_counts[c].get(ag, 0) for c in conds]
    axes[2].bar(conds, vals, bottom=bottom, label=ag, color=colors[i])
    bottom += vals

axes[2].set_ylabel("Count")
axes[2].set_title("Age group distribution")
axes[2].legend(fontsize=6, loc="upper right")

plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "fig4_demographics.png"), dpi=150, bbox_inches="tight")
plt.close()
print("  Fig 4 saved.")


# ============================================================
# 6. CRITERIA CITATION PATTERNS
# ============================================================
print("\n" + "="*60)
print("6. CRITERIA CITATION PATTERNS")
print("="*60)

criteria_by_year = defaultdict(Counter)
for r in human_studies:
    y = r.get("pub_year", "")
    if not y or not y.isdigit():
        continue
    y = int(y)
    criteria = [c.strip() for c in r.get("diagnostic_criteria_cited", "").split(";") if c.strip()]
    for c in criteria:
        criteria_by_year[y][c] += 1

# Summary
all_criteria = Counter()
for y_counts in criteria_by_year.values():
    all_criteria += y_counts

print(f"\nCriteria cited across all years:")
for c, n in all_criteria.most_common():
    print(f"  {c}: {n}")

# Pre vs post 2017
pre = Counter()
post = Counter()
for y, counts in criteria_by_year.items():
    for c, n in counts.items():
        if y < 2017:
            pre[c] += n
        else:
            post[c] += n

print(f"\nPre-2017 criteria citations:")
for c, n in pre.most_common():
    print(f"  {c}: {n}")

print(f"\nPost-2017 criteria citations:")
for c, n in post.most_common():
    print(f"  {c}: {n}")

# Figure 5: Criteria citation trends
fig, ax = plt.subplots(figsize=(12, 6))
criteria_names = ["2017 international classification", "Beighton", "Villefranche", "Brighton", "MCAS consensus criteria"]
for crit, color in zip(criteria_names, plt.cm.Set2.colors):
    vals = [criteria_by_year[y].get(crit, 0) for y in years]
    if sum(vals) > 0:
        ax.plot(years, vals, "o-", label=crit, markersize=3, color=color)

ax.axvline(x=2017, color="red", linestyle="--", alpha=0.5, label="2017 criteria published")
ax.set_xlabel("Year")
ax.set_ylabel("Number of citations")
ax.set_title("Diagnostic criteria cited in case reports over time")
ax.legend(fontsize=8)
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "fig5_criteria_trends.png"), dpi=150, bbox_inches="tight")
plt.close()
print("  Fig 5 saved.")


# ============================================================
# SAVE ANALYSIS SUMMARY
# ============================================================
summary = {
    "analysis_date": "2026-04-16",
    "corpus": {
        "total_articles": len(all_data),
        "case_reports": len(case_reports),
        "human_studies": len(human_studies),
        "year_range": f"{min(years)}-{max(years)}"
    },
    "condition_distribution": {
        "EDS_articles": sum(1 for r in human_studies if r["has_eds"]=="True"),
        "POTS_articles": sum(1 for r in human_studies if r["has_pots"]=="True"),
        "MCAS_articles": sum(1 for r in human_studies if r["has_mcas"]=="True"),
        "triad_articles": all_three,
    },
    "demographics_case_reports": {
        cond: {
            "n": len(ages),
            "mean_age": float(np.mean(ages)) if ages else None,
            "median_age": float(np.median(ages)) if ages else None,
        } for cond, ages in ages_by_condition.items()
    },
    "terminology_drift": {
        "pre_2017_top_eds_term": pre_2017_eds.most_common(1)[0][0] if pre_2017_eds else None,
        "post_2017_top_eds_term": post_2017_eds.most_common(1)[0][0] if post_2017_eds else None,
    },
    "co_occurrence": {
        "eds_only": eds_only, "pots_only": pots_only, "mcas_only": mcas_only,
        "eds_pots": eds_pots, "eds_mcas": eds_mcas, "pots_mcas": pots_mcas,
        "triad": all_three,
    }
}

with open(os.path.join(OUTPUT_DIR, "analysis_summary.json"), "w") as f:
    json.dump(summary, f, indent=2)

print(f"\nAnalysis complete. Outputs in {OUTPUT_DIR}")
