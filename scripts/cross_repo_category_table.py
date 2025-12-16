#!/usr/bin/env python3
# cross_repo_category_table.py
#
# Build a cross-repo table of category percentages, restricted to QC-PASS repos.
#
# Usage:
#   python scripts/cross_repo_category_table.py \
#       --qc analysis/qc_summary.csv \
#       --out analysis/cross_repo_category_percentages.csv
#
# Assumes that for each PASS repo there is a file:
#   <base>_category_percentages.csv
# where <base> is taken from the "base" column in qc_summary.csv
# (e.g. data_bug/<repo>/<repo>_bug_commits_classified).

import os
import argparse
import pandas as pd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qc", required=True, help="Path to qc_summary.csv")
    ap.add_argument("--out", required=True, help="Output CSV path for cross-repo category percentages")
    args = ap.parse_args()

    qc = pd.read_csv(args.qc)

    # Expect columns: repo, status, base, ...
    print("QC columns:", list(qc.columns))

    # Detect columns
    col_status = "status"
    col_base   = "base"
    col_repo   = "repo"
    for c in qc.columns:
        cl = c.lower()
        if "status" in cl:
            col_status = c
        if "base" in cl:
            col_base = c
        if cl == "repo":
            col_repo = c

    qc_pass = qc[qc[col_status].str.upper() == "PASS"].copy()
    print(f"PASS repos found in QC: {len(qc_pass)}")

    all_rows = []

    for _, row in qc_pass.iterrows():
        base = str(row[col_base])
        repo_name = str(row[col_repo])

        cat_file = base + "_category_percentages.csv"

        if not os.path.exists(cat_file):
            print(f"[WARN] Category percentages file not found for repo {repo_name}: {cat_file}")
            continue

        df = pd.read_csv(cat_file)

        # Try to detect category + percent columns
        col_cat = None
        col_pct = None
        for c in df.columns:
            cl = c.lower()
            if "category" in cl:
                col_cat = c
            if "percent" in cl:
                col_pct = c

        if col_cat is None or col_pct is None:
            print(f"[WARN] Could not find category/percent columns in {cat_file}")
            continue

        tmp = df[[col_cat, col_pct]].copy()
        tmp.rename(columns={col_cat: "bug_category", col_pct: "percent"}, inplace=True)
        tmp["repo"] = repo_name

        all_rows.append(tmp)

    if not all_rows:
        raise SystemExit("No per-repo category tables were collected. Check that *_category_percentages.csv exist for PASS repos.")

    out_df = pd.concat(all_rows, ignore_index=True)
    out_df = out_df[["repo", "bug_category", "percent"]]

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    out_df.to_csv(args.out, index=False)
    print(f"Saved cross-repo category table to: {args.out}")

if __name__ == "__main__":
    main()
