#!/usr/bin/env python3
"""
Phase 8: Expanded analysis on the unified 1400-article corpus.

Key analyses:
1. Narrow vs broad symptom profiles (now with genuine non-overlapping broad-only articles)
2. Pre-2017 vs post-2017 diagnostic drift on expanded corpus
3. Condition co-occurrence matrix
4. Adjacent condition symptom comparison
5. Temporal trends across full corpus
"""

import json
import os
import re
import csv
import datetime
import numpy as np

BASE_DIR = "/sessions/adoring-eager-allen/mnt/mphil/triad_phenotype_mining"
PROCESSED_DIR = os.path.join(BASE_DIR, "data/processed")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
FIG_DIR = os.path.join(OUTPUT_DIR, "figures")
TABLE_DIR = os.path.join(OUTPUT_DIR, "tables")

os.makedirs(FIG_DIR, exist_ok=True)
os.makedirs(TABLE_DIR, exist_ok=True)

# Symptom list
SYMPTOM_LIST = [
    "joint_hypermobility", "subluxations_dislocations", "chronic_pain",
    "orthostatic_intolerance", "tachycardia", "syncope",
    "flushing", "urticaria", "anaphylaxis",
    "skin_hyperextensibility", "easy_bruising", "fatigue",
    "gi_symptoms", "headache_migraine", "neuropathy",
    "chiari", "brain_fog", "mitral_valve_prolapse",
    "palpitations", "medication_sensitivity"
]


def load_data():
    """Load unified tiers and merged extractions."""
    with open(os.path.join(PROCESSED_DIR, "unified_tiered_classification.json")) as f:
        tiers = json.load(f)
    tier_map = {t["pmcid"]: t for t in tiers}

    with open(os.path.join(PROCESSED_DIR, "merged_extractions.json")) as f:
        extractions = json.load(f)
    ext_map = {e["pmcid"]: e for e in extractions}

    # Merge
    articles = []
    for pmcid, tier in tier_map.items():
        ext = ext_map.get(pmcid, {})
        entry = {**ext, **tier}

        # Pub year
        pubdate = ext.get("pubdate", "")
        m = re.search(r"(\d{4})", pubdate)
        entry["pub_year"] = int(m.group(1)) if m else None

        # Criteria era
        if entry["pub_year"]:
            if entry["pub_year"] < 2017:
                entry["criteria_era"] = "pre-2017"
            elif entry["pub_year"] == 2017:
                entry["criteria_era"] = "2017"
            else:
                entry["criteria_era"] = "post-2017"
        else:
            entry["criteria_era"] = "unknown"

        articles.append(entry)

    return articles


def symptom_freq(articles_subset, symptom_list=SYMPTOM_LIST):
    """Compute symptom frequencies for a subset of articles."""
    n = len(articles_subset)
    if n == 0:
        return {s: 0 for s in symptom_list}
    freqs = {}
    for s in symptom_list:
        count = sum(1 for a in articles_subset if s in a.get("symptoms_detected", []))
        freqs[s] = count / n * 100
    return freqs


def analysis_1_narrow_vs_broad(articles):
    """Compare symptom profiles: narrow vs broad-only for each condition."""
    print("\n" + "="*60)
    print("ANALYSIS 1: NARROW vs BROAD-ONLY SYMPTOM PROFILES")
    print("="*60)

    # Filter to case reports only
    case_reports = [a for a in articles if a.get("article_type") == "case_report"]
    print(f"Case reports in corpus: {len(case_reports)}")

    results = {}

    for condition, narrow_key, broad_key, label in [
        ("POTS", "pots_narrow", "pots_broad", "POTS vs Dysautonomia/OI"),
        ("EDS", "eds_narrow", "eds_broad", "hEDS vs JHS/HSD"),
        ("MCAS", "mcas_narrow", "mcas_broad", "MCAS vs Histamine/Mastocytosis"),
    ]:
        narrow = [a for a in case_reports if a[narrow_key]]
        broad_only = [a for a in case_reports if a[broad_key] and not a[narrow_key]]

        print(f"\n  {label}:")
        print(f"    Narrow ({condition}): {len(narrow)} case reports")
        print(f"    Broad-only: {len(broad_only)} case reports")

        if len(broad_only) < 3:
            print(f"    ** Too few broad-only articles for meaningful comparison")
            continue

        narrow_freq = symptom_freq(narrow)
        broad_freq = symptom_freq(broad_only)

        print(f"\n    {'Symptom':<30} {'Narrow %':>10} {'Broad-only %':>12} {'Diff':>8}")
        print(f"    {'-'*62}")

        diffs = []
        for s in SYMPTOM_LIST:
            nf = narrow_freq[s]
            bf = broad_freq[s]
            diff = nf - bf
            diffs.append((s, nf, bf, diff))
            if abs(diff) > 5:  # Only show >5% differences
                print(f"    {s:<30} {nf:>9.1f}% {bf:>11.1f}% {diff:>+7.1f}%")

        results[condition] = {
            "narrow_n": len(narrow),
            "broad_only_n": len(broad_only),
            "narrow_freq": narrow_freq,
            "broad_only_freq": broad_freq,
            "diffs": diffs
        }

    return results


