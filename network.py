import json
import secrets
import socket
import threading
import hashlib

SOCKET_TIMEOUT = 0.5
PORT_RANGE = (1, 65535)
USERNAME_LIMIT = 50
BUFFER_SIZE = 65535
ROOM_KEY_LIMIT = 32


def _validate_port(port: int) -> int:
    if not isinstance(port, int) or not (PORT_RANGE[0] <= port <= PORT_RANGE[1]):
        raise ValueError(f"Port must be between {PORT_RANGE[0]} and {PORT_RANGE[1]}")
    return port


def _validate_username(username: str) -> str:
    username = (username or "Player").strip()
    if not username:
        username = "Player"
    if len(username) > USERNAME_LIMIT:
        username = username[:USERNAME_LIMIT]
    return username



def _validate_room_key(room_key: str) -> str:
    room_key = (room_key or "").strip()
    if not room_key:
        return secrets.token_hex(4)
    if len(room_key) > ROOM_KEY_LIMIT or not room_key.isalnum():
        raise ValueError("Invalid room key")
    return room_key


def _hash_room_key(room_key: str) -> str:
    return hashlib.sha256(room_key.encode("utf-8")).hexdigest()


class Network:
    def __init__(self, host_ip="", port=55555, room_key=None, username="Player"):
        self.host_ip = host_ip
        self.port = _validate_port(port)
        self.username = _validate_username(username)
        self.room_key = _validate_room_key(room_key)
        self.room_key_hash = _hash_room_key(self.room_key)
        self.is_host = not bool(host_ip)

        self.callbacks = {}
        self.clients = {}
        self.running = True

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(SOCKET_TIMEOUT)

        if self.is_host:
            self.sock.bind(("", self.port))
            self.server_addr = None
        else:
            self.server_addr = (self.host_ip, self.port)
            self._send_raw(
                self.server_addr,
                {"type": "join", "data": {"username": self.username, "room_key_hash": self.room_key_hash}},
            )

        self.listener = threading.Thread(target=self._listen, daemon=True)
        self.listener.start()

    def on(self, event, callback):
        self.callbacks[event] = callback

    def send(self, event, data):
        payload = {"type": event, "data": data, "room_key_hash": self.room_key_hash, "username": self.username}
        if self.is_host:
            for addr in list(self.clients.keys()):
                self._send_raw(addr, payload)
        else:
            if self.server_addr:
                self._send_raw(self.server_addr, payload)

    def close(self):
        self.running = False
        try:
            self.sock.close()
        except OSError:
            pass

    def _send_raw(self, addr, payload):
        try:
            self.sock.sendto(json.dumps(payload).encode("utf-8"), addr)
        except OSError:
            pass

    def _listen(self):
        while self.running:
            try:
                raw, addr = self.sock.recvfrom(BUFFER_SIZE)
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                message = json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

            msg_type = message.get("type")
            data = message.get("data", {})
            if not isinstance(data, dict):
                continue
            if isinstance(data, dict) and message.get("username"):
                data.setdefault("_username", message.get("username"))

            if self.is_host:
                if msg_type == "join":
                    join_key_hash = data.get("room_key_hash")
                    if join_key_hash != self.room_key_hash:
                        continue
                    username = _validate_username(data.get("username", "Player"))
                    self.clients[addr] = username
                    callback = self.callbacks.get("user_joined")
                    if callback:
                        callback({"username": username}, addr)
                    continue

                if message.get("room_key_hash") != self.room_key_hash:
                    continue

            callback = self.callbacks.get(msg_type)
            if callback:
                callback(data, addr)
