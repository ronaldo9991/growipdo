# Five minute walkthrough

This makes the long video: a real screen recording of the deployed site, cut to a narration
track. It is not a mockup and not a re-enactment. The recording drives the live app and waits
for two real runs to finish, so the footage costs model calls and takes about nine minutes of
wall clock to capture.

Three steps.

**1. Record.** Needs Playwright, which is a capture tool here and not a dependency of the app.

```bash
npm i playwright && SITE=https://growpido.up.railway.app OUT=work/rec node walk.js | tee work/walk.log
```

It drives the site the way a person would: opens the home page, runs Track B on a public
profile URL, watches the stages advance, reads the result, signs the human gate with a real
name, renders the one minute summary, then runs Track A. It prints a `MARKS` line holding the
timestamp of every moment worth cutting to, and writes one webm.

**2. Narrate.** `narration.json` holds one line per mark. Generate one audio file per line,
named after its mark, into `work/vo/`, plus an `index.json` mapping each mark to its file, its
duration in seconds and its text. Any voice will do.

Keep the lines honest. Every number spoken in the narration has to match the run that is on
screen, so after a recording, check the spoken figures against the finished run and rewrite the
lines that no longer hold. The timings in particular move with load.

**3. Compose and render.**

```bash
python3 compose.py <recording_length_seconds>          # writes props.json
cp work/rec/*.webm ../public/walk.webm && cp work/vo/*.wav ../public/vo/
npx remotion render ../src/index.jsx Walkthrough out.mp4 --props=props.json
```

`compose.py` turns the marks into a 300 second cut list. A cut never runs shorter than the
narration sitting on it, long stretches such as a run in progress keep both their head and
their tail so the viewer sees the stages advance and then the finish, and marks with no
narration are treated as transitions and dropped.

The footage and the audio stay out of git: they are tens of megabytes and they are cheap to
make again.
