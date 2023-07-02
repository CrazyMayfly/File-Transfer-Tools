import hashlib
import os
import platform
import re
import signal
import struct
import sys
import tarfile
import threading
import pyperclip
from configparser import ConfigParser, NoOptionError, NoSectionError
from dataclasses import dataclass
from datetime import datetime
from send2trash import send2trash
from sys_info import get_size

# 获取当前平台
platform_ = platform.system()
WINDOWS = 'Windows'
LINUX = 'Linux'
MACOS = 'Macos'
# 解决win10的cmd中直接使用转义序列失效问题
if platform_ == WINDOWS:
    os.system("")


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


def receive_data(connection, size):
    # 避免粘包
    result = b''
    while size > 0:
        data = connection.recv(min(size, unit))
        size -= len(data)
        result += data
    return result


def send_clipboard(conn, log, FTC=True):
    # 读取并编码剪切板的内容
    content = pyperclip.paste().encode()
    # 没有内容则不发送
    content_length = len(content)
    if content_length == 0:
        if not FTC:
            filehead = struct.pack(fmt, b'', b'', 0)
            conn.send(filehead)
        return

    log(f'发送剪切板的内容，大小为 {get_size(content_length)}', color='blue')
    # 需要发送的内容较小则一趟发送
    if content_length <= filename_size:
        filehead = struct.pack(fmt, content, PUSH_CLIPBOARD.encode(), 0)
        conn.send(filehead)
    else:
        # 较大则多趟发送
        filehead = struct.pack(fmt, b'', PUSH_CLIPBOARD.encode(), content_length)
        conn.send(filehead)
        conn.send(content)


def get_clipboard(conn, log, filehead=None, FTC=True):
    # 获取对方剪切板的内容
    if FTC:
        filehead = struct.pack(fmt, b'', PULL_CLIPBOARD.encode(), 0)
        conn.send(filehead)
        filehead = receive_data(conn, fileinfo_size)
    content, command, filesize, = struct.unpack(fmt, filehead)
    if command.decode() != PUSH_CLIPBOARD:
        log('对方剪切板为空', color='yellow')
        return
        # 对方发送的内容较多则继续接收
    if filesize != 0:
        content = receive_data(conn, filesize)
    log('获取对方剪切板的内容，大小为 {}'.format(get_size(len(content.strip(b"\00")))), color='blue')
    content = content.decode('UTF-8').strip('\00')
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


def print_color(msg, color='white', highlight=0):
    print("\033[{}{}m{}\033[0m".format(highlight, color_dict[color], msg))


def get_log_msg(msg):
    t = threading.current_thread()
    now = datetime.now().strftime('%H:%M:%S.%f')[0:-3]
    return f'{now} {t.ident:5} {t.name:10} {msg}'


def get_relative_filename_from_basedir(base_dir):
    results = {}
    basedir_length = len(base_dir) + 1
    for path, dir_list, file_list in os.walk(base_dir):
        for file in file_list:
            # 将文件路径风格统一至Linux
            real_path = os.path.join(path, file).replace(os.path.sep, '/')
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
    for path, dir_list, file_list in os.walk(filepath):
        # 获取相对路径
        path = os.path.relpath(path, back_dir)
        all_dir_name.add(path)
        # 去除重复的路径，防止多次创建，降低效率
        all_dir_name.discard(os.path.dirname(path))
        all_file_name += [os.path.join(path, file) for file in file_list]
    return all_dir_name, all_file_name


def get_file_md5(filename):
    if not os.path.exists(filename):
        print(f"{filename} 不存在")
        return None
    md5 = hashlib.md5()
    with open(filename, 'rb') as fp:
        data = fp.read(unit)
        while data:
            md5.update(data)
            data = fp.read(unit)
    return md5.hexdigest()


def handle_ctrl_event():
    # determine platform, to fix ^c doesn't work on Windows
    if platform_ == WINDOWS:
        from win32api import SetConsoleCtrlHandler
        SetConsoleCtrlHandler(lambda ctrl_type: os.kill(os.getpid(), signal.CTRL_BREAK_EVENT)
        if ctrl_type in (signal.CTRL_C_EVENT, signal.CTRL_BREAK_EVENT)
        else None, 1)


