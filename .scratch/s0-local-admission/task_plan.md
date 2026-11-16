# S0 implementation

## Scope and completion

Implement tickets 01–10 on integration branch `feat/s0-local-admission`. Follow the existing module SPECs and ticket acceptance criteria. Each ticket needs a commit, executed checks, validation evidence, an Answer, and status `resolved`. Finish with integrated runtime/browser verification and review. No push or production deployment.

## Dependency graph

`01 → 02 → 03`; `03 → 04 → 06`; `03 → 05, 09`; `06 → 07, 08`; `05, 07, 08, 09 → 10`.

Each implementer gets a fresh context, branch, and worktree under `.worktrees/`, based on the integration tip. Merge completed work sequentially. Assign ownership explicitly and preserve unrelated changes. The parent owns the module map and this plan.

## Validation and risks

- Use ticket-defined public interfaces and behavior tests; read the `tdd` skill. Run real PostgreSQL/Redis integration checks where required.
- Use existing test containers and project environments; keep credentials out of output and evidence.
- Test actual HTTP behavior and browser interactions through gateway for relevant tickets. Preserve screenshots and validation records.
- Review complete diffs, including added files. Require two clean review rounds for substantial changes.
- Shared migrations, app assembly, generated API types, and control wiring need integration checks after merges.
- Remote GitHub Actions execution is separate from implementing and locally validating the workflow. Do not push to obtain it.
- Never delete pre-existing volumes or user worktrees. Clean only task-created, integrated worktrees.

## Progress

- [x] Observe Claude session `4f8056ea-9747-4623-ad40-d8ca5b1d9ed0` until explicit completion.
- [x] Close remaining ticket 01 acceptance gaps.
- [x] Implement and integrate 02, then 03.
- [ ] Run ready tickets 04, 05, 09 concurrently.
- [ ] Integrate 06, then run 07 and 08 concurrently.
- [ ] Complete 10 and integrated acceptance.
- [ ] Review, fix findings, update tracker and map, clean task worktrees.

## Session log

### Local execution pointers

- PowerShell: always `login:false`. `uv.exe` is `C:/Users/quqibing/.local/bin/uv.exe`; default existing cache supports `uv sync --frozen --offline` with filesystem approval. Use each worktree interpreter and verify import origin.
- Node24 executable directory: `C:/Users/quqibing/AppData/Local/Microsoft/WinGet/Packages/OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe/node-v24.19.0-win-x64`; prepend it to PATH. Frontend package manager remains pnpm, test runner `vitest run --maxWorkers=1`.
- Existing PG/Redis test-container connections are in ignored `.worktrees/s0-ticket-02/.env.s0-tests`. Read into process environment silently; never print contents or connection strings. Existing fixtures create isolated per-test databases. Do not stop shared test Redis for fault tests;08 must isolate its broker.
- Actual task Compose project `frameread-s0-t02` is served at127.0.0.1:8080, currently uses03worktree config/secrets and has two queued tasks occupying E=2. Parent coordinates rebuilds/browser acceptance; children must not concurrently change this stack or delete its volumes. Old baseline `frameread` stack is separate and must be preserved.
- Browser acceptance helpers are ignored under03worktree `tmp/browser/`; credential file is ignored under02worktree `tmp/s0-admin/password`. Reuse silently, never put passwords in tool arguments. Final cleanup must account for runtime bind mounts before removing worktrees.

