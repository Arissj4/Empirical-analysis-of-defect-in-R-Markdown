#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
find_rmd_repos_2022.py

Find GitHub repositories that are suitable for an R Markdown defect study,
AND enforce 2022 activity/keyword conditions:

Required (configurable):
1) Repo had activity in 2022 (>= 1 commit between 2022-01-01 and 2022-12-31).
2) Repo had at least N commits in 2022 (default: 24).
3) At least K commits in 2022 have "bug-like" keywords in their messages.

It also enforces R Markdown evidence (Rmd/config/render/knit/bookdown).

Usage
-----
export GITHUB_TOKEN=your_personal_access_token_here   # STRONGLY recommended
pip install requests

# Broad search + 2022 screening, output CSV of repos that meet all conditions:
python find_rmd_repos_2022.py \
  --stars-min 10 \
  --min-commits-2022 24 \
  --min-buglike-commits-2022 5 \
  --out repos_rmd_2022_candidates.csv

# Options:
#   --require-r-bytes                require some R bytes in languages
#   --require-description            require DESCRIPTION file (R package)
#   --include-quarto                 also look for .qmd / "quarto render"
#   --keywords "fix,bug,issue,error,crash,regression,hotfix,patch,revert"   # override built-ins
#   --max-repos 1200                 limit processing for speed
#   --skip-merges                    exclude merges from keyword matching (default: on)
#   --only-from-file repos.csv       read repos from CSV (column 'full_name') instead of searching

