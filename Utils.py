import os
import re
import signal
import socket
import sys
import threading
import struct
import time
import tarfile
from platform import system
from hashlib import md5
from configparser import ConfigParser, NoOptionError, NoSectionError
from dataclasses import dataclass
from datetime import datetime
from enum import IntFlag, StrEnum
from typing import TextIO, Final, Callable
from send2trash import send2trash
from sys_info import get_size

# 获取当前平台
platform_: Final[str] = system()
WINDOWS: Final[str] = 'Windows'
LINUX: Final[str] = 'Linux'
MACOS: Final[str] = 'Macos'
# 解决win10的cmd中直接使用转义序列失效问题
if platform_ == WINDOWS:
    os.system("")
    import pyperclip


# 配置实体类
@dataclass
class Configration:
    default_path: str
    cert_dir: str
    log_dir: str
    log_file_archive_count: int
    log_file_archive_size: int
    server_port: int
    server_signal_port: int
    client_signal_port: int


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
    def __init__(self, log_file_path: str):
        self.log_file = open(log_file_path, 'a', encoding=utf8)
        self.__log_lock = threading.Lock()
        self.__writing_lock = threading.Lock()
        self.__writing_buffer: list[str] = []
        threading.Thread(target=self.auto_flush, daemon=True).start()
        self.log('本次日志文件存放位置为: ' + os.path.normcase(log_file_path))

    def log(self, msg, level: LEVEL = LEVEL.LOG, highlight=0):
        msg = get_log_msg(msg)
        with self.__log_lock:
            print(f"\033[{highlight}{level}m{msg}\033[0m")
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
            self.log_file.writelines(msgs)
            msgs.clear()
            self.log_file.flush()

    def auto_flush(self):
        while True:
            self.flush()
            time.sleep(1)

    def close(self):
        if self.log_file.closed:
            return
        if self.__writing_buffer:
            self.log_file.writelines(self.__writing_buffer)
        self.log_file.close()


def receive_data(connection: socket.socket, size: int):
    # 避免粘包
    result = b''
    while size > 0:
        data: bytes = connection.recv(min(size, unit))
        size -= len(data)
        result += data
    return result


def send_clipboard(conn, logger: Logger, FTC=True):
    # 读取并编码剪切板的内容
    content = pyperclip.paste().encode()
    # 没有内容则不发送
    content_length = len(content)
    if content_length == 0:
        if not FTC:
            file_head = struct.pack(FMT.head_fmt, b'', b'', 0)
            conn.send(file_head)
        return

    logger.info(f'发送剪切板的内容，大小为 {get_size(content_length)}')
    # 需要发送的内容较小则一趟发送
    if content_length <= FMT.filename_fmt.size:
        file_head = struct.pack(FMT.head_fmt, content, PUSH_CLIPBOARD.encode(), 0)
        conn.send(file_head)
    else:
        # 较大则多趟发送
        file_head = struct.pack(FMT.head_fmt, b'', PUSH_CLIPBOARD.encode(), content_length)
        conn.send(file_head)
        conn.send(content)


def get_clipboard(conn, logger: Logger, file_head=None, FTC=True):
    # 获取对方剪切板的内容
    if FTC:
        file_head = struct.pack(FMT.head_fmt, b'', PULL_CLIPBOARD.encode(), 0)
        conn.send(file_head)
        file_head = receive_data(conn, FMT.head_fmt.size)
    content, command, file_size, = struct.unpack(FMT.head_fmt, file_head)
    if command.decode() != PUSH_CLIPBOARD:
        logger.warning('对方剪切板为空')
        return
        # 对方发送的内容较多则继续接收
    if file_size != 0:
        content = receive_data(conn, file_size)
    logger.info('获取对方剪切板的内容，大小为 {}'.format(get_size(len(content.strip(b"\00")))))
    content = content.decode(utf8).strip('\00')
    print(content)
    # 拷贝到剪切板
    pyperclip.copy(content)


def calcu_size(bytes, factor=1024):
    """
    计算文件大小所对应的合适的单位
    :param bytes: 原始文件大小，单位byte
    :param factor: 计算因子
    :return:返回合适的两个单位及对应的大小
    """
    scale = ["", "K", "M", "G", "T", "P"]
    for position, data_unit in enumerate(scale):
        if bytes < factor:
            return f"{bytes:.2f}{data_unit}B", f"{bytes * factor:.2f}{scale[position - 1]}B" if position > 0 else ''
        bytes /= factor


