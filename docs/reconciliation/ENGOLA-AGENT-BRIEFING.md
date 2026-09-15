# ENGOLA — AGENT BRIEFING (read this before touching anything)

You are one of several AI agents that have worked on Engola, a private AI
chief-of-staff for its owner, Engola Innocent. Multiple agents (Claude
sessions, ChatGPT, a Replit agent) have worked on this independently,
across dozens of exported zips, without a shared source of truth. That is
the single biggest risk to this project — not missing features. Read this
whole file before writing or claiming anything.

## 1. The actual state of the world (verified by direct inspection, 2026-09-13)

The owner uploaded four things in one batch: a "Stitch"-generated React/
Tailwind UI concept (`stitch_engola_ai_chief_of_staff_ui_architecture.zip`),
a giant archive of ~40 historical zips spanning v0.1 through v0.19
(`Engola_Jarvis.zip`), and two prompt documents written for whichever agent
picks this up next. Here is what inspecting the actual files (not the
prose claims inside them) showed:

- **There are at least three divergent "current" states**, none aware of
  the others:
  1. `canonical/engola-v05/` inside `Engola-MASTER-Handoff-2026-09-07.zip`
     — a single-file `app.py` FastAPI prototype. Its own `STATUS-TRUTH.md`
     explicitly says the router split does *not* exist here.
  2. `Engola-current.zip` — a **router-split FastAPI app (v0.6)** with
     `core/` and `routers/` packages, a `.venv`, and passing offline
     tests. This is the most architecturally advanced real codebase in
     the whole upload. It already implements: WebAuthn owner auth,
     chat/memory/permissions routes, a YouTube media router
     (`/api/media/youtube`, `/api/media/study`) wired to a working
     frontend, a Uganda knowledge-source registry, career-match scoring,
     Google OAuth (fails honestly if unconfigured), and voice
     **output** (browser `speechSynthesis`, British-voice preference,
     paced narration via `/api/voice/narrate`).
  3. One of the two uploaded prompt documents was written as if
     addressing a **Replit project** that may not have any of the above —
     it assumes voice and YouTube "regressed" and need restoring, and
     tells the agent to audit before assuming. That instinct is correct,
     but it should be pointed at `Engola-current.zip` as the reference
     for what "restored" should look like, not reinvented from scratch.
- **The Stitch/Magic Patterns UI concept is a disconnected mockup.** It's
  a clean React+Tailwind information architecture (Chat + Knowledge/
  Media/Tasks/Memory/Capabilities tabs, tiered source-authority model,
  honest "transcript vs metadata vs caption" labeling, KNOW→THINK→
  PREPARE→APPROVE→ACT→VERIFY→REMEMBER action lifecycle) — genuinely good
  UX thinking — but its `storage.ts` persists only to browser
  `localStorage` and it makes **zero calls** to the real FastAPI backend.
  Treat it as a wireframe/spec, not a deliverable to merge as-is.
- **Concretely verified gap:** v0.6's frontend has `speechSynthesis`
  (voice *out*) fully wired, but **no `SpeechRecognition`/microphone
  input anywhere** in `static/index.html`. So "voice" is half-built:
  Engola can talk, it cannot yet listen. This is a precise, checkable
  target — don't assume more or less than this.
- The zip collection contains many near-duplicate patch files
  (`-FIXED`, `-1`, `-2`, `-patch`, `-patch-1`...) for the same version
  number, with no changelog distinguishing them. Nobody — human or
  agent — can currently tell which one is authoritative just from the
  filename.

## 1.5. Update (verified 2026-09-13, later same day): a GitHub repo already exists

A fourth upload, `Engola.zip`, turned out to be a real GitHub export —
its zip comment field contains the commit SHA
`2c6555b63b7b4451126da109f95e234ee1f30e0c`, dated 2026-09-06/07, matching
`Engola-GitHub-Transfer-2c6555b-2026-09-07-2.zip` inside the historical
archive. This is **not** a fourth divergent state — a full recursive diff
against `Engola-current.zip` shows it is a strict, clean ancestor: every
difference (`routers/work.py`, `core/agent.py`, appended `tasks` table in
`core/db.py`, updated `chat.py`/`memory.py`/frontend) exists only in
`Engola-current.zip`'s favor. Nothing was removed or rewritten; nothing
exists on GitHub `master` that current.zip lacks. GitHub `master` is
simply frozen at v0.6.0 while local work advanced to v0.10.0.

