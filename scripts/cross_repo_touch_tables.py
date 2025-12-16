#!/usr/bin/env python3
# cross_repo_touch_tables.py
#
# Usage:
#   python scripts/cross_repo_touch_tables.py \
#       --qc analysis/qc_summary.csv \
#       --out-r analysis/cross_repo_r_touch_by_category.csv \
#       --out-rmd analysis/cross_repo_rmd_touch_by_category.csv
#
# For each PASS repo in qc_summary.csv, this script expects files:
#   <base>_r_touch_by_category.csv
#   <base>_rmd_touch_by_category.csv
# where <base> is the "base" column in qc_summary.csv
# (e.g. data_bug/<repo>/<repo>_bug_commits_classified)

import os
import argparse
import pandas as pd

def detect_col(df, substr):
    for c in df.columns:
        if substr.lower() in c.lower():
            return c
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qc", required=True, help="Path to qc_summary.csv")
    ap.add_argument("--out-r", required=True, help="Output CSV for cross-repo R-touch rates")
    ap.add_argument("--out-rmd", required=True, help="Output CSV for cross-repo Rmd-touch rates")
    args = ap.parse_args()

    qc = pd.read_csv(args.qc)
    print("QC columns:", list(qc.columns))

    # detect columns
    col_status = detect_col(qc, "status") or "status"
    col_base   = detect_col(qc, "base")   or "base"
    col_repo   = "repo"
    for c in qc.columns:
        if c.lower() == "repo":
            col_repo = c
            break

    qc_pass = qc[qc[col_status].astype(str).str.upper() == "PASS"].copy()
    print(f"PASS repos: {len(qc_pass)}")

    rows_r = []
    rows_rmd = []

    for _, row in qc_pass.iterrows():
        base = str(row[col_base])
        repo_name = str(row[col_repo])

        # R-touch file (classified summary)
        r_file = base + "_r_touch_by_category.csv"
        # Rmd-touch file
        rmd_file = base + "_rmd_touch_by_category.csv"

        if not os.path.exists(r_file):
            print(f"[WARN] R-touch file not found for {repo_name}: {r_file}")
        else:
            df_r = pd.read_csv(r_file)
            col_cat = detect_col(df_r, "category")
            col_pct = detect_col(df_r, "touches_r")
            if col_cat is None or col_pct is None:
                print(f"[WARN] Missing category/touches_r column in {r_file}")
            else:
                tmp = df_r[[col_cat, col_pct]].copy()
                tmp.rename(columns={col_cat: "bug_category", col_pct: "touches_r_%"}, inplace=True)
                tmp["repo"] = repo_name
                rows_r.append(tmp)

        if not os.path.exists(rmd_file):
            print(f"[WARN] Rmd-touch file not found for {repo_name}: {rmd_file}")
        else:
            df_rmd = pd.read_csv(rmd_file)
            col_cat2 = detect_col(df_rmd, "category")
            col_pct2 = detect_col(df_rmd, "touches_rmd")
            if col_cat2 is None or col_pct2 is None:
                print(f"[WARN] Missing category/touches_rmd column in {rmd_file}")
            else:
                tmp2 = df_rmd[[col_cat2, col_pct2]].copy()
                tmp2.rename(columns={col_cat2: "bug_category", col_pct2: "touches_rmd_%"}, inplace=True)
                tmp2["repo"] = repo_name
                rows_rmd.append(tmp2)

    if rows_r:
        all_r = pd.concat(rows_r, ignore_index=True)
        all_r = all_r[["repo", "bug_category", "touches_r_%"]]
        os.makedirs(os.path.dirname(args.out_r), exist_ok=True)
        all_r.to_csv(args.out_r, index=False)
        print(f"Saved cross-repo R-touch table to: {args.out_r}")
    else:
        print("No R-touch data collected.")

    if rows_rmd:
        all_rmd = pd.concat(rows_rmd, ignore_index=True)
        all_rmd = all_rmd[["repo", "bug_category", "touches_rmd_%"]]
        os.makedirs(os.path.dirname(args.out_rmd), exist_ok=True)
        all_rmd.to_csv(args.out_rmd, index=False)
        print(f"Saved cross-repo Rmd-touch table to: {args.out_rmd}")
    else:
        print("No Rmd-touch data collected.")

if __name__ == "__main__":
    main()