def print_color(msg, level: LEVEL = LEVEL.LOG, highlight=0):
    print(f"\033[{highlight}{level}m{msg}\033[0m")


def get_log_msg(msg):
    now = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    return f'{now} {threading.current_thread().name:12} {msg}'


def get_relative_filename_from_basedir(base_dir):
    results = {}
    basedir_length = len(base_dir) + 1
    for path, _, file_list in os.walk(base_dir):
        for file in file_list:
            # 将文件路径风格统一至Linux
            real_path = os.path.normcase(os.path.join(path, file)).replace(os.path.sep, '/')
            results.update({real_path[basedir_length:]: os.stat(real_path).st_size})
    return results


def get_dir_file_name(filepath):
    """
    获取某文件路径下的所有文件夹和文件的相对路径
    :param filepath: 文件路径
    :return :返回该文件路径下的所有文件夹、文件的相对路径
    """
    all_dir_name = set()
    all_file_name = []
    # 获取上一级文件夹名称
    back_dir = os.path.dirname(filepath)
    for path, _, file_list in os.walk(filepath):
        # 获取相对路径
        path = os.path.relpath(path, back_dir)
        all_dir_name.add(path)
        # 去除重复的路径，防止多次创建，降低效率
        all_dir_name.discard(os.path.dirname(path))
        all_file_name += [os.path.join(path, file) for file in file_list]
    return all_dir_name, all_file_name


def get_ip_and_hostname() -> (str, str):
    st = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        st.connect(('10.255.255.255', 1))
        ip = st.getsockname()[0]
    except OSError:
        ip = '127.0.0.1'
    finally:
        st.close()
    return ip, socket.gethostname()


def get_file_md5(filename):
    hash = md5()
    with open(filename, 'rb') as fp:
        while data := fp.read(unit):
            hash.update(data)
    return hash.hexdigest()


def handle_ctrl_event(logger: Logger):
    # determine platform, to fix ^c doesn't work on Windows
    if platform_ != WINDOWS:
        return

    def call_back(ctrl_type):
        if ctrl_type in (signal.CTRL_C_EVENT, signal.CTRL_BREAK_EVENT):
            logger.close()
            os.kill(os.getpid(), signal.CTRL_BREAK_EVENT)

    from win32api import SetConsoleCtrlHandler
    SetConsoleCtrlHandler(call_back, 1)


def extra_print2file(print_func: Callable, args: tuple, file: TextIO):
    """
    将print的内容同时输出到控制台和文件中
    """
    print_func(*args)
    # 将输出重定向到文件
    original_out, sys.stdout = sys.stdout, file
    print_func(*args)
    # 恢复原来的输出
    sys.stdout = original_out
    file.flush()


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


def compress_log_files(base_dir, log_type, logger: Logger):
    """
    压缩日志文件

    @param base_dir: 日志文件所在的目录
    @param log_type: 日志文件的类型：client 或 server
    @param logger: 打印日志对象
    @return:
    """
    appendix = log_type + '.log'
    # 必须以日期开头的文件
    pattern = r'^\d{4}_\d{2}_\d{2}'
    if not os.path.exists(base_dir):
        return
    for path, _, file_list in os.walk(base_dir):
        # 获取非今天的FTC或FTS日志文件名
        matching_files = [file for file in file_list if re.match(pattern, file) and
                          file.endswith(appendix) and not file.startswith(datetime.now().strftime('%Y_%m_%d'))]
        if not matching_files or len(matching_files) == 0:
            return
        # 当日志文件数大于10个时归档
        file_list = matching_files if len(matching_files) >= config.log_file_archive_count else None
        total_size = sum(
            os.stat(real_path).st_size for real_path in (os.path.join(path, file) for file in matching_files))
        if not file_list:
            # 日志文件小于十个但是总体积大于50MB也进行归档处理
            file_list = matching_files if total_size >= config.log_file_archive_size else None
            if not file_list:
                return
        dates = [datetime.strptime(file[0:10], '%Y_%m_%d') for file in matching_files]
        max_date = max(dates).strftime('%Y%m%d')
        min_date = min(dates).strftime('%Y%m%d')
        logger.info(
            f'开始对 {min_date} - {max_date} 时间范围内的 {log_type.upper()} 日志进行归档, 总计大小: {get_size(total_size)}')
        # 压缩后的输出文件名
        output_file = f'{min_date}_{max_date}.{log_type}.tar.gz'
        output_file = os.path.join(base_dir, output_file).replace('/', os.path.sep)
        # 创建一个 tar 归档文件对象
        with tarfile.open(os.path.join(base_dir, output_file), 'w:gz') as tar:
            # 逐个添加文件到归档文件中
            for file_name in file_list:
                tar.add(os.path.join(base_dir, file_name), arcname=file_name)
        # 若压缩文件完整则将日志文件移入回收站
        if tarfile.is_tarfile(output_file):
            for file_name in file_list:
                try:
                    send2trash(os.path.join(base_dir, file_name).replace('/', os.path.sep))
                except Exception as e:
                    logger.warning(f'{file_name}送往回收站失败，执行删除{e}')
                    os.remove(os.path.join(base_dir, file_name))

        logger.success(f'日志文件归档完成: {output_file}，压缩后的文件大小: {get_size(os.stat(output_file).st_size)}')
        # 不进行文件夹递归
        return


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


