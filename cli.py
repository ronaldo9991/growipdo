"""Command line entry points.

  python cli.py run <linkedin-url>
  python cli.py log <run_id>
  python cli.py approve <run_id> --by "Name" --note "What you checked"
  python cli.py list
  python cli.py models
"""
from __future__ import annotations

import argparse
import json
import sys

from app import config, pipeline
from app.ledger import Run


def cmd_run(args):
    run = Run.create(args.url)
    print(f"run {run.id}")
    try:
        pipeline.run_pipeline(run)
    except Exception as e:
        print(f"FAILED at stage {run.state.get('stage')}: {e}", file=sys.stderr)
        print(f"see: python cli.py log {run.id}", file=sys.stderr)
        sys.exit(1)
    c = run.state["counts"]
    print(f"draft ready: {run.diagnostic_path}")
    print(f"{c['verified']} verified, {c['partially_verified']} partially verified, {c['unverified']} refused")
    print(f"approve with: python cli.py approve {run.id} --by \"Your Name\" --note \"what you checked\"")


def cmd_log(args):
    run = Run.load(args.run_id)
    for e in run.read_log():
        line = f"{e['ts']} [{e['stage']}] {e['message']}"
        if e.get("data"):
            line += "  " + json.dumps(e["data"], ensure_ascii=False)
        print(line)
    print(f"status: {run.state['status']} stage: {run.state.get('stage')}")
    if run.state.get("error"):
        print(f"error: {run.state['error']}")


def cmd_approve(args):
    if config.APPROVER_TOKEN and args.token != config.APPROVER_TOKEN:
        print("APPROVER_TOKEN is set; pass --token", file=sys.stderr)
        sys.exit(2)
    run = Run.load(args.run_id)
    pipeline.approve(run, args.by, args.note)
    print(f"approved: {run.diagnostic_path}")


def cmd_list(args):
    for rid in Run.list_ids():
        r = Run.load(rid)
        subj = (r.state.get("subject") or {}).get("full_name") or r.state.get("input_url")
        print(f"{rid}  {r.state['status']:9}  {subj}")


def cmd_models(args):
    from app.llm import list_models
    for m in list_models():
        print(m)


def main(argv=None):
    p = argparse.ArgumentParser(description="prospect diagnostic")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("run"); s.add_argument("url"); s.set_defaults(fn=cmd_run)
    s = sub.add_parser("log"); s.add_argument("run_id"); s.set_defaults(fn=cmd_log)
    s = sub.add_parser("approve"); s.add_argument("run_id"); s.add_argument("--by", required=True)
    s.add_argument("--note", required=True); s.add_argument("--token", default=""); s.set_defaults(fn=cmd_approve)
    s = sub.add_parser("list"); s.set_defaults(fn=cmd_list)
    s = sub.add_parser("models"); s.set_defaults(fn=cmd_models)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
