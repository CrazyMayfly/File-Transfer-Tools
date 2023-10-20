import json
import os.path
import struct
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
        logger.warning(f'{file_path}文件时间修改失败，{e}')


def avoid_filename_duplication(filename: str):
    """
    当文件重复时另取新的文件名

    @param filename: 原文件名
    @return: 新文件名
    """
    if os.path.exists(filename):
        i = 1
        base, extension = os.path.splitext(filename)
        while os.path.exists(filename):
            filename = f"{base}({i}){extension}"
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
    return parser.parse_args()


class FTS:
    def __init__(self, base_dir, use_ssl, password=''):
        self.__password = password
        self.__ip = ''
        self.__base_dir: Path = Path(base_dir)
        self.__use_ssl = use_ssl
        self.__sessions = {}
        self.__sessions_lock = threading.Lock()
        self.logger = Logger(Path(config.log_dir, f'{datetime.now():%Y_%m_%d}_server.log'))
        self.logger.log(f'本次服务器密码: {password if password else "无"}')
        # 进行日志归档
        threading.Thread(name='ArchThread', target=compress_log_files,
                         args=(config.log_dir, 'server', self.logger)).start()

    class Session:
        def __init__(self, conn, host):
            self.main_conn = conn
            self.conns: set[socket.socket] = set()
            self.alive = True
            self.host = host
            self.file2size = {}
            self.__lock = threading.Lock()

        def add_conn(self, conn):
            self.conns.add(conn)

        def destroy(self):
            with self.__lock:
                if not self.alive:
                    return False
                self.alive = False
                for conn in self.conns:
                    conn.close()
                self.conns.clear()
                self.file2size.clear()
                return True

        @property
        def files(self):
            return list(self.file2size.keys())

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
            if create_dir_if_not_exist(new_base_dir, self.logger):
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
        conn.sendall(size_struct.pack(len(relative_filename)))
        # 再发送字符串
        conn.sendall(relative_filename)
        if receive_data(conn, 8)[0] != CONTROL.CONTINUE:
            self.logger.log("不继续比对Hash")
            return
        self.logger.log("继续对比文件Hash")
        str_len = size_struct.unpack(receive_data(conn, size_struct.size))[0]
        file_size_and_name_both_equal = receive_data(conn, str_len).decode(utf8).split("|")
        # 得到文件相对路径名: hash值字典
        results = {filename: get_file_md5(Path(dir_name, filename)) for filename in
                   file_size_and_name_both_equal}
        data = json.dumps(results, ensure_ascii=True).encode()
        conn.sendall(size_struct.pack(len(data)))
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
        data = json.dumps(get_sys_info(), ensure_ascii=True).encode()
        # 发送数据长度
        conn.sendall(size_struct.pack(len(data)))
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

    def __makedirs(self, conn, base_dir):
        size = size_struct.unpack(receive_data(conn, size_struct.size))[0]
        data = json.loads(receive_data(conn, size).decode())
        # 处理文件夹
        self.logger.info(f'开始创建文件夹，文件夹个数为 {len(data)}')
        for dir_name in data:
            cur_dir = Path(base_dir, dir_name)
            if cur_dir.exists():
                continue
            try:
                os.makedirs(cur_dir)
            except FileNotFoundError:
                self.logger.error(f'文件夹创建失败 {dir_name}', highlight=1)

    def __recv_files_in_dir(self, session: Session, dir_name, base_dir):
        self.logger.info(f'准备接收 {dir_name} 文件夹下的文件')
        real_dir = Path(base_dir, dir_name)
        if real_dir.exists():
            session.file2size = get_relative_filename_from_basedir(str(real_dir), prefix=dir_name)

        main_conn = session.main_conn
        self.__makedirs(main_conn, base_dir)
        # 发送已存在的文件名
        main_conn.sendall(size_struct.pack(len(data := json.dumps(session.files, ensure_ascii=True).encode())))
        main_conn.sendall(data)
        conns = session.conns
        threads = [threading.Thread(name=socket.inet_aton(conn.getpeername()[0]).hex() + hex(conn.getpeername()[1])[2:],
                                    target=self.__slave_work, args=(conn, base_dir, session)) for conn in conns]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        session.file2size = {}

    def __recv_single_file(self, conn: socket.socket, filename, file_size, base_dir, session: Session):
        file_path = Path(base_dir, filename)
        cur_download_file, fp = (original_file := avoid_filename_duplication(str(file_path))) + '.ftsdownload', None
        try:
            fp = open(cur_download_file, 'ab')
            rel_filename = filename + '.ftsdownload'
            size = session.file2size.get(rel_filename, 0) if session.file2size else os.path.getsize(cur_download_file)
            conn.sendall(size_struct.pack(size))
            rest_size = file_size - size
            self.logger.info(('准备接收文件 {0}，大小约 {1}，{2}' if size == 0 else
                              '断点续传文件 {0}，还需接收的大小约 {1}，{2}').format(
                os.path.relpath(original_file, base_dir), *calcu_size(rest_size)))
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
            os.rename(cur_download_file, original_file)
            self.logger.success(f'文件接收成功：{original_file}', highlight=1)
            timestamps = file_details_struct.unpack(receive_data(conn, file_details_struct.size))
            modify_file_time(original_file, self.logger, *timestamps)
        except ConnectionDisappearedError:
            self.logger.warning(f'客户端连接意外中止，文件接收失败：{original_file}')
        except PermissionError as err:
            self.logger.warning(f'文件重命名失败：{err}')
        except FileNotFoundError:
            self.logger.error(f'文件新建/打开失败，无法接收: {original_file}', highlight=1)
            conn.sendall(size_struct.pack(CONTROL.FAIL2OPEN))
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
        conn.settimeout(4)
        try:
            password, command, session_id = recv_head(conn)
        except (socket.timeout, struct.error) as exception:
            conn.close()
            self.logger.warning(('客户端 {}:{} 未及时校验密码，连接断开' if isinstance(exception, socket.timeout)
                                 else '服务器遭遇不明连接 {}:{}').format(peer_host, peer_port))
            return
        conn.settimeout(None)
        if command != COMMAND.BEFORE_WORKING:
            conn.close()
            return
        # 校验密码, 密码正确则发送当前平台
        msg = FAIL if password != self.__password else platform_
        session_id = uuid4().node if session_id == 0 else session_id
        conn.sendall(pack_head(msg, COMMAND.BEFORE_WORKING, session_id))
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
                continue
            if data[0] == 'HI-I-AM-FTC':
                target_ip, target_port = data[1], data[2]
                self.logger.info('收到来自 {0} 的探测请求'.format(target_ip))
                sk.sendto(content, (target_ip, int(target_port)))  # 单播

    def __slave_work(self, conn, base_dir, session):
        """
        从连接的工作，只用于处理多文件接收

        @param conn: 从连接
        @param base_dir: 文件保存位置
        @param session: 本次会话
        """
        try:
            while True:
                filename, command, file_size = recv_head(conn)
                if command == COMMAND.SEND_FILE:
                    self.__recv_single_file(conn, filename, file_size, base_dir, session)
                elif command == COMMAND.FINISH:
                    break
        except ConnectionError:
            return
        except UnicodeDecodeError:
            if session.destroy():
                self.logger.warning(f'{session.host} 数据流异常，连接断开')

    def __master_work(self, conn, session, host, port):
        """
        主连接的工作
        @param conn: 主连接
        @param session: 本次会话
        @param host: 客户端主机
        @param port: 客户端端口
        """
        self.logger.info(f'客户端连接 {get_hostname_by_ip(host)}, {host}:{port}')
        while session.alive:
            filename, command, file_size = recv_head(conn)
            cur_base_dir = Path.cwd() / self.__base_dir
            match command:
                case COMMAND.SEND_FILES_IN_DIR:
                    self.__recv_files_in_dir(session, filename, cur_base_dir)
                case COMMAND.SEND_FILE:
                    self.__recv_single_file(conn, filename, file_size, cur_base_dir, session)
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
                    get_clipboard(conn, self.logger, filename, command, file_size, ftc=False)
                case COMMAND.CLOSE:
                    if session.destroy():
                        self.logger.info(f'终止与客户端 {host}:{port} 的连接')

    def __route(self, conn: socket.socket, host, port):
        """
        根据会话是否存在判断一个连接是否为主连接并进行路由
        """
        session_id = self.__before_working(conn)
        if not session_id:
            return
        flag = False
        with self.__sessions_lock:
            if session_id not in self.__sessions.keys():
                self.__sessions[session_id] = self.Session(conn, host)
                flag = True
            self.__sessions[session_id].add_conn(conn)
        if flag:
            session = self.__sessions[session_id]
            try:
                self.__master_work(conn, session, host, port)
            except ConnectionDisappearedError as e:
                self.logger.warning(f'{host}:{port} {e}')
            except ConnectionResetError as e:
                self.logger.warning(f'{host}:{port} {e.strerror}')
            except UnicodeDecodeError:
                if session.destroy():
                    self.logger.warning(f'{host} 数据流异常，连接断开')
            except ssl.SSLEOFError as e:
                self.logger.warning(e)
            finally:
                with self.__sessions_lock:
                    self.__sessions.pop(session_id)

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
                conn, (host, port) = server_socket.accept()
                threading.Thread(name=socket.inet_aton(host).hex() + hex(port)[2:], target=self.__route,
                                 args=(conn, host, port)).start()
            except ssl.SSLError as e:
                self.logger.warning(f'SSLError: {e.reason}')


if __name__ == '__main__':
    args = get_args()
    fts = FTS(base_dir=args.dest, use_ssl=not args.plaintext, password=args.password)
    if not create_dir_if_not_exist(args.dest, fts.logger):
        sys.exit(-1)
    handle_ctrl_event(logger=fts.logger)
    fts.start()
