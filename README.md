# Smash or Pass

A lightweight LAN/WAN party game built with Python + Tkinter where players vote **Smash** or **Pass** on shared images in real time.

## Features
- Host or join a room with a simple room key.
- Live vote syncing over UDP.
- Local image folder support (`.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, `.webp`).
- Auto-created config file with sensible defaults.
- Basic input/path validation for safer local file handling.

## Requirements
- Python 3.9+
- Tkinter (usually included with Python)
- Pillow

Install dependencies:

```bash
pip install -r requirements.txt
```

## Quick Start
1. Run the app:
   ```bash
   python main.py
   ```
2. Enter a username.
3. Click **Select Image Folder** and choose a folder containing images.
4. Choose one:
   - **Host Game** to create a room.
   - **Join Game** to connect to a host (IP + room key required).
5. Start voting with **SMASH** or **PASS**.

## Networking Notes
- Default UDP port is `55555` (editable in `config.json`).
- This app is easiest to use on the same local network.
- **WAN play only works if you set up port forwarding on the host router _or_ use a VPN (e.g., Tailscale/ZeroTier/Radmin VPN).**
- If joining over WAN fails, verify:
  - host public IP is correct,
  - UDP port is forwarded to the host machine,
  - local firewall allows inbound UDP on the configured port,
  - both players use the same room key.

## Configuration
On first run, `config.json` is created if missing:

```json
{
  "default_image_folder": "./images",
  "default_port": 55555,
  "default_username": "Player"
}
```

You can edit these values before launching the app.

## Project Files
- `main.py` – Tkinter UI + app flow.
- `network.py` – UDP networking, room, callbacks.
- `game_logic.py` – image loading, validation, scaling.
- `config.json` – user defaults.

## Troubleshooting
- **No images found:** confirm your selected folder contains supported image extensions.
- **Can't connect:** check IP/room key/port and firewall rules.
- **Blank or failed image load:** verify image file integrity and format.

## Disclaimer
This project is for casual/private use. Please use image content responsibly and with consent.
