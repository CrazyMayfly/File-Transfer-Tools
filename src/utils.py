import lzma
import re
import os
import pickle
import random
import socket
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import md5
from os import PathLike
from pathlib import PurePath, Path
from datetime import datetime
from typing import TextIO
from tqdm import tqdm
import pyperclip
from constants import *

# 解决win10的cmd中直接使用转义序列失效问题
if windows:
    os.system("")


# 日志类，简化日志打印
class Logger:
    def __init__(self, log_file_path: PurePath):
        self.__log_file: TextIO = open(log_file_path, 'a', encoding=utf8)
        self.__log_lock: threading.Lock = threading.Lock()
        self.__writing_lock: threading.Lock = threading.Lock()
        self.__writing_buffer: list[str] = []
        threading.Thread(target=self.auto_flush, daemon=True).start()

    def log(self, msg, level: LEVEL = LEVEL.LOG, highlight=0):
        msg = get_log_msg(msg)
        with self.__log_lock:
            print(f"\r\033[{highlight}{level}m{msg}\033[0m")
        with self.__writing_lock:
            self.__writing_buffer.append(f'[{level.name:7}] {msg}\n')

    def info(self, msg, highlight=0):
        self.log(msg, LEVEL.INFO, highlight)

    def warning(self, msg, highlight=0):
        self.log(msg, LEVEL.WARNING, highlight)

    def error(self, msg, highlight=0):
        self.log(msg, LEVEL.ERROR, highlight)

    def success(self, msg, highlight=0):
        self.log(msg, LEVEL.SUCCESS, highlight)

    def flush(self):
        if self.__writing_buffer:
            with self.__writing_lock:
                msgs, self.__writing_buffer = self.__writing_buffer, []
            self.__log_file.writelines(msgs)
            msgs.clear()
            self.__log_file.flush()

    def auto_flush(self):
        while True:
            self.flush()
            time.sleep(1)

    def silent_write(self, msgs: list):
        with self.__writing_lock:
            self.__writing_buffer.extend(msgs)

    def close(self):
        if self.__log_file.closed:
            return
        self.flush()
        self.__log_file.close()


class ConnectionDisappearedError(ConnectionError):
    pass


class ESocket:
    MAX_BUFFER_SIZE = 4096

    def __init__(self, conn: socket.socket):
        if conn is None:
            raise ValueError('Connection Can Not Be None')
        self.__conn: socket.socket = conn
        self.__buf = bytearray(self.MAX_BUFFER_SIZE)
        self.__view = memoryview(self.__buf)

    def sendall(self, data):
        self.__conn.sendall(data)

    def sendfile(self, file, offset=0, count=None):
        return self.__conn.sendfile(file, offset, count)

    def send_size(self, size: int):
        self.__conn.sendall(size_struct.pack(size))

    def recv(self, size=MAX_BUFFER_SIZE):
        size = self.__conn.recv_into(self.__buf, size)
        if size == 0:
            raise ConnectionDisappearedError('Connection Disappeared')
        return self.__view[:size], size

    def getpeername(self):
        return self.__conn.getpeername()

    def close(self):
        self.__conn.shutdown(socket.SHUT_RDWR)
        self.__conn.close()

    def settimeout(self, value: float | None):
        self.__conn.settimeout(value)

    def recv_data(self, size: int):
        # 避免粘包
        result = bytearray()
        while size:
            data, recv_size = self.recv(min(self.MAX_BUFFER_SIZE, size))
            result += data
            size -= recv_size
        return result

    def recv_size(self) -> int:
        return size_struct.unpack(self.recv_data(size_struct.size))[0]

    def send_data_with_size(self, data: bytes):
        self.send_size(len(data))
        self.__conn.sendall(data)

    def send_with_compress(self, data):
        self.send_data_with_size(lzma.compress(pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL), preset=9))

    def recv_with_decompress(self):
        return pickle.loads(lzma.decompress(self.recv_data(self.recv_size())))

    def recv_head(self) -> tuple[str, str, int]:
        """
        接收文件头
        @return: 文件(夹)名等，命令，文件大小
        """
        command, data_size, name_size = head_struct.unpack(self.recv_data(head_struct.size))
        filename = self.recv_data(name_size).decode(utf8) if name_size else ''
        return filename, command, data_size

    def send_head(self, name: str, command: int, size: int):
        """
        打包文件头 14字节的命令类型 + 8字节的文件大小 + 2字节的文件夹名长度 + 文件夹名
        @param name: 文件(夹)名等
        @param command: 命令
        @param size: 文件大小
        @return: 打包后的文件头
        """
        length = len(name := name.encode(utf8))
        self.__conn.sendall(head_struct.pack(command, size, length))
        self.__conn.sendall(name)

    # def __getattr__(self, name):
    #     return getattr(self.__conn, name)


