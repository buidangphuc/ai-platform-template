# Research Workspace

This folder is for experiments, datasets, training templates, evaluation templates, and promoted artifacts. It is intentionally local-first: scripts run without cloud credentials and produce files that can be reviewed before anything is brought into `app/`.

Promotion rule:

- Every promoted artifact needs a manifest in `research/artifacts/`.
- The manifest must include runtime dependencies, an eval report or smoke result, and risk notes.
- App code should consume promoted artifacts only after the manifest is valid.

Useful commands:

```bash
make eval-smoke
uv run python research/training/train_template.py --output research/artifacts/sample_model_manifest.yaml
```