Notes
-----
- API rate limits apply: use a token to get 5000 requests/hour.
- The search step (code search) returns up to 1000 repos per query; we deduplicate across multiple queries.
- Commit enumeration uses the REST API with since/until and paginates at 100 per page.
- This is a single-threaded, conservative script designed for reliability.
"""

import os
import sys
import time
import csv
import argparse
from datetime import datetime, timezone
from urllib.parse import quote_plus

import requests

GITHUB = "https://api.github.com"
TOKEN = os.getenv("GITHUB_TOKEN", "").strip()

def log(msg, *a, **k):
    print(msg, *a, file=sys.stderr, **k)

def gh_get(url, params=None, accept=None):
    headers = {
        "Accept": accept or "application/vnd.github+json",
        "User-Agent": "rmarkdown-defect-finder-2022"
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    r = requests.get(url, headers=headers, params=params, timeout=30)
    if r.status_code == 403 and "rate limit" in r.text.lower():
        reset = r.headers.get("X-RateLimit-Reset")
        if reset:
            wait = max(int(reset) - int(time.time()) + 5, 5)
            log(f"[rate-limit] Sleeping {wait}s until reset...")
            time.sleep(wait)
            return gh_get(url, params=params, accept=accept)
    r.raise_for_status()
    return r

def search_code(q, per_page=100, max_pages=10):
    """Yield code-search items for query q."""
    for page in range(1, max_pages+1):
        params = {"q": q, "per_page": per_page, "page": page}
        resp = gh_get(f"{GITHUB}/search/code", params=params)
        data = resp.json()
        items = data.get("items", [])
        for it in items:
            yield it
        if len(items) < per_page:
            break
        time.sleep(0.15)

def get_repo(full_name):
    return gh_get(f"{GITHUB}/repos/{full_name}").json()

def get_langs(full_name):
    try:
        return gh_get(f"{GITHUB}/repos/{full_name}/languages").json()
    except requests.HTTPError:
        return {}

def has_description(full_name):
    try:
        gh_get(f"{GITHUB}/repos/{full_name}/contents/DESCRIPTION")
        return True
    except Exception:
        return False

def list_commits_2022(full_name, per_page=100, skip_merges=True):
    """Iterate commits in 2022 for a repo, optionally skipping merges."""
    since = "2022-01-01T00:00:00Z"
    until = "2022-12-31T23:59:59Z"
    page = 1
    while True:
        params = {"since": since, "until": until, "per_page": per_page, "page": page}
        # "application/vnd.github+json" is fine; we don't need the commit search preview headers
        resp = gh_get(f"{GITHUB}/repos/{full_name}/commits", params=params)
        items = resp.json()
        if not items:
            break
        for it in items:
            msg = ((it.get("commit") or {}).get("message") or "") if isinstance(it, dict) else ""
            if skip_merges and msg.startswith("Merge "):
                continue
            yield it
        if len(items) < per_page:
            break
        page += 1
        time.sleep(0.05)

def match_buglike(message, keywords):
    msg = (message or "").lower()
    return any(kw in msg for kw in keywords)

def main():
    ap = argparse.ArgumentParser(description="Find R Markdown repos that meet 2022 activity/keyword conditions.")
    ap.add_argument("--stars-min", type=int, default=10)
    ap.add_argument("--min-commits-2022", type=int, default=24)
    ap.add_argument("--min-buglike-commits-2022", type=int, default=5)
    ap.add_argument("--require-r-bytes", action="store_true")
    ap.add_argument("--require-description", action="store_true")
    ap.add_argument("--include-quarto", action="store_true")
    ap.add_argument("--max-repos", type=int, default=1200)
    ap.add_argument("--skip-merges", action="store_true", default=True)
    ap.add_argument("--keywords", type=str, default="fix, bug, bugfix, issue, error, crash, regression, hotfix, patch, revert, failing test, failure, broken")
    ap.add_argument("--only-from-file", type=str, default=None, help="CSV with a 'full_name' column; skip search and only screen these repos")
    ap.add_argument("--out", type=str, default="repos_rmd_2022_candidates.csv")
    args = ap.parse_args()

    keywords = [k.strip().lower() for k in args.keywords.split(",") if k.strip()]

    # Build the initial repo set
    repos = {}

    if args.only_from_file:
        # Read repos from CSV (column 'full_name')
        import pandas as pd
        df = pd.read_csv(args.only_from_file)
        if "full_name" not in df.columns:
            # try to guess
            for c in df.columns:
                if c.lower() == "full_name":
                    df = df.rename(columns={c: "full_name"})
                    break
        for rn in df["full_name"].dropna().astype(str).unique().tolist():
            repos[rn] = {"full_name": rn, "reasons": set(["from_file"])}
        log(f"[info] Loaded {len(repos)} repos from file.")
    else:
        queries = [
            'extension:Rmd',
            'filename:_site.yml',
            'filename:_output.yml',
            'filename:bookdown.yml',
            'rmarkdown::render language:R',
            'knitr::knit language:R',
            'bookdown::render_book language:R',
            'path:vignettes extension:Rmd',
        ]
        if args.include_quarto:
            queries += ['extension:qmd', 'quarto render']

        log("[info] Searching GitHub code for R Markdown signals...")
        for q in queries:
            for item in search_code(q):
                repo = item.get("repository", {})
                full_name = repo.get("full_name")
                if not full_name:
                    continue
                entry = repos.setdefault(full_name, {"full_name": full_name, "reasons": set()})
                entry["reasons"].add(q)
                if len(repos) >= args.max_repos:
                    break
            if len(repos) >= args.max_repos:
                break
        log(f"[info] Found {len(repos)} unique repos from code search (capped at {args.max_repos}).")

    # Fetch metadata and apply repo-level filters
    screened = []
    for i, (full_name, entry) in enumerate(sorted(repos.items()), start=1):
        try:
            meta = get_repo(full_name)
            langs = get_langs(full_name)
            is_desc = has_description(full_name) if args.require_description else None
        except Exception as e:
            log(f"[warn] Skipping {full_name}: {e}")
            continue

        fork = bool(meta.get("fork", False))
        archived = bool(meta.get("archived", False))
        stars = int(meta.get("stargazers_count", 0))
        pushed_at = meta.get("pushed_at")  # ISO8601 or None
        html_url = meta.get("html_url", "")
        topics = meta.get("topics") or []

        # Basic filters
        if fork or archived:
            continue
        if stars < args.stars_min:
            continue
        if args.require_r_bytes and (langs.get("R", 0) <= 0):
            continue
        if args.require_description and not is_desc:
            continue

        screened.append({
            "full_name": full_name,
            "html_url": html_url,
            "stars": stars,
            "pushed_at": pushed_at,
            "r_bytes": langs.get("R", 0),
            "topics": ";".join(topics),
            "reasons": "; ".join(sorted(entry.get("reasons", []))),
        })

        if i % 50 == 0:
            log(f"[info] Screened {i} repos...")

        time.sleep(0.1)

    log(f"[info] Repo-level screening passed: {len(screened)} repos. Checking 2022 commits...")

    # For each screened repo, enumerate 2022 commits and count bug-like messages
    out_rows = []
    for j, rec in enumerate(screened, start=1):
        full_name = rec["full_name"]
        total_2022 = 0
        buglike_2022 = 0
        updated_in_2022 = False

        try:
            for c in list_commits_2022(full_name, skip_merges=args.skip_merges):
                total_2022 += 1
                updated_in_2022 = True
                msg = ((c.get("commit") or {}).get("message") or "")
                if match_buglike(msg, keywords):
                    buglike_2022 += 1
        except Exception as e:
            log(f"[warn] Commits scan failed for {full_name}: {e}")
            continue

        passes = (updated_in_2022 and
                  (total_2022 >= args.min_commits_2022) and
                  (buglike_2022 >= args.min_buglike_commits_2022))

        out_rows.append({
            **rec,
            "commits_2022": total_2022,
            "buglike_2022": buglike_2022,
            "buglike_share_2022": round((buglike_2022 / total_2022 * 100.0), 1) if total_2022 > 0 else 0.0,
            "updated_in_2022": updated_in_2022,
            "passes_thresholds": passes,
        })

        if j % 25 == 0:
            log(f"[info] Checked 2022 activity for {j} repos...")

        time.sleep(0.05)

    # Save CSV
    out = args.out
    fieldnames = ["full_name","html_url","stars","pushed_at","r_bytes","topics","reasons",
                  "commits_2022","buglike_2022","buglike_share_2022","updated_in_2022","passes_thresholds"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    # Convenience: also write a filtered list (passes only)
    passes_out = out.replace(".csv", "_passes.csv")
    with open(passes_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in out_rows:
            if r["passes_thresholds"]:
                w.writerow(r)

    log(f"[done] Wrote {len(out_rows)} repos to {out} (and passing repos to {passes_out}).")

if __name__ == "__main__":
    main()
