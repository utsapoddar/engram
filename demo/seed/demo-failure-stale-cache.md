---
id: "demo-failure-stale-cache"
type: "failure"
status: "confirmed"
created_at: "2000-01-01T00:00:00+00:00"
updated_at: "2000-01-01T00:00:00+00:00"
last_verified: "2000-01-01T00:00:00+00:00"
source_refs: []
tags: ["orbit-api", "cache"]
---

Orbit API once served a fictional satellite's old status after a cache key
omitted the observation date. Cache keys now include satellite, date, and
schema version.
