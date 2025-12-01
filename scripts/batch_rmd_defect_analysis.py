#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Batch R / R Markdown defect analysis over multiple repository CSVs.

Improvements:
- Saves per-repo QC helpers:
  * <repo>_category_percentages.csv  (with median_score)
  * <repo>_touches_rmd_by_category.csv  and  <repo>_rmd_touch_by_category.csv (compat)
  * <repo>_r_touch_by_category.csv
  * <repo>_top_paths.csv
- Detects touches_r / touches_rmd from columns or infers from filenames.
- Options: --examples-per-cat, --lean-classified, --limit-diff-chars, --keep-merges
- Keeps cross-repo aggregates in the top-level --dir folder.
"""

import os, re, argparse, unicodedata
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

# ---- Safer Matplotlib defaults for PDFs
mpl.rcParams['text.usetex'] = False
mpl.rcParams['mathtext.default'] = 'regular'
mpl.rcParams['axes.unicode_minus'] = False
mpl.rcParams['font.family'] = 'DejaVu Sans Mono'
mpl.rcParams['pdf.fonttype'] = 42
mpl.rcParams['ps.fonttype'] = 42

# ---- Category set (fixed order)
CATEGORIES = [
    "Rendering / Conversion",
    "Dependency / Package",
    "Environment / Configuration",
    "Implementation / Logic",
    "Data / Input Handling",
    "Visualization / Plotting",
    "Reproducibility / Versioning",
    "File I/O and Export",
    "Documentation / Formatting",
    "Miscellaneous / Unknown",
]

# ---- File hints for touch inference
RMD_HINTS = (".rmd", ".qmd", "_site.yml", "_output.yml", "bookdown.yml")
RFILE_HINTS = (".r",)

def any_re(words, word_boundaries=True):
    parts = []
    for w in words:
        pat = re.escape(w)
        if word_boundaries and re.fullmatch(r"\w+", w):
            pat = r"\b" + pat + r"\b"
        parts.append(pat)
    if not parts:
        return re.compile(r"$a", re.IGNORECASE)
    return re.compile("|".join(parts), re.IGNORECASE)

# ---- Diff-aware rules (weights below)
RULES = {
    "Rendering / Conversion": {
        "diff": any_re([
            "rmarkdown::render","knitr::knit","bookdown::render_book","quarto::render",
            "pandoc","latex","tinytex","pdf_document","html_document","word_document",
            "beamer_presentation","compile","front matter","yaml header"
        ]),
        "msg":  any_re([
            "render","knit","quarto","pandoc","latex","pdf","html","word","compile",
            "conversion","format to","build site"
        ]),
        "path": any_re([".Rmd",".qmd","_site.yml","_output.yml","bookdown.yml","vignettes/","README.Rmd"], word_boundaries=False),
    },
    "Dependency / Package": {
        "diff": any_re([
            "library(","require(","install.packages","remove.packages","loadNamespace",
            "DESCRIPTION","NAMESPACE","renv.lock","renv::","pak::","BiocManager::install",
            "Imports:","Depends:","Suggests:","Remotes:","S3method","export(","import(",
            "registerS3method","useDynLib"
        ]),
        "msg":  any_re([
            "package","library","dependency","namespace","import","install","update",
            "CRAN","R CMD check","devtools::check","usethis::"
        ]),
        "path": any_re(["DESCRIPTION","NAMESPACE","renv.lock"], word_boundaries=False),
    },
    "Environment / Configuration": {
        "diff": any_re(["yaml","output:","params:","setwd(","Sys.getenv","Sys.setenv","file.exists","options(",
                        "withr::with_dir","here::here","config::get","path.expand"]),
        "msg":  any_re(["config","yaml","path","environment","setup","working directory","permission","option"]),
        "path": any_re(["_site.yml","_output.yml",".Renviron",".Rprofile",".Rbuildignore",".gitignore","Makefile","Makevars",".Rproj"], word_boundaries=False),
    },
    "Implementation / Logic": {
        "diff": any_re(["stop(","warning(","tryCatch(","match.arg(","is.na(","length(","subset","index","argument","bug","fix","NA","NULL"]),
        "msg":  any_re(["logic","syntax","argument","variable","index","subset","NA","NULL","error in"]),
        "path": any_re([".R",".Rmd"], word_boundaries=False),
    },
    "Data / Input Handling": {
        "diff": any_re(["read.csv","read.table","readr::read_","readxl::read_excel","vroom::vroom",
                        "data.table::fread","jsonlite::fromJSON","yaml::read_yaml","load(","readRDS("]),
        "msg":  any_re(["read","load","parse","input","dataset","file read","csv","tsv","missing data"]),
        "path": any_re(["/data/",".csv",".tsv",".xlsx",".rds",".json",".yml",".yaml"], word_boundaries=False),
    },
    "Visualization / Plotting": {
        "diff": any_re(["ggplot(","geom_","aes(","theme(","scale_","facet_","plotly::","lattice::","cowplot::","patchwork::"]),
        "msg":  any_re(["ggplot","plot","figure","legend","axis","theme","facet"]),
        "path": any_re(["fig/","figure","plots/"], word_boundaries=False),
    },
    "Reproducibility / Versioning": {
        "diff": any_re(["set.seed","sessionInfo()","R.version","RVERSION","renv::snapshot","renv::restore","DESCRIPTION","renv.lock"]),
        "msg":  any_re(["seed","reproducible","version","session","update","R CMD check","CRAN"]),
        "path": any_re(["renv.lock","DESCRIPTION"], word_boundaries=False),
    },
    "File I/O and Export": {
        "diff": any_re(["write.csv","write.table","readr::write_","saveRDS(","save(","save.image(","ggsave(","output_dir","file.copy(","file.remove("]),
        "msg":  any_re(["write","save","export","output","cannot open","saveRDS","write.csv"]),
        "path": any_re(["/output","/results","/exports",".csv",".rds",".rdata"], word_boundaries=False),
    },
    "Documentation / Formatting": {
        "diff": any_re([
            r"\[.*\]\(.*\)","title:","author:","date:","pkgdown",".Rd","#'","spelling",
            "typo","grammar","docs:","readme"
        ], word_boundaries=False),
        "msg":  any_re([
            "readme","vignette","roxygen","pkgdown","docs","documentation","heading",
            "format","typo","spelling","grammar","link","article","man page","news"
        ]),
        "path": any_re([
            "README.md","README.Rmd","vignettes/","man/","NEWS.md",".md",".Rmd",
            "inst/doc","cran-comments.md"
        ], word_boundaries=False),
    },
    "Miscellaneous / Unknown": {"diff": any_re([]), "msg": any_re([]), "path": any_re([])}
}

MSG_HINTS = {
    "Documentation / Formatting": any_re([
        "readme","vignette","docs","documentation","roxygen","pkgdown",
        "typo","spelling","grammar","link","article","man page","news"
    ]),
    "Rendering / Conversion": any_re([
        "render","knit","quarto","pandoc","latex","compile","build site"
    ]),
    "Dependency / Package": any_re([
        "dependency","namespace","import","install","CRAN","R CMD check"
    ]),
    "Visualization / Plotting": any_re(["ggplot","plot","legend","axis","figure","theme","facet"]),
    "Data / Input Handling": any_re(["read ","load","parse","input","csv","tsv","missing data"]),
    "Environment / Configuration": any_re(["config","yaml","path","environment","option","workflow","ci"]),
}

def message_hint_category(msg: str):
    m = str(msg or "")
    for cat, rx in MSG_HINTS.items():
        if rx.search(m):
            return cat
    return None

# ---- Weights & priority
DIFF_W, PATH_W, MSG_W = 3, 3, 1
MSG_W_IMPL = 0  # message-only for Implementation gets 0
PRIORITY = [
    "Rendering / Conversion",
    "Documentation / Formatting",
    "Visualization / Plotting",
    "Data / Input Handling",
    "Dependency / Package",
    "Environment / Configuration",
    "File I/O and Export",
    "Reproducibility / Versioning",
    "Implementation / Logic",
    "Miscellaneous / Unknown",
]

# ---- Utilities
def sanitize_for_pdf(x: object) -> str:
    s = str(x)
    s = ''.join(ch for ch in s if unicodedata.category(ch)[0] != 'C')
    s = s.replace('\\\\', r'\\\\').replace('$', r'\$')
    return s

def extract_paths(diff_text, filenames=None):
    paths = []
    for line in str(diff_text).splitlines():
        if line.startswith(('+++ ', '--- ')):
            p = re.sub(r'^[ab]/', '', line[4:].strip())
            paths.append(p)
    if not paths and filenames:
        paths.extend(str(filenames).split(';'))
    return " ".join(paths)

def classify_row(message: str, diff: str, filenames=None):
    context = extract_paths(diff or "", filenames)
    msg = str(message); d = str(diff); ctx = context
    scores = {k: 0 for k in CATEGORIES}
    has_strong = {k: False for k in CATEGORIES}
    for cat, pats in RULES.items():
        if pats["diff"].search(d):
            scores[cat] += DIFF_W; has_strong[cat] = True
        if ctx and pats["path"].search(ctx):
            scores[cat] += PATH_W; has_strong[cat] = True
        msg_w = MSG_W_IMPL if cat == "Implementation / Logic" else MSG_W
        if pats["msg"].search(msg):
            scores[cat] += msg_w
    msg_cat = message_hint_category(msg)
    strong = [c for c in CATEGORIES if has_strong[c]]
    if strong:
        best = max(strong, key=lambda c: (scores[c], -PRIORITY.index(c)))
        if msg_cat in ["Documentation / Formatting","Rendering / Conversion"]:
            if scores[msg_cat] >= scores[best] - 1:  # within 1 point, pick message cat
                return msg_cat, scores[msg_cat]
        return best, scores[best]
    
    if msg_cat:
        return msg_cat, scores[msg_cat]
    
    best = max(CATEGORIES, key=lambda c: (scores[c], -PRIORITY.index(c)))
    return best, scores[best]

def short_snip(s, n=180):
    s = str(s).replace("\\n", " ")
    return s[:n] + ("..." if len(s) > n else "")

def save_category_bar(freq_df: pd.DataFrame, out_png: str):
    plt.figure(figsize=(8,4))
    plt.bar(freq_df["bug_category"], freq_df["count"])
    plt.title("Bug Categories — Commit Counts")
    plt.xticks(rotation=60, ha="right")
    plt.ylabel("Commits")
    plt.tight_layout()
    plt.savefig(out_png, dpi=200)
    plt.close()

def save_examples_pdf(ex_df: pd.DataFrame, freq_df: pd.DataFrame, out_pdf: str, title="Examples per category"):
    with PdfPages(out_pdf) as pdf:
        fig1 = plt.figure(figsize=(8.5, 5))
        plt.bar(freq_df["bug_category"], freq_df["count"])
        plt.title("Bug Categories — Commit Counts")
        plt.xticks(rotation=60, ha="right")
        plt.ylabel("Commits")
        plt.tight_layout()
        pdf.savefig(fig1)
        plt.close(fig1)

        cols = ["repo","bug_category","commit_hash","date","author","message","score","diff_snippet"]
        chunk = 12
        if ex_df.empty:
            fig = plt.figure(figsize=(8.5, 11)); plt.axis('off')
            plt.title(title, loc="left")
            plt.text(0.05, 0.9, "No examples available.", fontsize=10)
            pdf.savefig(fig, bbox_inches='tight'); plt.close(fig); return

        for i in range(0, len(ex_df), chunk):
            sub = ex_df.iloc[i:i+chunk].copy()
            sub = sub[cols].applymap(sanitize_for_pdf)
            fig = plt.figure(figsize=(8.5, 11)); plt.axis('off')
            plt.title(title, loc="left")
            tbl = plt.table(cellText=sub.values, colLabels=sub.columns.tolist(),
                            loc='center', cellLoc='left', colLoc='left')
            tbl.auto_set_font_size(False); tbl.set_fontsize(7.5); tbl.scale(1, 1.2)
            pdf.savefig(fig, bbox_inches='tight'); plt.close(fig)

def detect_columns(df: pd.DataFrame):
    lc = {c.lower(): c for c in df.columns}
    def pick(cands):
        for k in cands:
            if k in lc: return lc[k]
        return None
    commit_col  = pick(["commit_hash","sha","hash","commit"])
    message_col = pick(["message","commit_message","msg"])
    diff_col    = pick(["diff","patch","changes","change"])
    filenames   = pick(["filenames","files","paths"])
    touches_r   = pick(["touches_r","touch_r"])
    touches_rmd = pick(["touches_rmd","touch_rmd","touches_r_markdown"])
    date_col    = pick(["date","author_date","commit_date"])
    author_col  = pick(["author","author_name","committer"])
    return {
        "commit": commit_col, "message": message_col, "diff": diff_col,
        "filenames": filenames, "touch_r": touches_r, "touch_rmd": touches_rmd,
        "date": date_col, "author": author_col
    }

def infer_touches(df: pd.DataFrame, cols):
    # Ensure boolean columns _touch_r/_touch_rmd exist
    # 1) Use provided boolean-ish columns if present
    for key, outcol in [("touch_r","_touch_r"), ("touch_rmd","_touch_rmd")]:
        c = cols.get(key)
        if c and c in df.columns:
            s = df[c]
            if s.dtype == object:
                s = s.astype(str).str.strip().str.lower().isin(["true","t","1","yes","y"])
            else:
                s = s.astype(bool)
            df[outcol] = s
        else:
            df[outcol] = False

    # 2) Fallback inference from filenames when missing
    files_col = cols.get("filenames")
    if files_col and files_col in df.columns:
        files = df[files_col].astype(str).str.lower()
        df["_touch_r"]   = df["_touch_r"]   | files.str.contains(r"\.r(;|$)", regex=True)
        rmd_pat = r"\.rmd(;|$)|\.qmd(;|$)|_site\.yml|_output\.yml|bookdown\.yml"
        df["_touch_rmd"] = df["_touch_rmd"] | files.str.contains(rmd_pat, regex=True)

    return df

def build_examples(df, repo_tag, examples_per_cat, limit_diff_chars):
    rows = []
    for cat in df["bug_category"].unique():
        sub = df[df["bug_category"] == cat].sort_values("category_score", ascending=False).head(examples_per_cat)
        for _, r in sub.iterrows():
            diff_text = r.get("diff", "")
            if limit_diff_chars is not None:
                diff_text = str(diff_text)[:limit_diff_chars]
            rows.append({
                "repo": repo_tag,
                "bug_category": cat,
                "commit_hash": str(r.get("commit_hash", ""))[:10],
                "date": r.get("date", ""),
                "author": r.get("author", ""),
                "message": short_snip(r.get("message", ""), 120),
                "score": r.get("category_score", 0),
                "diff_snippet": short_snip(diff_text, 220),
            })
    return pd.DataFrame(rows)

def save_qc_tables(df, repo_dir, repo_tag):
    # Percentages with median score
    pct = (df.groupby("bug_category", as_index=False)
             .agg(count=("bug_category","size"),
                  percent=("bug_category", lambda s: round(100.0*len(s)/len(df), 1)),
                  median_score=("category_score","median"))
             .sort_values("count", ascending=False))
    pct.to_csv(os.path.join(repo_dir, f"{repo_tag}_category_percentages.csv"), index=False, encoding="utf-8")

    # Touch rates by category (Rmd, R)
    t_rmd = (df.groupby("bug_category")["_touch_rmd"].mean().mul(100).round(1)
               .rename("touches_rmd_%").reset_index().sort_values("touches_rmd_%", ascending=False))
    t_r   = (df.groupby("bug_category")["_touch_r"].mean().mul(100).round(1)
               .rename("touches_r_%").reset_index().sort_values("touches_r_%", ascending=False))

    # Save both common filenames for Rmd (compat with older tools)
    rmd_a = os.path.join(repo_dir, f"{repo_tag}_touches_rmd_by_category.csv")
    rmd_b = os.path.join(repo_dir, f"{repo_tag}_rmd_touch_by_category.csv")
    t_rmd.to_csv(rmd_a, index=False, encoding="utf-8")
    t_rmd.to_csv(rmd_b, index=False, encoding="utf-8")

    r_csv = os.path.join(repo_dir, f"{repo_tag}_r_touch_by_category.csv")
    t_r.to_csv(r_csv, index=False, encoding="utf-8")

    # Top paths (from filenames if present)
    # explode semicolon-joined list; keep top 50
    top_paths_csv = os.path.join(repo_dir, f"{repo_tag}_top_paths.csv")
    paths_series = pd.Series(dtype=str)
    if "filenames" in df.columns:
        s = df["filenames"].dropna().astype(str).str.split(";")
        if not s.empty:
            paths_series = pd.Series([p.strip() for lst in s for p in lst if p and isinstance(lst, list)])
    if not paths_series.empty:
        top = (paths_series.value_counts()
                 .rename_axis("path")
                 .reset_index(name="count")
                 .head(50))
        top.to_csv(top_paths_csv, index=False, encoding="utf-8")
    else:
        pd.DataFrame(columns=["path","count"]).to_csv(top_paths_csv, index=False, encoding="utf-8")

def process_one_csv(path, skip_merges=True, examples_per_cat=3, lean_classified=False, limit_diff_chars=None):
    fname = os.path.basename(path)
    try:
        df = pd.read_csv(path, encoding="utf-8")
    except Exception:
        try:
            df = pd.read_csv(path, encoding="latin-1")
        except Exception:
            print(f"[skip] Could not read {fname}")
            return None

    cols = detect_columns(df)
    if not (cols["commit"] and cols["message"] and cols["diff"]):
        print(f"[skip] {fname}: missing required columns (need commit hash/message/diff)")
        return None

    # Normalize columns of interest
    rename_map = {cols["commit"]: "commit_hash", cols["message"]: "message", cols["diff"]: "diff"}
    for k in ["filenames","date","author"]:
        if cols.get(k): rename_map[cols[k]] = k
    df = df.rename(columns=rename_map)

    # Clean basic text
    for c in ["message","diff"]:
        df[c] = df[c].fillna("").astype(str)

    if skip_merges:
        df = df[~df["message"].str.startswith("Merge ")].copy()

    # Touch inference (creates _touch_r / _touch_rmd)
    df = infer_touches(df, cols)

    # Classify
    cats, scores = [], []
    for msg, diff, files in zip(df["message"], df["diff"], df.get("filenames", pd.Series([""]*len(df)))):
        cat, sc = classify_row(msg, diff, files)
        cats.append(cat); scores.append(sc)
    df["bug_category"] = cats
    df["category_score"] = scores

    # Repo folder
    repo_tag = os.path.splitext(fname)[0]
    repo_dir = os.path.join(os.path.dirname(path), repo_tag)
    os.makedirs(repo_dir, exist_ok=True)

    # Save classified
    classified_csv = os.path.join(repo_dir, f"{repo_tag}_classified.csv")
    out_df = df.copy()
    if lean_classified and "diff" in out_df.columns:
        out_df = out_df.drop(columns=["diff"])
    elif limit_diff_chars is not None:
        out_df["diff"] = out_df["diff"].astype(str).str.slice(0, int(limit_diff_chars))
    out_df.to_csv(classified_csv, index=False, encoding="utf-8")

    # Frequencies / bar chart
    freq = df["bug_category"].value_counts().rename_axis("bug_category").reset_index(name="count")
    freq["percent"] = (freq["count"] / len(df) * 100).round(1)
    bar_png = os.path.join(repo_dir, f"{repo_tag}_category_counts.png")
    save_category_bar(freq, bar_png)

    # Examples + PDF
    examples_csv = os.path.join(repo_dir, f"{repo_tag}_examples.csv")
    examples_pdf = os.path.join(repo_dir, f"{repo_tag}_examples_appendix.pdf")
    ex_df = build_examples(df, repo_tag, examples_per_cat, limit_diff_chars)
    ex_df.to_csv(examples_csv, index=False, encoding="utf-8")
    save_examples_pdf(ex_df, freq, examples_pdf, title=f"{repo_tag}: Examples per category")

    # QC helper tables
    save_qc_tables(df, repo_dir, repo_tag)

    print(f"[ok] {fname} -> {repo_dir} (n={len(df)})")

    # Return info for cross-repo aggregation
    return {
        "repo_tag": repo_tag,
        "n": len(df),
        "freq": freq.assign(repo=repo_tag)
    }

def main(in_dir: str, keep_merges: bool, examples_per_cat: int, lean_classified: bool, limit_diff_chars: int | None):
    aggregate_counts = []
    for fname in os.listdir(in_dir):
        if not fname.lower().endswith(".csv"):
            continue
        info = process_one_csv(
            os.path.join(in_dir, fname),
            skip_merges=(not keep_merges),
            examples_per_cat=examples_per_cat,
            lean_classified=lean_classified,
            limit_diff_chars=limit_diff_chars
        )
        if info:
            aggregate_counts.append(info["freq"])

    # Cross-repo aggregates at top level
    if aggregate_counts:
        agg = pd.concat(aggregate_counts, ignore_index=True)
        pivot = (agg.pivot_table(index="repo", columns="bug_category", values="count",
                                 aggfunc="sum", fill_value=0)
                    .reindex(columns=CATEGORIES, fill_value=0))
        agg_csv = os.path.join(in_dir, "cross_repo_category_counts.csv")
        pivot.to_csv(agg_csv, encoding="utf-8")

        totals = agg.groupby("bug_category")["count"].sum().reset_index()
        plt.figure(figsize=(8,4))
        plt.bar(totals["bug_category"], totals["count"])
        plt.title("All Repos — Bug Categories (Total Commits)")
        plt.xticks(rotation=60, ha="right")
        plt.ylabel("Commits")
        plt.tight_layout()
        totals_png = os.path.join(in_dir, "cross_repo_category_totals.png")
        plt.savefig(totals_png, dpi=200); plt.close()
        print(f"[ok] cross repo -> {agg_csv} | {totals_png}")

    print("Done.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Batch R / R Markdown defect analysis.")
    ap.add_argument("--dir", default=".", help="Folder with repo CSV files")
    ap.add_argument("--keep-merges", action="store_true", help="Keep merge commits (default: filtered)")
    ap.add_argument("--examples-per-cat", type=int, default=3, help="Examples per category in appendix")
    ap.add_argument("--lean-classified", action="store_true", help="Drop the 'diff' column in the classified CSV")
    ap.add_argument("--limit-diff-chars", type=int, default=None, help="Truncate diff text to N chars in outputs")
    args = ap.parse_args()
    main(args.dir, args.keep_merges, args.examples_per_cat, args.lean_classified, args.limit_diff_chars)
