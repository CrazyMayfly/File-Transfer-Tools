import hashlib
import json
import os
import struct
import threading
from datetime import datetime


def crypt(bytes, key, num=1024):
    # 将字节转化为二进制数据进行异或操作
    bin_data = int.from_bytes(bytes, 'big') ^ key
    # 将结果转化为字节
    return int.to_bytes(bin_data, num, 'big')


def receive_data(connection, size):
    # 避免粘包
    rest_size = size
    result = b''
    while rest_size > 0:
        data = connection.recv(min(rest_size, unit))
        rest_size -= len(data)
        result += data
    return result


def calcu_size(filesize):
    """
    计算文件大小所对应的合适的单位
    :param filesize: 原始文件大小，单位byte
    :return:返回合适的两个单位及对应的大小
    """
    file_size_KB = filesize / 1024
    file_size_MB = file_size_KB / 1024
    file_size_GB = file_size_MB / 1024
    KB_Str = str(round(file_size_KB, 2)) + ' KB'
    MB_Str = str(round(file_size_MB, 2)) + ' MB'
    GB_Str = str(round(file_size_GB, 2)) + ' GB'
    if file_size_GB >= 0.5:
        return GB_Str, MB_Str
    elif file_size_MB >= 0.5:
        return MB_Str, KB_Str
    else:
        return KB_Str, str(filesize) + ' bytes'


def get_rate_and_residue(number):
    residue = number % 1024
    rate = int((number - residue) / 1024)
    return rate, residue


def print_color(msg, color='white', highlight=0):
    color_dict = {
        'black': ';30',
        'red': ';31',
        'green': ';32',
        'yellow': ';33',
        'blue': ';34',
        'white': ''
    }

    print("\033[{}{}m{}\033[0m".format(highlight, color_dict[color], msg))


def get_log_msg(msg):
    t = threading.current_thread()
    now = datetime.now().strftime('%H:%M:%S.%f')[0:-3]
    ident = str(t.ident)
    while len(ident) < 5:
        ident = ident + ' '
    name = t.name
    while len(name) < 10:
        name = name + ' '
    msg = now + ' ' + ident + ' ' + name + ' ' + msg
    return msg


def get_relative_filename_from_basedir(base_dir):
    results = {}
    basedir_length = len(base_dir) + 1
    for path, dir_list, file_list in os.walk(base_dir):
        for file in file_list:
            real_path = os.path.join(path, file)
            filesize = os.stat(real_path).st_size
            results.update({os.path.join(path, file)[basedir_length:]: filesize})
    return results


def get_dir_file_name(dirname):
    """
    获取某文件路径下的所有文件夹和文件的相对路径
    :param dirname: 文件路径
    :return :返回该文件路径下的所有文件夹、文件的相对路径
    """
    all_dir_name = []
    all_file_name = []
    # 获取上一级文件夹名称
    back_dir = os.path.dirname(dirname)
    for path, dir_list, file_list in os.walk(dirname):
        # 获取相对路径
        path = os.path.relpath(path, back_dir)
        all_dir_name.append(path)
        if os.path.dirname(path) in all_dir_name:
            all_dir_name.remove(os.path.dirname(path))
        for file in file_list:
            all_file_name.append(os.path.join(path, file))
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


# 命令类型
SEND_FILE = "send_file"
SEND_DIR = "send_dir"
COMPARE_DIR = "compare_dir"
COMMAND = 'command'
SYSINFO = 'sysinfo'
SPEEDTEST = 'speedtest'
GET = 'get'
# 其他常量
CONTINUE = 'continue'
CANCEL = 'canceltf'

filename_fmt = '800s'
fmt = f'>{filename_fmt}{max(len(SEND_FILE), len(SEND_DIR), len(COMPARE_DIR), len(COMMAND), len(SYSINFO), len(SPEEDTEST))}sQ'  # 大端对齐，800位文件（夹）名，11位表示命令类型，Q为 8字节 unsigned 整数，表示文件大小 0~2^64-1
str_len_fmt = '>Q'
filename_size = struct.calcsize(filename_fmt)
fileinfo_size = struct.calcsize(fmt)
str_len_size = struct.calcsize(str_len_fmt)
log_dir = 'C:\ProgramData\logs'
cert_dir = '.\\cert'
unit = 1024 * 1024  # 1MB
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

server_port = 2023
server_signal_port = 2021
client_signal_port = 2022

if __name__ == '__main__':
    print(len(json.dumps(get_relative_filename_from_basedir("E:"), ensure_ascii=True)))
