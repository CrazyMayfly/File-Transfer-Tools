import argparse
import os.path
import pathlib
import socket
import ssl

from Utils import *
from sys_info import *


class FTS:
    def __init__(self, base_dir, ssl, avoid):
        log_file_path = os.path.join(log_dir, datetime.now().strftime('%Y_%m_%d') + '_server.log')
        print('本次日志文件存放位置为: ' + log_file_path)
        self.__log_file = open(log_file_path, 'a', encoding='utf-8')
        self.__log_lock = threading.Lock()
        self.ip = ''
        self.base_dir = base_dir
        self.__log_line = 0
        self.__use_ssl = ssl
        self.__avoid_file_duplicate = avoid

    def avoid_filename_duplication(self, filename, filesize):
        if os.path.exists(filename):
            if self.__avoid_file_duplicate:
                if os.stat(filename).st_size < filesize:
                    return filename, False
                else:
                    return filename, True
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
            return filename, True
        else:
            return filename, False

    def _log(self, msg, color='white', highlight=0):
        msg = get_log_msg(msg)
        level = 'INFO'
        if color == 'yellow':
            level = 'WARNING'
        if color == 'red':
            level = 'ERROR'
        with self.__log_lock:
            print_color(msg=msg, color=color, highlight=highlight)
            self.__log_line += 1
            self.__log_file.write('[{}] {}\n'.format(level, msg))
            if self.__log_line % 100 == 0:
                self.__log_file.flush()

    def _deal_data(self, conn, addr):
        self._log('客户端连接 {0}'.format(addr), 'blue')
        while True:
            try:
                filehead = receive_data(conn, fileinfo_size)
                if filehead:
                    filename, command, filesize = struct.unpack(fmt, filehead)
                    filename = filename.decode('UTF-8').strip('\00')
                    command = command.decode().strip('\00')
                    if command == SEND_DIR:
                        # 处理文件夹
                        cur_dir = os.path.join(self.base_dir, filename)
                        if not os.path.exists(cur_dir):
                            os.makedirs(cur_dir)
                            self._log('创建文件夹 {0}'.format(cur_dir))
                    elif command == SEND_FILE:
                        if self._recv_file(conn, filename, filesize, addr):
                            return
                    elif command == COMPARE_DIR:
                        self._compare_dir(conn, filename)
                    elif command == COMMAND:
                        self._execute_command(conn, filename)
                    elif command == SYSINFO:
                        self._compare_sysinfo(conn)
                    elif command == SPEEDTEST:
                        self._speedtest(conn, filesize)
            except ConnectionResetError as e:
                self._log(f'{addr[0]}:{addr[1]} {e.strerror}', color='yellow')
                break
            finally:
                # 每执行完一个操作写入日志文件
                with self.__log_lock:
                    self.__log_file.flush()

    def _signal_online(self):
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        sk.bind((self.ip, server_signal_port))
        content = ('04c8979a-a107-11ed-a8fc-0242ac120002_{}_{}'.format(self.ip, self.__use_ssl)).encode('UTF-8')
        addr = (self.ip[0:self.ip.rindex('.')] + '.255', client_signal_port)
        self._log('广播主机信息服务已启动')
        # 广播
        sk.sendto(content, addr)
        while True:
            data = sk.recv(1024).decode('UTF-8').split('_')
            if data[0] == '53b997bc-a140-11ed-a8fc-0242ac120002':
                target_ip = data[1]
                self._log('收到来自 {0} 的探测请求'.format(target_ip))
                # 单播
                sk.sendto(content, (target_ip, client_signal_port))

    def main(self):
        host = socket.gethostname()
        self.ip = socket.gethostbyname(host)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', server_port))
        s.listen(999)
        if self.__use_ssl:
            self._log('当前数据使用加密传输', color='green')
        else:
            self._log('当前数据未进行加密传输', color='yellow')
        self._log('服务器 {0}({1}) 已启动，等待连接...'.format(host, self.ip))
        self._log('当前默认文件存放位置为：' + self.base_dir)
        with self.__log_lock:
            self.__log_file.flush()
        threading.Thread(target=self._signal_online).start()
        if self.__use_ssl:
            # 生成SSL上下文
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            # 加载服务器所用证书和私钥
            context.load_cert_chain(os.path.join(cert_dir, 'server.crt'),
                                    os.path.join(cert_dir, 'server_rsa_private.pem'))
            with context.wrap_socket(s, server_side=True) as ss:
                while True:
                    try:
                        conn, addr = ss.accept()
                        t = threading.Thread(target=self._deal_data, args=(conn, addr))
                        t.start()
                    except ssl.SSLError as e:
                        self._log(f'SSLError: {e.reason}', color='yellow')

        else:
            while True:
                conn, addr = s.accept()
                t = threading.Thread(target=self._deal_data, args=(conn, addr))
                t.start()

    def _recv_file(self, conn, filename, filesize, addr):
        if filename == 'd1132ce8-7d22-434d-a4e9-75d81187d0ba':
            conn.close()
            self._log('终止与客户端 {0} 的连接'.format(addr), 'blue')
            # 返回True表示终止循环
            return True

        new_filename, file_exist = self.avoid_filename_duplication(os.path.join(self.base_dir, filename),
                                                                   filesize)
        if file_exist and self.__avoid_file_duplicate:
            self._log('{} 文件重复，取消接收'.format(os.path.join(self.base_dir, filename)), 'yellow')
            conn.send(CANCEL.encode('utf-8'))
        else:
            unit_1, unit_2 = calcu_size(filesize)
            conn.send(CONTINUE.encode('utf-8'))
            self._log('准备接收文件 {0}， 大小约 {1}，{2}'.format(new_filename, unit_1, unit_2))
            md5 = hashlib.md5()
            begin = time.time()
            fp = open(new_filename, 'wb')
            rest_size = filesize
            while rest_size > 0:
                recv_window = min(unit, rest_size)
                data = conn.recv(recv_window)
                rest_size -= len(data)
                md5.update(data)
                fp.write(data)
            fp.close()
            recv_digest = receive_data(conn, 16)
            digest = md5.digest()
            if recv_digest == digest:
                color = 'green'
                msg = 'Hash 比对一致'
                highlight = 0
                filename_confirm = struct.pack(filename_fmt, filename.encode("UTF-8"))
            else:
                color = 'red'
                msg = 'Hash 比对失败'
                highlight = 1
                filename_confirm = struct.pack(filename_fmt, "fail to receive".encode("UTF-8"))
            conn.send(filename_confirm)
            time_cost = time.time() - begin
            if time_cost == 0:
                time_cost = 0.00001
            self._log('{} 接收成功，MD5：{}，{}，耗时：{} s，平均速度为 {} MB/s\n'.
                      format(new_filename, digest.hex(), msg, round(time_cost, 2),
                             round(filesize / 1000000 / time_cost, 2)), color, highlight)
        return False

    def _compare_dir(self, conn, dirname):
        self._log(f"客户端请求对比文件夹：{dirname}")
        if os.path.exists(dirname):
            conn.send(DIRISCORRECT.encode())
            # 将数组拼接成字符串发送到客户端
            relative_filename = json.dumps(get_relative_filename_from_basedir(dirname), ensure_ascii=True).encode()
            # 先发送字符串的大小
            str_len_head = struct.pack(str_len_fmt, len(relative_filename))
            conn.send(str_len_head)
            # 再发送字符串
            conn.send(relative_filename)
            is_continue = receive_data(conn, 8).decode() == CONTINUE
            if is_continue:
                self._log("继续对比文件Hash")
                str_len = receive_data(conn, str_len_size)
                str_len = struct.unpack(str_len_fmt, str_len)[0]
                filesize_and_name_both_equal = receive_data(conn, str_len).decode("UTF-8").split("|")
                # 得到文件相对路径名: hash值字典
                results = {}
                for filename in filesize_and_name_both_equal:
                    real_path = os.path.join(dirname, filename)
                    results.update({filename: get_file_md5(real_path)})
                data = json.dumps(results, ensure_ascii=True).encode()
                conn.send(struct.pack(str_len_fmt, len(data)))
                conn.send(data)
                self._log("Hash 比对结束。")
            else:
                self._log("不继续比对Hash")
        else:
            conn.send(b'\00' * len(DIRISCORRECT))

    def _execute_command(self, conn, command):
        self._log("执行命令：" + command)
        result = os.popen("powershell " + command)
        s = result.read(1)
        while s:
            # UTF-32 为定宽字符编码
            conn.send(s.encode("UTF-32"))
            print(s, end='')
            s = result.read(1)
        # 命令执行结束
        conn.send(b'\00' * 8)

    def _compare_sysinfo(self, conn):
        self._log("目标获取系统信息")
        info = get_sys_info()
        data = json.dumps(info, ensure_ascii=True).encode()
        # 发送数据长度
        str_len = struct.pack(str_len_fmt, len(data))
        conn.send(str_len)
        # 发送数据
        conn.send(data)

    def _speedtest(self, conn, data_size):
        self._log(f"客户端请求速度测试，数据量为: {get_size(data_size, factor=1000)}")
        start = time.time()
        data_unit = 1000 * 1000
        for i in range(0, int(data_size / data_unit)):
            receive_data(conn, data_unit)
        time_cost = time.time() - start
        self._log(f"速度测试完毕, 耗时 {time_cost:.2f}s, 平均速度{get_size(data_size / time_cost, factor=1000)}/s.",
                  color='green')


if __name__ == '__main__':
    # base_dir = input('请输入文件保存位置（输入1默认为桌面）：')
    parser = argparse.ArgumentParser(description='File Transfer Server, used to RECEIVE files.')
    default_path = os.path.expanduser("~\Desktop")
    parser.add_argument('-d', '--dest', metavar='base_dir', type=pathlib.Path,
                        help='File storage location (default: {})'.format(default_path), default=default_path)
    parser.add_argument('-p', '--plaintext', action='store_true',
                        help='Use plaintext transfer (default: use ssl)')
    parser.add_argument('--avoid', action='store_true',
                        help='Do not continue the transfer when the file name is repeated.')
    args = parser.parse_args()
    base_dir = pathlib.PureWindowsPath(args.dest).as_posix()
    while not os.path.isdir(base_dir):
        base_dir = input('路径有误，请重新输入：')

    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
        print_color(get_log_msg('已创建文件夹 {}'.format(base_dir)))

    fts = FTS(base_dir, not args.plaintext, args.avoid)
    if not packaging:
        fts.main()
    else:
        try:
            fts.main()
        finally:
            os.system('pause')
            # input('请按任意键继续. . .')
