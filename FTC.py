import argparse
import json
import random
import socket
import ssl
from multiprocessing.pool import ThreadPool
from secrets import token_bytes

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


def split_dir(command):
    dirnames = command[8:].split('"')
    dirnames = dirnames[0].split(' ') if len(dirnames) == 1 else \
        [dirname.strip() for dirname in dirnames if dirname.strip()]
    return dirnames if len(dirnames) == 2 else (None, None)


class FTC:
    def __init__(self, threads, host, use_ssl, password=''):
        self.__peer_platform = None
        self.__password = password
        self.__use_ssl = use_ssl
        self.__pbar = None
        self.host = host
        self.threads = threads
        self.__log_lock = threading.Lock()
        self.__connections = self.Connections()
        self.__base_dir = ''
        self.__process_lock = threading.Lock()
        self.__position = 0
        self.__first_connect = True
        log_file = os.path.join(config.log_dir, datetime.now().strftime('%Y_%m_%d') + '_client.log')
        self.__log_file = open(log_file, 'a', encoding='utf-8')
        self.log('本次日志文件存放位置为: ' + log_file.replace('/', os.path.sep))
        # 进行日志归档
        threading.Thread(target=compress_log_files, args=(config.log_dir, 'client', self.log)).start()
        self.__thread_pool = None

    class Connections:
        def __init__(self):
            self.__conn_pool_ready = []
            self.__conn_pool_working = {}
            self.__lock = threading.Lock()

        def __enter__(self):
            # 从空闲的conn中取出一个使用
            with self.__lock:
                conn = self.__conn_pool_ready.pop()
                self.__conn_pool_working.update({threading.current_thread().ident: conn})
            return conn

        def get_connections(self):
            return self.__conn_pool_ready + list(self.__conn_pool_working.values())

        def add(self, conn):
            self.__conn_pool_ready.append(conn)

        def __exit__(self, exc_type, exc_val, exc_tb):
            # conn使用完毕，回收conn
            with self.__lock:
                conn = self.__conn_pool_working.pop(threading.current_thread().ident)
                self.__conn_pool_ready.append(conn)

    def connect(self, nums=1):
        """
        将现有的连接数量扩充至nums

        @param nums: 需要扩充到的连接数
        @return:
        """
        additional_connections_nums = nums - len(self.__connections.get_connections())
        if additional_connections_nums <= 0:
            return
        try:
            if self.__use_ssl:
                # 生成SSL上下文
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                # 加载信任根证书
                context.load_verify_locations(os.path.join(config.cert_dir, 'ca.crt'))
                for i in range(0, additional_connections_nums):
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        # 连接至服务器
                        s.connect((self.host, config.server_port))
                        # 将socket包装为securitySocket
                        ss = context.wrap_socket(s, server_hostname='FTS')
                        # 验证密码
                        if not self.__first_connect:
                            self.validate_password(ss)
                        # ss = context.wrap_socket(s, server_hostname='Server')
                        self.__connections.add(ss)
                    except ssl.SSLError as e:
                        self.log('连接至 {0} 失败，{1}'.format(self.host, e.verify_message), 'red', highlight=1)
                        sys.exit(-1)
            else:
                for i in range(0, additional_connections_nums):
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.connect((self.host, config.server_port))
                    # 验证密码
                    if not self.__first_connect:
                        self.validate_password(s)
                    self.__connections.add(s)
            if self.__first_connect:
                self.log(f'成功连接至服务器 {self.host}:{config.server_port}', 'green')
                if self.__use_ssl:
                    self.log('当前数据使用加密传输', 'green')
                else:
                    self.log('当前数据未进行加密传输', 'yellow')
                self.__first_connect = False
            else:
                self.log(f'将连接数扩充至: {nums}', color='blue')
        except socket.error as msg:
            self.log(f'连接至 {self.host} 失败, {msg}', 'red')
            sys.exit(-1)

    def validate_password(self, conn):
        filehead = struct.pack(fmt, self.__password.encode(), BEFORE_WORKING.encode(), 0)
        conn.send(filehead)
        filehead = receive_data(conn, fileinfo_size)
        msg = struct.unpack(fmt, filehead)[0]
        msg = msg.decode('UTF-8').strip('\00')
        return msg

    def probe_server(self, wait=1):
        if self.host:
            splits = self.host.split(":")
            if len(splits) == 2:
                config.server_port = int(splits[1])
                self.host = splits[0]
            self.log("目标主机: " + self.host + ", 目标端口: " + str(config.server_port))
            return
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        local_host = socket.gethostname()
        ip = socket.gethostbyname(local_host)
        sk.bind((ip, config.client_signal_port))
        ip_list = {}
        self.log('开始探测服务器信息，最短探测时长：{0}s.'.format(wait))
        content = ('53b997bc-a140-11ed-a8fc-0242ac120002_' + ip).encode('UTF-8')
        addr = (ip[0:ip.rindex('.')] + '.255', config.server_signal_port)
        sk.sendto(content, addr)
        begin = time.time()
        while time.time() - begin < wait:
            try:
                data = sk.recv(1024).decode('UTF-8').split('_')
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

    def log(self, msg, color='white', highlight=0):
        msg = get_log_msg(msg)
        with self.__log_lock:
            print_color(msg=msg, color=color, highlight=highlight)
            self.__log_file.write('[{}] {}\n'.format(color_level_dict.get(color, 'INFO'), msg))

    def close_connection(self, send_close_info=True):
        if self.__thread_pool:
            self.log('关闭线程池', 'blue')
            self.__thread_pool.terminate()
        close_info = struct.pack(fmt, b'', CLOSE.encode(), 0)
        self.log('断开与 {0}:{1} 的连接'.format(self.host, config.server_port), 'blue')
        try:
            for conn in self.__connections.get_connections():
                if send_close_info:
                    conn.send(close_info)
                # time.sleep(random.randint(0, 50) / 100)
                conn.close()
        finally:
            with self.__log_lock:
                self.__log_file.close()

    def _send_dir(self, dirname):
        filehead = struct.pack(fmt, dirname.encode('UTF-8'), SEND_DIR.encode(), 0)
        with self.__connections as conn:
            conn.send(filehead)

    def _send_file(self, filepath):
        real_path = os.path.join(self.__base_dir, filepath)
        # 定义文件头信息，包含文件名和文件大小
        file_size = os.stat(real_path).st_size
        filehead = struct.pack(fmt, filepath.encode('UTF-8'),
                               SEND_FILE.encode(), file_size)
        # 从空闲的conn中取出一个使用
        with self.__connections as conn:
            conn.send(filehead)
            is_continue = receive_data(conn, 8).decode('UTF-8') == CONTINUE
            if is_continue:
                md5 = hashlib.md5()
                with self.__process_lock:
                    position = self.__position
                    self.__position += 1
                with open(real_path, 'rb') as fp:
                    # self.log('开始发送文件')
                    with tqdm(total=file_size, desc=filepath, unit='bytes', unit_scale=True, mininterval=1,
                              position=position) as pbar:
                        data = fp.read(unit)
                        while data:
                            conn.send(data)
                            md5.update(data)
                            pbar.update(len(data))
                            if self.__pbar:
                                with self.__process_lock:
                                    self.__pbar.update(len(data))
                            data = fp.read(unit)
                conn.send(md5.digest())
                filepath = receive_data(conn, filename_size)
                filepath = filepath.decode('UTF-8').strip('\00')
            else:
                if self.__pbar:
                    with self.__process_lock:
                        self.__pbar.update(file_size)
        return filepath

    def main(self):
        self.log('当前线程数：{}'.format(self.threads), 'blue')
        self.__peer_platform = self._before_working()
        while True:
            tips = '请输入命令：'
            command = input(tips)
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
                elif command.startswith("compare"):
                    local_dir, dest_dir = split_dir(command)
                    if not dest_dir or not local_dir:
                        self.log('本地文件夹且远程文件夹不能为空', color='yellow')
                        continue
                    self._compare_dir(local_dir, dest_dir)
                elif command.startswith('clip '):
                    self.__exchange_clipboard(command.split()[1])
                else:
                    self._execute_command(command)
            except ConnectionResetError as e:
                self.log(e.strerror, color='red', highlight=1)
                if packaging:
                    os.system('pause')
                sys.exit(-1)
            except FileNotFoundError as e:
                self.log(f'文件路径太长(Windows限制文件绝对路径长度在250左右): {e.filename}', color='red', highlight=1)

    def _send_files_in_dir(self, filepath):
        self.connect(self.threads)
        # 每次发送文件夹时将进度条位置初始化
        self.__position = 0
        self.__base_dir = os.path.dirname(filepath)
        all_dir_name, all_file_name = get_dir_file_name(filepath)
        self.log('开始发送 {} 路径下所有文件夹，文件夹个数为 {}\n'.format(filepath, len(all_dir_name)), 'blue')
        # start = time.time()
        if self.__thread_pool is None:
            self.__thread_pool = ThreadPool(self.threads)
        results = [self.__thread_pool.apply_async(self._send_dir, (dirname,)) for dirname in all_dir_name]
        # 打乱列表以避免多个小文件聚簇在一起，影响效率
        random.shuffle(all_file_name)
        # 将待发送的文件打印到日志
        self.__log_file.write('[INFO] ' + get_log_msg("本次待发送的文件列表为：\n"))
        total_size = 0
        for filename in all_file_name:
            real_path = os.path.join(self.__base_dir, filename)
            file_size = os.stat(real_path).st_size
            sz1, sz2 = calcu_size(file_size)
            self.__log_file.write('[INFO] ' + get_log_msg(f"{real_path}, 约{sz1}, {sz2}\n"))
            total_size += file_size
        self.__log_file.flush()
        # 初始化总进度条
        with self.__process_lock:
            self.__pbar = tqdm(total=total_size, desc='累计发送量', unit='bytes',
                               unit_scale=True, mininterval=1, position=0)
            self.__position += 1
        # 等待文件夹发送完成
        for result in results:
            result.wait()
        # self.log('文件夹发送完毕，耗时 {} s'.format(round(time.time() - start, 2)), 'blue')
        self.log('开始发送 {} 路径下所有文件，文件个数为 {}\n'.format(filepath, len(all_file_name)), 'blue')
        # 异步发送文件并等待结果
        results = [self.__thread_pool.apply_async(self._send_file, (filename,)) for filename in all_file_name]
        # 比对发送成功或失败的文件
        success_recv = []
        try:
            for result in results:
                result.wait()
                success_recv.append(result.get())
        except Exception as e:
            print(e)
        finally:
            self.__pbar.close()
            self.__pbar = None
            fails = set(all_file_name) - set(success_recv)
            if fails:
                self.log("发送失败的文件：", color="red", highlight=1)
                for fail in fails:
                    self.log(fail, color='yellow')
            else:
                self.log("本次全部文件正常发送", color='green')

    def _send_single_file(self, filepath):
        self.__log_file.write("[INFO] 本次发送的文件: {}\n".format(filepath))
        self.__base_dir = os.path.dirname(filepath)
        filepath = os.path.basename(filepath)
        self.log("发送成功", color='green') if filepath == self._send_file(filepath) \
            else self.log("发送失败", color='red')

    def _compare_dir(self, local_dir, dest_dir):
        if not os.path.exists(local_dir):
            self.log('本地文件夹不存在', color='yellow')
            return
        filehead = struct.pack(fmt, dest_dir.encode("UTF-8"), COMPARE_DIR.encode(), 0)
        with self.__connections as conn:
            conn.send(filehead)
            is_dir_correct = receive_data(conn, len(DIRISCORRECT))
            is_dir_correct = is_dir_correct.decode() == DIRISCORRECT
            if is_dir_correct:
                local_dict = get_relative_filename_from_basedir(local_dir)
                # 获取本地的文件名
                local_filename = local_dict.keys()
                # 获取本次字符串大小
                data_size = receive_data(conn, str_len_size)
                data_size = struct.unpack(str_len_fmt, data_size)[0]
                # 接收字符串
                data = receive_data(conn, data_size).decode()
                # 将字符串转化为dict
                dest_dict = json.loads(data)
                dest_filename = dest_dict.keys()

                # 求各种集合
                file_in_local_smaller_than_dest = []
                file_in_dest_smaller_than_local = []
                filesize_and_name_both_equal = []
                for filename in local_filename:
                    size_diff = local_dict[filename] - dest_dict[filename]
                    if size_diff < 0:
                        file_in_local_smaller_than_dest.append(filename)
                    elif size_diff == 0:
                        filesize_and_name_both_equal.append(filename)
                    else:
                        file_in_dest_smaller_than_local.append(filename)

                file_not_exits_in_local = [filename for filename in dest_filename if filename not in local_filename]
                file_not_exits_in_dest = [filename for filename in local_filename if filename not in dest_dict]
                for arg in [("file exits in dest but not exits in local: ", file_not_exits_in_local),
                            ("file exits in local but not exits in dest: ", file_not_exits_in_dest),
                            ("file in local smaller than dest: ", file_in_local_smaller_than_dest),
                            ("file in dest smaller than local: ", file_in_dest_smaller_than_local),
                            ("filename and size both equal in two sides: ", filesize_and_name_both_equal)]:
                    print_filename_if_exits(*arg)

                if filesize_and_name_both_equal:
                    is_continue = input("Continue to compare hash for filename and size both equal set?(y/n): ") == 'y'
                    if is_continue:
                        # 发送继续请求
                        conn.send(CONTINUE.encode())
                        # 发送相同的文件名称大小
                        data_to_send = "|".join(filesize_and_name_both_equal).encode("UTF-8")
                        conn.send(struct.pack(str_len_fmt, len(data_to_send)))
                        # 发送字符串
                        conn.send(data_to_send)
                        results = {filename: get_file_md5(os.path.join(local_dir, filename)) for filename in
                                   filesize_and_name_both_equal}
                        # 获取本次字符串大小
                        data_size = receive_data(conn, str_len_size)
                        data_size = struct.unpack(str_len_fmt, data_size)[0]
                        # 接收字符串
                        data = receive_data(conn, data_size).decode()
                        # 将字符串转化为dict
                        dest_dict = json.loads(data)
                        hash_not_matching = [filename for filename in results.keys() if
                                             results[filename] != dest_dict[filename]]
                        print_filename_if_exits("hash not matching: ", hash_not_matching)
                    else:
                        conn.send(CANCEL.encode())
                else:
                    conn.send(CANCEL.encode())
            else:
                self.log(f"目标文件夹 {dest_dir} 不存在", color="yellow")

    def _execute_command(self, command):
        command = command.strip()
        # 防止命令将输入端交给服务器
        if len(command) == 0:
            return
        if self.__peer_platform == WINDOWS and (command.startswith('cmd') or command == 'powershell'):
            self.log('请不要将输入端交给服务器！', color='yellow')
            return
        command = command.encode("UTF-8")
        if len(command) > filename_size:
            self.log("指令过长", color='yellow')
            return

        with self.__connections as conn:
            filehead = struct.pack(fmt, command, COMMAND.encode(), len(command))
            conn.send(filehead)
            with self.__log_lock:
                self.__log_file.write('[INFO] ' + get_log_msg(f'下达指令: {command}\n'))
            # 接收返回结果
            result = receive_data(conn, 8)
            while result != b'\00' * 8:
                print(result.decode('UTF-32'), end='')
                result = receive_data(conn, 8)

    def _compare_sysinfo(self):
        # 发送比较系统信息的命令到FTS
        filehead = struct.pack(fmt, b'', SYSINFO.encode(), 0)
        with self.__connections as conn:
            conn.send(filehead)
            # 异步获取自己的系统信息
            t = MyThread(get_sys_info, args=())
            t.start()
            # 接收对方的系统信息
            data_length = struct.unpack(str_len_fmt, receive_data(conn, str_len_size))[0]
            data = receive_data(conn, data_length).decode()
        dest_sysinfo = json.loads(data)
        print_sysinfo(dest_sysinfo)
        # 等待本机系统信息获取完成
        t.join()
        local_sysinfo = t.get_result()
        print_sysinfo(local_sysinfo)

    def _speedtest(self, times):
        data_unit = 1000 * 1000  # 1MB
        data_size = times * data_unit
        filehead = struct.pack(fmt, b'', SPEEDTEST.encode(), data_size)
        with self.__connections as conn:
            conn.send(filehead)
            with tqdm(total=data_size, desc='speedtest', unit='bytes', unit_scale=True, mininterval=1) as pbar:
                for i in range(0, times):
                    # 生产随机字节
                    conn.send(token_bytes(data_unit))
                    pbar.update(data_unit)

    def _before_working(self):
        with self.__connections as conn:
            msg = self.validate_password(conn)
        if msg == FAIL:
            self.log('连接至服务器的密码错误', color='red', highlight=1)
            self.close_connection(send_close_info=False)
            sys.exit(-1)
        else:
            self.log('服务器所在平台: ' + msg, color='blue')
            return msg

    def __exchange_clipboard(self, command):
        """
        交换（发送，获取）对方剪切板内容

        @param command: get 或 send
        @return:
        """
        with self.__connections as conn:
            if command == SEND or command == PUSH:
                send_clipboard(conn, self.log)
            elif command == GET or command == PULL:
                get_clipboard(conn, self.log)


if __name__ == '__main__':
    # 添加命令行参数
    parser = argparse.ArgumentParser(description='File Transfer Client, used to SEND files and instructions.')
    logical_cpu_count = psutil.cpu_count(logical=True)
    parser.add_argument('-t', metavar='thread', type=int,
                        help=f'threads (default: {logical_cpu_count})', default=logical_cpu_count)
    parser.add_argument('-host', metavar='host',
                        help='destination hostname or ip address', default='')
    parser.add_argument('-p', '--password', metavar='password', type=str,
                        help='Use a password to connect host.', default='')
    parser.add_argument('--plaintext', action='store_true',
                        help='Use plaintext transfer (default: use ssl)')
    args = parser.parse_args()
    handle_ctrl_event()
    # 启动FTC服务
    ftc = FTC(threads=args.t, host=args.host, use_ssl=not args.plaintext, password=args.password)
    ftc.probe_server()
    if not packaging:
        ftc.connect()
        ftc.main()
    else:
        try:
            ftc.connect()
            ftc.main()
        finally:
            os.system('pause')
