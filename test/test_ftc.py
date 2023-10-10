import os
import shutil
import subprocess
import unittest
from datetime import datetime
from unittest.mock import patch
from FTC import FTC, config
from tools import create_random_file


class FTCTest(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.normcase(os.path.join('ftt_test', 'ftc_test'))
        self.fts_test_dir = os.path.normcase(os.path.join('ftt_test', 'fts_test'))
        if not os.path.exists(self.test_dir):
            os.makedirs(self.test_dir)
        self.signal_file = os.path.join(self.test_dir, 'signal_test_file.txt')
        create_random_file(self.signal_file)
        create_random_file(os.path.join(self.test_dir, 'ftc_file.txt'))
        create_random_file(os.path.join(self.test_dir, 'smaller_file.txt'), file_size=1024 * 6)
        create_random_file(os.path.join(self.test_dir, 'larger_file.txt'), file_size=1024 * 60)
        create_random_file(os.path.join(self.test_dir, 'hash_unmatch_file.txt'), file_size=1024 * 256)
        self.batch_send_dir = os.path.join(self.test_dir, 'batch_send_test')
        if not os.path.exists(self.batch_send_dir):
            os.makedirs(self.batch_send_dir)
        for i in range(15):
            create_random_file(os.path.join(self.batch_send_dir, f'test_file_{i}.txt'))

    @patch('builtins.input')
    def test_ftc(self, mock_input):
        mock_input.side_effect = ['pwd', 'get clipboard', 'send clipboard', self.signal_file,
                                  self.batch_send_dir, 'sysinfo', f'compare {self.test_dir} {self.fts_test_dir}', 'y',
                                  self.signal_file, self.batch_send_dir, 'speedtest 50', 'history 15',
                                  'q']
        with self.assertRaises(SystemExit) as cm:
            with self.assertWarns((ResourceWarning, DeprecationWarning)):
                FTC(threads=6, host='127.0.0.1', use_ssl=True, password='test').start()
            self.assertEqual(cm.exception.code, 0)

    def tearDown(self):
        fts_signal_file = os.path.join(self.fts_test_dir, 'signal_test_file.txt')
        try:
            self.assertEqual(int(os.path.getctime(self.signal_file)), int(os.path.getctime(fts_signal_file)))
            self.assertEqual(int(os.path.getmtime(self.signal_file)), int(os.path.getmtime(fts_signal_file)))
        finally:
            shutil.rmtree(os.path.dirname(self.test_dir))
            with self.assertWarns(ResourceWarning):
                subprocess.Popen(os.path.join(config.log_dir, f'{datetime.now():%Y_%m_%d}_client.log'), shell=True,
                                 text=True)


if __name__ == '__main__':
    unittest.main()
