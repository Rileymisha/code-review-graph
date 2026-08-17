"""FastMCP server: crg-runner-mcp / crg-runtime-signals-mcp results with LLM interpretation."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.tools.base import ToolResult

from crg_smart_mcp.llm import SYSTEM_INTERPRET, summarize_with_llm
from crg_smart_mcp.runner import run_command

mcp = FastMCP("crg-smart-mcp")

LOG_DIR = Path(".crg-smart-mcp-logs")


def _ok(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


async def _interpret_with_llm(raw_text: str, system_hint: str) -> tuple[str | None, str | None]:
    """Returns (summary, model_name). summary=None means LLM unreachable."""
    import os
    model = os.environ.get("OPENWEBUI_MODEL")

    def _do() -> str | None:
        return summarize_with_llm(
            prompt=raw_text,
            system=system_hint,
            model=model,
        )

    summary = await asyncio.to_thread(_do)
    return summary, model


@mcp.tool()
async def smart_run(cmd: str, timeout_s: int = 120) -> str:
    """Run a shell command and get a human-readable summary.

    Args:
        cmd: Shell command to execute (passed to `bash -lc`).
        timeout_s: Max runtime in seconds (default 120, recommended ≤ 300).

    Returns:
        JSON string with {raw, summary, model}:
        raw: {exit_code, stdout, stderr, duration_ms, truncated, log_file},
        summary: <LLM-interpreted string or null>,
        model: <model name or null>
    """
    try:
        result = await run_command(cmd, Path.cwd(), timeout_s=timeout_s, log_dir=LOG_DIR)
    except Exception as e:
        return ToolResult(
            content=f"ERROR: smart_run failed at runner: {type(e).__name__}: {e}",
            is_error=True,
        )

    raw = {
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_ms": result.duration_ms,
        "truncated": result.truncated,
        "log_file": str(result.log_file) if result.log_file else None,
    }
    summary, model = await _interpret_with_llm(
        f"$ {cmd}\n\n<exit_code>{result.exit_code}</exit_code>\n\n<stdout>\n{result.stdout}\n</stdout>\n\n<stderr>\n{result.stderr}\n</stderr>",
        SYSTEM_INTERPRET,
    )
    return _ok({"raw": raw, "summary": summary, "model": model})


@mcp.tool()
async def smart_run_test(timeout_s: int = 120) -> str:
    """Run `pytest -q` and summarize failures via LLM.

    Returns:
        JSON string with {raw: pytest stdout/stderr/exit_code, summary: <failure-cause explanation>, model}
    """
    try:
        result = await run_command("pytest -q", Path.cwd(), timeout_s=timeout_s, log_dir=LOG_DIR)
    except Exception as e:
        return ToolResult(
            content=f"ERROR: smart_run_test failed at runner: {type(e).__name__}: {e}",
            is_error=True,
        )
    raw = {
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_ms": result.duration_ms,
        "truncated": result.truncated,
        "log_file": str(result.log_file) if result.log_file else None,
    }
    summary, model = await _interpret_with_llm(
        f"$ pytest -q\n\n<exit_code>{result.exit_code}</exit_code>\n\n<stdout>\n{result.stdout}\n</stdout>\n\n<stderr>\n{result.stderr}\n</stderr>",
        "你是 pytest 输出解读助手。如果 exit_code=0,说\"测试通过 + 简要数据\";如果有失败,指出失败的 test 名称和最可能的原因(基于 stacktrace 的最后 5-10 行)。",
    )
    return _ok({"raw": raw, "summary": summary, "model": model})


@mcp.tool()
async def smart_list_signals(kind: str | None = None) -> str:
    """List runtime signals (logs / processes) with LLM categorization.

    Args:
        kind: 'log' | 'process' | None (= both). Mirrors crg-runtime-signals-mcp.

    Returns:
        JSON string with {raw: <list of items>, summary: <categorized human-readable description>, model}
    """
    # We don't have a direct crg-runtime-signals-mcp call here (avoid MCP stdio nesting).
    # Instead: shell out to `ps` / glob log files directly.
    from crg_smart_mcp.runner import run_command

    raw_items: list[dict] = []
    if kind in (None, "process"):
        # Get running Python processes via ps
        try:
            r = await run_command(
                "ps -eo pid=,comm=,rss=,args=", Path("/tmp"),
                timeout_s=10, log_dir=LOG_DIR,
            )
            if r.exit_code == 0:
                for line in r.stdout.splitlines():
                    parts = line.split(None, 3)
                    if len(parts) >= 4:
                        try:
                            raw_items.append({
                                "kind": "process",
                                "pid": int(parts[0]),
                                "comm": parts[1],
                                "rss_kb": int(parts[2]),
                                "args": parts[3][:200],
                            })
                        except ValueError:
                            pass
        except Exception:
            pass

    if kind in (None, "log"):
        # Get recent log files in /tmp
        try:
            r = await run_command(
                "ls -lt /tmp/*.log /tmp/*.txt 2>/dev/null | head -20",
                Path("/tmp"), timeout_s=10, log_dir=LOG_DIR,
            )
            for line in r.stdout.splitlines()[:20]:
                raw_items.append({"kind": "log_raw", "text": line})
        except Exception:
            pass

    summary, model = await _interpret_with_llm(
        f"这些是本机运行时信号:\n\n{json.dumps(raw_items, ensure_ascii=False, indent=2)[:4000]}\n\n请用 1-2 句话告诉我:这些进程在做什么?日志里有什么值得注意的?",
        "你是系统运行时解读助手。基于用户列出的进程和日志,1) 把进程分类(开发服务/守护进程/系统),2) 指出异常或值得注意的项。",
    )
    return _ok({"raw": raw_items, "summary": summary, "model": model})
