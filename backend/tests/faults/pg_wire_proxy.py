import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(frozen=True)
class ProxyMode:
    name: str


DROP_COMMIT = ProxyMode("drop_commit")
FORWARD_COMMIT_DROP_RESPONSE = ProxyMode("forward_commit_drop_response")
DROP_BEFORE_TASK_INSERT = ProxyMode("drop_before_task_insert")


class PostgreSQLWireProxy:
    """测试专用 PG 线协议代理；生产代码没有对应配置或分支。"""

    def __init__(self, upstream_host: str, upstream_port: int, *, mode: ProxyMode) -> None:
        self._upstream_host = upstream_host
        self._upstream_port = upstream_port
        self._mode = mode
        self._armed = threading.Event()
        self._stopped = threading.Event()
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._connections: set[tuple[socket.socket, socket.socket]] = set()
        self._lock = threading.Lock()
        self._triggered = threading.Event()
        self._drop_response_armed = threading.Event()
        self._target_commit: int | None = None
        self.commit_commands = 0

    @property
    def port(self) -> int:
        if self._listener is None:
            raise RuntimeError("proxy 未启动")
        return int(self._listener.getsockname()[1])

    @property
    def triggered(self) -> bool:
        return self._triggered.is_set()

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("proxy 不能重复启动")
        self._listener = socket.create_server(("127.0.0.1", 0), backlog=20)
        self._listener.settimeout(0.2)
        self._thread = threading.Thread(target=self._serve, name="frameread-pg-wire-proxy", daemon=True)
        self._thread.start()

    def arm(self) -> None:
        # TestClient 的目标请求先经过 require_admin；该依赖本身会提交一次
        # 只读校验事务。故障必须落在随后真正的受理 COMMIT 上。
        self._target_commit = (
            self.commit_commands + 2 if self._mode in (DROP_COMMIT, FORWARD_COMMIT_DROP_RESPONSE) else None
        )
        self._armed.set()

    def close(self) -> None:
        self._stopped.set()
        listener = self._listener
        if listener is not None:
            listener.close()
        with self._lock:
            pairs = list(self._connections)
        for client, upstream in pairs:
            self._close_pair(client, upstream)
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._thread = None

    def _serve(self) -> None:
        listener = self._listener
        if listener is None:
            return
        while not self._stopped.is_set():
            try:
                client, _ = listener.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            try:
                upstream = socket.create_connection((self._upstream_host, self._upstream_port), timeout=5)
                client.settimeout(5)
                upstream.settimeout(5)
            except OSError:
                client.close()
                continue
            with self._lock:
                self._connections.add((client, upstream))
            threading.Thread(
                target=self._proxy_connection,
                args=(client, upstream),
                name="frameread-pg-wire-connection",
                daemon=True,
            ).start()

    def _proxy_connection(self, client: socket.socket, upstream: socket.socket) -> None:
        client_to_server = threading.Thread(
            target=self._forward_client_to_server,
            args=(client, upstream),
            daemon=True,
        )
        server_to_client = threading.Thread(
            target=self._forward_server_to_client,
            args=(upstream, client),
            daemon=True,
        )
        client_to_server.start()
        server_to_client.start()
        client_to_server.join()
        server_to_client.join()
        self._close_pair(client, upstream)

    def _forward_client_to_server(self, client: socket.socket, upstream: socket.socket) -> None:
        buffer = b""
        startup = True
        try:
            while not self._stopped.is_set():
                chunk = client.recv(65536)
                if not chunk:
                    return
                buffer += chunk
                while True:
                    frame, buffer, is_startup = _take_frame(buffer, startup=startup)
                    if frame is None:
                        break
                    startup = is_startup
                    if startup:
                        upstream.sendall(frame)
                        continue
                    if self._should_drop_before_task_insert(frame):
                        self._triggered.set()
                        self._close_pair(client, upstream)
                        return
                    if _is_commit(frame):
                        self.commit_commands += 1
                        is_target = self._armed.is_set() and self.commit_commands == self._target_commit
                        if self._mode is DROP_COMMIT and is_target and not self._triggered.is_set():
                            self._triggered.set()
                            self._close_pair(client, upstream)
                            return
                        if self._mode is FORWARD_COMMIT_DROP_RESPONSE and is_target and not self._triggered.is_set():
                            # 先设置触发位，避免快速回包越过故障注入窗口。
                            self._drop_response_armed.set()
                        upstream.sendall(frame)
                        continue
                    upstream.sendall(frame)
        except OSError:
            self._close_pair(client, upstream)

    def _forward_server_to_client(self, upstream: socket.socket, client: socket.socket) -> None:
        try:
            while not self._stopped.is_set():
                chunk = upstream.recv(65536)
                if not chunk:
                    return
                if (
                    self._mode is FORWARD_COMMIT_DROP_RESPONSE
                    and self._drop_response_armed.is_set()
                    and not self._triggered.is_set()
                ):
                    # COMMIT 发出前已设触发位；此处丢弃对应回包并断开。
                    self._triggered.set()
                    self._close_pair(client, upstream)
                    return
                client.sendall(chunk)
        except OSError:
            self._close_pair(client, upstream)

    def _should_drop_before_task_insert(self, frame: bytes) -> bool:
        if self._mode is not DROP_BEFORE_TASK_INSERT or not self._armed.is_set() or self._triggered.is_set():
            return False
        query = _query_text(frame)
        if query is None:
            return False
        return "insert into tasks" in query.lower()

    @staticmethod
    def _close_pair(client: socket.socket, upstream: socket.socket) -> None:
        for connection in (client, upstream):
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                connection.close()
            except OSError:
                pass


def _take_frame(buffer: bytes, *, startup: bool) -> tuple[bytes | None, bytes, bool]:
    if startup:
        if len(buffer) < 4:
            return None, buffer, startup
        length = int.from_bytes(buffer[:4], "big")
        if length < 8 or len(buffer) < length:
            return None, buffer, startup
        return buffer[:length], buffer[length:], False
    if len(buffer) < 5:
        return None, buffer, startup
    length = int.from_bytes(buffer[1:5], "big")
    total = length + 1
    if length < 4 or len(buffer) < total:
        return None, buffer, startup
    return buffer[:total], buffer[total:], startup


def _query_text(frame: bytes) -> str | None:
    if not frame:
        return None
    tag = frame[:1]
    payload = frame[5:]
    if tag == b"Q":
        return payload.rstrip(b"\x00").decode("utf-8", errors="ignore").strip()
    if tag == b"P":
        fields = payload.split(b"\x00", 2)
        if len(fields) >= 2:
            return fields[1].decode("utf-8", errors="ignore").strip()
    return None


def _is_commit(frame: bytes) -> bool:
    query = _query_text(frame)
    return query is not None and query.rstrip(";").strip().upper() == "COMMIT"


@contextmanager
def running_pg_wire_proxy(host: str, port: int, *, mode: ProxyMode) -> Iterator[PostgreSQLWireProxy]:
    proxy = PostgreSQLWireProxy(host, port, mode=mode)
    proxy.start()
    try:
        yield proxy
    finally:
        proxy.close()
