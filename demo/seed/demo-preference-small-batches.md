---
id: "demo-preference-small-batches"
type: "preference"
status: "confirmed"
created_at: "2000-01-01T00:00:00+00:00"
updated_at: "2000-01-01T00:00:00+00:00"
last_verified: "2000-01-01T00:00:00+00:00"
source_refs: []
tags: ["orbit-api", "batching"]
---

The Orbit telemetry team prefers ingest batches near 500 observations. Smaller
batches simplify retries and keep fictional ground-station uploads within the
normal latency budget.
