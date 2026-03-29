from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class AgentMessage:
    sender: str
    recipient: str
    message_type: str
    payload: dict[str, object]


@dataclass(frozen=True)
class ToolInvocation:
    tool_name: str
    arguments: dict[str, object]


class AgentMessageBus:
    def __init__(self) -> None:
        self._queues: dict[str, deque[AgentMessage]] = defaultdict(deque)

    def send(self, message: AgentMessage) -> None:
        self._queues[message.recipient].append(message)

    def drain(self, recipient: str) -> list[AgentMessage]:
        queue = self._queues[recipient]
        messages = list(queue)
        queue.clear()
        return messages


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., object]] = {}

    def register(self, name: str, fn: Callable[..., object]) -> None:
        self._tools[name] = fn

    def invoke(self, invocation: ToolInvocation) -> object:
        if invocation.tool_name not in self._tools:
            raise KeyError(f"Unknown tool: {invocation.tool_name}")
        return self._tools[invocation.tool_name](**invocation.arguments)


@dataclass(frozen=True)
class ProtocolBridge:
    a2a: AgentMessageBus
    mcp: ToolRegistry

