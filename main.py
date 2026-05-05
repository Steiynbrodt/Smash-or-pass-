import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from PIL import Image, ImageTk
import os
import json
import base64
import io

MAX_IMAGE_BYTES = 45000
MAX_IMAGE_B64_CHARS = 70000
VALID_VOTES = {"smash", "pass", "hellyeah"}
VOTE_WEIGHTS = {"smash": 1, "pass": 0, "hellyeah": 2}
from game_logic import GameLogic
from network import Network

def create_default_config():
    """Create default config.json if it doesn't exist"""
    config_path = 'config.json'
    if not os.path.exists(config_path):
        default_config = {
            "default_image_folder": "./images",
            "default_port": 55555,
            "default_username": "Player"
        }
        try:
            with open(config_path, 'w') as f:
                json.dump(default_config, f, indent=4)
            print(f"Created default {config_path}")
        except IOError as e:
            print(f"Error creating config file: {e}")

def load_config():
    """Load config from config.json with validation"""
    create_default_config()
    try:
        with open('config.json') as f:
            config = json.load(f)
        
        # Validate required keys
        required_keys = ['default_image_folder', 'default_port', 'default_username']
        for key in required_keys:
            if key not in config:
                print(f"Warning: Missing key '{key}' in config, using default")
                return get_default_config()
        
        # Validate port is an integer
        if not isinstance(config['default_port'], int) or config['default_port'] <= 0 or config['default_port'] > 65535:
            print("Warning: Invalid port in config, using default")
            return get_default_config()
        
        return config
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading config: {e}, using defaults")
        return get_default_config()

def get_default_config():
    """Return default configuration"""
    return {
        "default_image_folder": "./images",
        "default_port": 55555,
        "default_username": "Player"
    }

class SmashOrPassApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Smash or Pass")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        # Load config
        config = load_config()
        self.image_folder = config['default_image_folder']
        self.port = config['default_port']
        self.username = simpledialog.askstring("Username", "Enter your username:", parent=self.root) or config['default_username']

        # Game logic
        self.game = GameLogic(self.image_folder)
        self.network = None
        self.votes = {}  # {username: vote}
        self.current_image_name = None
        self.has_voted_this_round = False
        self.next_round_after_id = None
        self.resize_after_id = None

        # UI
        self.setup_ui()

    def setup_ui(self):
        # Main container
        self.main_frame = tk.Frame(self.root, padx=10, pady=10)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # --- TOOLBAR (Top) ---
        self.toolbar = tk.Frame(self.main_frame, bd=1, relief=tk.RAISED, padx=5, pady=5)
        self.toolbar.pack(fill=tk.X, pady=(0, 10))

        # Toolbar buttons
        tk.Button(
            self.toolbar,
            text="📁 Select Image Folder",
            command=self.select_folder,
            width=20,
            font=("Arial", 10)
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            self.toolbar,
            text="🏠 Host Game",
            command=self.host_game,
            width=15,
            font=("Arial", 10)
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            self.toolbar,
            text="🔗 Join Game",
            command=self.join_game,
            width=15,
            font=("Arial", 10)
        ).pack(side=tk.LEFT, padx=5)

        # --- IMAGE DISPLAY (Center) ---
        self.image_frame = tk.Frame(self.main_frame, bd=2, relief=tk.SUNKEN, bg="black")
        self.image_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.image_label = tk.Label(self.image_frame, bg="black", text="No image loaded", fg="white")
        self.image_label.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.image_label.bind("<Configure>", self._on_image_frame_resize)

        # --- VOTING BUTTONS (Below Image) ---
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
            font=("Arial", 12, "bold")
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
            font=("Arial", 12, "bold")
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
            font=("Arial", 12, "bold")
        )
        self.pass_btn.pack(side=tk.LEFT, padx=20)

        # --- RESULTS PANEL (Bottom) ---
        self.results_frame = tk.LabelFrame(
            self.main_frame,
            text="📊 Live Votes",
            bd=1,
            relief=tk.GROOVE,
            padx=5,
            pady=5
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
            pady=5
        )
        self.results_text.pack(fill=tk.BOTH, expand=True)

        # --- STATUS BAR (Very Bottom) ---
        self.status_label = tk.Label(
            self.main_frame,
            text=f"Welcome, {self.username}! Select an image folder and host/join a game.",
            bd=1,
            relief=tk.SUNKEN,
            anchor=tk.W,
            font=("Arial", 10),
            padx=5
        )
        self.status_label.pack(fill=tk.X, pady=(10, 0))

        # Initial state
        self.current_image = None
        self.current_image_path = None

    def _on_image_frame_resize(self, _event=None):
        # Keep image sizing responsive, but debounce rapid resize events.
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
        w = max(300, self.image_frame.winfo_width() - 20)
        h = max(250, self.image_frame.winfo_height() - 20)
        return self.game._scale_image(img, max_size=(w, h))

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
        self.network.on('vote', self.receive_vote)
        self.network.on('next_image', self.receive_next_image)
        self.network.on('vote_results', self.receive_vote_results)
        self.network.on('user_joined', self.user_joined)
        self.status_label.config(text=f"Hosting game. Room key: {self.network.room_key}")
        self.start_game()

    def join_game(self):
        host_ip = simpledialog.askstring("Join Game", "Enter host IP:")
        room_key = simpledialog.askstring("Join Game", "Enter room key:")
        if host_ip and room_key:
            self.network = Network(host_ip=host_ip, port=self.port, room_key=room_key, username=self.username)
            self.network.on('next_image', self.receive_next_image)
            self.network.on('vote', self.receive_vote)
            self.network.on('vote_results', self.receive_vote_results)
            self.network.on('user_joined', self.user_joined)
            self.status_label.config(text=f"Joined game at {host_ip}")
            self._set_vote_buttons_enabled(False)

    def start_game(self):
        self.next_image()

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
                payload = {'filename': self.current_image_name}
                encoded = self._encode_image_for_network(path)
                if encoded:
                    payload['image_b64'] = encoded
                self.network.send('next_image', payload)

    def _set_vote_buttons_enabled(self, enabled):
        state = tk.NORMAL if enabled else tk.DISABLED
        self.smash_btn.config(state=state)
        self.hellyeah_btn.config(state=state)
        self.pass_btn.config(state=state)


    def _encode_image_for_network(self, path):
        try:
            with Image.open(path) as opened:
                img = self.game._scale_image(opened)
            if img is None:
                return None
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=70, optimize=True)
            data = buffer.getvalue()
            if len(data) > MAX_IMAGE_BYTES:
                return None
            return base64.b64encode(data).decode("ascii")
        except Exception as e:
            print(f"Error encoding image for network: {e}")
            return None

    def receive_next_image(self, data, addr=None):
        self.root.after(0, lambda: self._receive_next_image(data))

    def _receive_next_image(self, data):
        filename = data.get('filename')
        if not filename:
            print("Error: No filename provided in next_image")
            return
        filename = os.path.basename(filename)
        if not filename:
            print("Error: Invalid filename provided in next_image")
            return
        image_b64 = data.get('image_b64')
        if image_b64 and len(image_b64) > MAX_IMAGE_B64_CHARS:
            print("Security warning: oversized image payload blocked")
            return
        try:
            if image_b64:
                decoded = base64.b64decode(image_b64, validate=True)
                if len(decoded) > MAX_IMAGE_BYTES:
                    print("Security warning: oversized decoded image blocked")
                    return
                with Image.open(io.BytesIO(decoded)) as opened:
                    img = self.game._scale_image(opened)
                path = os.path.abspath(os.path.join(self.game.image_folder, filename))
            else:
                path = os.path.abspath(os.path.join(self.game.image_folder, filename))
                if os.path.commonpath([self.game.image_folder, path]) != self.game.image_folder:
                    print("Security warning: blocked invalid image path")
                    return
                with Image.open(path) as opened:
                    img = self.game._scale_image(opened)

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
        except Exception as e:
            print(f"Error loading image from network: {e}")

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
        self.network.send('vote', {'vote': vote, 'image': image_name})
        if self.network.is_host:
            self._try_finalize_round()

    def receive_vote(self, data, addr=None):
        if not self.network or not addr:
            return

        vote = data.get('vote', 'unknown')
        if vote not in VALID_VOTES:
            return
        image_name = data.get('image')
        if self.current_image_name and image_name and image_name != self.current_image_name:
            return

        if self.network.is_host:
            username = self.network.clients.get(addr, data.get('_username', 'Unknown'))
            self.votes[username] = vote
            self.update_results()
            self.network.send('vote', {'vote': vote, '_username': username, 'image': image_name})
            self._try_finalize_round()
        else:
            username = data.get('_username', data.get('username', 'Unknown'))
            self.votes[username] = vote
            self.update_results()

    def _try_finalize_round(self):
        if not self.network or not self.network.is_host:
            return
        expected_votes = len(self.network.clients) + 1  # all connected clients + host
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
            self.network.send('vote_results', results_payload)
            self._receive_vote_results(results_payload)
            if self.next_round_after_id:
                self.root.after_cancel(self.next_round_after_id)
            self.next_round_after_id = self.root.after(1500, self.next_image)

    def receive_vote_results(self, data, addr=None):
        self.root.after(0, lambda: self._receive_vote_results(data))

    def _receive_vote_results(self, data):
        if self.current_image_name and data.get("image") and data.get("image") != self.current_image_name:
            return
        smash_count = int(data.get("smash", 0))
        hellyeah_count = int(data.get("hellyeah", 0))
        pass_count = int(data.get("pass", 0))
        weighted_smash = int(data.get("weighted_smash", smash_count + (2 * hellyeah_count)))
        total = int(data.get("total", smash_count + pass_count))
        if "total" not in data:
            total = smash_count + hellyeah_count + pass_count
        self.results_text.config(state=tk.NORMAL)
        self.results_text.insert(tk.END, "\n--- Round Result ---\n")
        self.results_text.insert(tk.END, f"Total votes: {total}\n")
        self.results_text.insert(tk.END, f"✅ SMASH: {smash_count}\n")
        self.results_text.insert(tk.END, f"🔥 HELLYEAH (x2): {hellyeah_count}\n")
        self.results_text.insert(tk.END, f"❌ PASS: {pass_count}\n")
        self.results_text.insert(tk.END, f"💥 Weighted Smash Score: {weighted_smash}\n")
        self.results_text.config(state=tk.DISABLED)

    def user_joined(self, data, addr=None):
        username = data.get('username', 'Unknown')
        self.results_text.config(state=tk.NORMAL)
        self.results_text.insert(tk.END, f"👤 {username} joined the game.\n")
        self.results_text.config(state=tk.DISABLED)

    def update_results(self):
        self.results_text.config(state=tk.NORMAL)
        self.results_text.delete(1.0, tk.END)
        if not self.votes:
            self.results_text.insert(tk.END, "No votes yet.\n")
        else:
            for user, vote in sorted(self.votes.items(), key=lambda item: item[0].lower()):
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
        self.root.quit()

if __name__ == '__main__':
    root = tk.Tk()
    app = SmashOrPassApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
