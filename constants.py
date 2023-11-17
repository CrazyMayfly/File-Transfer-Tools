import sys
import psutil
from dataclasses import dataclass
from enum import IntEnum, StrEnum, auto
from struct import Struct
from typing import Final
from platform import system

WINDOWS: Final[str] = 'Windows'
LINUX: Final[str] = 'Linux'
MACOS: Final[str] = 'Macos'

cur_platform: Final[str] = system()
windows = cur_platform == WINDOWS

username = psutil.users()[0].name
cpu_count = psutil.cpu_count(logical=False)

LARGE_FILE_SIZE_THRESHOLD = 20  # 1024 * 1024
SMALL_FILE_CHUNK_SIZE = 21  # 1024 * 1024 * 2

package = getattr(sys, 'frozen', False)


class LEVEL(StrEnum):
    """
    日志打印等级的枚举类，值为等级对应的颜色代码
    """
    LOG = ''
    INFO = ';34'
    WARNING = ';33'
    SUCCESS = ';32'
    ERROR = ';31'


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


# 控制类型
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


# 配置实体类
@dataclass
class Configration:
    default_path: str
    log_dir: str
    log_file_archive_count: int
    log_file_archive_size: int
    server_port: int
    signal_port: int


# 其他常量
FAIL: Final[str] = 'fail'
GET: Final[str] = 'get'
SEND: Final[str] = 'send'
OVER: Final[bytes] = b'\00'
utf8: Final[str] = 'utf-8'
buf_size: Final[int] = 1024 * 1024  # 1MB
sysinfo: Final[str] = 'sysinfo'
compare: Final[str] = "compare"
speedtest: Final[str] = 'speedtest'
setbase: Final[str] = 'setbase'
history: Final[str] = 'history'
say: Final[str] = 'say'
clipboard_send: Final[str] = 'send clipboard'
clipboard_get: Final[str] = 'get clipboard'
commands: Final[list] = [sysinfo, compare, speedtest, setbase, say, history, clipboard_send, clipboard_get]

# Struct 对象
# B为 1字节 unsigned char，0~127
# Q为 8字节 unsigned long long， 0~2^64-1
# q为 8字节 long long， -2^63~2^63-1
# H为 2字节 unsigned short， 0~65535
# d为 8字节 double， 2.3E-308~1.7E+308
head_struct = Struct('>BQH')
size_struct = Struct('q')
times_struct = Struct('ddd')
