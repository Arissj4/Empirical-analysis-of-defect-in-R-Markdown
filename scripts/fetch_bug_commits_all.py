#!/usr/bin/env python3
"""
Fetch bug-like commits (all history) for a list of GitHub repos.

Inputs
------
--repos-csv : CSV with repository identifiers. Any ONE of:
              - columns: 'owner','repo'
              - column: 'url' like 'https://github.com/<owner>/<repo>'
              - column: 'full_name' like '<owner>/<repo>'

Outputs
-------
One CSV per repo in --out-dir:
  <owner>_<repo>_bug_commits.csv

Columns:
  repo_owner, repo_name, commit_hash, author_name, author_email,
  author_date, committer_name, committer_email, committer_date,
  message, filenames (semicolon-joined), touches_rmd (bool),
  is_merge (bool), added, deleted, changed, diff (joined patches)

Auth
----
Set your PAT before running (higher rate limits):
  Windows (cmd):   set GITHUB_TOKEN=ghp_xxx
  PowerShell:      $env:GITHUB_TOKEN = "ghp_xxx"
  mac/Linux (bash):export GITHUB_TOKEN=ghp_xxx

Examples
--------
python fetch_bug_commits_all.py ^
  --repos-csv repos_rmd_2022_candidates_passes.csv ^
  --out-dir data_bug ^
  --skip-merges ^
  --require-rmd-touch

"""

import argparse, csv, os, re, sys, time, datetime as dt
from typing import Iterable, Dict, Any, List, Tuple, Optional

import requests
import pandas as pd

GITHUB = "https://api.github.com"

DEFAULT_KEYWORDS = [
    'fix','fixes','fixed','fixing',
    'defect','defects',
    'error','errors',
    'bug','bug fix','bugfix','bugfixing','bugs',
    'issue','issues',
    'mistake','mistakes','mistaken',
    'incorrect',
    'fault','faults',
    'flaw','flaws',
    'failure','failures',
    'correction','corrections',
    'hotfix','regression','patch'
]

RMD_HINTS = (".rmd", ".qmd", "_site.yml", "_output.yml", "bookdown.yml")
RFILE_HINTS = (".r",)

# ---------- utils

def any_re(words: Iterable[str], word_boundaries=True) -> re.Pattern:
    parts = []
    for w in words:
        w = w.strip()
        if not w:
            continue
        pat = re.escape(w)
        # Add \b only for pure "word" tokens; phrases/punct rely on raw match.
        if word_boundaries and re.fullmatch(r"\w+", w, flags=re.UNICODE):
            pat = r"\b" + pat + r"\b"
        parts.append(pat)
    if not parts:
        return re.compile(r"$a", re.I)
    return re.compile("|".join(parts), re.I)

def load_keywords(args) -> List[str]:
    if args.keywords_file:
        with open(args.keywords_file, "r", encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip()]
    if args.keywords:
        return [s.strip() for s in args.keywords.split(",") if s.strip()]
    return DEFAULT_KEYWORDS

def normalize_repo_df(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    cols = {c.lower(): c for c in df.columns}

    def has(*names):
        return any(n.lower() in cols for n in names)

    if has("owner") and has("repo"):
        out = df[[cols["owner"], cols["repo"]]].rename(columns={cols["owner"]:"owner", cols["repo"]:"repo"})
    elif has("full_name"):
        s = df[cols["full_name"]].astype(str).str.strip()
        out = s.str.split("/", n=1, expand=True)
        out.columns = ["owner","repo"]
    elif has("url"):
        s = df[cols["url"]].astype(str).str.replace("https://github.com/","", regex=False)
        out = s.str.split("/", n=1, expand=True)
        out.columns = ["owner","repo"]
    else:
        raise SystemExit("repos CSV must have either (owner,repo) or full_name or url columns.")

    out = out.dropna().drop_duplicates().reset_index(drop=True)
    # guard against trailing slashes etc.
    out["owner"] = out["owner"].str.strip().str.strip("/")
    out["repo"]  = out["repo"].str.strip().str.strip("/")
    return out

def gh_get(url: str, params: Dict[str, Any] = None, token: Optional[str]=None, max_retries=5) -> requests.Response:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "rmd-defect-study/1.0",
    }
    if token:
        headers["Authorization"] = f"token {token}"
    for attempt in range(max_retries):
        r = requests.get(url, params=params, headers=headers)
        # Handle secondary rate limiting (403) or abuse detection with retry
        if r.status_code == 403 and "rate limit" in r.text.lower():
            reset = r.headers.get("X-RateLimit-Reset")
            wait_s = 60
            if reset:
                try:
                    wait_s = max(5, int(reset) - int(time.time()) + 2)
                except Exception:
                    wait_s = 60
            time.sleep(min(wait_s, 90))
            continue
        if r.status_code in (502, 503, 504):
            time.sleep(1.5 * (attempt + 1))
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r  # unreachable

def list_commits(owner: str, repo: str, token: Optional[str], since: Optional[str], until: Optional[str]) -> Iterable[Dict[str,Any]]:
    page = 1
    params = {"per_page": 100}
    if since: params["since"] = since
    if until: params["until"] = until
    while True:
        params["page"] = page
        resp = gh_get(f"{GITHUB}/repos/{owner}/{repo}/commits", params=params, token=token)
        data = resp.json()
        if not data:
            break
        for item in data:
            yield item
        page += 1

def get_commit_details(owner: str, repo: str, sha: str, token: Optional[str]) -> Dict[str,Any]:
    resp = gh_get(f"{GITHUB}/repos/{owner}/{repo}/commits/{sha}", token=token)
    return resp.json()

def is_merge_commit(commit_json: Dict[str,Any]) -> bool:
    try:
        return len(commit_json.get("parents", []) or []) > 1
    except Exception:
        return False

