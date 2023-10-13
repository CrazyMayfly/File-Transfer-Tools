import json
import os.path
import subprocess
import pathlib
import ssl
from uuid import uuid4
from Utils import *
from sys_info import *
from argparse import ArgumentParser, Namespace

if platform_ == WINDOWS:
    from win32file import CreateFile, SetFileTime, CloseHandle, GENERIC_WRITE, OPEN_EXISTING
    import win32timezone


def modify_file_time(file_path: str, logger: Logger, create_timestamp: float,
                     modify_timestamp: float, access_timestamp: float):
    """
    用来修改文件的相关时间属性
    :param file_path: 文件路径名
    :param logger: 日志打印对象
    :param create_timestamp: 创建时间戳
    :param modify_timestamp: 修改时间戳
    :param access_timestamp: 访问时间戳
    """
    try:
        if platform_ == WINDOWS:
            # 调用文件处理器对时间进行修改
            handler = CreateFile(file_path, GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, 0)
            SetFileTime(handler, datetime.fromtimestamp(create_timestamp), datetime.fromtimestamp(access_timestamp),
                        datetime.fromtimestamp(modify_timestamp))
            CloseHandle(handler)
        elif platform_ == LINUX:
            os.utime(path=file_path, times=(access_timestamp, modify_timestamp))
    except Exception as e:
        logger.warning(f'{file_path}修改失败，{e}')


def avoid_filename_duplication(filename: str):
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


def create_dir_if_not_exist(directory: Path, logger: Logger) -> bool:
    """
    创建文件夹
    @param directory: 文件夹路径
    @param logger: 日志对象
    @return: 是否创建成功
    """
    if directory.exists():
        return True
    try:
        os.makedirs(directory)
    except OSError as error:
        logger.error(f'无法创建 {directory}, {error}', highlight=1)
        return False
    logger.info('已创建文件夹 {}'.format(directory))
    return True


def get_args() -> Namespace:
    """
    获取命令行参数解析器
    """
    parser = ArgumentParser(
        description='File Transfer Server, used to RECEIVE files and EXECUTE instructions.')
    default_path = Path(config.default_path).expanduser()
    parser.add_argument('-d', '--dest', metavar='base_dir', type=pathlib.Path,
                        help='File storage location (default: {})'.format(default_path), default=default_path)
    parser.add_argument('-p', '--password', metavar='password', type=str,
                        help='Set a password for the host.', default='')
    parser.add_argument('--plaintext', action='store_true',
                        help='Use plaintext transfer (default: use ssl)')
    parser.add_argument('--repeated', action='store_true',
                        help='Continue receive the file when file name already exists (cancel by default).')
    return parser.parse_args()