def analysis_2_pre_post_2017(articles):
    """Pre-2017 vs post-2017 symptom profiles on expanded corpus."""
    print("\n" + "="*60)
    print("ANALYSIS 2: PRE-2017 vs POST-2017 DIAGNOSTIC DRIFT (EXPANDED)")
    print("="*60)

    case_reports = [a for a in articles if a.get("article_type") == "case_report"]

    results = {}

    for condition, key, label in [
        ("EDS_narrow", "eds_narrow", "hEDS/EDS-III (narrow)"),
        ("POTS_narrow", "pots_narrow", "POTS (narrow)"),
        ("POTS_broad", "pots_broad", "POTS + dysautonomia (broad)"),
        ("MCAS_narrow", "mcas_narrow", "MCAS (narrow)"),
    ]:
        subset = [a for a in case_reports if a[key]]
        pre = [a for a in subset if a["criteria_era"] == "pre-2017"]
        post = [a for a in subset if a["criteria_era"] == "post-2017"]

        print(f"\n  {label}:")
        print(f"    Pre-2017: {len(pre)} case reports")
        print(f"    Post-2017: {len(post)} case reports")

        if len(pre) < 5 or len(post) < 5:
            print(f"    ** Insufficient data for comparison")
            continue

        pre_freq = symptom_freq(pre)
        post_freq = symptom_freq(post)

        print(f"\n    {'Symptom':<30} {'Pre-2017 %':>10} {'Post-2017 %':>12} {'Shift':>8}")
        print(f"    {'-'*62}")

        diffs = []
        for s in SYMPTOM_LIST:
            pref = pre_freq[s]
            postf = post_freq[s]
            diff = postf - pref
            diffs.append((s, pref, postf, diff))
            if abs(diff) > 10:
                print(f"    {s:<30} {pref:>9.1f}% {postf:>11.1f}% {diff:>+7.1f}%")

        results[condition] = {
            "pre_n": len(pre),
            "post_n": len(post),
            "pre_freq": pre_freq,
            "post_freq": post_freq,
            "diffs": diffs
        }

    return results


def analysis_3_co_occurrence(articles):
    """Condition co-occurrence matrix across full corpus."""
    print("\n" + "="*60)
    print("ANALYSIS 3: CONDITION CO-OCCURRENCE MATRIX")
    print("="*60)

    conditions = [
        ("EDS (narrow)", "eds_narrow"),
        ("POTS (narrow)", "pots_narrow"),
        ("MCAS (narrow)", "mcas_narrow"),
        ("Dysautonomia", "dysautonomia_mentioned"),
        ("OI", "orthostatic_intolerance_mentioned"),
        ("Vasovagal", "vasovagal_mentioned"),
        ("JHS", "jhs_mentioned"),
        ("HSD", "hsd_mentioned"),
        ("Mastocytosis", "mastocytosis_mentioned"),
        ("Hist. intol.", "histamine_intolerance_mentioned"),
    ]

    case_reports = [a for a in articles if a.get("article_type") == "case_report"]
    n = len(case_reports)

    print(f"\n  Co-occurrence in {n} case reports:")
    print(f"\n  {'':20}", end="")
    for label, _ in conditions:
        print(f"{label[:8]:>10}", end="")
    print()

    matrix = []
    for label1, key1 in conditions:
        row = []
        print(f"  {label1:20}", end="")
        for label2, key2 in conditions:
            count = sum(1 for a in case_reports if a.get(key1) and a.get(key2))
            row.append(count)
            print(f"{count:>10}", end="")
        print()
        matrix.append(row)

    return matrix, [l for l, _ in conditions]


