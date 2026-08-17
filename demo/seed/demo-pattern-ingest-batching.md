---
id: "demo-pattern-ingest-batching"
type: "pattern"
status: "confirmed"
created_at: "2000-01-01T00:00:00+00:00"
updated_at: "2000-01-01T00:00:00+00:00"
last_verified: "2000-01-01T00:00:00+00:00"
source_refs: []
tags: ["orbit-api", "ingest"]
---

Orbit API ingest workers validate an entire batch, persist it once, and
acknowledge it only after the fictional segment checksum is durable. Partial
batch acceptance is not used.
