import argparse
import random
import secrets
import socket
import ssl
import sys
from multiprocessing.pool import ThreadPool

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


class FTC:
    def __init__(self, thread_num, host, use_ssl):
        self.__use_ssl = use_ssl
        self.__pbar = None
        self.host = host
        self.threading_number = thread_num
        self.__conn_pool_ready = []
        self.__conn_pool_working = []
        self.__lock = threading.Lock()
        self.__thread_pool = ThreadPool(thread_num)
        self.__log_lock = threading.Lock()
        self.__base_dir = ''
        self.__process_lock = threading.Lock()
        self.__position = 0
        log_file = os.path.join(log_dir, datetime.now().strftime('%Y_%m_%d') + '_client.log')
        print('本次日志文件存放位置为: ' + log_file)
        self.__log_file = open(log_file, 'a', encoding='utf-8')

    def connect(self):
        try:
            if self.__use_ssl:
                # 生成SSL上下文
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                # 加载信任根证书
                context.load_verify_locations(os.path.join(cert_dir, 'ca.crt'))
                for i in range(0, self.threading_number):
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    # 连接至服务器
                    s.connect((self.host, server_port))
                    # 将socket包装为securitySocket
                    ss = context.wrap_socket(s, server_hostname='FTS')
                    self.__conn_pool_ready.append(ss)
            else:
                for i in range(0, self.threading_number):
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.connect((self.host, server_port))
                    self.__conn_pool_ready.append(s)

            self.log('成功连接至服务器 ({0}, {1})'.format(self.host, server_port), 'green')
            if self.__use_ssl:
                self.log('当前数据使用加密传输', 'green')
            else:
                self.log('当前数据未进行加密传输', 'yellow')
        except socket.error as msg:
            self.log('连接至 {0} 失败'.format(self.host), 'red')
            print(msg)
            sys.exit(1)

    def probe_server(self, wait):
        global server_port
        if self.host:
            splits = self.host.split(":")
            if len(splits) == 2:
                server_port = int(splits[1])
                self.host = splits[0]
            self.log("目标主机: " + self.host + ", 目标端口: " + str(server_port))
            return
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        local_host = socket.gethostname()
        ip = socket.gethostbyname(local_host)
        sk.bind((ip, client_signal_port))
        ip_list = {}
        self.log('开始探测服务器信息，最短探测时长：{0}s.'.format(wait))
        content = ('53b997bc-a140-11ed-a8fc-0242ac120002_' + ip).encode('UTF-8')
        addr = (ip[0:ip.rindex('.')] + '.255', server_signal_port)
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
                if server_ip not in ip_list:
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
            except:
                pass
            print('ip: {}, hostname: {}, useSSL: {}'.format(ip, hostname, ip_list.get(ip)))
            if ip_num == 1:
                hostname = ip
                self.__use_ssl = ip_list.get(ip)
                self.host = hostname
                break
        if ip_num > 1:
            hostname = input('请输入主机名/ip: ')
            self.host = hostname
            if hostname in all_ip:
                self.__use_ssl = ip_list.get(ip)
            else:
                self.__use_ssl = input('开启 SSL(y/n)? ') == 'y'

    def log(self, msg, color='white', highlight=0):
        msg = get_log_msg(msg)
        level = 'INFO'
        if color == 'yellow':
            level = 'WARNING'
        if color == 'red':
            level = 'ERROR'
        with self.__log_lock:
            print_color(msg=msg, color=color, highlight=highlight)
            self.__log_file.write('[{}] {}\n'.format(level, msg))

    def close_connection(self):
        self.log('关闭线程池', 'blue')
        self.__thread_pool.terminate()
        close_info = struct.pack(fmt, 'd1132ce8-7d22-434d-a4e9-75d81187d0ba'.encode('UTF-8'),
                                 SEND_FILE.encode(), 0)
        self.log('断开与 {0}:{1} 的连接'.format(self.host, server_port), 'blue')
        for conn in self.__conn_pool_ready + self.__conn_pool_working:
            try:
                conn.send(close_info)
                time.sleep(random.randint(0, 50) / 100)
                conn.close()
            except:
                self.log('连接状态异常', 'yellow')
        with self.__log_lock:
            self.__log_file.close()

    def _get_connection(self):
        # 从空闲的conn中取出一个使用
        self.__lock.acquire()
        conn = self.__conn_pool_ready.pop()
        self.__conn_pool_working.append(conn)
        self.__lock.release()
        return conn

    def _return_connection(self, conn):
        # conn使用完毕，回收conn
        self.__lock.acquire()
        self.__conn_pool_ready.append(conn)
        self.__conn_pool_working.remove(conn)
        self.__lock.release()

    def _send_file(self, filepath, is_dir):
        # 从空闲的conn中取出一个使用
        conn = self._get_connection()
        if is_dir:
            filehead = struct.pack(fmt, filepath.encode('UTF-8'),
                                   SEND_DIR.encode(), 0)
            conn.send(filehead)
            self._return_connection(conn)
        else:
            real_path = os.path.join(self.__base_dir, filepath)
            # 定义文件头信息，包含文件名和文件大小
            file_size = os.stat(real_path).st_size
            # unit_1, unit_2 = calcu_size(file_size)
            # key = token_bytes(nbytes=512)
            filehead = struct.pack(fmt, filepath.encode('UTF-8'),
                                   SEND_FILE.encode(), file_size)
            # key = int.from_bytes(key + key_right, 'big')
            # self.log('文件名：{}，大小约 {}，{}'.format(filepath, unit_1, unit_2))
            conn.send(filehead)
            is_continue = receive_data(conn, 8)
            is_continue = is_continue.decode('UTF-8') == CONTINUE
            if is_continue:
                fp = open(real_path, 'rb')
                # self.log('开始发送文件')
                md5 = hashlib.md5()
                with self.__process_lock:
                    position = self.__position
                    self.__position += 1
                with tqdm(total=file_size, desc=filepath, unit='bytes', unit_scale=True, mininterval=1,
                          position=position) as pbar:
                    data = fp.read(unit)
                    while data:
                        conn.send(data)
                        md5.update(data)
                        # data = crypt(data, key)
                        pbar.update(len(data))
                        with self.__process_lock:
                            if self.__pbar:
                                self.__pbar.update(len(data))
                        data = fp.read(unit)
                fp.close()
                digest = md5.digest()
                conn.send(digest)
                filepath = receive_data(conn, filename_size)
                filepath = filepath.decode('UTF-8').strip('\00')
            else:
                with self.__process_lock:
                    if self.__pbar:
                        self.__pbar.update(file_size)
            self._return_connection(conn)
            return filepath

    def main(self):
        self.log('当前线程数：{}'.format(self.threading_number), 'blue')
        while True:
            tips = '请输入命令：'
            command = input(tips)
            if command == 'q' or command == 'quit' or command == 'exit':
                self.close_connection()
                return
            elif os.path.isdir(command) and os.path.exists(command):
                self._send_files_in_dir(command)
            elif os.path.isfile(command) and os.path.exists(command):
                self._send_single_file(command)
            elif command == "sysinfo":
                self._compare_sysinfo()
            elif command.startswith('speedtest'):
                times = command[10:]
                while not (times.isdigit() and int(times)) > 0:
                    times = input("请重新输入数据量（单位MB）：")
                self._speedtest(times=int(times))
            elif command.startswith("compare"):
                # 该算法仅适用于windows
                dirname_splits = command[8:].split(" ")
                i = -1
                for split in dirname_splits:
                    i += 1
                    if i > 0 and len(split) > 1 and split[1] == ":":
                        break
                local_dir = " ".join(dirname_splits[0:i])
                dest_dir = " ".join(dirname_splits[i:])
                self._compare_dir(local_dir, dest_dir)
            # elif command.startswith("get"):
            #     file_store_location = os.path.expanduser("~\Desktop")
            #     dirname_splits = command[4:].split(" ")
            #     has_2nd_arg = False
            #     i = -1
            #     for split in dirname_splits:
            #         i += 1
            #         if i > 0 and len(split) > 1 and split[1] == ":":
            #             has_2nd_arg = True
            #             break
            #     if has_2nd_arg:
            #         dest_resource = " ".join(dirname_splits[0:i])
            #         file_store_location = " ".join(dirname_splits[i:])
            #     else:
            #         dest_resource = " ".join(dirname_splits[0:])
            #     print("dest_resource: " + dest_resource)
            #     print("file_store_location: " + file_store_location)
            #     self._get_resources(dest_resource, file_store_location)

            else:
                self._execute_command(command)

    def _send_files_in_dir(self, filepath):
        # 每次发送文件夹时将进度条位置初始化
        self.__position = 0
        self.__base_dir = os.path.dirname(filepath)
        all_dir_name, all_file_name = get_dir_file_name(filepath)
        self.log('开始发送 {} 路径下所有文件夹，文件夹个数为 {}\n'.format(filepath, len(all_dir_name)), 'blue')
        results = []
        # start = time.time()
        for dirname in all_dir_name:
            result = self.__thread_pool.apply_async(self._send_file, (dirname, True))
            results.append(result)
        for result in results:
            result.wait()
        # self.log('文件夹发送完毕，耗时 {} s'.format(round(time.time() - start, 2)), 'blue')
        # 将待发送的文件打印到日志
        self.__log_file.write(get_log_msg("本次待发送的文件列表为：\n"))
        total_size = 0
        for filename in all_file_name:
            real_path = os.path.join(self.__base_dir, filename)
            file_size = os.stat(real_path).st_size
            sz1, sz2 = calcu_size(file_size)
            self.__log_file.write(get_log_msg(f"{real_path}, 约{sz1}, {sz2}\n"))
            total_size += file_size
        self.__log_file.flush()
        self.log('开始发送 {} 路径下所有文件，文件个数为 {}\n'.format(filepath, len(all_file_name)), 'blue')
        # 初始化总进度条
        with self.__process_lock:
            self.__pbar = tqdm(total=total_size, desc='累计发送量', unit='bytes', unit_scale=True,
                               mininterval=1,
                               position=0)
            self.__position += 1
        # 异步发送文件并等待结果
        results = []
        for filename in all_file_name:
            result = self.__thread_pool.apply_async(self._send_file, (filename, False))
            results.append(result)
        # 比对发送成功或失败的文件
        success_recv = []
        try:
            for result in results:
                result.wait()
                success_recv.append(result.get())
        except Exception as e:
            print(e)
        finally:
            with self.__process_lock:
                self.__pbar.close()
            fails = set(all_file_name) - set(success_recv)
            if fails:
                self.log("发送失败的文件：", color="red", highlight=1)
                for fail in fails:
                    self.log(fail, color='yellow')
            else:
                self.log("本次全部文件正常发送", color='green')

    def _send_single_file(self, filepath):
        self.__log_file.write("本次发送的文件: {}\n".format(filepath))
        self.__base_dir = os.path.dirname(filepath)
        filepath = os.path.basename(filepath)
        if filepath == self._send_file(filepath, False):
            self.log("发送成功", color='green')
        else:
            self.log("发送失败", color='red')

    def _compare_dir(self, local_dir, dest_dir):
        filehead = struct.pack(fmt, dest_dir.encode("UTF-8"), COMPARE_DIR.encode(), 0)
        conn = self._get_connection()
        conn.send(filehead)
        is_dir_correct = receive_data(conn, 14)
        is_dir_correct = is_dir_correct.decode() == "dir is correct"
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
            file_not_exits_in_dest = []
            file_not_exits_in_local = []
            file_in_local_smaller_than_dest = []
            file_in_dest_smaller_than_local = []
            filesize_and_name_both_equal = []
            hash_not_matching = []
            for filename in local_filename:
                if filename not in dest_dict:
                    file_not_exits_in_dest.append(filename)
                else:
                    local_filesize = local_dict[filename]
                    dest_filesize = dest_dict[filename]
                    if local_filesize < dest_filesize:
                        file_in_local_smaller_than_dest.append(filename)
                    elif local_filesize == dest_filesize:
                        filesize_and_name_both_equal.append(filename)
                    else:
                        file_in_dest_smaller_than_local.append(filename)

            for filename in dest_filename:
                if filename not in local_filename:
                    file_not_exits_in_local.append(filename)

            print_filename_if_exits("file exits in dest but not exits in local: ", file_not_exits_in_local)
            print_filename_if_exits("file exits in local but not exits in dest: ", file_not_exits_in_dest)
            print_filename_if_exits("file in local smaller than dest: ", file_in_local_smaller_than_dest)
            print_filename_if_exits("file in dest smaller than local: ", file_in_dest_smaller_than_local)
            print_filename_if_exits("filename and size both equal in two sides: ", filesize_and_name_both_equal)

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
                    results = {}
                    for filename in filesize_and_name_both_equal:
                        real_path = os.path.join(local_dir, filename)
                        results.update({filename: get_file_md5(real_path)})
                    # 获取本次字符串大小
                    data_size = receive_data(conn, str_len_size)
                    data_size = struct.unpack(str_len_fmt, data_size)[0]
                    # 接收字符串
                    data = receive_data(conn, data_size).decode()
                    # 将字符串转化为dict
                    dest_dict = json.loads(data)
                    for filename in results.keys():
                        if results[filename] != dest_dict[filename]:
                            hash_not_matching.append(filename)
                    print_filename_if_exits("hash not matching: ", hash_not_matching)
                else:
                    conn.send(CANCEL.encode())
            else:
                conn.send(CANCEL.encode())
        else:
            self.log(f"目标文件夹 {dest_dir} 不存在", color="yellow")
        self._return_connection(conn)

    def _execute_command(self, command):
        # 防止命令为空时将输出端交给服务器
        if len(command.strip()) == 0:
            return
        command = command.encode("UTF-8")
        if len(command) > filename_size:
            print_color("指令过长", color='yellow')
            return

        conn = self._get_connection()
        filehead = struct.pack(fmt, command, COMMAND.encode(), len(command))
        conn.send(filehead)
        # 接收返回结果
        result = receive_data(conn, 8)
        while result != b'\00' * 8:
            print(result.decode('UTF-32'), end='')
            result = receive_data(conn, 8)
        self._return_connection(conn)

    def _compare_sysinfo(self):
        conn = self._get_connection()
        t = MyThread(get_sys_info, args=())
        t.start()
        filehead = struct.pack(fmt, b'', SYSINFO.encode(), 0)
        conn.send(filehead)
        data_length = struct.unpack(str_len_fmt, receive_data(conn, str_len_size))[0]
        data = receive_data(conn, data_length).decode()
        dest_sysinfo = json.loads(data)
        print_sysinfo(dest_sysinfo)
        t.join()
        local_sysinfo = t.get_result()
        print_sysinfo(local_sysinfo)
        self._return_connection(conn)

    def _speedtest(self, times):
        conn = self._get_connection()
        data_unit = 1000 * 1000  # 1MB
        data_size = times * data_unit
        filehead = struct.pack(fmt, b'', SPEEDTEST.encode(), data_size)
        conn.send(filehead)
        with tqdm(total=data_size, desc='speedtest', unit='bytes', unit_scale=True, mininterval=1) as pbar:
            for i in range(0, times):
                # 生产随机字节
                conn.send(secrets.token_bytes(data_unit))
                pbar.update(data_unit)

        self._return_connection(conn)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='File Transfer Client, used to SEND files.')
    parser.add_argument('-t', metavar='thread', type=int,
                        help='threading number (default: 3)', default=3)
    parser.add_argument('-host', metavar='host',
                        help='destination hostname or ip address', default='')
    parser.add_argument('-p', '--plaintext', action='store_true',
                        help='Use plaintext transfer (default: use ssl)')
    args = parser.parse_args()
    ftc = FTC(thread_num=args.t, host=args.host, use_ssl=not args.plaintext)
    ftc.probe_server(1)
    ftc.connect()
    ftc.main()
    # try:
    #     ftc.main()
    # except Exception as e:
    #     print(e)
    #     # ftc.log('中断与服务器的文件传输', 'yellow')
    #     ftc.close_connection()
