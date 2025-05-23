import signal
import struct
import select

from ftt_lib import *
from ftt_base import FTTBase
from ftt_sn import FTTSn


class FTT(FTTBase):
    def __init__(self, password, host, base_dir, threads):
        super().__init__(threads, False)
        self.peer_username: str = ...
        self.peer_platform: str = ...
        self.base_dir: Path = base_dir.expanduser().absolute()
        self.main_conn_recv: ESocket = ...
        self.main_conn: ESocket = ...
        self.busy_lock: threading.Lock = threading.Lock()
        self.connections: list[ESocket] = []
        self.__ftc: FTC = ...
        self.__fts: FTS = ...
        self.__host: str = host
        self.__alive: bool = True
        self.__password: str = password

    def __change_base_dir(self, new_base_dir: str):
        """
        切换FTS的文件保存目录
        """
        if not new_base_dir or new_base_dir.isspace():
            return
        new_base_dir = Path(new_base_dir).expanduser().absolute()
        if new_base_dir.is_file():
            self.logger.error(f'{new_base_dir} is a file, please input a directory')
            return
        if self.create_folder_if_not_exist(new_base_dir):
            self.base_dir = new_base_dir
            self.logger.success(f'File save location changed to: {new_base_dir}')

    def __connect(self):
        try:
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            voucher = self.__password.encode() + self.__first_connect(context, self.__host)
            for i in range(0, self.threads + 1):
                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_socket.connect((self.__host, config.server_port))
                client_socket = ESocket(context.wrap_socket(client_socket, server_hostname='FTS'))
                client_socket.sendall(voucher)
                self.connections.append(client_socket)
            self.main_conn_recv = self.connections.pop()
        except (ssl.SSLError, OSError) as msg:
            self.logger.error(f'Failed to connect to the server {self.__host}, {msg}')
            pause_before_exit(-1)

    def __first_connect(self, context, host):
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # 连接至服务器
        client_socket.connect((host, config.server_port))
        # 将socket包装为securitySocket
        client_socket = ESocket(context.wrap_socket(client_socket, server_hostname='FTS'))
        client_socket.send_head(f'{self.__password}', COMMAND.BEFORE_WORKING, self.threads)
        client_socket.send_head(f'{cur_platform}_{username}', COMMAND.BEFORE_WORKING, 0)
        client_socket.sendall(connect_id := os.urandom(64))
        msg, _, threads = client_socket.recv_head()
        if msg == FAIL:
            self.logger.error('Wrong password to connect to server', highlight=1)
            client_socket.close()
            pause_before_exit(-1)
        # self.logger.info(f'服务器所在平台: {msg}\n')
        self.peer_platform, *peer_username = msg.split('_')
        if self.threads != threads:
            self.logger.info(f"Thread count mismatch, use a lower value: {min(self.threads, threads)}")
        self.threads = min(self.threads, threads)
        self.peer_username = '_'.join(peer_username)
        self.main_conn = client_socket
        return connect_id

    def _shutdown(self, send_info=True):
        try:
            if send_info:
                self.main_conn.send_head('', COMMAND.CLOSE, 0)
            for conn in self.connections + [self.main_conn_recv, self.main_conn]:
                if conn is not ...:
                    conn.close()
        except (ssl.SSLEOFError, ConnectionError):
            pass
        finally:
            self.logger.close()
            self._history_file.close()
            if package:
                os.system('pause')
            os.kill(os.getpid(), signal.SIGINT)

    def __verify_connection(self, conn: ESocket):
        peer_ip, peer_port = conn.getpeername()
        conn.settimeout(4)
        try:
            password, command, threads = conn.recv_head()
            info, _, _ = conn.recv_head()
            peer_platform, *peer_username = info.split('_')
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
        msg = FAIL if password != self.__password else f'{cur_platform}_{username}'
        conn.send_head(msg, COMMAND.BEFORE_WORKING, self.threads)
        if password != self.__password:
            conn.close()
            self.logger.warning(f'Client {peer_ip}:{peer_port} password("{password}") is wrong')
            return

        self.peer_platform = peer_platform
        self.peer_username = '_'.join(peer_username)
        if self.threads != threads:
            self.logger.info(f"Thread count mismatch, use a lower value: {min(self.threads, threads)}")
        self.threads = min(self.threads, threads)
        return self.__password.encode() + conn.recv_data(64)

    def __waiting_connect(self, ip):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server_socket.bind(('0.0.0.0', config.server_port))
        except (OSError, PermissionError):
            server_socket.bind((ip, config.server_port))
        server_socket.listen(100)
        # 加载服务器所用证书和私钥
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(cert_path := generate_cert())
        os.remove(cert_path)
        peer_ip, voucher = None, None
        while True:
            try:
                if not select.select([server_socket], [], [], 0.2)[0]:
                    continue
                conn, (peer_ip, _) = server_socket.accept()
                conn = ESocket(context.wrap_socket(conn, server_side=True))
                if voucher := self.__verify_connection(conn):
                    self.main_conn_recv = conn
                    self.__host = peer_ip
                    break
            except KeyboardInterrupt:
                self._shutdown(send_info=False)
        while len(self.connections) < self.threads + 1:
            try:
                if not select.select([server_socket], [], [], 0.1)[0]:
                    continue
                conn, (ip, port) = server_socket.accept()
                conn = ESocket(context.wrap_socket(conn, server_side=True))
                if ip != peer_ip or conn.recv_data(len(voucher)) != voucher:
                    continue
                self.connections.append(conn)
            except ssl.SSLError as e:
                self.logger.warning(f'SSLError: {e.reason}')
            except TimeoutError:
                self.logger.warning(f'Connection timeout')
            except KeyboardInterrupt:
                self._shutdown(send_info=False)
        server_socket.close()
        self.main_conn = self.connections.pop()

    def __find_server(self, ip):
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        try:
            try:
                sk.bind(('0.0.0.0', config.signal_port))
            except (OSError, PermissionError):
                sk.bind((ip, config.signal_port))
            content = f'HI-THERE-IS-FTT_{username}_{ip}_{config.signal_port}'.encode(utf8)
            # 先广播自己信息
            broadcast_to_all_interfaces(sk, content=content)
            while True:
                if not select.select([sk], [], [], 0.2)[0]:
                    continue
                data = sk.recv(1024).decode(utf8).split('_')
                if data[0] == 'HI-THERE-IS-FTT':
                    *target_username, target_ip, target_port = data[1:]
                    if target_ip == ip:
                        continue
                    target_username = '_'.join(target_username)
                    self.logger.info(f'Received probe request from {target_username}({target_ip})')
                    sk.sendto(f'FTT-CONNECT-REQUEST'.encode(), (target_ip, int(target_port)))  # 单播
                    sk.close()
                    self.__host = target_ip
                    self.__connect()
                    break
                elif data[0] == 'FTT-CONNECT-REQUEST':
                    sk.close()
                    self.__waiting_connect(ip)
                    break
        except OSError as e:
            self.logger.error(f'Failed to start the broadcast service: {e.strerror}')
            pause_before_exit(-1)
        except KeyboardInterrupt:
            self.logger.close()
            self._history_file.close()
            pause_before_exit()

    def _boot(self):
        threading.Thread(name='ArchThread', target=self._compress_log_files, daemon=True).start()
        if self.__host:
            # 处理ip和端口
            if len(splits := self.__host.split(":")) == 2:
                self.__host, config.server_port = splits[0], int(splits[1])
            self.__connect()
        else:
            ip = get_ip()
            self.logger.log(f'Server {username}({ip}:{config.server_port}) started, waiting for connection...')
            if self.__password:
                self.__waiting_connect(ip)
            else:
                self.__find_server(ip)
        self.logger.success(f'Connected to peer {self.peer_username}({self.__host}:{config.server_port})')
        self.executor = concurrent.futures.ThreadPoolExecutor(thread_name_prefix=compact_ip(self.__host))
        self.__ftc, self.__fts = FTC(ftt=self), FTS(ftt=self)
        threading.Thread(name='SeverThread', target=self.__server, daemon=True).start()
        self.logger.info(f'Current threads: {self.threads}')
        self.logger.log(f'Current file storage location: {os.path.normcase(self.base_dir)}')

    def __server(self):
        try:
            while self.__alive:
                filename, command, file_size = self.main_conn_recv.recv_head()
                if command == COMMAND.CLOSE:
                    self.logger.info(f'Peer closed connections')
                    break
                self.__fts.execute(filename, command, file_size)
        except (ConnectionDisappearedError, ssl.SSLEOFError) as e:
            if self.__alive:
                self.logger.error(f'{e}')
        except ConnectionResetError as e:
            if self.__alive:
                self.logger.error(f'{e.strerror}')
        except UnicodeDecodeError:
            self.logger.error(f'Peer data flow abnormality, connection disconnected')
        finally:
            if not self.busy_lock.locked():
                self._shutdown(send_info=False)
            else:
                self.__alive = False

    def start(self):
        self._boot()
        try:
            while self.__alive:
                command = input('> ').strip()
                if not command:
                    continue
                self._add_history(command)
                if command in ['q', 'quit', 'exit']:
                    self.__alive = False
                    break
                elif command.startswith(setbase):
                    self.__change_base_dir(command[8:])
                    continue
                self.__ftc.execute(command)
        except (ssl.SSLError, ConnectionError) as e:
            self.logger.error(e.strerror if e.strerror else e, highlight=1)
        finally:
            self._shutdown()


if __name__ == '__main__':
    args = get_args()
    ftt: FTTBase = FTT(password=args.password, host=args.host, base_dir=args.dest,
                       threads=args.t) if not args.single else FTTSn(threads=args.t)
    ftt.start()
