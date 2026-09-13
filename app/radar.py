"""Track A: reputation radar. Finds public mentions of the subjects, classifies each by sentiment and
risk with two models, escalates anything ambiguous to a human, writes a weekly brief, and never drafts
a response until a named human has approved drafting one.

LinkedIn is never fetched. LinkedIn mentions come in as search engine snippets only and are labelled so."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx

from . import config, lint
from .fetch import fetch, read_snapshot
from .ledger import Run
from .llm import LLM
from .search import search, search_news
from .util import host_of, now_iso

RISKS = ("ignore", "watch", "respond_now")
SENTIMENTS = ("positive", "neutral", "negative", "mixed")
MAX_MENTIONS = 40


# ---------- subjects and profile ----------

def parse_subjects(raw: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"[,;\n]", raw or "") if p.strip()]
    return parts[:4]


PROFILE_SYSTEM = """You are given web search snippets about a person and an organisation. Write a short factual profile that a
classifier can use to decide whether a later mention is about these subjects or about a namesake.
Use only what the snippets say. Return JSON: {"profile": 3 to 5 plain sentences, "disambiguators": [short facts that
distinguish the subjects from namesakes, e.g. company, city, role, industry], "evidence_urls": [urls used]}.
No em dashes."""


def build_profile(subjects: list[str], llm: LLM, log) -> dict:
    results, seen = [], set()
    for s in subjects:
        for q in (f'"{s}"', f'"{s}" ' + " ".join(x for x in subjects if x != s)):
            for r in search(q, max_results=6, keep_blocked=True):
                if r["url"] not in seen:
                    seen.add(r["url"])
                    results.append(r)
    snippets = "\n\n".join(f"[{i+1}] {r['title']}\nURL: {r['url']}\n{r['snippet'][:500]}" for i, r in enumerate(results[:24]))
    out = llm.json(PROFILE_SYSTEM, f"Subjects: {', '.join(subjects)}\n\nSnippets:\n{snippets}", max_tokens=700)
    profile = {"profile": str(out.get("profile") or ""), "disambiguators": [str(d) for d in out.get("disambiguators") or []],
               "evidence_urls": [u for u in out.get("evidence_urls") or [] if u in seen]}
    log("profile", "subject profile written from public snippets", disambiguators=profile["disambiguators"])
    return profile


# ---------- collection ----------

def query_plan(subjects: list[str]) -> list[tuple[str, str]]:
    """(query, mode) pairs. mode is web or news."""
    plan = []
    for s in subjects:
        plan += [(f'"{s}"', "web"), (f'"{s}" linkedin', "web"), (f'"{s}" review OR complaint OR scam', "web"),
                 (f'"{s}" interview OR podcast OR webinar', "web"), (f'"{s}"', "news")]
    if len(subjects) > 1:
        plan.append((" ".join(f'"{s}"' for s in subjects), "web"))
    return plan


def parse_date(raw: str, now: datetime) -> str:
    """Return an ISO date or '' for the search engine's date string."""
    if not raw:
        return ""
    t = raw.strip().lower()
    m = re.match(r"(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago", t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {"minute": timedelta(minutes=n), "hour": timedelta(hours=n), "day": timedelta(days=n),
                 "week": timedelta(weeks=n), "month": timedelta(days=30 * n), "year": timedelta(days=365 * n)}[unit]
        return (now - delta).date().isoformat()
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y", "%Y-%m-%dt%H:%M:%S"):
        try:
            return datetime.strptime(t[:len(datetime.now().strftime(fmt))] if fmt.endswith("%S") else t, fmt).date().isoformat()
        except ValueError:
            continue
    m = re.search(r"(20\d\d)-(\d\d)-(\d\d)", t)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


def channel_of(url: str, mode: str) -> str:
    host = host_of(url)
    if "linkedin.com" in host:
        return "linkedin"
    if mode == "news" or any(h in host for h in ("news", "gulfbusiness", "khaleejtimes", "thenational", "zawya", "arabianbusiness", "entrepreneur")):
        return "news"
    return "web"


def mentions_subject(subject: str, *texts: str) -> bool:
    key = subject.split()[-1].lower() if " " in subject else subject.lower()
    blob = " ".join(t or "" for t in texts).lower()
    return key in blob


def collect(subjects: list[str], run_id: str, log) -> list[dict]:
    now = datetime.now(timezone.utc)
    found: dict[str, dict] = {}
    for q, mode in query_plan(subjects):
        try:
            results = search_news(q, max_results=8, keep_blocked=True) if mode == "news" else search(q, max_results=8, keep_blocked=True)
        except Exception as e:
            log("collect", f"search failed: {q!r} ({mode})", error=str(e))
            continue
        log("collect", f"{len(results)} results: {q!r} ({mode})")
        for r in results:
            url = r["url"]
            subject = next((s for s in subjects if mentions_subject(s, r["title"], r["snippet"], url)), None)
            if subject is None:
                continue  # the search engine matched loosely; the subject is not even named
            if url in found:
                found[url]["queries"].append(q)
                continue
            found[url] = {"url": url, "title": r["title"], "snippet": r["snippet"], "subject": subject,
                          "channel": channel_of(url, mode), "date": parse_date(r.get("date") or "", now),
                          "date_raw": r.get("date") or "", "publisher": r.get("source") or host_of(url),
                          "queries": [q], "blocked": r.get("blocked", False)}
    items = list(found.values())
    order = {"news": 0, "linkedin": 1, "web": 2}
    items.sort(key=lambda m: (order[m["channel"]], -len(m["queries"])))
    items = items[:MAX_MENTIONS]
    log("collect", f"{len(found)} distinct mentions, keeping {len(items)}",
        by_channel={c: sum(1 for m in items if m["channel"] == c) for c in order})

    # Fetch the non LinkedIn pages so the classifier sees more than a snippet. LinkedIn stays a snippet.
    client = httpx.Client(follow_redirects=True, timeout=config.FETCH_TIMEOUT,
                          headers={"User-Agent": config.USER_AGENT, "Accept": "text/html,*/*;q=0.8"})
    to_fetch = [m for m in items if not m["blocked"]]
    with ThreadPoolExecutor(max_workers=6) as pool:
        fetched = list(pool.map(lambda m: fetch(m["url"], run_id, client), to_fetch))
    client.close()
    for m, res in zip(to_fetch, fetched):
        m["fetch_status"] = res.status
        m["snapshot"] = res.snapshot
        m["text_chars"] = len(res.text)
        if res.status == "ok" and not mentions_subject(m["subject"], res.text):
            m["fetch_status"] = "subject_not_in_page"
    for m in items:
        if m["blocked"]:
            m["fetch_status"] = "snippet_only"
            m["snapshot"] = ""
            m["text_chars"] = 0
    for i, m in enumerate(items, start=1):
        m["id"] = f"M{i}"
    return items


# ---------- classification ----------

CLASSIFY_SYSTEM = """You triage public mentions for a reputation monitor. For one mention, decide:
about_subject: "yes" if the mention is about the named subject described in the profile, "no" if it is about someone or
  something else with the same name, "unsure" if you cannot tell from the text.
sentiment: positive, neutral, negative or mixed, about the subject specifically.
risk, from the subject's point of view:
  respond_now: a factual error about the subject, a complaint or accusation, a legal or regulatory reference, a scam
    or impersonation using the name, or a negative piece with real reach. Something a person would regret not seeing today.
  watch: mixed or mildly negative, a question about the subject, a competitor comparison, an old negative item, or a
    neutral item with reach that could turn.
  ignore: positive or neutral with no action needed, the subject's own content, or not about the subject at all.
confidence: 0 to 1 that your about_subject and risk are right.
Quote the sentence that drove the decision. Do not invent facts about the subject. No em dashes.
Return JSON: {"about_subject": ..., "sentiment": ..., "risk": ..., "confidence": number, "reason": one or two sentences, "quote": string}"""


def _mention_text(m: dict) -> str:
    if m.get("snapshot") and m.get("fetch_status") in ("ok", "subject_not_in_page"):
        try:
            return read_snapshot(m["snapshot"])[:6000]
        except Exception:
            pass
    return ""


def classify_one(m: dict, profile: dict, llm: LLM) -> dict:
    body = _mention_text(m)
    user = (
        f"Subject: {m['subject']}\nProfile: {profile.get('profile')}\nDisambiguators: {', '.join(profile.get('disambiguators') or [])}\n\n"
        f"Mention channel: {m['channel']} ({'search snippet only, page not fetched' if m['channel'] == 'linkedin' else m.get('fetch_status')})\n"
        f"URL: {m['url']}\nTitle: {m['title']}\nDate: {m['date'] or 'unknown'}\nSnippet: {m['snippet']}\n\n"
        f"Page text (may be empty):\n{body}"
    )
    out = llm.json(CLASSIFY_SYSTEM, user, max_tokens=500)
    about = str(out.get("about_subject") or "unsure").lower()
    if about not in ("yes", "no", "unsure"):
        about = "unsure"
    sentiment = str(out.get("sentiment") or "neutral").lower()
    if sentiment not in SENTIMENTS:
        sentiment = "neutral"
    risk = str(out.get("risk") or "watch").lower().replace(" ", "_")
    if risk not in RISKS:
        risk = "watch"
    try:
        conf = max(0.0, min(1.0, float(out.get("confidence") or 0)))
    except (TypeError, ValueError):
        conf = 0.0
    return {"about_subject": about, "sentiment": sentiment, "risk": risk, "confidence": conf,
            "reason": str(out.get("reason") or ""), "quote": str(out.get("quote") or ""), "model": llm.model}


def needs_second_opinion(c: dict, m: dict | None = None) -> bool:
    """Anything that is not a confident, positive-or-neutral ignore gets a second reading. So does any
    mention whose title does not even name the subject: a namesake slipped through as a confident ignore
    in the first live run, and a cheap second reading is the right price for catching that."""
    if c["about_subject"] != "yes" or c["risk"] != "ignore" or c["sentiment"] in ("negative", "mixed") or c["confidence"] < 0.75:
        return True
    if m is not None and not mentions_subject(m["subject"], m.get("title") or ""):
        return True
    return False


def decide(p1: dict, p2: dict | None) -> dict:
    """Fixed rules. respond_now needs both passes to agree. Any disagreement, or any 'unsure', is ambiguous
    and goes to a human with the cautious label, never the confident one."""
    if p2 is None:
        return {"about_subject": p1["about_subject"], "sentiment": p1["sentiment"], "risk": p1["risk"],
                "ambiguous": False, "why": "one pass, confident ignore"}
    abouts = {p1["about_subject"], p2["about_subject"]}
    if abouts == {"no"}:
        return {"about_subject": "no", "sentiment": "neutral", "risk": "ignore", "ambiguous": False,
                "why": "both passes say this is not about the subject"}
    if "unsure" in abouts or len(abouts) > 1:
        return {"about_subject": "unsure", "sentiment": p1["sentiment"], "risk": "watch", "ambiguous": True,
                "why": f"passes disagree on whether this is the subject ({p1['about_subject']} vs {p2['about_subject']}); a human decides"}
    if p1["risk"] == p2["risk"]:
        sentiment = p1["sentiment"] if p1["sentiment"] == p2["sentiment"] else "mixed"
        return {"about_subject": "yes", "sentiment": sentiment, "risk": p1["risk"], "ambiguous": False,
                "why": "both passes agree"}
    rank = {r: i for i, r in enumerate(RISKS)}
    cautious = "watch" if "respond_now" in (p1["risk"], p2["risk"]) else max((p1["risk"], p2["risk"]), key=lambda r: rank[r])
    return {"about_subject": "yes", "sentiment": p1["sentiment"], "risk": cautious, "ambiguous": True,
            "why": f"passes disagree on risk ({p1['risk']} vs {p2['risk']}); held at {cautious} for a human"}


def classify_all(mentions: list[dict], profile: dict, llm1: LLM, llm2: LLM, log) -> None:
    for m in mentions:
        p1 = classify_one(m, profile, llm1)
        p2 = classify_one(m, profile, llm2) if needs_second_opinion(p1, m) else None
        m["pass1"], m["pass2"] = p1, p2
        m["final"] = decide(p1, p2)
        log("classify", f"{m['id']} {m['final']['risk']}{' AMBIGUOUS' if m['final']['ambiguous'] else ''}: {m['title'][:70]}",
            pass1=p1["risk"], pass2=p2["risk"] if p2 else None, about=m["final"]["about_subject"])


# ---------- brief ----------

BRIEF_SYSTEM = """Write the opening of a weekly reputation brief for a busy founder. Three bullet points, each one sentence,
plain English, that say what matters this week and what needs a decision. Use only the items given. Every number you
write must appear in the items or the counts given. No em dashes, no hashtags, no filler words such as leverage,
robust, journey, landscape, navigate, empower, unlock, seamless, testament, pivotal, delve, crucial, innovative.
Return plain text: three lines, each starting with "- "."""


def week_window(now: datetime) -> tuple[str, str]:
    end = now.date()
    start = end - timedelta(days=6)
    return start.isoformat(), end.isoformat()


def counts_of(mentions: list[dict]) -> dict:
    live = [m for m in mentions if m["final"]["about_subject"] != "no"]
    return {"total": len(mentions), "about_subject": len(live), "not_subject": len(mentions) - len(live),
            "respond_now": sum(1 for m in live if m["final"]["risk"] == "respond_now"),
            "watch": sum(1 for m in live if m["final"]["risk"] == "watch" and not m["final"]["ambiguous"]),
            "ignore": sum(1 for m in live if m["final"]["risk"] == "ignore"),
            "ambiguous": sum(1 for m in mentions if m["final"]["ambiguous"]),
            "linkedin": sum(1 for m in live if m["channel"] == "linkedin"),
            "news": sum(1 for m in live if m["channel"] == "news"),
            "web": sum(1 for m in live if m["channel"] == "web")}


def _t(text: str) -> str:
    """Quoted titles and reasons are rendered without hashtags or em dashes. Search engines return post
    titles with their hashtags; the brief is ours, so the house rules apply to what we print."""
    return lint.mechanical_fix(text or "").strip()


def _line(m: dict) -> str:
    when = m["date"] or "undated"
    ch = {"linkedin": "LinkedIn, snippet only", "news": "news", "web": "web"}[m["channel"]]
    return (f"- {m['id']}. {_t(m['title']) or m['url']} ({m['publisher']}, {ch}, {when}). Sentiment {m['final']['sentiment']}. "
            f"{_t(m['final']['why'])}. Reason: {_t(m['pass1']['reason'])}\n  {m['url']}")


def write_brief(run: Run, subjects: list[str], profile: dict, mentions: list[dict], llm: LLM, log) -> tuple[str, list[str]]:
    now = datetime.now(timezone.utc)
    start, end = week_window(now)
    c = counts_of(mentions)
    live = [m for m in mentions if m["final"]["about_subject"] != "no"]
    respond = [m for m in live if m["final"]["risk"] == "respond_now"]
    ambiguous = [m for m in mentions if m["final"]["ambiguous"]]
    watch = [m for m in live if m["final"]["risk"] == "watch" and not m["final"]["ambiguous"]]
    ignore = [m for m in live if m["final"]["risk"] == "ignore"]
    this_week = [m for m in live if m["date"] and m["date"] >= start]

    items = "\n".join(f"{m['id']} [{m['final']['risk']}{', ambiguous' if m['final']['ambiguous'] else ''}] {m['title'][:120]} "
                      f"({m['channel']}, {m['date'] or 'undated'}): {m['pass1']['reason'][:200]}" for m in respond + ambiguous + watch)
    user = (f"Subjects: {', '.join(subjects)}\nWeek: {start} to {end}\nCounts: {c}\n\nItems needing attention:\n{items or '(none)'}\n\n"
            f"Write the three bullets.")
    allowed = [str(v) for v in c.values()]
    allowed += [start, end] + [m["title"] + " " + m["snippet"] + " " + (m.get("date") or "") + " " + (m.get("pass1", {}).get("reason") or "") for m in mentions]
    opening = llm.text(BRIEF_SYSTEM, user, max_tokens=400).strip()
    problems = [str(i) for i in lint.lint_text(opening)] + [f"number {n!r} not in the items" for n in lint.untraced_numbers(opening, allowed)]
    if problems:
        log("brief", "opening failed house rules, one rewrite", problems=problems)
        opening = llm.text(BRIEF_SYSTEM, user + "\n\nYour previous draft broke these rules, fix every one:\n- " + "\n- ".join(problems)
                           + "\n\nPrevious draft:\n" + opening, max_tokens=400).strip()
        problems = [str(i) for i in lint.lint_text(opening)] + [f"number {n!r} not in the items" for n in lint.untraced_numbers(opening, allowed)]
    if problems:
        opening = lint.mechanical_fix(opening)
        problems = [str(i) for i in lint.lint_text(opening)] + [f"number {n!r} not in the items" for n in lint.untraced_numbers(opening, allowed)]

    L = []
    L.append(f"# Reputation radar: weekly brief for {', '.join(subjects)}")
    L.append("")
    L.append(f"Week {start} to {end}. Run {run.id}. Reading time about three minutes.")
    L.append("")
    approval = run.state.get("approval")
    if approval:
        L.append(f"Status: APPROVED by {approval['by']} on {approval['at']}")
        L.append(f"Approver note: {approval['note']}")
    else:
        L.append("Status: DRAFT, not approved. A human must approve this brief before it is circulated.")
    L.append("")
    L.append("## Read this first")
    L.append("")
    L.append(opening)
    L.append("")
    L.append("## The week in numbers")
    L.append("")
    L.append(f"{c['total']} public mentions found, {c['about_subject']} about the subjects, {c['not_subject']} about namesakes and set aside. "
             f"{c['respond_now']} need a response, {c['watch']} to watch, {c['ambiguous']} ambiguous and waiting for a human, {c['ignore']} need nothing. "
             f"By channel: {c['linkedin']} LinkedIn (search snippets only, never fetched), {c['news']} news, {c['web']} web. "
             f"{len(this_week)} carry a date inside the week; the rest are undated or older and are listed as background.")
    L.append("")
    L.append(f"## Respond now ({len(respond)})")
    L.append("")
    if respond:
        for m in respond:
            L.append(_line(m))
        L.append("")
        L.append("No response has been drafted. A named person must approve drafting on the run page before the system writes one, "
                 "and must approve that draft before it is marked ready. Nothing is ever posted by the system.")
    else:
        L.append("Nothing this week needs a response.")
    L.append("")
    L.append(f"## Ambiguous, held for a human ({len(ambiguous)})")
    L.append("")
    if ambiguous:
        L.append("The two classifiers disagreed or could not tell whether the item is about the subject. The system did not guess: "
                 "each item is held at watch and shown here with both readings.")
        L.append("")
        for m in ambiguous:
            p2 = m.get("pass2") or {}
            L.append(_line(m))
            L.append(f"  Pass 1 ({m['pass1']['model']}): about {m['pass1']['about_subject']}, {m['pass1']['risk']}, confidence {m['pass1']['confidence']:.2f}. "
                     f"Pass 2 ({p2.get('model')}): about {p2.get('about_subject')}, {p2.get('risk')}, confidence {float(p2.get('confidence') or 0):.2f}.")
    else:
        L.append("Nothing ambiguous this week.")
    L.append("")
    L.append(f"## Watch ({len(watch)})")
    L.append("")
    for m in watch:
        L.append(_line(m))
    if not watch:
        L.append("Nothing to watch.")
    L.append("")
    L.append(f"## Nothing needed ({len(ignore)})")
    L.append("")
    for m in ignore:
        L.append(f"- {m['id']}. {_t(m['title']) or m['url']} ({m['publisher']}, {m['channel']}, {m['date'] or 'undated'}), {m['final']['sentiment']}. {m['url']}")
    if not ignore:
        L.append("None.")
    L.append("")
    not_subject = [m for m in mentions if m["final"]["about_subject"] == "no"]
    L.append(f"## Set aside as namesakes ({len(not_subject)})")
    L.append("")
    for m in not_subject:
        L.append(f"- {m['id']}. {_t(m['title']) or m['url']}. {_t(m['pass1']['reason'])[:160]} {m['url']}")
    if not not_subject:
        L.append("None.")
    L.append("")
    L.append("## Method")
    L.append("")
    L.append(f"Subjects were profiled from public search snippets so a classifier can tell them from namesakes: {_t(profile.get('profile'))} "
             f"Mentions came from web and news searches; LinkedIn results were kept as search engine snippets and never fetched, nothing behind a login was read. "
             f"Every mention was classified by {run.state['models']['primary']}; anything not a confident ignore was classified again by "
             f"{run.state['models']['second_opinion']}. The final label follows fixed rules: respond now needs both to agree, any disagreement or "
             f"any doubt about identity is marked ambiguous and held for a human. Nobody was contacted.")
    L.append("")
    if problems:
        L.append("## House rules warnings")
        L.append("")
        for p in problems:
            L.append(f"- {p}")
        L.append("")
    return "\n".join(L), problems


# ---------- pipeline ----------

def run_radar(run: Run) -> Run:
    try:
        primary = config.require("MODEL_PRIMARY")
        second = config.require("MODEL_SECOND_OPINION")
        run.state["models"] = {"primary": primary, "second_opinion": second}
        llm1, llm2 = LLM(primary, log=run.log), LLM(second, log=run.log)
        subjects = parse_subjects(run.state["input_url"])
        if not subjects:
            raise RuntimeError("no subject given")
        run.ledger["subjects"] = subjects

        run.set_stage("profile")
        profile = build_profile(subjects, llm1, run.log)
        run.ledger["profile"] = profile
        run.state["subject"] = {"full_name": ", ".join(subjects), "role": "reputation radar", "company": "", "location": "", "confidence": 1.0}
        run.save()

        run.set_stage("collect")
        mentions = collect(subjects, run.id, run.log)
        if not mentions:
            raise RuntimeError("no public mentions found for the subjects")
        run.ledger["mentions"] = mentions
        run.save()

        run.set_stage("classify")
        classify_all(mentions, profile, llm1, llm2, run.log)
        run.state["counts"] = counts_of(mentions)
        run.save()

        run.set_stage("brief")
        run.ledger["responses"] = {}
        write_brief_file(run, llm1)
        run.state["status"] = "draft"
        run.state["stage"] = "human_gate"
        run.save()
        run.log("human_gate", "brief drafted, waiting for a human", counts=run.state["counts"])
    except Exception as exc:
        run.fail(exc)
        raise
    return run


def write_brief_file(run: Run, llm: LLM | None = None) -> str:
    if llm is None:
        llm = LLM(run.state["models"]["primary"], log=run.log)
    if run.ledger.get("brief_opening_locked"):
        # After approval the brief is re-rendered without calling the model again.
        text = run.ledger["brief"]
        header_old = "Status: DRAFT, not approved. A human must approve this brief before it is circulated."
        approval = run.state.get("approval")
        if approval and header_old in text:
            text = text.replace(header_old, f"Status: APPROVED by {approval['by']} on {approval['at']}\nApprover note: {approval['note']}")
        run.ledger["brief"] = text
    else:
        text, problems = write_brief(run, run.ledger["subjects"], run.ledger["profile"], run.ledger["mentions"], llm, run.log)
        run.ledger["brief"] = text
        run.ledger["lint"] = problems
        run.ledger["brief_opening_locked"] = True
    run.brief_path.write_text(run.ledger["brief"], encoding="utf-8")
    run.save()
    return run.ledger["brief"]


def approve_brief(run: Run, by: str, note: str) -> Run:
    if run.state["status"] != "draft":
        raise RuntimeError(f"run is {run.state['status']}, only a draft can be approved")
    if not by.strip() or len(note.strip()) < 10:
        raise RuntimeError("approval needs a name and a note of at least 10 characters")
    run.state["approval"] = {"by": by.strip(), "note": note.strip(), "at": now_iso()}
    run.state["status"] = "approved"
    run.save()
    write_brief_file(run)
    run.log("human_gate", f"brief approved by {by.strip()}", note=note.strip())
    return run


def resolve_ambiguous(run: Run, mention_id: str, by: str, about_subject: str, risk: str, note: str) -> Run:
    """A human settles an ambiguous item. Recorded with their name; the brief is not rewritten by the model."""
    m = next((x for x in run.ledger["mentions"] if x["id"] == mention_id), None)
    if not m:
        raise RuntimeError(f"no mention {mention_id}")
    if about_subject not in ("yes", "no") or risk not in RISKS or not by.strip():
        raise RuntimeError("need a name, about_subject yes or no, and a risk")
    m["final"] = {"about_subject": about_subject, "sentiment": m["final"]["sentiment"], "risk": risk if about_subject == "yes" else "ignore",
                  "ambiguous": False, "why": f"decided by {by.strip()}: {note.strip() or 'no note'}", "decided_by": by.strip(), "decided_at": now_iso()}
    run.state["counts"] = counts_of(run.ledger["mentions"])
    run.save()
    run.log("human_gate", f"{mention_id} resolved by {by.strip()}: about={about_subject} risk={m['final']['risk']}", note=note.strip())
    return run


RESPONSE_SYSTEM = """Draft a short public reply on behalf of the subject to the mention given. Calm, factual, no defensiveness, no
promises you cannot keep, no legal language. Under 90 words. State only facts that appear in the profile or the
mention. No em dashes, no hashtags, no filler. Return plain text."""


def request_response(run: Run, mention_id: str, by: str, note: str, llm: LLM | None = None) -> Run:
    """Gate 1: a named human approves that a response be drafted. Only then does the model write one."""
    m = next((x for x in run.ledger["mentions"] if x["id"] == mention_id), None)
    if not m:
        raise RuntimeError(f"no mention {mention_id}")
    if not by.strip() or len(note.strip()) < 5:
        raise RuntimeError("drafting needs a name and a short note")
    if m["final"]["about_subject"] == "no":
        raise RuntimeError("this mention was set aside as not about the subject")
    responses = run.ledger.setdefault("responses", {})
    responses[mention_id] = {"status": "drafting", "requested_by": by.strip(), "request_note": note.strip(), "requested_at": now_iso()}
    run.save()
    run.log("response", f"{mention_id}: drafting approved by {by.strip()}", note=note.strip())
    llm = llm or LLM(run.state["models"]["second_opinion"], log=run.log)
    user = (f"Subject: {m['subject']}\nProfile: {run.ledger['profile'].get('profile')}\n\nMention title: {m['title']}\n"
            f"Mention text: {m['snippet']}\n{_mention_text(m)[:2500]}\n\nWhy it needs a reply: {m['pass1']['reason']}\nHuman's note: {note}")
    draft = lint.mechanical_fix(llm.text(RESPONSE_SYSTEM, user, max_tokens=300).strip())
    responses[mention_id].update({"status": "draft", "draft": draft, "drafted_at": now_iso(),
                                  "lint": [str(i) for i in lint.lint_text(draft)]})
    run.save()
    run.log("response", f"{mention_id}: draft written, waiting for approval", lint=responses[mention_id]["lint"])
    return run


def approve_response(run: Run, mention_id: str, by: str, note: str, edited: str | None = None) -> Run:
    """Gate 2: a named human approves (optionally edits) the draft. It is marked ready; the system never posts it."""
    r = (run.ledger.get("responses") or {}).get(mention_id)
    if not r or r.get("status") != "draft":
        raise RuntimeError("no draft waiting for approval on this mention")
    if not by.strip():
        raise RuntimeError("approval needs a name")
    if edited and edited.strip():
        r["draft"] = edited.strip()
        r["edited"] = True
    r.update({"status": "approved", "approved_by": by.strip(), "approve_note": note.strip(), "approved_at": now_iso()})
    run.save()
    run.log("response", f"{mention_id}: draft approved by {by.strip()}, ready for a human to post manually", note=note.strip())
    return run


def decline_response(run: Run, mention_id: str, by: str, note: str) -> Run:
    r = (run.ledger.get("responses") or {}).get(mention_id)
    if not r:
        raise RuntimeError("no response request on this mention")
    r.update({"status": "declined", "declined_by": by.strip(), "decline_note": note.strip(), "declined_at": now_iso()})
    run.save()
    run.log("response", f"{mention_id}: draft declined by {by.strip()}", note=note.strip())
    return run