# 打包控制变量，用于将程序打包为exe后防止直接退出控制台
# Packaging control variable,
# used to prevent the console from exiting directly after the program is packaged as exe
packaging = getattr(sys, 'frozen', False)

# 命令类型
SEND_FILE: Final[str] = "send_file"
SEND_DIR: Final[str] = "send_dir"
SEND_FILES_IN_DIR: Final[str] = "send_files_dir"
COMPARE_DIR: Final[str] = "compare_dir"
COMMAND: Final[str] = 'command'
SYSINFO: Final[str] = 'sysinfo'
FINISH: Final[str] = 'finish'
SPEEDTEST: Final[str] = 'speedtest'
BEFORE_WORKING: Final[str] = 'before_working'
CLOSE: Final[str] = 'close'
CLIP: Final[str] = 'clip'
HISTORY: Final[str] = 'history'
COMPARE: Final[str] = "compare"
PUSH_CLIPBOARD: Final[str] = 'push_clipboard'
PULL_CLIPBOARD: Final[str] = 'pull_clipboard'

# 其他常量
FAIL: Final[str] = 'fail'
PUSH: Final[str] = 'push'
PULL: Final[str] = 'pull'
GET: Final[str] = 'get'
SEND: Final[str] = 'send'
OVER: Final[bytes] = b'\00'
DIRISCORRECT: Final[str] = "DIC"
utf8: Final[str] = 'utf-8'
unit: Final[int] = 1024 * 1024  # 1MB
commands: Final[list] = [SYSINFO, COMPARE, SPEEDTEST, HISTORY, CLIP, PUSH, PULL, SEND, GET]


class FMT(StrEnum):
    filename_fmt = '800s'
    head_fmt = f'>{filename_fmt}14sQ'  # 大端对齐，800位文件（夹）名，14位表示命令类型，Q为 8字节 unsigned 整数，表示文件大小 0~2^64-1
    size_fmt = 'q'
    file_details_fmt = 'ddd'

    @property
    def size(self):
        return struct.calcsize(self)


class Control(IntFlag):
    CONTINUE = 0
    CANCEL = -1
    TOOLONG = -2


class ConfigOption(StrEnum):
    """
    配置文件的Option的枚举类
    name为配置项名称，value为配置的默认值
    """
    windows_default_path = '~/Desktop'
    linux_default_path = '~/FileTransferTool/FileRecv'
    cert_dir = './cert'
    windows_log_dir = 'C:/ProgramData/logs'
    linux_log_dir = '~/FileTransferTool/logs'
    log_file_archive_count = '10'
    log_file_archive_size = '52428800'
    server_port = '2023'
    client_signal_port = '2022'
    server_signal_port = '2021'

    @property
    def optionAndValue(self):
        return self.name, self


