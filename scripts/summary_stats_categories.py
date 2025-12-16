#!/usr/bin/env python3
# summary_stats_categories.py
#
# Usage:
#   python scripts/summary_stats_categories.py \
#       --in analysis/cross_repo_category_percentages.csv \
#       --out analysis/category_stats.csv

import argparse
import pandas as pd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="cross_repo_category_percentages.csv")
    ap.add_argument("--out", dest="out", required=True, help="output CSV with stats per category")
    args = ap.parse_args()

    df = pd.read_csv(args.inp)

    # Expect columns: repo, bug_category, percent
    # If names differ, tweak here
    print("Columns:", df.columns.tolist())

    stats = (
        df.groupby("bug_category")["percent"]
          .agg(["mean", "median", "min", "max", "std", "count"])
          .reset_index()
    )

    # Sort by mean descending
    stats = stats.sort_values("mean", ascending=False)

    stats.to_csv(args.out, index=False)
    print(f"Saved category stats to {args.out}")
    print(stats)

if __name__ == "__main__":
    main()
