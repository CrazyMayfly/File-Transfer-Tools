import ssl
import random
import os.path
import readline
from Utils import *
from tqdm import tqdm
from sys_info import *
from pathlib import Path
from collections import deque
from shutil import get_terminal_size


def print_history(nums=10):
    current_length = readline.get_current_history_length()
    start = max(1, current_length - nums + 1)
    for i in range(start, current_length + 1):
        print(readline.get_history_item(i))


def print_filename_if_exists(prompt, filename_list):
    msg = [prompt]
    if filename_list:
        msg.extend([('\t' + file_name) for file_name in filename_list])
    else:
        msg.append('\tNone')
    print('\n'.join(msg))
    msg.append('')
    return '\n'.join(msg)


def get_dir_file_name(filepath):
    """
    获取某文件路径下的所有文件夹和文件的相对路径
    :param filepath: 文件路径
    :return :返回该文件路径下的所有文件夹、文件的相对路径
    """
    folders, files = {}, []
    for path, _, file_list in os.walk(filepath):
        rel_path = os.path.relpath(path, filepath)
        folders[rel_path] = os.path.getatime(path), os.path.getmtime(path)
        files += [PurePath(rel_path, file).as_posix() for file in file_list]
    return folders, files


def split_by_threshold(info):
    result = []
    current_sum = last_idx = 0
    for idx, (_, size, _) in enumerate(info, start=1):
        current_sum += size
        if current_sum >> SMALL_FILE_CHUNK_SIZE:
            result.append((current_sum, idx - last_idx, info[last_idx:idx]))
            last_idx = idx
            current_sum = 0
    if (rest := len(info) - last_idx) > 0:
        result.append((current_sum, rest, info[last_idx:]))
    return result