def analysis_4_adjacent_symptom_profiles(articles):
    """Compare symptom profiles across adjacent conditions."""
    print("\n" + "="*60)
    print("ANALYSIS 4: ADJACENT CONDITION SYMPTOM PROFILES")
    print("="*60)

    case_reports = [a for a in articles if a.get("article_type") == "case_report"]

    groups = {
        "POTS only (no EDS/MCAS)": [a for a in case_reports if a["pots_narrow"] and not a["eds_narrow"] and not a["mcas_narrow"]],
        "Dysautonomia only (no POTS/EDS/MCAS)": [a for a in case_reports if a.get("dysautonomia_mentioned") and not a["pots_narrow"] and not a["eds_narrow"] and not a["mcas_narrow"]],
        "OI only (no POTS/EDS/MCAS)": [a for a in case_reports if a.get("orthostatic_intolerance_mentioned") and not a["pots_narrow"] and not a["eds_narrow"] and not a["mcas_narrow"]],
        "Vasovagal only (no POTS/EDS/MCAS)": [a for a in case_reports if a.get("vasovagal_mentioned") and not a["pots_narrow"] and not a["eds_narrow"] and not a["mcas_narrow"]],
        "hEDS only (no POTS/MCAS)": [a for a in case_reports if a["eds_narrow"] and not a["pots_narrow"] and not a["mcas_narrow"]],
        "MCAS only (no EDS/POTS)": [a for a in case_reports if a["mcas_narrow"] and not a["eds_narrow"] and not a["pots_narrow"]],
        "Triad (narrow)": [a for a in case_reports if a["triad_narrow"]],
    }

    print(f"\n  Group sizes:")
    for name, grp in groups.items():
        print(f"    {name}: {len(grp)}")

    # Compute frequencies
    all_freqs = {}
    for name, grp in groups.items():
        if len(grp) >= 5:
            all_freqs[name] = symptom_freq(grp)

    # Print comparison for key symptoms
    key_symptoms = ["joint_hypermobility", "tachycardia", "syncope", "fatigue",
                    "gi_symptoms", "chronic_pain", "flushing", "anaphylaxis",
                    "headache_migraine", "palpitations", "neuropathy", "brain_fog"]

    print(f"\n  {'Symptom':<28}", end="")
    for name in all_freqs:
        short = name[:12]
        print(f"{short:>14}", end="")
    print()
    print(f"  {'-'*28}", end="")
    for _ in all_freqs:
        print(f"{'':>14}", end="")
    print()

    for s in key_symptoms:
        print(f"  {s:<28}", end="")
        for name in all_freqs:
            print(f"{all_freqs[name][s]:>13.1f}%", end="")
        print()

    return all_freqs, groups


def analysis_5_temporal_trends(articles):
    """Publication volume by year across conditions."""
    print("\n" + "="*60)
    print("ANALYSIS 5: TEMPORAL TRENDS (EXPANDED CORPUS)")
    print("="*60)

    case_reports = [a for a in articles if a.get("article_type") == "case_report" and a.get("pub_year")]

    # By year and condition
    years = sorted(set(a["pub_year"] for a in case_reports if a["pub_year"]))
    if not years:
        print("  No year data available")
        return

    print(f"\n  {'Year':<8}", end="")
    for label in ["EDS", "POTS", "Dysaut", "MCAS", "OI", "Triad"]:
        print(f"{label:>8}", end="")
    print(f"{'Total':>8}")

    for year in years:
        yr_articles = [a for a in case_reports if a["pub_year"] == year]
        eds = sum(1 for a in yr_articles if a["eds_narrow"])
        pots = sum(1 for a in yr_articles if a["pots_narrow"])
        dysaut = sum(1 for a in yr_articles if a.get("dysautonomia_mentioned") and not a["pots_narrow"])
        mcas = sum(1 for a in yr_articles if a["mcas_narrow"])
        oi = sum(1 for a in yr_articles if a.get("orthostatic_intolerance_mentioned") and not a["pots_narrow"])
        triad = sum(1 for a in yr_articles if a["triad_narrow"])
        total = len(yr_articles)
        print(f"  {year:<8}{eds:>8}{pots:>8}{dysaut:>8}{mcas:>8}{oi:>8}{triad:>8}{total:>8}")


