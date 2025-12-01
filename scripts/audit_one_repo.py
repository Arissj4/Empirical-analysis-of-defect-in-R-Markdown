#!/usr/bin/env python3
import argparse, os, re, pandas as pd

# ----- thresholds you can tune
MIN_STRONG_SCORE = 6       # classification score >= this => trust classifier (no suspect)
REQUIRE_MSG_STRONG = True  # only flag suspect if message has a strong, category-specific hint
IGNORE_GENERIC = True      # ignore generic messages (fix/update/etc.) as message hints
DELTA_ALLOW = 2            # if classifier score is within DELTA of a hinted cat, keep classifier

def rx(p, flags=re.I): return re.compile(p, flags)

# High-precision message hints per category (NO generic words here)
MSG_HINTS = {
    "Documentation / Formatting": rx(r"\b(readme|vignette|roxygen|pkgdown|docs?|heading|typo|spelling|grammar|man page|news)\b"),
    "Rendering / Conversion":     rx(r"\b(render|knit|quarto|pandoc|latex|compile|build site)\b"),
    "Dependency / Package":       rx(r"\b(dependency|namespace|import|install|cran|r cmd check)\b"),
    "Visualization / Plotting":   rx(r"\b(ggplot|legend|axis|figure|theme|facet)\b"),
    "Data / Input Handling":      rx(r"\b(read\s|load|parse|input|csv|tsv|missing data)\b"),
    "Environment / Configuration":rx(r"\b(config|yaml|path|environment|option|workflow|ci)\b"),
    "File I/O and Export":        rx(r"\b(write\.?csv|write(file|lines)?|save(rds| image)?|export|ggsave)\b"),
    "Implementation / Logic":     rx(r"\b(argument|index|subset|logic|na\b|null\b|trycatch|stop\()"),
}

# Generic words that should NOT trigger a suspect by themselves
GENERIC = rx(r"\b(fix|fixed|fixes|update|minor|misc|refactor|cleanup|improve|adjust|change|tweak|polish)\b")

# Minimal diff/path patterns to decide if the classifier had strong evidence
DIFF_PATH = {
    "Documentation / Formatting": (
        rx(r"(?:^|[/\\])(readme(?:\.r?md)?|vignettes|man|pkgdown|inst[/\\]doc|docs|news\.md)(?:[/\\]|$)"),
        rx(r"\b(readme|pkgdown|vignette|roxygen|typo|spelling|grammar)\b"),
    ),
    "Rendering / Conversion": (
        rx(r"(?:\.rmd|\.qmd|_output\.yml|_site\.yml|bookdown\.yml)$"),
        rx(r"\b(rmarkdown::render|knit|quarto|pandoc|latex|compile)\b"),
    ),
    "Dependency / Package": (
        rx(r"(?:^|[/\\])(DESCRIPTION|NAMESPACE|renv\.lock)(?:$|[/\\])"),
        rx(r"\b(library\(|require\(|install\.packages|::)\b"),
    ),
    "Visualization / Plotting": (rx(r""), rx(r"\b(ggplot2?::ggplot|ggplot\(|geom_|aes\()")),
    "Data / Input Handling":     (rx(r""), rx(r"\b(read\.csv|readr::read_|fread\(|fromJSON|readRDS)\b")),
    "Environment / Configuration":(rx(r"(?:^|[/\\])(\.Rprofile|\.Renviron|\.github[/\\]workflows)(?:$|[/\\])"), rx(r"")),
    "File I/O and Export":        (rx(r""), rx(r"\b(write\.csv|writeLines|saveRDS|ggsave|export)\b")),
    "Implementation / Logic":     (rx(r""), rx(r"")),
    "Reproducibility / Versioning":(rx(r"(?:^|[/\\])(renv\.lock|DESCRIPTION)(?:$|[/\\])"), rx(r"\b(set\.seed|sessionInfo\(\)|renv::(snapshot|restore))\b")),
    "Miscellaneous / Unknown":    (rx(r""), rx(r"")),
}

