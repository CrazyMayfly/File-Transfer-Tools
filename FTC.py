import json
import os.path
import readline
import random
import ssl
from shutil import get_terminal_size
from argparse import ArgumentParser, Namespace
from multiprocessing.pool import ThreadPool
from tqdm import tqdm
from Utils import *
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
    parser.add_argument('--plaintext', action='store_true',
                        help='Use plaintext transfer (default: use ssl)')
    return parser.parse_args()


class FTC:
    def __init__(self, threads, host, use_ssl, password=''):
        self.__peer_platform = None
        self.__password = password
        self.__use_ssl = use_ssl
        self.__pbar = None
        self.__host = host
        self.__threads = threads
        self.__connections = self.__Connections()
        self.__base_dir = ''
        self.__session_id = 0
        self.__first_connect = True
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
            self.__thread_conn_dict: dict[str:socket.socket] = {}
            self.__lock = threading.Lock()

        def __enter__(self):
            # 从空闲的conn中取出一个使用
            conn = self.__thread_conn_dict.get(threading.current_thread().ident, None)
            if not conn:
                with self.__lock:
                    conn = self.__conn_pool.pop() if len(self.__conn_pool) > 0 else self.__thread_conn_dict.get(
                        threading.main_thread().ident)
                    self.__thread_conn_dict[threading.current_thread().ident] = conn
            return conn

        @property
        def connections(self) -> set[socket.socket]:
            return set(self.__thread_conn_dict.values())

        @property
        def main_conn(self) -> socket.socket:
            return self.__thread_conn_dict[threading.main_thread().ident]

        def add(self, conn):
            self.__conn_pool.append(conn)

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    def __add_history(self, history: str):
        readline.add_history(history)
        self.__history_file.write(history + '\n')
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

        file_head = pack_filehead(peer_dir, COMMAND.COMPARE_DIR, 0)
        with self.__connections as conn:
            conn.sendall(file_head)
            if receive_data(conn, len(DIRISCORRECT)).decode() != DIRISCORRECT:
                self.logger.warning(f"目标文件夹 {peer_dir} 不存在")
                return
            local_dict = get_relative_filename_from_basedir(local_dir)
            # 获取本地的文件名
            local_filenames = local_dict.keys()
            # 获取本次字符串大小
            data_size = receive_data(conn, size_fmt.size)
            data_size = size_fmt.unpack(data_size)[0]
            # 接收字符串
            data = receive_data(conn, data_size).decode()
            # 将字符串转化为dict
            peer_dict: dict = json.loads(data)
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
                conn.sendall(size_fmt.pack(CONTROL.CANCEL))
                return
            if input("Continue to compare hash for filename and size both equal set?(y/n): ") != 'y':
                conn.sendall(size_fmt.pack(CONTROL.CANCEL))
                return
            # 发送继续请求
            conn.sendall(size_fmt.pack(CONTROL.CONTINUE))
            # 发送相同的文件名称大小
            data_to_send = "|".join(file_size_and_name_both_equal).encode(utf8)
            conn.sendall(size_fmt.pack(len(data_to_send)))
            # 发送字符串
            conn.sendall(data_to_send)
            results = {filename: get_file_md5(Path(local_dir, filename)) for filename in
                       file_size_and_name_both_equal}
            # 获取本次字符串大小
            data_size = receive_data(conn, size_fmt.size)
            data_size = size_fmt.unpack(data_size)[0]
            # 接收字符串
            data = receive_data(conn, data_size).decode()
            # 将字符串转化为dict
            peer_dict = json.loads(data)
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
            file_head = pack_filehead(command, COMMAND.EXECUTE_COMMAND, len(command.encode(utf8)))
            conn.sendall(file_head)
            self.logger.flush()
            self.logger.log_file.write('\n[INFO   ] ' + get_log_msg(f'下达指令: {command}\n'))
            # 接收返回结果
            while (result := receive_data(conn, 8).decode('UTF-32')) != '\00' * 2:
                print(result, end='')
                self.logger.log_file.write(result)
            self.logger.log_file.flush()

    def __compare_sysinfo(self):
        # 发送比较系统信息的命令到FTS
        file_head = pack_filehead('', COMMAND.SYSINFO, 0)
        with self.__connections as conn:
            conn.sendall(file_head)
            # 异步获取自己的系统信息
            thread = MyThread(get_sys_info)
            thread.start()
            # 接收对方的系统信息
            data_length = size_fmt.unpack(receive_data(conn, size_fmt.size))[0]
            data = receive_data(conn, data_length).decode()
        peer_sysinfo = json.loads(data)
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
        file_head = pack_filehead('', COMMAND.SPEEDTEST, data_size)
        with self.__connections as conn:
            conn.sendall(file_head)
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
                    receive_data(conn, data_unit)
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

    def __send_files_in_dir(self, filepath):
        all_dir_name, all_file_name = get_dir_file_name(filepath)
        data = json.dumps({'num': len(all_dir_name), 'dir_names': '|'.join(all_dir_name)}).encode()
        self.__connections.main_conn.sendall(pack_filehead('', COMMAND.SEND_FILES_IN_DIR, len(data)))
        self.logger.info('开始发送 {} 路径下所有文件夹，文件夹个数为 {}'.format(filepath, len(all_dir_name)))
        self.logger.flush()
        self.__connections.main_conn.sendall(data)
        del data
        self.__base_dir = os.path.dirname(filepath)
        for dir_name in all_dir_name:
            self.logger.log_file.write(f'{Path(self.__base_dir, dir_name)}\n')
        # 将待发送的文件打印到日志
        self.logger.log_file.write('\n[INFO   ] ' + get_log_msg("本次待发送的文件列表为：\n"))
        total_size = 0
        for filename in all_file_name:
            real_path = Path(self.__base_dir, filename)
            file_size = os.path.getsize(real_path)
            sz1, sz2 = calcu_size(file_size)
            self.logger.log_file.write(f"{real_path}, 约{sz1}, {sz2}\n")
            total_size += file_size
        self.logger.log_file.write('\n')
        self.logger.log_file.flush()
        # 打乱列表以避免多个小文件聚簇在一起，影响效率
        random.shuffle(all_file_name)
        # 扩充连接和初始化线程池
        self.__connect(self.__threads)
        if self.__thread_pool is None:
            self.__thread_pool = ThreadPool(self.__threads)
        # 等待文件夹发送完成
        receive_data(self.__connections.main_conn, 1)
        self.logger.info('开始发送 {} 路径下所有文件，文件个数为 {}'.format(filepath, len(all_file_name)))
        # 初始化总进度条
        self.__pbar = tqdm(total=total_size, desc='累计发送量', unit='bytes',
                           unit_scale=True, mininterval=1, position=0, colour='#01579B')
        # 异步发送文件并等待结果
        results = [self.__thread_pool.apply_async(self.__send_file, (filename,)) for filename in all_file_name]
        # 比对发送成功或失败的文件
        success_recv = set()
        try:
            success_recv = set([result.get() for result in results])
            file_head = pack_filehead('', FINISH, 0)
            for conn in self.__connections.connections:
                conn.sendall(file_head)
        except ssl.SSLEOFError:
            self.logger.warning('文件传输超时')
        finally:
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
        file_size = os.path.getsize(real_path := os.path.normcase(Path(self.__base_dir, filepath)))
        # 从空闲的conn中取出一个使用
        with self.__connections as conn:
            conn.sendall(pack_filehead(filepath, COMMAND.SEND_FILE, file_size))
            flag = size_fmt.unpack(receive_data(conn, size_fmt.size))[0]
            if flag == CONTROL.CANCEL:
                self.__update_global_pbar(file_size, decrease=True)
            elif flag != CONTROL.FAIL2OPEN:
                try:
                    fp = open(real_path, 'rb')
                except FileNotFoundError:
                    self.logger.error(f'文件打开失败，无法发送: {real_path}', highlight=1)
                    conn.sendall(size_fmt.pack(CONTROL.FAIL2OPEN))
                    return
                # 服务端已有的文件大小
                fp.seek(exist_size := flag, 0)
                conn.sendall(size_fmt.pack(CONTROL.CONTINUE))
                # 发送文件的创建、访问、修改时间戳
                conn.sendall(file_details_fmt.pack(os.path.getctime(real_path), os.path.getmtime(real_path),
                                                   os.path.getatime(real_path)))
                rest_size = file_size - exist_size
                if rest_size > unit:
                    position, leave = (self.__position.popleft(), False) if self.__pbar else (0, True)
                    pbar_width = get_terminal_size().columns / 4
                    pbar = tqdm(total=rest_size, desc=shorten_path(filepath, pbar_width), unit='bytes', unit_scale=True,
                                mininterval=1, position=position, leave=leave)
                    while data := fp.read(unit):
                        conn.sendall(data)
                        pbar.update(data_size := len(data))
                        self.__update_global_pbar(data_size)
                    pbar.close()
                    self.__position.append(position)
                else:
                    # 小文件
                    conn.sendall(data := fp.read(unit))
                    self.__update_global_pbar(len(data))
                fp.close()
                self.__update_global_pbar(exist_size, decrease=True)
            else:
                self.logger.error(f'对方接收文件失败：{real_path}', highlight=1)
                return
        return filepath

    def __validate_password(self, conn):
        conn.sendall(pack_filehead(self.__password, COMMAND.BEFORE_WORKING, self.__session_id))
        msg, _, session_id = recv_filehead(conn)
        return msg, session_id

    def __before_working(self):
        with self.__connections as conn:
            msg, session_id = self.__validate_password(conn)
        if msg == FAIL:
            self.logger.error('连接至服务器的密码错误', highlight=1)
            self.shutdown(send_close_info=False)
        else:
            self.logger.info(f'服务器所在平台: {msg}\n')
            self.__peer_platform = msg
            self.__command_prefix = 'powershell ' if self.__peer_platform == WINDOWS else ''
            self.__session_id = session_id

    def __probe_server(self, wait=1):
        if self.__host:
            splits = self.__host.split(":")
            if len(splits) == 2:
                config.server_port = int(splits[1])
                self.__host = splits[0]
            self.logger.log(f"目标主机: {self.__host}, 目标端口: {config.server_port}")
            return
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        ip, _ = get_ip_and_hostname()
        sk.bind((ip, config.client_signal_port))
        self.logger.log(f'开始探测服务器信息，最短探测时长：{wait}s.')
        content = f'HI-I-AM-FTC_{ip}_{config.client_signal_port}'.encode(utf8)
        broadcast_to_all_interfaces(sk, port=config.server_signal_port, content=content)
        begin = time.time()
        ip_use_ssl = {}
        while time.time() - begin < wait:
            try:
                data = sk.recv(1024).decode(utf8).split('_')
            except socket.timeout:
                break
            if data[0] == 'HI-I-AM-FTS':
                ip_use_ssl[data[1]] = data[2] == 'True'
            sk.settimeout(wait)
        sk.close()
        addresses = list(ip_use_ssl.keys())
        msg = ['当前可用主机列表：']
        msg += [f'ip: {address}, hostname: {get_hostname_by_ip(address)}, useSSL: {ip_use_ssl.get(address)}' for
                address in addresses]
        self.logger.log('\n'.join(msg))
        if len(addresses) == 1:
            self.__use_ssl = ip_use_ssl.get(addresses[0])
            self.__host = addresses[0]
            return
        hostname = input('请输入主机名/ip: ')
        self.__host = hostname
        self.__use_ssl = ip_use_ssl.get(hostname) if hostname in addresses \
            else input('开启 SSL(y/n)? ').lower() == 'y'

    def shutdown(self, send_close_info=True):
        if self.__thread_pool:
            self.logger.info('关闭线程池')
            self.__thread_pool.terminate()
        close_info = pack_filehead('', COMMAND.CLOSE, 0)
        self.logger.info('断开与 {0}:{1} 的连接'.format(self.__host, config.server_port))
        try:
            for conn in self.__connections.connections:
                if send_close_info:
                    conn.sendall(close_info)
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
        additional_connections_nums = nums - len(self.__connections.connections)
        if additional_connections_nums <= 0:
            return
        try:
            context = None
            if self.__use_ssl:
                # 生成SSL上下文
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                # 加载信任根证书
                context.load_verify_locations(Path(config.cert_dir, 'ca.crt'))
            for i in range(0, additional_connections_nums):
                try:
                    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    # 连接至服务器
                    client_socket.connect((self.__host, config.server_port))
                    # 将socket包装为securitySocket
                    if self.__use_ssl:
                        client_socket = context.wrap_socket(client_socket, server_hostname='FTS')
                    # 验证密码
                    if not self.__first_connect:
                        self.__validate_password(client_socket)
                    # client_socket = context.wrap_socket(s, server_hostname='Server')
                    self.__connections.add(client_socket)
                except ssl.SSLError as e:
                    self.logger.error('连接至 {0} 失败，{1}'.format(self.__host, e.verify_message), highlight=1)
                    sys.exit(-1)
            if self.__first_connect:
                self.logger.success(f'成功连接至服务器 {self.__host}:{config.server_port}')
                self.logger.success('当前数据使用加密传输') if self.__use_ssl else self.logger.warning(
                    '当前数据未进行加密传输')
                self.__first_connect = False
            else:
                self.logger.info(f'将连接数扩充至: {nums}')
        except socket.error as msg:
            self.logger.error(f'连接至 {self.__host} 失败, {msg}')
            sys.exit(-1)

    def start(self):
        self.__probe_server()
        self.__connect()
        self.logger.info('当前线程数：{}'.format(self.__threads))
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
                elif command == COMMAND.SYSINFO:
                    self.__compare_sysinfo()
                elif command.startswith(COMMAND.SPEEDTEST):
                    self.__speedtest(times=command[10:])
                elif command.startswith(COMMAND.COMPARE):
                    local_dir, destination_dir = split_dir(command)
                    if not destination_dir or not local_dir:
                        self.logger.warning('本地文件夹且远程文件夹不能为空')
                        continue
                    self.__compare_dir(local_dir, destination_dir)
                elif command.endswith('clipboard'):
                    self.__exchange_clipboard(command.split()[0])
                elif command.startswith(COMMAND.HISTORY):
                    print_history(int(command.split()[1])) if len(command.split()) > 1 and command.split()[
                        1].isdigit() else print_history()
                else:
                    self.__execute_command(command)
            except ConnectionResetError as e:
                self.logger.error(e.strerror, highlight=1)
                self.logger.close()
                if packaging:
                    os.system('pause')
                sys.exit(-1)


if __name__ == '__main__':
    args = get_args()
    # 启动FTC服务
    ftc = FTC(threads=args.t, host=args.host, use_ssl=not args.plaintext, password=args.password)
    handle_ctrl_event(logger=ftc.logger)
    ftc.start()
    if packaging:
        os.system('pause')
