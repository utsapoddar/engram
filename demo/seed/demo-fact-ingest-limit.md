---
id: "demo-fact-ingest-limit"
type: "fact"
status: "confirmed"
created_at: "2000-01-01T00:00:00+00:00"
updated_at: "2000-01-01T00:00:00+00:00"
last_verified: "2000-01-01T00:00:00+00:00"
source_refs: []
tags: ["orbit-api", "limits"]
---

Orbit API accepts at most 500 fictional telemetry observations in one ingest
request. Larger uploads must be divided into multiple idempotent batches.
