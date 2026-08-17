---
id: "demo-environment-clock-source"
type: "environment"
status: "confirmed"
created_at: "2000-01-01T00:00:00+00:00"
updated_at: "2000-01-01T00:00:00+00:00"
last_verified: "2000-01-01T00:00:00+00:00"
source_refs: []
tags: ["orbit-api", "time"]
---

All Orbit API environments store timestamps in UTC. The fictional telemetry
generator can skew its clock by up to ten minutes for validation tests, while
service clocks remain unmodified.
