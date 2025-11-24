# Empirical-analysis-of-defect-in-R-Markdown
This repository contains the data, scripts, and reproducible pipeline for a thesis project studying bug-fix commits in the R / R Markdown ecosystem.
# Empirical Analysis of Defects in R & R Markdown

This repository contains the data, scripts, and reproducible pipeline for a thesis project studying **bug-fix commits** in the R / R Markdown ecosystem. We mine GitHub repositories, filter commits by **bug-fix keywords**, classify each commit into a **10-category defect taxonomy** using **diff-aware, R-specific rules**, and report per-repo and cross-repo defect distributions. For each commit we also record whether it touches **R source** (`.R`) and/or **R Markdown artifacts** (`.Rmd/.qmd/_site.yml/_output.yml/bookdown.yml`).

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
