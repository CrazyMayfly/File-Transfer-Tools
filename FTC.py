import os.path
import random
from pathlib import Path
import concurrent.futures
import readline
import ssl
from shutil import get_terminal_size
from argparse import ArgumentParser, Namespace
from tqdm import tqdm
from Utils import *
from sys_info import *
from collections import deque

LARGE_FILE_SIZE_THRESHOLD = 1024 * 1024
SMALL_FILE_CHUNK_SIZE = 1024 * 1024 * 2


def print_history(nums=10):
    current_history_length = readline.get_current_history_length()
    start_index = current_history_length - nums + 1 if current_history_length > nums else 1
    for i in range(start_index, current_history_length + 1):
        print(readline.get_history_item(i))


def completer(text, state):
    options = [i for i in commands if i.startswith(text)]
    return options[state] if state < len(options) else None


def split_dir(command):
    """
    将命令分割为两个目录名
    """
    dir_names = command[8:].split('"')
    dir_names = dir_names[0].split(' ') if len(dir_names) == 1 else \
        [dir_name.strip() for dir_name in dir_names if dir_name.strip()]
    return dir_names if len(dir_names) == 2 else (None, None)


def read_line_setup() -> PurePath:
    """
    设置readline的补全和历史记录功能
    """
    readline.set_completer(completer)
    readline.set_history_length(1000)
    readline.parse_and_bind('tab: complete')
    history_filename = PurePath(config.log_dir, 'history.txt')
    readline.read_history_file(history_filename)
    return history_filename


def get_dir_file_name(filepath):
    """
    获取某文件路径下的所有文件夹和文件的相对路径
    :param filepath: 文件路径
    :return :返回该文件路径下的所有文件夹、文件的相对路径
    """
    all_dir_name = {}
    all_file_name = []
    # 获取上一级文件夹名称
    for path, _, file_list in os.walk(filepath):
        # 获取相对路径
        rel_path = os.path.relpath(path, filepath)
        all_dir_name[rel_path] = os.path.getatime(path), os.path.getmtime(path)
        all_file_name += [PurePath(rel_path, file).as_posix() for file in file_list]
    return all_dir_name, all_file_name


def split_by_threshold(info):
    result = []
    current_sum = last_idx = 0
    for idx, (_, size, _) in enumerate(info, start=1):
        current_sum += size
        if current_sum > SMALL_FILE_CHUNK_SIZE:
            result.append((current_sum, idx - last_idx, info[last_idx:idx]))
            last_idx = idx
            current_sum = 0
    if (rest := len(info) - last_idx) > 0:
        result.append((current_sum, rest, info[last_idx:]))
    return result


def get_args() -> Namespace:
    """
    获取命令行参数解析器
    """
    parser = ArgumentParser(description='File Transfer Client, used to SEND files and instructions.')
    cpu_count = psutil.cpu_count(logical=False)
    parser.add_argument('-t', metavar='thread', type=int,
                        help=f'threads (default: {cpu_count})', default=cpu_count)
    parser.add_argument('-host', metavar='host',
                        help='destination hostname or ip address', default='')
    parser.add_argument('-p', '--password', metavar='password', type=str,
                        help='Use a password to connect host.', default='')
    return parser.parse_args()


