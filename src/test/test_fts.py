import os.path
import unittest
from pathlib import Path

from src.FTS import FTS
from tools import create_random_file


class FTSTest(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path('ftt_test', 'fts_test')
        if not self.test_dir.exists():
            os.makedirs(self.test_dir)
        create_random_file(Path(self.test_dir, 'fts_file.txt'))
        create_random_file(Path(self.test_dir, 'smaller_file.txt'), file_size=1024 * 60)
        create_random_file(Path(self.test_dir, 'larger_file.txt'), file_size=1024 * 6)
        create_random_file(Path(self.test_dir, 'hash_unmatch_file.txt'), file_size=1024 * 256)

    def test_fts(self):
        with self.assertWarns((ResourceWarning, DeprecationWarning)):
            fts = FTS(base_dir=self.test_dir, password='test')
            fts.start()


if __name__ == '__main__':
    unittest.main()
