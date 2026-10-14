# Spec — Làm sắc lại Claude skills: bỏ chung chung, trỏ vào repo, + menu code-pattern

## Goal

Cắt phần "nói chung chung" khỏi skill Claude ở `~/.claude/skills/**` (nặng nhất: 25 file vendored `parallel-scrum/references/experts/**` = ~12.1k dòng lời khuyên industry generic), thay bằng **anchor trỏ thẳng vào file có thật** trong 2 repo đang làm. Kèm **review compliance** (skill khuyên X — repo có làm X không?) và **một file duy nhất** `code-patterns.md` dạng menu để user tick chọn cách viết code (mục tiêu: code không lê thê, dễ hiểu). Đồng thời điền skill `langfuse` đang là stub rỗng.

## User stories

1. **Agent chạy pscrum** — Given agent load `experts.md`, When cần rubric review cho task backend, Then đọc checklist ngắn + danh sách anchor thật (`app/core/pagination.py`, `app/modules/platform/idempotency/`) thay vì mở file 530 dòng dạy REST-vs-GraphQL generic.
2. **User đọc findings** — Given `plan/findings.md`, When skill khuyên một practice mà repo chưa có (hoặc đã có cách khác), Then finding ghi rõ: trích skill + bằng chứng `path` + phân loại, KHÔNG sửa code repo.
3. **User chọn pattern** — Given `code-patterns.md`, When đọc 6 mục, Then mỗi mục có option A/B/C + ví dụ ngắn từ repo + `Recommended:` + ô tick; user tick xong thì file thành luật cho mọi agent.
4. **Agent làm Langfuse** — Given skill `langfuse` có nội dung, When task chạm tracing/prompt/score, Then thấy đúng anchor backend (`app/modules/ai/llm/langfuse.py`, `scripts/smoke/langfuse_callback.py`, `make smoke-langfuse`, `docker-compose.langfuse.yaml`, `platform/feedback`).

## Non-goals

- KHÔNG sửa code `app/**`, `tests/**`, `src/**` của bất kỳ repo nào. Findings chỉ báo cáo.
- KHÔNG sửa `.agents/**` của 2 repo (skill repo-local) — chỉ thêm **1 file pointer stub** trỏ về `code-patterns.md` (integration wave, backend repo).
- KHÔNG dọn worktree `backend-dev` đang bẩn (user tự dọn) và KHÔNG đụng worktree DS đang có agent khác chạy.
- KHÔNG xử lý việc trùng lặp `feat/assistant-chatbot` vs `001-assistant-foundation` (ghi memory, để sau).
- KHÔNG viết lại `task-packet.md`, `validate_plan.py`, `forcing_questions.md` (đang dùng tốt).
- `plan/` không commit.

## Architecture decisions

- **Nguồn sự thật = branch `dev`** của backend (`/Users/phuc.buidang/Documents/backend*`, dev @ `41aa2fb`) và branch `dev` của DS (`/Users/phuc.buidang/Documents/datasience`). Đọc bằng `git show dev:<path>` — miễn nhiễm với working tree bẩn.
- **Mọi write nằm ngoài repo**: `~/.claude/skills/parallel-scrum/**` + `~/.claude/skills/langfuse/**`. Vì vậy các task chạy được ngay, không chờ user dọn worktree. Ngoại lệ duy nhất: pointer stub ở integration wave.
- **Xử lý `experts/**`**: giữ `experts.md` (checklist dạng quyết định) + `experts/se/forcing_questions.md` (7 gate question, SKILL.md đang trỏ tới) + `experts/ATTRIBUTION.md`. **Xoá 23 file deep-dive generic** (~11.9k dòng). Thay mục "Deep-dive map" trong `experts.md` bằng **"Repo anchors"**: mỗi role → 3-6 anchor thật trong 2 repo.
- **`code-patterns.md`**: canonical tại `~/.claude/skills/parallel-scrum/references/code-patterns.md`; repo nhận **pointer stub 5 dòng** (không copy nội dung → không lệch bản). Đúng **6 mục**: P1 hình dạng hàm (guard clause / nesting / độ dài), P2 error handling, P3 comment & docstring, P4 DI + composition, P5 test style (fake vs mock), P6 lazy import.
- **Codegraph**: `SKILL.md` hiện nêu `codegraph_explore` (thật) lẫn `codegraph_callers` / `codegraph_impact` (không tồn tại trong MCP hiện tại) → chỉ giữ `codegraph_explore` + shell `codegraph explore`; các đoạn "semantic disjointness" viết lại theo đúng khả năng thật.
- **Ngôn ngữ**: skill tiếng Anh (đồng bộ hiện trạng). `findings.md` tiếng Việt (user đọc).
- **Findings phân loại**: `filler` (xoá được, không đổi quyết định) | `stale` (nói sai về tool/repo) | `gap` (repo có thứ skill không biết) | `violation` (repo trái practice skill khuyên — chỉ báo cáo).

