import os.path
import unittest

from FTS import FTS, handle_ctrl_event
from tools import create_random_file


class FTSTest(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.normcase(os.path.join('ftt_test', 'fts_test'))
        if not os.path.exists(self.test_dir):
            os.makedirs(self.test_dir)
        create_random_file(os.path.join(self.test_dir, 'fts_file.txt'))
        create_random_file(os.path.join(self.test_dir, 'smaller_file.txt'), file_size=1024 * 60)
        create_random_file(os.path.join(self.test_dir, 'larger_file.txt'), file_size=1024 * 6)
        create_random_file(os.path.join(self.test_dir, 'hash_unmatch_file.txt'), file_size=1024 * 256)

    def test_fts(self):
        with self.assertWarns((ResourceWarning, DeprecationWarning)):
            fts = FTS(base_dir=self.test_dir, use_ssl=True, repeated=False, password='test')
            handle_ctrl_event(fts.logger)
            fts.start()


if __name__ == '__main__':
    unittest.main()
