# Phase 5 — Verify and ship v1

## Goal
End-to-end proof on real URLs against every requirement, fix
what verification finds, then release v1.0.0.

## Tasks

### 5.1 Full test suite, including the slow tests
- Run the whole suite with no deselections: all 31 tests.
- Check: 31 passed.

### 5.2 End-to-end VOD (the core promise)
- One real YouTube VOD (Rick Astley, already used for Phases
  1–3): `probe` → `clips` → `download_section` of the top
  40-second window → `process` → finished clip.
- Check the output: 1080x1920, H.264/AAC, MP4, 40.0 seconds,
  captions burned in (visible in frames), face tracked (subject
  stays centred). Watch it start to finish via frames sampled
  every 10 seconds.
- Also run the same window through the GUI worker path
  (VodClipWorker, offscreen) to prove the path the user will
  actually use.
- Check: FR1, FR2, FR4, FR8, FR10, FR11, NFR5.

### 5.3 End-to-end live (best effort on this VM)
- Resolve a live Twitch stream, run the monitor for 120 seconds,
  and confirm the chat reader flows, the ring buffer records
  segments, and no crash occurs. Spike triggering itself is
  already proven by synthetic bursts in Phase 2; a real spike
  cannot be scheduled.
- If no stream is live at verification time, record the real
  live run as a manual check for the user instead of faking it.
- Check: FR5, FR6, FR7 (buffer + chat flow; trigger by unit test).

### 5.4 Requirements traceability
- Write `.planning/phase-5/VERIFICATION.md`: every FR1–FR12 and
  NFR1–NFR5 with the evidence that proves it (test name, file,
  or run) or an honest gap.
- Fix list: anything the checks find goes here with its fix and
  re-run result. Re-run until clean.
- Check: no requirement left without evidence or a recorded gap.

### 5.5 Ship v1.0.0
- Version the app (`__version__ = "1.0.0"`, shown in the window
  title), `CHANGELOG.md`, known-issues list in the README,
  README status updated to v1 shipped.
- Deliverable: v1 build (the Phase 4 bundle plus these fixes),
  README, known-issues list.
- Check: the shipped bundle still passes its smoke test after
  any fix, and the README tells the user exactly how to run it
  on Windows.

## Verification criteria
- Every check above passes.
- The fix list is empty or holds only items the user accepted
  as known issues.
- Nothing in the release notes claims a check that did not run.

## Out of scope for this phase
- The Windows build itself (built on the user PC from
  `packaging/build-windows.md`).
- Any new feature. Phase 5 only verifies and fixes.
