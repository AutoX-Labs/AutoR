from __future__ import annotations

import json

import pytest

from src.jsonrpc import (
    ErrorCode,
    JsonRpcError,
    JsonRpcException,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    decode_message,
    encode_error_response,
    encode_notification,
    encode_request,
    encode_response,
)


class TestEncodeRequest:
    def test_request_with_params(self):
        msg = encode_request("acp.task.create", {"prompt": "hello"}, id=1)
        parsed = json.loads(msg)
        assert parsed == {
            "jsonrpc": "2.0",
            "method": "acp.task.create",
            "params": {"prompt": "hello"},
            "id": 1,
        }

    def test_request_without_params(self):
        msg = encode_request("acp.task.list", id=2)
        parsed = json.loads(msg)
        assert parsed["method"] == "acp.task.list"
        assert "params" not in parsed
        assert parsed["id"] == 2

    def test_request_with_string_id(self):
        msg = encode_request("test", id="abc-123")
        parsed = json.loads(msg)
        assert parsed["id"] == "abc-123"


class TestEncodeResponse:
    def test_success_response(self):
        msg = encode_response({"task_id": "t1", "status": "running"}, id=1)
        parsed = json.loads(msg)
        assert parsed == {
            "jsonrpc": "2.0",
            "result": {"task_id": "t1", "status": "running"},
            "id": 1,
        }

    def test_error_response(self):
        msg = encode_error_response(
            code=ErrorCode.INTERNAL_ERROR,
            message="something failed",
            data={"detail": "stack trace"},
            id=1,
        )
        parsed = json.loads(msg)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["error"]["code"] == -32603
        assert parsed["error"]["message"] == "something failed"
        assert parsed["error"]["data"] == {"detail": "stack trace"}
        assert parsed["id"] == 1

    def test_error_response_without_data(self):
        msg = encode_error_response(
            code=ErrorCode.PARSE_ERROR,
            message="bad input",
            id=5,
        )
        parsed = json.loads(msg)
        assert "data" not in parsed["error"]


class TestEncodeNotification:
    def test_notification_has_no_id(self):
        msg = encode_notification("acp.event.progress", {"tokens": 100})
        parsed = json.loads(msg)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["method"] == "acp.event.progress"
        assert parsed["params"] == {"tokens": 100}
        assert "id" not in parsed

    def test_notification_without_params(self):
        msg = encode_notification("acp.event.heartbeat")
        parsed = json.loads(msg)
        assert "params" not in parsed


class TestDecodeMessage:
    def test_decode_request(self):
        raw = '{"jsonrpc": "2.0", "method": "test", "params": {"x": 1}, "id": 5}'
        msg = decode_message(raw)
        assert isinstance(msg, JsonRpcRequest)
        assert msg.method == "test"
        assert msg.params == {"x": 1}
        assert msg.id == 5

    def test_decode_success_response(self):
        raw = '{"jsonrpc": "2.0", "result": {"ok": true}, "id": 5}'
        msg = decode_message(raw)
        assert isinstance(msg, JsonRpcResponse)
        assert msg.result == {"ok": True}
        assert msg.id == 5

    def test_decode_error_response(self):
        raw = '{"jsonrpc": "2.0", "error": {"code": -32600, "message": "bad"}, "id": 5}'
        msg = decode_message(raw)
        assert isinstance(msg, JsonRpcError)
        assert msg.code == -32600
        assert msg.message == "bad"
        assert msg.id == 5

    def test_decode_notification(self):
        raw = '{"jsonrpc": "2.0", "method": "event", "params": {"a": 1}}'
        msg = decode_message(raw)
        assert isinstance(msg, JsonRpcNotification)
        assert msg.method == "event"
        assert msg.params == {"a": 1}

    def test_decode_invalid_json(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            decode_message("not json")

    def test_decode_missing_jsonrpc_field(self):
        with pytest.raises(ValueError, match="jsonrpc"):
            decode_message('{"method": "test", "id": 1}')

    def test_decode_wrong_version(self):
        with pytest.raises(ValueError, match="2.0"):
            decode_message('{"jsonrpc": "1.0", "method": "test", "id": 1}')

    def test_decode_non_object(self):
        with pytest.raises(ValueError, match="object"):
            decode_message('"just a string"')

    def test_decode_request_without_params(self):
        raw = '{"jsonrpc": "2.0", "method": "ping", "id": 10}'
        msg = decode_message(raw)
        assert isinstance(msg, JsonRpcRequest)
        assert msg.params is None

    def test_roundtrip_request(self):
        encoded = encode_request("test.method", {"key": "value"}, id=42)
        decoded = decode_message(encoded)
        assert isinstance(decoded, JsonRpcRequest)
        assert decoded.method == "test.method"
        assert decoded.params == {"key": "value"}
        assert decoded.id == 42

    def test_roundtrip_notification(self):
        encoded = encode_notification("test.event", {"data": 123})
        decoded = decode_message(encoded)
        assert isinstance(decoded, JsonRpcNotification)
        assert decoded.method == "test.event"
        assert decoded.params == {"data": 123}


class TestErrorCode:
    def test_standard_codes(self):
        assert ErrorCode.PARSE_ERROR == -32700
        assert ErrorCode.INVALID_REQUEST == -32600
        assert ErrorCode.METHOD_NOT_FOUND == -32601
        assert ErrorCode.INVALID_PARAMS == -32602
        assert ErrorCode.INTERNAL_ERROR == -32603

    def test_custom_acp_codes(self):
        assert ErrorCode.SESSION_NOT_FOUND == -32000
        assert ErrorCode.TOKEN_LIMIT_EXCEEDED == -32001
        assert ErrorCode.TOOL_EXECUTION_FAILED == -32002
        assert ErrorCode.TASK_CANCELLED == -32003
        assert ErrorCode.TIMEOUT == -32004


class TestJsonRpcException:
    def test_exception_carries_code_and_message(self):
        exc = JsonRpcException(ErrorCode.METHOD_NOT_FOUND, "no such method")
        assert exc.code == -32601
        assert str(exc) == "no such method"
        assert exc.data is None

    def test_exception_carries_data(self):
        exc = JsonRpcException(ErrorCode.INTERNAL_ERROR, "boom", data={"detail": "stack"})
        assert exc.data == {"detail": "stack"}

    def test_exception_is_raisable(self):
        with pytest.raises(JsonRpcException) as exc_info:
            raise JsonRpcException(ErrorCode.TIMEOUT, "timed out")
        assert exc_info.value.code == ErrorCode.TIMEOUT

    def test_exception_is_exception_subclass(self):
        exc = JsonRpcException(ErrorCode.PARSE_ERROR, "bad json")
        assert isinstance(exc, Exception)
