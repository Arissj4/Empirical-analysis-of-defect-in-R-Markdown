#!/usr/bin/env python3
# summary_touch_stats.py
#
# Usage:
#   python scripts/summary_touch_stats.py \
#       --in-r analysis/cross_repo_r_touch_by_category.csv \
#       --in-rmd analysis/cross_repo_rmd_touch_by_category.csv \
#       --out analysis/touch_stats_by_category.csv

import argparse
import pandas as pd

def agg_stats(df, value_col, prefix):
    g = (
        df.groupby("bug_category")[value_col]
          .agg(["mean", "median", "min", "max", "std", "count"])
          .reset_index()
    )
    g = g.rename(columns={
        "mean": f"{prefix}_mean",
        "median": f"{prefix}_median",
        "min": f"{prefix}_min",
        "max": f"{prefix}_max",
        "std": f"{prefix}_std",
        "count": f"{prefix}_count",
    })
    return g

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-r", required=True, help="cross_repo_r_touch_by_category.csv")
    ap.add_argument("--in-rmd", required=True, help="cross_repo_rmd_touch_by_category.csv")
    ap.add_argument("--out", required=True, help="output CSV with stats per category")
    args = ap.parse_args()

    r_df = pd.read_csv(args.in_r)
    rmd_df = pd.read_csv(args.in_rmd)

    # Expect columns: repo, bug_category, touches_r_% / touches_rmd_%
    print("R columns:", r_df.columns.tolist())
    print("Rmd columns:", rmd_df.columns.tolist())

    # Detect value cols
    col_r = None
    for c in r_df.columns:
        if "touches_r_" in c.lower():
            col_r = c
            break
    if col_r is None:
        raise SystemExit("Could not find touches_r_% column in R file")

    col_rmd = None
    for c in rmd_df.columns:
        if "touches_rmd_" in c.lower():
            col_rmd = c
            break
    if col_rmd is None:
        raise SystemExit("Could not find touches_rmd_% column in Rmd file")

    stats_r = agg_stats(r_df, col_r, "r")
    stats_rmd = agg_stats(rmd_df, col_rmd, "rmd")

    # Merge on bug_category
    merged = pd.merge(stats_r, stats_rmd, on="bug_category", how="outer")

    # Optional: sort by, e.g., rmd_mean descending
    merged = merged.sort_values("bug_category")

    merged.to_csv(args.out, index=False)
    print(f"Saved touch stats by category to {args.out}")
    print(merged)

if __name__ == "__main__":
    main()
