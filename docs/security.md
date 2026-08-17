# Security model

## Local by default

Engram data stays local, and library operations make zero network calls.
External corpora are read-only. Generated SQLite files, locks, embeddings, and
other files under `state/` are disposable and rebuildable from canonical
Markdown.

Semantic model provisioning is a separate, explicit, network-capable action.
Recall never downloads a model. From the repository root, install the pinned
optional dependency with `python -m pip install -e '.[semantic]'`, then run:

```sh
python - <<'PY'
from pathlib import Path
from fastembed import TextEmbedding
import hashlib, json
p = Path("state/models")
list(TextEmbedding(model_name="BAAI/bge-small-en-v1.5", cache_dir=str(p)).embed(["provision"]))
artifacts = {str(f.relative_to(p)): hashlib.sha256(f.read_bytes()).hexdigest()
             for f in p.rglob("*") if f.is_file() and not f.name.startswith(".engram-model")}
(p / ".engram-model.json").write_text(json.dumps({"model_name": "BAAI/bge-small-en-v1.5", "artifacts": artifacts}))
PY
```

The manifest is written only after successful provisioning. Recall verifies the
configured model name and every artifact hash, uses only the stable
`state/models` cache, and requires the embedding provider to support local-only
loading.

## Write and capture boundaries

`sanitize.py` rejects obvious credentials before a note is written. This is a
defense-in-depth guard rather than a substitute for reviewing content or
running a secret scanner.

Session capture stores metadata and bounded last-visible user and assistant
summaries. It does not copy full transcripts, tool traces, hidden reasoning, or
private chain-of-thought. A capture containing a recognized credential is
rejected.

## History and recovery

Corrections preserve history: the replacement becomes confirmed and the prior
note becomes superseded rather than being overwritten. A durable,
replacement-first journal is recovered before recall, status, and maintenance,
so interruption cannot expose two canonical truths. Because canonical truth is
Markdown, a quarantined or deleted index can be rebuilt without data loss.
