---
id: "demo-pattern-dead-letter"
type: "pattern"
status: "confirmed"
created_at: "2000-01-01T00:00:00+00:00"
updated_at: "2000-01-01T00:00:00+00:00"
last_verified: "2000-01-01T00:00:00+00:00"
source_refs: []
tags: ["orbit-api", "recovery"]
---

Malformed fictional telemetry enters a bounded dead-letter queue with a reason
code and payload checksum. Operators replay only after a parser change and
never edit queued payloads in place.
