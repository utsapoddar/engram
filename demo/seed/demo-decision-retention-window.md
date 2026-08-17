---
id: "demo-decision-retention-window"
type: "decision"
status: "confirmed"
created_at: "2000-01-01T00:00:00+00:00"
updated_at: "2000-01-01T00:00:00+00:00"
last_verified: "2000-01-01T00:00:00+00:00"
source_refs: []
tags: ["orbit-api", "storage"]
---

Orbit API keeps full-resolution fictional telemetry for 30 days and hourly
rollups for one year. Retention jobs delete raw segments only after the matching
rollup checksum is verified.
