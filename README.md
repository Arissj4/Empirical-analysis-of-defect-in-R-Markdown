# Empirical-analysis-of-defect-in-R-Markdown

This repository contains the data, scripts, and reproducible pipeline for a thesis project studying bug-fix commits in the R / R Markdown ecosystem.

We mine GitHub repositories, filter commits by **bug-fix keywords**, classify each commit into a **10-category defect taxonomy** using **diff-aware, R-specific rules**, and report per-repo and cross-repo defect distributions. For each commit we also record whether it touches **R source** (`.R`) and/or **R Markdown artifacts** (`.Rmd/.qmd/_site.yml/_output.yml/bookdown.yml`).

The repository includes the complete results of the final batch run: **57 repositories analyzed**, with QC status per repository (currently **53 PASS**, **4 FAIL**) stored in `analysis/qc_summary.csv`. All thesis analyses are based on the **QC-passing subset**.

---

## Goals
- Build a high-quality dataset of **bug-keyword commits** from R/Rmd projects by mining full GitHub histories.
- Classify defect types using a **diff-aware, path-aware, and R-aware** rule-based system rather than message-only heuristics.
- Apply strict **quality control (QC) thresholds** (coverage, low-confidence, unknown, suspects) to ensure reliable and reproducible results.
- Provide per-repo and cross-repo **defect distributions**, including `.R` / `.Rmd` touch rates for studying reproducible-research workflows.
- Enable fully reproducible results through a transparent, script-driven pipeline and published intermediate artifacts.

---

## Defect taxonomy (10 categories)

Each bug-keyword commit is classified into one of the following ten categories using a diff-aware, file-path-aware, R-specific scoring system:

1. **Rendering / Conversion**  
   Issues related to knitting, rendering, HTML/PDF output, `rmarkdown::render()`, or format conversion.
2. **Dependency / Package**  
   Missing/updated packages, version conflicts, namespace errors, or dependency breakages.
3. **Environment / Configuration**  
   Problems with project configuration, working directory, environment variables, options, YAML configs, or build settings.
4. **Implementation / Logic**  
   Incorrect computations, wrong function behavior, algorithmic bugs, or logic errors in `.R` or code chunks.
5. **Data / Input Handling**  
   Issues in loading, cleaning, parsing, or validating input data.
6. **Visualization / Plotting**  
   Bugs in plotting libraries (e.g., ggplot2), layout issues, plotting errors, or graphical output.
7. **Reproducibility / Versioning**  
   Breakages due to version mismatches, reproducibility failures, or non-deterministic behavior.
8. **File I/O and Export**  
   Reading/writing files, export failures, missing output files, or path resolution issues.
9. **Documentation / Formatting**  
   Errors in Markdown text, formatting, vignettes, README files, or inline documentation.
10. **Miscellaneous / Unknown**  
   Commits where evidence is insufficient or unclear, or that do not fit any other category.

---

## Pipeline overview

1. **Repository selection** (external step)  
   Start from a CSV containing GitHub repositories that satisfy activity criteria and include R/Rmd artifacts.

2. **Fetch** bug-keyword commits (full history)  
   `fetch_bug_commits_all.py` mines each repository, filters by bug-fix keywords, records diff, filenames, and R/Rmd touch flags.

3. **Classify** commits into the 10-category defect taxonomy  
   `batch_rmd_defect_analysis.py` runs the diff-aware, path-aware, R-aware classifier and generates all per-repo classification files.

4. **QC evaluation** (PASS / FAIL per repository)  
   `batch_qc_all.py` applies strict thresholds (coverage, low-confidence, unknown, suspects) and produces a global `qc_summary.csv`.

5. **Summarize** per-repo results and compute cross-repo aggregates  
   `summarize_repo.py` creates category percentages + `.R` / `.Rmd` touch summaries; cross-repo tables and plots live in `/analysis`.

6. **Sensitivity analysis**  
   Compare baseline labels vs. “exclude suspects” vs. “reassign suspects.”  
   (In the final dataset, suspects = 0%, so the sensitivity results are stable.)

---

## Repository layout

- `/scripts`
  - `fetch_bug_commits_all.py` — fetch full-history bug-keyword commits from GitHub
  - `batch_rmd_defect_analysis.py` — classify commits (diff-aware, path-aware, R-aware)
  - `batch_qc_all.py` — compute QC metrics for all repositories and produce `qc_summary.csv`
  - `pass_fail_thresholds.py` — QC evaluation for a single repo or directory
  - `audit_one_repo.py` — optional suspect-relabelling audit (message-based)
  - `summarize_repo.py` — per-repo summaries (category percentages, R/Rmd touch rates)

- `/data_bug`  
  Contains all raw and classified bug-commit datasets.  
  Each repository has:
  - `<repo>_bug_commits.csv`
  - `<repo>_bug_commits_classified.csv`
  - `<repo>_classified_category_percentages.csv`
  - Additional per-repo QC and summary files

