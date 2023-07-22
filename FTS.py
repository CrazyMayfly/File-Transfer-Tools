import argparse
import json
import os.path
import pathlib
import ssl

from Utils import *
from sys_info import *


class FTS:
    def __init__(self, base_dir, use_ssl, avoid, password=''):
        self.__password = password
        log_file_path = os.path.normcase(
            os.path.join(config.log_dir, datetime.now().strftime('%Y_%m_%d') + '_server.log'))
        self.ip = ''
        self.base_dir = base_dir
        self.__use_ssl = use_ssl
        self.__avoid_file_duplicate = avoid
        self.logger = Logger(log_file_path)
        self.logger.log('本次日志文件存放位置: ' + log_file_path)
        self.logger.log(f'本次服务器密码: {password if password else "无"}')
        # 进行日志归档
        threading.Thread(target=compress_log_files, args=(config.log_dir, 'server', self.logger)).start()

    def avoid_filename_duplication(self, filename: str):
        """
        当文件重复时另取新的文件名

        @param filename: 原文件名
        @return: 新文件名
        """
        i = 1
        while os.path.exists(filename):
            path_split = os.path.splitext(filename)
            if i == 1:
                filename = path_split[0] + ' (1)' + path_split[1]
            else:
                tmp = list(path_split[0])
                tmp[-2] = str(i)
                filename = ''.join(tmp) + path_split[1]
            i += 1
        return filename

    def _deal_data(self, conn: socket.socket, addr):
        if self._before_working(conn):
            return
        self.logger.info(f'客户端连接 {addr[0]}:{addr[1]}')
        while True:
            try:
                file_head = receive_data(conn, fileinfo_size)
                filename, command, file_size = struct.unpack(fmt, file_head)
                filename = filename.decode(utf8).strip('\00')
                command = command.decode().strip('\00')
                if command == CLOSE:
                    conn.close()
                    self.logger.info(f'终止与客户端 {addr[0]}:{addr[1]} 的连接')
                    return
                elif command == SEND_DIR:
                    self._makedir(filename)
                elif command == SEND_FILE:
                    self._recv_file(conn, filename, file_size)
                elif command == COMPARE_DIR:
                    self._compare_dir(conn, filename)
                elif command == COMMAND:
                    self._execute_command(conn, filename)
                elif command == SYSINFO:
                    self._compare_sysinfo(conn)
                elif command == SPEEDTEST:
                    self._speedtest(conn, file_size)
                elif command == PULL_CLIPBOARD:
                    send_clipboard(conn, self.logger, FTC=False)
                elif command == PUSH_CLIPBOARD:
                    get_clipboard(conn, self.logger, file_head=file_head, FTC=False)
            except ConnectionResetError as e:
                self.logger.warning(f'{addr[0]}:{addr[1]} {e.strerror}')
                return

    def _makedir(self, dir_name):
        # 处理文件夹
        cur_dir = os.path.join(self.base_dir, dir_name)
        try:
            if not os.path.exists(cur_dir):
                os.makedirs(cur_dir)
                self.logger.info('创建文件夹 {0}'.format(dir_name))
        except FileNotFoundError:
            self.logger.error('文件夹路径太长，创建文件夹失败 {0}'.format(dir_name), highlight=1)

    def _signal_online(self):
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        try:
            sk.bind(('0.0.0.0', config.server_signal_port))
        except OSError as e:
            self.logger.error(f'广播主机信息服务启动失败，{e.strerror}')
            return
        content = ('04c8979a-a107-11ed-a8fc-0242ac120002_{}_{}'.format(self.ip, self.__use_ssl)).encode(utf8)
        addr = (self.ip[0:self.ip.rindex('.')] + '.255', config.client_signal_port)
        self.logger.log('广播主机信息服务已启动')
        # 广播
        sk.sendto(content, addr)
        while True:
            try:
                data = sk.recv(1024).decode(utf8).split('_')
            except ConnectionResetError:
                pass
            else:
                if data[0] == '53b997bc-a140-11ed-a8fc-0242ac120002':
                    target_ip = data[1]
                    self.logger.info('收到来自 {0} 的探测请求'.format(target_ip))
                    # 单播
                    sk.sendto(content, (target_ip, config.client_signal_port))

    def main(self):
        host = socket.gethostname()
        self.ip = socket.gethostbyname(host)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', config.server_port))
        s.listen(9999)
        if self.__use_ssl:
            self.logger.success('当前数据使用加密传输')
        else:
            self.logger.warning('当前数据未进行加密传输')
        self.logger.log(f'服务器 {host}({self.ip}:{config.server_port}) 已启动，等待连接...')
        self.logger.log('当前默认文件存放位置：' + self.base_dir)
        t = threading.Thread(target=self._signal_online)
        t.setName('SignThread')
        t.setDaemon(True)
        t.start()
        if self.__use_ssl:
            # 生成SSL上下文
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            # 加载服务器所用证书和私钥
            context.load_cert_chain(os.path.join(config.cert_dir, 'server.crt'),
                                    os.path.join(config.cert_dir, 'server_rsa_private.pem'))
            with context.wrap_socket(s, server_side=True) as ss:
                while True:
                    try:
                        conn, addr = ss.accept()
                        t = threading.Thread(target=self._deal_data, args=(conn, addr))
                        t.start()
                    except ssl.SSLError as e:
                        self.logger.warning(f'SSLError: {e.reason}')

        else:
            while True:
                conn, addr = s.accept()
                t = threading.Thread(target=self._deal_data, args=(conn, addr))
                t.start()

    def _recv_file(self, conn: socket.socket, filename, file_size):
        file_path = os.path.normcase(os.path.join(self.base_dir, filename))
        if self.__avoid_file_duplicate and os.path.exists(file_path):
            self.logger.warning('{} 文件重复，取消接收'.format(shorten_path(file_path, pbar_width)))
            conn.sendall(struct.pack('Q', Control.CANCEL.value))
        else:
            original_file = self.avoid_filename_duplication(file_path)
            cur_download_file = original_file + '.ftsdownload'
            size = 0
            if os.path.exists(cur_download_file):
                fp = openfile_with_retires(cur_download_file, 'ab')
                size = os.stat(cur_download_file).st_size
            else:
                fp = openfile_with_retires(cur_download_file, 'wb')
            if not fp:
                self.logger.error(f'文件路径太长，无法接收: {original_file}', highlight=1)
                conn.sendall(struct.pack('Q', Control.TOOLONG.value))
                return
            if size == 0:
                conn.sendall(struct.pack('Q', Control.CONTINUE.value))
            else:
                # 此处+4是为了与控制标志的值分开
                conn.sendall(struct.pack('Q', size + 4))
            command = struct.unpack('Q', receive_data(conn, 8))
            if command == Control.TOOLONG:
                self.logger.warning('对方因文件路径太长无法发送文件 {}'.format(original_file))
            else:
                relpath = os.path.relpath(original_file, self.base_dir)
                if size == 0:
                    self.logger.info('准备接收文件 {0}， 大小约 {1}，{2}'.format(relpath, *calcu_size(file_size)))
                else:
                    self.logger.info('断点续传文件 {0}， 还需接收的大小约 {1}，{2}'.format(relpath,
                                                                                         *calcu_size(file_size - size)))
                timestamps = struct.unpack(file_details_fmt, receive_data(conn, file_details_size))
                begin = time.time()
                rest_size = file_size - size
                while rest_size > 0:
                    recv_window = min(unit, rest_size)
                    data = conn.recv(recv_window)
                    rest_size -= len(data)
                    fp.write(data)
                fp.close()
                time_cost = time.time() - begin
                avg_speed = file_size / 1000000 / time_cost if time_cost != 0 else 0
                self.logger.success(
                    f'{relpath} 接收成功，耗时：{time_cost:.2f} s，平均速度 {avg_speed :.2f} MB/s', highlight=1)
                os.rename(cur_download_file, original_file)
                modifyFileTime(original_file, self.logger, *timestamps)

    def _compare_dir(self, conn: socket.socket, dir_name):
        self.logger.info(f"客户端请求对比文件夹：{dir_name}")
        if os.path.exists(dir_name):
            conn.sendall(DIRISCORRECT.encode())
            # 将数组拼接成字符串发送到客户端
            relative_filename = json.dumps(get_relative_filename_from_basedir(dir_name), ensure_ascii=True).encode()
            # 先发送字符串的大小
            str_len_head = struct.pack(str_len_fmt, len(relative_filename))
            conn.sendall(str_len_head)
            # 再发送字符串
            conn.sendall(relative_filename)
            is_continue = receive_data(conn, 8)[0] == Control.CONTINUE
            if is_continue:
                self.logger.log("继续对比文件Hash")
                str_len = receive_data(conn, str_len_size)
                str_len = struct.unpack(str_len_fmt, str_len)[0]
                file_size_and_name_both_equal = receive_data(conn, str_len).decode(utf8).split("|")
                # 得到文件相对路径名: hash值字典
                results = {filename: get_file_md5(os.path.join(dir_name, filename)) for filename in
                           file_size_and_name_both_equal}
                data = json.dumps(results, ensure_ascii=True).encode()
                conn.sendall(struct.pack(str_len_fmt, len(data)))
                conn.sendall(data)
                self.logger.log("Hash 比对结束。")
            else:
                self.logger.log("不继续比对Hash")
        else:
            conn.sendall(b'\00' * len(DIRISCORRECT))

    def _execute_command(self, conn: socket.socket, command):
        self.logger.log("执行命令：" + command)
        result = os.popen(command)
        s = result.read(1)
        while s:
            # UTF-32 为定宽字符编码
            conn.sendall(s.encode("UTF-32"))
            print(s, end='')
            s = result.read(1)
        # 命令执行结束
        conn.sendall(b'\00' * 8)

    def _compare_sysinfo(self, conn: socket.socket):
        self.logger.log("目标获取系统信息")
        info = get_sys_info()
        data = json.dumps(info, ensure_ascii=True).encode()
        # 发送数据长度
        str_len = struct.pack(str_len_fmt, len(data))
        conn.sendall(str_len)
        # 发送数据
        conn.sendall(data)

    def _speedtest(self, conn: socket.socket, data_size):
        self.logger.log(f"客户端请求速度测试，数据量: {get_size(data_size, factor=1000)}")
        start = time.time()
        data_unit = 1000 * 1000
        for i in range(0, int(data_size / data_unit)):
            receive_data(conn, data_unit)
        time_cost = time.time() - start
        self.logger.success(
            f"速度测试完毕, 耗时 {time_cost:.2f}s, 平均速度{get_size(data_size / time_cost, factor=1000)}/s.")

    def _before_working(self, conn: socket.socket):
        """
        在传输之前的预处理

        @param conn: 当前连接
        @return: True表示断开连接
        """
        peer_host, peer_port = conn.getpeername()
        conn.settimeout(2)
        try:
            file_head = receive_data(conn, fileinfo_size)
            password, command, _ = struct.unpack(fmt, file_head)
        except (socket.timeout, struct.error) as exception:
            conn.close()
            if isinstance(exception, socket.timeout):
                message = f'客户端 {peer_host}:{peer_port} 未及时校验密码，连接断开'
            else:
                message = f'服务器遭遇不明连接 {peer_host}:{peer_port}'
            self.logger.warning(message)
            return True
        conn.settimeout(None)
        password = password.decode(utf8).strip('\00')
        command = command.decode().strip('\00')
        if command != BEFORE_WORKING:
            conn.close()
            return True
        # 校验密码, 密码正确则发送当前平台
        msg = FAIL if password != self.__password else platform_
        file_head = struct.pack(fmt, msg.encode(), BEFORE_WORKING.encode(), 0)
        conn.sendall(file_head)
        if password != self.__password:
            conn.close()
            self.logger.warning(f'客户端 {peer_host}:{peer_port} 密码("{password}")错误，断开连接')
            return True
        return False


