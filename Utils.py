import lzma
import os
import pickle
import socket
import threading
import time
from hashlib import md5
from pathlib import PurePath
from datetime import datetime
from typing import TextIO
from constants import *
from configparser import ConfigParser, NoOptionError, NoSectionError

# 解决win10的cmd中直接使用转义序列失效问题
if windows:
    os.system("")
    import pyperclip


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
    content = pyperclip.paste()
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
        logger.warning(f"Clipboard is empty or too large({get_size(length)}) to get.")
        return

    logger.log(f"Get clipboard, size: {get_size(length)}\n{content}")
    # 拷贝到剪切板
    pyperclip.copy(content)


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


def get_files_info_relative_to_basedir(base_dir):
    return {(abspath := PurePath(path, file)).relative_to(base_dir).as_posix(): os.path.getsize(abspath)
            for path, _, file_list in os.walk(base_dir) for file in file_list}


def format_time(time_interval):
    units = [(86400, 'd'), (3600, 'h'), (60, 'm'), (1, 's')]
    formatted_time = ''
    for unit_time, unit_label in units:
        if time_interval >= unit_time:
            unit_count, time_interval = divmod(time_interval, unit_time)
            formatted_time += f"{int(unit_count)}{unit_label}"
    return formatted_time if formatted_time else '0s'


def show_bandwidth(msg, data_size, interval, logger: Logger):
    avg_bandwidth = get_size((data_size * 8 / interval) if interval != 0 else 0, factor=1000, suffix='bps')
    logger.success(f"{msg}, average bandwidth {avg_bandwidth}, takes {format_time(interval)}")


def pause_before_exit(exit_code=0):
    if package:
        os.system('pause')
    sys.exit(exit_code)


def get_file_md5(filename):
    view = memoryview(buf := bytearray(buf_size))
    file_md5 = md5()
    with open(filename, 'rb') as fp:
        while size := fp.readinto(buf):
            file_md5.update(view[:size])
    return file_md5.hexdigest()


def shorten_path(path: str, max_width: float) -> str:
    return path[:int((max_width - 3) / 3)] + '...' + path[-2 * int((max_width - 3) / 3):] if len(
        path) > max_width else path + ' ' * (int(max_width) - len(path))


# 配置文件相关
class Config:
    config_file: Final[str] = 'config'

    @staticmethod
    def generate_config():
        config_parser = ConfigParser()
        cur_section = ''
        for name, item in ConfigOption.__members__.items():
            if name.startswith('section'):
                cur_section = item
                config_parser.add_section(cur_section)
            else:
                config_parser.set(cur_section, *item.name_and_value)
        try:
            with open(Config.config_file, 'w', encoding=utf8) as f:
                config_parser.write(f)
        except PermissionError as error:
            print_color(f'Failed to create the config file, {error}', level=LEVEL.ERROR, highlight=1)
            pause_before_exit(-1)

    @staticmethod
    def load_config():
        if not (exist := os.path.exists(Config.config_file)):
            # 生成配置文件
            Config.generate_config()
        cnf = ConfigParser()
        cnf.read(Config.config_file, encoding=utf8)
        try:
            path_name = ConfigOption.windows_default_path.name if windows else ConfigOption.linux_default_path.name
            default_path = cnf.get(ConfigOption.section_Main, path_name)
            log_dir_name = (ConfigOption.windows_log_dir if windows else ConfigOption.linux_log_dir).name
            if not os.path.exists(log_dir := os.path.expanduser(cnf.get(ConfigOption.section_Log, log_dir_name))):
                os.makedirs(log_dir)
            log_file_archive_count = cnf.getint(ConfigOption.section_Log, ConfigOption.log_file_archive_count.name)
            log_file_archive_size = cnf.getint(ConfigOption.section_Log, ConfigOption.log_file_archive_size.name)
            server_port = cnf.getint(ConfigOption.section_Port, ConfigOption.server_port.name)
            signal_port = cnf.getint(ConfigOption.section_Port, ConfigOption.signal_port.name)
            # 原先配置不存在则删除生成的配置文件
            if not exist:
                os.remove(Config.config_file)
        except OSError as e:
            print_color(f'Failed to create the log folder, {e}', level=LEVEL.ERROR, highlight=1)
            pause_before_exit(-1)
        except (NoOptionError, NoSectionError) as e:
            print_color(f'{e}', level=LEVEL.ERROR, highlight=1)
            pause_before_exit(-1)
        except ValueError as e:
            print_color(f'Configuration error, {e}', level=LEVEL.ERROR, highlight=1)
            pause_before_exit(-1)
        else:
            return Configration(default_path=default_path, log_dir=log_dir, server_port=server_port,
                                log_file_archive_count=log_file_archive_count, signal_port=signal_port,
                                log_file_archive_size=log_file_archive_size)


# 加载配置
config: Final[Configration] = Config.load_config()

if __name__ == '__main__':
    print(get_files_info_relative_to_basedir(input('>>> ')))
