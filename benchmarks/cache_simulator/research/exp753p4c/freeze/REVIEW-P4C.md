# REVIEW-P4C — independent review record, exp753p4c pre-freeze (2026-11-09)

Instrument (recorded exactly as invoked):
  pi --print --provider mimo --model mimo --no-tools   (pi CLI 1.5.0, Mack)
  Input: REVIEW-BRIEF-P4C.txt (verdicts Q1–Q5 + findings 1–11), raw output REVIEW-P4C-raw.txt.
  (Second pass B closes finding 1 with the full frozen prereg + analyzer/build hashes attached;
  see PASS-B at the end of this file.)

## Reviewer verdicts (pass A)
- Q1 mechanism: **YES** — eos_token_id=-1 makes both stop-checks unreachable (vocab ids ≥ 0),
  loop runs to exhaustion → exactly max_tokens=64 tokens, EOS kept at sampled index; greedy
  argmax, no masking. Empirically confirmed by smoke S1.
- Q2 diff: **YES, minimal** — without the flag behaviorally inert; with the flag the only semantic
  change is the attribute flip (+ provenance). "Flag-inertness for all non-p4 rows is provable
  from sealed evidence: only p4 emitted EOS before step 63, so no other row's stream can change."
- Q3 gate satisfiable: **YES** — break fires only after EOS appended at index 20; tokens 0–20
  identical forced/unforced.
- Q4 smoke design: sound in structure; hygiene defects fixed in smoke v2 (see F10).
- Q5: no P0 in mechanism or diff; hidden confounds = forced warmup footprint (F2), HF/engine
  post-EOS regime mismatch (F3), prereg scope must be attached (F1).

## Findings and dispositions (all closed before freeze; full text in PREREG-P4C.md §8.5)
1. P0 reviewer lacked full prereg/analyzer text → CLOSED by pass B (below) + hashes pinned in
   FREEZE/out/RUN_SHA256.
2. P1 forced warmup / second-order footprint → PREREG §8.5 F2: accepted as the single defined
   intervention; no frozen label consumes cache/latency stats; cross-run median comparison banned.
3. P1 HF-vs-engine asymmetry at index ≥20 → PREREG §8.5 F3: explicit quarantine of engine p4
   suffix; no cross-arm comparison at ≥20 in any claim.
4. P1 build not pinned → run_exp753p4.sh out/RUN_SHA256 now includes generation_loop.py +
   big_modeling.py; smoke fixture hashes recorded in out/SMOKE-PROMPT-HASHES.json.
5. P1 single-construction-path coupling → smoke v2 adds S3 (C-style trace+timing forced run);
   runner adds per-cell FORCED-LEN fail-fast → out/ANOMALY (fail-closed, frozen rules apply).
6. P1 prefix-flake disposition → PREREG §8.5 F6 frozen rule: exactly one attempt per cell, no
   selective rerun; whole-run void + new UID on documented external invalidation only.
7. P2 top-level analyzer safety inferred → grep-verified at freeze (no top-level whitelist).
8. P2 finish_reason under force → harness consumes only output_token_ids; never recorded.
9. P2 elided loop body → re-grep of generation_loop.py (break/finish_reason/output_token_ids)
   recorded in FREEZE at freeze time.
10. P2 smoke hygiene → smoke v2: prompt-identity row matching, explicit presence check for the
    unforced control, negative banner check, fixture hashes, C-style coverage.
11. P2 sticky mutation → noted (one arm per process; no EOS-dependent later phase).

Sequencing: smoke v2 (pre-freeze, disclosed) may yield its own amendments (exp753 §10 precedent);
all such amendments land BEFORE the freeze commit; measurement starts only after freeze.

## Pass B (finding-1 closure; instrument: pi --print --provider mimo --model mimo --no-tools)
Input REVIEW-BRIEF-P4C-B2.txt (full frozen prereg text + analyzer/build script hashes), output
REVIEW-P4C-B2-raw.txt, verbatim verdict:
    FINDING-1-DOWNGRADED: yes
    BLOCKING: none
(First pass-B attempt REVIEW-BRIEF-P4C-B.txt produced tool-call fragments only — output
REVIEW-P4C-B-raw.txt — and was superseded by the B2 retry above; both artifacts retained.)