class ThreadWithResult(threading.Thread):
    def __init__(self, func, args=()):
        super(ThreadWithResult, self).__init__()
        self.func = func
        self.args = args
        self.result = None

    def run(self):
        self.result = self.func(*self.args)

    def get_result(self):
        self.join()
        return self.result


def send_clipboard(conn: ESocket, logger: Logger, ftc=True):
    # 读取并编码剪切板的内容
    try:
        content = pyperclip.paste()
    except pyperclip.PyperclipException as e:
        logger.error(f'Get clipboard error: {e}')
        if not ftc:
            conn.send_head('', COMMAND.NULL, 0)
        return
    content_length = len(content.encode(utf8))
    if content_length == 0 or content_length > 65535:
        if content_length == 0:
            logger.warning(f'Clipboard is empty')
        else:
            logger.warning(f'Clipboard is too large({get_size(content_length)}) to send.')
        if not ftc:
            conn.send_head('', COMMAND.NULL, content_length)
        return
    # logger.info(f'Send clipboard, size: {get_size(content_length)}')
    conn.send_head(content, COMMAND.PUSH_CLIPBOARD, content_length)


def get_clipboard(conn: ESocket, logger: Logger, content=None, command=None, length=None, ftc=True):
    # 获取对方剪切板的内容
    if ftc:
        conn.send_head('', COMMAND.PULL_CLIPBOARD, 0)
        content, command, length = conn.recv_head()
    if command != COMMAND.PUSH_CLIPBOARD:
        logger.warning(f"Can not get content in clipboard for some reason.")
        return

    logger.log(f"Get clipboard, size: {get_size(length)}\n{content}")
    # 拷贝到剪切板
    try:
        pyperclip.copy(content)
    except pyperclip.PyperclipException as e:
        logger.error(f'Copy content into clipboard error: {e}')
        print(f"Content: \n{content}")


def print_color(msg, level: LEVEL = LEVEL.LOG, highlight=0):
    print(f"\r\033[{highlight}{level}m{msg}\033[0m")


def get_log_msg(msg):
    now = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    return f'{now} {threading.current_thread().name:12} {msg}'


def get_size(size, factor=1024, suffix="B"):
    """
    Scale bytes to its proper format
    e.g:
        1253656 => '1.20MB'
        1253656678 => '1.17GB'
    """
    for data_unit in ["", "K", "M", "G", "T", "P"]:
        if size < factor:
            return f"{size:.2f}{data_unit}{suffix}"
        size /= factor


def get_files_info_relative_to_basedir(base_dir: str, desc_suffix='files', position=0) -> dict[str, int]:
    """
    获取某个目录下所有文件的相对路径和文件大小，并显示进度条
    """
    result = {}
    root_abs_path = os.path.abspath(base_dir)
    queue = deque([(root_abs_path, '.')])
    processed_paths = set()
    folders = 0
    total_size = 0

    # 初始化进度显示
    pbar = tqdm(desc=f"Collecting {desc_suffix}", unit=" files", position=position, dynamic_ncols=True)
    while queue:
        current_abs_path, current_rel_path = queue.popleft()
        if current_abs_path in processed_paths:
            continue
        processed_paths.add(current_abs_path)
        folders += 1
        try:
            with os.scandir(current_abs_path) as it:
                for entry in it:
                    entry_rel_path = f"{current_rel_path}/{entry.name}" if current_rel_path != '.' else entry.name
                    if entry.is_dir(follow_symlinks=False):
                        queue.append((entry.path, entry_rel_path))
                    elif entry.is_file(follow_symlinks=False):
                        size = entry.stat().st_size
                        result[entry_rel_path] = size
                        total_size += size
                        pbar.update(1)
        except PermissionError:
            continue

    # 更新进度条描述
    pbar.set_postfix(folders=folders, size=get_size(total_size))
    pbar.close()
    return result