if __name__ == '__main__':
    # base_dir = input('请输入文件保存位置（输入1默认为桌面）：')
    parser = argparse.ArgumentParser(
        description='File Transfer Server, used to RECEIVE files and EXECUTE instructions.')
    default_path = os.path.expanduser(config.default_path)
    parser.add_argument('-d', '--dest', metavar='base_dir', type=pathlib.Path,
                        help='File storage location (default: {})'.format(default_path), default=default_path)
    parser.add_argument('-p', '--password', metavar='password', type=str,
                        help='Set a password for the host.', default='')
    parser.add_argument('--plaintext', action='store_true',
                        help='Use plaintext transfer (default: use ssl)')
    parser.add_argument('--avoid', action='store_true',
                        help='Do not continue the transfer when the file name is repeated.')
    args = parser.parse_args()
    base_dir = pathlib.PureWindowsPath(args.dest).as_posix()
    if platform_ == LINUX:
        base_dir = pathlib.PurePath(args.dest).as_posix()
    base_dir = os.path.normcase(base_dir)
    if not os.path.exists(base_dir):
        try:
            os.makedirs(base_dir)
        except OSError as error:
            print_color(f'无法创建 {base_dir}, {error}', level=LEVEL.ERROR, highlight=1)
            sys.exit(1)
        print_color(get_log_msg('已创建文件夹 {}'.format(base_dir)), level=LEVEL.INFO)

    fts = FTS(base_dir=base_dir, use_ssl=not args.plaintext, avoid=args.avoid, password=args.password)
    handle_ctrl_event()
    try:
        fts.main()
    finally:
        if packaging:
            os.system('pause')
