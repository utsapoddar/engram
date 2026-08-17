from __future__ import annotations

import json
from pathlib import Path

from .config import LOCAL_CORPUS


def run_eval(store, fixture: Path):
    fixture_data = json.loads(Path(fixture).read_text())
    rows = fixture_data["cases"]
    for distractor in fixture_data.get("distractors", []):
        try:
            store.get(distractor["id"])
        except KeyError:
            store.remember("fact", distractor["body"], id=distractor["id"], tags=["eval", "distractor"])
    for row in rows:
        try:
            store.get(row["id"])
        except KeyError:
            store.remember("fact", row["body"], id=row["id"], tags=["eval"])
    hits, ranks = 0, []
    for row in rows:
        ids = [result["id"] for result in store.index.search(row["query"], corpus=LOCAL_CORPUS, limit=5)]
        if row["expected_id"] in ids:
            hits += 1
            ranks.append(ids.index(row["expected_id"]) + 1)
        else:
            ranks.append(None)
    return {"queries": len(rows), "hits_at_5": hits,
            "recall_at_5": hits / len(rows) if rows else 0.0, "ranks": ranks}
