import argparse
import json
import os.path
import random
import ssl
from multiprocessing.pool import ThreadPool
from secrets import token_bytes

import readline
from tqdm import tqdm

from Utils import *
from sys_info import *


def print_filename_if_exits(prompt, filename_list):
    print(prompt)
    if filename_list:
        for filename in filename_list:
            print('\t' + filename)
    else:
        print('\tNone')


def print_history(nums=10):
    current_history_length = readline.get_current_history_length()
    start_index = current_history_length - nums + 1 if current_history_length > nums else 1
    for i in range(start_index, current_history_length + 1):
        print(readline.get_history_item(i))


def completer(text, state):
    options = [i for i in commands if i.startswith(text)]
    return options[state] if state < len(options) else None


def split_dir(command):
    dir_names = command[8:].split('"')
    dir_names = dir_names[0].split(' ') if len(dir_names) == 1 else \
        [dir_name.strip() for dir_name in dir_names if dir_name.strip()]
    return dir_names if len(dir_names) == 2 else (None, None)


class FTC:
    def __init__(self, threads, host, use_ssl, password=''):
        self.__peer_platform = None
        self.__password = password
        self.__use_ssl = use_ssl
        self.__pbar = None
        self.host = host
        self.threads = threads
        self.__connections = self.Connections()
        self.__base_dir = ''
        self.__process_lock = threading.Lock()
        self.__position = 0
        self.__first_connect = True
        log_file = os.path.normcase(os.path.join(config.log_dir, datetime.now().strftime('%Y_%m_%d') + '_client.log'))
        self.logger = Logger(log_file)
        self.logger.log('本次日志文件存放位置为: ' + log_file)
        # 进行日志归档
        threading.Thread(target=compress_log_files, args=(config.log_dir, 'client', self.logger)).start()
        self.__thread_pool = None

    class Connections:
        def __init__(self):
            self.__conn_pool = []
            self.__thread_conn_map = {}
            self.__lock = threading.Lock()

        def __enter__(self):
            # 从空闲的conn中取出一个使用
            conn = self.__thread_conn_map.get(threading.current_thread().name, None)
            if not conn:
                with self.__lock:
                    conn = self.__conn_pool.pop() if len(
                        self.__conn_pool) > 0 else self.__thread_conn_map.get('MainThread')
                    self.__thread_conn_map[threading.current_thread().name] = conn
            return conn

        @property
        def connections(self):
            return set(self.__thread_conn_map.values())

        def add(self, conn):
            self.__conn_pool.append(conn)

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    def connect(self, nums=1):
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
                context.load_verify_locations(os.path.join(config.cert_dir, 'ca.crt'))
            for i in range(0, additional_connections_nums):
                try:
                    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    # 连接至服务器
                    client_socket.connect((self.host, config.server_port))
                    # 将socket包装为securitySocket
                    if self.__use_ssl:
                        client_socket = context.wrap_socket(client_socket, server_hostname='FTS')
                    # 验证密码
                    if not self.__first_connect:
                        self.validate_password(client_socket)
                    # client_socket = context.wrap_socket(s, server_hostname='Server')
                    self.__connections.add(client_socket)
                except ssl.SSLError as e:
                    self.logger.error('连接至 {0} 失败，{1}'.format(self.host, e.verify_message), highlight=1)
                    sys.exit(-1)
            if self.__first_connect:
                self.logger.success(f'成功连接至服务器 {self.host}:{config.server_port}')
                if self.__use_ssl:
                    self.logger.success('当前数据使用加密传输')
                else:
                    self.logger.warning('当前数据未进行加密传输')
                self.__first_connect = False
            else:
                self.logger.info(f'将连接数扩充至: {nums}')
        except socket.error as msg:
            self.logger.error(f'连接至 {self.host} 失败, {msg}')
            sys.exit(-1)

    def validate_password(self, conn):
        file_head = struct.pack(FMT.head_fmt.value, self.__password.encode(), BEFORE_WORKING.encode(), 0)
        conn.sendall(file_head)
        file_head = receive_data(conn, FMT.head_fmt.size)
        msg = struct.unpack(FMT.head_fmt.value, file_head)[0]
        msg = msg.decode(utf8).strip('\00')
        return msg

    def probe_server(self, wait=1):
        if self.host:
            splits = self.host.split(":")
            if len(splits) == 2:
                config.server_port = int(splits[1])
                self.host = splits[0]
            self.logger.log(f"目标主机: {self.host}, 目标端口: {config.server_port}")
            return
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        local_host = socket.gethostname()
        ip = socket.gethostbyname(local_host)
        sk.bind((ip, config.client_signal_port))
        ip_list = {}
        self.logger.log('开始探测服务器信息，最短探测时长：{0}s.'.format(wait))
        content = ('53b997bc-a140-11ed-a8fc-0242ac120002_' + ip).encode(utf8)
        addr = (ip[0:ip.rindex('.')] + '.255', config.server_signal_port)
        sk.sendto(content, addr)
        begin = time.time()
        while time.time() - begin < wait:
            try:
                data = sk.recv(1024).decode(utf8).split('_')
            except socket.timeout:
                break
            if data[0] == '04c8979a-a107-11ed-a8fc-0242ac120002':
                server_ip = data[1]
                use_ssl = data[2] == 'True'
                if server_ip not in ip_list.keys():
                    ip_list.update({server_ip: use_ssl})
            sk.settimeout(wait)
        sk.close()
        all_ip = ip_list.keys()
        ip_num = len(all_ip)
        print('当前可用主机列表：')
        for ip in all_ip:
            hostname = 'unknown'
            try:
                hostname = socket.gethostbyaddr(ip)[0]
            finally:
                print('ip: {}, hostname: {}, useSSL: {}'.format(ip, hostname, ip_list.get(ip)))
                if ip_num == 1:
                    hostname = ip
                    self.__use_ssl = ip_list.get(ip)
                    self.host = hostname
                    break
        if ip_num > 1:
            hostname = input('请输入主机名/ip: ')
            self.host = hostname
            self.__use_ssl = ip_list.get(ip) if hostname in all_ip \
                else input('开启 SSL(y/n)? ').lower() == 'y'

    def close_connection(self, send_close_info=True):
        if self.__thread_pool:
            self.logger.info('关闭线程池')
            self.__thread_pool.terminate()
        close_info = struct.pack(FMT.head_fmt.value, b'', CLOSE.encode(), 0)
        self.logger.info('断开与 {0}:{1} 的连接'.format(self.host, config.server_port))
        try:
            for conn in self.__connections.connections:
                if send_close_info:
                    conn.sendall(close_info)
                # time.sleep(random.randint(0, 50) / 100)
                conn.close()
        finally:
            self.logger.close()

    def _send_dir(self, dir_name):
        file_head = struct.pack(FMT.head_fmt.value, dir_name.encode(utf8), SEND_DIR.encode(), 0)
        with self.__connections as conn:
            conn.sendall(file_head)

    def _send_file(self, filepath):
        real_path = os.path.normcase(os.path.join(self.__base_dir, filepath))
        # 定义文件头信息，包含文件名和文件大小
        file_size = os.stat(real_path).st_size
        file_head = struct.pack(FMT.head_fmt.value, filepath.encode(utf8), SEND_FILE.encode(), file_size)
        # 从空闲的conn中取出一个使用
        with self.__connections as conn:
            conn.sendall(file_head)
            flag = struct.unpack(FMT.size_fmt.value, receive_data(conn, FMT.size_fmt.size))[0]
            if flag == Control.CANCEL:
                if self.__pbar:
                    with self.__process_lock:
                        self.__pbar.update(file_size)
            elif flag == Control.TOOLONG:
                self.logger.error(f'对方因文件路径太长无法接收文件', highlight=1)
                return
            else:
                fp = openfile_with_retires(real_path, 'rb')
                if not fp:
                    self.logger.error(f'文件路径太长，无法接收: {real_path}', highlight=1)
                    conn.sendall(struct.pack(FMT.size_fmt.value, Control.TOOLONG))
                    return
                size = flag
                if size > 4:
                    size -= 4
                    fp.seek(size, 0)
                    file_size = file_size - size
                conn.sendall(struct.pack(FMT.size_fmt.value, Control.CONTINUE))
                conn.sendall(struct.pack(FMT.file_details_fmt.value, *get_file_time_details(real_path)))
                big_file = file_size > 1024 * 1024
                if big_file:  # 小文件不画进度条
                    with self.__process_lock:
                        position = self.__position
                        self.__position += 1
                    pbar = tqdm(total=file_size, desc=shorten_path(filepath, pbar_width), unit='bytes', unit_scale=True,
                                mininterval=1, position=position)
                data = fp.read(unit)
                while data:
                    conn.sendall(data)
                    if big_file:
                        pbar.update(len(data))
                    if self.__pbar:
                        with self.__process_lock:
                            self.__pbar.update(len(data))
                    data = fp.read(unit)
                if self.__pbar:
                    with self.__process_lock:
                        self.__pbar.update(size)
                if big_file:
                    pbar.close()
                fp.close()
        return filepath

    def main(self):
        self.logger.info('当前线程数：{}'.format(self.threads))
        self.__peer_platform = self._before_working()
        while True:
            tips = '请输入命令：'
            command = input(tips)
            readline.add_history(command)
            try:
                if command in ['q', 'quit', 'exit']:
                    self.close_connection()
                    return
                elif os.path.isdir(command) and os.path.exists(command):
                    self._send_files_in_dir(command)
                elif os.path.isfile(command) and os.path.exists(command):
                    self._send_single_file(command)
                elif command == SYSINFO:
                    self._compare_sysinfo()
                elif command.startswith(SPEEDTEST):
                    times = command[10:]
                    while not (times.isdigit() and int(times) > 0):
                        times = input("请重新输入数据量（单位MB）：")
                    self._speedtest(times=int(times))
                elif command.startswith(COMPARE):
                    local_dir, destination_dir = split_dir(command)
                    if not destination_dir or not local_dir:
                        self.logger.warning('本地文件夹且远程文件夹不能为空')
                        continue
                    self._compare_dir(local_dir, destination_dir)
                elif command.startswith(CLIP + ' '):
                    self.__exchange_clipboard(command.split()[1])
                elif command.startswith(HISTORY):
                    if len(command.split()) > 1 and command.split()[1].isdigit():
                        print_history(int(command.split()[1]))
                    else:
                        print_history()
                else:
                    self._execute_command(command)
            except ConnectionResetError as e:
                self.logger.error(e.strerror, highlight=1)
                if packaging:
                    os.system('pause')
                sys.exit(-1)

    def _send_files_in_dir(self, filepath):
        self.connect(self.threads)
        # 每次发送文件夹时将进度条位置初始化
        self.__position = 0
        self.__base_dir = os.path.dirname(filepath)
        all_dir_name, all_file_name = get_dir_file_name(filepath)
        self.logger.info('开始发送 {} 路径下所有文件夹，文件夹个数为 {}\n'.format(filepath, len(all_dir_name)))
        # start = time.time()
        if self.__thread_pool is None:
            self.__thread_pool = ThreadPool(self.threads)
        results = [self.__thread_pool.apply_async(self._send_dir, (dir_name,)) for dir_name in all_dir_name]
        # 打乱列表以避免多个小文件聚簇在一起，影响效率
        random.shuffle(all_file_name)
        # 将待发送的文件打印到日志
        self.logger.log("本次待发送的文件列表为：\n", screen=False)
        total_size = 0
        for filename in all_file_name:
            real_path = os.path.join(self.__base_dir, filename)
            file_size = os.stat(real_path).st_size
            sz1, sz2 = calcu_size(file_size)
            self.logger.log(f"{real_path}, 约{sz1}, {sz2}", screen=False)
            total_size += file_size
        # 初始化总进度条
        with self.__process_lock:
            self.__pbar = tqdm(total=total_size, desc='累计发送量', unit='bytes',
                               unit_scale=True, mininterval=1, position=0)
            self.__position += 1
        # 等待文件夹发送完成
        for result in results:
            result.wait()
        # self.log('文件夹发送完毕，耗时 {} s'.format(round(time.time() - start, 2)), 'blue')
        self.logger.info('开始发送 {} 路径下所有文件，文件个数为 {}\n'.format(filepath, len(all_file_name)))
        # 异步发送文件并等待结果
        results = [self.__thread_pool.apply_async(self._send_file, (filename,)) for filename in all_file_name]
        # 比对发送成功或失败的文件
        success_recv = []
        try:
            for result in results:
                result.wait()
                success_recv.append(result.get())
        finally:
            self.__pbar.close()
            self.__pbar = None
            fails = set(all_file_name) - set(success_recv)
            if fails:
                self.logger.error("发送失败的文件：", highlight=1)
                for fail in fails:
                    self.logger.warning(fail)
            else:
                self.logger.success("本次全部文件正常发送")

    def _send_single_file(self, filepath):
        self.logger.log(f'本次发送的文件: {filepath}\n', screen=False)
        self.__base_dir = os.path.dirname(filepath)
        filepath = os.path.basename(filepath)
        self.logger.success("发送成功") if filepath == self._send_file(filepath) \
            else self.logger.error("发送失败")

    def _compare_dir(self, local_dir, peer_dir):
        if not os.path.exists(local_dir):
            self.logger.warning('本地文件夹不存在')
            return
        file_head = struct.pack(FMT.head_fmt.value, peer_dir.encode(utf8), COMPARE_DIR.encode(), 0)
        with self.__connections as conn:
            conn.sendall(file_head)
            is_dir_correct = receive_data(conn, len(DIRISCORRECT))
            is_dir_correct = is_dir_correct.decode() == DIRISCORRECT
            if is_dir_correct:
                local_dict = get_relative_filename_from_basedir(local_dir)
                # 获取本地的文件名
                local_filenames = local_dict.keys()
                # 获取本次字符串大小
                data_size = receive_data(conn, FMT.size_fmt.size)
                data_size = struct.unpack(FMT.size_fmt.value, data_size)[0]
                # 接收字符串
                data = receive_data(conn, data_size).decode()
                # 将字符串转化为dict
                peer_dict = json.loads(data)
                peer_filenames = peer_dict.keys()

                # 求各种集合
                file_in_local_smaller_than_peer = []
                file_in_peer_smaller_than_local = []
                file_size_and_name_both_equal = []
                for filename in local_filenames:
                    size_diff = local_dict[filename] - peer_dict[filename]
                    if size_diff < 0:
                        file_in_local_smaller_than_peer.append(filename)
                    elif size_diff == 0:
                        file_size_and_name_both_equal.append(filename)
                    else:
                        file_in_peer_smaller_than_local.append(filename)

                file_not_exits_in_local = [filename for filename in peer_filenames if filename not in local_filenames]
                file_not_exits_in_peer = [filename for filename in local_filenames if filename not in peer_dict]
                for arg in [("file exits in peer but not exits in local: ", file_not_exits_in_local),
                            ("file exits in local but not exits in peer: ", file_not_exits_in_peer),
                            ("file in local smaller than peer: ", file_in_local_smaller_than_peer),
                            ("file in peer smaller than local: ", file_in_peer_smaller_than_local),
                            ("file name and size both equal in two sides: ", file_size_and_name_both_equal)]:
                    print_filename_if_exits(*arg)

                if file_size_and_name_both_equal:
                    is_continue = input("Continue to compare hash for filename and size both equal set?(y/n): ") == 'y'
                    if is_continue:
                        # 发送继续请求
                        conn.sendall(struct.pack(FMT.size_fmt.value, Control.CONTINUE.value))
                        # 发送相同的文件名称大小
                        data_to_send = "|".join(file_size_and_name_both_equal).encode(utf8)
                        conn.sendall(struct.pack(FMT.size_fmt.value, len(data_to_send)))
                        # 发送字符串
                        conn.sendall(data_to_send)
                        results = {filename: get_file_md5(os.path.join(local_dir, filename)) for filename in
                                   file_size_and_name_both_equal}
                        # 获取本次字符串大小
                        data_size = receive_data(conn, FMT.size_fmt.size)
                        data_size = struct.unpack(FMT.size_fmt.value, data_size)[0]
                        # 接收字符串
                        data = receive_data(conn, data_size).decode()
                        # 将字符串转化为dict
                        peer_dict = json.loads(data)
                        hash_not_matching = [filename for filename in results.keys() if
                                             results[filename] != peer_dict[filename]]
                        print_filename_if_exits("hash not matching: ", hash_not_matching)
                    else:
                        conn.sendall(struct.pack(FMT.size_fmt.value, Control.CANCEL.value))
                else:
                    conn.sendall(struct.pack(FMT.size_fmt.value, Control.CANCEL.value))
            else:
                self.logger.warning(f"目标文件夹 {peer_dir} 不存在")

    def _execute_command(self, command):
        command = command.strip()
        # 防止命令将输入端交给服务器
        if len(command) == 0:
            return
        if self.__peer_platform == WINDOWS and (command.startswith('cmd') or command == 'powershell'):
            self.logger.warning('请不要将输入端交给服务器！')
            return
        command = command.encode(utf8)
        if len(command) > FMT.filename_fmt.size:
            self.logger.warning("指令过长")
            return

        with self.__connections as conn:
            file_head = struct.pack(FMT.head_fmt.value, command, COMMAND.encode(), len(command))
            conn.sendall(file_head)
            self.logger.log(f'下达指令: {command}\n', screen=False)
            # 接收返回结果
            result = receive_data(conn, 8)
            while result != b'\00' * 8:
                print(result.decode('UTF-32'), end='')
                result = receive_data(conn, 8)

    def _compare_sysinfo(self):
        # 发送比较系统信息的命令到FTS
        file_head = struct.pack(FMT.head_fmt.value, b'', SYSINFO.encode(), 0)
        with self.__connections as conn:
            conn.sendall(file_head)
            # 异步获取自己的系统信息
            t = MyThread(get_sys_info, args=())
            t.start()
            # 接收对方的系统信息
            data_length = struct.unpack(FMT.size_fmt.value, receive_data(conn, FMT.size_fmt.size))[0]
            data = receive_data(conn, data_length).decode()
        peer_sysinfo = json.loads(data)
        print_sysinfo(peer_sysinfo)
        # 等待本机系统信息获取完成
        t.join()
        local_sysinfo = t.get_result()
        print_sysinfo(local_sysinfo)

    def _speedtest(self, times):
        data_unit = 1000 * 1000  # 1MB
        data_size = times * data_unit
        file_head = struct.pack(FMT.head_fmt.value, b'', SPEEDTEST.encode(), data_size)
        with self.__connections as conn:
            conn.sendall(file_head)
            with tqdm(total=data_size, desc='speedtest', unit='bytes', unit_scale=True, mininterval=1) as pbar:
                for i in range(0, times):
                    # 生产随机字节
                    conn.sendall(token_bytes(data_unit))
                    pbar.update(data_unit)

    def _before_working(self):
        with self.__connections as conn:
            msg = self.validate_password(conn)
        if msg == FAIL:
            self.logger.error('连接至服务器的密码错误', highlight=1)
            self.close_connection(send_close_info=False)
            sys.exit(-1)
        else:
            self.logger.info('服务器所在平台: ' + msg)
            return msg

    def __exchange_clipboard(self, command):
        """
        交换（发送，获取）对方剪切板内容

        @param command: get 或 send
        @return:
        """
        with self.__connections as conn:
            if command == SEND or command == PUSH:
                send_clipboard(conn, self.logger)
            elif command == GET or command == PULL:
                get_clipboard(conn, self.logger)


if __name__ == '__main__':
    # 添加命令行参数
    parser = argparse.ArgumentParser(description='File Transfer Client, used to SEND files and instructions.')
    cpu_count = psutil.cpu_count(logical=False)
    parser.add_argument('-t', metavar='thread', type=int,
                        help=f'threads (default: {cpu_count})', default=cpu_count)
    parser.add_argument('-host', metavar='host',
                        help='destination hostname or ip address', default='')
    parser.add_argument('-p', '--password', metavar='password', type=str,
                        help='Use a password to connect host.', default='')
    parser.add_argument('--plaintext', action='store_true',
                        help='Use plaintext transfer (default: use ssl)')
    args = parser.parse_args()
    handle_ctrl_event()
    # 自动补全设置
    readline.set_completer(completer)
    readline.set_history_length(1000)
    readline.parse_and_bind('tab: complete')
    history_file = os.path.join(config.log_dir, 'history.txt')
    readline.read_history_file(history_file)
    # 启动FTC服务
    ftc = FTC(threads=args.t, host=args.host, use_ssl=not args.plaintext, password=args.password)
    ftc.probe_server()
    try:
        ftc.connect()
        ftc.main()
    finally:
        readline.write_history_file(history_file)
        if packaging:
            os.system('pause')
