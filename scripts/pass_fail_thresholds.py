#!/usr/bin/env python3
import argparse, sys, os
import pandas as pd

# ---- thresholds (tune if needed)
COVERAGE_MIN = 0.85      # >= 85% of commits have score > 0
LOWCONF_MAX  = 0.15      # <= 15% have score <= 2
UNKNOWN_MAX  = 0.10      # <= 10% Unknown category
SUSPECT_WARN = 0.02      # >2% suspects -> WARN
SUSPECT_MAX  = 0.10      # >10% suspects -> FAIL

def load_pct(base):
    return pd.read_csv(base + "_category_percentages.csv")

def load_sus(base):
    try:    return pd.read_csv(base + "_suspect_relabels.csv")
    except: return pd.DataFrame()

def load_touch(base):
    for suffix in ("_touches_rmd_by_category.csv", "_rmd_touch_by_category.csv"):
        try:
            df = pd.read_csv(base + suffix)
            if "touches_rmd_%" in df.columns:
                df["touches_rmd_%"] = pd.to_numeric(df["touches_rmd_%"], errors="coerce")
            return df
        except Exception:
            continue
    return pd.DataFrame()

def load_touch_r(base):
    """Load touches .R by category; always return a DataFrame (possibly empty)."""
    try:
        df = pd.read_csv(base + "_r_touch_by_category.csv")
        if "touches_r_%" in df.columns:
            df["touches_r_%"] = pd.to_numeric(df["touches_r_%"], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()


def coverage_lowconf(classified_path):
    try:
        df = pd.read_csv(classified_path)
    except Exception:
        return None, None
    lc = {c.lower(): c for c in df.columns}
    score_col = lc.get("category_score")
    if not score_col: 
        return None, None
    s = pd.to_numeric(df[score_col], errors="coerce")
    cov = float((s > 0).mean()) if len(s) else None
    low = float((s <= 2).mean()) if len(s) else None
    return cov, low

def grade_repo(base, classified=None, show_tables=True):
    pct = load_pct(base)
    sus = load_sus(base)
    touch = load_touch(base)
    touch_r = load_touch_r(base)

    n_commits = int(pd.to_numeric(pct["count"], errors="coerce").sum())
    unknown_pct = float(
        pct.loc[pct["bug_category"].str.contains("Unknown", case=False, na=False), "percent"].sum()
    ) if "percent" in pct.columns else 0.0
    suspect_rate = (len(sus) / n_commits) if n_commits else 0.0

    cov, low = (None, None)
    if classified:
        cov, low = coverage_lowconf(classified)

    status = "PASS"
    reasons = []

    if unknown_pct > UNKNOWN_MAX * 100:
        status = "FAIL"; reasons.append(f"Unknown {unknown_pct:.1f}% > {UNKNOWN_MAX*100:.0f}%")
    if cov is not None and cov < COVERAGE_MIN:
        status = "FAIL"; reasons.append(f"Coverage {cov:.1%} < {COVERAGE_MIN:.0%}")
    if low is not None and low > LOWCONF_MAX:
        status = "FAIL"; reasons.append(f"LowConf {low:.1%} > {LOWCONF_MAX:.0%}")
    if suspect_rate > SUSPECT_MAX:
        status = "FAIL"; reasons.append(f"Suspects {suspect_rate:.1%} > {SUSPECT_MAX:.0%}")
    elif suspect_rate > SUSPECT_WARN and status != "FAIL":
        status = "WARN"; reasons.append(f"Suspects {suspect_rate:.1%} > {SUSPECT_WARN:.0%}")

    print(f"Repo base: {base}")
    print(f"Total commits: {n_commits}")
    print(f"Unknown %: {unknown_pct:.2f}")
    print(f"Suspect relabels: {len(sus)} ({suspect_rate*100:.2f}%)")
    if cov is not None: print(f"Coverage (score>0): {cov:.2%}")
    if low is not None: print(f"Low-confidence (score<=2): {low:.2%}")
    print(f"RESULT: {status}" + (f"  |  " + " ; ".join(reasons) if reasons else ""))

    if show_tables:
        print("\nCategory percentages:")
        print(pct.sort_values("count", ascending=False))
        if not touch.empty:
            print("\nTouches .Rmd by category (%):")
            print(touch.sort_values("touches_rmd_%", ascending=False))
        if not touch_r.empty:
            print("\nTouches .R by category (%):")
            print(touch_r.sort_values("touches_r_%", ascending=False))

    return 0 if status == "PASS" else (1 if status == "WARN" else 2)

def main():
    ap = argparse.ArgumentParser(description="Pass/Fail gate for a single repo’s analysis outputs.")
    ap.add_argument("--base", required=True, help="Path prefix without suffix, e.g. data_all\\owner_repo\\owner_repo_classified")
    ap.add_argument("--classified", help="Optional path to the full *_classified.csv for coverage/low-confidence")
    ap.add_argument("--quiet", action="store_true", help="Hide tables; only print summary line")
    args = ap.parse_args()

    code = grade_repo(args.base, args.classified, show_tables=not args.quiet)
    sys.exit(code)

if __name__ == "__main__":
    main()
