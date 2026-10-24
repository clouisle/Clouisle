#!/usr/bin/env python
"""Measure model-facing tool-output encodings with the runtime tokenizer.

Fixtures mirror the payloads produced by the repository's builtin tools:
``search_memory`` / ``get_memory_subgraph``, read-only database tools, MCP,
Skills, and the Asset read/search/list family. The script compares:

* current JSON (``json.dumps(payload, ensure_ascii=False)``),
* compact JSON (no separators whitespace),
* TOON via the official ``toon-format`` package when installed,
* a dedicated text rendering (the current worktree repository renderer for
  ``KNOWN_OUTPUT_TOOLS``, plus candidate renderings for DB/Skill/MCP).

Pass ``--json`` for a machine-readable result document. TOON is an experiment
only and is intentionally not a backend dependency. Install it in a throwaway
environment before running:

    uv venv /tmp/toolout_bench_venv --python 3.13
    uv pip install --python /tmp/toolout_bench_venv/bin/python \
        "tiktoken>=0.12.0" "toon-format==1.2.0"
    cd backend
    PYTHONPATH=. /tmp/toolout_bench_venv/bin/python \
        scripts/benchmark_tool_output_tokens.py [--json]

The script performs no network or model calls.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import struct
import uuid
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

try:
    from app.llm.token_counter import count_tokens
except ModuleNotFoundError:
    # The tokenizer module only needs tiktoken. Lazy-load it by path so the
    # benchmark can run in a throwaway environment without every provider SDK.
    import importlib.util
    from pathlib import Path

    _token_counter_path = (
        Path(__file__).resolve().parents[1] / "app" / "llm" / "token_counter.py"
    )
    _spec = importlib.util.spec_from_file_location(
        "_repo_token_counter", _token_counter_path
    )
    if _spec is None or _spec.loader is None:  # pragma: no cover - defensive
        raise
    _token_counter = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_token_counter)
    count_tokens = _token_counter.count_tokens

from app.utils.tool_output import render_tool_output

try:  # optional experiment dependency
    import toon_format
except ImportError:  # pragma: no cover - documented experiment setup
    toon_format = None

# Actual encoding names resolved by app.llm.token_counter.MODEL_ENCODING_MAP.
ENCODINGS = (("gpt-4", "cl100k_base"), ("gpt-4o", "o200k_base"))


def _cell(value: Any, *, separator: str = "|") -> str:
    if value is None:
        return "NULL"
    text = str(value)
    return (
        text.replace("\\", "\\\\")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace(separator, "\\" + separator)
    )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def text_database_rows(payload: dict[str, Any]) -> str:
    columns = payload.get("columns") or []
    rows = payload.get("rows") or []
    lines = [
        f"columns={','.join(_cell(column) for column in columns)} · "
        f"rows={len(rows)} · truncated={str(bool(payload.get('truncated'))).lower()}"
    ]
    if not rows:
        lines.append("No rows.")
        return "\n".join(lines)
    lines.append("|".join(_cell(column) for column in columns))
    for row in rows:
        lines.append("|".join(_cell(value) for value in row))
    return "\n".join(lines)


def text_mcp_result(payload: dict[str, Any]) -> str:
    if payload.get("error") is not None:
        return _json(payload)
    result = payload.get("result")
    if isinstance(result, str):
        return f"success · result_chars={len(result)}\nresult:\n{result}"
    return _json(payload)


def text_skill_result(payload: dict[str, Any]) -> str:
    lines = [
        f"success={str(bool(payload.get('success'))).lower()} · "
        f"status={payload.get('status')} · duration_ms={payload.get('duration_ms')}"
    ]
    if payload.get("result") is not None:
        result = payload["result"]
        lines.append(f"result: {result if isinstance(result, str) else _json(result)}")
    if payload.get("error") is not None:
        lines.append(f"error: {payload['error']}")
    artifacts = payload.get("artifacts") or []
    if artifacts:
        lines.append(f"artifacts ({len(artifacts)}):")
        for artifact in artifacts:
            lines.append(
                f"- {artifact.get('filename')} · {artifact.get('path')} · "
                f"{artifact.get('size')} B · {artifact.get('content_type')} · "
                f"{artifact.get('url')}"
            )
    if payload.get("stdout_summary"):
        lines.append("stdout_summary:")
        lines.append(payload["stdout_summary"])
    if payload.get("stderr_summary"):
        lines.append("stderr_summary:")
        lines.append(payload["stderr_summary"])
    return "\n".join(lines)


@dataclass(frozen=True)
class Case:
    name: str
    tool: str
    payload: dict[str, Any]
    text: Callable[[dict[str, Any]], str]
    preserve: tuple[str, ...] = ()


def _memory_entity(
    entity_id: str,
    name: str,
    entity_type: str,
    description: str,
    properties: dict[str, Any],
    updated_at: str,
) -> dict[str, Any]:
    return {
        "id": entity_id,
        "name": name,
        "type": entity_type,
        "description": description,
        "properties": properties,
        "updated_at": updated_at,
    }


def _db_rows() -> list[list[Any]]:
    names = [
        "张伟",
        "王芳",
        "李娜",
        "刘洋",
        "陈静",
        "杨帆",
        "赵磊",
        "黄敏",
        "周杰",
        "吴桐",
        "徐晨",
        "孙悦",
        "马超",
        "朱琳",
        "胡斌",
        "郭婷",
        "林浩",
        "何雨",
        "高翔",
        "罗雪",
        "郑凯",
        "梁爽",
        "谢楠",
        "宋佳",
        "唐宇",
        "韩梅",
        "冯刚",
        "邓丽",
        "曹阳",
        "彭博",
    ]
    cities = ["杭州", "上海", "北京", "深圳", "成都", "武汉"]
    departments = ["研发", "产品", "设计", "运营", "销售"]
    rows: list[list[Any]] = []
    for index, name in enumerate(names):
        rows.append(
            [
                index + 1,
                name,
                departments[index % len(departments)],
                cities[index % len(cities)],
                round(60 + (index * 7) % 40 + index / 100, 2),
                12000 + index * 850,
                index % 3 != 0,
                f"2026-{1 + index % 9:02d}-{1 + index % 27:02d}T"
                f"{8 + index % 10:02d}:30:00+08:00",
                None
                if index % 6 == 0
                else (
                    ""
                    if index % 5 == 0
                    else f"季度目标：完成率 {70 + index % 30}% | 备注「{name}」"
                ),
            ]
        )
    return rows


def _code_lines() -> list[dict[str, Any]]:
    source = [
        "from __future__ import annotations",
        "",
        "import asyncio",
        "import json",
        "from dataclasses import dataclass",
        "",
        "",
        "@dataclass(slots=True)",
        "class PipelineStep:",
        '    """一个流水线步骤。"""',
        "",
        "    name: str",
        "    concurrency: int = 4",
        "    retries: int = 0",
        "",
        "    def describe(self) -> str:",
        '        return f"{self.name} (concurrency={self.concurrency})"',
        "",
        "",
        "async def run_step(step: PipelineStep, payload: dict) -> dict:",
        '    """执行步骤，失败时按 retries 重试。"""',
        "    last_error: Exception | None = None",
        "    for attempt in range(step.retries + 1):",
        "        try:",
        "            await asyncio.sleep(0)",
        "            return {",
        '                "step": step.describe(),',
        '                "attempt": attempt,',
        '                "payload": payload,',
        "            }",
        "        except asyncio.CancelledError:",
        "            raise",
        "        except Exception as exc:  # noqa: BLE001",
        "            last_error = exc",
        '    raise RuntimeError(f"{step.name} failed: {last_error}")',
        "",
        "",
        "async def main() -> None:",
        '    steps = [PipelineStep("抽取"), PipelineStep("清洗", retries=2), PipelineStep("入库")]',
        "    results = await asyncio.gather(",
        '        *(run_step(step, {"source": "knowledge-base"}) for step in steps)',
        "    )",
        "    print(json.dumps(results, ensure_ascii=False, indent=2))",
        "",
        "",
        'if __name__ == "__main__":',
        "    asyncio.run(main())",
    ]
    return [
        {"line": number + 1, "text": text, "continuation": False}
        for number, text in enumerate(source)
    ]


def build_cases() -> list[Case]:
    memory_results = [
        _memory_entity(
            "8f14e45f-ceea-4a67-9a3c-1d4a91b7c2aa",
            "张三",
            "person",
            "用户的同事，负责数据平台，偏好简洁的会议纪要和中文沟通。",
            {
                "city": "杭州",
                "role": "数据工程师",
                "skills": ["Python", "SQL", "Flink"],
            },
            "2026-10-20",
        ),
        _memory_entity(
            "3c59dc04-8e9d-4f0e-9c2a-2b6a1f5d7e11",
            "龙井茶",
            "preference",
            "用户喜欢明前龙井，冲泡水温 80℃ 左右，不加糖。",
            {"category": "饮品", "temperature": "80℃"},
            "2026-10-18",
        ),
        _memory_entity(
            "b6d767d2-f7a2-4f7f-8d5b-0a1c3e5f7a90",
            "Clouisle 项目",
            "project",
            "团队正在构建的多租户 Agent 平台，目标是在三季度完成知识库检索优化。",
            {"stage": "beta", "team_size": 8, "deadline": "2026-12-31"},
            "2026-10-22",
        ),
        _memory_entity(
            "6f4922f4-5a3b-4c8d-9e1f-7b2c3d4e5f60",
            "每周跑步",
            "habit",
            "用户每周二、四晨跑 5 公里，配速约 6 分钟。",
            {},
            "2026-10-21",
        ),
        _memory_entity(
            "1f0c2b3a-4d5e-4f60-8a9b-0c1d2e3f4a5b",
            "英语学习",
            "goal",
            "希望年底前通过雅思 7 分，重点提升写作和口语。",
            {"target_score": 7, "exam": "IELTS"},
            "2026-10-19",
        ),
    ]

    subgraph_entities = [
        {
            "id": "8f14e45f-ceea-4a67-9a3c-1d4a91b7c2aa",
            "name": "张三",
            "type": "person",
            "description": "用户的同事，负责数据平台。",
            "properties": {"role": "数据工程师"},
            "depth": 0,
        },
        {
            "id": "b6d767d2-f7a2-4f7f-8d5b-0a1c3e5f7a90",
            "name": "Clouisle 项目",
            "type": "project",
            "description": "多租户 Agent 平台。",
            "properties": {"stage": "beta"},
            "depth": 1,
        },
        {
            "id": "1f0c2b3a-4d5e-4f60-8a9b-0c1d2e3f4a5b",
            "name": "知识库检索优化",
            "type": "task",
            "description": "提升混合检索的召回率与延迟。",
            "properties": {"priority": "P0"},
            "depth": 2,
        },
        {
            "id": "3c59dc04-8e9d-4f0e-9c2a-2b6a1f5d7e11",
            "name": "技术评审会",
            "type": "event",
            "description": "每周五下午的架构评审。",
            "properties": {},
            "depth": 2,
        },
    ]
    subgraph_relations = [
        {
            "id": "aa11",
            "source_entity_id": subgraph_entities[0]["id"],
            "source_name": "张三",
            "relation_type": "works_on",
            "target_entity_id": subgraph_entities[1]["id"],
            "target_name": "Clouisle 项目",
            "description": "负责数据管道部分。",
            "properties": {"since": "2025-03"},
        },
        {
            "id": "aa12",
            "source_entity_id": subgraph_entities[1]["id"],
            "source_name": "Clouisle 项目",
            "relation_type": "includes",
            "target_entity_id": subgraph_entities[2]["id"],
            "target_name": "知识库检索优化",
            "description": None,
            "properties": {},
        },
        {
            "id": "aa13",
            "source_entity_id": subgraph_entities[0]["id"],
            "source_name": "张三",
            "relation_type": "participates_in",
            "target_entity_id": subgraph_entities[3]["id"],
            "target_name": "技术评审会",
            "description": "主讲检索架构。",
            "properties": {"role": "speaker"},
        },
        {
            "id": "aa14",
            "source_entity_id": subgraph_entities[2]["id"],
            "source_name": "知识库检索优化",
            "relation_type": "depends_on",
            "target_entity_id": subgraph_entities[3]["id"],
            "target_name": "技术评审会",
            "description": None,
            "properties": {},
        },
    ]

    code_segments = _code_lines()
    long_line = (
        "这是一段用于验证超长行续读的中文文本，" * 40
        + '包含引号"、反斜杠\\、制表符\t、emoji 🚀 与 Markdown `code`。'
    )
    escaped_segments = [
        {
            "line": 118,
            "text": 'print("他说：\\"你好\\"")  # 反斜杠 \\\\ 与制表符\\t',
            "continuation": False,
        },
        {
            "line": 119,
            "text": 'emoji 🚀🔥 中文标点「引号」、破折号——以及 <xml attr="v">',
            "continuation": False,
        },
        {"line": 120, "text": long_line, "continuation": True},
    ]

    search_matches = [
        {
            "line": 42,
            "text": "检索策略：先做向量召回，再用 BM25 重排，最后按团队权限过滤。",
            "match_start": 0,
            "match_end": 2,
            "truncated": False,
            "context": [
                {"line": 41, "text": "## 混合检索", "truncated": False},
                {
                    "line": 43,
                    "text": "注意：权限过滤必须发生在返回上下文之前。",
                    "truncated": False,
                },
            ],
        },
        {
            "line": 88,
            "text": "混合检索的候选集大小建议为 top_k 的 4 倍；超过 200 条后延迟明显上升。",
            "match_start": 0,
            "match_end": 2,
            "truncated": True,
            "context": [
                {"line": 87, "text": "性能观察：", "truncated": False},
                {"line": 89, "text": None, "truncated": False},
            ],
        },
    ]

    asset_items = [
        {
            "ref": f"a{index:03d}",
            "name": name,
            "type": content_type,
            "size": size,
            "origin": origin,
            "created_at": created_at,
            "capabilities": capabilities,
        }
        for index, (
            name,
            content_type,
            size,
            origin,
            created_at,
            capabilities,
        ) in enumerate(
            [
                (
                    "产品需求文档-v3.pdf",
                    "application/pdf",
                    2_310_442,
                    "upload",
                    "2026-10-23T09:12:00+08:00",
                    ["read", "search", "view"],
                ),
                (
                    "季度复盘.pptx",
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    8_812_004,
                    "generated",
                    "2026-10-22T17:45:10+08:00",
                    ["read", "view"],
                ),
                (
                    "架构图.png",
                    "image/png",
                    182_330,
                    "upload",
                    "2026-10-22T11:03:44+08:00",
                    ["view"],
                ),
                (
                    "interview-notes.md",
                    "text/markdown",
                    12_880,
                    "generated",
                    "2026-10-21T20:15:09+08:00",
                    ["read", "search"],
                ),
                (
                    "客户访谈录音.m4a",
                    "audio/mp4",
                    6_402_119,
                    "upload",
                    "2026-10-21T08:00:00+08:00",
                    ["view"],
                ),
                (
                    "数据分析.csv",
                    "text/csv",
                    88_441,
                    "upload",
                    "2026-10-20T16:31:52+08:00",
                    ["read", "search"],
                ),
                (
                    "产品演示.mp4",
                    "video/mp4",
                    44_120_880,
                    "generated",
                    "2026-10-19T14:20:30+08:00",
                    ["view"],
                ),
                (
                    "术语表.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    400_120,
                    "upload",
                    "2026-10-18T10:10:10+08:00",
                    ["read"],
                ),
                (
                    "迁移脚本.sql",
                    "application/sql",
                    9_300,
                    "generated",
                    "2026-10-17T22:05:00+08:00",
                    ["read", "search"],
                ),
                (
                    "会议纪要-2026-10-16.docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    51_200,
                    "generated",
                    "2026-10-16T18:40:00+08:00",
                    ["read", "search"],
                ),
            ],
            start=1,
        )
    ]

    rss_articles = [
        {
            "title": title,
            "link": f"https://blog.example.com/posts/{index:02d}",
            "citation_id": f"web_{index:016x}",
            "published": f"2026-10-{10 + index:02d}T08:00:00+08:00",
            "author": author,
            "summary": summary,
        }
        for index, (title, author, summary) in enumerate(
            [
                (
                    "混合检索在千万级文档上的落地经验",
                    "张伟",
                    "本文介绍向量召回、BM25 重排与权限过滤的组合策略，并给出延迟与召回率的实测数据。",
                ),
                (
                    "从 JSON 到 TOON：大模型上下文编码实验",
                    "李娜",
                    "我们比较了 JSON、精简 JSON 与 TOON 在中文、表格和代码样本上的 token 消耗，结论并不适用于所有结构。",
                ),
                (
                    "Agent 工具调用的幂等设计",
                    "王芳",
                    "通过稳定任务 ID、持久化状态机和事件去重，避免重试导致的重复副作用。",
                ),
                (
                    "多租户知识库的权限边界",
                    "刘洋",
                    "团队、工作空间与资源可见性之间的关系，以及 PRIVATE 资源的创建者语义。",
                ),
                (
                    "流式响应的断线恢复",
                    "陈静",
                    "基于会话游标和消息分片实现断线续传，避免重复生成与历史丢失。",
                ),
                (
                    "沙箱执行的资源限额",
                    "杨帆",
                    "CPU、内存、磁盘与超时的分级限额，以及超限后的可诊断错误。",
                ),
                (
                    "可观测性：从指标到告警",
                    "赵磊",
                    "把请求延迟、队列积压和失败率串成一条可定位的采集链路。",
                ),
                (
                    "PostgreSQL 索引选择实战",
                    "黄敏",
                    "顺序扫描、位图扫描与覆盖索引在统计聚合查询上的差异。",
                ),
                (
                    "前端长列表的渲染策略",
                    "周杰",
                    "虚拟滚动、分页游标和缓存失效的取舍。",
                ),
                (
                    "发布流程中的灰度与回滚",
                    "吴桐",
                    "使用版本化配置和一次性迁移任务降低发布风险。",
                ),
            ],
            start=1,
        )
    ]

    mcp_json_text = json.dumps(
        {
            "issues": [
                {"key": "YUN-153", "summary": "统计接口越权", "status": "Done"},
                {
                    "key": "YUN-207",
                    "summary": "工具输出 token 优化",
                    "status": "In Progress",
                },
            ],
            "total": 2,
        },
        ensure_ascii=False,
    )

    return [
        Case(
            "memory_search_zh",
            "search_memory",
            {
                "success": True,
                "results": memory_results,
                "count": len(memory_results),
                "message": "找到 5 条相关记忆。",
            },
            lambda payload: render_tool_output("search_memory", payload),
            preserve=(
                memory_results[0]["id"],
                "张三",
                "数据平台",
                "2026-10-20",
                "Python",
                memory_results[2]["description"],
            ),
        ),
        Case(
            "memory_subgraph_zh",
            "get_memory_subgraph",
            {
                "success": True,
                "entities": subgraph_entities,
                "relations": subgraph_relations,
                "truncated": True,
            },
            lambda payload: render_tool_output("get_memory_subgraph", payload),
            preserve=(
                subgraph_entities[0]["id"],
                subgraph_entities[2]["id"],
                "知识库检索优化",
                "works_on",
                "depends_on",
                "depth=2",
                "Result truncated.",
            ),
        ),
        Case(
            "memory_search_empty",
            "search_memory",
            {
                "success": True,
                "results": [],
                "count": 0,
                "message": "未找到记忆。这可能是第一次对话，或者相关信息尚未保存。",
            },
            lambda payload: render_tool_output("search_memory", payload),
            preserve=("count=0", "未找到记忆"),
        ),
        Case(
            "memory_error",
            "search_memory",
            {"success": False, "error": "Memory 工具执行失败"},
            text_mcp_result,
            preserve=("Memory 工具执行失败", "false"),
        ),
        Case(
            "db_rows_paged",
            "postgresql_query",
            {
                "columns": [
                    "id",
                    "name",
                    "department",
                    "city",
                    "score",
                    "salary",
                    "active",
                    "created_at",
                    "notes",
                ],
                "rows": _db_rows(),
                "total_rows": 30,
                "truncated": True,
                "success": True,
            },
            text_database_rows,
            preserve=(
                "张伟",
                "彭博",
                "季度目标：完成率 77% \\| 备注「黄敏」",
                "NULL",
                "truncated=true",
                "2026-01-01T08:30:00+08:00",
            ),
        ),
        Case(
            "db_rows_empty",
            "postgresql_query",
            {
                "columns": [],
                "rows": [],
                "total_rows": 0,
                "truncated": False,
                "success": True,
            },
            text_database_rows,
            preserve=("rows=0", "No rows."),
        ),
        Case(
            "db_error",
            "mysql_query",
            {"error": "sql_query_required", "success": False},
            text_mcp_result,
            preserve=("sql_query_required", "false"),
        ),
        Case(
            "skill_result",
            "skill_docx_report",
            {
                "success": True,
                "result": {"message": "报告已生成", "pages": 12, "language": "zh-CN"},
                "error": None,
                "artifact_count": 2,
                "duration_ms": 2480,
                "status": "completed",
                "artifacts": [
                    {
                        "path": "reports/季度报告.docx",
                        "url": "https://files.example.com/team/2026/q3-report.docx?token=abc",
                        "filename": "季度报告.docx",
                        "size": 184320,
                        "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    },
                    {
                        "path": "reports/chart.png",
                        "url": "https://files.example.com/team/2026/q3-chart.png",
                        "filename": "chart.png",
                        "size": 20480,
                        "content_type": "image/png",
                    },
                ],
                "stdout_summary": "加载模板...\n渲染 12 页...\n完成",
                "stderr_summary": "warning: 字体回退到 Noto Sans CJK SC",
            },
            text_skill_result,
            preserve=(
                "reports/季度报告.docx",
                "https://files.example.com/team/2026/q3-report.docx?token=abc",
                "2480",
                "completed",
                "字体回退",
                "报告已生成",
            ),
        ),
        Case(
            "mcp_json_text_result",
            "mcp_issue_tracker_search_issues",
            {
                "success": True,
                "result": mcp_json_text,
                "error": None,
            },
            text_mcp_result,
            preserve=("YUN-153", "工具输出 token 优化", "result_chars="),
        ),
        Case(
            "mcp_structured_result",
            "mcp_metrics_query",
            {
                "success": True,
                "result": [
                    {"service": "api", "p95_ms": 182.5, "errors": 3},
                    {"service": "worker", "p95_ms": 940.1, "errors": 0},
                ],
                "error": None,
            },
            text_mcp_result,
            preserve=("worker", "940.1"),
        ),
        Case(
            "read_asset_code",
            "read_asset",
            {
                "filename": "pipeline.py",
                "representation_id": "sha256:9f2c4e8a",
                "start_line": 1,
                "total_lines": 120,
                "segments": code_segments,
                "next_cursor": "9f2c",
                "eof": False,
                "ref": "7f3a",
                "citation_id": "cit_asset_7f3a",
            },
            lambda payload: render_tool_output("read_asset", payload),
            preserve=(
                "pipeline.py",
                "lines 1–47/120",
                "9f2c",
                "执行步骤",
                "asyncio.gather",
                "citation_id=cit_asset_7f3a",
            ),
        ),
        Case(
            "read_asset_long_escaped_line",
            "read_asset",
            {
                "filename": "notes.md",
                "representation_id": "sha256:aa11",
                "start_line": 118,
                "total_lines": 120,
                "segments": escaped_segments,
                "next_cursor": None,
                "eof": True,
                "ref": "2b8c",
                "citation_id": "cit_asset_2b8c",
            },
            lambda payload: render_tool_output("read_asset", payload),
            preserve=(
                "他说",
                "反斜杠",
                "emoji 🚀",
                "[line continues]",
                "End of results.",
            ),
        ),
        Case(
            "search_asset_zh",
            "search_asset",
            {
                "filename": "架构设计.md",
                "representation_id": "sha256:bb22",
                "query": "混合检索",
                "total_lines": 300,
                "matches": search_matches,
                "next_cursor": "bb22",
                "eof": False,
                "ref": "5c1d",
                "citation_id": "cit_asset_5c1d",
            },
            lambda payload: render_tool_output("search_asset", payload),
            preserve=(
                "混合检索",
                "42│",
                "88│",
                "snippet clipped",
                "bb22",
            ),
        ),
        Case(
            "list_assets_paged",
            "list_assets",
            {
                "items": asset_items,
                "has_more": True,
                "next_cursor": "a010",
            },
            lambda payload: render_tool_output("list_assets", payload),
            preserve=(
                "a001",
                "a010",
                "产品需求文档-v3.pdf",
                "2026-10-23T09:12:00+08:00",
                "a010",
            ),
        ),
        Case(
            "list_assets_empty",
            "list_assets",
            {"items": [], "has_more": False, "next_cursor": None},
            lambda payload: render_tool_output("list_assets", payload),
            preserve=("No results.",),
        ),
        Case(
            "rss_feed_zh",
            "rss_feed_reader",
            {
                "url": "https://blog.example.com/feed.xml",
                "feed_title": "Clouisle 技术博客",
                "feed_link": "https://blog.example.com",
                "feed_description": "工程实践、架构设计与产品思考。",
                "articles": rss_articles,
                "total_articles": len(rss_articles),
                "citation_id": "web_feed0123456789ab",
                "success": True,
            },
            lambda payload: render_tool_output("rss_feed_reader", payload),
            preserve=(
                "Clouisle 技术博客",
                "混合检索在千万级文档上的落地经验",
                "https://blog.example.com/posts/01",
                "延迟与召回率",
                "发布流程中的灰度与回滚",
                "web_000000000000000a",
            ),
        ),
    ]


def _rows(case: Case) -> list[tuple[str, str, bool | None]]:
    payload = case.payload
    current = json.dumps(payload, ensure_ascii=False)
    compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    text = case.text(payload)
    rows: list[tuple[str, str, bool | None]] = [
        ("current JSON", current, True),
        ("compact JSON", compact, True),
    ]
    if toon_format is not None:
        toon = toon_format.dumps(payload)
        try:
            roundtrip = toon_format.loads(toon) == payload
        except Exception:  # pragma: no cover - defensive for exotic values
            roundtrip = False
        rows.append(("TOON", toon, roundtrip))
    rows.append(("dedicated text", text, None))
    return rows


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


# Deterministic but high-entropy identities: real UUID + SHA-256 hex values,
# so zlib compression reflects random hashes rather than repeated placeholders.
_PARENT_ID = str(
    uuid.uuid5(uuid.NAMESPACE_URL, "https://clouisle.example/benchmark/asset")
)
_REPRESENTATION_ID = hashlib.sha256(b"clouisle-benchmark-representation").hexdigest()
_REPRESENTATION_VERSION = hashlib.sha256(b"clouisle-benchmark-version").hexdigest()
_QUERY_HASH = hashlib.sha256("混合检索".encode("utf-8")).hexdigest()[:16]


def _current_cursor(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return _b64(raw.encode("utf-8"))


def _packed_cursor(
    *,
    kind: int,
    offset: int,
    line: int,
    context_lines: int = 0,
    limit: int = 0,
    query_hash: str = "",
) -> str:
    binding_source = "\0".join(
        (_PARENT_ID, _REPRESENTATION_ID, _REPRESENTATION_VERSION, query_hash)
    )
    binding = hashlib.sha256(binding_source.encode("utf-8")).digest()[:16]
    payload = struct.pack(">BBQI", 1, kind, offset, line)
    if kind == 2:
        payload += struct.pack(">BH", context_lines, limit)
        payload += bytes.fromhex(query_hash)
    return _b64(payload + binding)


def _zlib_cursor(payload: dict[str, Any]) -> str:
    # Same shape as asset_document._encode_cursor: sorted JSON, default zlib
    # level, urlsafe base64 without padding.
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _b64(zlib.compress(raw))


def _array_cursor(values: list[Any]) -> str:
    return _b64(json.dumps(values, separators=(",", ":")).encode("utf-8"))


def _text_rss_tight(payload: dict[str, Any]) -> str:
    articles = payload.get("articles") or []
    lines = [
        f"{payload.get('feed_title') or payload.get('url')} · {len(articles)} articles"
    ]
    if not articles:
        lines.append("No articles.")
        return "\n".join(lines)
    for index, article in enumerate(articles, 1):
        identity = " · ".join(
            _cell(article[field])
            for field in ("citation_id", "title", "author", "published")
            if article.get(field) is not None
        )
        lines.append(f"{index}. {identity}")
        if article.get("link"):
            lines.append(f"   {article['link']}")
        if article.get("summary"):
            lines.append(f"   {article['summary']}")
    return "\n".join(lines)


def collect_rss_layout(cases: list[Case]) -> list[dict[str, Any]]:
    case = next(case for case in cases if case.name == "rss_feed_zh")
    variants = {
        "current renderer": render_tool_output("rss_feed_reader", case.payload),
        "tight one-line layout": _text_rss_tight(case.payload),
    }
    return [
        {
            "layout": label,
            "chars": len(text),
            "tokens": {
                model: count_tokens(text, model_id=model) for model, _ in ENCODINGS
            },
        }
        for label, text in variants.items()
    ]


def _cursor_variants(cases: list[Case]) -> tuple[dict[str, str], dict[str, str]]:
    read_payload = {
        "v": 1,
        "k": "read",
        "r": _REPRESENTATION_ID,
        "p": _PARENT_ID,
        "rv": _REPRESENTATION_VERSION,
        "o": 1_234_567,
        "l": 50_000,
    }
    search_payload = {
        "v": 1,
        "k": "search",
        "r": _REPRESENTATION_ID,
        "p": _PARENT_ID,
        "rv": _REPRESENTATION_VERSION,
        "o": 2_345_678,
        "l": 60_000,
        "q": _QUERY_HASH,
        "c": 2,
        "n": 20,
    }
    read_binding = _packed_cursor(kind=1, offset=1_234_567, line=50_000)
    search_binding = _packed_cursor(
        kind=2,
        offset=2_345_678,
        line=60_000,
        context_lines=2,
        limit=20,
        query_hash=_QUERY_HASH,
    )
    read_variants = {
        "current JSON": _current_cursor(read_payload),
        "zlib(JSON)": _zlib_cursor(read_payload),
        "JSON array + hex binding": _array_cursor(
            [
                1,
                1,
                1_234_567,
                50_000,
                hashlib.sha256(
                    "\0".join(
                        (_PARENT_ID, _REPRESENTATION_ID, _REPRESENTATION_VERSION)
                    ).encode()
                ).hexdigest()[:32],
            ]
        ),
        "binary tuple + binding": read_binding,
    }
    search_variants = {
        "current JSON": _current_cursor(search_payload),
        "zlib(JSON)": _zlib_cursor(search_payload),
        "JSON array + hex binding": _array_cursor(
            [
                1,
                2,
                2_345_678,
                60_000,
                2,
                20,
                _QUERY_HASH,
                hashlib.sha256(
                    "\0".join(
                        (
                            _PARENT_ID,
                            _REPRESENTATION_ID,
                            _REPRESENTATION_VERSION,
                            _QUERY_HASH,
                        )
                    ).encode()
                ).hexdigest()[:32],
            ]
        ),
        "binary tuple + binding": search_binding,
    }

    return read_variants, search_variants


def collect_cursors(cases: list[Case]) -> dict[str, Any]:
    read_variants, search_variants = _cursor_variants(cases)
    cursors: list[dict[str, Any]] = []
    for kind, variants in (("read", read_variants), ("search", search_variants)):
        for label, cursor in variants.items():
            cursors.append(
                {
                    "kind": kind,
                    "variant": label,
                    "chars": len(cursor),
                    "tokens": {
                        model: count_tokens(cursor, model_id=model)
                        for model, _ in ENCODINGS
                    },
                }
            )

    payloads: list[dict[str, Any]] = []
    read_case = next(case for case in cases if case.name == "read_asset_code")
    search_case = next(case for case in cases if case.name == "search_asset_zh")
    for kind, case, variants in (
        ("read_asset", read_case, read_variants),
        ("search_asset", search_case, search_variants),
    ):
        for label, cursor in variants.items():
            payload = dict(case.payload)
            payload["next_cursor"] = cursor
            text = case.text(payload)
            payloads.append(
                {
                    "kind": kind,
                    "variant": label,
                    "tokens": {
                        model: count_tokens(text, model_id=model)
                        for model, _ in ENCODINGS
                    },
                }
            )
    return {"cursors": cursors, "payloads": payloads}


def _tokens(text: str) -> dict[str, int]:
    return {model: count_tokens(text, model_id=model) for model, _ in ENCODINGS}


def collect_case_metrics(cases: list[Case]) -> dict[str, Any]:
    totals: dict[str, dict[str, int]] = {}
    failures: list[str] = []
    measured: list[dict[str, Any]] = []

    for case in cases:
        rows = _rows(case)
        baseline = _tokens(rows[0][1])
        encodings: list[dict[str, Any]] = []
        for label, text, roundtrip in rows:
            counts = _tokens(text)
            for model, count in counts.items():
                totals.setdefault(label, {model: 0 for model, _ in ENCODINGS})[
                    model
                ] += count
            if label == "dedicated text":
                missing = [value for value in case.preserve if value not in text]
                if missing:
                    failures.append(f"{case.name}: missing {missing!r}")
            encodings.append(
                {
                    "encoding": label,
                    "chars": len(text),
                    "tokens": counts,
                    "roundtrip": (
                        "yes"
                        if roundtrip is True
                        else "no"
                        if roundtrip is False
                        else "lossy"
                    ),
                }
            )
        measured.append(
            {
                "case": case.name,
                "tool": case.tool,
                "baseline": baseline,
                "encodings": encodings,
            }
        )

    return {
        "encodings": [
            {"model": model, "tokenizer": encoding} for model, encoding in ENCODINGS
        ],
        "cases": measured,
        "totals": totals,
        "text_preservation": {"ok": not failures, "failures": failures},
    }


def _percent(count: int, base: int) -> str:
    return f"{count / base:.0%}" if base else "-"


def render_markdown(results: dict[str, Any]) -> None:
    models = [entry["model"] for entry in results["encodings"]]
    labels = [
        f"{entry['model']} ({entry['tokenizer']})" for entry in results["encodings"]
    ]
    print("| Case | Encoding | " + " | ".join(labels) + " | Exact round-trip |")
    print("|" + "---|" * (len(models) + 3))
    for case in results["cases"]:
        for encoding in case["encodings"]:
            counts = [encoding["tokens"][model] for model in models]
            ratio = [
                _percent(count, case["baseline"][model])
                for count, model in zip(counts, models, strict=True)
            ]
            print(
                f"| {case['case']} | {encoding['encoding']} | "
                + " | ".join(
                    f"{count} ({percent})"
                    for count, percent in zip(counts, ratio, strict=True)
                )
                + f" | {encoding['roundtrip']} |"
            )

    print()
    print("| Total | " + " | ".join(models) + " |")
    print("|" + "---|" * (len(models) + 1))
    for label, totals in results["totals"].items():
        counts = [totals[model] for model in models]
        ratio = [
            _percent(count, results["totals"]["current JSON"][model])
            for count, model in zip(counts, models, strict=True)
        ]
        print(
            f"| {label} | "
            + " | ".join(
                f"{count} ({percent})"
                for count, percent in zip(counts, ratio, strict=True)
            )
            + " |"
        )

    print()
    preservation = results["text_preservation"]
    if preservation["ok"]:
        print("Text preservation checks: all listed literals retained.")
    else:
        print("Text preservation failures:")
        for failure in preservation["failures"]:
            print(f"- {failure}")

    print()
    print("### RSS layout diagnostic")
    print()
    print("| RSS layout | " + " | ".join(models) + " |")
    print("|" + "---|" * (len(models) + 1))
    for row in results["rss_layout"]:
        print(
            f"| {row['layout']} | "
            + " | ".join(str(row["tokens"][model]) for model in models)
            + " |"
        )

    print()
    print("### Continuation cursor overhead")
    print()
    print("| Cursor | chars | " + " | ".join(models) + " |")
    print("|" + "---|" * (len(models) + 2))
    for row in results["cursors"]["cursors"]:
        print(
            f"| {row['kind']} {row['variant']} | {row['chars']} | "
            + " | ".join(str(row["tokens"][model]) for model in models)
            + " |"
        )

    print()
    print("| Result payload | " + " | ".join(models) + " |")
    print("|" + "---|" * (len(models) + 1))
    for row in results["cursors"]["payloads"]:
        print(
            f"| {row['kind']} {row['variant']} | "
            + " | ".join(str(row["tokens"][model]) for model in models)
            + " |"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable results instead of markdown",
    )
    args = parser.parse_args()

    cases = build_cases()
    results = collect_case_metrics(cases)
    results["rss_layout"] = collect_rss_layout(cases)
    results["cursors"] = collect_cursors(cases)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        render_markdown(results)


if __name__ == "__main__":
    main()
