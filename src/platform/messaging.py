from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OutboundMessage:
    channel: str
    text: str


class FileMessageChannel:
    def __init__(self, outbox_path: Path) -> None:
        self.outbox_path = outbox_path

    def send(self, message: OutboundMessage) -> None:
        self.outbox_path.parent.mkdir(parents=True, exist_ok=True)
        with self.outbox_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"channel": message.channel, "text": message.text}, ensure_ascii=True) + "\n")


class MessagingHub:
    def __init__(self, channels: list[FileMessageChannel] | None = None) -> None:
        self.channels = channels or []

    def broadcast(self, text: str) -> None:
        for channel in self.channels:
            channel.send(OutboundMessage(channel="file", text=text))

