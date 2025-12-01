#!/usr/bin/env python3
import os, sys, argparse, subprocess, pandas as pd, traceback

COVERAGE_MIN = 0.85
LOWCONF_MAX  = 0.15
UNKNOWN_MAX  = 0.10
SUSPECT_WARN = 0.02
SUSPECT_MAX  = 0.10

def find_classified_csvs(data_dir: str):
    out = []
    for root, _, files in os.walk(data_dir):
        for f in files:
            if f.endswith("_classified.csv"):
                out.append(os.path.join(root, f))
    return sorted(out)

def ensure_percentages(classified_csv: str, base_prefix: str):
    pct_path = base_prefix + "_category_percentages.csv"
    if os.path.exists(pct_path):
        return pct_path
    df = pd.read_csv(classified_csv)
    grp = df.groupby("bug_category", as_index=False)
    pct = grp.size().rename(columns={"size":"count"})
    pct["percent"] = (pct["count"]/len(df)*100).round(1)
    if "category_score" in df.columns:
        med = grp["category_score"].median()
        pct = pct.merge(med, on="bug_category", how="left").rename(columns={"category_score":"median_score"})
    pct = pct.sort_values("count", ascending=False)
    pct.to_csv(pct_path, index=False)
    return pct_path

def run_audit_if_missing(base_prefix: str, scripts_dir: str):
    sus_path = base_prefix + "_suspect_relabels.csv"
    if os.path.exists(sus_path):
        return sus_path
    audit_py = os.path.join(scripts_dir, "audit_one_repo.py")
    if not os.path.exists(audit_py):
        return sus_path
    try:
        subprocess.run([sys.executable, audit_py, "--base", base_prefix],
                       check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception:
        pass
    return sus_path

def coverage_lowconf(classified_csv: str):
    df = pd.read_csv(classified_csv)
    s = pd.to_numeric(df.get("category_score"), errors="coerce")
    cov = float((s > 0).mean()) if len(s) else float("nan")
    low = float((s <= 2).mean()) if len(s) else float("nan")
    return cov, low, len(df)

def qc_one(classified_csv: str, scripts_dir: str):
    base_prefix, _ = os.path.splitext(classified_csv)
    pct_csv = ensure_percentages(classified_csv, base_prefix)

    pct = pd.read_csv(pct_csv)
    n_commits = int(pd.to_numeric(pct["count"], errors="coerce").sum())
    unknown_pct = float(
        pct.loc[pct["bug_category"].str.contains("Unknown", case=False, na=False), "percent"].sum()
    ) if "percent" in pct.columns else 0.0

    sus_csv = run_audit_if_missing(base_prefix, scripts_dir)
    suspects = 0
    if os.path.exists(sus_csv):
        try:
            suspects = len(pd.read_csv(sus_csv))
        except Exception:
            suspects = 0
    suspect_rate = (suspects / n_commits) if n_commits else 0.0

    cov, low, _ = coverage_lowconf(classified_csv)

    status, reasons = "PASS", []
    if unknown_pct/100.0 > UNKNOWN_MAX:
        status = "FAIL"; reasons.append(f"Unknown {unknown_pct:.1f}% > {UNKNOWN_MAX*100:.0f}%")
    if cov < COVERAGE_MIN:
        status = "FAIL"; reasons.append(f"Coverage {cov:.1%} < {COVERAGE_MIN:.0%}")
    if low > LOWCONF_MAX:
        status = "FAIL"; reasons.append(f"LowConf {low:.1%} > {LOWCONF_MAX:.0%}")
    if suspect_rate > SUSPECT_MAX:
        status = "FAIL"; reasons.append(f"Suspects {suspect_rate*100:.1f}% > {SUSPECT_MAX*100:.0f}%")
    elif suspect_rate > SUSPECT_WARN and status != "FAIL":
        status = "WARN"; reasons.append(f"Suspects {suspect_rate*100:.1f}% > {SUSPECT_WARN*100:.0f}%")

    repo_tag = os.path.basename(base_prefix)
    return {
        "repo": repo_tag,
        "n_commits": n_commits,
        "coverage": round(cov, 4),
        "low_conf": round(low, 4),
        "unknown_pct": round(unknown_pct, 2),
        "suspects_pct": round(suspect_rate*100, 2),
        "status": status,
        "reasons": " ; ".join(reasons),
        "base": base_prefix
    }

def main():
    ap = argparse.ArgumentParser(description="Batch QC across all repos.")
    ap.add_argument("--data-dir", default="data_bug", help="Folder containing per-repo subfolders")
    ap.add_argument("--scripts-dir", default="scripts", help="Folder containing audit_one_repo.py")
    ap.add_argument("--out", default="analysis/qc_summary.csv", help="Summary CSV output")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    rows, errors = [], []

    classified_files = find_classified_csvs(args.data_dir)
    if not classified_files:
        print(f"No *_classified.csv files found under {args.data_dir}")
        sys.exit(1)

    for cfile in classified_files:
        try:
            rows.append(qc_one(cfile, args.scripts_dir))
        except Exception as e:
            tb = traceback.format_exc()
            errors.append({"classified_csv": cfile, "error": str(e)})
            print(f"[QC-SKIP] {cfile}: {e}")
            print(tb)

    df = pd.DataFrame(rows)
    if not df.empty:
        status_order = {"FAIL":0, "WARN":1, "PASS":2}
        df["__ord"] = df["status"].map(status_order).fillna(3)
        df = df.sort_values(["__ord","suspects_pct","coverage"], ascending=[True, False, True]).drop(columns="__ord")
        df.to_csv(args.out, index=False)
        print(f"Wrote: {args.out}")
        print(df[["repo","status","n_commits","coverage","low_conf","unknown_pct","suspects_pct","reasons"]].to_string(index=False))

    if errors:
        err_csv = os.path.splitext(args.out)[0] + "_errors.csv"
        pd.DataFrame(errors).to_csv(err_csv, index=False)
        print(f"Some repos failed QC; see: {err_csv}")

if __name__ == "__main__":
    main()
