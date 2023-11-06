import ipaddress
import lzma
import os
import pickle
import socket
import sys
import threading
import time
import psutil
from hashlib import md5
from struct import Struct
from platform import system
from pathlib import PurePath
from sys_info import get_size
from datetime import datetime
from typing import TextIO, Final
from dataclasses import dataclass
from enum import StrEnum, IntEnum, auto
from configparser import ConfigParser, NoOptionError, NoSectionError

# 获取当前平台
platform_: Final[str] = system()
WINDOWS: Final[str] = 'Windows'
LINUX: Final[str] = 'Linux'
MACOS: Final[str] = 'Macos'
# 解决win10的cmd中直接使用转义序列失效问题
windows = platform_ == WINDOWS
if windows:
    os.system("")
    import pyperclip


# 配置实体类
@dataclass
class Configration:
    default_path: str
    log_dir: str
    log_file_archive_count: int
    log_file_archive_size: int
    server_port: int
    signal_port: int


class LEVEL(StrEnum):
    """
    日志打印等级的枚举类，值为等级对应的颜色代码
    """
    LOG = ''
    INFO = ';34'
    WARNING = ';33'
    SUCCESS = ';32'
    ERROR = ';31'


# 日志类，简化日志打印
class Logger:
    def __init__(self, log_file_path: PurePath):
        self.__log_file = open(log_file_path, 'a', encoding=utf8)
        self.__log_lock = threading.Lock()
        self.__writing_lock = threading.Lock()
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
        self.__conn = conn

    def sendall(self, data: bytes):
        self.__conn.sendall(data)

    def send_size(self, size: int):
        self.__conn.sendall(size_struct.pack(size))

    def recv(self, size=MAX_BUFFER_SIZE):
        data = self.__conn.recv(size)
        if not data:
            raise ConnectionDisappearedError('Connection Disappeared')
        return data

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
            size -= len(data := self.recv(min(self.MAX_BUFFER_SIZE, size)))
            result += data
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


def calcu_size(bytes, factor=1024):
    """
    计算文件大小所对应的合适的单位
    :param bytes: 原始文件大小，单位 byte
    :param factor: 计算因子
    :return:返回合适的两个单位及对应的大小
    """
    scale = ["", "K", "M", "G", "T", "P"]
    for position, data_unit in enumerate(scale):
        if bytes < factor:
            return f"{bytes:.2f}{data_unit}B", f"{bytes * factor:.2f}{scale[position - 1]}B" if position > 0 else ''
        bytes /= factor


def print_color(msg, level: LEVEL = LEVEL.LOG, highlight=0):
    print(f"\r\033[{highlight}{level}m{msg}\033[0m")


def get_log_msg(msg):
    now = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    return f'{now} {threading.current_thread().name:12} {msg}'


def get_files_info_relative_to_basedir(base_dir):
    return {(abspath := PurePath(path, file)).relative_to(base_dir).as_posix(): os.path.getsize(abspath)
            for path, _, file_list in os.walk(base_dir) for file in file_list}


def get_ip() -> str:
    st = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        st.connect(('10.255.255.255', 1))
        ip = st.getsockname()[0]
    except OSError:
        ip = '127.0.0.1'
    finally:
        st.close()
    return ip


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


def broadcast_to_all_interfaces(sk: socket.socket, content: bytes):
    interface_stats = psutil.net_if_stats()
    for interface, addresses in psutil.net_if_addrs().items():
        if not interface_stats[interface].isup:
            continue
        for addr in addresses:
            if addr.family == socket.AF_INET and addr.netmask:
                broadcast_address = ipaddress.IPv4Network(f"{addr.address}/{addr.netmask}",
                                                          strict=False).broadcast_address
                if broadcast_address.is_loopback:
                    continue
                try:
                    sk.sendto(content, (str(broadcast_address), config.signal_port))
                except OSError:
                    pass


def get_file_md5(filename):
    file_hash = md5()
    with open(filename, 'rb') as fp:
        while data := fp.read(unit):
            file_hash.update(data)
    return file_hash.hexdigest()


def openfile_with_retires(filename: str, mode: str, max_retries: int = 50) -> TextIO | None:
    """
    多次重试创建文件，用于解决文件路径过长时
    Windows容易无法创建文件的问题

    @param filename: 需要打开的文件的绝对路径
    @param mode: 打开模式
    @param max_retries: 最大重试数
    @return: 文件指针
    """
    file, retries = None, 0
    while not file and retries < max_retries:
        try:
            file = open(filename, mode)
        except FileNotFoundError:
            retries += 1
    return file


