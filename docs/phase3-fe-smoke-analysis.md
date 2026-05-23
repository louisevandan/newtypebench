# Phase 3 FE Smoke Failure Analysis (2026-05-24)

## TL;DR

The first frontend 10-instance smoke (Claude Opus 4.7 / reference agent-loop
runner / bruno source) scored **0/10 binary** — but **3 of those failures
were not the agent's fault**. The agent produced a *byte-identical* copy
of the reference PR's patch on three instances and still scored 0,
exposing a reproducibility bug in the frontend harness path that
blocks v1 launch credibility.

## The numbers

| Bucket | Count | Detail |
|---|---:|---|
| Agent fault — wrong / partial diff | 7 | file structure mis-read, logic drift, etc. |
| Harness fault — byte-identical to reference patch, still scored 0 | **3** | #7948, #7947, #7912 |
| Total | 10 | |

The 3 harness-fault cases are the ones to focus on first: they are
existence proofs that the v1 frontend score is not deterministic with
respect to the reference solution itself.

## Per-PR detail

| # | PR | F2P passing | Δ vs reference patch | Verdict |
|---|---|---:|---|---|
| 1 | 8003 | 0/1 | 4 ref files → 3 agent (StyledWrapper.js dropped) | agent |
| 2 | 7987 | 0/1 | 3 → 2 (TabPanelErrorBoundary.js dropped) | agent |
| 3 | 7942 | 2/3 | 6 → 3 (CollectionItem, selectors/tab, snapshot util dropped) | agent |
| 4 | 7989 | 0/3 | 10 → 4 (6 dropped) | agent |
| 5 | **7948** | **4/4** | **byte-identical (1 file, 1705 B)** — P2P 13/14 (1 snapshot regression) | **harness** |
| 6 | **7947** | 0/12 | **byte-identical (1 file, 629 B)** — 12 F2P specs all missing | **harness** |
| 7 | 7762 | 0/1 | 6 → 6 (100% file overlap, sizes differ → logic drift) | agent |
| 8 | 7968 | 0/2 | 5 → 1 (4 dropped) | agent |
| 9 | 7971 | 0/5 | 9 → 5 (4 dropped) | agent |
| 10 | **7912** | 2/3 | **byte-identical (1 file, 9590 B)** — 1 F2P spec missing | **harness** |

## Agent-fault pattern

> 7/10 of the failures were the agent producing only **a subset of the
> files** that the reference PR touched.

Average files dropped: 3–5. The file categories that consistently get
dropped:

- `StyledWrapper.js` — CSS-in-JS visual styling
- `selectors/*.js` — Redux selectors / store derivations
- `utils/snapshot/*.spec.js` — utility test helpers (the agent confuses
  these with the canonical test files and stays away — fair, but the
  reference PR did need to update them)
- `*/index.js` co-located with the changed component — barrel re-exports

PrototypeBench v1's interface (per PLAN.md §5.5) gives the agent designer
all responsibility for prompting / tool allowlist / planning. Our
reference runner under-performs here because it doesn't push the model
to enumerate all related files (`Glob`, then read each). Submitters who
build a better agent against the same task spec will likely close most
of this gap.

## Harness-fault pattern — 3 PRs, byte-identical diffs, score 0

These are the surprising ones.

### #7948 (F2P 4/4, P2P 13/14, regressed: snapshot test)

- The 1 P2P regression is `tests/snapshots/basic.spec.ts::Snapshot: Tab
  Persistence > open tabs are restored after app restart`.
- This is a Playwright **snapshot** test. Snapshot tests are
  notoriously brittle in any CI-vs-local environment difference (font
  rendering, timing, DPI, OS theme).
- Treatment options:
  - exclude `tests/snapshots/**` from P2P sets at extract time, or
  - move snapshot tests into a separate "advisory" tier that doesn't
    fail the score, or
  - require P2P to allow N flaky failures (small constant).

### #7947 (F2P 0/12, P2P clean)

- All 12 F2P specs live in `tests/request/body-scroll/scroll-persistent.spec.ts`.
- Reference patch touches `src/components/RequestPane/Assertions/index.js`
  (629 bytes). Agent's diff equals this byte-for-byte.
