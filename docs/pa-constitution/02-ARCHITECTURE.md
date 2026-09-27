# 02. Architecture

## System context

```mermaid
flowchart LR
  Doctor([Doctor]) --> Web[Next.js app on Vercel]
  Reviewer([Policy reviewer]) --> Admin[/admin/policies/]
  Web -- REST --> Engine[PA engine, FastAPI]
  Admin -- REST --> Engine
  Synth[Synthetic generator CLI] --> DB
  Engine --> DB[(Supabase Postgres)]
  Engine --> Store[(Supabase Storage)]
  Engine --> OpenAI[OpenAI: extract, phrase, quotes]
  Engine --> Judge[Gemini or Grok: judge]
  DB -- Realtime --> Web
```

## Components

```mermaid
flowchart TB
  API[api routers] --> Runner[pipeline_runner]
  Runner --> Ingest[ingestion services]
  Runner --> Ctx[context_builder]
  Runner --> Mem[working_memory]
  API --> Review[review]
  API --> Check[check engine]
  API --> Fhir[fhir engine]
  Ingest --> Pre[precheck, cascade]
  Ingest --> Ext[extractors]
  Ingest --> Val[grounding, judges]
  Ingest --> QB[question_builder]
  Check --> Match[service_matcher, coverage_gate]
  Check --> Fill[answer_filler, quote, dates]
  Check --> Eval[pass_eval, scorer]
  Check --> Pack[packet, insurer]
```

## Layer rules

1. Routers hold no logic.
2. Only `repository.py` touches Supabase, and it enforces the human edit lock (H1).
3. Only `llm.py` touches model APIs (plain httpx, JSON repair retry, think-tag stripping, timeouts per call type).
4. Only `pipeline_runner.py` sequences model calls (F4).
5. Every model input is built by `context_builder.py` (F6).
6. Only `review.py` sets review states (G5).
7. Only `pass_eval.py` decides met or missing (G6).
8. Only `fhir/` builds FHIR resources, and everything it emits is validated before it is stored or returned.
9. Only `pipeline/episodes.py` writes episodes; every stage, call, and human action goes through it.
10. Only `pipeline/cache.py` reads and writes `artifact_cache`; every model call goes through the model-call cache in `llm.py`.

## Sequence: ingestion

```mermaid
sequenceDiagram
  participant R as Reviewer
  participant E as Engine
  participant L as OpenAI
  participant J as Judge
  participant D as Supabase
  R->>E: POST /policies (file, role, source_url)
  E->>E: validate, sha256, resume state
  E->>E: pages, context builder, pre-check
  E->>L: plan identity
  E->>E: 4-tier cascade, role route, load plan memory
  loop page groups in order
    E->>L: extract with working memory
    E->>E: validate, ground, merge memory, checkpoint
  end
  E->>J: judge items (bounded, re-sorted)
  E->>E: questions, checks, FHIR build and validate
  E->>D: draft items, audit file
  R->>E: Gate 1 accept, edit, reject each item
  R->>E: Gate 2 go live
```

## Sequence: order check

```mermaid
sequenceDiagram
  participant W as Web
  participant E as Engine
  participant L as OpenAI (quotes only)
  participant D as Supabase
  W->>E: POST /pa/check
  E->>E: service match, coverage gate
  E->>D: live rules, patient records
  loop rules in policy order, questions in link order
    E->>E: code lookup or date math
    E->>L: exact quote when free text
    E->>E: verify quote, enableWhen
  end
  E->>E: pass conditions, readiness
  E->>D: request, criteria, answers, events
  E-->>W: checklist
```

## Folder layout

