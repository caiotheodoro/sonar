# Review — `src/sonar/monid/client.py`, `src/sonar/monid/ledger.py`, `tests/test_errors.py`

**Date**: 2026-09-02
**Reviewer stance**: skeptical, no stake in the result
**Checked against**

| Key | Source |
|---|---|
| CONTRACTS | `CONTRACTS.md` `schema_rev` 1.1.0 — §Enumerations `CostSource`, §RunRecord, §Receipt verdict rule |
| D012 | `docs/DECISIONS.md` D012, findings F12 and F13 |
| DESIGN | `docs/research/2026-09-02-task-graph-and-design.md` Appendix §Error matrix (L237–253), §Endpoint reference (L255–272) |

Severity: **S1** wrong number or lost/misrepresented money; **S2** contract
violation that doesn't move a published number; **S3** style or clarity.

Verification method: read the three files against the cited sections line by
line; ran `uv run pytest tests/test_errors.py -q` (8 passed); wrote two
throwaway repro scripts under the session scratchpad (not committed, no
network) that import the real `sonar.monid` package to (a) construct a
`RunRecord` with `cost_source="local"` and (b) run a full submit → 402 →
reconcile cycle and evaluate the CONTRACTS verdict rule against the result.

---

## Verdict: **FAIL**

Four S1 findings, all one bug traced through three files: `CostSource` does
not have the `local` member CONTRACTS 1.1.0 / D012 F12+F13 added, `Ledger`
never stamps `run_id=null` rows `cost_source="local"` "at write time" as the
contract requires, its `reconcile()` compensates with the wrong enum value
under the wrong condition, and `tests/test_errors.py` asserts the wrong
behavior as correct, so the suite is green while the contract is violated.

---

## S1 — wrong number or lost/misrepresented money

### F1. `CostSource` is missing the `local` member the contract added

- CONTRACTS.md:64: `CostSource = Literal["/v1/runs", "unreconciled", "local"]`.
- `src/sonar/monid/ledger.py:33`: `CostSource = Literal["/v1/runs", "unreconciled"]`.
- `src/sonar/models.py:55` carries the identical, identically wrong, literal
  (out of the reviewed scope but load-bearing: it's what `Receipt.verdict`
  actually type-checks against).

Repro (`/private/tmp/.../scratchpad/repro_cost_source.py`, run via
`uv run python`): constructing `ledger.RunRecord(..., cost_source="local", ...)`
raises `pydantic.ValidationError: Input should be '/v1/runs' or
'unreconciled'`. A value CONTRACTS 1.1.0 mandates cannot be represented.

### F2. `Ledger.close()` never reconciles a local-only row "at write time"

- CONTRACTS.md:210: `cost_source`: "`local` for `run_id=null` rows (every
  `LOCAL_*` status), reconciled by construction with `cost_usd=0.0` **at
  write time**".
- `src/sonar/monid/ledger.py:253-271` (`Ledger.close`): the `model_copy`
  update sets `run_id`, `status`, `completed_at`, `provider_http_status`,
  `n_results`, `attempts`, `error` — never `cost_usd` or `cost_source`. A row
  closed with e.g. `LOCAL_REJECTED_402` or `LOCAL_BACKOFF_EXHAUSTED` keeps
  whatever `open()` set: `cost_usd=None, cost_source="unreconciled"`.

Repro confirms: after `ledger.submit(...)` for a 402, the record printed
`2 None LOCAL_REJECTED_402 None unreconciled` — no reconciliation happened at
write time at all; it depends entirely on a later, separate `reconcile()`
call succeeding under specific conditions (see F3).

### F3. `Ledger.reconcile()`'s compensating block writes the wrong `cost_source` under the wrong condition

- `src/sonar/monid/ledger.py:367-379`: when a null-`run_id` row is upgraded,
  it is set to `cost_source="/v1/runs"` — the value CONTRACTS.md:210 reserves
  for "`cost_usd` was filled from the listing", which a `run_id=null` row
  never is (it was never submitted to Monid). CONTRACTS requires
  `cost_source="local"` here, not `"/v1/runs"`.
