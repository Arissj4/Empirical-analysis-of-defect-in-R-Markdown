#!/usr/bin/env python3
# summarize_repo.py
# Usage:
#   py summarize_repo.py "data_all\<REPO>\<REPO>_classified.csv"
# Outputs (next to the input file):
#   <REPO>_classified_category_percentages.csv
#   <REPO>_classified_rmd_touch_by_category.csv
#   <REPO>_classified_top_paths.csv

import sys, os, pandas as pd
from collections import Counter

def detect(df, *cands):
    lower = {c.lower(): c for c in df.columns}
    for c in cands:
        if c.lower() in lower: return lower[c.lower()]
    return None

def infer_rmd_touch(row, col_files):
    """If touches_rmd is missing, infer it from filenames."""
    if col_files is None:
        return False
    val = str(row[col_files] or "")
    toks = [t.strip().lower() for t in val.split(";") if t.strip()]
    if not toks:
        return False
    RMD_HINTS = (".rmd", ".qmd", "_site.yml", "_output.yml", "bookdown.yml")
    return any(any(tok.endswith(h) or h in tok for h in RMD_HINTS) for tok in toks)

def pct_table(d, col_cat):
    c = d[col_cat].value_counts(dropna=False).rename_axis('bug_category').reset_index(name='count')
    c['percent'] = (c['count'] / len(d) * 100).round(1)
    return c.sort_values('count', ascending=False).reset_index(drop=True)

def main():
    if len(sys.argv) < 2:
        print("Usage: py summarize_repo.py path\\to\\<REPO>_classified.csv")
        sys.exit(1)

    in_csv = sys.argv[1]
    df = pd.read_csv(in_csv)

    # Column detection
    col_cat   = detect(df, "bug_category","category","label")
    col_score = detect(df, "category_score","score")
    col_touch = detect(df, "touches_rmd","touch_rmd","rmd")
    col_files = detect(df, "filenames","files","paths")
    col_touch_r = detect(df, "touches_r", "touch_r")

    if col_cat is None:
        raise SystemExit("Could not find bug_category column (aliases: bug_category/category/label).")

    # Ensure strings for safe ops
    if col_files and col_files in df:
        df[col_files] = df[col_files].fillna("").astype(str)

    # 1) Category percentages
    pct = pct_table(df, col_cat)

    # 2) Rmd touch rates by category
    if col_touch and col_touch in df.columns:
        s = df[col_touch]
        if s.dtype == object:
            s = s.astype(str).str.strip().str.lower().isin(["true","t","1","yes","y"])
        else:
            s = s.astype(bool)
        df["_touch_rmd"] = s
    else:
        df["_touch_rmd"] = df.apply(lambda r: infer_rmd_touch(r, col_files), axis=1)

    touch = (df.groupby(col_cat)["_touch_rmd"]
               .mean()
               .mul(100).round(1)
               .rename("touches_rmd_%")
               .reset_index()
               .sort_values("touches_rmd_%", ascending=False)
             )

    # 3) Top paths (from filenames)
    top_paths = pd.DataFrame(columns=["path","count"])
    if col_files and col_files in df.columns:
        all_files = []
        for x in df[col_files]:
            if not x: continue
            all_files.extend([p.strip() for p in str(x).split(";") if p.strip()])
        if all_files:
            cnt = Counter(all_files).most_common(15)
            top_paths = pd.DataFrame(cnt, columns=["path","count"])

    # 4) R touch rates by category
    if col_touch_r and col_touch_r in df.columns:
        s_r = df[col_touch_r]
        if s_r.dtype == object:
            s_r = s_r.astype(str).str.strip().str.lower().isin(["true","t","1","yes","y"])
        else:
            s_r = s_r.astype(bool)
        df["_touch_r"] = s_r
    else:
        # Fallback inference from filenames column if present
        df["_touch_r"] = False
        if col_files and col_files in df.columns:
            df["_touch_r"] = df[col_files].astype(str).str.lower().str.contains(r"\.r(;|$)", regex=True)


    # Save next to input
    touch_r = (df.groupby(col_cat)["_touch_r"]
        .mean().mul(100).round(1)
        .rename("touches_r_%")
        .reset_index()
        .sort_values("touches_r_%", ascending=False))
    

    base, _ = os.path.splitext(in_csv)
    out_touch_r = base + "_r_touch_by_category.csv"
    out_pct   = base + "_category_percentages.csv"
    out_touch = base + "_rmd_touch_by_category.csv"
    out_paths = base + "_top_paths.csv"

    touch_r.to_csv(out_touch_r, index=False)
    pct.to_csv(out_pct, index=False)
    touch.to_csv(out_touch, index=False)
    if not top_paths.empty:
        top_paths.to_csv(out_paths, index=False)

    # Console summary
    print(f"Repo summary for: {in_csv}")
    print(pct)
    print("\nTouches .Rmd by category (%):")
    print(touch)
    if not top_paths.empty:
        print("\nTop touched paths:")
        print(top_paths)
    else:
        print("\nTop touched paths: (no filenames column found or empty)")

if __name__ == "__main__":
    main()
