import tempfile
import unittest
from pathlib import Path

from PIL import Image

from game_logic import GameLogic
from network import _validate_port, _validate_room_key, _validate_username


class TestNetworkValidation(unittest.TestCase):
    def test_validate_port(self):
        self.assertEqual(_validate_port(55555), 55555)
        with self.assertRaises(ValueError):
            _validate_port(0)

    def test_validate_username(self):
        self.assertEqual(_validate_username("  "), "Player")
        self.assertEqual(_validate_username("A" * 100), "A" * 50)

    def test_validate_room_key(self):
        self.assertEqual(_validate_room_key("Room123"), "Room123")
        with self.assertRaises(ValueError):
            _validate_room_key("bad-key!")


class TestGameLogic(unittest.TestCase):
    def test_scale_image_to_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            image_path = folder / "sample.png"
            Image.new("RGB", (1200, 600), (255, 0, 0)).save(image_path)

            logic = GameLogic(str(folder), max_size=(500, 500))
            with Image.open(image_path) as img:
                scaled = logic._scale_image(img, max_size=(320, 240))

            self.assertIsNotNone(scaled)
            self.assertEqual(scaled.size, (320, 240))


if __name__ == "__main__":
    unittest.main()
