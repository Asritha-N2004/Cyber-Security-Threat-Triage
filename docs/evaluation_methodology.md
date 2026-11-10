# Research evaluation

`python evaluation/study.py --count 50` runs six explicit ablation arms across fixed seeds: rules, fuzzy rules, single-agent recommendation, multi-agent investigation without a critic, multi-agent with independent validation, and multi-agent with validation plus bounded self-correction. `--provider mock` is the default; `--provider openai` requires configured credentials and incurs paid calls.

Model inputs exclude ground-truth labels. Injected discrepancies and known matching pairs are labeled separately by the generator. Reference corruption provides a fuzzy-recoverable case. Outputs record matching precision/recall, false-match rate, unmatched rate, exception/root-cause classification accuracy, abstention, validation pass rate, escalation, attempt counts, latency and available token usage. Human acceptance, infrastructure cost and real financial resolution are not fabricated; unavailable measures remain null or explicitly zero for unperformed external resolution.

Mock results are software/control baselines, not evidence of LLM reasoning quality. `evaluation/results.json` is a reproducible mock study output. No superiority, production calibration or real-world efficiency claim is made. `evaluation/run.py` also retains the small baseline and explicitly injected unbalanced-proposal repair experiment.

ML ranking uses Decimal-derived numeric features and pairwise character TF-IDF text similarity, Logistic Regression or Random Forest, held-out precision/recall, Brier score and reliability bins. Training consumes audited human accept/reject decisions; training/test job IDs and underlying records must be disjoint. Models are versioned in tenant-scoped database artifacts and only rank candidates. Ranking cannot accept matches or bypass deterministic financial constraints. Scores are labeled uncalibrated.

A publication-grade study still requires representative independent datasets, adequate sample sizes, uncertainty intervals, blinded human assessment, actual paid-provider runs when intended, and organization-specific cost/acceptance/resolution measurement. Those experiments cannot be substituted by deterministic mock output.