- The block only runs `if started_at is not None and not unmatched_remote`
  (ledger.py:370, :372). Repro shows that when there is any
  `unmatched_remote_run_id` — a condition unrelated to the local row's own
  correctness — the block never executes and the local row stays
  `cost_source="unreconciled"` forever. This is exactly the scenario
  `tests/test_errors.py:375-419` (`test_reconcile_reports_unmatched_remote_and_keeps_null_rows_unreconciled`)
  exercises, and it asserts (line 416) `result.unreconciled_local_seqs == [2]`
  for the null-`run_id` row — directly contradicting CONTRACTS.md:425 / D012
  F13: "never in `unreconciled_local_seqs`". The test's own name
  ("...keeps_null_rows_unreconciled") documents the violation.
- `ledger.py:318` and `:386` compute `unreconciled_local_seqs` as
  `cost_source != "/v1/runs"`; since a correctly-fixed `local` row is also
  `!= "/v1/runs"`, this filter would keep flagging `local` rows as
  unreconciled even after F1–F3 are fixed, unless it is changed to exclude
  `cost_source == "local"` explicitly.

### F4. `tests/test_errors.py` asserts the wrong value at line 371

- `tests/test_errors.py:371`: `assert (c.run_id, c.cost_usd, c.cost_source) ==
  (None, 0.0, "/v1/runs")` for a `LOCAL_REJECTED_503` row with no `run_id`.
  Per CONTRACTS.md:210 this row's `cost_source` should be `"local"`, not
  `"/v1/runs"`. The test currently locks in the bug from F3.

**Downstream consequence (why this is S1, not S2):** CONTRACTS.md:416-419's
Receipt verdict rule filters `cost_source == "/v1/runs"` only over
`runs if r.run_id is not None` — i.e. a `local` row must never be required to
equal `/v1/runs` to reach `RECONCILED`. `src/sonar/models.py:627`
(`all(r.cost_source == "/v1/runs" for r in runs)`, no `run_id is not None`
filter — also out of the three reviewed files, but this is the function that
actually computes `Receipt.verdict`) has no such exemption. Combined with
F1–F3, a session with even one local-only failure (a 402, an exhausted 429
backoff, a network error) can reconcile every real Monid run perfectly and
still never reach `RECONCILED`, or — worse, per F3 — can reach it only by a
struck-through side effect that mislabels a local row as
`cost_source="/v1/runs"` it never earned. Either way the receipt's
`verdict`/`reconciliation.unreconciled_local_seqs` fields, which
`sonar verify` gates on, misreport reality for any run that ever had a local
failure — which the error matrix says is a normal, expected, exit-0 outcome
(429/`TIMED_OUT`/deadline/`provider_failed`), not a rare edge case.

---

## S2 — contract violation, not (yet) a wrong published number

### F5. `ledger.py` duplicates `RunRecord`/`CostSource` instead of importing them from `models.py`

- `src/sonar/monid/ledger.py:9-11` (module docstring): "`src/sonar/models.py`
  (W2.1) is the package-wide home for records; when it lands, this module can
  import `RunRecord` from there instead of defining it."
- `models.py` has landed (`src/sonar/models.py`, 947+ lines, `RunRecord` at
  line ~440) but `ledger.py:53-88` still defines its own `RunRecord` and
  `ledger.py:33` its own `CostSource`. Both copies are independently, and
  identically, missing `"local"` (F1) — which is exactly how two
  hand-maintained copies of the same enum drift, or in this case, agree to be
  wrong together. Fixing one file without the other silently reintroduces
  the bug the next time either is touched.

### F6. `LOCAL_PENDING` is not a CONTRACTS-recognized status value

- CONTRACTS.md:204 enumerates the local statuses exhaustively as
  `LOCAL_REJECTED_<http>`, `LOCAL_BACKOFF_EXHAUSTED`, `LOCAL_DEADLINE`.
