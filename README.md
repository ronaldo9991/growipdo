# Growpido task: both tracks

One plain Python app, two tracks, one rule: nothing reaches a client without a source and a signature.
The home page routes to either track and a toggle in the header switches between them.

**Track A, Reputation Radar** (`/radar`): finds public mentions of Nidhi Hooda and Growpido across LinkedIn
search snippets, news and the open web, classifies each by sentiment and risk (ignore, watch, respond now)
with two models, holds anything ambiguous for a human, writes a weekly brief readable in three minutes, and
never drafts a response until a named person approves drafting one, then approves the draft.

**Track B, Prospect to Diagnostic** (`/diagnostic`): from a LinkedIn URL, research a UAE founder on the
public web, check every factual claim twice against a primary source, label each finding verified,
partially verified or refused, name the three biggest gaps in how they show up publicly, and produce a one
page diagnostic that a named human must approve before it leaves the building.

Built for Growpido's AI and Automation Engineer task.

## Track A: how a radar run works

1. profile: the subjects are profiled from public search snippets, with disambiguators (company, city,
   role) so the classifier can tell them from namesakes.
2. collect: web and news searches per subject. LinkedIn results are kept as search engine snippets and are
   never fetched; nothing behind a login is read. Other pages are fetched and archived under `evidence/`.
   A result that does not even name the subject is dropped before classification.
3. classify: MODEL_PRIMARY reads every mention (is it about the subject, sentiment, risk, confidence, the
   sentence that drove it). MODEL_SECOND_OPINION re-reads anything that is not a confident, non negative
   ignore, and any mention whose title does not name the subject. Fixed rules in `app/radar.py` decide:
   respond now needs both to agree; any disagreement or any doubt about identity is marked ambiguous and
   held at watch for a human.
4. brief: `brief.md` with a three bullet opening (linted, numbers traced to the items), the week in numbers,
   respond now, ambiguous held for a human with both readings, watch, nothing needed, namesakes set aside.
5. human gate: a named person approves the brief. Ambiguous items are decided on the run page with a name.
   For a respond now item, gate 1 approves drafting (only then does the model write), gate 2 approves or
   edits the draft. Approved means ready for a person to post; the system never posts anything.

## What neither track does

- Neither fetches LinkedIn. Track B parses the URL for the slug and resolves it on the open web; Track A keeps
  LinkedIn results as search engine snippets. LinkedIn hosts are on a never-fetch list in `app/fetch.py`.
- Neither logs in anywhere or contacts anyone.
- Neither weakens a verdict to make the page look better. A claim only the company states comes out
  partially verified at best. A claim only the press repeats is refused. A mention the two models disagree on
  is held for a human, not guessed.

## Track B: how a run works

1. identify: derive name guesses from the slug, search the public web, ask the model who this is.
   Confidence under 0.6 stops the run for a human.
2. research: run a fixed query plan (regulators, official lists, company releases, funding, traction, interviews),
   fetch up to 36 pages with httpx, save every page as text under `evidence/<run_id>/`. Pages that return
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

Track A: open http://127.0.0.1:8000/radar, subjects default to "Nidhi Hooda, Growpido", or
`curl -X POST /radar/run -d 'subjects=Nidhi Hooda, Growpido'`. Output at `runs/radar/<id>/brief.md`.

Track B:

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
app/pipeline.py  Track B orchestration, approve, reject
app/radar.py     Track A: profile, collect, classify, decide, brief, gates
app/main.py      FastAPI routes and JSON endpoints
app/templates/   page shells
app/static/      stylesheet and front end script
cli.py           command line
runs/<id>/       Track B: run.json, ledger.json, log.jsonl, diagnostic.md
runs/radar/<id>/ Track A: run.json, ledger.json, log.jsonl, brief.md
evidence/<id>/   one text snapshot per fetched url
```

## Deploy

Railway with Nixpacks: `Procfile` and `runtime.txt` are enough. Mount a volume at `/app/runs` so the ledger
survives redeploys, and set `EVIDENCE_DIR=/app/runs/evidence` so the snapshots do too.

## One minute summary videos

Every finished run can render a sixty second video of itself with Remotion. Open a run and press
"Make 1 min video"; the file lands at `/runs/<id>/summary.mp4` or `/radar/runs/<id>/summary.mp4`.
Six scenes: who the subject is, the verdict bar with the counts, the summary or the week's opening
bullets, the three gaps or the items waiting for a decision, one refused claim or one namesake set
aside, and the sign-off card. Nothing in the video is written for it: every line comes from that run's
ledger, so each number traces back to a finding, a mention or the approval record.

The compositions live in `video/` and are plain React. To work on them:

```
cd video && npm install && npm run studio
```

Rendering needs Node and a headless browser. The `Dockerfile` at the repository root installs
Python, Node and the browser libraries so the deployed app can render too. On Railway a sixty
second video takes about eighty five seconds of wall clock, measured on the two runs in
`evidence/`: the radar video finished in 86 seconds at 4.0 MB and the diagnostic video in 82
seconds at 5.0 MB. The render runs in the background, so the page stays usable and the button
turns into a link when the file is ready.

## Speed

Claim extraction, mention classification, verification and page fetching all run concurrently, with
worker counts set by CLAIM_WORKERS, CLASSIFY_WORKERS, VERIFY_WORKERS and FETCH_WORKERS.

| Run | Before | After |
|---|---|---|
| Track B, Mark Chahwan | 418 seconds | 137 seconds |
| Track A, weekly radar | 203 seconds | 44 seconds |

Run pages poll a small status endpoint and pull the full ledger only when the run has moved, instead
of re-downloading hundreds of kilobytes every few seconds.

## Seven things added after the first submission

1. Conflicts between sources: accepted findings that disagree on the same figure are listed in the diagnostic
   and on the run page, so neither number is quoted without its source.
2. Concurrent verification: claims are checked VERIFY_WORKERS at a time; findings keep claim order.
3. Weekly scheduler: set RADAR_SCHEDULE (for example `mon 09:00`, UTC) and RADAR_SUBJECTS and the radar runs
   itself once a week, in process, with the last start recorded so a restart does not double run.
4. Memory between weeks: each radar run compares its mentions with the previous run (approved preferred) and
   the brief says what is new and what was already seen, with the earlier decision carried on the item.
5. Approver token: set APPROVER_TOKEN and every approve, reject, decide and draft action must carry it. The
   run page says plainly when no token is configured.
6. Evidence bundle: `/runs/<id>/evidence.zip` and `/radar/runs/<id>/evidence.zip` return the run folder and its
   page snapshots, so the server's audit trail can be pulled back into the repo.
7. Reach estimate: engagement counts in a mention's title or snippet plus the channel give a low, medium or high
   reach; a negative item both passes would ignore is held at watch when its reach is high. It never creates a
   respond now on its own.

See `HONEST.md` for what broke while making it run and where the code is still weak.