## Contracts

**`plan/findings.md`** (Wave 0 → input mọi task Wave 1):
```md
### F<N> — <filler|stale|gap|violation> — target: <file skill sẽ sửa>
Skill nói: "<trích nguyên văn>"
Repo thực tế: <repo>:<path> — <bằng chứng 1 dòng>
Hành động: <xoá | thay bằng anchor X | chỉ báo cáo>
```

**`experts.md` mục Repo anchors** (thay Deep-dive map):
```md
### <ROLE> — repo anchors
- <việc cần làm> → `<repo>:<path>` (<symbol/ý nghĩa 1 dòng>)
```

**`code-patterns.md` mục**:
```md
## P<N> — <tên>   Chọn: [ ] A  [ ] B  [ ] C
A. <1 dòng> — repo: `<path>`
   <snippet 2-4 dòng>
B. <1 dòng> — <repo hoặc phản ví dụ>
Recommended: <A|B|C> — <1 dòng lý do>
```

**Anchor rule** (áp cho mọi task): mọi `path` viết ra phải verify bằng `git show dev:<path>` (hoặc `git --git-dir=<ds>/.git show dev:<path>`) trước khi ghi vào file. Anchor không verify được = task fail.

## Conventions

- Verify từng task: `bash` loop `git show` toàn bộ anchor mới viết + `rg` tên symbol; cuối cùng `python ~/.claude/skills/parallel-scrum/scripts/validate_plan.py plan/`.
- Không đụng: `app/**`, `tests/**`, `src/**`, `.env*`, `alembic/**`, `.agents/**` (trừ pointer stub ở W2), worktree `chatbot/model-serving` (agent khác đang chạy).
- Skill files giữ nguyên frontmatter `name` + `description` (description quyết định việc skill có được trigger — đổi là đổi hành vi, ngoài scope).
- Xoá file dùng `rm` (skill dir không phải git repo).

## Facts đã verify (đầu vào, không verify lại)

- `~/.claude/skills/` chỉ có 2 skill: `parallel-scrum` (SKILL.md 175 dòng + references 12.328 dòng) và `langfuse` (**không có SKILL.md**, chỉ `references/` rỗng từ 2026-05-21 → không load được).
- Top filler đã đọc mẫu: `ds/statistical_methods_advanced.md` (80 dòng, mở đầu "World-class statistical methods advanced for senior data scientist", khuyên "Handle 10x current load"), `de/dataops_best_practices.md` (1.502 dòng, dạy Great Expectations), `se/api_design_patterns.md` (530 dòng, dạy pagination/idempotency/rate-limit generic).
- 18 anchor backend trên `dev` đã verify tồn tại (pagination, errors, resilience, redaction, idempotency, rate_limit, quota, **feedback**, evals/runner, llm/router, rag/factory, bootstrap/addons+resources, completions/stream, tests/factories, Makefile, docker-compose.langfuse.yaml, scripts/smoke/langfuse_callback.py).
- 15 anchor DS trên `dev` đã verify tồn tại (gate.py, dvc.yaml, registry/local+stages, serve/local, components/model_trainer+data_validation, tune/loop, monitor, bench, config/params+serving, constants/paths, .agents/ml-pipeline-repo/SKILL.md, tests/conftest.py).
- MCP codegraph hiện chỉ expose `codegraph_explore`; SKILL.md còn nhắc `codegraph_callers`/`codegraph_impact` (stale).
- Worktree `backend-dev` đang ở branch `dev`, thiếu 20 file tracked + 2 file modified → **chỉ đọc qua `git show`**, user sẽ tự dọn.

## Locked

(chưa — chờ user "chốt")