class FTS:
    def __init__(self, base_dir, use_ssl, repeated, password=''):
        self.__password = password
        self.__ip = ''
        self.__base_dir: Path = base_dir
        self.__use_ssl = use_ssl
        self.__sessions_lock = threading.Lock()
        self.__sessions: dict[int:set[socket.socket]] = {}
        self.__avoid_file_duplicate = not repeated
        self.logger = Logger(Path(config.log_dir, f'{datetime.now():%Y_%m_%d}_server.log'))
        self.logger.log(f'本次服务器密码: {password if password else "无"}')
        # 进行日志归档
        threading.Thread(name='ArchThread', target=compress_log_files,
                         args=(config.log_dir, 'server', self.logger)).start()

    def __change_base_dir(self):
        """
        切换FTS的文件保存目录
        """
        while True:
            try:
                new_base_dir = input('>>> ')
            except EOFError:
                break
            if not new_base_dir or new_base_dir.isspace():
                continue
            new_base_dir = Path.cwd() / Path(new_base_dir)
            if not create_dir_if_not_exist(new_base_dir, self.logger):
                continue
            self.__base_dir = new_base_dir
            self.logger.success(f'已将文件保存位置更改为: {self.__base_dir}')

    def __compare_dir(self, conn: socket.socket, dir_name):
        self.logger.info(f"客户端请求对比文件夹：{dir_name}")
        if not os.path.exists(dir_name):
            # 发送目录不存在
            conn.sendall(OVER * len(DIRISCORRECT))
            return
        conn.sendall(DIRISCORRECT.encode())
        # 将数组拼接成字符串发送到客户端
        relative_filename = json.dumps(get_relative_filename_from_basedir(dir_name), ensure_ascii=True).encode()
        # 先发送字符串的大小
        conn.sendall(struct.pack(FMT.size_fmt, len(relative_filename)))
        # 再发送字符串
        conn.sendall(relative_filename)
        if receive_data(conn, 8)[0] != CONTROL.CONTINUE:
            self.logger.log("不继续比对Hash")
            return
        self.logger.log("继续对比文件Hash")
        str_len = struct.unpack(FMT.size_fmt, receive_data(conn, FMT.size_fmt.size))[0]
        file_size_and_name_both_equal = receive_data(conn, str_len).decode(utf8).split("|")
        # 得到文件相对路径名: hash值字典
        results = {filename: get_file_md5(Path(dir_name, filename)) for filename in
                   file_size_and_name_both_equal}
        data = json.dumps(results, ensure_ascii=True).encode()
        conn.sendall(struct.pack(FMT.size_fmt, len(data)))
        conn.sendall(data)
        self.logger.log("Hash 比对结束。")

    def __execute_command(self, conn: socket.socket, command):
        out = subprocess.Popen(args=command, shell=True, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT).stdout
        output = ''
        while temp := out.read(1):
            conn.sendall(temp.encode("UTF-32"))
            output += temp
        # 命令执行结束
        conn.sendall(OVER * 8)
        self.logger.log(f"执行命令：{command}\n{output}")

    def __compare_sysinfo(self, conn: socket.socket):
        self.logger.log("目标获取系统信息")
        info = get_sys_info()
        data = json.dumps(info, ensure_ascii=True).encode()
        # 发送数据长度
        str_len = struct.pack(FMT.size_fmt, len(data))
        conn.sendall(str_len)
        # 发送数据
        conn.sendall(data)

    def __speedtest(self, conn: socket.socket, data_size):
        self.logger.log(f"客户端请求速度测试，数据量: {get_size(2 * data_size, factor=1000)}")
        start = time.time()
        data_unit = 1000 * 1000
        for i in range(0, int(data_size / data_unit)):
            receive_data(conn, data_unit)
        show_bandwidth('下载速度测试完毕', data_size, interval=time.time() - start, logger=self.logger)
        download_over = time.time()
        for i in range(0, int(data_size / data_unit)):
            conn.sendall(os.urandom(data_unit))
        show_bandwidth('上传速度测试完毕', data_size, interval=time.time() - download_over, logger=self.logger)

    def __makedirs(self, conn, base_dir, size):
        data = json.loads(receive_data(conn, size).decode())
        # 处理文件夹
        self.logger.info(f'开始创建文件夹，文件夹个数为 {data["num"]}')
        for dir_name in data['dir_names'].split('|'):
            cur_dir = Path(base_dir, dir_name)
            if cur_dir.exists():
                continue
            try:
                os.makedirs(cur_dir)
            except FileNotFoundError:
                self.logger.error(f'文件夹创建失败 {dir_name}', highlight=1)
        conn.sendall(OVER)

    def __recv_files_in_dir(self, session_id, base_dir):
        with self.__sessions_lock:
            conns = self.__sessions.get(session_id)
        threads = []
        for conn in conns:
            peer_host, peer_port = conn.getpeername()
            t = threading.Thread(name=socket.inet_aton(peer_host).hex() + hex(peer_port)[2:], target=self.__slave_work,
                                 args=(conn, base_dir, session_id))
            t.start()
            threads.append(t)
        for t in threads:
            t.join()

    def __recv_single_file(self, conn: socket.socket, filename, file_size, base_dir):
        file_path = Path(base_dir, filename)
        if self.__avoid_file_duplicate and file_path.exists():
            # self.logger.warning('{} 文件重复，取消接收'.format(shorten_path(file_path, pbar_width)))
            conn.sendall(struct.pack(FMT.size_fmt, CONTROL.CANCEL))
            return
        cur_download_file, fp = (original_file := avoid_filename_duplication(str(file_path))) + '.ftsdownload', None
        try:
            fp = open(cur_download_file, 'ab')
            size = os.path.getsize(cur_download_file)
            conn.sendall(struct.pack(FMT.size_fmt, CONTROL.CONTINUE + size))
            command = struct.unpack(FMT.size_fmt, receive_data(conn, FMT.size_fmt.size))
            if command == CONTROL.FAIL2OPEN:
                self.logger.warning('对方文件发送失败 {}'.format(original_file))
                return
            timestamps = struct.unpack(FMT.file_details_fmt, receive_data(conn, FMT.file_details_fmt.size))
            rest_size = temp = file_size - size
            relpath = os.path.relpath(original_file, base_dir)
            begin = time.time()
            self.logger.info(('准备接收文件 {0}，大小约 {1}，{2}' if size == 0 else
                              '断点续传文件 {0}，还需接收的大小约 {1}，{2}').format(relpath, *calcu_size(rest_size)))
            conn.settimeout(5)
            while rest_size > 4096:
                data = conn.recv(4096)
                if data:
                    rest_size -= len(data)
                    fp.write(data)
                else:
                    raise ConnectionDisappearedError
            fp.write(receive_data(conn, rest_size))
            fp.close()
            avg_speed = temp / 1000000 / time_cost if (time_cost := time.time() - begin) else 0
            self.logger.success(
                f'{relpath} 接收成功，耗时：{time_cost:.2f} s，平均速度 {avg_speed :.2f} MB/s', highlight=1)
            os.rename(cur_download_file, original_file)
            modify_file_time(original_file, self.logger, *timestamps)
        except ConnectionDisappearedError:
            self.logger.warning(f'客户端连接意外中止，文件接收失败：{original_file}')
        except PermissionError as err:
            self.logger.warning(f'文件重命名失败：{err}')
        except FileNotFoundError:
            self.logger.error(f'文件新建/打开失败，无法接收: {original_file}', highlight=1)
            conn.sendall(struct.pack(FMT.size_fmt, CONTROL.FAIL2OPEN))
        except TimeoutError:
            self.logger.warning(f'客户端传输超时，传输失败文件 {original_file}')
        finally:
            conn.settimeout(None)
            if fp and not fp.closed:
                fp.close()

    def __before_working(self, conn: socket.socket):
        """
        在传输之前的预处理

        @param conn: 当前连接
        @return: 若成功连接则返回本次连接的 session_id
        """
        peer_host, peer_port = conn.getpeername()
        conn.settimeout(2)
        try:
            file_head = receive_data(conn, FMT.head_fmt.size)
            password, command, session_id = struct.unpack(FMT.head_fmt, file_head)
        except (socket.timeout, struct.error) as exception:
            conn.close()
            self.logger.warning(('客户端 {}:{} 未及时校验密码，连接断开' if isinstance(exception, socket.timeout)
                                 else '服务器遭遇不明连接 {}:{}').format(peer_host, peer_port))
            return
        conn.settimeout(None)
        command = command.decode().strip('\00')
        if command != COMMAND.BEFORE_WORKING:
            conn.close()
            return
        password = password.decode(utf8).strip('\00')
        # 校验密码, 密码正确则发送当前平台
        msg = FAIL if password != self.__password else platform_
        session_id = uuid4().node if session_id == 0 else session_id
        file_head = struct.pack(FMT.head_fmt, msg.encode(), COMMAND.BEFORE_WORKING.encode(), session_id)
        conn.sendall(file_head)
        if password != self.__password:
            conn.close()
            self.logger.warning(f'客户端 {peer_host}:{peer_port} 密码("{password}")错误，断开连接')
            return
        return session_id

    def __signal_online(self):
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        try:
            sk.bind(('0.0.0.0', config.server_signal_port))
        except OSError as e:
            self.logger.error(f'广播主机信息服务启动失败，{e.strerror}')
            return
        content = f'HI-I-AM-FTS_{self.__ip}_{self.__use_ssl}'.encode(utf8)
        self.logger.log('广播主机信息服务已启动')
        broadcast_to_all_interfaces(sk, config.client_signal_port, content)
        while True:
            try:
                data = sk.recv(1024).decode(utf8).split('_')
            except ConnectionResetError:
                return
            else:
                if data[0] == 'HI-I-AM-FTC':
                    target_ip, target_port = data[1], data[2]
                    self.logger.info('收到来自 {0} 的探测请求'.format(target_ip))
                    sk.sendto(content, (target_ip, int(target_port)))  # 单播

    def __slave_work(self, conn, base_dir, session_id):
        """
        从连接的工作，只用于处理多文件接受

        @param conn: 从连接
        @param base_dir: 文件保存位置
        @param session_id: 本次会话id
        """
        try:
            while True:
                file_head = receive_data(conn, FMT.head_fmt.size)
                filename, command, file_size = struct.unpack(FMT.head_fmt, file_head)
                filename = filename.decode(utf8).strip('\00')
                command = command.decode().strip('\00')
                if command == COMMAND.SEND_FILE:
                    self.__recv_single_file(conn, filename, file_size, base_dir)
                elif command == FINISH:
                    break
        except ConnectionError:
            return
        except UnicodeDecodeError:
            self.logger.warning(f'数据流异常，连接断开')
            conn.close()
        else:
            # 首次工作结束后将连接添加到session里面
            with self.__sessions_lock:
                self.__sessions[session_id].add(conn)

    def __master_work(self, conn, addr, session_id):
        """
        主连接的工作
        @param conn: 主连接
        @param addr: 客户端地址
        @param session_id: 本次会话id
        """
        self.logger.info(f'客户端连接 {get_hostname_by_ip(addr[0])}, {addr[0]}:{addr[1]}')
        try:
            while True:
                file_head = receive_data(conn, FMT.head_fmt.size)
                filename, command, file_size = struct.unpack(FMT.head_fmt, file_head)
                filename = filename.decode(utf8).strip('\00')
                command = command.decode().strip('\00')
                cur_base_dir = self.__base_dir
                match command:
                    case COMMAND.SEND_FILES_IN_DIR:
                        self.__makedirs(conn, base_dir=cur_base_dir, size=file_size)
                        self.__recv_files_in_dir(session_id, cur_base_dir)
                    case COMMAND.SEND_FILE:
                        self.__recv_single_file(conn, filename, file_size, cur_base_dir)
                    case COMMAND.COMPARE_DIR:
                        self.__compare_dir(conn, filename)
                    case COMMAND.EXECUTE_COMMAND:
                        self.__execute_command(conn, filename)
                    case COMMAND.SYSINFO:
                        self.__compare_sysinfo(conn)
                    case COMMAND.SPEEDTEST:
                        self.__speedtest(conn, file_size)
                    case COMMAND.PULL_CLIPBOARD:
                        send_clipboard(conn, self.logger, ftc=False)
                    case COMMAND.PUSH_CLIPBOARD:
                        get_clipboard(conn, self.logger, file_head=file_head, ftc=False)
                    case COMMAND.CLOSE:
                        for conn in self.__sessions[session_id]:
                            conn.close()
                        self.logger.info(f'终止与客户端 {addr[0]}:{addr[1]} 的连接')
                        break
        except ConnectionDisappearedError as e:
            self.logger.warning(f'{addr[0]}:{addr[1]} {e}')
        except ConnectionResetError as e:
            self.logger.warning(f'{addr[0]}:{addr[1]} {e.strerror}')
        except UnicodeDecodeError:
            self.logger.warning(f'{addr[0]}:{addr[1]} 数据流异常，连接断开')
            for conn in self.__sessions[session_id]:
                conn.close()
        except ssl.SSLEOFError as e:
            self.logger.warning(e)
        finally:
            with self.__sessions_lock:
                self.__sessions.pop(session_id)

    def __route(self, conn: socket.socket, addr):
        """
        根据会话是否存在判断一个连接是否为主连接并进行路由
        """
        session_id = self.__before_working(conn)
        if not session_id:
            return
        if session_id not in self.__sessions.keys():
            with self.__sessions_lock:
                self.__sessions[session_id] = {conn}
            self.__master_work(conn, addr, session_id)
        else:
            self.__slave_work(conn, self.__base_dir, session_id)

    def start(self):
        self.__ip, host = get_ip_and_hostname()
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('0.0.0.0', config.server_port))
        server_socket.listen(9999)
        self.logger.success('当前数据使用加密传输') if self.__use_ssl else self.logger.warning('当前数据未进行加密传输')
        self.logger.log(f'服务器 {host}({self.__ip}:{config.server_port}) 已启动，等待连接...')
        self.logger.log('当前默认文件存放位置：' + os.path.normcase(self.__base_dir))
        threading.Thread(name='SignThread', daemon=True, target=self.__signal_online).start()
        threading.Thread(name='CBDThread ', daemon=True, target=self.__change_base_dir).start()
        if self.__use_ssl:
            # 生成SSL上下文
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            # 加载服务器所用证书和私钥
            context.load_cert_chain(Path(config.cert_dir, 'server.crt'),
                                    Path(config.cert_dir, 'server_rsa_private.pem'))
            server_socket = context.wrap_socket(server_socket, server_side=True)
        while True:
            try:
                conn, addr = server_socket.accept()
                threading.Thread(name=socket.inet_aton(addr[0]).hex() + hex(addr[1])[2:], target=self.__route,
                                 args=(conn, addr)).start()
            except ssl.SSLError as e:
                self.logger.warning(f'SSLError: {e.reason}')


if __name__ == '__main__':
    args = get_args()
    fts = FTS(base_dir=Path(args.dest), use_ssl=not args.plaintext, repeated=args.repeated, password=args.password)
    if not create_dir_if_not_exist(Path(args.dest), fts.logger):
        sys.exit(-1)
    handle_ctrl_event(logger=fts.logger)
    fts.start()
