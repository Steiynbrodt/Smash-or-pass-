import os
import random
from PIL import Image, ImageTk

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
        
        images = []
        try:
            for f in os.listdir(self.image_folder):
                # Validate file is within image folder (prevent directory traversal)
                file_path = os.path.join(self.image_folder, f)
                file_abs_path = os.path.abspath(file_path)
                
                # Security check: ensure file is within the image folder
                if os.path.commonpath([self.image_folder, file_abs_path]) != self.image_folder:
                    print(f"Security warning: Skipping file outside image folder: {f}")
                    continue
                
                if os.path.isfile(file_abs_path) and f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                    images.append(f)
        except OSError as e:
            print(f"Error reading image folder: {e}")
        
        return images

    def get_random_image(self):
        """Get random image with security validation"""
        if not self.images:
            return None, None
        
        try:
            filename = random.choice(self.images)
            self.current_image_path = os.path.join(self.image_folder, filename)
            
            # Security check: verify the resolved path is still within image folder
            file_abs_path = os.path.abspath(self.current_image_path)
            if os.path.commonpath([self.image_folder, file_abs_path]) != self.image_folder:
                print(f"Security error: Attempted directory traversal detected")
                return None, None
            
            img = Image.open(file_abs_path)
            img = self._scale_image(img)
            return ImageTk.PhotoImage(img), file_abs_path
        except Exception as e:
            print(f"Error loading image: {e}")
            return None, None

    def _scale_image(self, img, max_size=None):
        """Scale image maintaining aspect ratio"""
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