def format_time(time_interval):
    if time_interval < 60:
        return f"{time_interval:.2f}".rstrip("0").rstrip(".") + 's'
    units = [(86400, 'd'), (3600, 'h'), (60, 'm'), (1, 's')]
    formatted_time = ''
    for unit_time, unit_label in units:
        if time_interval >= unit_time:
            unit_count, time_interval = divmod(time_interval, unit_time)
            formatted_time += f"{int(unit_count)}{unit_label}"
    return formatted_time if formatted_time else '0s'


def parse_command(command: str) -> tuple[None, None, None] | tuple[str, str, str]:
    """
    解析形如 'command "source" "target"' 或 'command source target' 的命令字符串。
    """
    pattern = r'''
        ^\s*(\w+)\s+                          # 命令
        (?:
            "([^"]+)"                         # source - 带双引号
            |
            ([^\s"]+)                         # source - 不带引号，不能包含空格或引号
        )\s+
        (?:
            "([^"]+)"                         # target - 带双引号
            |
            ([^\s"]+)                         # target - 不带引号
        )\s*$
    '''
    match = re.match(pattern, command, re.VERBOSE)
    if not match:
        return None, None, None

    cmd = match.group(1)
    source = match.group(2) if match.group(2) is not None else match.group(3)
    target = match.group(4) if match.group(4) is not None else match.group(5)
    return cmd, source, target


def compare_files_info(source_files_info, target_files_info):
    """
    获取两个文件信息字典的差异
    """
    files_smaller_than_target, files_smaller_than_source, files_info_equal, files_not_exist_in_target = [], [], [], []
    for filename in source_files_info.keys():
        target_size = target_files_info.pop(filename, -1)
        if target_size == -1:
            files_not_exist_in_target.append(filename)
            continue
        size_diff = source_files_info[filename] - target_size
        if size_diff < 0:
            files_smaller_than_target.append(filename)
        elif size_diff == 0:
            files_info_equal.append(filename)
        else:
            files_smaller_than_source.append(filename)
    file_not_exists_in_source = list(target_files_info.keys())
    return files_smaller_than_target, files_smaller_than_source, files_info_equal, files_not_exist_in_target, file_not_exists_in_source


def print_compare_result(source: str, target: str, compare_result: tuple):
    files_smaller_than_target, files_smaller_than_source, files_info_equal, files_not_exist_in_target, file_not_exists_in_source = compare_result
    simplified_info = files_info_equal[:10] + ['(more hidden...)'] if len(
        files_info_equal) > 10 else files_info_equal
    msgs = ['\n[INFO   ] ' + get_log_msg(
        f'Compare the differences between source folder {source} and target folder {target}\n')]
    for arg in [("files exist in target but not in source: ", file_not_exists_in_source),
                ("files exist in source but not in target: ", files_not_exist_in_target),
                ("files in source smaller than target: ", files_smaller_than_target),
                ("files in target smaller than source: ", files_smaller_than_source),
                ("files name and size both equal in two sides: ", simplified_info)]:
        msgs.append(print_filename_if_exists(*arg))
    return msgs


def show_bandwidth(msg, data_size, interval, logger: Logger, level=LEVEL.SUCCESS):
    avg_bandwidth = get_size((data_size * 8 / interval) if interval != 0 else 0, factor=1000, suffix='bps')
    logger.log(f"{msg}, average bandwidth {avg_bandwidth}, takes {format_time(interval)}", level)


if windows:
    from win_set_time import set_times