class FTC:
    def __init__(self, ftt):
        self.__ftt = ftt
        self.__pbar: tqdm = ...
        self.__base_dir: Path = ...
        self.__main_conn: ESocket = ftt.main_conn
        self.__connections: list[ESocket] = ftt.connections
        self.__command_prefix: str = 'powershell ' if ftt.peer_platform == WINDOWS else ''
        self.logger: Logger = ftt.logger
        self.__large_files_info: deque = deque()
        self.__small_files_info: deque = deque()
        self.__finished_files: deque = deque()

    def __prepare_to_compare(self, command):
        folders = command[8:].split('"')
        folders = folders[0].split(' ') if len(folders) == 1 else \
            [dir_name.strip() for dir_name in folders if dir_name.strip()]
        if len(folders) != 2:
            self.logger.warning('Local folder and peer folder cannot be empty')
            return

        local_folder, peer_folder = folders
        if not os.path.exists(local_folder):
            self.logger.warning('Local folder does not exist')
            return

        self.__main_conn.send_head(peer_folder, COMMAND.COMPARE_FOLDER, 0)
        if self.__main_conn.recv_size() != CONTROL.CONTINUE:
            self.logger.warning(f"Peer folder {peer_folder} does not exist")
            return
        return folders

    def __compare_folder(self, local_folder, peer_folder):
        conn: ESocket = self.__main_conn
        local_files_info = get_files_info_relative_to_basedir(local_folder)
        # 将字符串转化为dict
        peer_files_info: dict = conn.recv_with_decompress()
        # 求各种集合
        files_smaller_than_peer, files_smaller_than_local, files_info_equal, files_not_exist_in_peer = [], [], [], []
        for filename in local_files_info.keys():
            peer_size = peer_files_info.pop(filename, -1)
            if peer_size == -1:
                files_not_exist_in_peer.append(filename)
                continue
            size_diff = local_files_info[filename] - peer_size
            if size_diff < 0:
                files_smaller_than_peer.append(filename)
            elif size_diff == 0:
                files_info_equal.append(filename)
            else:
                files_smaller_than_local.append(filename)
        simplified_info = files_info_equal[:10] + ['(more hidden...)'] if len(
            files_info_equal) > 10 else files_info_equal
        file_not_exists_in_local = peer_files_info.keys()
        msgs = ['\n[INFO   ] ' + get_log_msg(
            f'Compare the differences between local folder {local_folder} and peer folder {peer_folder}\n')]
        for arg in [("files exist in peer but not in local: ", file_not_exists_in_local),
                    ("files exist in local but not in peer: ", files_not_exist_in_peer),
                    ("files in local smaller than peer: ", files_smaller_than_peer),
                    ("files in peer smaller than local: ", files_smaller_than_local),
                    ("files name and size both equal in two sides: ", simplified_info)]:
            msgs.append(print_filename_if_exists(*arg))
        self.logger.silent_write(msgs)
        if not files_info_equal:
            conn.send_size(CONTROL.CANCEL)
            return
        if input("Continue to compare hash for filename and size both equal set?(y/n): ").lower() != 'y':
            conn.send_size(CONTROL.CANCEL)
            return
        # 发送继续请求
        conn.send_size(CONTROL.CONTINUE)
        # 发送相同的文件名称
        conn.send_with_compress(files_info_equal)
        results = {filename: get_file_md5(PurePath(local_folder, filename)) for filename in
                   tqdm(files_info_equal, desc='calc hash', unit='files', mininterval=0.2, leave=False)}
        # 获取本次字符串大小
        peer_files_info = conn.recv_with_decompress()
        hash_not_matching = [filename for filename in results.keys() if
                             results[filename] != peer_files_info[filename]]
        self.logger.silent_write([print_filename_if_exists("hash not matching: ", hash_not_matching)])

    def __update_global_pbar(self, size, decrease=False):
        with self.__pbar.get_lock():
            if not decrease:
                self.__pbar.update(size)
            else:
                self.__pbar.total -= size

    def __set_pbar_status(self, fail):
        self.__pbar.colour = '#F44336' if fail else '#98c379'
        self.__pbar.close()

    def __execute_command(self, command):
        if len(command) == 0:
            return
        if self.__ftt.peer_platform == WINDOWS and (command.startswith('cmd') or command == 'powershell'):
            if command == 'powershell':
                self.logger.info('use windows powershell')
                self.__command_prefix = 'powershell '
            else:
                self.logger.info('use command prompt')
                self.__command_prefix = ''
            return
        command = self.__command_prefix + command
        conn = self.__main_conn
        conn.send_head(command, COMMAND.EXECUTE_COMMAND, 0)
        msgs = [f'\n[INFO   ] {get_log_msg("Give command: ")}{command}']
        # 接收返回结果
        result, command, _ = conn.recv_head()
        while command == COMMAND.EXECUTE_RESULT:
            print(result, end='')
            msgs.append(result)
            result, command, _ = conn.recv_head()
        self.logger.silent_write(msgs)

    def __compare_sysinfo(self):
        # 发送比较系统信息的命令到FTS
        self.__main_conn.send_head('', COMMAND.SYSINFO, 0)
        # 异步获取自己的系统信息
        thread = ThreadWithResult(get_sys_info)
        thread.start()
        # 接收对方的系统信息
        peer_sysinfo = self.__main_conn.recv_with_decompress()
        msgs = [f'[INFO   ] {get_log_msg("Compare the system information of both parties: ")}\n',
                print_sysinfo(peer_sysinfo), print_sysinfo(thread.get_result())]
        # 等待本机系统信息获取完成
        self.logger.silent_write(msgs)

    def __speedtest(self, times):
        times = '500' if times.isspace() or not times else times
        while not (times.isdigit() and int(times) > 0):
            times = input("Please re-enter the data amount (in MB): ")
        times, data_unit = int(times), 1000 * 1000  # 1MB
        data_size = times * data_unit
        conn = self.__main_conn
        conn.send_head('', COMMAND.SPEEDTEST, data_size)
        start = time.time()
        with tqdm(total=data_size, desc='upload speedtest', unit='bytes', unit_scale=True, mininterval=1) as pbar:
            for i in range(times):
                # 生产随机字节
                conn.sendall(os.urandom(data_unit))
                pbar.update(data_unit)
        show_bandwidth('Upload speed test completed', data_size, time.time() - start, self.logger)
        upload_over = time.time()
        with tqdm(total=data_size, desc='download speedtest', unit='bytes', unit_scale=True, mininterval=1) as pbar:
            for i in range(times):
                conn.recv_data(data_unit)
                pbar.update(data_unit)
        show_bandwidth('Download speed test completed', data_size, time.time() - upload_over, self.logger)

    def __exchange_clipboard(self, command):
        """
        交换（发送，获取）对方剪切板内容

        @param command: get 或 send
        @return:
        """
        func = get_clipboard if command == GET else send_clipboard
        func(self.__main_conn, self.logger)

    def __prepare_to_send(self, folder):
        self.__base_dir = folder
        # 发送文件夹命令
        self.__main_conn.send_head(PurePath(folder).name, COMMAND.SEND_FILES_IN_FOLDER, 0)
        self.logger.info(f'Collect files information')
        folders, files = get_dir_file_name(folder)
        # 发送文件夹数据
        self.__main_conn.send_with_compress(folders)
        # 接收对方已有的文件名并计算出对方没有的文件
        files = set(files) - set(self.__main_conn.recv_with_decompress())
        if not files:
            self.__main_conn.send_size(0)
            self.logger.info('No files to send', highlight=1)
            return
        # 将待发送的文件打印到日志，计算待发送的文件总大小
        msgs = [f'\n[INFO   ] {get_log_msg("Files to be sent: ")}\n']
        # 统计待发送的文件信息
        total_size = 0
        large_files_info, small_files_info = [], []
        for file in files:
            real_path = Path(folder, file)
            file_size = (file_stat := real_path.stat()).st_size
            info = file, file_size, (file_stat.st_ctime, file_stat.st_mtime, file_stat.st_atime)
            # 记录每个文件大小
            large_files_info.append(info) if file_size >> LARGE_FILE_SIZE_THRESHOLD else small_files_info.append(info)
            total_size += file_size
            msgs.append(f"{real_path}, {file_size}B\n")
        self.logger.silent_write(msgs)
        self.__main_conn.send_size(total_size)
        random.shuffle(small_files_info)
        self.__large_files_info = deque(sorted(large_files_info, key=lambda item: item[1]))
        self.__small_files_info = deque(split_by_threshold(small_files_info))
        self.logger.info(f'Send files under {folder}, number: {len(files)}')
        # 初始化总进度条
        self.__pbar = tqdm(total=total_size, desc='total', unit='bytes', unit_scale=True,
                           mininterval=1, position=0, colour='#01579B')
        return files

    def __send_files_in_folder(self, folder):
        if self.__ftt.busy_lock.locked():
            self.logger.warning('Currently receiving/sending folder, please try again later.', highlight=1)
            return
        with self.__ftt.busy_lock:
            if not (files := self.__prepare_to_send(folder)):
                return
            # 发送文件
            futures = [self.__ftt.executor.submit(self.__send_file, conn, position) for position, conn in
                       enumerate(self.__connections, start=1)]
            for future in futures:
                while not future.done():
                    time.sleep(0.2)

            fails = files - set(self.__finished_files)
            self.__finished_files.clear()
            # 比对发送失败的文件
            self.__set_pbar_status(len(fails))
            if fails:
                self.logger.error("Failed to sent: ", highlight=1)
                for fail in fails:
                    self.logger.warning(fail)
            errors = [future.exception() for future in futures]
            if errors.count(None) != len(errors):
                errors = '\n'.join([f'Thread-{idx}: {exception}' for idx, exception in enumerate(errors) if exception])
                self.logger.error(f"Exceptions occurred during this sending: \n{errors}", highlight=1)

    def __send_single_file(self, file: Path):
        self.logger.silent_write([f'\n[INFO   ] {get_log_msg(f"Send a single file: {file}")}\n'])
        self.__base_dir = file.parent
        file_size = (file_stat := file.stat()).st_size
        time_info = file_stat.st_ctime, file_stat.st_mtime, file_stat.st_atime
        self.__large_files_info.append((file.name, file_size, time_info))
        pbar_width = get_terminal_size().columns / 4
        self.__pbar = tqdm(total=file_size, desc=shorten_path(file.name, pbar_width), unit='bytes',
                           unit_scale=True, mininterval=1, position=0, colour='#01579B')
        try:
            self.__send_large_files(self.__main_conn, 0)
        except (ssl.SSLError, ConnectionError) as error:
            self.logger.error(error)
        finally:
            success = len(self.__finished_files) and self.__finished_files.pop() == file.name
            self.__set_pbar_status(fail=not success)
            self.logger.success(f"{file} sent successfully") if success else self.logger.error(f"{file} failed to send")

    def __send_large_files(self, conn: ESocket, position: int):
        view = memoryview(buf := bytearray(buf_size))
        while len(self.__large_files_info):
            filename, file_size, time_info = self.__large_files_info.pop()
            real_path = PurePath(self.__base_dir, filename)
            try:
                fp = open(real_path, 'rb')
            except FileNotFoundError:
                self.logger.error(f'Failed to open: {real_path}')
                continue
            conn.send_head(filename, COMMAND.SEND_LARGE_FILE, file_size)
            if (flag := conn.recv_size()) == CONTROL.FAIL2OPEN:
                self.logger.error(f'Peer failed to receive the file: {real_path}', highlight=1)
                return
            # 服务端已有的文件大小
            fp.seek(peer_exist_size := flag, 0)
            rest_size = file_size - peer_exist_size
            pbar_width = get_terminal_size().columns / 4
            with tqdm(total=rest_size, desc=shorten_path(filename, pbar_width), unit='bytes', unit_scale=True,
                      mininterval=1, position=position, leave=False, disable=position == 0) as pbar:
                while data_size := fp.readinto(buf):
                    conn.sendall(view[:min(data_size, rest_size)])
                    pbar.update(data_size)
                    rest_size -= data_size
                    self.__update_global_pbar(data_size)
            fp.close()
            # 发送文件的创建、访问、修改时间戳
            conn.sendall(times_struct.pack(*time_info))
            self.__update_global_pbar(peer_exist_size, decrease=True)
            self.__finished_files.append(filename)

    def __send_small_files(self, conn: ESocket, position: int):
        idx, real_path, files_info = 0, Path(""), []
        while len(self.__small_files_info):
            try:
                total_size, num, files_info = self.__small_files_info.pop()
                conn.send_head('', COMMAND.SEND_SMALL_FILE, total_size)
                conn.send_with_compress(files_info)
                with tqdm(total=total_size, desc=f'{num} small files', unit='bytes', unit_scale=True,
                          mininterval=0.2, position=position, leave=False) as pbar:
                    for idx, (filename, file_size, _) in enumerate(files_info):
                        real_path = Path(self.__base_dir, filename)
                        with real_path.open('rb') as fp:
                            conn.sendall(fp.read(file_size))
                        pbar.update(file_size)
                self.__update_global_pbar(total_size)
            except FileNotFoundError:
                self.logger.error(f'Failed to open: {real_path}')
            finally:
                self.__finished_files.extend([filename for filename, _, _ in files_info[:idx + 1]])

    def __send_file(self, conn: ESocket, position: int):
        try:
            if position < 3:
                self.__send_large_files(conn, position)
                self.__send_small_files(conn, position)
            else:
                self.__send_small_files(conn, position)
                self.__send_large_files(conn, position)
        finally:
            conn.send_head('', COMMAND.FINISH, 0)

    def execute(self, command):
        if os.path.isdir(command) and os.path.exists(command):
            self.__send_files_in_folder(command)
        elif os.path.isfile(command) and os.path.exists(command):
            self.__send_single_file(Path(command))
        elif command == sysinfo:
            self.__compare_sysinfo()
        elif command.startswith(speedtest):
            self.__speedtest(times=command[10:])
        elif command.startswith(compare):
            if folders := self.__prepare_to_compare(command):
                self.__compare_folder(*folders)
        elif command.startswith(say):
            self.__main_conn.send_head(command[4:], COMMAND.CHAT, 0)
        elif command.endswith('clipboard'):
            self.__exchange_clipboard(command.split()[0])
        elif command.startswith(history):
            print_history(int(command.split()[1])) if len(command.split()) > 1 and command.split()[
                1].isdigit() else print_history()
        else:
            self.__execute_command(command)
