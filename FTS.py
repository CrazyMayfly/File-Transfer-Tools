import os.path
import random
import struct
import subprocess
import ssl
import tempfile
from uuid import uuid4
from Utils import *
from sys_info import *
from argparse import ArgumentParser, Namespace
from OpenSSL import crypto
from pathlib import Path


def generate_cert():
    # 生成密钥对
    key = crypto.PKey()
    key.generate_key(crypto.TYPE_RSA, 2048)
    # 生成自签名证书
    cert = crypto.X509()
    cert.get_subject().CN = "FTS"
    cert.set_serial_number(random.randint(1, 9999))
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(100)
    cert.set_pubkey(key)
    cert.sign(key, "sha256")
    # 将密钥保存到临时文件中，确保最大的安全性
    file, path = tempfile.mkstemp()
    file = open(file, 'wb')
    file.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    file.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, key))
    file.close()
    return path


if platform_ == WINDOWS:
    from win32file import CreateFile, SetFileTime, CloseHandle, GENERIC_WRITE, OPEN_EXISTING
    import win32timezone


def compact_host_port(host, port):
    return socket.inet_aton(host).hex() + hex(port)[2:]


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
        directory.mkdir(parents=True)
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
    parser.add_argument('-d', '--dest', metavar='base_dir', type=Path,
                        help='File storage location (default: {})'.format(default_path), default=default_path)
    parser.add_argument('-p', '--password', metavar='password', type=str,
                        help='Set a password for the host.', default='')
    return parser.parse_args()