# 配置文件相关
class Config:
    config_file: Final[str] = 'config.txt'

    section_Main: Final[str] = 'Main'
    section_Log: Final[str] = 'Log'
    section_Port: Final[str] = 'Port'

    @staticmethod
    def generate_config():
        config = ConfigParser()
        config.add_section(Config.section_Main)
        if platform_ == WINDOWS:
            config.set(Config.section_Main, *ConfigOption.windows_default_path.optionAndValue)
        elif platform_ == LINUX:
            config.set(Config.section_Main, *ConfigOption.linux_default_path.optionAndValue)
        config.set(Config.section_Main, *ConfigOption.cert_dir.optionAndValue)
        config.add_section(Config.section_Log)
        config.set(Config.section_Log, *ConfigOption.windows_log_dir.optionAndValue)
        config.set(Config.section_Log, *ConfigOption.linux_log_dir.optionAndValue)
        config.set(Config.section_Log, *ConfigOption.log_file_archive_count.optionAndValue)
        config.set(Config.section_Log, *ConfigOption.log_file_archive_size.optionAndValue)
        config.add_section(Config.section_Port)
        config.set(Config.section_Port, *ConfigOption.server_port.optionAndValue)
        config.set(Config.section_Port, *ConfigOption.server_signal_port.optionAndValue)
        config.set(Config.section_Port, *ConfigOption.client_signal_port.optionAndValue)
        with open(Config.config_file, 'w', encoding=utf8) as f:
            config.write(f)

    @staticmethod
    def load_config():
        config = ConfigParser()
        config.read(Config.config_file, encoding=utf8)
        try:
            default_path = config.get(Config.section_Main,
                                      ConfigOption.windows_default_path.name) if platform_ == WINDOWS else config.get(
                Config.section_Main, ConfigOption.linux_default_path.name)
            cert_dir = config.get(Config.section_Main, ConfigOption.cert_dir.name)
            if not os.path.exists(cert_dir):
                cert_dir = f'{os.path.dirname(os.path.abspath(__file__))}/cert'

            if not os.path.exists(cert_dir):
                print_color(
                    '未找到证书文件，默认位置为"./cert"文件夹中。\n'
                    'The certificate file was not found, the default location is in the "./cert" folder.\n',
                    level=LEVEL.ERROR, highlight=1)
                if packaging:
                    os.system('pause')
                sys.exit(-2)

            # 默认为Windows平台
            log_dir = os.path.expanduser(config.get(Config.section_Log, ConfigOption.windows_log_dir.name))
            # Linux 的日志存放位置
            if platform_ == LINUX:
                log_dir = os.path.expanduser(config.get(Config.section_Log, ConfigOption.linux_log_dir.name))
            if not os.path.exists(log_dir):
                try:
                    os.makedirs(log_dir)
                except Exception as e:
                    print_color(f'日志文件夹 "{log_dir}" 创建失败 {e}', level=LEVEL.ERROR, highlight=1)
                    sys.exit(-1)

            log_file_archive_count = config.getint(Config.section_Log, ConfigOption.log_file_archive_count.name)
            log_file_archive_size = config.getint(Config.section_Log, ConfigOption.log_file_archive_size.name)
            server_port = config.getint(Config.section_Port, ConfigOption.server_port.name)
            server_signal_port = config.getint(Config.section_Port, ConfigOption.server_signal_port.name)
            client_signal_port = config.getint(Config.section_Port, ConfigOption.client_signal_port.name)
        except (NoOptionError, NoSectionError) as e:
            print_color(f'{e}', level=LEVEL.ERROR, highlight=1)
            sys.exit(-1)
        except ValueError as e:
            print_color(f'配置错误 {e}', level=LEVEL.ERROR, highlight=1)
            sys.exit(-1)
        return Configration(default_path=default_path, cert_dir=cert_dir, log_dir=log_dir,
                            log_file_archive_count=log_file_archive_count, log_file_archive_size=log_file_archive_size,
                            server_port=server_port, server_signal_port=server_signal_port,
                            client_signal_port=client_signal_port)


if not os.path.exists(Config.config_file):
    print_color(
        '未找到配置文件，采用默认配置\nThe configuration file was not found, using the default configuration.\n',
        level=LEVEL.WARNING, highlight=1)
    # 生成配置文件
    Config.generate_config()

# 加载配置
config: Final[Configration] = Config.load_config()

if __name__ == '__main__':
    print(get_relative_filename_from_basedir(input('>>> ')))
