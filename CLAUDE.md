# Hướng dẫn điều phối dự án (Orchestration Rules)

Bạn là **Orchestrator** chính cho repo này. Trong môi trường có sẵn một trợ lý ngầm là **Codex CLI** (`codex exec`), đã được auth bằng tài khoản công ty.

## Nguồn instruction kiến trúc chung

Khi làm các task hiểu repo, thêm endpoint/service, migrate legacy/DGL, sửa wiring, hoặc review boundary platform/business/API, dùng repo-local skill làm nguồn chuẩn:

- Đọc `.agents/fastapi-template-repo/SKILL.md` trước.
- Đọc thêm `.agents/fastapi-template-repo/references/architecture.md` khi task đụng đến bootstrap, platform capability, business service, API dependency adapter, hoặc migration legacy.
- Nếu agent có tool codegraph, dùng codegraph trước để map flow/symbol; nếu không có thì fallback bằng `rg`, `sed`, `nl`, và focused tests.

Không duplicate lại toàn bộ rule kiến trúc vào `CLAUDE.md`; khi cần sửa convention, sửa trong repo-local agent skill trước để Codex và Claude dùng chung một nguồn.

## Khi nào ủy thác cho `codex exec`

Để tránh làm ô nhiễm context window và để tận dụng quota riêng của Codex, **không tự làm** trong context chính các tác vụ sau — thay vào đó ủy thác qua `codex exec`:

1. Đọc và phân tích các file log thô dung lượng lớn (>1MB).
2. Trích xuất / bóc tách dữ liệu văn bản hàng loạt sang JSON có schema.
3. Tạo mock data số lượng lớn.
4. Bulk text transformation (regex sweep, format conversion) trên nhiều file.

## Cách ủy thác

Dùng `Bash` tool gọi `codex exec` theo template sau. Lưu ý `--output-schema` nhận **file path** tới một JSON Schema, không phải inline JSON:

```bash
# Bước 1: ghi schema ra file tạm.
# QUAN TRỌNG: mọi object trong schema PHẢI có "additionalProperties": false
# (OpenAI strict schema mode), nếu không Codex sẽ fail với invalid_json_schema.
cat > /tmp/codex_<task_id>_schema.json <<'EOF'
{
  "type": "object",
  "additionalProperties": false,
  "properties": { "...": "..." },
  "required": ["..."]
}
EOF

# Bước 2: chạy codex với schema đó.
# Tách stderr ra file riêng vì codex in banner/progress ra stderr —
# nếu không tách, JSON output sẽ bị lẫn log và không parse được.
codex exec "<nhiệm vụ mô tả rõ ràng>" \
  --output-schema /tmp/codex_<task_id>_schema.json \
  > /tmp/codex_<task_id>.json \
  2> /tmp/codex_<task_id>.err
```

Nếu không cần structured output, có thể bỏ `--output-schema` và parse text trả về trực tiếp, hoặc dùng `--json` để có event log dạng JSONL.

Sau đó:

1. `Read` file `/tmp/codex_<task_id>.json` để lấy dữ liệu sạch.
2. Dùng dữ liệu đó tiếp tục tác vụ kiến trúc / coding chính.
3. Xóa file tạm khi xong: `rm /tmp/codex_<task_id>*`.

## Khi nào KHÔNG ủy thác

- Sửa code logic / kiến trúc trong `app/` — đây là việc của bạn.
- Đọc file nhỏ (<500 dòng) — tự dùng `Read` cho nhanh.
- Tác vụ cần hiểu sâu code context hiện tại — Codex chạy ngầm không có full context.

## Quy ước file tạm

- Output từ Codex luôn ghi vào `/tmp/codex_*.json` (không commit vào repo).
- Dọn dẹp ngay sau khi consume xong.
