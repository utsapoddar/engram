---
id: "demo-fact-ingest-limit-near-duplicate"
type: "fact"
status: "confirmed"
created_at: "2000-01-01T00:00:00+00:00"
updated_at: "2000-01-01T00:00:00+00:00"
last_verified: "2000-01-01T00:00:00+00:00"
source_refs: []
tags: ["orbit-api", "batching"]
---

The recommended Orbit API upload contains 400 to 500 fictional telemetry
observations, with 500 as the hard per-request ceiling. Client libraries split
larger collections automatically.
