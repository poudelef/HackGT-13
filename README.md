# ClearPath PA

Prior authorization for ClearPath Health. A document is read, a second model flags risk, and a person decides at every gate. Patients in this demo are synthetic.

The rules live in `docs/pa-constitution/`. `memory.md` is the decision log.

## Run

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r pa-engine/requirements.txt
.venv/bin/python pa-engine/scripts/reset_demo.py

cd pa-engine && ../.venv/bin/uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd web && npm install && npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

The sample library is a labeled fictional fallback so the app runs without model keys. Set `OPENAI_API_KEY` and `GEMINI_API_KEY` (or `GROK_API_KEY` with `JUDGE_PROVIDER=grok`) to read a published PDF through the same pipeline. Copy `.env.example` to `.env`.

## What you can do

1. Policy library: load the sample, or upload a text-layer PDF. Accept, edit, or reject each item, then go live.
2. Order: check an office visit (not required) or lumbar MRI code `72148` (4 of 5 met).
3. Add the withheld physical-therapy note. Readiness becomes 5 of 5.
4. Set an answer aside, enter a replacement with an attestation, verify every rule, preview, and submit. The fake insurer approves. It never produces a denial.

## Tests

```bash
cd pa-engine && ../.venv/bin/python -m pytest
```

After a code change (frees old :8000/:3000 listeners, starts a fresh API, runs edge + port tests):

```bash
cd pa-engine && ../.venv/bin/python scripts/verify_change.py --keep
```

Omit `--keep` to stop the temporary API when the suite finishes. Add `--web` to also restart Next on :3000.
