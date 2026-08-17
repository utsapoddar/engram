---
id: "demo-decision-idempotency-keys"
type: "decision"
status: "confirmed"
created_at: "2000-01-01T00:00:00+00:00"
updated_at: "2000-01-01T00:00:00+00:00"
last_verified: "2000-01-01T00:00:00+00:00"
source_refs: []
tags: ["orbit-api", "ingest"]
---

Every Orbit API telemetry upload includes an idempotency key derived from the
fictional satellite identifier, observation window, and payload checksum.
Servers retain accepted keys for 24 hours.