- `/analysis`  
  Contains cross-repo outputs:
  - `qc_summary.csv` (final QC table — 53 PASS, 4 FAIL)
  - cross-repo category counts and percentages
  - aggregate charts and visualizations

- `repos_rmd_2022_candidates_passes.csv`  
  Example input list of repositories (owner/repo pairs).

---

## Setup
- **Python**: 3.10+ recommended  
- **Install dependencies**:

```bash
pip install pandas requests matplotlib
```


---

## GitHub authentication
To avoid GitHub API rate limits, set a GitHub Personal Access Token (classic) before running  
`fetch_bug_commits_all.py`.

- **Windows (cmd):**

    set GITHUB_TOKEN=ghp_your_token_here

- **PowerShell:**

    $env:GITHUB_TOKEN = "ghp_your_token_here"

- **macOS/Linux (bash):**

    export GITHUB_TOKEN=ghp_your_token_here

> The token is used only for GitHub API requests during the fetch step.
> None of the other scripts requires authentication.

---

## 1) Fetch bug-keyword commits (full history)

Run without any “require touch” flags to include **all bug-keyword commits**, while still recording whether they touch R or Rmd artifacts.

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

> Tip: for sharing/browsing, you can also derive a lean version without the diff column while keeping the full version for analysis.

---

## 2) Classify defect types

Run the R/Rmd-aware classifier on all fetched bug-keyword commits:

    python scripts/batch_rmd_defect_analysis.py --dir data_bug

This script reads each \<owner>_\<repo>_bug_commits.csv, applies a diff-aware, path-aware, R-aware scoring system, and assigns each commit to one of the 10 defect categories.

**Summary of rules & scoring**
- Weights: **diff = 3, path = 3, message = 1** (message-only for *Implementation/Logic* is suppressed).
- Tie-break: prefer categories with **diff/path** evidence (e.g., `rmarkdown::render`, `ggplot(`, `README.Rmd`, `vignettes/`).
- Paths: ensure **both** `.R` and `.Rmd` are recognized as “code paths” for *Implementation/Logic*; rendering/docs use Rmd-centric cues and R Markdown–specific files.

**Outputs (per repo):**
- `<repo>_bug_commits_classified.csv` (commit → category + score + touches_r/md flags)  
- `<repo>_bug_commits_category_counts.png` (bar chart)  
- `<repo>_bug_commits_examples.csv` and `<repo>_bug_commits_examples_appendix.pdf` (illustrative commits)

**Cross-repo outputs (in `/analysis`):**
- `cross_repo_category_counts.csv`
- `cross_repo_category_totals.png`

> Note: Filenames may contain “_classified” or “_bug_commits_classified” depending on your run; keep them consistent in your repo.

---

## 3) QC gate: PASS / WARN / FAIL

Evaluate the quality of each repository’s classification results using consistency and coverage thresholds.

**Single repo:**

    python scripts/pass_fail_thresholds.py --base data_bug/<REPO>/<REPO>_bug_commits --quiet

**Batch mode → produce full QC summary:**

    python scripts/batch_qc_all.py --dir data_bug --out analysis/qc_summary.csv

**QC thresholds**
A repository is marked PASS only if it satisfies all of the following:
- **Coverage ≥ 85%**
  `Share of bug-keyword commits with a non-zero category score.`
- **Low-confidence ≤ 15%**
  `Share of commits classified with score ≤ 2.`
- **Unknown ≤ 10%**
  `Commits receiving total score = 0.`
- **Suspects ≤ 10%**
  `(With a WARN flag if suspects > 2%)`

> `pass_fail_thresholds.py` can recompute suspects (message-only heuristic) if a saved `*_suspect_relabels.csv` isn’t present.

**Final QC results (full dataset)**
After running the full pipeline:
- **Repositories analyzed: 57**
- *Pass: 53*
- **Fail: 4**
- **Unknown commits: 0% across all repositories**
- **Suspects: 0% across all repositories**

The main quantitative analysis in the thesis is based on the 53 QC-passing repositories.  
The 4 failing repositories are retained for transparency and are analyzed separately through manual inspection and qualitative discussion.

`analysis/qc_summary.csv` contains the full PASS/FAIL table with per-repo metrics.

---

## 4) Per-repo summaries

Generate additional summaries for each repository to support both per-project analysis and cross-repo aggregation:

    py scripts/summarize_repo.py "data_bug/<REPO>/<REPO>_bug_commits.csv"

**Artifacts created (per repo):**
- `<repo>_classified_category_percentages.csv`
  Percentage of commits in each defect category.
- `<repo>_rmd_touch_by_category.csv`
  R Markdown touch rates by defect category.
- `<repo>_r_touch_by_category.csv`
  R source touch rates by defect category.
- `<repo>_top_paths.csv`
  Most frequently modified paths associated with defect types (if filenames available).

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

