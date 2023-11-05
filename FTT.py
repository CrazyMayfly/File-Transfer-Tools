from FTC import *
from FTS import *

username = psutil.users()[0].name


class FTT:
    def __init__(self, password='', host='', threads=6):
        self.voucher = None
        self.__command_prefix = None
        self.__peer_platform = None
        self.host = host
        self.threads = threads
        self.password = password
        self.main_conn = ...
        self.connections = []
        self.logger = Logger(PurePath(config.log_dir, f'{datetime.now():%Y_%m_%d}_ftt.log'))

    def main(self):
        pass

    def prepare(self):
        if self.host:
            # 处理ip和端口
            if len(splits := self.host.split(":")) == 2:
                config.server_port = int(splits[1])
                self.host = splits[0]
            self.connect(host=self.host)
            return
        if self.password:
            self.waiting_connect()
        else:
            self.finding_server()

    def connect(self, host):
        try:
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            id = os.urandom(64)
            # 连接至服务器
            client_socket.connect((host, config.server_port))
            # 将socket包装为securitySocket
            client_socket = ESocket(context.wrap_socket(client_socket, server_hostname='FTS'))
            client_socket.send_head(f'{self.password}_{platform_}_{username}', COMMAND.BEFORE_WORKING, self.threads)
            client_socket.sendall(id)
            msg, _, threads = client_socket.recv_head()
            if msg == FAIL:
                self.logger.error('Wrong password to connect to server', highlight=1)
                # self.shutdown(send_close_info=False)
                sys.exit(-1)
            else:
                # self.logger.info(f'服务器所在平台: {msg}\n')
                self.__peer_platform, peer_username = msg.split('_')
                self.__command_prefix = 'powershell ' if self.__peer_platform == WINDOWS else ''
                self.logger.success(f'Connected to the server {peer_username}({host}:{config.server_port})')
                self.threads = min(self.threads, threads)
            self.connections.append(client_socket)
            voucher = self.password.encode() + id
            for i in range(1, self.threads):
                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                # 连接至服务器
                client_socket.connect((host, config.server_port))
                # 将socket包装为securitySocket
                client_socket = ESocket(context.wrap_socket(client_socket, server_hostname='FTS'))
                client_socket.sendall(voucher)
                self.connections.append(client_socket)
        except (ssl.SSLError, OSError) as msg:
            self.logger.error(f'Failed to connect to the server {host}, {msg}')
            sys.exit(-1)

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

        self.voucher = self.password.encode() + conn.recv_data(64)
        self.peer_platform = peer_platform
        self.threads = min(self.threads, threads)
        return True

    def waiting_connect(self):
        ip, host = get_ip_and_hostname()
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('0.0.0.0', config.server_port))
        server_socket.listen(9999)
        self.logger.log(f'Server {host}({ip}:{config.server_port}) started, waiting for connection...')
        # self.logger.log('Current file storage location: ' + os.path.normcase(self.__base_dir))
        # 加载服务器所用证书和私钥
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(cert_path := generate_cert())
        os.remove(cert_path)
        while True:
            conn, (peer_ip, _) = server_socket.accept()
            conn = ESocket(context.wrap_socket(conn, server_side=True))
            if not self.__before_working(conn):
                continue
            self.main_conn = conn
            self.connections.append(conn)
        while len(self.connections) < self.threads:
            try:
                conn, (ip, port) = server_socket.accept()
                conn.settimeout(4)
                conn = ESocket(context.wrap_socket(conn, server_side=True))
                if ip != peer_ip or conn.recv_data(len(self.voucher)) != self.voucher:
                    # self.logger.warning(f'Connection from {ip}:{port} refused')
                    continue
                conn.settimeout(None)
                self.connections.append(conn)
            except ssl.SSLError as e:
                self.logger.warning(f'SSLError: {e.reason}')
            except TimeoutError:
                self.logger.warning(f'Connection timeout')

        # self.logger.info(f'Connected')

    def finding_server(self):
        ip, host = get_ip_and_hostname()
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        try:
            sk.bind(('0.0.0.0', config.server_signal_port))
        except OSError as e:
            self.logger.error(f'Failed to start the broadcast service: {e.strerror}')
            sys.exit(-1)
        self.logger.log(f'Start searching for servers')
        content = f'HI-THERE-IS-FTT_{host}_{ip}_{config.client_signal_port}'.encode(utf8)
        # 先广播自己信息
        broadcast_to_all_interfaces(sk, port=config.server_signal_port, content=content)
        try:
            while True:
                if not select.select([sk], [], [], 0.2)[0]:
                    continue
                data = sk.recv(1024).decode(utf8).split('_')
                if data[0] == 'HI-THERE-IS-FTT':
                    target_host, target_ip, target_port = data[1], data[2], data[3]
                    self.logger.info(f'Received probe request from {target_host}({target_ip})')
                    sk.sendto(f'FTT-CONNECT-REQUEST', (target_ip, int(target_port)))  # 单播
                    sk.close()
                    self.connect(target_ip)
                    break
                elif data[0] == 'FTT-CONNECT-REQUEST':
                    sk.close()
                    self.waiting_connect()
                    break
        except KeyboardInterrupt:
            self.logger.close()
            # self.__history_file.close()
            sys.exit(0)


if __name__ == '__main__':
    args = ftc_get_args()
    # 启动FTC服务
    ftt = FTT(password=args.password, host=args.host)
    ftt.prepare()