class FTS:
    def __init__(self, base_dir, password=''):
        self.__password = password
        self.__ip = ''
        self.__base_dir: Path = Path(base_dir)
        self.__sessions = {}
        self.__sessions_lock = threading.Lock()
        self.logger = Logger(Path(config.log_dir, f'{datetime.now():%Y_%m_%d}_server.log'))
        # self.logger.log(f'本次服务器密码: {password if password else "无"}')
        # 进行日志归档
        threading.Thread(name='ArchThread', target=compress_log_files,
                         args=(config.log_dir, 'server', self.logger)).start()

    class Session:
        def __init__(self, conn, host):
            self.main_conn: ESocket = conn
            self.conns: set[ESocket] = set()
            self.alive: bool = True
            self.base_dir: PurePath = PurePath()
            self.cur_rel_dir: PurePath = PurePath()
            self.host: str = host
            self.file2size: dict[str:int] = {}
            self.__lock = threading.Lock()

        @property
        def cur_dir(self) -> Path:
            return Path(self.base_dir, self.cur_rel_dir)

        @property
        def files(self) -> list[str]:
            return list(self.file2size.keys())

        def add_conn(self, conn: ESocket):
            self.conns.add(conn)

        def reset(self):
            self.base_dir = PurePath()
            self.cur_rel_dir = PurePath()
            self.file2size.clear()

        def destroy(self) -> bool:
            """
            销毁会话
            @return: 销毁前会话状态
            """
            with self.__lock:
                if not self.alive:
                    return False
                self.alive = False
                for conn in self.conns:
                    conn.close()
                self.conns.clear()
                self.file2size.clear()
                return True

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
            new_base_dir = Path.cwd() / new_base_dir
            if create_dir_if_not_exist(new_base_dir, self.logger):
                self.__base_dir = new_base_dir
                self.logger.success(f'已将文件保存位置更改为: {self.__base_dir}')

    def __modify_file_time(self, file_path: str, create_timestamp: float, modify_timestamp: float,
                           access_timestamp: float):
        """
        用来修改文件的相关时间属性
        :param file_path: 文件路径名
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
            self.logger.warning(f'{file_path}文件时间修改失败，{e}')

    def __compare_dir(self, conn: ESocket, dir_name):
        self.logger.info(f"客户端请求对比文件夹：{dir_name}")
        if not os.path.exists(dir_name):
            # 发送目录不存在
            conn.sendall(OVER * len(DIRISCORRECT))
            return
        conn.sendall(DIRISCORRECT.encode())
        # 将数组拼接成字符串发送到客户端
        conn.send_with_compress(get_relative_filename_from_basedir(dir_name))
        if conn.receive_data(8)[0] != CONTROL.CONTINUE:
            return
        self.logger.log("继续对比文件Hash")
        file_size_and_name_both_equal = conn.recv_with_decompress()
        # 得到文件相对路径名: hash值字典
        results = {filename: get_file_md5(PurePath(dir_name, filename)) for filename in
                   file_size_and_name_both_equal}
        conn.send_with_compress(results)

    def __execute_command(self, conn: ESocket, command):
        out = subprocess.Popen(args=command, shell=True, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT).stdout
        output = []
        while result := out.readline():
            conn.send_head(result, COMMAND.EXECUTE_RESULT, 0)
            output.append(result)
        # 命令执行结束
        conn.send_head('', COMMAND.FINISH, 0)
        self.logger.log(f"执行命令：{command}\n{''.join(output)}")

    def __speedtest(self, conn: ESocket, data_size):
        self.logger.info(f"客户端请求速度测试，数据量: {get_size(2 * data_size, factor=1000)}")
        start = time.time()
        data_unit = 1000 * 1000
        for i in range(0, int(data_size / data_unit)):
            conn.receive_data(data_unit)
        show_bandwidth('下载速度测试完毕', data_size, interval=time.time() - start, logger=self.logger)
        download_over = time.time()
        for i in range(0, int(data_size / data_unit)):
            conn.sendall(os.urandom(data_unit))
        show_bandwidth('上传速度测试完毕', data_size, interval=time.time() - download_over, logger=self.logger)

    def __makedirs(self, dir_names, base_dir):
        for dir_name in dir_names:
            cur_dir = Path(base_dir, dir_name)
            if cur_dir.exists():
                continue
            try:
                cur_dir.mkdir(parents=True)
            except FileNotFoundError:
                self.logger.error(f'文件夹创建失败 {dir_name}', highlight=1)

    def __recv_files_in_dir(self, session: Session):
        if session.cur_dir.exists():
            session.file2size = get_relative_filename_from_basedir(str(session.cur_dir))
        main_conn = session.main_conn
        self.__makedirs(main_conn.recv_with_decompress(), session.cur_dir)
        # 发送已存在的文件名
        main_conn.send_with_compress(session.files)
        threads = [threading.Thread(name=compact_host_port(session.host, conn.getpeername()[1]),
                                    target=self.__slave_work, args=(conn, session)) for conn in session.conns]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        session.reset()

    def __recv_small_files(self, conn: ESocket, files_info, session: Session):
        cur_dir, real_path = session.cur_dir, Path("")
        try:
            msgs = []
            for filename, file_size, time_info in files_info:
                real_path = Path(cur_dir, filename)
                real_path.write_bytes(conn.receive_data(file_size))
                self.__modify_file_time(str(real_path), *times_struct.unpack(time_info))
                msgs.append(f'[SUCCESS] {get_log_msg("文件接收成功")}：{real_path}\n')
            self.logger.success(f'小文件簇接收成功，个数为 {len(files_info)}')
            self.logger.silent_write(msgs)
        except ConnectionDisappearedError:
            self.logger.warning(f'客户端连接意外中止，文件接收失败：{real_path}')
            real_path.unlink(True)
        except FileNotFoundError:
            self.logger.error(f'文件新建/打开失败，无法接收: {real_path}', highlight=1)
            real_path.unlink(True)

    def __recv_large_file(self, conn: ESocket, filename, file_size, session: Session):
        real_path = PurePath(session.cur_dir, filename)
        cur_download_file = (original_file := avoid_filename_duplication(str(real_path))) + '.ftsdownload'
        try:
            rel_filename = filename + '.ftsdownload'
            with open(cur_download_file, 'ab') as fp:
                size = session.file2size.get(rel_filename, 0) if session.file2size else os.path.getsize(
                    cur_download_file)
                rest_size = file_size - size
                conn.sendall(size_struct.pack(size))
                while rest_size > 4096:
                    data = conn.recv()
                    if data:
                        rest_size -= len(data)
                        fp.write(data)
                    else:
                        raise ConnectionDisappearedError
                fp.write(conn.receive_data(rest_size))
            os.rename(cur_download_file, original_file)
            self.logger.success(f'文件接收成功：{original_file}')
            timestamps = times_struct.unpack(conn.receive_data(times_struct.size))
            self.__modify_file_time(original_file, *timestamps)
        except ConnectionDisappearedError:
            self.logger.warning(f'客户端连接意外中止，文件接收失败：{original_file}')
        except PermissionError as err:
            self.logger.warning(f'文件重命名失败：{err}')
        except FileNotFoundError:
            self.logger.error(f'文件新建/打开失败，无法接收: {original_file}', highlight=1)
            conn.sendall(size_struct.pack(CONTROL.FAIL2OPEN))

    def __before_working(self, conn: ESocket):
        """
        在传输之前的预处理

        @param conn: 当前连接
        @return: 若成功连接则返回本次连接的 session_id
        """
        peer_host, peer_port = conn.getpeername()
        conn.settimeout(4)
        try:
            password, command, session_id = conn.recv_head()
        except (TimeoutError, struct.error) as error:
            conn.close()
            self.logger.warning(('客户端 {}:{} 未及时校验密码，连接断开' if isinstance(error, TimeoutError)
                                 else '服务器遭遇不明连接 {}:{}').format(peer_host, peer_port))
            return
        conn.settimeout(None)
        if command != COMMAND.BEFORE_WORKING:
            conn.close()
            return
        # 校验密码, 密码正确则发送当前平台
        msg = FAIL if password != self.__password else platform_
        session_id = uuid4().node if session_id == 0 else session_id
        conn.send_head(msg, COMMAND.BEFORE_WORKING, session_id)
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
        content = f'HI-I-AM-FTS_{self.__ip}'.encode(utf8)
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

    def __slave_work(self, conn: ESocket, session):
        """
        从连接的工作，只用于处理多文件接收

        @param conn: 从连接
        @param session: 本次会话
        """
        try:
            while True:
                filename, command, file_size = conn.recv_head()
                if command == COMMAND.SEND_LARGE_FILE:
                    self.__recv_large_file(conn, filename, file_size, session)
                elif command == COMMAND.SEND_SMALL_FILE:
                    self.__recv_small_files(conn, conn.recv_with_decompress(), session)
                elif command == COMMAND.FINISH:
                    break
        except ConnectionError:
            return
        except UnicodeDecodeError:
            if session.destroy():
                self.logger.warning(f'{session.host} 数据流异常，连接断开')

    def __master_work(self, session):
        """
        主连接的工作
        @param session: 本次会话
        """
        self.logger.info(f'客户端连接 {get_hostname_by_ip(session.host)}({session.host})')
        main_conn = session.main_conn
        while session.alive:
            filename, command, file_size = main_conn.recv_head()
            session.base_dir = Path.cwd() / self.__base_dir
            match command:
                case COMMAND.SEND_FILES_IN_DIR:
                    session.cur_rel_dir = filename
                    self.__recv_files_in_dir(session)
                case COMMAND.SEND_LARGE_FILE:
                    self.__recv_large_file(main_conn, filename, file_size, session)
                case COMMAND.COMPARE_DIR:
                    self.__compare_dir(main_conn, filename)
                case COMMAND.EXECUTE_COMMAND:
                    self.__execute_command(main_conn, filename)
                case COMMAND.SYSINFO:
                    main_conn.send_with_compress(get_sys_info())
                case COMMAND.SPEEDTEST:
                    self.__speedtest(main_conn, file_size)
                case COMMAND.PULL_CLIPBOARD:
                    send_clipboard(main_conn, self.logger, ftc=False)
                case COMMAND.PUSH_CLIPBOARD:
                    get_clipboard(main_conn, self.logger, filename, command, file_size, ftc=False)
                case COMMAND.CLOSE:
                    if session.destroy():
                        self.logger.info(f'终止与客户端 {session.host} 的连接')

    def __route(self, conn: ESocket, host, port):
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
                self.__master_work(session)
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
        self.logger.log(f'服务器 {host}({self.__ip}:{config.server_port}) 已启动，等待连接...')
        self.logger.log('当前默认文件存放位置：' + os.path.normcase(self.__base_dir))
        threading.Thread(name='SignThread', daemon=True, target=self.__signal_online).start()
        threading.Thread(name='CBDThread ', daemon=True, target=self.__change_base_dir).start()
        # 加载服务器所用证书和私钥
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(cert_path := generate_cert())
        os.remove(cert_path)
        while True:
            try:
                conn, (host, port) = server_socket.accept()
                threading.Thread(name=compact_host_port(host, port), target=self.__route,
                                 args=(ESocket(context.wrap_socket(conn, server_side=True)), host, port)).start()
            except ssl.SSLError as e:
                self.logger.warning(f'SSLError: {e.reason}')


if __name__ == '__main__':
    args = get_args()
    fts = FTS(base_dir=args.dest, password=args.password)
    if not create_dir_if_not_exist(args.dest, fts.logger):
        sys.exit(-1)
    handle_ctrl_event(logger=fts.logger)
    fts.start()
