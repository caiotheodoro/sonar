# Test Fixtures

Recorded-fixture layout for adapter tests. Every file in this directory
is produced by ``sonar record`` from a live Monid run; no fixture is
hand-written.

## Layout

```
tests/fixtures/
  <provider>_<endpoint>_<brand>_<timestamp>.json   # raw provider response payload
  runs.jsonl                                        # ledger (one JSON line per RunRecord)
  v1_runs_page.json                                 # snapshot of GET /v1/runs response
  labels.json                                       # sentiment labels (single JSON object keyed by mention_id)
  samples/                                          # hand-built sample payloads (exempt from Rule 1, see samples/README.md)
```

- **One raw payload per (provider, endpoint, brand)**.  The filename
  includes the provider, the last path segment of the endpoint, the brand
  slug, and an ISO-8601 date so that different ``sonar record`` sessions
  produce distinct files.
- **runs.jsonl** — append-only; each line is a
  :class:`~sonar.models.RunRecord` serialised as JSON.  Written *before*
  the ``POST /v1/run`` and updated in-place by ``local_seq`` after the
  run completes.
- **v1_runs_page.json** — the full ``GET /v1/runs`` response captured at
  reconcile time.  Contains the ``runId``, ``status``,
  ``providerResponse.httpStatus``, ``cost``, and ``billedUnits`` fields
  the receipt depends on.
- **labels.json** — a single JSON object ``{"labels": {<mention_id>: {...}, ...}}``
  produced by the two-signal labelling pipeline.  Used by ``test_labeler.py``
  and ``test_rules.py``.

## Recording convention

```bash
uv run sonar record --profile smoke <brand>
```

This runs the smoke-cap sources (reddit + google_maps) against the
brand, writes the raw payloads and ledger to ``tests/fixtures/``, and
logs the spend in ``docs/HANDOFF.md``.  The ``--profile lite`` and
``--profile full`` variants produce additional fixtures as needed.

## Rules

1. **Recorded from real runs, never hand-written.**  A fixture that was
   typed or fabricated is invalid; adapter tests depend on the exact
   field shapes Monid returns.
2. **Committed to the repo.**  Fixtures are version-controlled so that
   adapter tests run offline (no network, no API key).
3. **One file per (provider, endpoint, brand).**  The record command
   deduplicates by overwriting only when the endpoint input digest
   changes.
4. **Spends are logged.**  Every ``sonar record`` run that hits Monid is
   logged in ``docs/HANDOFF.md`` with the run ids and cost.