def extract_record(owner: str, repo: str, details: Dict[str,Any]) -> Dict[str,Any]:
    c = details.get("commit", {}) or {}
    author = c.get("author") or {}
    committer = c.get("committer") or {}
    files = details.get("files") or []
    filenames = [f.get("filename","") for f in files if f.get("filename")]
    touched_rmd = False
    touched_r = False
    for fn in filenames:
        l = fn.lower()
        if any((l.endswith(h) or h in l) for h in RMD_HINTS):
            touched_rmd = True
        if l.endswith(".r"):  # plain R files
            touched_r = True

    # assemble diff text
    patches = []
    added = deleted = changed = 0
    for f in files:
        if f.get("patch"):
            patches.append(f"---FILE: {f.get('filename')}---\n{f.get('patch')}")
        added   += int(f.get("additions", 0) or 0)
        deleted += int(f.get("deletions", 0) or 0)
        changed += int(f.get("changes",   0) or 0)

    return {
        "repo_owner": owner,
        "repo_name": repo,
        "commit_hash": details.get("sha",""),
        "author_name": author.get("name",""),
        "author_email": author.get("email",""),
        "author_date": author.get("date",""),
        "committer_name": committer.get("name",""),
        "committer_email": committer.get("email",""),
        "committer_date": committer.get("date",""),
        "message": c.get("message",""),
        "filenames": ";".join(filenames),
        "touches_rmd": touched_rmd,
        "touches_r": touched_r,
        "touches_r_or_rmd": (touched_r or touched_rmd),
        "is_merge": is_merge_commit(details),
        "added": added,
        "deleted": deleted,
        "changed": changed,
        "diff": "\n\n".join(patches)
    }

# ---------- main

def main():
    ap = argparse.ArgumentParser(description="Fetch all-history bug-like commits per repo (keyword filter).")
    ap.add_argument("--repos-csv", required=True, help="CSV with owner/repo or full_name or url columns.")
    ap.add_argument("--out-dir", required=True, help="Output folder for per-repo CSVs.")
    ap.add_argument("--keywords", help="Comma-separated keywords; defaults to curated list.")
    ap.add_argument("--keywords-file", help="Text file with one keyword/phrase per line.")
    ap.add_argument("--since", help="ISO8601 start date (e.g., 2010-01-01T00:00:00Z). Omit for full history.")
    ap.add_argument("--until", help="ISO8601 end date (default: none).")
    ap.add_argument("--skip-merges", action="store_true", help="Skip merge commits (default: off).")
    ap.add_argument("--require-rmd-touch", action="store_true",
                    help="Keep only commits that touch .Rmd/.qmd/_site.yml/_output.yml/bookdown.yml.")
    ap.add_argument("--require-r-or-rmd-touch", action="store_true",
                    help="Keep only commits that touch .R OR R Markdown artifacts (.Rmd/.qmd/_site.yml/_output.yml/bookdown.yml).")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing per-repo CSVs if present.")
    args = ap.parse_args()

    token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PAT")
    if not token:
        print("WARNING: No GITHUB_TOKEN/PAT set. You will hit rate limits quickly.", file=sys.stderr)

    os.makedirs(args.out_dir, exist_ok=True)
    kw_list = load_keywords(args)
    kw_re = any_re(kw_list, word_boundaries=True)
    repos = normalize_repo_df(args.repos_csv)

    for i, row in repos.iterrows():
        owner, repo = row["owner"], row["repo"]
        tag = f"{owner}_{repo}"
        out_csv = os.path.join(args.out_dir, f"{tag}_bug_commits.csv")

        if os.path.exists(out_csv) and not args.overwrite:
            print(f"[{i+1}/{len(repos)}] {tag}: exists, skipping (use --overwrite to refetch).")
            continue

        print(f"[{i+1}/{len(repos)}] {tag}: listing commits (all history{' since '+args.since if args.since else ''})...")
        matched: List[str] = []
        total_listed = 0
        for item in list_commits(owner, repo, token=token, since=args.since, until=args.until):
            total_listed += 1
            msg = ((item.get("commit") or {}).get("message") or "")[:10000]
            if kw_re.search(msg):
                matched.append(item.get("sha"))

        print(f"  -> listed {total_listed} commits, keyword-matched {len(matched)}.")

        rows: List[Dict[str,Any]] = []
        for idx, sha in enumerate(matched, 1):
            try:
                details = get_commit_details(owner, repo, sha, token=token)
                if args.skip_merges and is_merge_commit(details):
                    continue
                rec = extract_record(owner, repo, details)
                if args.require_r_or_rmd_touch and not rec["touches_r_or_rmd"]:
                    continue
                elif args.require_rmd_touch and not rec["touches_rmd"]:
                    continue
                rows.append(rec)
            except requests.HTTPError as e:
                print(f"    ! HTTPError on {sha}: {e}", file=sys.stderr)
                continue
            except Exception as e:
                print(f"    ! Error on {sha}: {e}", file=sys.stderr)
                continue

            # be polite to the API
            if idx % 50 == 0:
                time.sleep(0.3)

        if not rows:
            # still write an empty file for traceability
            pd.DataFrame(columns=[
                "repo_owner","repo_name","commit_hash","author_name","author_email",
                "author_date","committer_name","committer_email","committer_date",
                "message","filenames","touches_rmd","is_merge","added","deleted","changed","diff"
            ]).to_csv(out_csv, index=False)
            print(f"  -> saved 0 rows to {out_csv}")
            continue

        df = pd.DataFrame(rows)
        df.to_csv(out_csv, index=False)
        print(f"  -> saved {len(df)} rows to {out_csv}")

if __name__ == "__main__":
    main()
