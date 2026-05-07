import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from PIL import Image, ImageTk
import os
import json
import base64
import io

from game_logic import GameLogic
from network import Network


# UDP-safe image transfer settings
# Keep chunks small to avoid UDP fragmentation after JSON/protocol overhead.
MAX_IMAGE_BYTES = 0  # force chunked transfer for network images
MAX_IMAGE_B64_CHARS = 52000

CHUNK_B64_SIZE = 700
MAX_CHUNKS = 300
MAX_CHUNKED_IMAGE_BYTES = 180000
MAX_CHUNKED_IMAGE_B64_CHARS = MAX_CHUNKS * CHUNK_B64_SIZE
CHUNK_REDUNDANCY = 3
CHUNK_RECEIVE_TIMEOUT_MS = 8000
CHUNK_SEND_DELAY_MS = 2

VALID_VOTES = {"smash", "pass", "hellyeah"}
VOTE_WEIGHTS = {"smash": 1, "pass": 0, "hellyeah": 2}


def create_default_config():
    """Create default config.json if it doesn't exist."""
    config_path = "config.json"

    if not os.path.exists(config_path):
        default_config = {
            "default_image_folder": "./images",
            "default_port": 55555,
            "default_username": "Player",
        }

        try:
            with open(config_path, "w") as f:
                json.dump(default_config, f, indent=4)
            print(f"Created default {config_path}")
        except IOError as e:
            print(f"Error creating config file: {e}")


def get_default_config():
    """Return default configuration."""
    return {
        "default_image_folder": "./images",
        "default_port": 55555,
        "default_username": "Player",
    }


def load_config():
    """Load config from config.json with validation."""
    create_default_config()

    try:
        with open("config.json") as f:
            config = json.load(f)

        required_keys = ["default_image_folder", "default_port", "default_username"]

        for key in required_keys:
            if key not in config:
                print(f"Warning: Missing key '{key}' in config, using default")
                return get_default_config()

        if (
            not isinstance(config["default_port"], int)
            or config["default_port"] <= 0
            or config["default_port"] > 65535
        ):
            print("Warning: Invalid port in config, using default")
            return get_default_config()

        return config

    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading config: {e}, using defaults")
        return get_default_config()


class SmashOrPassApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Smash or Pass")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        config = load_config()
        self.image_folder = config["default_image_folder"]
        self.port = config["default_port"]
        self.username = (
            simpledialog.askstring(
                "Username",
                "Enter your username:",
                parent=self.root,
            )
            or config["default_username"]
        )

        self.game = GameLogic(self.image_folder)
        self.network = None

        self.votes = {}
        self.current_image_name = None
        self.has_voted_this_round = False

        self.resize_after_id = None
        self.next_round_after_id = None

        # transfer_id -> {
        #   filename: str,
        #   total: int,
        #   chunks: dict[int, str],
        #   started_ms: int
        # }
        self.pending_image_chunks = {}

        self.current_image = None
        self.current_image_path = None

        self.setup_ui()

    def setup_ui(self):
        self.main_frame = tk.Frame(self.root, padx=10, pady=10)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.toolbar = tk.Frame(self.main_frame, bd=1, relief=tk.RAISED, padx=5, pady=5)
        self.toolbar.pack(fill=tk.X, pady=(0, 10))

        tk.Button(
            self.toolbar,
            text="📁 Select Image Folder",
            command=self.select_folder,
            width=20,
            font=("Arial", 10),
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            self.toolbar,
            text="🏠 Host Game",
            command=self.host_game,
            width=15,
            font=("Arial", 10),
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            self.toolbar,
            text="🔗 Join Game",
            command=self.join_game,
            width=15,
            font=("Arial", 10),
        ).pack(side=tk.LEFT, padx=5)

        self.skip_btn = tk.Button(
            self.toolbar,
            text="⏭️ Skip Round",
            command=self.skip_round,
            state=tk.DISABLED,
            width=15,
            font=("Arial", 10),
        )
        self.skip_btn.pack(side=tk.LEFT, padx=5)

        self.image_frame = tk.Frame(self.main_frame, bd=2, relief=tk.SUNKEN, bg="black")
        self.image_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.image_label = tk.Label(
            self.image_frame,
            bg="black",
            text="No image loaded",
            fg="white",
        )
        self.image_label.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.image_label.bind("<Configure>", self._on_image_frame_resize)

        self.vote_frame = tk.Frame(self.main_frame)
        self.vote_frame.pack(fill=tk.X, pady=10)

        self.smash_btn = tk.Button(
            self.vote_frame,
            text="✅ SMASH",
            command=self.vote_smash,
            state=tk.DISABLED,
            width=12,
            height=2,
            bg="#4CAF50",
            fg="white",
            font=("Arial", 12, "bold"),
        )
        self.smash_btn.pack(side=tk.LEFT, padx=20)

        self.hellyeah_btn = tk.Button(
            self.vote_frame,
            text="🔥 HELLYEAH x2",
            command=self.vote_hellyeah,
            state=tk.DISABLED,
            width=14,
            height=2,
            bg="#FF9800",
            fg="white",
            font=("Arial", 12, "bold"),
        )
        self.hellyeah_btn.pack(side=tk.LEFT, padx=20)

        self.pass_btn = tk.Button(
            self.vote_frame,
            text="❌ PASS",
            command=self.vote_pass,
            state=tk.DISABLED,
            width=12,
            height=2,
            bg="#F44336",
            fg="white",
            font=("Arial", 12, "bold"),
        )
        self.pass_btn.pack(side=tk.LEFT, padx=20)

        self.results_frame = tk.LabelFrame(
            self.main_frame,
            text="📊 Live Votes",
            bd=1,
            relief=tk.GROOVE,
            padx=5,
            pady=5,
        )
        self.results_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.results_text = tk.Text(
            self.results_frame,
            height=6,
            width=60,
            state=tk.DISABLED,
            font=("Arial", 10),
            wrap=tk.WORD,
            padx=5,
            pady=5,
        )
        self.results_text.pack(fill=tk.BOTH, expand=True)

        self.status_label = tk.Label(
            self.main_frame,
            text=f"Welcome, {self.username}! Select an image folder and host/join a game.",
            bd=1,
            relief=tk.SUNKEN,
            anchor=tk.W,
            font=("Arial", 10),
            padx=5,
        )
        self.status_label.pack(fill=tk.X, pady=(10, 0))

    # ------------------------------------------------------------------
    # UI image handling
    # ------------------------------------------------------------------

    def _on_image_frame_resize(self, _event=None):
        if self.resize_after_id:
            self.root.after_cancel(self.resize_after_id)

        self.resize_after_id = self.root.after(100, self._refresh_current_image)

    def _refresh_current_image(self):
        if not self.current_image_path or not os.path.isfile(self.current_image_path):
            return

        try:
            with Image.open(self.current_image_path) as img:
                scaled = self._scale_for_ui(img)

            if scaled is None:
                return

            img_tk = ImageTk.PhotoImage(scaled)
            self.current_image = img_tk
            self.image_label.config(image=img_tk, text="")
            self.image_label.image = img_tk

        except Exception as e:
            print(f"Error refreshing image: {e}")

    def _scale_for_ui(self, img):
        frame_w = self.image_frame.winfo_width()
        frame_h = self.image_frame.winfo_height()
        root_h = self.root.winfo_height()

        w = max(300, frame_w - 20)
        h = max(250, frame_h - 20)

        max_ui_height = int(root_h * 0.52)
        h = min(h, max_ui_height)

        return self.game._scale_image(img, max_size=(w, h))

    # ------------------------------------------------------------------
    # Setup / hosting / joining
    # ------------------------------------------------------------------

    def select_folder(self):
        folder = filedialog.askdirectory()

        if folder:
            self.image_folder = folder
            self.game = GameLogic(folder)
            self.status_label.config(text=f"Image folder: {folder}")

    def host_game(self):
        if not self.game.images:
            messagebox.showerror("Error", "No images in folder!")
            return

        self.network = Network(port=self.port, username=self.username)

        self.network.on("vote", self.receive_vote)
        self.network.on("next_image", self.receive_next_image)
        self.network.on("vote_results", self.receive_vote_results)
        self.network.on("user_joined", self.user_joined)
        self.network.on("next_image_chunk", self.receive_next_image_chunk)

        self.status_label.config(text=f"Hosting game. Room key: {self.network.room_key}")
        self.skip_btn.config(state=tk.NORMAL)

        self.start_game()

    def join_game(self):
        host_ip = simpledialog.askstring("Join Game", "Enter host IP:")
        room_key = simpledialog.askstring("Join Game", "Enter room key:")

        if host_ip and room_key:
            self.network = Network(
                host_ip=host_ip,
                port=self.port,
                room_key=room_key,
                username=self.username,
            )

            self.network.on("next_image", self.receive_next_image)
            self.network.on("vote", self.receive_vote)
            self.network.on("vote_results", self.receive_vote_results)
            self.network.on("user_joined", self.user_joined)
            self.network.on("next_image_chunk", self.receive_next_image_chunk)

            self.status_label.config(text=f"Joined game at {host_ip}")
            self.skip_btn.config(state=tk.DISABLED)

    def start_game(self):
        self.next_image()
        self._set_vote_buttons_enabled(True)

    def skip_round(self):
        if not self.network or not self.network.is_host:
            return

        if self.next_round_after_id:
            self.root.after_cancel(self.next_round_after_id)
            self.next_round_after_id = None

        self.pending_image_chunks = {}
        self.next_image()

    # ------------------------------------------------------------------
    # Image sending
    # ------------------------------------------------------------------

    def next_image(self):
        img, path = self.game.get_random_image()

        if img:
            self.current_image = img
            self.current_image_path = path
            self.current_image_name = os.path.basename(path)
            self.has_voted_this_round = False

            self._set_vote_buttons_enabled(True)
            self.image_label.config(image=img, text="")
            self.image_label.image = img

            self.votes = {}
            self.update_results()

            if self.network and self.network.is_host:
                encoded, best_data = self._encode_image_for_network(path)

                if encoded:
                    self.network.send(
                        "next_image",
                        {
                            "filename": self.current_image_name,
                            "image_b64": encoded,
                        },
                    )
                elif best_data:
                    self._send_chunked_image(self.current_image_name, best_data)
                else:
                    self.network.send(
                        "next_image",
                        {
                            "filename": self.current_image_name,
                        },
                    )

            return

        self.current_image = None
        self.current_image_path = None
        self.current_image_name = None
        self.image_label.config(image="", text="No loadable images found")
        self.image_label.image = None
        self.status_label.config(
            text="No image could be loaded. Check image files and format support."
        )
        self._set_vote_buttons_enabled(False)

    def _encode_image_for_network(self, path):
        try:
            with Image.open(path) as opened:
                img = self.game._scale_image(opened)

            if img is None:
                return None, None

            best_data = None

            # Try progressively smaller JPEGs.
            for quality in (70, 55, 40, 30, 20, 12):
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=quality, optimize=True)
                data = buffer.getvalue()

                if MAX_IMAGE_BYTES and len(data) <= MAX_IMAGE_BYTES:
                    return base64.b64encode(data).decode("ascii"), data

                if best_data is None or len(data) < len(best_data):
                    best_data = data

            if best_data and len(best_data) <= MAX_CHUNKED_IMAGE_BYTES:
                return None, best_data

            print(
                f"Encoded image too large even after compression: "
                f"{len(best_data) if best_data else 0} bytes"
            )
            return None, None

        except Exception as e:
            print(f"Error encoding image for network: {e}")
            return None, None

    def _send_chunked_image(self, filename, image_data):
        if not self.network or not self.network.is_host or not image_data:
            return

        image_b64 = base64.b64encode(image_data).decode("ascii")

        if len(image_b64) > MAX_CHUNKED_IMAGE_B64_CHARS:
            print("Image too large for chunked transfer")
            return

        chunks = [
            image_b64[i : i + CHUNK_B64_SIZE]
            for i in range(0, len(image_b64), CHUNK_B64_SIZE)
        ]

        if not chunks or len(chunks) > MAX_CHUNKS:
            print(f"Too many chunks: {len(chunks)}")
            return

        transfer_id = f"{filename}:{len(image_data)}:{len(chunks)}"

        print(
            f"Sending chunked image: {filename}, "
            f"bytes={len(image_data)}, b64={len(image_b64)}, chunks={len(chunks)}"
        )

        header_payload = {
            "filename": filename,
            "transfer_id": transfer_id,
            "chunked": True,
            "total_chunks": len(chunks),
        }

        # Send header more than once because UDP can drop it.
        for _ in range(CHUNK_REDUNDANCY):
            self.network.send("next_image", header_payload)

        delay = 0

        for index, chunk in enumerate(chunks):
            payload = {
                "filename": filename,
                "transfer_id": transfer_id,
                "index": index,
                "total_chunks": len(chunks),
                "chunk": chunk,
            }

            for _ in range(CHUNK_REDUNDANCY):
                self.root.after(
                    delay,
                    lambda p=payload: self.network.send("next_image_chunk", p),
                )
                delay += CHUNK_SEND_DELAY_MS

    # ------------------------------------------------------------------
    # Image receiving
    # ------------------------------------------------------------------

    def receive_next_image(self, data, addr=None):
        self.root.after(0, lambda: self._receive_next_image(data))

    def _receive_next_image(self, data):
        filename = data.get("filename")

        if not filename:
            print("Error: No filename provided in next_image")
            return

        filename = os.path.basename(filename)

        if not filename:
            print("Error: Invalid filename provided in next_image")
            return

        image_b64 = data.get("image_b64")

        if data.get("chunked"):
            self._prune_stale_chunk_transfers()

            transfer_id = data.get("transfer_id")

            try:
                total_chunks = int(data.get("total_chunks", 0))
            except (TypeError, ValueError):
                return

            if not transfer_id or total_chunks <= 0 or total_chunks > MAX_CHUNKS:
                return

            now_ms = self._now_ms()

            existing = self.pending_image_chunks.get(transfer_id)

            if existing:
                existing["filename"] = filename
                existing["total"] = total_chunks
                existing.setdefault("chunks", {})
                existing.setdefault("started_ms", now_ms)
            else:
                self.pending_image_chunks[transfer_id] = {
                    "filename": filename,
                    "total": total_chunks,
                    "chunks": {},
                    "started_ms": now_ms,
                }

            self.status_label.config(
                text=f"Receiving image chunks: {filename} ({total_chunks} chunks)"
            )
            return

        is_chunked_transfer = bool(data.get("chunked_transfer"))
        max_b64_chars = (
            MAX_CHUNKED_IMAGE_B64_CHARS if is_chunked_transfer else MAX_IMAGE_B64_CHARS
        )

        if image_b64 and len(image_b64) > max_b64_chars:
            print("Security warning: oversized image payload blocked")
            return

        try:
            if image_b64:
                decoded = base64.b64decode(image_b64, validate=True)

                decoded_limit = (
                    MAX_CHUNKED_IMAGE_BYTES if is_chunked_transfer else MAX_IMAGE_BYTES
                )

                if decoded_limit and len(decoded) > decoded_limit:
                    print("Security warning: oversized decoded image blocked")
                    return

                with Image.open(io.BytesIO(decoded)) as opened:
                    img = self.game._scale_image(opened)

                # Save received image into memory-only path marker.
                # Do not rely on this path for refresh unless file exists.
                folder = os.path.abspath(self.game.image_folder)
                path = os.path.abspath(os.path.join(folder, filename))

            else:
                folder = os.path.abspath(self.game.image_folder)
                path = os.path.abspath(os.path.join(folder, filename))

                if os.path.commonpath([folder, path]) != folder:
                    print("Security warning: blocked invalid image path")
                    return

                if not os.path.isfile(path):
                    self.status_label.config(
                        text="Image not received: host image was not embedded or chunked."
                    )
                    return

                with Image.open(path) as opened:
                    img = self.game._scale_image(opened)

            if img is None:
                self.status_label.config(text="Failed to scale received image.")
                return

            img_tk = ImageTk.PhotoImage(img)
            self.current_image = img_tk
            self.current_image_path = path
            self.current_image_name = filename
            self.has_voted_this_round = False

            self._set_vote_buttons_enabled(True)
            self.image_label.config(image=img_tk, text="")
            self.image_label.image = img_tk

            self.votes = {}
            self.update_results()

            self.status_label.config(text=f"Image loaded: {filename}")

        except Exception as e:
            self.status_label.config(text="Failed to decode received image.")
            print(f"Error loading image from network: {e}")

    def receive_next_image_chunk(self, data, addr=None):
        self.root.after(0, lambda: self._receive_next_image_chunk(data))

    def _receive_next_image_chunk(self, data):
        self._prune_stale_chunk_transfers()

        transfer_id = data.get("transfer_id")
        chunk = data.get("chunk")
        index = data.get("index")

        try:
            index = int(index)
            total_chunks = int(data.get("total_chunks", 0))
        except (TypeError, ValueError):
            return

        if not transfer_id or not isinstance(chunk, str):
            return

        if total_chunks <= 0 or total_chunks > MAX_CHUNKS:
            return

        if index < 0 or index >= total_chunks:
            return

        if len(chunk) > CHUNK_B64_SIZE + 100:
            print("Security warning: oversized chunk blocked")
            return

        pending = self.pending_image_chunks.get(transfer_id)

        # Important fix:
        # UDP chunks may arrive before the metadata/header packet.
        # Create the transfer from the chunk if needed.
        if not pending:
            filename = os.path.basename(data.get("filename", "received.jpg"))
            now_ms = self._now_ms()

            pending = {
                "filename": filename,
                "total": total_chunks,
                "chunks": {},
                "started_ms": now_ms,
            }

            self.pending_image_chunks[transfer_id] = pending

        if pending.get("total") != total_chunks:
            return

        pending["chunks"][index] = chunk

        received = len(pending["chunks"])
        self.status_label.config(
            text=f"Receiving image chunks: {received}/{total_chunks}"
        )

        print(f"Received chunk {index + 1}/{total_chunks} for {transfer_id}")

        if received < total_chunks:
            return

        assembled = "".join(pending["chunks"].get(i, "") for i in range(total_chunks))

        del self.pending_image_chunks[transfer_id]

        if len(assembled) > MAX_CHUNKED_IMAGE_B64_CHARS:
            print("Security warning: assembled image too large")
            return

        self._receive_next_image(
            {
                "filename": pending["filename"],
                "image_b64": assembled,
                "chunked_transfer": True,
            }
        )

    def _prune_stale_chunk_transfers(self):
        now_ms = self._now_ms()

        stale_ids = [
            tid
            for tid, payload in self.pending_image_chunks.items()
            if now_ms - payload.get("started_ms", now_ms) > CHUNK_RECEIVE_TIMEOUT_MS
        ]

        for tid in stale_ids:
            print(f"Pruning stale image transfer: {tid}")
            del self.pending_image_chunks[tid]

    def _now_ms(self):
        return int(self.root.winfo_toplevel().tk.call("clock", "milliseconds"))

    # ------------------------------------------------------------------
    # Voting
    # ------------------------------------------------------------------

    def _set_vote_buttons_enabled(self, enabled):
        state = tk.NORMAL if enabled else tk.DISABLED
        self.smash_btn.config(state=state)
        self.hellyeah_btn.config(state=state)
        self.pass_btn.config(state=state)

    def vote_smash(self):
        self.send_vote("smash")

    def vote_hellyeah(self):
        self.send_vote("hellyeah")

    def vote_pass(self):
        self.send_vote("pass")

    def send_vote(self, vote):
        if vote not in VALID_VOTES or not self.network or not self.current_image_name:
            return

        if self.has_voted_this_round:
            return

        self.has_voted_this_round = True
        self._set_vote_buttons_enabled(False)

        self.votes[self.username] = vote
        self.update_results()

        image_name = self.current_image_name

        self.network.send(
            "vote",
            {
                "vote": vote,
                "image": image_name,
            },
        )

        if self.network.is_host:
            self._try_finalize_round()

    def receive_vote(self, data, addr=None):
        if not self.network or not addr:
            return

        vote = data.get("vote", "unknown")

        if vote not in VALID_VOTES:
            return

        image_name = data.get("image")

        if self.current_image_name and image_name and image_name != self.current_image_name:
            return

        if self.network.is_host:
            username = self.network.clients.get(addr, data.get("_username", "Unknown"))

            self.votes[username] = vote
            self.update_results()

            self.network.send(
                "vote",
                {
                    "vote": vote,
                    "_username": username,
                    "image": image_name,
                },
            )

            self._try_finalize_round()

        else:
            username = data.get("_username", data.get("username", "Unknown"))
            self.votes[username] = vote
            self.update_results()

    def _try_finalize_round(self):
        if not self.network or not self.network.is_host:
            return

        expected_votes = len(self.network.clients) + 1

        if expected_votes > 0 and len(self.votes) >= expected_votes:
            smash_count = sum(1 for v in self.votes.values() if v == "smash")
            hellyeah_count = sum(1 for v in self.votes.values() if v == "hellyeah")
            pass_count = sum(1 for v in self.votes.values() if v == "pass")
            weighted_smash = sum(VOTE_WEIGHTS.get(v, 0) for v in self.votes.values())

            results_payload = {
                "image": self.current_image_name,
                "total": len(self.votes),
                "smash": smash_count,
                "hellyeah": hellyeah_count,
                "pass": pass_count,
                "weighted_smash": weighted_smash,
            }

            self.network.send("vote_results", results_payload)
            self._receive_vote_results(results_payload)

            if self.next_round_after_id:
                self.root.after_cancel(self.next_round_after_id)

            self.next_round_after_id = self.root.after(3500, self.next_image)

    def receive_vote_results(self, data, addr=None):
        self.root.after(0, lambda: self._receive_vote_results(data))

    def _receive_vote_results(self, data):
        if self.current_image_name and data.get("image") and data.get("image") != self.current_image_name:
            return

        smash_count = int(data.get("smash", 0))
        hellyeah_count = int(data.get("hellyeah", 0))
        pass_count = int(data.get("pass", 0))
        weighted_smash = int(
            data.get("weighted_smash", smash_count + (2 * hellyeah_count))
        )
        total = int(data.get("total", smash_count + pass_count + hellyeah_count))

        self.results_text.config(state=tk.NORMAL)
        self.results_text.insert(tk.END, "\n--- Round Result ---\n")
        self.results_text.insert(tk.END, f"Total votes: {total}\n")
        self.results_text.insert(tk.END, f"✅ SMASH: {smash_count}\n")
        self.results_text.insert(tk.END, f"🔥 HELLYEAH (x2): {hellyeah_count}\n")
        self.results_text.insert(tk.END, f"❌ PASS: {pass_count}\n")
        self.results_text.insert(tk.END, f"💥 Weighted Smash Score: {weighted_smash}\n")
        self.results_text.config(state=tk.DISABLED)

    def user_joined(self, data, addr=None):
        username = data.get("username", "Unknown")

        self.results_text.config(state=tk.NORMAL)
        self.results_text.insert(tk.END, f"👤 {username} joined the game.\n")
        self.results_text.config(state=tk.DISABLED)

        if (
            self.network
            and self.network.is_host
            and addr
            and self.current_image_path
            and self.current_image_name
        ):
            encoded, best_data = self._encode_image_for_network(self.current_image_path)

            if encoded:
                self.network.send_to(
                    addr,
                    "next_image",
                    {
                        "filename": self.current_image_name,
                        "image_b64": encoded,
                    },
                )

            elif best_data:
                self._send_chunked_image_to(addr, self.current_image_name, best_data)

            else:
                self.network.send_to(
                    addr,
                    "next_image",
                    {
                        "filename": self.current_image_name,
                    },
                )

    def _send_chunked_image_to(self, addr, filename, image_data):
        if not self.network or not self.network.is_host or not image_data:
            return

        image_b64 = base64.b64encode(image_data).decode("ascii")

        if len(image_b64) > MAX_CHUNKED_IMAGE_B64_CHARS:
            print("Image too large for chunked transfer")
            return

        chunks = [
            image_b64[i : i + CHUNK_B64_SIZE]
            for i in range(0, len(image_b64), CHUNK_B64_SIZE)
        ]

        if not chunks or len(chunks) > MAX_CHUNKS:
            print(f"Too many chunks: {len(chunks)}")
            return

        transfer_id = f"{filename}:{len(image_data)}:{len(chunks)}"

        header_payload = {
            "filename": filename,
            "transfer_id": transfer_id,
            "chunked": True,
            "total_chunks": len(chunks),
        }

        for _ in range(CHUNK_REDUNDANCY):
            self.network.send_to(addr, "next_image", header_payload)

        delay = 0

        for index, chunk in enumerate(chunks):
            payload = {
                "filename": filename,
                "transfer_id": transfer_id,
                "index": index,
                "total_chunks": len(chunks),
                "chunk": chunk,
            }

            for _ in range(CHUNK_REDUNDANCY):
                self.root.after(
                    delay,
                    lambda p=payload: self.network.send_to(
                        addr,
                        "next_image_chunk",
                        p,
                    ),
                )
                delay += CHUNK_SEND_DELAY_MS

    def update_results(self):
        self.results_text.config(state=tk.NORMAL)
        self.results_text.delete(1.0, tk.END)

        if not self.votes:
            self.results_text.insert(tk.END, "No votes yet.\n")
        else:
            for user in sorted(self.votes):
                vote = self.votes[user]
                emoji = "✅" if vote == "smash" else "🔥" if vote == "hellyeah" else "❌"
                label = "HELLYEAH x2" if vote == "hellyeah" else vote.upper()
                self.results_text.insert(tk.END, f"{emoji} {user}: {label}\n")

        self.results_text.config(state=tk.DISABLED)

    def on_close(self):
        if self.next_round_after_id:
            self.root.after_cancel(self.next_round_after_id)

        if self.resize_after_id:
            self.root.after_cancel(self.resize_after_id)

        if self.network:
            self.network.close()

        self.game.close()
        self.root.quit()


if __name__ == "__main__":
    root = tk.Tk()
    app = SmashOrPassApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
