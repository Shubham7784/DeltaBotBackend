import asyncio
import json
import logging
import sys
from datetime import datetime
from typing import Any
from fastapi import WebSocket, WebSocketDisconnect


class ConnectionManager:
    def __init__(self, history_size: int = 500):
        self.active_connections: list[WebSocket] = []
        self.history: list[dict[str, Any]] = []
        self.history_size = history_size

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any] | str):
        payload = self._normalize_message(message)
        self._add_history(payload)
        text = json.dumps(payload)

        for connection in list(self.active_connections):
            try:
                await connection.send_text(text)
            except Exception:
                self.disconnect(connection)

    def _add_history(self, payload: dict[str, Any]):
        self.history.append(payload)
        if len(self.history) > self.history_size:
            self.history.pop(0)

    def get_recent_messages(self, message_type: str | None = None) -> list[dict[str, Any]]:
        if message_type is None:
            return list(self.history)
        return [message for message in self.history if message.get("type") == message_type]

    def _normalize_message(self, message: dict[str, Any] | str) -> dict[str, Any]:
        if isinstance(message, str):
            return {"type": "TEXT", "timestamp": datetime.utcnow().isoformat() + "Z", "message": message}
        return message


class WebSocketLogHandler(logging.Handler):
    def __init__(self, manager: ConnectionManager, level: int = logging.NOTSET):
        super().__init__(level)
        self.manager = manager
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            payload = {
                "type": "LOG",
                "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
                "level": record.levelname,
                "logger": record.name,
                "message": message,
            }
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                loop.create_task(self.manager.broadcast(payload))
        except Exception:
            pass


class StreamToLogger:
    def __init__(self, logger: logging.Logger, level: int, original_stream=None):
        self.logger = logger
        self.level = level
        self.original_stream = original_stream or sys.__stdout__
        self._buffer = ""

    def write(self, message: str) -> None:
        message = message.rstrip("\n")
        if not message:
            return

        for line in message.splitlines():
            self.logger.log(self.level, line)

    def flush(self) -> None:
        if hasattr(self.original_stream, "flush"):
            self.original_stream.flush()

    def isatty(self) -> bool:
        return getattr(self.original_stream, "isatty", lambda: False)()

    def fileno(self) -> int:
        return getattr(self.original_stream, "fileno", lambda: 1)()

    def writable(self) -> bool:
        return True

    @property
    def encoding(self) -> str:
        return getattr(self.original_stream, "encoding", "utf-8")

    @property
    def errors(self) -> str:
        return getattr(self.original_stream, "errors", "strict")


log_manager = ConnectionManager()


def configure_logging(level: int = logging.INFO) -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    stream_handler = logging.StreamHandler(sys.__stdout__)
    stream_handler.setFormatter(formatter)
    if not any(isinstance(handler, logging.StreamHandler) for handler in root_logger.handlers):
        root_logger.addHandler(stream_handler)

    websocket_handler = WebSocketLogHandler(log_manager)
    if not any(isinstance(handler, WebSocketLogHandler) for handler in root_logger.handlers):
        root_logger.addHandler(websocket_handler)

    sys.stdout = StreamToLogger(root_logger, logging.INFO, sys.__stdout__)
    sys.stderr = StreamToLogger(root_logger, logging.ERROR, sys.__stderr__)