- 2026-11-16: Claude completed at 01:06 CST, integration tip `0f05d38`. Ticket 01 remains claimed; its recorded local baseline is 176 passing tests. Root worktree has only pre-existing untracked `.claude/`. No implementation was started before Claude ended.
- 2026-11-16: Ticket 01 resolved and merged at `4ffa24f` (implementation `431aa59`, evidence `275d0c7`). Final local suite: 177 passed; lint/type/lock checks passed; exact health CLI longest 0.369s; isolated runtime network observation had zero external TX with a positive control. Remote CI remains unrun. Ticket 02 started in `.worktrees/s0-ticket-02`.
- 2026-11-16: Corrected local T1 ordering wording in M03 and Ticket03 to match existing SPEC §7.1/§9.1 and M01: look up accepted keys before the write gate, which applies only to new admission. Research notes: `C:/Users/quqibing/AppData/Local/Temp/frameread-s0-admission-notes.md`.
- 2026-11-16: Ticket 02 in progress with disjoint auth/frontend/gateway owners. Reported focused checks: 17 CLI/pure-security tests and 16 real-PG/Redis HTTP tests passed; full integrated/browser acceptance pending. Its ignored `.env.s0-tests` supplies test-container connections without exposing credentials. Added mypy-cache ignore to prevent generated SQLite caches being staged.
- 2026-11-16: Parent review found session-read metadata and session cleanup bypassing the frozen gate. Ticket02 reproduced three regression cases and fixed them under an instance SHARE lock; auth/cleanup focused suite now 21 passed. Excluded task worktrees, local agent settings, and environment files from Docker build context before final root builds.
- 2026-11-16: Original Ticket02 implementer hit a usage limit after code and runtime checks; a fresh closeout implementer took over the existing worktree. Parent completed 10 real Playwright browser checks, saved two DOM snapshots and seven screenshots, and viewed every image at desktop/mobile sizes with no layout defects found. CSRF rejection triggered one refresh GET without automatic DELETE replay; the sixth incorrect password returned 429. Evidence lives under the Ticket02 worktree `docs/validation/s0-ticket02/`; final code review, tracker closure and integration pending.
- 2026-11-16: Ticket02 resolved and merged at `0eddb23` (code `bcc592e`, evidence `bc6f063`). Final backend 217 passed, frontend 13 passed; lock/lint/type/build and regenerated OpenAPI/TS byte comparisons passed; two clean implementation reviews plus independent merger preflight. Child auto-review rejected merge for missing original user context; parent supplied the actual user-invoked implement-spec step5 and disjoint-change evidence, and local merge was approved. Ticket03 started from this integration tip in `.worktrees/s0-ticket-03`, with parser/frontend/backend work allowed in disjoint ownership. Runtime02 task project `frameread-s0-t02` and its ignored secrets are retained for continuation; never delete its volumes.
- 2026-11-16: After further agent quota interruptions, parent owns Ticket03 backend/runtime and a fresh frontend-only agent handles frontend regressions. Added an actual failing gate/actions test (two failures), fixed snapshot projection using the same RR snapshot for task/epoch/gate, then ran final backend suite: 256 passed; Ruff, format and strict mypy passed. Reused unchanged locked Ticket02 dependencies with explicit Ticket03 PYTHONPATH and verified import origin because03venv was incomplete; stopped an unnecessary download. Added0004 nullable task references, preserving already-applied0003. Excluded task tmp data from Docker context and stopped the completed Ticket01 observation container. Frontend/runtime/browser completion remains pending.
- 2026-11-16: Ticket03 final implementation `0c03ded`, synced integration at `c01f901`. Own worktree environment restored offline. Final checks: 258 backend and35frontend passed, Ruff/format/strictmypy/locks/typecheck/build passed, regenerated contracts byte-identical. Actual HTTP202/replay/conflict/snapshot passed; Playwright10checks plus5screenshots viewed. Fixed gateway DNS caching; actual address change recovered in2.516s without gateway restart. Independent merger review pending. Followup05 must distinguish known QUEUE_FULL from ADMISSION_UNCONFIRMED while preserving the key; followup07 must refresh same-revision ambient allowed_actions when adding cancel UI, and show attempt_no for08.
- 2026-11-16: Fresh merger reviewed all03diff through `d3c5abd`, found no blocking issue, verified compatibility with333d620. Ticket03 resolved and integrated; code0c03ded, evidence397f6e1, deployment-doc correctiond3c5abd. Starting04/05/09in separateworktrees. Ticket05 also owns in-flight submit field locking and persisting uncertain status before network send, so refresh/response loss cannot change input under the original key.
- 2026-11-16: Parent checked official Celery5.6.3 docs through Context7 for06 preparation. [signals](https://github.com/celery/celery/blob/v5.6.3/docs/userguide/signals.rst): worker_process_init runs perchild and handlers must not block beyond4s; create/dispose DB pools aroundfork and avoid starting inherited heartbeatthreads. [calling](https://github.com/celery/celery/blob/v5.6.3/docs/userguide/calling.rst): apply_async retry=False disables producer retries. [Redis](https://github.com/celery/celery/blob/v5.6.3/docs/getting-started/backends-and-brokers/redis.rst): visibility timeout settings must agree; no resultbackend per projectSPEC. Keep5.6series, realprefork verification in Linuxcontainer. scripts/check_compose_s0.py currently expects fourreadychecks and06 must add worker_heartbeats expectation whenregisteringprobe; final10 mustcheckrealhealthfaults.
- 2026-11-16: User explicitly approved deleting `.scratch/frameread-v1/spec-brief-batch-a.md` only AFTER S0 acceptance passes. Keep until then; Ticket10 cleanup may execute without asking again, update any affected references.
- 2026-11-16: Ticket04 resolved and integrated at `1cd421f` (implementation `9ad4af6`, evidence `aabb76b`, whitespace correction `799edf2`). Final backend suite 270 passed; Ruff/format/strict mypy/locked dependencies passed. Independent merger reviewed the complete diff. Root preserves pre-existing AGENTS.md/.claude/.tmp-ticket09 changes.05 and09 have resumed in their existing worktrees;06 is now unblocked. Delegation messages have a transport issue, so resumed agents inherit assignment context.