def generate_figures(articles):
    """Generate publication-quality figures."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
    except ImportError:
        print("matplotlib not available, skipping figures")
        return

    case_reports = [a for a in articles if a.get("article_type") == "case_report"]

    # Figure 9: Narrow vs Broad symptom heatmap (POTS focus)
    pots_narrow = [a for a in case_reports if a["pots_narrow"]]
    pots_broad_only = [a for a in case_reports if a["pots_broad"] and not a["pots_narrow"]]

    if len(pots_broad_only) >= 5:
        fig, axes = plt.subplots(1, 2, figsize=(16, 8))

        narrow_freq = symptom_freq(pots_narrow)
        broad_freq = symptom_freq(pots_broad_only)

        symptoms_sorted = sorted(SYMPTOM_LIST, key=lambda s: narrow_freq[s], reverse=True)
        labels = [s.replace("_", " ").title() for s in symptoms_sorted]

        # Bar chart comparison
        x = np.arange(len(symptoms_sorted))
        width = 0.35

        axes[0].barh(x - width/2, [narrow_freq[s] for s in symptoms_sorted],
                     width, label=f"POTS narrow (n={len(pots_narrow)})", color="#2196F3", alpha=0.8)
        axes[0].barh(x + width/2, [broad_freq[s] for s in symptoms_sorted],
                     width, label=f"Dysautonomia/OI broad-only (n={len(pots_broad_only)})", color="#FF9800", alpha=0.8)
        axes[0].set_yticks(x)
        axes[0].set_yticklabels(labels, fontsize=9)
        axes[0].set_xlabel("Frequency (%)")
        axes[0].set_title("Symptom Frequency: POTS (Narrow) vs Dysautonomia/OI (Broad-only)")
        axes[0].legend(loc="lower right", fontsize=9)
        axes[0].invert_yaxis()

        # Difference plot
        diffs = [narrow_freq[s] - broad_freq[s] for s in symptoms_sorted]
        colors = ["#4CAF50" if d > 0 else "#F44336" for d in diffs]
        axes[1].barh(x, diffs, color=colors, alpha=0.8)
        axes[1].set_yticks(x)
        axes[1].set_yticklabels(labels, fontsize=9)
        axes[1].set_xlabel("Difference (POTS narrow - Broad-only) %")
        axes[1].set_title("Symptom Profile Difference")
        axes[1].axvline(x=0, color="black", linewidth=0.5)
        axes[1].invert_yaxis()

        plt.tight_layout()
        fig.savefig(os.path.join(FIG_DIR, "fig9_narrow_vs_broad_pots_expanded.png"), dpi=150, bbox_inches="tight")
        plt.close()
        print("Saved fig9_narrow_vs_broad_pots_expanded.png")

    # Figure 10: Multi-condition symptom comparison
    groups = {
        "POTS only": [a for a in case_reports if a["pots_narrow"] and not a["eds_narrow"] and not a["mcas_narrow"]],
        "Dysautonomia\n(not POTS)": [a for a in case_reports if a.get("dysautonomia_mentioned") and not a["pots_narrow"] and not a["eds_narrow"] and not a["mcas_narrow"]],
        "hEDS only": [a for a in case_reports if a["eds_narrow"] and not a["pots_narrow"] and not a["mcas_narrow"]],
        "MCAS only": [a for a in case_reports if a["mcas_narrow"] and not a["eds_narrow"] and not a["pots_narrow"]],
        "Triad": [a for a in case_reports if a["triad_narrow"]],
    }

    valid_groups = {k: v for k, v in groups.items() if len(v) >= 5}

    if valid_groups:
        key_symptoms = ["joint_hypermobility", "tachycardia", "syncope", "fatigue",
                        "gi_symptoms", "chronic_pain", "flushing", "anaphylaxis",
                        "headache_migraine", "palpitations", "neuropathy"]

        fig, ax = plt.subplots(figsize=(14, 8))

        freqs_matrix = []
        group_labels = []
        for name, grp in valid_groups.items():
            freq = symptom_freq(grp, key_symptoms)
            freqs_matrix.append([freq[s] for s in key_symptoms])
            group_labels.append(f"{name}\n(n={len(grp)})")

        data = np.array(freqs_matrix)
        im = ax.imshow(data, aspect="auto", cmap="YlOrRd", vmin=0, vmax=100)

        ax.set_xticks(range(len(key_symptoms)))
        ax.set_xticklabels([s.replace("_", " ").title() for s in key_symptoms],
                          rotation=45, ha="right", fontsize=9)
        ax.set_yticks(range(len(group_labels)))
        ax.set_yticklabels(group_labels, fontsize=10)

        # Annotate cells
        for i in range(len(group_labels)):
            for j in range(len(key_symptoms)):
                val = data[i, j]
                color = "white" if val > 50 else "black"
                ax.text(j, i, f"{val:.0f}%", ha="center", va="center", color=color, fontsize=8)

        plt.colorbar(im, label="Frequency (%)", shrink=0.8)
        ax.set_title("Symptom Frequency Heatmap: Condition-Specific Case Reports", fontsize=12, pad=10)
        plt.tight_layout()
        fig.savefig(os.path.join(FIG_DIR, "fig10_multi_condition_heatmap.png"), dpi=150, bbox_inches="tight")
        plt.close()
        print("Saved fig10_multi_condition_heatmap.png")

    # Figure 11: Temporal publication volume
    years_data = {}
    for a in case_reports:
        yr = a.get("pub_year")
        if yr and 2005 <= yr <= 2026:
            if yr not in years_data:
                years_data[yr] = {"eds": 0, "pots": 0, "dysaut": 0, "mcas": 0, "total": 0}
            years_data[yr]["total"] += 1
            if a["eds_narrow"]:
                years_data[yr]["eds"] += 1
            if a["pots_narrow"]:
                years_data[yr]["pots"] += 1
            if a.get("dysautonomia_mentioned") and not a["pots_narrow"]:
                years_data[yr]["dysaut"] += 1
            if a["mcas_narrow"]:
                years_data[yr]["mcas"] += 1

    if years_data:
        fig, ax = plt.subplots(figsize=(12, 6))
        years = sorted(years_data.keys())

        for key, label, color in [
            ("eds", "hEDS", "#E91E63"),
            ("pots", "POTS", "#2196F3"),
            ("dysaut", "Dysautonomia (not POTS)", "#FF9800"),
            ("mcas", "MCAS", "#9C27B0"),
        ]:
            vals = [years_data.get(y, {}).get(key, 0) for y in years]
            ax.plot(years, vals, marker="o", label=label, color=color, linewidth=2, markersize=4)

        ax.axvline(x=2017, color="red", linestyle="--", alpha=0.5, label="2017 hEDS criteria")
        ax.set_xlabel("Publication Year")
        ax.set_ylabel("Number of Case Reports")
        ax.set_title("Case Report Publication Trends: Expanded Corpus (n=1400)")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        fig.savefig(os.path.join(FIG_DIR, "fig11_expanded_temporal_trends.png"), dpi=150, bbox_inches="tight")
        plt.close()
        print("Saved fig11_expanded_temporal_trends.png")

    # Figure 12: Pre vs Post 2017 symptom shift (expanded)
    for condition, key, label, color in [
        ("POTS_broad", "pots_broad", "POTS + Dysautonomia (Broad)", "#2196F3"),
    ]:
        subset = [a for a in case_reports if a[key]]
        pre = [a for a in subset if a["criteria_era"] == "pre-2017"]
        post = [a for a in subset if a["criteria_era"] == "post-2017"]

        if len(pre) >= 5 and len(post) >= 5:
            fig, ax = plt.subplots(figsize=(14, 8))
            pre_freq = symptom_freq(pre)
            post_freq = symptom_freq(post)

            symptoms_sorted = sorted(SYMPTOM_LIST, key=lambda s: abs(post_freq[s] - pre_freq[s]), reverse=True)
            labels = [s.replace("_", " ").title() for s in symptoms_sorted]

            x = np.arange(len(symptoms_sorted))
            width = 0.35

            ax.barh(x - width/2, [pre_freq[s] for s in symptoms_sorted],
                    width, label=f"Pre-2017 (n={len(pre)})", color="#90CAF9", alpha=0.9)
            ax.barh(x + width/2, [post_freq[s] for s in symptoms_sorted],
                    width, label=f"Post-2017 (n={len(post)})", color="#1565C0", alpha=0.9)
            ax.set_yticks(x)
            ax.set_yticklabels(labels, fontsize=9)
            ax.set_xlabel("Frequency (%)")
            ax.set_title(f"Symptom Shift: {label}\nPre-2017 vs Post-2017")
            ax.legend(loc="lower right")
            ax.invert_yaxis()
            plt.tight_layout()
            fig.savefig(os.path.join(FIG_DIR, f"fig12_pre_post_2017_{condition.lower()}.png"), dpi=150, bbox_inches="tight")
            plt.close()
            print(f"Saved fig12_pre_post_2017_{condition.lower()}.png")


def save_tables(articles, narrow_broad_results, drift_results):
    """Save analysis tables as CSVs."""

    case_reports = [a for a in articles if a.get("article_type") == "case_report"]

    # Table: Narrow vs broad symptom comparison
    rows = []
    for condition, data in narrow_broad_results.items():
        for s, nf, bf, diff in data["diffs"]:
            rows.append({
                "condition": condition,
                "symptom": s,
                "narrow_pct": round(nf, 1),
                "broad_only_pct": round(bf, 1),
                "difference_pct": round(diff, 1),
                "narrow_n": data["narrow_n"],
                "broad_only_n": data["broad_only_n"],
            })
    csv_path = os.path.join(TABLE_DIR, "narrow_vs_broad_expanded.csv")
    if rows:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"Saved {csv_path}")

    # Table: Pre/post 2017 drift
    rows = []
    for condition, data in drift_results.items():
        for s, pref, postf, diff in data["diffs"]:
            rows.append({
                "condition": condition,
                "symptom": s,
                "pre_2017_pct": round(pref, 1),
                "post_2017_pct": round(postf, 1),
                "shift_pct": round(diff, 1),
                "pre_n": data["pre_n"],
                "post_n": data["post_n"],
            })
    csv_path = os.path.join(TABLE_DIR, "diagnostic_drift_expanded.csv")
    if rows:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"Saved {csv_path}")

    # Table: Full corpus summary
    summary = {
        "total_articles": len(articles),
        "case_reports": len(case_reports),
        "clinical_studies": sum(1 for a in articles if a.get("article_type") == "clinical_study"),
        "reviews": sum(1 for a in articles if a.get("article_type") == "review_or_study"),
        "animal_studies": sum(1 for a in articles if a.get("article_type") == "animal_study"),
        "original_corpus": sum(1 for a in articles if a.get("corpus_source") == "original"),
        "adjacent_corpus": sum(1 for a in articles if a.get("corpus_source") == "adjacent"),
        "eds_narrow": sum(1 for a in articles if a.get("eds_narrow")),
        "pots_narrow": sum(1 for a in articles if a.get("pots_narrow")),
        "pots_broad_only": sum(1 for a in articles if a.get("pots_broad") and not a.get("pots_narrow")),
        "mcas_narrow": sum(1 for a in articles if a.get("mcas_narrow")),
        "triad_narrow": sum(1 for a in articles if a.get("triad_narrow")),
        "triad_broad": sum(1 for a in articles if a.get("triad_broad")),
        "pre_2017": sum(1 for a in articles if a.get("criteria_era") == "pre-2017"),
        "post_2017": sum(1 for a in articles if a.get("criteria_era") == "post-2017"),
    }
    csv_path = os.path.join(TABLE_DIR, "corpus_summary_expanded.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value"])
        for k, v in summary.items():
            writer.writerow([k, v])
    print(f"Saved {csv_path}")


def main():
    print("Loading unified corpus...")
    articles = load_data()
    print(f"Loaded {len(articles)} articles")

    nb_results = analysis_1_narrow_vs_broad(articles)
    drift_results = analysis_2_pre_post_2017(articles)
    analysis_3_co_occurrence(articles)
    analysis_4_adjacent_symptom_profiles(articles)
    analysis_5_temporal_trends(articles)

    print("\nGenerating figures...")
    generate_figures(articles)

    print("\nSaving tables...")
    save_tables(articles, nb_results, drift_results)

    print("\nDone.")


if __name__ == "__main__":
    main()