**Correction to Step 2 below:** do not create a new repo. Clone/pull the
existing GitHub repo, replace its contents with `Engola-current.zip`'s
tree in a single commit on top of `2c6555b`, and tag it `v0.10.0`. This
is a fast-forward, not a merge — there is no conflict to resolve.

## 2. Root cause

The project's actual problem isn't the feature set — it's that **git is
not being used as the source of truth**. Instead, each agent session ends
by exporting a zip, and the next session (sometimes a different AI, on a
different platform) starts from whichever zip it was handed, with no
guaranteed relationship to what actually shipped last. Every "regression"
the owner has experienced (lost voice, lost YouTube study) is a natural
consequence of that pattern, not of any one agent being careless. Fixing
the workflow fixes the recurring symptom.

## 3. What you must do if you are the agent picking this up

1. **Do not trust any prose status claim, including this one, over the
   actual filesystem.** Inspect the code first. If a `.git` directory or
   GitHub remote is reachable, that supersedes every zip.
2. **A GitHub repo already exists at commit `2c6555b` (v0.6.0, master
   branch) — do not create a new one.** Pull it, replace its tree with
   `Engola-current.zip`'s contents (verified clean fast-forward, see
   §1.5), commit, and tag `v0.10.0`. From this point forward, every
   session should start with a pull and end with a commit — no more
   zip handoffs between agents.
3. **Never claim a capability exists without finding the code that
   implements it.** In particular: "Engola watched this video" is never
   true — only transcript/caption/metadata-derived analysis exists.
   Label everything by its actual basis (this rule is already correctly
   specified in the project's own docs — keep it).
4. **Next real feature, in priority order** (per the owner's own stated
   priority and confirmed against what's missing):
   - Wire microphone input (`SpeechRecognition`/`webkitSpeechRecognition`)
     into `static/index.html`, feeding the existing chat pipeline, with
     explicit Idle/Listening/Processing/Responding/Error states and
     graceful fallback when unsupported — completing the voice loop that
     already has working output.
   - Reconcile the Stitch UI's information architecture (tabs, authority
     tiers, honest media-basis labeling) into the real FastAPI static
     frontend, rather than building it out as a separate unconnected app.
   - Move knowledge search from keyword matching (current) toward the
     Postgres/vector-search architecture already specified in
     `BUILD-SPEC-v0.3.md`, once a real database is provisioned.
   - Leave Telegram-archive and Termux/Android companion work as
     interface stubs only, exactly as currently done — do not fabricate
     integrations that don't exist yet.
5. **Do not do a cosmetic redesign pass.** Multiple docs in this project
   already say this explicitly — respect it. Usability fixes (loading/
   empty/error states, mobile layout, voice status) are fine; gradients
   and decorative rework are not the priority.
6. **Before ending your session**, produce a status report with: what you
   verified by reading code (not by trusting prior claims), what you
   changed, what you tested and how, and what remains unverified. Commit
   and report the commit SHA. Do not say "fully working" for anything
   you didn't actually run.

## 4. Standing rules carried over from the project's own docs (keep these)

- Never expose API keys client-side; never fake authentication or
  biometric verification.
- Financial actions and career submissions are deny-by-default and
  require explicit owner approval.
- OpenAI/paid APIs must stay optional — the app must not break with no
  key configured, and free/browser-native capability is preferred.
- External or irreversible actions follow: KNOW → THINK → PREPARE →
  APPROVE → ACT → VERIFY → REMEMBER.
- Source authority is tiered (primary law/regulation > official guidance
  > international bodies > academic > Wikipedia/general reference >
  general web) — never present Wikipedia as equivalent to primary law.