- At extract time, head produced 12 passing specs that base did not pass
  → 12 F2P. At score time, the same code state should reproduce those 12
  passes. It produced 0.
- This is the most damning signal.

### #7912 (F2P 2/3, P2P clean)

- Missing spec: `tests/variable-tooltip/variable-tooltip.spec.ts::Variable
  Tooltip > should copy latest val...`
- 2/3 reproduce, 1 doesn't. Slightly flaky but same root cause family
  as #7947.

## Suspected root causes (ranked)

1. **`patch` vs `head_commit` divergence**. Our extractor builds `patch`
   = `git diff base..head -- <non-test paths>`. If the PR landed as a
   *merge* (multi-commit) or if its head also touched lock files /
   build artifacts / config files we elsewhere `:!`-excluded, then
   `base + test_patch + patch` reproduces a *similar* but not *identical*
   tree to the head_commit that originally passed F2P at extract time.
   The byte-identical agent_patch can therefore legitimately produce
   different test outcomes.

2. **bruno's rsbuild build artifacts**. bruno's frontend serves through
   `npm run dev:web` (rsbuild dev). The dev bundler reads `src/`
   directly. *But* the workspace dependencies (`bruno-common`,
   `bruno-requests`, ...) are pre-built into `packages/*/dist/cjs|esm`
   by `npm run setup`. If a reference PR also modifies those upstream
   workspaces (e.g. selectors that get re-exported through
   bruno-common), then base + agent_patch (which only touched
   bruno-app/src) misses those upstream changes. The dist/ build is
   from base's workspace code, not head's.

3. **Playwright e2e timing flake at runtime**. `CI=1` enables 2 retries;
   the docker container has Xvfb, Electron, two webServers. 12/12
   all failing rules out pure flake, but 1/3 missing (#7912) is in the
   timing-flake range.

(1) and (2) are structural — they would affect every submitter, not
just our reference runner. They invalidate the **reproducibility
contract** of `score`. (3) is statistical noise we can amortize with
retries.

## Recommended follow-ups

These are the work items that block "Frontend score is trustworthy" —
not blocking Phase 3 internal beta (where we measure relative model
performance and the noise affects all candidates equally), but blocking
Phase 4 public leaderboard.

1. **Reproduce the byte-identical failures.** Re-run `pbench agent-score`
   on #7947 with the same patch a few times. If results differ run-to-run,
   it's (3). If they're consistent, it's (1) or (2).

2. **Audit `patch` vs the full PR diff for the 3 cases.**
   `gh pr diff usebruno/bruno#7947` vs `instances.bruno.jsonl[#7947].patch`.
   If the PR diff has *more* than `patch` + `test_patch` (e.g. dependency
   bumps, generated files), promote those to `patch` (or to a new
   `build_patch` field the harness applies before scoring).

3. **Implement partial credit** (§9 → §3.2). Even with the harness fixed,
   the contract is currently too strict for FE — see #7948 (1 snapshot
   flake kills the score). A partial-credit score
   `(|F2P_passed| + α·|P2P_passed|) / (|F2P| + α·|P2P|)` would track
   actual model capability much more cleanly.

4. **Exclude snapshot tests from P2P** (or move them to an advisory
   tier). Even after #7948-style flakes are fixed, snapshot tests
   shouldn't be load-bearing on a binary score.

5. **Improve reference runner's file-exploration prompt** — but this is
   §5.5 territory, so the right move is to *document* in the submission
   spec that an agent should `Glob` all files referenced by the related
   modules, not to bake that into the harness contract.

## Open question for the next session

> Is the byte-identical agent_patch failure deterministic? Re-run
> `pbench agent-score --pr 7947 --source bruno` with the same diff
> N=3 times. If results vary → (3) flake. If they're stable at 0/12 →
> (1) or (2) — structural patch/extract bug that needs fixing before
> v1 publishes the next frontend revision.

The agent's actual file-exploration weakness (the 7/10 agent-fault
group) is a separate concern that submitters can solve by writing a
better runner against `pbench score`. We don't need to fix that in the
harness.
