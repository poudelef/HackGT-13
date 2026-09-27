# 08. Questionnaire design and pass conditions

## Principles

1. Ask for facts, never verdicts ("How many weeks...", never "Does the patient meet...").
2. One fact per question.
3. Typed answers: boolean, quantity, date, string, coding.
4. Follow-ups only when relevant (`enableWhen`).
5. Every "unless", "except", "or", "one of" becomes a branch.
6. Neutral wording.
7. Every question links to its rule, conditions (`covers`), and page.
8. Answerable from a chart.
9. Code writes pass conditions; the LLM only phrases text.

## Generation (hybrid)

1. Rule type and subtype select a template.
2. Code creates slots: link ids (`{criterion_key}.{part}`), answer types, units, fill methods, enableWhen, `covers`, and the pass condition from the rule's condition values and logic.
3. Exceptions and alternatives add branches; `any_of` logic yields one question set per alternative joined by `any`.
4. P5 phrases each slot's text; on failure the template default text is used and the item goes to `pending_review`.
5. Code checks and P6 run; then Gate 2 (`11`).

## Templates

| Type | Questions (suffix: type, fill) | Pass condition |
|---|---|---|
| diagnosis | `codes`: coding, code_lookup | `codes` prefix_in rule codes |
| lab | `value`: quantity, code_lookup; `date`: date, code_lookup | value op threshold and date within window |
| prior_treatment / medication | `prescribed`: boolean, code_lookup; `start`: date; `end`: date (optional) | prescribed and duration(start, end or today) >= threshold |
| prior_treatment / therapy | `received`: boolean, llm_quote or code_lookup; `weeks`: quantity, llm_quote_value or date_math; `last_date`: date, date_math | received and weeks >= threshold and last_date within window |
| duration | `onset`: date, date_math | at_least_ago(onset, threshold) |
| clinical_note | `documented`: boolean, llm_quote | documented = true |
| exclusion | `present`: boolean, code_lookup or llm_quote | present = false (unknown stays missing) |
| age | `age`: quantity (years), date_math from dob | within range |
| prescriber | `specialty`: coding, code_lookup; optional `consult`: boolean, llm_quote | specialty in list, or consult = true if allowed |
| any exception | `{name}`: boolean, llm_quote; `{name}_reason`: string, llm_quote | added as `any` alternative |

Follow-ups (`start`, `weeks`, `last_date`, `_reason`) are enabled only when their parent boolean is true. A therapy exception question is enabled when `received` is not true.

## Worked example

Rule (page 13): "At least 6 weeks of physical therapy within the past 6 months, unless physical therapy is contraindicated."

| link_id | Question | Type | Enabled when | Covers |
|---|---|---|---|---|
| pt_six_weeks.received | Has the patient received physical therapy for this condition? | boolean | always | pt_received |
| pt_six_weeks.weeks | How many weeks of physical therapy were completed? | quantity (weeks) | received = true | pt_duration |
| pt_six_weeks.last_date | What was the date of the most recent physical therapy session? | date | received = true | pt_recency |
| pt_six_weeks.contraindicated | Is physical therapy medically contraindicated for this patient? | boolean | received != true | pt_contraindicated |
| pt_six_weeks.contra_reason | What is the documented reason physical therapy is contraindicated? | string | contraindicated = true | pt_contraindicated |

## Pass condition language

```json
{ "any": [
  { "all": [
    { "q": "pt_six_weeks.received", "op": "eq", "value": true },
    { "q": "pt_six_weeks.weeks", "op": "gte", "value": 6, "unit": "weeks",
      "fail": "Physical therapy completed: {value} weeks; policy requires 6" },
    { "q": "pt_six_weeks.last_date", "op": "within", "value": 6, "unit": "months",
      "fail": "Most recent physical therapy on {value}; policy requires within 6 months" } ] },
  { "all": [
    { "q": "pt_six_weeks.contraindicated", "op": "eq", "value": true },
    { "q": "pt_six_weeks.contra_reason", "op": "exists" } ] } ] }
```

| Operator | Meaning |
|---|---|
| eq | equals |
| gte, gt, lte, lt | numeric compare; units converted in code |
| within | date within N days, weeks, months of today |
| at_least_ago | date at least N units before today |
| duration_gte | span between two answers (or answer and today) at least N |
| prefix_in | any coded answer starts with any listed prefix |
| in | value in list |
| exists | answer present and non-empty |

## Question checks (code)

```
for each rule:
  every condition_key covered by some question
  every number in question text equals a value of the conditions it covers
  no text matching /meet|qualif|satisf|eligib/ (leading)
  every pass condition leaf references an existing link_id
  every exception condition reachable through an any branch
```

## Human edits

At Gate 2 the reviewer may edit wording; numbers and units are re-checked; the edit is locked. Pass conditions are never edited directly; editing the rule's conditions rebuilds them. At Gate 3 a clinician-entered answer is evaluated like any other answer.