- `src/sonar/monid/ledger.py:35,241`: `Ledger.open()` writes the pre-POST row
  with `status="LOCAL_PENDING"`, a value absent from that list. The ledger is
  append-only and "last line per `local_seq` wins on load" (ledger.py:6); if
  the process crashes between `open()` and `close()`, this un-cataloged
  status value is what a rebuilt `Receipt.runs` row would carry.

---

## S3 — style or clarity

### F7. 402 received mid-poll trips the breaker but keeps polling the same run

- `src/sonar/monid/client.py:404-412` (`MonidClient._poll`): on a 402 while
  polling `GET /v1/runs/{id}`, the breaker trips (`self._breaker.trip(...)`)
  but the loop `continue`s polling the same run rather than returning
  immediately. This is defensible — the breaker's contract job is to stop
  further *submissions*, and this run was already accepted — but it is
  undocumented (the module docstring only describes the POST-time 402 path)
  and untested (`tests/test_errors.py` has no case for a 402 arriving during
  a poll). Worth a one-line comment or a test either way so it reads as a
  decision, not an oversight.

### F8. Stale docstring once F5 is fixed

- `src/sonar/monid/ledger.py:9-11` will need its wording updated once the
  duplicate `RunRecord`/`CostSource` definitions are replaced with an import
  from `models.py` (F5) — currently correctly describes the *intended* end
  state, not what's implemented.

---

## Confirmed consistent (checked, not just assumed)

- 429 backoff: `Retry-After` honoured else `2, 4, 8, 16` s × 4 retries (5
  attempts total) — `client.py:41-42,330-357`, matches
  `tests/test_errors.py:100-154` exactly (`clock.sleeps == [2.0, 7.0]` /
  `[2.0, 4.0, 8.0, 16.0]`).
- 402 process-wide breaker: single module-level `BREAKER` instance shared by
  every `MonidClient` unless explicitly overridden; trips on 402 from POST,
  poll-GET, and listing-GET; blocks all further POSTs including from a
  fresh client on a fresh ledger (`client.py:69-90`, confirmed by
  `tests/test_errors.py:160-186`).
- `TIMED_OUT` / deadline: never resubmitted. `find_submitted()`
  (ledger.py:204-209) keys only on `run_id is not None`, and both a Monid
  `TIMED_OUT` terminal status and a local `LOCAL_DEADLINE` keep `run_id` set
  (client.py `_poll`; CONTRACTS.md:204), so `AlreadySubmitted` fires on any
  retry — confirmed by `tests/test_errors.py:192-227`.
- Reconcile failure (`GET /v1/runs` non-2xx) leaves the ledger untouched and
  reports `fetched_at=None` — `ledger.py:310-321`, matches
  `tests/test_errors.py:284-295`; exit-4 mapping itself lives in `cli.py`,
  out of scope here.
- Provider errors cost 0: a run with a `run_id` whose Monid status is
  `FAILED`/etc. reconciles normally through the ordinary (non-null-`run_id`)
  path to `cost_usd=0.0, cost_source="/v1/runs"` —
  `tests/test_errors.py:369-370`, correct and unaffected by F1–F4 (which are
  specifically about `run_id=null` rows).
- Monid API facts: `POST /v1/run` body `{provider, endpoint, input}`
  (`RunRequest.body()`); 202+`runId` polls `GET /v1/runs/{id}`
  (`client.py:315-329,371-431`); `GET /v1/runs` pages by cursor
  (`nextCursor`/`cursor`/`next_cursor`), `limit=min(limit,100)`
  (`client.py:435-456`, confirmed by `tests/test_errors.py:355-359`); key
  read from `MONID_API_KEY` env var, else `$SONAR_ENV` path, else
  `~/.sonar/.env` (`client.py:36-38,120-132`).

---

## Fix list

Each item is independently applicable.

1. Add `"local"` to the `CostSource` `Literal` in `src/sonar/monid/ledger.py:33`
   (and in `src/sonar/models.py:55`, even though that file is outside this
   review's named scope — F1's repro shows the type is unrepresentable
   without both).