def strong_msg_category(msg):
    m = str(msg or "")
    cats = [c for c, pat in MSG_HINTS.items() if pat.search(m)]
    if not cats: return None
    # prefer more specific categories first
    order = ["Documentation / Formatting","Rendering / Conversion","Visualization / Plotting",
             "Data / Input Handling","Dependency / Package","Environment / Configuration",
             "File I/O and Export","Reproducibility / Versioning","Implementation / Logic"]
    cats.sort(key=lambda c: order.index(c))
    return cats[0]

def classifier_has_strong_evidence(cat, diff_text, filenames):
    path_pat, diff_pat = DIFF_PATH.get(cat, (rx(r""), rx(r"")))
    files = (filenames or "").lower()
    diff  = diff_text or ""
    if path_pat.pattern and path_pat.search(files): return True
    if diff_pat.pattern and diff_pat.search(diff):  return True
    return False

def detect_columns(df):
    lc = {c.lower(): c for c in df.columns}
    def pick(cands):
        for k in cands:
            if k in lc: return lc[k]
        return None
    return {
        "msg":       pick(["message","commit_message","msg"]),
        "cat":       pick(["bug_category","category"]),
        "score":     pick(["category_score","score"]),
        "diff":      pick(["diff","patch","changes"]),
        "filenames": pick(["filenames","files","paths"]),
        "sha":       pick(["commit_hash","sha","hash","commit"]),
    }

def run(classified_csv, out_csv):
    df = pd.read_csv(classified_csv)
    cols = detect_columns(df)
    for need in ["msg","cat","score"]:
        if not cols[need]:
            raise SystemExit(f"Missing required column: {need}")

    suspects = []
    for _, r in df.iterrows():
        msg   = r.get(cols["msg"], "")
        cat   = r.get(cols["cat"], "")
        score = pd.to_numeric(r.get(cols["score"]), errors="coerce")
        diff  = r.get(cols["diff"], "")
        files = r.get(cols["filenames"], "")

        # 1) strong classifier? -> never suspect
        if pd.notna(score) and score >= MIN_STRONG_SCORE:
            continue

        # 2) strong message hint?
        msg_cat = strong_msg_category(msg)
        if REQUIRE_MSG_STRONG and not msg_cat:
            continue

        # 3) ignore purely generic messages
        if IGNORE_GENERIC and (GENERIC.search(str(msg)) and not msg_cat):
            continue

        # 4) if classifier has strong path/diff evidence -> trust it
        if classifier_has_strong_evidence(cat, diff, files):
            continue

        # 5) if message cat equals classifier -> not suspect
        if msg_cat and msg_cat == cat:
            continue

        # 6) optional small margin: if classifier score is close enough, keep it
        if pd.notna(score) and score >= max(MIN_STRONG_SCORE - DELTA_ALLOW, 0):
            continue

        suspects.append({
            "commit_hash": r.get(cols["sha"]),
            "message": msg,
            "assigned_category": cat,
            "category_score": score,
            "message_hint_category": msg_cat,
        })

    out_df = pd.DataFrame(suspects)
    out_df.to_csv(out_csv, index=False)
    print(f"Suspects written: {len(out_df)} -> {out_csv}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--classified", help="Path to *_classified.csv")
    src.add_argument("--base", help="Prefix without .csv (e.g., data_bug\\repo\\repo_classified)")
    ap.add_argument("--out", help="Output CSV (default: <base>_suspect_relabels.csv)")
    args = ap.parse_args()

    if args.base:
        classified = args.base + ".csv"
        out = args.out or args.base + "_suspect_relabels.csv"
    else:
        classified = args.classified
        b, _ = os.path.splitext(classified)
        out = args.out or b + "_suspect_relabels.csv"

    run(classified, out)
