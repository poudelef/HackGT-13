# 10. Prompts

Prompts live in `pa-engine/app/prompts/`. Every call: temperature 0, JSON only, schema included, pydantic validation, one repair retry with the validation error. No prompt names an insurer, plan, or fixed service list. No prompt asks a model to decide anything about a patient's health or coverage.

| Prompt | Model | Used in |
|---|---|---|
| P-ID plan identity | OpenAI | Ingestion stage 6 |
| P0 coverage | OpenAI | Benefit summary route |
| P1 rules | OpenAI | Clinical policy route |
| P1-D drug block | OpenAI | Drug criteria route |
| P2 judge | Gemini or Grok | Ingestion stage 11 |
| P3 facts | OpenAI | Report extraction |
| P4 quote, P4b quote and value | OpenAI | Answer filling |
| P5 question phrasing | OpenAI | Ingestion stage 12 |
| P6 question judge | Gemini or Grok | Ingestion stage 12 |
| P-SVC service match | OpenAI | Order matching |
| P-NOTE synthetic note writer | OpenAI | Synthetic generator only (`15`), never the engine |

## Shared block for extraction prompts (P0, P1, P1-D)

```
- Blocks marked CONTEXT ONLY and the memory blocks are for understanding. Never extract from them or cite their pages.
- Do not repeat items listed in items_found.
- If a requirement starts on the last target page and continues beyond it, return it as open_item.
- If a target page completes the open_item, return the full item citing the page where it started.
- Return memory_updates: {"definitions":[{"term","text","page","evidence"}],"markers":[{"marker","meaning","page","evidence"}],"open_item":{...}|null}
- Every evidence string must be copied exactly from a target page. Use page numbers exactly as labeled.
```

## P-ID

```
From the first pages of an insurance document, return who issued it and for which plan.
Return JSON only: {"insurer":{"value":str|null,"evidence":str|null,"page":int|null},
"plan_name":{...},"plan_year":{...},"document_title":{...}}
Evidence must be copied exactly. Return null when not stated. Never guess.
```

## P0 coverage

```
You read benefit summary or evidence of coverage pages and list services and whether each requires prior authorization.
Return JSON only: {"coverage":[{"service_label":"as written","service_codes":["as written"],"pa_required":bool,
"page":int,"evidence_text":"exact sentence or table cell","marker_used":str|null,"reference":str|null}],"memory_updates":{...}}
- Only services the text explicitly addresses.
- pa_required true only when the text says authorization, precertification, preauthorization, or prior approval is required,
  or uses a marker defined (in memory or on the page) as meaning that; then set marker_used.
```

## P1 rules

```
You extract prior authorization criteria from a clinical policy. You never make decisions about any patient.
Return JSON only: {"criteria":[{
 "criterion_key":"snake_case","requirement_text":"one plain sentence",
 "criterion_type":"diagnosis|lab|prior_treatment|duration|clinical_note|exclusion|age|prescriber",
 "subtype":"medication|therapy|null","logic":"all_of|any_of","policy_page":int,
 "applies_to":["services or codes as written"],"codes":["as written"],
 "conditions":[{"condition_key":"snake_case","text":"policy words","kind":"requirement|exception|alternative",
   "value":number|null,"unit":"days|weeks|months|years|percent|null"}]}],"memory_updates":{...}}
- Only requirements explicitly stated. Skip administrative steps.
- Split into atomic conditions: "6 weeks within 6 months" is two conditions.
- Every unless, except, or becomes its own condition.
- "All of the following" is logic all_of; "one of the following" is any_of with alternative conditions.
- Copy numbers and units exactly.
```

## P1-D drug block

```
You extract prior authorization criteria for one drug block.
Return JSON only: {"block_label":"as written","criteria":[P1 schema],"coverage_duration":{"text":str,"page":int}|null}
Required medical information and other criteria: rules of the matching type. Exclusion criteria: type exclusion, one per condition.
Age restrictions: type age. Prescriber restrictions: type prescriber, specialties as written. Coverage duration: metadata, not a criterion.
Use only text inside the block. Copy numbers, units, drug names exactly.
```

## P2 judge

```
You check one extracted item against the page it came from. You flag risk; you never approve or deny.
Return JSON only: {"verdict":"ACCURATE|WRONG_VALUE|HALLUCINATED|VAGUE","reason":"one sentence"}
ACCURATE: the page states it, including every number, unit, code, duration, and exception.
WRONG_VALUE: stated, but a number, unit, code, duration, or exception differs or is missing.
HALLUCINATED: the page does not state it.
VAGUE: implied but ambiguous.
Use only the page text.
```

## P3 facts

```
You convert one clinical document into structured facts. Copy only what is written.
Return JSON only: {"author_name":str|null,"document_date":"YYYY-MM-DD"|null,
"facts":[{"record_kind":"diagnosis|medication|lab|procedure|referral","code":str|null,
"code_system":"ICD-10|RxNorm|LOINC|CPT|null","display":str,"value":str|null,"unit":str|null,
"start_date":"YYYY-MM-DD"|null,"end_date":"YYYY-MM-DD"|null}]}
Never infer a diagnosis, code, or date that is not written.
```

## P4 quote and P4b quote with value

```
P4: Find text in the note that answers the question. Return {"quote":"exact text"|null}.
Copy character for character. Shortest complete phrase. Null if not answered. Do not judge any requirement.

P4b: Find text that states the requested value. Return {"quote":"exact"|null,"value":number|null,"unit":str|null}.
The quote must contain the number returned.
```

## P5 phrasing

```
Write clear, neutral questionnaire questions. You receive a requirement and slots (link_id, answer type, conditions).
Return JSON only: {"questions":[{"link_id":"as given","text":"one question"}]}
Ask for a fact, never whether the patient meets or qualifies. Keep every number and unit exactly.
Add nothing not in the slot. Plain English a clinician can answer from a chart.
```

## P6 question judge

```
Check whether questions fully and only capture one requirement.
Return JSON only: {"verdict":"complete|missing_condition|added_condition|leading","detail":"one sentence"}
```

## P-SVC

```
Match an order to plan document items. Return {"candidates":[{"item_key":str,"matched_phrase":"exact text from the item's label or applies_to"}]}.
Return every plausible candidate or none. Do not choose between close candidates.
```

## P-NOTE (synthetic generator only)

```
Write a realistic clinical note for a SYNTHETIC patient from the outline.
Return JSON only: {"note_text":str}
You MUST include every sentence in required_sentences exactly as written.
You MUST NOT mention any topic in forbidden_topics.
Use only the names, dates, and facts given. Do not add diagnoses, medications, or results not in the outline.
```

## Change rule

After any prompt change: `pytest`, `scripts/eval.py`, and a `memory.md` entry with before and after numbers. False met above zero blocks the merge.
