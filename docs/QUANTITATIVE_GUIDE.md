# Quantitative Guide

## Supported files
XLSX, XLS, CSV, TSV, TXT (delimited), JSON (array or records), JSONL, tables inside DOCX and text-based PDFs.
Several tables on one sheet separated by blank rows become separate datasets. Encoding and delimiters are detected.

## Data understanding
Each column gets a suggested **type** (categorical, numeric, integer, date, boolean, string, ignore) and **role**
(identifier, sex, age, geography levels, origin/destination, coordinates, date, round, weight, binary, multiple
response, measure, score, personal name, phone, free text) with a confidence and the reasons. Columns that may contain
personal data are flagged. Nothing is final until you confirm; the confirmation is audited.

**Unit of analysis matters.** Households, individuals, assistance events and movements are counted separately and never added together.

## Quality and cleaning
Checks: missingness, sentinel codes (-99, 999, "don't know"), out-of-range ages/household sizes/coordinates, extreme
values (3×IQR, flagged not removed), duplicates (rows and IDs), inconsistent category spellings, consent.
Operations: trim whitespace, standardise categories, set missing codes, drop duplicates, flag outliers, set out-of-range
to missing, recode, band numeric values, rename, exclude rows by condition, weighted-sum scores.
Each is previewed (rows/cells affected), approved, applied to the analytical copy only, and can be reverted.

## Statistics
Descriptives (weighted or not), frequencies (single and multiple response), cross-tabulations with chi-square or
Fisher's exact test and Cramér's V, group comparisons (Welch t / Mann–Whitney / ANOVA / Kruskal–Wallis with normality
checks), Spearman/Pearson correlation, time series, ETS forecast (≥12 monthly observations), anomalies (robust z),
OLS regression (minimum sample size enforced, heteroskedasticity check). Tests state assumptions and caveats. Lucerna
reports associations, not causes.

## Indicators
Types: percentage, count, unique count, mean, median, sum, ratio. Conditions are structured (column, operator, values),
never free code. Percentages include a Wilson 95% interval. Status moves provisional → configured → verified (verification
by a Project/MEAL Manager). Every calculation is stored with the dataset version and a configuration hash.

## Templates
`lucerna/quant/templates.py` documents WFP FCS weights and rCSI severity weights with sources; apply them with a
weighted-sum transformation.

## Comparisons
Choose two datasets (rounds, baseline/endline). Lucerna checks units of analysis, column types and category overlap
before comparing, then reports changes with two-proportion z-tests or Welch/Mann–Whitney tests, assuming independent samples.
