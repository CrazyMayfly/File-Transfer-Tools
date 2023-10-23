import os.path
import readline
import random
import ssl
from shutil import get_terminal_size
from argparse import ArgumentParser, Namespace
from multiprocessing.pool import ThreadPool
from tqdm import tqdm
from Utils import *
from functools import cached_property
from sys_info import *
from collections import deque


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


def read_line_setup() -> Path:
    """
    设置readline的补全和历史记录功能
    """
    readline.set_completer(completer)
    readline.set_history_length(1000)
    readline.parse_and_bind('tab: complete')
    history_filename = Path(config.log_dir, 'history.txt')
    readline.read_history_file(history_filename)
    return history_filename


def get_dir_file_name(filepath):
    """
    获取某文件路径下的所有文件夹和文件的相对路径
    :param filepath: 文件路径
    :return :返回该文件路径下的所有文件夹、文件的相对路径
    """
    all_dir_name = set()
    all_file_name = []
    # 获取上一级文件夹名称
    for path, _, file_list in os.walk(filepath):
        # 获取相对路径
        path = os.path.relpath(path, filepath)
        all_dir_name.add(path)
        # 去除重复的路径，防止多次创建，降低效率
        all_dir_name.discard(os.path.dirname(path))
        all_file_name += [Path(path, file).as_posix() for file in file_list]
    return all_dir_name, all_file_name


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
        self.__connections = self.__Connections()
        self.__base_dir = ''
        self.__session_id = 0
        self.__first_connect = True
        self.__file2size = {}
        self.__command_prefix = ''
        self.logger = Logger(Path(config.log_dir, f'{datetime.now():%Y_%m_%d}_client.log'))
        self.__thread_pool = None
        self.__history_file = open(read_line_setup(), 'a', encoding=utf8)
        self.__position = deque(range(1, threads + 1))
        # 进行日志归档
        threading.Thread(name='ArchiveThread', target=compress_log_files,
                         args=(config.log_dir, 'client', self.logger)).start()

    class __Connections:
        def __init__(self):
            self.__conn_pool = []
            self.__thread_conn_dict: dict[int:ESocket] = {}
            self.__lock = threading.Lock()

        def __enter__(self) -> ESocket:
            # 从空闲的conn中取出一个使用
            conn = self.__thread_conn_dict.get(threading.current_thread().ident, None)
            if not conn:
                with self.__lock:
                    conn = self.__conn_pool.pop() if len(self.__conn_pool) > 0 else self.main_conn
                    self.__thread_conn_dict[threading.current_thread().ident] = conn
            return conn

        @property
        def connections(self) -> set[ESocket]:
            return set(list(self.__thread_conn_dict.values()) + self.__conn_pool)

        @cached_property
        def main_conn(self) -> ESocket:
            return self.__thread_conn_dict[threading.main_thread().ident]

        def add(self, conn):
            self.__conn_pool.append(conn)

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    def __add_history(self, command: str):
        readline.add_history(command)
        self.__history_file.write(command + '\n')
        self.__history_file.flush()

    def __compare_dir(self, local_dir, peer_dir):
        def print_filename_if_exits(prompt, filename_list):
            print(prompt)
            if filename_list:
                for file_name in filename_list:
                    print('\t' + file_name)
            else:
                print('\tNone')

        self.logger.flush()
        self.logger.log_file.write(
            '\n[INFO   ] ' + get_log_msg(f'对比本地文件夹 {local_dir} 和目标文件夹 {peer_dir} 的差异\n'))
        if not os.path.exists(local_dir):
            self.logger.warning('本地文件夹不存在')
            return

        with self.__connections as conn:
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
            for arg in [("file exits in peer but not exits in local: ", file_not_exits_in_local),
                        ("file exits in local but not exits in peer: ", file_not_exits_in_peer),
                        ("file in local smaller than peer: ", file_in_local_smaller_than_peer),
                        ("file in peer smaller than local: ", file_in_peer_smaller_than_local),
                        ("file name and size both equal in two sides: ", tmp)]:
                extra_print2file(print_filename_if_exits, arg, self.logger.log_file)

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
            results = {filename: get_file_md5(Path(local_dir, filename)) for filename in
                       file_size_and_name_both_equal}
            # 获取本次字符串大小
            peer_dict = conn.recv_with_decompress()
            hash_not_matching = [filename for filename in results.keys() if
                                 results[filename] != peer_dict[filename]]
            extra_print2file(print_filename_if_exits, ("hash not matching: ", hash_not_matching), self.logger.log_file)

    def __update_global_pbar(self, size, decrease=False):
        if size == 0 or self.__pbar is None:
            return
        with self.__pbar.get_lock():
            if not decrease:
                self.__pbar.update(size)
            else:
                self.__pbar.total -= size

    def __execute_command(self, command):
        # 防止命令将输入端交给服务器
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
        with self.__connections as conn:
            conn.send_head(command, COMMAND.EXECUTE_COMMAND, 0)
            self.logger.flush()
            self.logger.log_file.write('\n[INFO   ] ' + get_log_msg(f'下达指令: {command}\n'))
            # 接收返回结果
            result, command, _ = conn.recv_head()
            while command == COMMAND.EXECUTE_RESULT:
                print(result, end='')
                self.logger.log_file.write(result)
                result, command, _ = conn.recv_head()
            self.logger.log_file.flush()

    def __compare_sysinfo(self):
        # 发送比较系统信息的命令到FTS
        with self.__connections as conn:
            conn.send_head('', COMMAND.SYSINFO, 0)
            # 异步获取自己的系统信息
            thread = MyThread(get_sys_info)
            thread.start()
            # 接收对方的系统信息
            peer_sysinfo = conn.recv_with_decompress()
        self.logger.flush()
        self.logger.log_file.write('[INFO   ] ' + get_log_msg("对比双方系统信息：\n"))
        extra_print2file(print_sysinfo, (peer_sysinfo,), self.logger.log_file)
        # 等待本机系统信息获取完成
        thread.join()
        local_sysinfo = thread.get_result()
        extra_print2file(print_sysinfo, (local_sysinfo,), self.logger.log_file)

    def __speedtest(self, times):
        times = '500' if times.isspace() or not times else times
        while not (times.isdigit() and int(times) > 0):
            times = input("请重新输入数据量（单位MB）：")
        times = int(times)
        data_unit = 1000 * 1000  # 1MB
        data_size = times * data_unit
        with self.__connections as conn:
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
        with self.__connections as conn:
            func(conn, self.logger)

    def __prepare_to_send(self, filepath, conn: ESocket):
        self.__base_dir = filepath
        # 发送文件夹命令
        conn.send_head(Path(filepath).name, COMMAND.SEND_FILES_IN_DIR, 0)
        all_dir_name, all_file_name = get_dir_file_name(filepath)
        # 发送文件夹数据
        conn.send_with_compress(list(all_dir_name))
        self.logger.info(f'开始发送 {filepath} 路径下所有文件夹，文件夹个数为 {len(all_dir_name)}')
        # 将发送的文件夹信息写入日志
        self.logger.flush()
        for name in all_dir_name:
            self.logger.log_file.write(f'{Path(filepath, name)}\n')
        # 接收对方已有的文件名
        peer_file_names = set(conn.recv_with_decompress())
        total_size = 0
        # 计算出对方没有的文件
        all_file_name = list(set(all_file_name) - peer_file_names)
        # 将待发送的文件打印到日志，计算待发送的文件总大小
        self.logger.log_file.write('\n[INFO   ] ' + get_log_msg("本次待发送的文件列表为：\n"))
        for filename in all_file_name:
            real_path = Path(filepath, filename)
            file_size = os.path.getsize(real_path)
            # 记录每个文件大小
            self.__file2size[filename] = file_size
            sz1, sz2 = calcu_size(file_size)
            self.logger.log_file.write(f"{real_path}, 约{sz1}, {sz2}\n")
            total_size += file_size
        self.logger.log_file.write('\n')
        self.logger.log_file.flush()
        return all_file_name, total_size

    def __send_files_in_dir(self, filepath):
        # 扩充连接和初始化线程池
        self.__connect(self.__threads)
        all_file_name, total_size = self.__prepare_to_send(filepath, self.__connections.main_conn)
        # 打乱列表以避免多个小文件聚簇在一起，影响效率
        random.shuffle(all_file_name)
        if self.__thread_pool is None:
            self.__thread_pool = ThreadPool(self.__threads)
        self.logger.info(f'开始发送 {filepath} 路径下所有文件，文件个数为 {len(all_file_name)}')
        # 初始化总进度条
        self.__pbar = tqdm(total=total_size, desc='累计发送量', unit='bytes',
                           unit_scale=True, mininterval=1, position=0, colour='#01579B')
        # 异步发送文件并等待结果
        results = [self.__thread_pool.apply_async(self.__send_file, (filename,)) for filename in all_file_name]
        # 比对发送成功或失败的文件
        success_recv = set()
        try:
            success_recv = set([result.get() for result in results])
            for conn in self.__connections.connections:
                conn.send_head('', COMMAND.FINISH, 0)
        except ssl.SSLEOFError:
            self.logger.warning('文件传输超时')
        finally:
            self.__file2size = {}
            fails = set(all_file_name) - success_recv
            if fails:
                self.__pbar.colour = '#F44336'
                self.__pbar = self.__pbar.close()
                self.logger.error("发送失败的文件：", highlight=1)
                for fail in fails:
                    self.logger.warning(fail)
            else:
                self.__pbar.colour = '#98c379'
                data_size, interval = self.__pbar.total, time.time() - self.__pbar.start_t
                self.__pbar = self.__pbar.close()
                show_bandwidth('本次全部文件正常发送', data_size, interval=interval, logger=self.logger)

    def __send_single_file(self, filepath):
        self.logger.flush()
        self.logger.log_file.write(f'[INFO   ] {get_log_msg(f"发送单个文件: {filepath}")}\n\n')
        self.__base_dir = os.path.dirname(filepath)
        filepath = os.path.basename(filepath)
        self.logger.success("发送成功") if filepath == self.__send_file(filepath) \
            else self.logger.error("发送失败")

    def __send_file(self, filepath):
        # 定义文件头信息，包含文件名和文件大小
        real_path = Path(self.__base_dir, filepath)
        file_size = self.__file2size[filepath] if self.__file2size else os.path.getsize(real_path)
        # 从空闲的conn中取出一个使用
        with self.__connections as conn:
            conn.send_head(filepath, COMMAND.SEND_FILE, file_size)
            flag = conn.recv_size()
            if flag == CONTROL.FAIL2OPEN:
                self.logger.error(f'对方接收文件失败：{real_path}', highlight=1)
                return
            fp = open(real_path, 'rb')
            # 服务端已有的文件大小
            fp.seek(exist_size := flag, 0)
            rest_size = file_size - exist_size
            if rest_size > unit:
                position, leave = (self.__position.popleft(), False) if self.__pbar else (0, True)
                pbar_width = get_terminal_size().columns / 4
                pbar = tqdm(total=rest_size, desc=shorten_path(filepath, pbar_width), unit='bytes', unit_scale=True,
                            mininterval=1, position=position, leave=leave)
                while data := fp.read(min(rest_size, unit)):
                    conn.sendall(data)
                    pbar.update(data_size := len(data))
                    rest_size -= data_size
                    self.__update_global_pbar(data_size)
                pbar.close()
                self.__position.append(position)
            else:
                # 小文件
                conn.sendall(data := fp.read(rest_size))
                self.__update_global_pbar(len(data))
            fp.close()
            # 发送文件的创建、访问、修改时间戳
            conn.sendall(file_details_struct.pack(os.path.getctime(real_path), os.path.getmtime(real_path),
                                                  os.path.getatime(real_path)))
            self.__update_global_pbar(exist_size, decrease=True)
        return filepath

    def __validate_password(self, conn: ESocket):
        conn.send_head(self.__password, COMMAND.BEFORE_WORKING, self.__session_id)
        msg, _, session_id = conn.recv_head()
        return msg, session_id

    def __before_working(self):
        with self.__connections as conn:
            msg, session_id = self.__validate_password(conn)
        if msg == FAIL:
            self.logger.error('连接至服务器的密码错误', highlight=1)
            self.shutdown(send_close_info=False)
        else:
            # self.logger.info(f'服务器所在平台: {msg}\n')
            self.__peer_platform = msg
            self.__command_prefix = 'powershell ' if self.__peer_platform == WINDOWS else ''
            self.__session_id = session_id

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
            msg = ['当前可用主机列表：']
            msg += [f'ip: {address}, hostname: {get_hostname_by_ip(address)}' for address in addresses]
            self.logger.log('\n'.join(msg))
            self.__host = input('请输入主机名/ip: ')

    def shutdown(self, send_close_info=True):
        if self.__thread_pool:
            self.__thread_pool.terminate()
        # self.logger.info(f'断开与 {self.__host}:{config.server_port} 的连接')
        try:
            for conn in self.__connections.connections:
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
        additional_conn_nums = nums - len(self.__connections.connections)
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
                # 验证密码
                if not self.__first_connect:
                    self.__validate_password(client_socket)
                self.__connections.add(client_socket)
        except (ssl.SSLError, OSError) as msg:
            self.logger.error(f'连接至 {self.__host} 失败, {msg}')
            sys.exit(-1)
        if self.__first_connect:
            self.logger.success(f'成功连接至服务器 {self.__host}:{config.server_port}')
            self.__first_connect = False

    def start(self):
        self.__find_server()
        self.__connect()
        self.logger.info(f'当前线程数：{self.__threads}')
        self.__before_working()
        while True:
            command = input('>>> ').strip()
            self.__add_history(command)
            try:
                if command in ['q', 'quit', 'exit']:
                    self.shutdown()
                elif os.path.isdir(command) and os.path.exists(command):
                    self.__send_files_in_dir(command)
                elif os.path.isfile(command) and os.path.exists(command):
                    self.__send_single_file(command)
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
            except ConnectionError as e:
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