def compress_log_files(base_dir, log_type, log):
    """
    压缩日志文件

    @param base_dir: 日志文件所在的目录
    @param log_type: 日志文件的类型：client 或 server
    @param log: 打印日志方法
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
        log(f'开始对 {min_date} - {max_date} 时间范围内的 {log_type.upper()} 日志进行归档, 总计大小: {get_size(total_size)}',
            color='blue')
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
                    log(f'{file_name}送往回收站失败，执行删除{e}', color='yellow')
                    os.remove(os.path.join(base_dir, file_name))

        log(f'日志文件归档完成: {output_file}，压缩后的文件大小: {get_size(os.stat(output_file).st_size)}',
            color='green')
        # 不进行文件夹递归
        return


def generate_config():
    config = ConfigParser()
    config.add_section(section_Main)
    if platform_ == WINDOWS:
        config.set(section_Main, option_windows_default_path, '~/Desktop')
    elif platform_ == LINUX:
        config.set(section_Main, option_linux_default_path, '~/FileTransferTool/FileRecv')
    config.set(section_Main, option_cert_dir, './cert')
    config.add_section(section_Log)
    config.set(section_Log, option_windows_log_dir, 'C:/ProgramData/logs')
    config.set(section_Log, option_linux_log_dir, '~/FileTransferTool/logs')
    config.set(section_Log, option_log_file_archive_count, '10')
    config.set(section_Log, option_log_file_archive_size, '52428800')
    config.add_section(section_Port)
    config.set(section_Port, option_server_port, '2023')
    config.set(section_Port, option_server_signal_port, '2021')
    config.set(section_Port, option_client_signal_port, '2022')
    with open(config_file, 'w', encoding='UTF-8') as f:
        config.write(f)


def load_config():
    config = ConfigParser()
    config.read(config_file, encoding='UTF-8')
    try:
        default_path = config.get(section_Main, option_windows_default_path) if platform_ == WINDOWS else config.get(
            section_Main, option_linux_default_path)
        cert_dir = config.get(section_Main, option_cert_dir)
        if not os.path.exists(cert_dir):
            cert_dir = f'{os.path.dirname(os.path.abspath(__file__))}/cert'

        if not os.path.exists(cert_dir):
            print_color(
                '未找到证书文件，默认位置为"./cert"文件夹中。\n'
                'The certificate file was not found, the default location is in the "./cert" folder.\n',
                color='red', highlight=1)
            if packaging:
                os.system('pause')
            sys.exit(-2)

        # 默认为Windows平台
        log_dir = os.path.expanduser(config.get(section_Log, option_windows_log_dir))
        # Linux 的日志存放位置
        if platform_ == LINUX:
            log_dir = os.path.expanduser(config.get(section_Log, option_linux_log_dir))
        if not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir)
            except Exception as e:
                print_color(f'日志文件夹 "{log_dir}" 创建失败 {e}', color='red', highlight=1)
                sys.exit(-1)

        log_file_archive_count = config.getint(section_Log, option_log_file_archive_count)
        log_file_archive_size = config.getint(section_Log, option_log_file_archive_size)
        server_port = config.getint(section_Port, option_server_port)
        server_signal_port = config.getint(section_Port, option_server_signal_port)
        client_signal_port = config.getint(section_Port, option_client_signal_port)
    except (NoOptionError, NoSectionError) as e:
        print_color(f'{e}', color='red', highlight=1)
        sys.exit(-1)
    except ValueError as e:
        print_color(f'配置错误 {e}', color='red', highlight=1)
        sys.exit(-1)
    return Configration(default_path=default_path, cert_dir=cert_dir, log_dir=log_dir,
                        log_file_archive_count=log_file_archive_count, log_file_archive_size=log_file_archive_size,
                        server_port=server_port, server_signal_port=server_signal_port,
                        client_signal_port=client_signal_port)


# 打包控制变量，用于将程序打包为exe后防止直接退出控制台
# Packaging control variable,
# used to prevent the console from exiting directly after the program is packaged as exe
packaging = False

# 命令类型
SEND_FILE = "send_file"
SEND_DIR = "send_dir"
COMPARE_DIR = "compare_dir"
COMMAND = 'command'
SYSINFO = 'sysinfo'
SPEEDTEST = 'speedtest'
BEFORE_WORKING = 'before_working'
CLOSE = 'close'
PUSH_CLIPBOARD = 'push_clipboard'
PULL_CLIPBOARD = 'pull_clipboard'

# 其他常量
FAIL = 'fail'
PUSH = 'push'
PULL = 'pull'
GET = 'get'
SEND = 'send'
CONTINUE = 'continue'
CANCEL = 'cancelTf'
DIRISCORRECT = "DirIsCorrect"
filename_fmt = '800s'
fmt = f'>{filename_fmt}{len(BEFORE_WORKING)}sQ'  # 大端对齐，800位文件（夹）名，11位表示命令类型，Q为 8字节 unsigned 整数，表示文件大小 0~2^64-1
str_len_fmt = '>Q'
filename_size = struct.calcsize(filename_fmt)
fileinfo_size = struct.calcsize(fmt)
str_len_size = struct.calcsize(str_len_fmt)
unit = 1024 * 1024  # 1MB
color_dict = {
    'black': ';30',
    'red': ';31',
    'green': ';32',
    'yellow': ';33',
    'blue': ';34',
    'white': ''
}
# 配置文件相关
config_file = 'config.txt'

section_Main = 'Main'
section_Log = 'Log'
section_Port = 'Port'

option_windows_default_path = 'windows_default_path'
option_linux_default_path = 'linux_default_path'
option_cert_dir = 'cert_dir'
option_windows_log_dir = 'windows_log_dir'
option_linux_log_dir = 'linux_log_dir'
option_log_file_archive_count = 'log_file_archive_count'
option_log_file_archive_size = 'log_file_archive_size'
option_server_port = 'server_port'
option_server_signal_port = 'server_signal_port'
option_client_signal_port = 'client_signal_port'

if not os.path.exists(config_file):
    print_color(
        '未找到配置文件，采用默认配置\nThe configuration file was not found, using the default configuration.\n',
        color='yellow', highlight=1)
    # 生成配置文件
    generate_config()

# 加载配置
config = load_config()

if __name__ == '__main__':
    print(get_relative_filename_from_basedir(input('>>> ')))
