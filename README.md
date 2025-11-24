# Empirical-analysis-of-defect-in-R-Markdown
This repository contains the data, scripts, and reproducible pipeline for a thesis project studying bug-fix commits in the R / R Markdown ecosystem.

We mine GitHub repositories, filter commits by **bug-fix keywords**, classify each commit into a **10-category defect taxonomy** using **diff-aware, R-specific rules**, and report per-repo and cross-repo defect distributions. For each commit we also record whether it touches **R source** (`.R`) and/or **R Markdown artifacts** (`.Rmd/.qmd/_site.yml/_output.yml/bookdown.yml`).

---

## Goals
- Build a high-quality dataset of **bug-keyword commits** from R/Rmd projects.
- Classify defect types with rules that prioritize **diff & file-path evidence** over generic message text.
- Provide **quality control (QC)** thresholds and **sensitivity analyses** to keep results robust and reproducible.

---

## Defect taxonomy (10 categories)
1. **Rendering / Conversion**  
2. **Dependency / Package**  
3. **Environment / Configuration**  
4. **Implementation / Logic**  
5. **Data / Input Handling**  
6. **Visualization / Plotting**  
7. **Reproducibility / Versioning**  
8. **File I/O and Export**  
9. **Documentation / Formatting**  
10. **Miscellaneous / Unknown**

---

## Pipeline overview
1. **Repository selection** (external step): CSV list of GitHub repos that meet activity criteria and contain R/Rmd artifacts.  
2. **Fetch** bug-keyword commits across full history (per repo).  
3. **Classify** each commit into the 10-category taxonomy (diff-aware + R-aware).  
4. **Validate** with audit/QC thresholds (PASS/WARN/FAIL).  
5. **Summarize** per-repo and **aggregate** cross-repo tables/plots.  
6. **Sensitivity** analyses (baseline vs. excluding/reassigning suspects).

---

## Repository layout

- `/scripts`
  - `fetch_bug_commits_all.py` — fetch bug-keyword commits (full history)
  - `batch_rmd_defect_analysis.py` — classify + generate per-repo outputs
  - `pass_fail_thresholds.py` — PASS/WARN/FAIL QC gate (single or batch)
  - `audit_one_repo.py` — flag message-based suspect relabels
  - `summarize_repo.py` — per-repo summaries (percentages, touch rates)
- `/data_bug` — output of fetch (one CSV per repo)
- `/analysis` — charts, examples, cross-repo summaries
- `repos_rmd_2022_candidates_passes.csv` — example repo list (owner/repo)

---

## Setup
- **Python**: 3.10+ recommended  
- **Install dependencies** (create a venv if you like):

    pip install pandas requests matplotlib

---

## GitHub authentication
Set a GitHub Personal Access Token (to avoid rate limits).

- **Windows (cmd):**

    set GITHUB_TOKEN=ghp_your_token_here

- **PowerShell:**

    $env:GITHUB_TOKEN = "ghp_your_token_here"

- **macOS/Linux (bash):**

    export GITHUB_TOKEN=ghp_your_token_here

> The token is only used by `fetch_bug_commits_all.py` to call the GitHub API.

---

## 1) Fetch bug-keyword commits (full history)

Run without any “require touch” flags to include **all bug-keyword commits**, while still recording whether they touch R or Rmd.

    python scripts/fetch_bug_commits_all.py \
      --repos-csv repos_rmd_2022_candidates_passes.csv \
      --out-dir data_bug \
      --skip-merges

**Key options** (optional):
- `--keywords` / `--keywords-file` — customize the keyword list (default includes: fix, bug, error, issue, incorrect, regression, patch, ...).
- `--skip-merges` — ignore merge commits.
- `--require-rmd-touch` — keep only commits that touch R Markdown artifacts. (Off by default.)
- `--require-r-or-rmd-touch` — keep only commits that touch `.R` **or** R Markdown artifacts. (Off by default.)
- `--overwrite` — overwrite per-repo CSV if it exists.

**Output (per repo):** `<owner>_<repo>_bug_commits.csv` with columns:
- `repo_owner, repo_name, commit_hash, message, author_date, ...`
- `filenames` (semicolon-joined), `touches_r`, `touches_rmd`, `touches_r_or_rmd`, `is_merge`
- `added, deleted, changed` and the unified **`diff`** (multi-line) for classification & audit

