"""Turns the real recording plus the narration into a five minute cut list for Remotion.

Each mark in the walkthrough becomes one cut. A cut is never shorter than its narration,
and long stretches (a run in progress) keep their head and their tail so the viewer sees
the stages advancing and then the finish, rather than a smooth lie.
"""
import json
import os
import pathlib
import sys

FPS = 30
TARGET = 300.0
D = pathlib.Path(os.environ.get("WORK") or pathlib.Path(__file__).parent)

LABELS = {
    "home": "Home",
    "trackB_form": "Track B, the only input",
    "trackB_submit": "Track B, run starts",
    "trackB_running": "Track B, running live",
    "trackB_log": "Track B, audit trail",
    "trackB_done": "Track B, draft ready",
    "trackB_doc": "The diagnostic",
    "trackB_findings": "Verified, partial, refused",
    "trackB_sources": "Source tiers",
    "gate": "Human gate",
    "gate_approve": "Signed off",
    "video": "One minute summary",
    "trackA_form": "Track A, the watch list",
    "trackA_running": "Track A, running live",
    "trackA_brief": "The weekly brief",
    "trackA_queue": "Decisions that need a person",
    "trackA_mentions": "Every mention stays open",
    "end": "Two tracks, both real",
}
WEIGHT = {"trackB_log": 5, "trackA_running": 4, "trackB_running": 3, "trackB_doc": 2,
          "trackB_findings": 2, "trackA_queue": 2, "trackA_mentions": 2, "home": 2}
SPLIT = {"trackB_log", "trackB_running", "trackA_running"}


def build(marks, src_end, vo):
    """One cut per narrated mark. A cut always lasts at least as long as its narration,
    even when that means holding on footage past the next mark, and never runs off the end
    of the recording. Marks with no narration are transitions and are dropped."""
    spans = []
    for i, m in enumerate(marks):
        if m["label"] not in vo:
            continue
        nxt = marks[i + 1]["t"] if i + 1 < len(marks) else src_end
        v = vo[m["label"]]
        floor = v["seconds"] + 2.4
        spans.append({"label": m["label"], "start": m["t"], "avail": max(0.0, nxt - m["t"]),
                      "vo": v, "len": floor})

    for _ in range(120):
        left = TARGET - sum(s["len"] for s in spans)
        if left <= 0.2:
            break
        room = [(s, (s["avail"] - s["len"]) * WEIGHT.get(s["label"], 1)) for s in spans]
        room = [(s, w) for s, w in room if w > 0.01]
        if not room:
            break
        pool = sum(w for _, w in room)
        for s, w in room:
            s["len"] = min(s["avail"], s["len"] + left * (w / pool))

    # anything still unspent goes to the longest stretches so the total lands on target
    left = TARGET - sum(s["len"] for s in spans)
    if left > 0.2:
        big = sorted(spans, key=lambda s: -s["avail"])[:3]
        for s in big:
            s["len"] += left / len(big)

    cuts, cursor = [], 0.0
    for s in spans:
        slack = s["avail"] - s["len"]
        if s["label"] in SPLIT and slack > 8.0 and s["len"] > 16.0:
            head = s["len"] * 0.62
            pieces = [(s["start"], head, True), (s["start"] + s["avail"] - (s["len"] - head), s["len"] - head, False)]
        else:
            pieces = [(s["start"], s["len"], True)]
        for src_from, length, first in pieces:
            src_from = max(0.0, min(src_from, src_end - length))
            cut = {"label": LABELS.get(s["label"], s["label"]), "from": round(cursor * FPS),
                   "len": max(1, round(length * FPS)), "srcFrom": round(src_from * FPS)}
            if first:
                cut["vo"] = s["vo"]["file"]
                cut["voSeconds"] = s["vo"]["seconds"]
                cut["text"] = s["vo"]["text"]
            cuts.append(cut)
            cursor += length
    return cuts, cursor


def main():
    marks = json.loads((D / "marks.json").read_text())
    src_end = float(sys.argv[1])
    vo = json.loads((D / "vo2" / "index.json").read_text())
    cuts, total = build(marks, src_end, vo)
    props = {"clip": "walk.webm", "cuts": cuts, "total": round(total * FPS)}
    (D / "props.json").write_text(json.dumps(props, indent=2))
    print(f"{len(cuts)} cuts, {total:.1f}s ({props['total']} frames) from {src_end:.1f}s of footage")
    for c in cuts:
        print(f"  {c['from']/FPS:6.1f}s  {c['len']/FPS:5.1f}s  src {c['srcFrom']/FPS:6.1f}s  {c['label']}"
              + (f"  [vo {c['voSeconds']}s]" if c.get("vo") else ""))


if __name__ == "__main__":
    main()
