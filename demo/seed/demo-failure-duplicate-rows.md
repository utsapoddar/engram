---
id: "demo-failure-duplicate-rows"
type: "failure"
status: "confirmed"
created_at: "2000-01-01T00:00:00+00:00"
updated_at: "2000-01-01T00:00:00+00:00"
last_verified: "2000-01-01T00:00:00+00:00"
source_refs: []
tags: ["orbit-api", "postmortem"]
---

A fictional retry race created duplicate telemetry rows because the checksum
was recorded after insertion. The fix records the idempotency key in the same
transaction as the batch.