def get_hostname_by_ip(ip):
    hostname = 'unknown'
    try:
        hostname = socket.gethostbyaddr(ip)[0]
    finally:
        return hostname


def shorten_path(path: str, max_width: float) -> str:
    return path[:int((max_width - 3) / 3)] + '...' + path[-2 * int((max_width - 3) / 3):] if len(
        path) > max_width else path + ' ' * (int(max_width) - len(path))

    # def shorten_string(string: str, width):
    #     if width <= 0:
    #         return '...'
    #     if len(string) - width <= 0:
    #         return string
    #     margin = int(width / 2)
    #     return '...' if margin == 0 else string[0:margin] + '..' + string[-margin:]
    #
    # parts: list = path.split(os.path.sep)
    # if len(path) <= max_width or len(parts) == 1:
    #     return shorten_string(path, max_width)
    # path_sep = '...' + os.path.sep
    # base = parts.pop()
    # if len(base) - 4 >= max_width:
    #     return path_sep + shorten_string(base, len(base) - 4)
    # avg_width = int((max_width - len(base)) / len(parts))
    # if avg_width < 2:
    #     return shorten_string(os.path.sep.join(parts), max_width - len(base)) + os.path.sep + base
    # shortened_parts = [shorten_string(part, avg_width) for part in parts]
    # shortened_parts.append(base)
    # return os.path.sep.join(shortened_parts)


# 命令类型
class COMMAND(IntEnum):
    NULL = auto()
    SEND_FILES_IN_FOLDER = auto()
    SEND_SMALL_FILE = auto()
    SEND_LARGE_FILE = auto()
    COMPARE_FOLDER = auto()
    EXECUTE_COMMAND = auto()
    EXECUTE_RESULT = auto()
    SYSINFO = auto()
    SPEEDTEST = auto()
    BEFORE_WORKING = auto()
    CLOSE = auto()
    HISTORY = auto()
    COMPARE = auto()
    CHAT = auto()
    FINISH = auto()
    PUSH_CLIPBOARD = auto()
    PULL_CLIPBOARD = auto()


# 其他常量
FAIL: Final[str] = 'fail'
GET: Final[str] = 'get'
SEND: Final[str] = 'send'
OVER: Final[bytes] = b'\00'
utf8: Final[str] = 'utf-8'
unit: Final[int] = 1024 * 1024 * 2  # 2MB
sysinfo = 'sysinfo'
compare = "compare"
speedtest = 'speedtest'
setbase = 'setbase'
history = 'history'
say = 'say'
clipboard_send = 'send clipboard'
clipboard_get = 'get clipboard'
commands: Final[list] = [sysinfo, compare, speedtest, history, clipboard_send, clipboard_get, setbase, say]

# Struct 对象
# B为 1字节 unsigned char，0~127
# Q为 8字节 unsigned long long， 0~2^64-1
# q为 8字节 long long， -2^63~2^63-1
# H为 2字节 unsigned short， 0~65535
# d为 8字节 double， 2.3E-308~1.7E+308
head_struct = Struct('>BQH')
size_struct = Struct('q')
times_struct = Struct('ddd')


class CONTROL(IntEnum):
    CONTINUE = 0
    CANCEL = -1
    FAIL2OPEN = -2


class ConfigOption(StrEnum):
    """
    配置文件的Option的枚举类
    name为配置项名称，value为配置的默认值
    """
    section_Main = 'Main'
    windows_default_path = '~/Desktop'
    linux_default_path = '~/FileTransferTool/FileRecv'

    section_Log = 'Log'
    windows_log_dir = 'C:/ProgramData/logs'
    linux_log_dir = '~/FileTransferTool/logs'
    log_file_archive_count = '10'
    log_file_archive_size = '52428800'

    section_Port = 'Port'
    server_port = '2023'
    signal_port = '2022'

    @property
    def name_and_value(self):
        return self.name, self


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
            sys.exit(-1)

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
            sys.exit(-1)
        except (NoOptionError, NoSectionError) as e:
            print_color(f'{e}', level=LEVEL.ERROR, highlight=1)
            sys.exit(-1)
        except ValueError as e:
            print_color(f'Configuration error, {e}', level=LEVEL.ERROR, highlight=1)
            sys.exit(-1)
        return Configration(default_path=default_path, log_dir=log_dir, server_port=server_port,
                            log_file_archive_count=log_file_archive_count, log_file_archive_size=log_file_archive_size,
                            signal_port=signal_port)


# 加载配置
config: Final[Configration] = Config.load_config()

if __name__ == '__main__':
    print(get_files_info_relative_to_basedir(input('>>> ')))
