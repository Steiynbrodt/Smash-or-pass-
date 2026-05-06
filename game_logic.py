import os
import random
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageTk


def _validate_image_path(args):
    image_folder, rel_path = args
    file_abs_path = os.path.abspath(os.path.join(image_folder, rel_path))
    try:
        if os.path.commonpath([image_folder, file_abs_path]) != image_folder:
            return None
        with Image.open(file_abs_path) as img:
            img.verify()
        return rel_path
    except Exception:
        return None


class GameLogic:
    def __init__(self, image_folder, max_size=(500, 500)):
        self.image_folder = os.path.abspath(image_folder)  # Resolve to absolute path
        self.max_size = max_size
        self.images = self._load_images()
        self.current_image = None
        self.current_image_path = None

    def _load_images(self):
        """Load images from folder with path validation"""
        if not os.path.exists(self.image_folder):
            try:
                os.makedirs(self.image_folder, exist_ok=True)
            except OSError as e:
                print(f"Error creating image folder: {e}")
            return []

        if not os.path.isdir(self.image_folder):
            print(f"Error: {self.image_folder} is not a directory")
            return []

        candidates = []
        valid_ext = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')

        try:
            for root, _, files in os.walk(self.image_folder):
                for f in files:
                    file_path = os.path.join(root, f)
                    file_abs_path = os.path.abspath(file_path)

                    if os.path.commonpath([self.image_folder, file_abs_path]) != self.image_folder:
                        print(f"Security warning: Skipping file outside image folder: {f}")
                        continue

                    if os.path.isfile(file_abs_path) and f.lower().endswith(valid_ext):
                        rel_path = os.path.relpath(file_abs_path, self.image_folder)
                        candidates.append(rel_path)
        except OSError as e:
            print(f"Error reading image folder: {e}")
            return []

        if not candidates:
            return []

        max_workers = min(32, max(4, (os.cpu_count() or 1) * 2))
        images = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for rel_path in pool.map(_validate_image_path, [(self.image_folder, p) for p in candidates]):
                if rel_path:
                    images.append(rel_path)

        return images

    def get_random_image(self):
        """Get a random valid image, skipping unreadable/corrupt files."""
        if not self.images:
            return None, None

        candidates = self.images.copy()
        random.shuffle(candidates)

        for filename in candidates:
            try:
                self.current_image_path = os.path.join(self.image_folder, filename)

                # Security check: verify the resolved path is still within image folder
                file_abs_path = os.path.abspath(self.current_image_path)
                if os.path.commonpath([self.image_folder, file_abs_path]) != self.image_folder:
                    print("Security error: Attempted directory traversal detected")
                    continue

                with Image.open(file_abs_path) as opened:
                    img = self._scale_image(opened)
                if img is None:
                    continue
                return ImageTk.PhotoImage(img), file_abs_path
            except Exception as e:
                print(f"Error loading image '{filename}': {e}")
                continue

        return None, None

    def _scale_image(self, img, max_size=None):
        """Scale image maintaining aspect ratio and centered letterboxing."""
        try:
            target_size = max_size or self.max_size
            working_img = img.copy().convert("RGB")
            # Maintain aspect ratio, fit within max_size
            working_img.thumbnail(target_size, Image.LANCZOS)
            # Create a new image with black background
            background = Image.new('RGB', target_size, (0, 0, 0))
            # Paste the resized image in the center
            offset = (
                (target_size[0] - working_img.width) // 2,
                (target_size[1] - working_img.height) // 2
            )
            background.paste(working_img, offset)
            return background
        except Exception as e:
            print(f"Error scaling image: {e}")
            return None
