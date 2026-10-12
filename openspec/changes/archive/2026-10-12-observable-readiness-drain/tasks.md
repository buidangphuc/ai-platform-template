## 1. Draining entry

Owns: `app/serve.py`, `app/core/config/runtime.py`, `.env.example`, `Dockerfile`, `README.md`

- [x] 1.1 Delay server and setting; verify `tests/unit/test_serve_entry.py`
- [x] 1.2 Dockerfile CMD and README k8s notes; verify live `python -m app.serve` and `docker stop` polling `/readyz`
