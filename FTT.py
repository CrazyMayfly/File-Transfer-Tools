from FTC import *
from FTS import *

username = psutil.users()[0].name


def get_args() -> Namespace:
    """
    获取命令行参数解析器
    """
    default_path = Path(config.default_path).expanduser()
    parser = ArgumentParser(description='File Transfer Tool, used to transfer files and execute commands.')
    cpu_count = psutil.cpu_count(logical=False)
    parser.add_argument('-t', metavar='thread', type=int,
                        help=f'Threads (default: {cpu_count})', default=cpu_count)
    parser.add_argument('-host', metavar='host',
                        help='Destination hostname or ip address', default='')
    parser.add_argument('-p', '--password', metavar='password', type=str,
                        help='Set a password for the host or Use a password to connect host.', default='')
    parser.add_argument('-d', '--dest', metavar='base_dir', type=Path,
                        help='File save location (default: {})'.format(default_path), default=default_path)
    return parser.parse_args()


class FTT:
    def __init__(self, password='', host='', dest='', threads=6):
        self.fts = None
        self.ftc = None
        self.__history_file = open(read_line_setup(), 'a', encoding=utf8)
        self.__command_prefix = None
        self.peer_platform = None
        self.host = host
        self.alive = True
        self.threads = threads
        self.password = password
        self.__base_dir = dest
        self.main_conn_recv = ...
        self.main_conn = ...
        self.connections = []
        self.logger = Logger(PurePath(config.log_dir, f'{datetime.now():%Y_%m_%d}_ftt.log'))

    def __add_history(self, command: str):
        readline.add_history(command)
        self.__history_file.write(command + '\n')
        self.__history_file.flush()

    def __change_base_dir(self, new_base_dir):
        """
        切换FTS的文件保存目录
        """
        if not new_base_dir or new_base_dir.isspace():
            return
        new_base_dir = Path(new_base_dir).expanduser().absolute()
        if create_folder_if_not_exist(new_base_dir, self.logger):
            self.fts.base_dir = new_base_dir
            self.logger.success(f'File save location changed to: {new_base_dir}')

    def server(self):
        try:
            while True:
                filename, command, file_size = self.main_conn_recv.recv_head()
                if command == COMMAND.CLOSE:
                    self.logger.info(f'Peer closed the connection')
                    break
                self.fts.execute(filename, command, file_size)
        except (ConnectionDisappearedError, ssl.SSLEOFError) as e:
            if self.alive:
                self.logger.warning(f'{e}')
        except ConnectionResetError as e:
            self.logger.warning(f'{e.strerror}')
        except UnicodeDecodeError:
            self.logger.warning(f'Peer data flow abnormality, connection disconnected')
        finally:
            self.shutdown(send_info=False)

    def start(self):
        self.prepare()
        try:
            while True:
                command = input('>>> ').strip()
                self.__add_history(command)
                if command in ['q', 'quit', 'exit']:
                    break
                elif command.startswith(setbase):
                    self.__change_base_dir(command[8:])
                    continue
                self.ftc.execute(command)
        except (ssl.SSLError, ConnectionError) as e:
            self.logger.error(e.strerror if e.strerror else e, highlight=1)
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()

    def prepare(self):
        if self.host:
            # 处理ip和端口
            if len(splits := self.host.split(":")) == 2:
                self.host, config.server_port = splits[0], int(splits[1])
            self.connect()
        else:
            if self.password:
                self.waiting_connect()
            else:
                self.finding_server()
        executor = concurrent.futures.ThreadPoolExecutor(thread_name_prefix=compact_ip(self.host))
        self.ftc = FTC(connections=self.connections + [self.main_conn], peer_platform=self.peer_platform,
                       logger=self.logger, executor=executor)
        self.fts = FTS(connections=self.connections + [self.main_conn_recv], logger=self.logger,
                       base_dir=self.__base_dir, executor=executor)
        threading.Thread(name='SeverThread', target=self.server, args=(), daemon=True).start()
        threading.Thread(name='ArchiveThread', target=compress_log_files,
                         args=(config.log_dir, 'ftt', self.logger)).start()
        self.logger.log('Current file storage location: ' + os.path.normcase(self.__base_dir))

    def connect(self):
        try:
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            voucher = self.password.encode() + self.first_connect(context, self.host)
            for i in range(0, self.threads + 1):
                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_socket.connect((self.host, config.server_port))
                client_socket = ESocket(context.wrap_socket(client_socket, server_hostname='FTS'))
                client_socket.sendall(voucher)
                self.connections.append(client_socket)
            self.main_conn_recv = self.connections.pop()
        except (ssl.SSLError, OSError) as msg:
            self.logger.error(f'Failed to connect to the server {self.host}, {msg}')
            sys.exit(-1)

    def first_connect(self, context, host):
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # 连接至服务器
        client_socket.connect((host, config.server_port))
        # 将socket包装为securitySocket
        client_socket = ESocket(context.wrap_socket(client_socket, server_hostname='FTS'))
        client_socket.send_head(f'{self.password}_{platform_}_{username}', COMMAND.BEFORE_WORKING, self.threads)
        client_socket.sendall(connect_id := os.urandom(64))
        msg, _, threads = client_socket.recv_head()
        if msg == FAIL:
            self.logger.error('Wrong password to connect to server', highlight=1)
            client_socket.close()
            sys.exit(-1)
        # self.logger.info(f'服务器所在平台: {msg}\n')
        self.peer_platform, peer_username = msg.split('_')
        self.__command_prefix = 'powershell ' if self.peer_platform == WINDOWS else ''
        self.logger.success(f'Connected to the server {peer_username}({host}:{config.server_port})')
        self.threads = min(self.threads, threads)
        self.main_conn = client_socket
        return connect_id

    def shutdown(self, send_info=True):
        self.alive = False
        try:
            if send_info:
                self.main_conn.send_head('', COMMAND.CLOSE, 0)
            for conn in self.connections + [self.main_conn_recv, self.main_conn]:
                conn.close()
        except (ssl.SSLEOFError, ConnectionError):
            pass
        finally:
            self.logger.close()
            self.__history_file.close()
            os.kill(os.getpid(), signal.SIGINT)

    def __before_working(self, conn: ESocket):
        peer_ip, peer_port = conn.getpeername()
        conn.settimeout(4)
        try:
            info, command, threads = conn.recv_head()
            *password, peer_platform, peer_username = info.split('_')
        except (TimeoutError, struct.error) as error:
            conn.close()
            self.logger.warning(('Client {}:{} failed to verify the password in time' if isinstance(error, TimeoutError)
                                 else 'Encountered unknown connection {}:{}').format(peer_ip, peer_port))
            return
        conn.settimeout(None)
        if command != COMMAND.BEFORE_WORKING:
            conn.close()
            return
        # 校验密码, 密码正确则发送当前平台
        msg = FAIL if (password := '_'.join(password)) != self.password else f'{platform_}_{username}'
        conn.send_head(msg, COMMAND.BEFORE_WORKING, self.threads)
        if password != self.password:
            conn.close()
            self.logger.warning(f'Client {peer_ip}:{peer_port} password("{password}") is wrong')
            return

        self.peer_platform = peer_platform
        self.threads = min(self.threads, threads)
        return self.password.encode() + conn.recv_data(64)

    def waiting_connect(self):
        ip, host = get_ip_and_hostname()
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('0.0.0.0', config.server_port))
        server_socket.listen(9999)
        self.logger.log(f'Server {host}({ip}:{config.server_port}) started, waiting for connection...')
        # 加载服务器所用证书和私钥
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(cert_path := generate_cert())
        os.remove(cert_path)
        while True:
            conn, (peer_ip, _) = server_socket.accept()
            conn = ESocket(context.wrap_socket(conn, server_side=True))
            if not (voucher := self.__before_working(conn)):
                continue
            self.main_conn_recv = conn
            self.host = peer_ip
            break
        while len(self.connections) < self.threads + 1:
            try:
                conn, (ip, port) = server_socket.accept()
                conn = ESocket(context.wrap_socket(conn, server_side=True))
                if ip != peer_ip or conn.recv_data(len(voucher)) != voucher:
                    continue
                self.connections.append(conn)
            except ssl.SSLError as e:
                self.logger.warning(f'SSLError: {e.reason}')
            except TimeoutError:
                self.logger.warning(f'Connection timeout')
        self.main_conn = self.connections.pop()

    def finding_server(self):
        ip, _ = get_ip_and_hostname()
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        try:
            sk.bind(('0.0.0.0', config.server_signal_port))
        except OSError as e:
            self.logger.error(f'Failed to start the broadcast service: {e.strerror}')
            sys.exit(-1)
        self.logger.log(f'Start searching for servers')
        content = f'HI-THERE-IS-FTT_{username}_{ip}_{config.client_signal_port}'.encode(utf8)
        # 先广播自己信息
        broadcast_to_all_interfaces(sk, port=config.server_signal_port, content=content)
        try:
            while True:
                if not select.select([sk], [], [], 0.2)[0]:
                    continue
                data = sk.recv(1024).decode(utf8).split('_')
                if data[0] == 'HI-THERE-IS-FTT':
                    target_username, target_ip, target_port = data[1], data[2], data[3]
                    self.logger.info(f'Received probe request from {target_username}({target_ip})')
                    sk.sendto(f'FTT-CONNECT-REQUEST'.encode(), (target_ip, int(target_port)))  # 单播
                    sk.close()
                    self.host = target_ip
                    self.connect()
                    break
                elif data[0] == 'FTT-CONNECT-REQUEST':
                    sk.close()
                    self.waiting_connect()
                    break
        except KeyboardInterrupt:
            self.logger.close()
            self.__history_file.close()
            sys.exit(0)


if __name__ == '__main__':
    args = get_args()
    # 启动FTC服务
    ftt = FTT(password=args.password, host=args.host, dest=args.dest)
    if not create_folder_if_not_exist(args.dest, ftt.logger):
        sys.exit(-1)
    ftt.start()
