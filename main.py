# Fixed constants for UDP transmission

MAX_IMAGE_BYTES = 0  # force chunking
MAX_IMAGE_B64_CHARS = 52000
CHUNK_B64_SIZE = 900
MAX_CHUNKS = 300
MAX_CHUNKED_IMAGE_BYTES = 180000
MAX_CHUNKED_IMAGE_B64_CHARS = MAX_CHUNKS * CHUNK_B64_SIZE
CHUNK_REDUNDANCY = 3
CHUNK_RECEIVE_TIMEOUT_MS = 8000

# --- Replace _send_chunked_image with this version ---

def _send_chunked_image(self, filename, image_data):
    if not self.network or not self.network.is_host or not image_data:
        return

    image_b64 = base64.b64encode(image_data).decode("ascii")

    chunks = [
        image_b64[i:i + CHUNK_B64_SIZE]
        for i in range(0, len(image_b64), CHUNK_B64_SIZE)
    ]

    if not chunks or len(chunks) > MAX_CHUNKS:
        print("Too many chunks")
        return

    transfer_id = f"{filename}:{len(image_data)}"

    print(f"Sending chunked image: {filename}, bytes={len(image_data)}, chunks={len(chunks)}")

    self.network.send(
        'next_image',
        {
            'filename': filename,
            'transfer_id': transfer_id,
            'chunked': True,
            'total_chunks': len(chunks)
        }
    )

    delay = 0

    for index, chunk in enumerate(chunks):
        payload = {
            'filename': filename,
            'transfer_id': transfer_id,
            'index': index,
            'total_chunks': len(chunks),
            'chunk': chunk,
        }

        for _ in range(CHUNK_REDUNDANCY):
            self.root.after(
                delay,
                lambda p=payload: self.network.send('next_image_chunk', p)
            )
            delay += 2


# --- Replace _receive_next_image_chunk with this version ---

def _receive_next_image_chunk(self, data):
    self._prune_stale_chunk_transfers()

    transfer_id = data.get('transfer_id')
    chunk = data.get('chunk')
    index = data.get('index')

    try:
        index = int(index)
        total_chunks = int(data.get('total_chunks', 0))
    except (TypeError, ValueError):
        return

    if not transfer_id or not isinstance(chunk, str):
        return

    pending = self.pending_image_chunks.get(transfer_id)

    # FIX: allow chunks BEFORE header packet arrives
    if not pending:
        filename = os.path.basename(data.get("filename", "received.jpg"))

        now_ms = int(
            self.root.winfo_toplevel().tk.call("clock", "milliseconds")
        )

        pending = {
            "filename": filename,
            "total": total_chunks,
            "chunks": {},
            "started_ms": now_ms
        }

        self.pending_image_chunks[transfer_id] = pending

    if pending.get('total') != total_chunks:
        return

    if index < 0 or index >= total_chunks:
        return

    pending['chunks'][index] = chunk

    print(f"Received chunk {index + 1}/{total_chunks} for {transfer_id}")

    if len(pending['chunks']) < total_chunks:
        return

    assembled = ''.join(
        pending['chunks'].get(i, '')
        for i in range(total_chunks)
    )

    del self.pending_image_chunks[transfer_id]

    self._receive_next_image({
        'filename': pending['filename'],
        'image_b64': assembled,
        'chunked_transfer': True
    })


# --- Replace path validation block in _receive_next_image ---

folder = os.path.abspath(self.game.image_folder)
path = os.path.abspath(os.path.join(folder, filename))

if os.path.commonpath([folder, path]) != folder:
    print("Security warning: blocked invalid image path")
    return
