import inspect
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from gis_agent.core.model import ModelError, ModelReply, TokenCounter
from gis_agent.persistence.json import json_text
from gis_agent.prompts import render_prompt


logger = logging.getLogger(__name__)


class AuxiliaryError(ValueError):
    pass


@dataclass
class AuxiliaryCalls:
    chat: Callable[..., ModelReply]
    record: Callable[[dict[str, Any]], None]
    count_tokens: TokenCounter
    token_limit: int = 900_000
    used: int = 0

    def reset(self) -> None:
        self.used = 0

    def ask(self, purpose: str, instructions: str, data: Any) -> Any:
        messages = [
            {"role": "system", "content": instructions + "\n" + render_prompt("json_output.txt")},
            {"role": "user", "content": json_text(data)},
        ]
        if self.count_tokens(messages, []) > self.token_limit:
            raise AuxiliaryError(f"{purpose} 输入超过 token 预算。")
        self.used += 1
        try:
            reply = self.chat(messages, [])
        except ModelError as error:
            self.record({'purpose': purpose, 'attempt': self.used, 'error': str(error), 'usage': None})
            raise AuxiliaryError(f'{purpose}: {error}') from error
        self.record({"purpose": purpose, "attempt": self.used, **reply.metadata(), "message": reply.message})
        logger.info("Auxiliary: %s %s %s", purpose, self.used, reply.metadata())
        if reply.finish_reason != "stop" or reply.message.get("tool_calls"):
            raise AuxiliaryError(f"{purpose} 没有返回完整的普通响应。")
        try:
            return json.loads(reply.message.get("content") or "")
        except json.JSONDecodeError as error:
            raise AuxiliaryError(f"{purpose} 返回的 JSON 无效：{error}") from error

    def ask_text(
        self, purpose: str, instructions: str, data: Any, *, max_tokens: int | None = None,
    ) -> str:
        messages = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": data if isinstance(data, str) else json_text(data)},
        ]
        if self.count_tokens(messages, []) > self.token_limit:
            raise AuxiliaryError(f"{purpose} 输入超过 token 预算。")
        self.used += 1
        kwargs: dict[str, Any] = {}
        if max_tokens is not None:
            params = inspect.signature(self.chat).parameters
            if "max_tokens" in params or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
                kwargs["max_tokens"] = max_tokens
        try:
            reply = self.chat(messages, [], **kwargs)
        except ModelError as error:
            self.record({"purpose": purpose, "attempt": self.used, "error": str(error), "usage": None})
            raise AuxiliaryError(f"{purpose}: {error}") from error
        self.record({"purpose": purpose, "attempt": self.used, **reply.metadata(), "message": reply.message})
        logger.info("Auxiliary: %s %s %s", purpose, self.used, reply.metadata())
        if reply.finish_reason not in {"stop", "length"} or reply.message.get("tool_calls"):
            raise AuxiliaryError(f"{purpose} 没有返回完整的普通响应。")
        text = (reply.message.get("content") or "").strip()
        if not text:
            raise AuxiliaryError(f"{purpose} 返回正文为空。")
        return text