> Tip: For sharing/browsing, you can generate a *lean* version without the `diff` column.

---

## 2) Classify defect types

    python scripts/batch_rmd_defect_analysis.py --dir data_bug

**Summary of rules & scoring**
- Weights: **diff = 3, path = 3, message = 1** (message-only for *Implementation/Logic* is suppressed).
- Tie-break: prefer categories with **diff/path** evidence (e.g., `rmarkdown::render`, `ggplot(`, `README.Rmd`, `vignettes/`).
- Paths: ensure **both** `.R` and `.Rmd` are recognized as “code paths” for *Implementation/Logic*; rendering/docs use Rmd-centric cues.

**Outputs (per repo):**
- `<repo>_bug_commits_classified.csv` (commit → category + score + touches_r/md flags)  
- `<repo>_bug_commits_category_counts.png` (bar chart)  
- `<repo>_bug_commits_examples.csv` and `_examples_appendix.pdf` (illustrative commits)

**Cross-repo outputs (in `/analysis`):**
- `cross_repo_category_counts.csv`
- `cross_repo_category_totals.png`

> Note: Filenames may contain “_classified” or “_bug_commits_classified” depending on your run; keep them consistent in your repo.

---

## 3) QC gate: PASS / WARN / FAIL

**Single repo:**

    python scripts/pass_fail_thresholds.py --base data_bug/<REPO>/<REPO>_bug_commits --quiet

**Batch → CSV:**

    python scripts/pass_fail_thresholds.py --dir data_bug --out analysis/qc_summary.csv

**Thresholds**
- **Coverage ≥ 85%** (share with `category_score > 0`)
- **Low-confidence ≤ 15%** (share with `category_score ≤ 2`)
- **Unknown ≤ 10%**
- **Suspects ≤ 10%** — **WARN** if > **2%**

> `pass_fail_thresholds.py` can recompute suspects (message-only heuristic) if a saved `*_suspect_relabels.csv` isn’t present.

---

## 4) Per-repo summaries

Create percentages & touch rates next to the input CSV:

    py scripts/summarize_repo.py "data_bug/<REPO>/<REPO>_bug_commits.csv"

**Artifacts created:**
- `_category_percentages.csv`
- `_rmd_touch_by_category.csv`
- `_r_touch_by_category.csv`
- `_top_paths.csv` (if filenames available)

**Optional:** a four-way split across all commits (`R only`, `Rmd only`, `Both`, `Neither`) can be computed from the flags `touches_r`/`touches_rmd` for figures.

---

## Sensitivity analysis (robustness)
We provide three views to demonstrate robustness of category shares:
1. **Baseline** (original labels)
2. **Excluding suspects** (drop message-mismatch rows)
3. **Reassigned suspects** (map each suspect to its hinted category)

If the category ranking and major percentages are stable across these views, the conclusions are robust.

---

## Reproducibility & data hygiene
- Keep a **full** CSV (with `diff`) for classification/review and optionally a **lean** CSV (no `diff`) for readability.
- Multi-line `diff` cells may look like extra lines in raw viewers; use a CSV-aware tool (Excel import / pandas) to see them properly.
- Avoid committing secrets: **do not** commit your GitHub token.

---

## Known limitations / threats to validity
- **Keyword filter** may miss some non-keyword bug fixes (trade-off for precision/scale).
- **Rule-based labeling** can misclassify edge cases; we mitigate with diff/path weighting, suspect-relabel audits, and sensitivity analysis.
- **Project diversity** (size, domain) can influence category distribution; we report cross-repo variation and include QC gates.

---

## Results (fill as you go)
- QC summary: `analysis/qc_summary.csv`
- Cross-repo percentages: `analysis/cross_repo_category_counts.csv`
- Charts: `analysis/cross_repo_category_totals.png`

> Add a sentence or two here once you’ve run the full batch (e.g., “Implementation/Logic and Dependency/Package dominate across N repos; Rendering/Conversion and Documentation/Formatting show the highest `.Rmd` touch rates,” etc.).

---

## License & citation
- Add your preferred OSS license (`LICENSE` file).
- Cite the base empirical study you build on in your thesis/README and include these scripts and CSVs in your replication package.

---

## Contact
For questions or issues, open a GitHub issue or contact the author of the thesis project.

