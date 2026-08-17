---
id: "demo-failure-clock-skew"
type: "failure"
status: "confirmed"
created_at: "2000-01-01T00:00:00+00:00"
updated_at: "2000-01-01T00:00:00+00:00"
last_verified: "2000-01-01T00:00:00+00:00"
source_refs: []
tags: ["orbit-api", "time"]
---

A fictional ground-station clock jumped ahead and caused fresh observations to
look expired. Orbit API now compares event time with receipt time and
quarantines implausible skew.