def modify_file_time(logger: Logger, file_path: str, create_timestamp: float, modify_timestamp: float,
                     access_timestamp: float):
    """
    用来修改文件的相关时间属性
    :param logger: 日志对象
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
        logger.warning(f'{file_path} file time modification failed, {error}')


def makedirs(logger: Logger, dir_names, base_dir: str | PathLike):
    for dir_name in tqdm(dir_names, unit='folders', mininterval=0.1, delay=0.1, desc='Creating folders', leave=False):
        cur_dir = Path(base_dir, dir_name)
        if cur_dir.exists():
            continue
        try:
            cur_dir.mkdir(parents=True)
        except FileNotFoundError:
            logger.error(f'Failed to create folder {cur_dir}', highlight=1)


def pause_before_exit(exit_code=0):
    if package:
        os.system('pause')
    sys.exit(exit_code)


def get_files_modified_time(base_folder, file_rel_paths: list[str], desc: str = 'files') -> dict[str, float]:
    results = {}
    for file_rel_path in tqdm(file_rel_paths, unit='files', mininterval=0.2, desc=f'Get {desc} modified time',
                              leave=False):
        file_path = PurePath(base_folder, file_rel_path)
        results[file_rel_path] = os.path.getmtime(file_path)
    return results


def format_timestamp(timestamp: float):
    return time.strftime(TIME_FORMAT, time.localtime(timestamp))


class FileHash:
    @staticmethod
    def _file_digest(file, file_md5, remained_size):
        """
        计算文件的MD5值

        @param remained_size: 文件剩余需要读取的大小
        @return:
        """
        if remained_size >> SMALL_FILE_CHUNK_SIZE:
            buf = bytearray(buf_size)
            view = memoryview(buf)
            while size := file.readinto(buf):
                file_md5.update(view[:size])
        else:
            file_md5.update(file.read())
        return file_md5.hexdigest()

    @staticmethod
    def full_digest(filename):
        with open(filename, 'rb') as fp:
            return FileHash._file_digest(fp, md5(), os.path.getsize(filename))

    @staticmethod
    def fast_digest(filename):
        file_size = os.path.getsize(filename)
        with open(filename, 'rb') as fp:
            file_md5 = md5()
            if file_size >> SMALL_FILE_CHUNK_SIZE:
                tiny_buf = bytearray(32 * KB)
                tiny_view = memoryview(tiny_buf)
                tail = file_size - FILE_TAIL_SIZE
                # Large file, read in chunks and include tail
                for offset in range(48):
                    fp.seek(offset * (tail // 48))
                    size = fp.readinto(tiny_buf)
                    file_md5.update(tiny_view[:size])
                # Read the tail of the file
                fp.seek(tail)
                return FileHash._file_digest(fp, file_md5, FILE_TAIL_SIZE)
            return FileHash._file_digest(fp, file_md5, file_size)

    @staticmethod
    def parallel_calc_hash(base_folder, file_rel_paths: list[str], is_fast: bool):
        digest_func = FileHash.fast_digest if is_fast else FileHash.full_digest
        file_rel_paths = file_rel_paths.copy()
        random.shuffle(file_rel_paths)
        results = {}
        with ThreadPoolExecutor(max_workers=cpu_count) as executor:
            future_to_file = {executor.submit(digest_func, PurePath(base_folder, rel_path)): rel_path for rel_path in
                              file_rel_paths}
            for future in tqdm(as_completed(future_to_file), total=len(file_rel_paths), unit='files', mininterval=0.2,
                               desc=f'{"fast" if is_fast else "full"} hash calc', leave=False):
                filename = future_to_file[future]
                digest_value = future.result()
                results[filename] = digest_value
        return results


def shorten_path(path: str, max_width: float) -> str:
    return path[:int((max_width - 3) / 3)] + '...' + path[-2 * int((max_width - 3) / 3):] if len(
        path) > max_width else path + ' ' * (int(max_width) - len(path))


def print_filename_if_exists(prompt, filename_list, print_if_empty=True):
    msg = [prompt]
    if filename_list:
        msg.extend([('\t' + file_name) for file_name in filename_list])
    else:
        msg.append('\tNone')
    if filename_list or print_if_empty:
        print('\n'.join(msg))
    msg.append('')
    return '\n'.join(msg)


if __name__ == '__main__':
    print(get_files_info_relative_to_basedir(input('>>> ')))
