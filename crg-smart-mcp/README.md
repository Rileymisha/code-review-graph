# crg-smart-mcp

stdio MCP server: crg-runner-mcp / crg-runtime-signals-mcp results with LLM interpretation.

## Tools

- `smart_run(cmd, timeout_s=120)` — 跑命令,返 raw 输出 + LLM 总结
- `smart_run_test(timeout_s=120)` — 跑 `pytest -q`,返 raw + 失败原因解读
- `smart_list_signals(kind?)` — 列进程/日志,返 raw + 分类解读

## env

| Var | 必填 | 默认 |
|---|---|---|
| OPENWEBUI_SMART_KEY | ✅ | shell `export`;`.mcp.json` 用 `${...}` 占位 |
| OPENWEBUI_BASE_URL | ❌ | http://localhost:3000 |
| OPENWEBUI_MODEL | ❌ | minimax |

## 安装

```bash
cd /home/riley/workspace/code-review-graph/crg-smart-mcp
uv venv --python 3.10 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
```

## 测试

```bash
.venv/bin/pytest -v
```

## 注册(同 crg-runner-mcp)

编辑 `code-review-graph/.mcp.json` + `~/.cursor/mcp.json`,加:

```json
"crg-smart-mcp": {
  "type": "stdio",
  "command": "/home/riley/workspace/code-review-graph/crg-smart-mcp/.venv/bin/python",
  "args": ["-m", "crg_smart_mcp"],
  "cwd": "/home/riley/workspace/code-review-graph/crg-smart-mcp"
}
```

重启 Cursor 后 `mcp__crg-smart-mcp__*` 出现。
