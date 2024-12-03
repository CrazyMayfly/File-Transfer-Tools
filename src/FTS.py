import os.path
import subprocess
import concurrent.futures

import send2trash

from Utils import *
from sys_info import *
from pathlib import Path

if windows:
    from win_set_time import set_times


def avoid_filename_duplication(filename: str):
    """
    当文件重复时另取新的文件名

    @param filename: 原文件名
    @return: 新文件名
    """
    if os.path.exists(filename):
        i = 1
        base, extension = os.path.splitext(filename)
        while os.path.exists(filename):
            filename = f"{base}({i}){extension}"
            i += 1
    return filename


class FTS:
    def __init__(self, ftt):
        self.__ftt = ftt
        self.__main_conn: ESocket = ftt.main_conn_recv
        self.logger: Logger = ftt.logger

    def __modify_file_time(self, file_path: str, create_timestamp: float, modify_timestamp: float,
                           access_timestamp: float):
        """
        用来修改文件的相关时间属性
        :param file_path: 文件路径名
        :param create_timestamp: 创建时间戳
        :param modify_timestamp: 修改时间戳
        :param access_timestamp: 访问时间戳
        """
        try:
            if windows:
                set_times(file_path, create_timestamp, modify_timestamp, access_timestamp)
            else:
                os.utime(path=file_path, times=(access_timestamp, modify_timestamp))
        except Exception as error:
            self.logger.warning(f'{file_path} file time modification failed, {error}')

    def __compare_folder(self, folder):
        # self.logger.info(f"Client request to compare folder: {folder}")
        if not os.path.exists(folder):
            # 发送目录不存在
            self.__main_conn.send_size(CONTROL.CANCEL)
            return
        self.__main_conn.send_size(CONTROL.CONTINUE)
        # 将数组拼接成字符串发送到客户端
        self.__main_conn.send_with_compress(get_files_info_relative_to_basedir(folder))
        if self.__main_conn.recv_size() != CONTROL.CONTINUE:
            return
        file_size_and_name_both_equal = self.__main_conn.recv_with_decompress()
        # 得到文件相对路径名: hash值字典
        results = FileHash.parallel_calc_hash(folder, file_size_and_name_both_equal, True)
        self.__main_conn.send_with_compress(results)
        files_hash_equal = self.__main_conn.recv_with_decompress()
        if not files_hash_equal:
            return
        results = FileHash.parallel_calc_hash(folder, file_size_and_name_both_equal, False)
        self.__main_conn.send_with_compress(results)

    def __force_sync_folder(self, folder):
        if not os.path.exists(folder):
            # 发送目录不存在
            self.__main_conn.send_size(CONTROL.CANCEL)
            return
        self.__main_conn.send_size(CONTROL.CONTINUE)
        self.logger.info(f"Peer request to force sync folder: {folder}")
        # 将数组拼接成字符串发送到客户端
        self.__main_conn.send_with_compress(get_files_info_relative_to_basedir(folder))
        # 得到文件相对路径名: hash值字典
        file_info_equal = self.__main_conn.recv_with_decompress()
        self.__main_conn.send_with_compress(FileHash.parallel_calc_hash(folder, file_info_equal, True))
        if self.__main_conn.recv_size() != CONTROL.CONTINUE:
            self.logger.info("Peer canceled the sync.")
            return
        files_to_remove: list = self.__main_conn.recv_with_decompress()
        self.logger.silent_write([print_filename_if_exists('Files to be removed:', files_to_remove, False)])
        for file_rel_path in files_to_remove:
            try:
                send2trash.send2trash(PurePath(folder, file_rel_path))
            except Exception as e:
                self.logger.warning(f'Failed to remove {file_rel_path}, reason: {e}')
        self.__recv_files_in_folder(Path(folder))

    def __execute_command(self, command):
        out = subprocess.Popen(args=command, shell=True, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT).stdout
        output = [f'[LOG    ] {get_log_msg("Execute command")}: {command}']
        while result := out.readline():
            self.__main_conn.send_head(result, COMMAND.EXECUTE_RESULT, 0)
            output.append(result)
        # 命令执行结束
        self.__main_conn.send_head('', COMMAND.FINISH, 0)
        self.logger.silent_write(output)

    def __speedtest(self, data_size):
        self.logger.info(f"Client request speed test, size: {get_size(2 * data_size, factor=1000)}")
        start = time.time()
        data_unit = 1000 * 1000
        for i in range(0, int(data_size / data_unit)):
            self.__main_conn.recv_data(data_unit)
        show_bandwidth('Download speed test completed', data_size, time.time() - start, self.logger)
        download_over = time.time()
        for i in range(0, int(data_size / data_unit)):
            self.__main_conn.sendall(os.urandom(data_unit))
        show_bandwidth('Upload speed test completed', data_size, time.time() - download_over, self.logger)

    def __makedirs(self, dir_names, base_dir):
        for dir_name in dir_names:
            cur_dir = Path(base_dir, dir_name)
            if cur_dir.exists():
                continue
            try:
                cur_dir.mkdir()
            except FileNotFoundError:
                self.logger.error(f'Failed to create folder {cur_dir}', highlight=1)

    def __recv_files_in_folder(self, cur_dir: Path):
        with self.__ftt.busy_lock:
            files = []
            if cur_dir.exists():
                for path, _, file_list in os.walk(cur_dir):
                    files += [PurePath(PurePath(path).relative_to(cur_dir), file).as_posix() for file in file_list]
            dirs_info: dict = self.__main_conn.recv_with_decompress()
            self.__makedirs(dirs_info.keys(), cur_dir)
            # 发送已存在的文件名
            self.__main_conn.send_with_compress(files)
            start, total_size = time.time(), self.__main_conn.recv_size()
            if not total_size:
                self.logger.info('No files to receive')
                return
            futures = [self.__ftt.executor.submit(self.__slave_work, conn, cur_dir) for conn in self.__ftt.connections]
            concurrent.futures.wait(futures)

            for dir_name, times in dirs_info.items():
                folder = PurePath(cur_dir, dir_name)
                try:
                    os.utime(path=folder, times=times)
                except Exception as error:
                    self.logger.warning(f'Folder {cur_dir} time modification failed, {error}', highlight=1)
            show_bandwidth('Received folder', total_size, time.time() - start, self.logger, LEVEL.INFO)

    def __recv_small_files(self, conn: ESocket, cur_dir, files_info):
        real_path = Path("")
        try:
            msgs = []
            for filename, file_size, time_info in files_info:
                real_path = Path(cur_dir, filename)
                real_path.write_bytes(conn.recv_data(file_size))
                self.__modify_file_time(str(real_path), *time_info)
                msgs.append(f'[SUCCESS] {get_log_msg("Received")}: {real_path}\n')
            self.logger.success(f'Received: {len(files_info)} small files')
            self.logger.silent_write(msgs)
        except ConnectionDisappearedError:
            self.logger.warning(f'Connection was terminated unexpectedly and reception failed: {real_path}')
        except FileNotFoundError:
            self.logger.warning(f'File creation/opening failed that cannot be received: {real_path}', highlight=1)

    def __recv_large_file(self, conn: ESocket, cur_dir, filename, file_size):
        original_file = avoid_filename_duplication(str(PurePath(cur_dir, filename)))
        cur_download_file = f'{original_file}.ftsdownload'
        try:
            with open(cur_download_file, 'ab') as fp:
                conn.send_size(size := os.path.getsize(cur_download_file))
                rest_size = file_size - size
                while rest_size >> 12:
                    data, size = conn.recv()
                    fp.write(data)
                    rest_size -= size
                fp.write(conn.recv_data(rest_size))
            os.rename(cur_download_file, original_file)
            self.logger.success(f'Received: {original_file}')
            timestamps = times_struct.unpack(conn.recv_data(times_struct.size))
            self.__modify_file_time(original_file, *timestamps)
        except ConnectionDisappearedError:
            self.logger.warning(f'Connection was terminated unexpectedly and reception failed: {original_file}')
        except PermissionError as err:
            self.logger.warning(f'Failed to rename: {cur_download_file} -> {original_file}, {err}')
        except FileNotFoundError:
            self.logger.warning(f'File creation/opening failed that cannot be received: {original_file}', highlight=1)
            conn.sendall(size_struct.pack(CONTROL.FAIL2OPEN))

    def __slave_work(self, conn: ESocket, cur_dir):
        """
        从连接的工作，只用于处理多文件接收

        @param conn: 从连接
        """
        try:
            while True:
                filename, command, file_size = conn.recv_head()
                if command == COMMAND.SEND_LARGE_FILE:
                    self.__recv_large_file(conn, cur_dir, filename, file_size)
                elif command == COMMAND.SEND_SMALL_FILE:
                    self.__recv_small_files(conn, cur_dir, conn.recv_with_decompress())
                elif command == COMMAND.FINISH:
                    break
        except ConnectionError:
            return
        except Exception as e:
            msg = 'Peer data flow abnormality, connection disconnected' if isinstance(e, UnicodeDecodeError) else str(e)
            self.logger.error(msg, highlight=1)

    def execute(self, filename, command, file_size):
        """
        主连接的工作
        """
        match command:
            case COMMAND.SEND_FILES_IN_FOLDER:
                self.logger.info(f'Receiving folder: {filename}')
                self.__recv_files_in_folder(Path(self.__ftt.base_dir, filename))
            case COMMAND.SEND_LARGE_FILE:
                self.logger.info(f'Receiving single file: {filename}, size: {get_size(file_size)}')
                self.__recv_large_file(self.__main_conn, self.__ftt.base_dir, filename, file_size)
            case COMMAND.COMPARE_FOLDER:
                self.__compare_folder(filename)
            case COMMAND.FORCE_SYNC_FOLDER:
                self.__force_sync_folder(filename)
            case COMMAND.EXECUTE_COMMAND:
                self.__execute_command(filename)
            case COMMAND.SYSINFO:
                self.__main_conn.send_with_compress(get_sys_info())
            case COMMAND.SPEEDTEST:
                self.__speedtest(file_size)
            case COMMAND.CHAT:
                self.logger.log(f'{self.__ftt.peer_username} said: {filename}')
            case COMMAND.PULL_CLIPBOARD:
                send_clipboard(self.__main_conn, self.logger, ftc=False)
            case COMMAND.PUSH_CLIPBOARD:
                get_clipboard(self.__main_conn, self.logger, filename, command, file_size, ftc=False)