class FTC:
    def __init__(self, threads, host, password=''):
        self.__peer_platform = None
        self.__password = password
        self.__pbar = None
        self.__host = host
        self.__threads = threads
        self.__connections = []
        self.__main_conn = None
        self.__base_dir = ''
        self.__session_id = 0
        self.__command_prefix = ''
        self.logger = Logger(PurePath(config.log_dir, f'{datetime.now():%Y_%m_%d}_client.log'))
        self.__large_file_info: deque = deque()
        self.__small_file_info: deque = deque()
        self.__finished_files: deque = deque()
        self.__history_file = open(read_line_setup(), 'a', encoding=utf8)
        # 进行日志归档
        threading.Thread(name='ArchiveThread', target=compress_log_files,
                         args=(config.log_dir, 'client', self.logger)).start()

    def __add_history(self, command: str):
        readline.add_history(command)
        self.__history_file.write(command + '\n')
        self.__history_file.flush()

    def __compare_dir(self, local_dir, peer_dir):
        def print_filename_if_exits(prompt, filename_list):
            msg = [prompt]
            if filename_list:
                msg.extend([('\t' + file_name) for file_name in filename_list])
            else:
                msg.append('\tNone')
            print('\n'.join(msg))
            return '\n'.join(msg)

        if not os.path.exists(local_dir):
            self.logger.warning('本地文件夹不存在')
            return

        conn = self.__main_conn
        conn.send_head(peer_dir, COMMAND.COMPARE_DIR, 0)
        if conn.receive_data(len(DIRISCORRECT)).decode() != DIRISCORRECT:
            self.logger.warning(f"目标文件夹 {peer_dir} 不存在")
            return
        local_dict = get_relative_filename_from_basedir(local_dir)
        # 获取本地的文件名
        local_filenames = local_dict.keys()
        # 将字符串转化为dict
        peer_dict: dict = conn.recv_with_decompress()
        # 求各种集合
        file_in_local_smaller_than_peer = []
        file_in_peer_smaller_than_local = []
        file_size_and_name_both_equal = []
        file_not_exits_in_peer = []
        for filename in local_filenames:
            peer_size = peer_dict.pop(filename, -1)
            if peer_size == -1:
                file_not_exits_in_peer.append(filename)
                continue
            size_diff = local_dict[filename] - peer_size
            if size_diff < 0:
                file_in_local_smaller_than_peer.append(filename)
            elif size_diff == 0:
                file_size_and_name_both_equal.append(filename)
            else:
                file_in_peer_smaller_than_local.append(filename)
        tmp = file_size_and_name_both_equal[:10] + ['(more hidden...)'] if len(
            file_size_and_name_both_equal) > 10 else file_size_and_name_both_equal
        file_not_exits_in_local = peer_dict.keys()
        msgs = ['\n[INFO   ] ' + get_log_msg(f'对比本地文件夹 {local_dir} 和目标文件夹 {peer_dir} 的差异\n')]
        for arg in [("file exits in peer but not exits in local: ", file_not_exits_in_local),
                    ("file exits in local but not exits in peer: ", file_not_exits_in_peer),
                    ("file in local smaller than peer: ", file_in_local_smaller_than_peer),
                    ("file in peer smaller than local: ", file_in_peer_smaller_than_local),
                    ("file name and size both equal in two sides: ", tmp)]:
            msgs.append(print_filename_if_exits(*arg))
        self.logger.silent_write(msgs)
        if not file_size_and_name_both_equal:
            conn.sendall(size_struct.pack(CONTROL.CANCEL))
            return
        if input("Continue to compare hash for filename and size both equal set?(y/n): ") != 'y':
            conn.sendall(size_struct.pack(CONTROL.CANCEL))
            return
        # 发送继续请求
        conn.sendall(size_struct.pack(CONTROL.CONTINUE))
        # 发送相同的文件名称
        conn.send_with_compress(file_size_and_name_both_equal)
        results = {filename: get_file_md5(PurePath(local_dir, filename)) for filename in
                   file_size_and_name_both_equal}
        # 获取本次字符串大小
        peer_dict = conn.recv_with_decompress()
        hash_not_matching = [filename for filename in results.keys() if
                             results[filename] != peer_dict[filename]]
        self.logger.silent_write([print_filename_if_exits("hash not matching: ", hash_not_matching)])

    def __update_global_pbar(self, size, decrease=False):
        with self.__pbar.get_lock():
            if not decrease:
                self.__pbar.update(size)
            else:
                self.__pbar.total -= size

    def __execute_command(self, command):
        if len(command) == 0:
            return
        if self.__peer_platform == WINDOWS and (command.startswith('cmd') or command == 'powershell'):
            if command == 'powershell':
                self.logger.info('使用Windows PowerShell')
                self.__command_prefix = 'powershell '
            else:
                self.logger.info('使用CMD(命令提示符)')
                self.__command_prefix = ''
            return
        command = self.__command_prefix + command
        conn = self.__main_conn
        conn.send_head(command, COMMAND.EXECUTE_COMMAND, 0)
        msgs = ['\n[INFO   ] ' + get_log_msg(f'下达指令: {command}')]
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
        thread = MyThread(get_sys_info)
        thread.start()
        # 接收对方的系统信息
        peer_sysinfo = self.__main_conn.recv_with_decompress()
        msgs = ['[INFO   ] ' + get_log_msg("对比双方系统信息："), print_sysinfo(peer_sysinfo),
                print_sysinfo(thread.get_result())]
        # 等待本机系统信息获取完成
        self.logger.silent_write(msgs)

    def __speedtest(self, times):
        times = '500' if times.isspace() or not times else times
        while not (times.isdigit() and int(times) > 0):
            times = input("请重新输入数据量（单位MB）：")
        times, data_unit = int(times), 1000 * 1000  # 1MB
        data_size = times * data_unit
        conn = self.__main_conn
        conn.send_head('', COMMAND.SPEEDTEST, data_size)
        start = time.time()
        with tqdm(total=data_size, desc='speedtest_upload', unit='bytes', unit_scale=True, mininterval=1) as pbar:
            for i in range(times):
                # 生产随机字节
                conn.sendall(os.urandom(data_unit))
                pbar.update(data_unit)
        show_bandwidth('上传速度测试完毕', data_size, interval=time.time() - start, logger=self.logger)
        upload_over = time.time()
        with tqdm(total=data_size, desc='speedtest_download', unit='bytes', unit_scale=True, mininterval=1) as pbar:
            for i in range(times):
                conn.receive_data(data_unit)
                pbar.update(data_unit)
        show_bandwidth('下载速度测试完毕', data_size, interval=time.time() - upload_over, logger=self.logger)

    def __exchange_clipboard(self, command):
        """
        交换（发送，获取）对方剪切板内容

        @param command: get 或 send
        @return:
        """
        func = get_clipboard if command == GET else send_clipboard
        func(self.__main_conn, self.logger)

    def __prepare_to_send(self, dir_name, conn: ESocket):
        # 扩充连接
        self.__base_dir = dir_name
        # 发送文件夹命令
        conn.send_head(PurePath(dir_name).name, COMMAND.SEND_FILES_IN_DIR, 0)
        all_dir_name, all_file_name = get_dir_file_name(dir_name)
        # 发送文件夹数据
        self.logger.info(f'开始发送 {dir_name} 路径下所有文件夹，文件夹个数为 {len(all_dir_name)}')
        conn.send_with_compress(all_dir_name)
        # 将发送的文件夹信息写入日志
        msgs = [f'{PurePath(dir_name, name).as_posix()}\n' for name in all_dir_name.keys()]
        # 接收对方已有的文件名并计算出对方没有的文件
        all_file_name = list(set(all_file_name) - set(conn.recv_with_decompress()))
        # 将待发送的文件打印到日志，计算待发送的文件总大小
        msgs.append('\n[INFO   ] ' + get_log_msg("本次待发送的文件列表为：\n"))
        # 统计待发送的文件信息
        total_size = 0
        large_file_info, small_file_info = [], []
        for filename in all_file_name:
            real_path = Path(dir_name, filename)
            file_size = (file_stat := real_path.stat()).st_size
            info = filename, file_size, (file_stat.st_ctime, file_stat.st_mtime, file_stat.st_atime)
            # 记录每个文件大小
            small_file_info.append(info) if file_size < LARGE_FILE_SIZE_THRESHOLD else large_file_info.append(info)
            total_size += file_size
            msgs.append("{}, 约{}, {}\n".format(real_path, *calcu_size(file_size)))
        self.logger.silent_write(msgs)
        random.shuffle(small_file_info)
        self.__large_file_info = deque(sorted(large_file_info, key=lambda item: item[1]))
        self.__small_file_info = deque(split_by_threshold(small_file_info))
        return all_file_name, total_size

    def __send_files_in_dir(self, dir_name):
        self.__connect(self.__threads)
        all_file_name, total_size = self.__prepare_to_send(dir_name, self.__main_conn)
        self.logger.info(f'开始发送 {dir_name} 路径下所有文件，文件个数为 {len(all_file_name)}')
        # 初始化总进度条
        self.__pbar = tqdm(total=total_size, desc='累计发送量', unit='bytes',
                           unit_scale=True, mininterval=1, position=0, colour='#01579B')
        # 发送文件
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.__threads, thread_name_prefix='Slave') as executor:
            futures = [executor.submit(self.__send_file, conn, position) for position, conn in
                       enumerate(self.__connections, start=1)]
            concurrent.futures.wait(futures)
        try:
            for conn in self.__connections:
                conn.send_head('', COMMAND.FINISH, 0)
        except (ssl.SSLError, ConnectionError) as error:
            self.logger.error(error)
        finally:
            fails = set(all_file_name) - set(self.__finished_files)
            self.__finished_files.clear()
            # 比对发送失败的文件
            if fails:
                self.__pbar.colour = '#F44336'
                self.__pbar.close()
                self.logger.error("发送失败的文件：", highlight=1)
                for fail in fails:
                    self.logger.warning(fail)
            else:
                self.__pbar.colour = '#98c379'
                data_size, interval = self.__pbar.total, time.time() - self.__pbar.start_t
                self.__pbar.close()
                show_bandwidth('本次全部文件正常发送', data_size, interval=interval, logger=self.logger)
            exceptions = [future.exception() for future in futures]
            if exceptions.count(None) != len(exceptions):
                exceptions = '\n'.join(
                    [f'Thread-{idx}: {exception}' for idx, exception in enumerate(exceptions) if exception is not None])
                self.logger.error(f"本次发送中出现的异常：\n{exceptions}", highlight=1)

    def __send_single_file(self, filename: Path):
        self.logger.silent_write([f'\n[INFO   ] {get_log_msg(f"发送单个文件: {filename}")}\n'])
        self.__base_dir = filename.parent
        file_size = (file_stat := filename.stat()).st_size
        time_info = file_stat.st_ctime, file_stat.st_mtime, file_stat.st_atime
        self.__large_file_info.append((filename.name, file_size, time_info))
        pbar_width = get_terminal_size().columns / 4
        self.__pbar = tqdm(total=file_size, desc=shorten_path(filename.name, pbar_width), unit='bytes',
                           unit_scale=True, mininterval=1, position=0, colour='#01579B')
        self.__send_large_file(self.__main_conn, 0)
        if len(self.__finished_files) and self.__finished_files.pop() == filename.name:
            self.__pbar.colour = '#98c379'
            self.__pbar.close()
            self.logger.success(f"{filename} 发送成功")
        else:
            self.__pbar.colour = '#F44336'
            self.__pbar.close()
            self.logger.error(f"{filename} 发送失败")

    def __send_large_file(self, conn: ESocket, position: int):
        while len(self.__large_file_info):
            filename, file_size, time_info = self.__large_file_info.pop()
            real_path = PurePath(self.__base_dir, filename)
            try:
                fp = open(real_path, 'rb')
                conn.send_head(filename, COMMAND.SEND_LARGE_FILE, file_size)
                if (flag := conn.recv_size()) == CONTROL.FAIL2OPEN:
                    self.logger.error(f'对方接收文件失败：{real_path}', highlight=1)
                    return
                # 服务端已有的文件大小
                fp.seek(peer_exist_size := flag, 0)
                rest_size = file_size - peer_exist_size
                pbar_width = get_terminal_size().columns / 4
                with tqdm(total=rest_size, desc=shorten_path(filename, pbar_width), unit='bytes', unit_scale=True,
                          mininterval=1, position=position, leave=False, disable=position == 0) as pbar:
                    while data := fp.read(min(rest_size, unit)):
                        conn.sendall(data)
                        pbar.update(data_size := len(data))
                        rest_size -= data_size
                        self.__update_global_pbar(data_size)
                fp.close()
                # 发送文件的创建、访问、修改时间戳
                conn.sendall(times_struct.pack(*time_info))
                self.__update_global_pbar(peer_exist_size, decrease=True)
                self.__finished_files.append(filename)
            except (ssl.SSLError, ConnectionError) as error:
                self.logger.error(error)
            except FileNotFoundError:
                self.logger.error(f'文件打开失败：{real_path}')

    def __send_small_file(self, conn: ESocket, position: int):
        idx, real_path, files_info = 0, Path(""), []
        while len(self.__small_file_info):
            try:
                total_size, num, files_info = self.__small_file_info.pop()
                conn.send_head('', COMMAND.SEND_SMALL_FILE, total_size)
                conn.send_with_compress(files_info)
                with tqdm(total=total_size, desc='发送小文件簇', unit='bytes', unit_scale=True,
                          mininterval=1, position=position, leave=False) as pbar:
                    for idx, (filename, file_size, _) in enumerate(files_info):
                        real_path = Path(self.__base_dir, filename)
                        with real_path.open('rb') as fp:
                            conn.sendall(fp.read(file_size))
                        pbar.update(file_size)
                self.__update_global_pbar(total_size)
            except (ssl.SSLError, ConnectionError) as error:
                self.logger.error(error)
            except FileNotFoundError:
                self.logger.error(f'文件打开失败：{real_path}')
            finally:
                self.__finished_files.extend([filename for filename, _, _ in files_info[:idx + 1]])

    def __send_file(self, conn: ESocket, position: int):
        if position < 3:
            self.__send_large_file(conn, position)
            self.__send_small_file(conn, position)
        else:
            self.__send_small_file(conn, position)
            self.__send_large_file(conn, position)

    def __validate_password(self, conn: ESocket):
        conn.send_head(self.__password, COMMAND.BEFORE_WORKING, self.__session_id)
        msg, _, session_id = conn.recv_head()
        return msg, session_id

    def __find_server(self, wait=1):
        if self.__host:
            splits = self.__host.split(":")
            if len(splits) == 2:
                config.server_port = int(splits[1])
                self.__host = splits[0]
            # self.logger.log(f"目标主机: {self.__host}, 目标端口: {config.server_port}")
            return
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        ip, _ = get_ip_and_hostname()
        sk.bind((ip, config.client_signal_port))
        self.logger.log(f'开始探测服务器信息')
        content = f'HI-I-AM-FTC_{ip}_{config.client_signal_port}'.encode(utf8)
        broadcast_to_all_interfaces(sk, port=config.server_signal_port, content=content)
        begin = time.time()
        addresses = set()
        while time.time() - begin < wait:
            try:
                data = sk.recv(1024).decode(utf8).split('_')
            except TimeoutError:
                break
            if data[0] == 'HI-I-AM-FTS':
                addresses.add(data[1])
            sk.settimeout(wait)
        sk.close()
        if len(addresses) == 1:
            self.__host = addresses.pop()
        else:
            msg = ['当前可用主机列表：'] + [f'ip: {address}, hostname: {get_hostname_by_ip(address)}' for address in addresses]
            self.logger.log('\n'.join(msg))
            self.__host = input('请输入主机名/ip: ')

    def shutdown(self, send_close_info=True):
        try:
            for conn in self.__connections:
                if send_close_info:
                    conn.send_head('', COMMAND.CLOSE, 0)
                conn.close()
        finally:
            self.logger.close()
            self.__history_file.close()
            sys.exit(0)

    def __connect(self, nums=1):
        """
        将现有的连接数量扩充至nums

        @param nums: 需要扩充到的连接数
        @return:
        """
        additional_conn_nums = nums - len(self.__connections)
        if additional_conn_nums <= 0:
            return
        try:
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            for i in range(0, additional_conn_nums):
                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                # 连接至服务器
                client_socket.connect((self.__host, config.server_port))
                # 将socket包装为securitySocket
                client_socket = ESocket(context.wrap_socket(client_socket, server_hostname='FTS'))
                self.__connections.append(client_socket)
                if self.__main_conn:
                    # 验证密码
                    self.__validate_password(client_socket)
                    continue
                # 首次连接
                self.__main_conn = client_socket
                msg, session_id = self.__validate_password(client_socket)
                if msg == FAIL:
                    self.logger.error('连接至服务器的密码错误', highlight=1)
                    self.shutdown(send_close_info=False)
                else:
                    # self.logger.info(f'服务器所在平台: {msg}\n')
                    self.__peer_platform = msg
                    self.__command_prefix = 'powershell ' if self.__peer_platform == WINDOWS else ''
                    self.__session_id = session_id
                    self.logger.success(f'成功连接至服务器 {self.__host}:{config.server_port}')
        except (ssl.SSLError, OSError) as msg:
            self.logger.error(f'连接至 {self.__host} 失败, {msg}')
            sys.exit(-1)

    def start(self):
        self.__find_server()
        self.__connect()
        self.logger.info(f'当前线程数：{self.__threads}')
        while True:
            command = input('>>> ').strip()
            self.__add_history(command)
            try:
                if command in ['q', 'quit', 'exit']:
                    self.shutdown()
                elif os.path.isdir(command) and os.path.exists(command):
                    self.__send_files_in_dir(command)
                elif os.path.isfile(command) and os.path.exists(command):
                    self.__send_single_file(Path(command))
                elif command == sysinfo:
                    self.__compare_sysinfo()
                elif command.startswith(speedtest):
                    self.__speedtest(times=command[10:])
                elif command.startswith(compare):
                    local_dir, destination_dir = split_dir(command)
                    if not destination_dir or not local_dir:
                        self.logger.warning('本地文件夹且远程文件夹不能为空')
                        continue
                    self.__compare_dir(local_dir, destination_dir)
                elif command.endswith('clipboard'):
                    self.__exchange_clipboard(command.split()[0])
                elif command.startswith(history):
                    print_history(int(command.split()[1])) if len(command.split()) > 1 and command.split()[
                        1].isdigit() else print_history()
                else:
                    self.__execute_command(command)
            except (ssl.SSLError, ConnectionError) as e:
                self.logger.error(e.strerror if e.strerror else e, highlight=1)
                self.logger.close()
                if packaging:
                    os.system('pause')
                sys.exit(-1)


if __name__ == '__main__':
    args = get_args()
    # 启动FTC服务
    ftc = FTC(threads=args.t, host=args.host, password=args.password)
    handle_ctrl_event(logger=ftc.logger)
    ftc.start()
    if packaging:
        os.system('pause')
