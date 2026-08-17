---
id: "demo-decision-retry-policy"
type: "decision"
status: "confirmed"
created_at: "2000-01-01T00:00:00+00:00"
updated_at: "2000-01-01T00:00:00+00:00"
last_verified: "2000-01-01T00:00:00+00:00"
source_refs: []
tags: ["orbit-api", "reliability"]
---

Orbit API clients retry with exponential backoff starting at 200ms, capped at
five attempts. Retries apply only to 429 and 5xx responses; other client errors
are surfaced immediately.

**Why:** Immediate retries magnified load when the fictional ingest tier shed
burst traffic.
