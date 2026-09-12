# prospect-diagnostic

From a LinkedIn URL, research a UAE founder on the public web, check every factual claim twice against a
primary source, label each finding verified, partially verified or refused, name the three biggest gaps in
how they show up publicly, and produce a one page diagnostic that a named human must approve before it
leaves the building.

Built for Growpido's AI and Automation Engineer task, Track B.

## What it does not do

- It never fetches LinkedIn. The URL is only parsed for the profile slug; the slug is resolved on the open web.
  LinkedIn hosts are on a never-fetch list and LinkedIn search results are dropped before anyone reads them.
- It never logs in anywhere and never contacts anyone.
- It never weakens a verdict to make the page look better. A claim only the company states comes out
  partially verified at best. A claim only the press repeats is refused.

## How a run works

1. identify: derive name guesses from the slug, search the public web, ask the model who this is.
   Confidence under 0.6 stops the run for a human.
2. research: run a fixed query plan (regulators, official lists, company releases, funding, traction, interviews),
   fetch up to 24 pages with httpx, save every page as text under `evidence/<run_id>/`. Pages that return
   403, PDFs, and JavaScript only pages are recorded as "could not check", not spoofed harder.
   Each source is tiered: primary (regulator, official register, publisher of an official list), company
   (its own site or a wire release it issued), secondary (press).
3. claims: extract atomic claims from each readable source, dedupe syndicated copies.
4. verify: every claim gets two passes. Pass 1 uses MODEL_PRIMARY over excerpts retrieved from the claim text.
   Pass 2 uses MODEL_SECOND_OPINION over separately retrieved excerpts built from the original quote and its
   numbers. Retrieval is lexical (idf weighted term overlap plus a bonus for exact number matches).
   The label is set by fixed rules in `app/verify.py`, not by the model:
   - verified: both passes say supported and both cite a primary source
   - partially verified: support exists but the best source is the company's own word, or the details differ
   - refused (unverified): contradicted, not found by either pass, or repeated only by press
5. gaps: the stronger model names three gaps, each tied to finding ids.
6. report: the summary is written from verified and partially verified findings only. Every number in the
   Summary and Gaps sections is checked mechanically against those findings. Em dashes, hashtags and the
   filler list in `app/lint.py` are flagged; the model gets one rewrite, then a mechanical fix; anything
   left is shown as a warning on the draft page so the approver sees it.
7. human gate: the run stops as a draft. Approval needs a name and a note and is written into the ledger and
   the diagnostic header.

## Setup

```
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY, TAVILY_API_KEY, MODEL_PRIMARY, MODEL_SECOND_OPINION
python -m pytest -q
```

`python cli.py models` lists the model ids your key can use.

### Model API

`LLM_PROVIDER=anthropic` uses the Anthropic messages API with ANTHROPIC_API_KEY.
`LLM_PROVIDER=openai` uses any OpenAI compatible chat completions endpoint: set OPENAI_API_KEY and, if it is
not api.openai.com, OPENAI_BASE_URL. MODEL_PRIMARY and MODEL_SECOND_OPINION must be two different ids from
that endpoint; the stronger one goes second.

### Web search

`SEARCH_PROVIDER` picks the backend. All of them return the same shape and all drop LinkedIn results.

| provider | key | notes |
|---|---|---|
| tavily | TAVILY_API_KEY | default; 1,000 free credits a month, one run uses about 32 |
| brave | BRAVE_API_KEY | Brave Search API, JSON web results, free tier |
| serper | SERPER_API_KEY | Google results through serper.dev, free starter credits |
| duckduckgo | none | scrapes the HTML endpoint; rate limited and brittle, only for a demo |

## Run

```
python cli.py run https://www.linkedin.com/in/<slug>
python cli.py log <run_id>
python cli.py approve <run_id> --by "Your Name" --note "what you checked"
```

Web app:

```
uvicorn app.main:app
```

Open http://127.0.0.1:8000, paste the URL, watch the stages and the live log, open the draft, approve it.
The pages under `app/templates` are static shells; `app/static/app.js` renders them from the JSON endpoints,
so what the reviewer sees is exactly what is in `ledger.json`.
The markdown is served at `/runs/<id>/diagnostic.md`, the full ledger at `/runs/<id>/ledger.json`.

## Layout

```
app/config.py    settings, host tiers, never-fetch list
app/identify.py  slug to person
app/research.py  query plan, fetching, source tiers
app/fetch.py     httpx fetch, html to text, evidence snapshots
app/claims.py    claim extraction and dedupe
app/verify.py    lexical retrieval, two passes, verdict rules
app/gaps.py      three gaps
app/report.py    summary, number tracing, markdown
app/lint.py      house rules
app/pipeline.py  orchestration, approve, reject
app/main.py      FastAPI routes and JSON endpoints
app/templates/   page shells
app/static/      stylesheet and front end script
cli.py           command line
runs/<id>/       run.json, ledger.json, log.jsonl, diagnostic.md
evidence/<id>/   one text snapshot per fetched url
```

## Deploy

Railway with Nixpacks: `Procfile` and `runtime.txt` are enough. Mount a volume at `/app/runs` so the ledger
survives redeploys, and set `EVIDENCE_DIR=/app/runs/evidence` so the snapshots do too.

See `HONEST.md` for what broke while making it run and where the code is still weak.
