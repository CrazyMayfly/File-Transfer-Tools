import ssl
import os.path
import readline

from pbar_manager import PbarManager
from utils import *
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


def get_dir_file_name(filepath, desc_suffix='files', position=0):
    """
    获取某文件路径下的所有文件夹和文件的相对路径，并显示进度条。
    :param desc_suffix: 描述后缀
    :param position: 进度条位置
    :param filepath: 文件路径
    :return: 返回该文件路径下的所有文件夹、文件的相对路径
    """
    folders, files = {}, []
    root_abs_path = os.path.abspath(filepath)
    queue = deque([(root_abs_path, '.')])
    processed_paths = set()

    # 初始化进度显示
    pbar = tqdm(desc=f"Scanning {desc_suffix}", unit=" files", position=position, dynamic_ncols=True)

    while queue:
        current_abs_path, current_rel_path = queue.popleft()
        if current_abs_path in processed_paths:
            continue
        processed_paths.add(current_abs_path)

        stat = os.stat(current_abs_path)
        folders[current_rel_path] = (stat.st_atime, stat.st_mtime)

        try:
            with os.scandir(current_abs_path) as it:
                for entry in it:
                    entry_rel_path = f"{current_rel_path}/{entry.name}" if current_rel_path != '.' else entry.name
                    if entry.is_dir(follow_symlinks=False):
                        queue.append((entry.path, entry_rel_path))
                    elif entry.is_file(follow_symlinks=False):
                        files.append(entry_rel_path)
                        pbar.update(1)
        except PermissionError:
            continue

    # 更新进度条描述
    pbar.set_postfix(folders=len(folders))
    pbar.close()
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


def alternate_first_last(input_list):
    """
    Place the first and last elements of input list alternatively
    """
    result = []
    left, right = 0, len(input_list) - 1

    while left <= right:
        if left == right:  # Handle the middle element when the list has odd length
            result.append(input_list[left])
        else:
            result.append(input_list[left])
            result.append(input_list[right])
        left += 1
        right -= 1
    return result


def collect_files_info(logger: Logger, files: set[str], root: str):
    # 将待发送的文件打印到日志，计算待发送的文件总大小
    msgs = [f'\n[INFO   ] {get_log_msg("Files to be sent: ")}\n']
    # 统计待发送的文件信息
    total_size = 0
    large_files_info, small_files_info = [], []
    for file in tqdm(files, delay=0.1, desc='collect files info', unit='files', mininterval=0.2, leave=False):
        real_path = Path(root, file)
        file_size = (file_stat := real_path.stat()).st_size
        info = file, file_size, (file_stat.st_ctime, file_stat.st_mtime, file_stat.st_atime)
        # 记录每个文件大小
        large_files_info.append(info) if file_size >> LARGE_FILE_SIZE_THRESHOLD else small_files_info.append(info)
        total_size += file_size
        msgs.append(f"{real_path}, {file_size}B\n")
    logger.silent_write(msgs)
    random.shuffle(small_files_info)
    large_files_info = deque(alternate_first_last(sorted(large_files_info, key=lambda item: item[1])))
    small_files_info = deque(split_by_threshold(small_files_info))
    logger.info(f'Send files under {root}, number: {len(files)}')
    # 初始化总进度条
    pbar = tqdm(total=total_size, desc='total', unit='bytes', unit_scale=True,
                mininterval=1, position=0, colour='#01579B', unit_divisor=1024)
    return large_files_info, small_files_info, total_size, pbar