```
pa-engine/
  app/
    main.py  config.py  llm.py  repository.py
    api/           health.py policies.py review.py reports.py pa.py fhir.py
    pipeline/      pipeline_runner.py context_builder.py working_memory.py episodes.py cache.py
    ingest/        upload_validation.py pdf_reader.py precheck.py cascade.py
                   plan_identity.py coverage_extractor.py rule_extractor.py drug_extractor.py
                   grounding.py judge.py question_builder.py question_judge.py
    review/        review.py locks.py audit_export.py
    check/         service_matcher.py coverage_gate.py fact_extractor.py answer_filler.py
                   quote.py dates.py pass_eval.py scorer.py owner.py packet.py insurer.py
    fhir/          builders.py mappings.py validate.py extensions.py
    prompts/       p_id.txt p0.txt p1.txt p1d.txt p2.txt p3.txt p4.txt p4b.txt p5.txt p6.txt p_svc.txt
    models/        pydantic shapes
  synth/           scenario.py structured.py notes.py render_pdf.py roundtrip.py (see 15)
  eval/            gold_rules/ gold_coverage/ gold_questions/ gold_patients/ mutations.json
  scripts/         download_docs.py ingest_real_docs.py reset_demo.py e2e.py eval.py
  tests/
data/policies/     SOURCES.md (committed), PDFs (gitignored), caches
docs/pa-constitution/
web/app/admin/policies/   web/app/doctor/pa/[id]/   web/components/pa/   web/mocks/pa/
```

## Tech stack

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.11 | PDF and data tooling |
| API | FastAPI + uvicorn | Typed, auto docs |
| PDF read | pdfplumber | Per-page text, tables, character styles for header scan |
| Section scoring | rank_bm25 | Tier D, no vector store |
| Validation | pydantic v2 | Strict schemas |
| HTTP to models | httpx, plain REST | No SDK transport surprises |
| Database | Supabase (Postgres, Realtime, Storage), supabase-py | Shared team state |
| FHIR | `fhir.resources`, R4B models, version matched to our pydantic major (see `09`) | Structural validation |
| Extractor model | OpenAI gpt-4.1-mini class, pinned id | Structured output, cost |
| Judge model | Gemini (or Grok for SpaceXAI) | Different provider |
| PDF render (synthetic) | reportlab | Realistic report PDFs |
| Synthetic base patient | Synthea (optional) or hand-authored FHIR bundle | See `15` |
| Frontend | Next.js, TypeScript, Tailwind, shadcn/ui, react-pdf | Team app |
| Tests | pytest; autouse fixture blocks real model calls | No accidental billed calls |

## Environment

```
SUPABASE_URL=  SUPABASE_SERVICE_KEY=
OPENAI_API_KEY=  OPENAI_MODEL=gpt-4.1-mini
JUDGE_PROVIDER=gemini  GEMINI_API_KEY=  GROK_API_KEY=
TIMEOUT_EXTRACT_SECONDS=120  TIMEOUT_JUDGE_SECONDS=60  TIMEOUT_QUOTE_SECONDS=20
MAX_CONCURRENT_LLM_CALLS=4
CONTEXT_GROUP_PAGES=3  CONTEXT_NEIGHBOR_LINES=15  CONTEXT_MAX_TOKENS=12000
WORKING_MEMORY_MAX_TOKENS=1500  SECTION_PAGE_CAP=40
RUN_MAX_MODEL_CALLS=400  RUN_MAX_SECONDS=1200
PIPELINE_VERSION=v4  FHIR_BUILDER_VERSION=1  SYNTH_GENERATOR_VERSION=1
ARTIFACT_BUCKET=artifacts
DEMO_MODE=false  DEMO_TODAY=2026-09-27
INSURER_REQUEST_INFO=false  INSURER_DELAY_SECONDS=5
FHIR_BASE_URL=https://clearpath.example/fhir
ALLOWED_ORIGINS=http://localhost:3000,https://<vercel-app>
```

`config.py` calls `load_dotenv()`. `.env.example` committed, `.env` never.

## Deployment

Engine on Render or Railway; web uses `NEXT_PUBLIC_PA_ENGINE_URL`. The live demo runs locally with the deployed engine as backup. `GET /health` returns git commit, DB, OpenAI, judge reachability; after a restart, confirm the commit matches before trusting results.
