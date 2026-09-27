# 14. Real insurance documents

## What to collect (one plan, aligned)

| Role | Purpose | What to look for |
|---|---|---|
| benefit_summary | Is PA required | Plan's Evidence of Coverage or Summary of Benefits, with a benefits chart marking PA |
| clinical_policy | Criteria for one imaging service | The same insurer's public medical or clinical policy for lumbar spine MRI, or the imaging vendor guideline the EOC names |
| drug_criteria | Criteria for one drug | The same plan's published Part D prior authorization criteria document |

Alignment matters more than quantity: the clinical policy and drug criteria should belong to the same insurer (and ideally plan year) as the benefit summary, so the coverage gate and criteria connect.

## Where to find them

1. Medicare Advantage and Part D plan websites: EOC, formulary, PA criteria PDFs. Medicare Advantage plans must also post internal coverage criteria they use beyond Medicare rules.
2. Insurer public medical policy libraries.
3. Imaging benefit manager guideline pages, when the insurer delegates imaging.
4. CMS Medicare Coverage Database (national and local coverage determinations).

Time box: 45 minutes total. Prefer text-based PDFs. Choose one imaging service and one common PA drug.

## Storing them (R6)

- PDFs are **not committed** to the public repo (`.gitignore` on `data/policies/*.pdf`).
- `data/policies/SOURCES.md` is committed: title, insurer, role, URL, download date, sha256.
- `scripts/download_docs.py` downloads each URL and verifies the sha256.
- Caches and audits contain only short evidence quotes with page citations.

## Second insurer (generality proof)

Ingest at least one benefit summary or clinical policy from a second insurer (no patient flow needed) and record the cascade tier, items, and verdicts in `memory.md`. This proves nothing is hardcoded.

## Fallback

If no aligned real set is found in the time box: use the best real documents available, even from different insurers, and state it. Only if a role has no usable real document, write a short fictional one modeled on published criteria, upload with `source_kind = fictional_fallback`; the UI and packet label it everywhere.
