# Data sources and licensing log

Fellowship contract s. 3(b): every source must be used in compliance with law,
third-party Terms of Service and upstream licences, and I must have the right to
re-publish anything included in the final deliverables. Record each check here.

| Source | Used for | Terms checked? | Can re-publish? | Notes |
|--------|----------|----------------|-----------------|-------|
| A2AJ case law (HuggingFace: SCC, ONCA, BCCA) | Case index, cross-validation | TODO | TODO | Confirm dataset licence/citation requirements |
| SCC RSS/JSON feeds (decisions.scc-csc.ca) | Leave-grant alerts | TODO | n/a (alerts only) | Confirm feed contains leave *grants* and what fields it exposes |
| SCC case dockets (scc-csc.ca) | Counsel/intervener data | TODO | TODO | Read site Terms and conditions; check scraping rate/limits |
| Ontario CA dockets | Stage 3 | TODO | TODO | |
| BC CA dockets | Stage 3 | TODO | TODO | |

## Open questions
- Publishing named individual counsel in an open dataset: any privacy or
  professional-conduct considerations? Decide before release.
- Which SCC Rules provisions drive the deadline calculator? Verify each
  deadline against the current Rules; do not hard-code from memory.
