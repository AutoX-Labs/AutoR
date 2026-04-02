"""Minimal JSON-RPC 2.0 codec. No I/O -- pure encode/decode."""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import IntEnum
from typing import Any


JSONRPC_VERSION = "2.0"


class ErrorCode(IntEnum):
    """JSON-RPC 2.0 standard error codes + ACP extensions."""

    # Standard JSON-RPC 2.0 error codes
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # ACP-specific error codes (server error range: -32000 to -32099)
    SESSION_NOT_FOUND = -32000
    TOKEN_LIMIT_EXCEEDED = -32001
    TOOL_EXECUTION_FAILED = -32002
    TASK_CANCELLED = -32003
    TIMEOUT = -32004


@dataclass(frozen=True)
class JsonRpcRequest:
    method: str
    id: int | str
    params: dict[str, Any] | None = None


@dataclass(frozen=True)
class JsonRpcResponse:
    result: Any
    id: int | str


@dataclass(frozen=True)
class JsonRpcError:
    """JSON-RPC 2.0 error response message (wire format)."""
    code: int
    message: str
    id: int | str | None
    data: Any = None


class JsonRpcException(Exception):
    """Raisable exception carrying a structured JSON-RPC error code.

    Server methods raise this to signal typed errors.  The caller
    (ACPOperator) can inspect ``code`` to decide recovery strategy
    instead of string-matching on the message.
    """

    def __init__(self, code: int | ErrorCode, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = int(code)
        self.data = data


@dataclass(frozen=True)
class JsonRpcNotification:
    method: str
    params: dict[str, Any] | None = None


Message = JsonRpcRequest | JsonRpcResponse | JsonRpcError | JsonRpcNotification


def encode_request(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    id: int | str,
) -> str:
    msg: dict[str, Any] = {"jsonrpc": JSONRPC_VERSION, "method": method, "id": id}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg, ensure_ascii=True)


def encode_response(result: Any, *, id: int | str) -> str:
    return json.dumps(
        {"jsonrpc": JSONRPC_VERSION, "result": result, "id": id},
        ensure_ascii=True,
    )


def encode_error_response(
    code: int,
    message: str,
    data: Any = None,
    *,
    id: int | str | None,
) -> str:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return json.dumps(
        {"jsonrpc": JSONRPC_VERSION, "error": error, "id": id},
        ensure_ascii=True,
    )


def encode_notification(method: str, params: dict[str, Any] | None = None) -> str:
    msg: dict[str, Any] = {"jsonrpc": JSONRPC_VERSION, "method": method}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg, ensure_ascii=True)


def decode_message(raw: str) -> Message:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("JSON-RPC message must be an object")

    if data.get("jsonrpc") != JSONRPC_VERSION:
        raise ValueError(f"Expected jsonrpc version 2.0, got: {data.get('jsonrpc')!r}")

    # Error response
    if "error" in data:
        err = data["error"]
        return JsonRpcError(
            code=int(err.get("code", ErrorCode.INTERNAL_ERROR)),
            message=str(err.get("message", "")),
            id=data.get("id"),
            data=err.get("data"),
        )

    # Success response
    if "result" in data:
        return JsonRpcResponse(result=data["result"], id=data["id"])

    # Request or notification
    method = data.get("method")
    if not isinstance(method, str):
        raise ValueError("JSON-RPC request/notification must have a string 'method'")

    if "id" in data:
        return JsonRpcRequest(method=method, id=data["id"], params=data.get("params"))

    return JsonRpcNotification(method=method, params=data.get("params"))