2. In `src/sonar/monid/ledger.py::Ledger.close()`, when the outcome has
   `run_id is None` and `status` starts with `LOCAL_` **and is not**
   `LOCAL_DEADLINE` (which per CONTRACTS.md:204 uniquely keeps its `run_id`
   and must stay `unreconciled` until matched later), add `cost_usd=0.0` and
   `cost_source="local"` to the same `model_copy(update={...})` call that
   already sets `status`/`run_id`/etc., so the row is reconciled "at write
   time" as the contract requires, with no dependency on a later
   `reconcile()` call ever running.
3. In `src/sonar/monid/ledger.py::Ledger.reconcile()` (lines 367-379), stop
   setting `cost_source="/v1/runs"` for `run_id=None` rows. Once fix 2 lands
   this block is redundant for newly-written rows; if kept for ledgers
   written before the fix, it must set `cost_source="local"` (not
   `"/v1/runs"`) and must not be gated on `unmatched_remote_run_ids == []` —
   a local row's correctness has nothing to do with an unrelated unmatched
   remote run.
4. In `src/sonar/monid/ledger.py`, change the `unreconciled_local_seqs`
   computation at lines 318 and 386 from `cost_source != "/v1/runs"` to
   exclude `cost_source == "local"` as well (e.g. `cost_source ==
   "unreconciled"`), so `run_id=null` rows are never listed there, per
   CONTRACTS.md:425 / D012 F13.
5. In `tests/test_errors.py`, change line 371's assertion from
   `(None, 0.0, "/v1/runs")` to `(None, 0.0, "local")` for the null-`run_id`
   row in `test_reconcile_joins_by_run_id_and_pages_by_cursor`.
6. Rewrite `test_reconcile_reports_unmatched_remote_and_keeps_null_rows_unreconciled`
   in `tests/test_errors.py` (currently lines 375-419) to assert
   `result.unreconciled_local_seqs == []` and
   `ledger.records[1].cost_source == "local"` — the point of D012 F13 is
   that a local-only row reconciles independently of whether some other,
   unrelated remote run went unmatched; rename the test to match the
   corrected behavior (e.g. `..._local_rows_reconcile_regardless`).
7. Add assertions to `test_402_trips_breaker_and_blocks_further_posts` and
   `test_rate_limit_exhausts_after_four_retries` in `tests/test_errors.py`
   that the closed record has `cost_source == "local"` and
   `cost_usd == 0.0` immediately, with no call to `reconcile()` — this is
   the "at write time" guarantee from CONTRACTS.md:210 and is currently
   untested.
8. In `src/sonar/models.py`, fix the `Receipt.verdict` computation (around
   line 627) to filter `if r.run_id is not None` before checking
   `r.cost_source == "/v1/runs"`, matching CONTRACTS.md:416-419's verdict
   rule verbatim — otherwise fixes 1-7 are necessary but not sufficient: a
   session with any local-only failure will still never reach `RECONCILED`.
   Also update the `unreconciled` list at line 667 to match fix 4's
   `cost_source == "local"` exclusion.
9. Replace the duplicate `RunRecord`/`CostSource` definitions in
   `src/sonar/monid/ledger.py` (lines 33, 53-88) with an import of both from
   `src/sonar/models.py`, per the module's own docstring intent
   (ledger.py:9-11); update that docstring once done so it describes the
   current state rather than a still-pending migration.
10. Give `LOCAL_PENDING` (`src/sonar/monid/ledger.py:35`) an entry in
    CONTRACTS.md's RunRecord.status local-status list (it's a real, reachable
    persisted value on process crash between `open()` and `close()`), or
    document in the ledger module why it's intentionally excluded from that
    enumeration.
11. Add a test (or a code comment at `src/sonar/monid/client.py:409-412`)
    documenting the decision that a 402 received mid-poll trips the breaker
    but does not abort the in-flight poll of the already-accepted run.
