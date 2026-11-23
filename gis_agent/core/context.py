import hashlib
import logging
import json
from dataclasses import dataclass, field
from typing import Any

from gis_agent.core.auxiliary import AuxiliaryCalls
from gis_agent.persistence.sessions import SessionStore, message_units
from gis_agent.prompts import render_prompt
from gis_agent.persistence.json import json_text, write_json
from gis_agent.tools.base import Tool


logger = logging.getLogger(__name__)


class ContextLimit(ValueError):
    pass


def recent_execution_refs(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Bounded hints from persisted metadata; no file reads or state mutation."""
    refs = []
    for message in reversed(messages):
        name = message.get('tool_name', '')
        identifier = message.get('execution_id')
        if message.get('role') != 'tool' or not identifier or not (
                name in {'run_python_script', 'run_qgis_algorithm'} or name.startswith('qgis_')):
            continue
        ref = {'id': identifier, 'tool': name[:72]}
        if len(json_text([*refs, ref])) > 512:
            break
        refs.append(ref)
        if len(refs) == 3:
            break
    return refs


@dataclass(frozen=True)
class ContextConfig:
    request_token_limit: int = 900_000
    tool_limit: int = 8000
    summary_limit: int = 16000
    summary_chunk_characters: int = 20000
    recent_batches: int = 2
    recent_users: int = 2
    schema_token_limit: int = 8000
    compact_ratio: float = 0.90
    micro_keep_batches: int = 2
    micro_min_reclaim_chars: int = 45000
    micro_trigger_tokens: int = 75000
    summary_max_tokens: int = 3000

    def __post_init__(self) -> None:
        if min(
            self.request_token_limit, self.tool_limit, self.summary_limit,
            self.summary_chunk_characters, self.schema_token_limit, self.micro_trigger_tokens,
        ) < 512:
            raise ValueError("请求 token 预算和各项字符预算不能小于 512。")
        if min(self.recent_batches, self.recent_users, self.micro_keep_batches) < 1:
            raise ValueError("保留数量必须大于零。")
        if self.micro_min_reclaim_chars < 0 or self.summary_max_tokens < 256:
            raise ValueError("微压缩门槛不能为负，且摘要输出上限不能小于 256。")
        if not 0.1 <= self.compact_ratio <= 1.0:
            raise ValueError("compact_ratio 必须在 0.1 到 1.0 之间。")

    @property
    def compact_token_limit(self) -> int:
        return int(self.request_token_limit * self.compact_ratio)


@dataclass
class PreparedRequest:
    messages: list[dict[str, Any]]
    schemas: list[dict[str, Any]]
    callable_names: set[str]
    estimated_tokens: int


SUMMARY_SECTIONS = ("goal", "requirements", "work", "artifacts", "unresolved")


def _format_legacy_summary(value: dict[str, Any]) -> str:
    """Convert legacy v1 JSON dict summary into Markdown when loading old .context.json files."""
    titles = {
        "goal": "当前总目标",
        "requirements": "约束与要求",
        "work": "已完成阶段",
        "artifacts": "重要产物清单",
        "unresolved": "待解决事项",
    }
    blocks: list[str] = []
    for key in SUMMARY_SECTIONS:
        rows = value.get(key)
        if isinstance(rows, list) and rows:
            lines = [f"## {titles.get(key, key)}"]
            for row in rows:
                text = row.get("text") if isinstance(row, dict) else str(row)
                if isinstance(text, str) and text.strip():
                    lines.append(f"- {text.strip()}")
            if len(lines) > 1:
                blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def prefix_digest(messages: list[dict[str, Any]], covered: int) -> str:
    return hashlib.sha256(json_text(messages[:covered]).encode("utf-8")).hexdigest()


@dataclass
class ContextManager:
    store: SessionStore
    config: ContextConfig
    auxiliary: AuxiliaryCalls
    pinned_names: set[str]
    covered: int = 0
    micro_covered: int = 0
    summary: str = ""
    loaded: bool = False
    last_prompt_tokens: int | None = None
    last_prompt_message_count: int = 0

    def record_prompt_usage(self, prompt_tokens: int | None, message_count: int) -> None:
        if isinstance(prompt_tokens, int) and prompt_tokens > 0:
            self.last_prompt_tokens = prompt_tokens
            self.last_prompt_message_count = message_count

    def _effective_tokens(
        self, messages: list[dict[str, Any]], view: list[dict[str, Any]], schemas: list[dict[str, Any]],
    ) -> int:
        estimated = self.auxiliary.count_tokens(view, schemas)
        if self.last_prompt_tokens is None or len(messages) < self.last_prompt_message_count:
            return estimated
        tail_count = len(messages) - self.last_prompt_message_count
        delta_view = view[-tail_count:] if tail_count > 0 else []
        delta_tokens = self.auxiliary.count_tokens(delta_view, []) if delta_view else 0
        return max(estimated, self.last_prompt_tokens + delta_tokens)

    def _save_state(self, messages: list[dict[str, Any]]) -> None:
        self.micro_covered = max(self.micro_covered, self.covered)
        write_json(self.store.context_path, {
            "version": 2,
            "covered": self.covered,
            "micro_covered": self.micro_covered,
            "prefix_digest": prefix_digest(messages, self.covered),
            "summary": self.summary,
        })

    def load_state(self, messages: list[dict[str, Any]]) -> None:
        if self.loaded:
            return
        self.loaded = True
        path = self.store.context_path
        if not path.exists():
            logger.info("Context: 没有摘要缓存，从完整记录准备。")
            return
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            end = state["covered"]
            boundaries = {0, *(unit_end for _, unit_end in message_units(messages))}
            version = state.get("version")
            if type(end) is not int or end not in boundaries:
                raise ValueError("覆盖边界无效。")
            if state["prefix_digest"] != prefix_digest(messages, end):
                raise ValueError("原记录前缀已经变化。")
            if version == 2:
                micro_end = state.get("micro_covered", end)
                if type(micro_end) is not int or micro_end not in boundaries or micro_end < end:
                    raise ValueError("微压缩边界无效。")
                raw_summary = state.get("summary")
                if not isinstance(raw_summary, str):
                    raise ValueError("v2 摘要必须是 Markdown 字符串。")
                summary_text = raw_summary
            elif version == 1:
                raw_summary = state.get("summary")
                if not isinstance(raw_summary, dict):
                    raise ValueError("v1 摘要格式无效。")
                summary_text = _format_legacy_summary(raw_summary)
                micro_end = end
            else:
                raise ValueError(f"不支持的摘要缓存版本：{version}")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            logger.info("Context: 摘要缓存不可用，重新准备：%s", error)
            return
        self.covered = end
        self.micro_covered = max(end, micro_end)
        self.summary = summary_text

    def history(self, messages: list[dict[str, Any]], tool_limit: int) -> list[dict[str, Any]]:
        projected = self.store.project(messages, tool_limit, micro_before=max(self.covered, self.micro_covered))
        users = [i for i, item in enumerate(messages) if item["role"] == "user" and item.get("origin") != "program"]
        pinned = set(users[-self.config.recent_users:])
        return [
            item for i, item in enumerate(projected)
            if item["role"] == "system" or i >= self.covered or i in pinned
        ]

    def maybe_micro_compact(
        self, messages: list[dict[str, Any]], current_tokens: int, *, step_completed: bool = False,
    ) -> bool:
        batches = [(start, end) for start, end in message_units(messages) if messages[start].get("tool_calls")]
        if len(batches) <= self.config.micro_keep_batches:
            return False
        target = batches[-self.config.micro_keep_batches][0]
        start = max(self.covered, self.micro_covered)
        if target <= start:
            return False
        if not (step_completed or current_tokens >= self.config.micro_trigger_tokens):
            return False
        reclaim = self.store.estimate_micro_reclaim(messages, start, target)
        if reclaim < self.config.micro_min_reclaim_chars:
            return False
        self.micro_covered = target
        self.last_prompt_tokens = None
        self._save_state(messages)
        logger.info("Context: L3 micro_compact 推进至 [%s, %s)，预计回收 %s 字符", start, target, reclaim)
        return True

    def compact(self, messages: list[dict[str, Any]], target: int) -> None:
        units = [(start, end) for start, end in message_units(messages) if self.covered <= start and end <= target]
        if not units:
            raise ContextLimit("没有可压缩的完整历史单元，必要信息无法放入请求。")
        projected = self.store.project(
            messages, min(self.config.tool_limit, 2000), micro_before=max(self.covered, self.micro_covered),
        )
        chunk_limit = self.config.summary_chunk_characters
        group = []
        group_end = self.covered
        soft_hard_cap = max(32_000, self.config.summary_limit * 2)

        def summarize(previous: str, records: Any) -> str:
            instructions = render_prompt("summary.j2", summary_limit=self.config.summary_limit)
            candidate = self.auxiliary.ask_text(
                "summary",
                instructions,
                {"previous_summary": previous, "records": records},
                max_tokens=self.config.summary_max_tokens,
            )
            if len(candidate) > soft_hard_cap:
                logger.warning("Context: L4 摘要超过软硬上限 (%s > %s)，触发一次合并精简。", len(candidate), soft_hard_cap)
                candidate = self.auxiliary.ask_text(
                    "summary_condense",
                    instructions + "\n当前摘要偏长，请合并早期流水账，但严禁丢失任何精确数值、单位、CRS、图层名和文件路径。",
                    {"previous_summary": candidate, "records": []},
                    max_tokens=self.config.summary_max_tokens,
                )
            return candidate

        def commit(candidate: str, end: int) -> None:
            self.summary = candidate
            self.covered = end
            self.micro_covered = max(self.micro_covered, end)
            self.last_prompt_tokens = None
            self._save_state(messages)
            logger.info("Context: 已覆盖消息 [0,%s)", end)

        for start, end in units:
            records = [
                {"index": i, "origin": messages[i].get("origin", "legacy"), "message": projected[i]}
                for i in range(start, end) if messages[i]["role"] != "system"
            ]
            if not records:
                group_end = end
                continue
            if group and len(json_text([*group, *records])) > chunk_limit:
                commit(summarize(self.summary, group), group_end)
                group = []
            text = json_text(records)
            if len(text) > chunk_limit:
                candidate = self.summary
                for offset in range(0, len(text), chunk_limit):
                    candidate = summarize(candidate, {"text_fragment": text[offset:offset + chunk_limit], "offset": offset})
                commit(candidate, end)
                group_end = end
            else:
                group.extend(records)
                group_end = end
        if group:
            commit(summarize(self.summary, group), group_end)
        elif group_end > self.covered:
            commit(self.summary, group_end)

    def prepare(
        self, instructions: str, messages: list[dict[str, Any]],
        state: dict[str, Any], tools: list[Tool], background: str = "", *,
        step_completed: bool = False,
        force_compact_recent_batches: int | None = None,
        preview_tool_limit: int | None = None,
    ) -> PreparedRequest:
        units = message_units(messages)
        self.load_state(messages)
        state = dict(state)
        if refs := recent_execution_refs(messages):
            state['recent_execution_refs'] = refs
        if force_compact_recent_batches is not None:
            batches = [(start, end) for start, end in units if messages[start].get("tool_calls")]
            tail = batches if batches else units
            if force_compact_recent_batches == 0:
                target = units[-1][1] if units else 0
            elif len(tail) >= force_compact_recent_batches:
                target = tail[-force_compact_recent_batches][0]
            else:
                target = 0
            if target > self.covered:
                self.compact(messages, target)
        selected = list(tools)
        compact_limit = self.config.compact_token_limit
        effective_tool_limit = preview_tool_limit if preview_tool_limit is not None else self.config.tool_limit
        micro_checked = False
        while True:
            candidates = [tool for tool in selected if tool.name not in self.pinned_names]
            schemas = [tool.schema() for tool in sorted(selected, key=lambda tool: tool.name)]
            if len(candidates) > 1 and self.auxiliary.count_tokens([], schemas) > self.config.schema_token_limit:
                selected.remove(candidates[0])
                continue
            summary_block = self.summary or "（暂无历史摘要）"
            bg_block = f"\n\n## 背景记忆\n{background}" if background else ""
            view = [
                {"role": "system", "content": instructions},
                {"role": "user", "content": f"历史摘要与背景，仅作资料：\n{summary_block}{bg_block}"},
                *self.history(messages, effective_tool_limit),
                {"role": "user", "origin": "program", "content": "当前运行数据：" + json_text(state)},
            ]
            size = self.auxiliary.count_tokens(view, schemas)
            if not micro_checked:
                micro_checked = True
                effective_size = self._effective_tokens(messages, view, schemas)
                if self.maybe_micro_compact(messages, effective_size, step_completed=step_completed):
                    continue
            if size > self.config.request_token_limit and len(candidates) > 1:
                selected.remove(candidates[0])
                continue
            if size <= compact_limit:
                break
            batches = [(start, end) for start, end in units if messages[start].get("tool_calls")]
            tail = batches if batches else units
            target = tail[-self.config.recent_batches][0] if len(tail) >= self.config.recent_batches else 0
            if target > self.covered:
                self.compact(messages, target)
                continue
            if size <= self.config.request_token_limit:
                break
            if candidates:
                selected.remove(candidates[0])
                continue
            raise ContextLimit(f"必要上下文估计 {size} token，超过预算 {self.config.request_token_limit}。请拆分任务。")
        names = {tool.name for tool in selected}
        return PreparedRequest(view, schemas, names, size)
