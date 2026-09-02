# Hand-built sample payloads

Files here are **not** recorded fixtures and are exempt from the rule in
`tests/fixtures/README.md` ("recorded from real runs, never hand-written").
Each filename contains `sample` (either `_sample.json` or `SAMPLE-hand-built-*`)
to make that visible. They exist so adapter tests can run before
`sonar record --profile smoke` (W3.7) lands the real payloads; once a recorded
fixture for the same `(provider, endpoint)` exists, the adapter test switches
to it and the sample is deleted.

See the directory listing for the current set of sample files. Files prefixed
`SAMPLE-hand-built-*` were created to test adapters for which no recorded
fixture yet exists.

Field names follow the endpoint reference table of
`docs/research/2026-09-02-task-graph-and-design.md` and the actor's public
output schema; shapes that differ in the recorded fixture are a schema
finding for the adapter, not for the sample.