class FTC:
    def __init__(self, ftt):
        self.__ftt = ftt
        self.__pbar: PbarManager = ...
        self.__base_dir: Path = ...
        self.__main_conn: ESocket = ftt.main_conn
        self.__connections: list[ESocket] = ftt.connections
        self.__command_prefix: str = 'powershell ' if ftt.peer_platform == WINDOWS else ''
        self.logger: Logger = ftt.logger
        self.__large_files_info: deque = deque()
        self.__small_files_info: deque = deque()
        self.__finished_files: deque = deque()

    def __prepare_to_compare_or_sync(self, command, is_compare: bool):
        prefix_length = len(compare if is_compare else force_sync) + 1
        folders = command[prefix_length:].split('"')
        folders = folders[0].split(' ') if len(folders) == 1 else \
            [dir_name.strip() for dir_name in folders if dir_name.strip()]
        if len(folders) != 2:
            self.logger.warning('Local folder and peer folder cannot be empty')
            return

        local_folder, peer_folder = folders
        if not os.path.exists(local_folder):
            self.logger.warning('Local folder does not exist')
            return

        self.__main_conn.send_head(peer_folder, COMMAND.COMPARE_FOLDER if is_compare else COMMAND.FORCE_SYNC_FOLDER, 0)
        if self.__main_conn.recv_size() != CONTROL.CONTINUE:
            self.logger.warning(f"Peer folder {peer_folder} does not exist")
            return
        return folders

    def __compare_or_sync_folder(self, command):
        is_compare = command.startswith(compare)
        if folders := self.__prepare_to_compare_or_sync(command, is_compare):
            if is_compare:
                self.__compare_folder(*folders)
            else:
                self.__force_sync_folder(*folders)

    def __compare_folder(self, local_folder, peer_folder):
        conn: ESocket = self.__main_conn
        local_files_info = get_files_info_relative_to_basedir(local_folder)
        # 将字符串转化为dict
        peer_files_info: dict = conn.recv_with_decompress()
        # 求各种集合
        compare_result = compare_files_info(local_files_info, peer_files_info)
        msgs = print_compare_result(local_folder, peer_folder, compare_result)
        self.logger.silent_write(msgs)
        files_info_equal = compare_result[2]
        if not files_info_equal:
            conn.send_size(CONTROL.CANCEL)
            return
        command = input("Continue to compare hash for filename and size both equal set?(y/n): ").lower()
        if command not in ('y', 'yes'):
            conn.send_size(CONTROL.CANCEL)
            return
        conn.send_size(CONTROL.CONTINUE)
        # 发送相同的文件名称
        conn.send_with_compress(files_info_equal)
        results = FileHash.parallel_calc_hash(local_folder, files_info_equal, True)
        peer_files_info = conn.recv_with_decompress()
        hash_not_matching = [filename for filename in files_info_equal if
                             results[filename] != peer_files_info[filename]]
        msg = ["hash not matching: "] + [('\t' + file_name) for file_name in hash_not_matching]
        print('\n'.join(msg))
        files_hash_equal = [filename for filename in files_info_equal if os.path.getsize(
            PurePath(local_folder, filename)) >> SMALL_FILE_CHUNK_SIZE and filename not in hash_not_matching]
        conn.send_with_compress(files_hash_equal)
        if not files_hash_equal:
            return
        results = FileHash.parallel_calc_hash(local_folder, files_info_equal, False)
        peer_files_info = conn.recv_with_decompress()
        for filename in files_hash_equal:
            if results[filename] != peer_files_info[filename]:
                print('\t' + filename)
                msg.append('\t' + filename)
        if len(msg) == 1:
            print('\t' + 'None')
            msg.append('\t' + 'None')
        msg.append('')
        self.logger.silent_write(['\n'.join(msg)])

    def __force_sync_folder(self, local_folder, peer_folder):
        """
        强制将本地文件夹的内容同步到对方文件夹，同步后双方文件夹中的文件内容一致
        """
        conn: ESocket = self.__main_conn
        local_files_info = get_files_info_relative_to_basedir(local_folder)
        # 将字符串转化为dict
        peer_files_info: dict = conn.recv_with_decompress()
        files_smaller_than_peer, files_smaller_than_local, files_info_equal, _, file_not_exists_in_local = compare_files_info(
            local_files_info, peer_files_info)
        # 传回文件名称、大小都相等的文件信息，用于后续的文件hash比较
        conn.send_with_compress(files_info_equal)
        # 进行快速hash比较
        results = get_files_modified_time(local_folder, files_info_equal)
        peer_files_info = conn.recv_with_decompress()
        mtime_not_matching = [filename for filename in files_info_equal if
                              int(results[filename]) != int(peer_files_info[filename])]
        msgs = ['\n[INFO   ] ' + get_log_msg(
            f'Force sync files: local folder {local_folder} -> peer folder {peer_folder}\n')]
        for arg in [("files exist in peer but not in local: ", file_not_exists_in_local),
                    ("files in local smaller than peer: ", files_smaller_than_peer),
                    ("files in peer smaller than local: ", files_smaller_than_local)]:
            msgs.append(print_filename_if_exists(*arg, print_if_empty=False))
        msg = ["files modified time not matching: "]
        if mtime_not_matching:
            msg.extend([
                f'\t{filename}: {format_timestamp(results[filename])} <-> {format_timestamp(peer_files_info[filename])}'
                for filename in mtime_not_matching])
        else:
            msg.append('\tNone')
        if mtime_not_matching:
            print('\n'.join(msg))
        msg.append('')
        self.logger.silent_write(msgs)

        files_to_remove_in_peer = files_smaller_than_peer + files_smaller_than_local + file_not_exists_in_local + mtime_not_matching
        if len(files_to_remove_in_peer) != 0:
            command = input(
                f"Continue to force sync files in local folder({local_folder})\n"
                f"    with above files removed in peer folder?(y/n): ").lower()
            if command not in ('y', 'yes'):
                conn.send_size(CONTROL.CANCEL)
                return
        conn.send_size(CONTROL.CONTINUE)
        conn.send_with_compress(files_to_remove_in_peer)
        self.__send_files_in_folder(local_folder, True)

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

    def __prepare_to_send(self, folder, is_sync):
        self.__base_dir = folder
        # 发送文件夹命令
        if not is_sync:
            self.__main_conn.send_head(PurePath(folder).name, COMMAND.SEND_FILES_IN_FOLDER, 0)
        folders, files = get_dir_file_name(folder)
        # 发送文件夹数据
        self.__main_conn.send_with_compress(folders)
        # 接收对方已有的文件名并计算出对方没有的文件
        files = set(files) - set(self.__main_conn.recv_with_decompress())
        if not files:
            self.__main_conn.send_size(0)
            self.logger.info('No files to send', highlight=1)
            return None
        large_files_info, small_files_info, total_size, pbar = collect_files_info(self.logger, files, folder)
        self.__main_conn.send_size(total_size)
        self.__large_files_info = large_files_info
        self.__small_files_info = small_files_info
        self.__pbar = PbarManager(pbar)
        return files

    def __send_files_in_folder(self, folder, is_sync=False):
        if self.__ftt.busy_lock.locked():
            self.logger.warning('Currently receiving/sending folder, please try again later.', highlight=1)
            return
        with self.__ftt.busy_lock:
            if not (files := self.__prepare_to_send(folder, is_sync)):
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
            self.__pbar.set_status(len(fails) > 0)
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
        self.__pbar = PbarManager(tqdm(total=file_size, desc=shorten_path(file.name, pbar_width), unit='bytes',
                           unit_scale=True, mininterval=1, position=0, colour='#01579B', unit_divisor=1024))
        try:
            self.__send_large_files(self.__main_conn, 0)
        except (ssl.SSLError, ConnectionError) as error:
            self.logger.error(error)
        finally:
            is_success = len(self.__finished_files) and self.__finished_files.pop() == file.name
            self.__pbar.set_status(not is_success)
            self.logger.success(f"{file} sent successfully") if is_success else self.logger.error(f"{file} failed to send")

    def __send_large_files(self, conn: ESocket, position: int):
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
                      mininterval=1, position=position, leave=False, disable=position == 0, unit_divisor=1024) as pbar:
                while rest_size > 0:
                    sent_size = conn.sendfile(fp, offset=fp.tell(), count=5 * MB)
                    rest_size -= sent_size
                    pbar.update(sent_size)
                    self.__pbar.update(sent_size)
            fp.close()
            # 发送文件的创建、访问、修改时间戳
            conn.sendall(times_struct.pack(*time_info))
            self.__pbar.update(peer_exist_size, decrease=True)
            self.__finished_files.append(filename)

    def __send_small_files(self, conn: ESocket, position: int):
        idx, real_path, files_info = 0, Path(""), []
        while len(self.__small_files_info):
            try:
                total_size, num, files_info = self.__small_files_info.pop()
                conn.send_head('', COMMAND.SEND_SMALL_FILE, total_size)
                conn.send_with_compress(files_info)
                with tqdm(total=total_size, desc=f'{num} small files', unit='bytes', unit_scale=True,
                          mininterval=0.2, position=position, leave=False, unit_divisor=1024) as pbar:
                    for idx, (filename, file_size, _) in enumerate(files_info):
                        real_path = Path(self.__base_dir, filename)
                        with real_path.open('rb') as fp:
                            conn.sendfile(fp)
                        pbar.update(file_size)
                self.__pbar.update(total_size)
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
        if command == sysinfo:
            self.__compare_sysinfo()
        elif command.startswith(speedtest):
            self.__speedtest(times=command[10:])
        elif command.startswith((compare, force_sync)):
            self.__compare_or_sync_folder(command)
        elif command.startswith(say):
            self.__main_conn.send_head(command[4:], COMMAND.CHAT, 0)
        elif command.endswith('clipboard'):
            self.__exchange_clipboard(command.split()[0])
        elif command.startswith(history):
            print_history(int(command.split()[1])) if len(command.split()) > 1 and command.split()[
                1].isdigit() else print_history()
        else:
            paths = command.split('|')
            # 由于判断是否为发送文件夹，若不为则执行命令
            flag = True
            path_not_exists = []
            for path in paths:
                if os.path.exists(path):
                    flag = False
                    if os.path.isdir(path):
                        self.__send_files_in_folder(path)
                    else:
                        self.__send_single_file(Path(path))
                else:
                    path_not_exists.append(path)
            if flag:
                self.__execute_command(command)
            elif len(path_not_exists):
                for path in path_not_exists:
                    self.logger.warning(f'Path does not exist: {path}, skipped.', highlight=1)
