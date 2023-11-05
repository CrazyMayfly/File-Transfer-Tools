import os.path
import random
import struct
import subprocess
import ssl
import tempfile
import signal
import concurrent.futures
from Utils import *
from sys_info import *
from uuid import uuid4
from pathlib import Path
from OpenSSL import crypto
from argparse import ArgumentParser, Namespace


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
    from win_set_time import set_times


def compact_ip(ip, appendix=''):
    return str(socket.inet_aton(ip).hex()) + appendix


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


def create_folder_if_not_exist(folder: Path, logger: Logger) -> bool:
    """
    创建文件夹
    @param folder: 文件夹路径
    @param logger: 日志对象
    @return: 是否创建成功
    """
    if folder.exists():
        return True
    try:
        folder.mkdir(parents=True)
    except OSError as error:
        logger.error(f'Failed to create {folder}, {error}', highlight=1)
        return False
    logger.info(f'Created {folder}')
    return True


class FTS:
    def __init__(self, base_dir, logger, connections, executor):
        self.executor = executor
        self.main_conn = connections.pop()
        self.connections = connections
        self.base_dir: Path = Path(base_dir)
        self.logger = logger

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
                set_times(file_path, create_timestamp, modify_timestamp, access_timestamp)
            elif platform_ == LINUX:
                os.utime(path=file_path, times=(access_timestamp, modify_timestamp))
        except Exception as error:
            self.logger.warning(f'{file_path} file time modification failed, {error}')

    def __compare_folder(self, conn: ESocket, folder):
        self.logger.info(f"Client request to compare folder: {folder}")
        if not os.path.exists(folder):
            # 发送目录不存在
            conn.send_size(CONTROL.CANCEL)
            return
        conn.send_size(CONTROL.CONTINUE)
        # 将数组拼接成字符串发送到客户端
        conn.send_with_compress(get_files_info_relative_to_basedir(folder))
        if conn.recv_size() != CONTROL.CONTINUE:
            return
        self.logger.log("Continue to compare hash")
        file_size_and_name_both_equal = conn.recv_with_decompress()
        # 得到文件相对路径名: hash值字典
        results = {filename: get_file_md5(PurePath(folder, filename)) for filename in
                   file_size_and_name_both_equal}
        conn.send_with_compress(results)

    def __execute_command(self, conn: ESocket, command):
        out = subprocess.Popen(args=command, shell=True, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT).stdout
        output = [f'[LOG    ] {get_log_msg("Execute command")}: {command}']
        while result := out.readline():
            conn.send_head(result, COMMAND.EXECUTE_RESULT, 0)
            output.append(result)
        # 命令执行结束
        conn.send_head('', COMMAND.FINISH, 0)
        self.logger.silent_write(output)

    def __speedtest(self, conn: ESocket, data_size):
        self.logger.info(f"Client request speed test, size: {get_size(2 * data_size, factor=1000)}")
        start = time.time()
        data_unit = 1000 * 1000
        for i in range(0, int(data_size / data_unit)):
            conn.recv_data(data_unit)
        show_bandwidth('Download speed test completed', data_size, time.time() - start, self.logger)
        download_over = time.time()
        for i in range(0, int(data_size / data_unit)):
            conn.sendall(os.urandom(data_unit))
        show_bandwidth('Upload speed test completed', data_size, time.time() - download_over, self.logger)

    def __makedirs(self, dir_names, base_dir):
        for dir_name in dir_names:
            cur_dir = Path(base_dir, dir_name)
            if cur_dir.exists():
                continue
            try:
                cur_dir.mkdir()
            except FileNotFoundError:
                self.logger.error(f'Failed to create folder {cur_dir}', highlight=1)

    def __recv_files_in_folder(self, cur_dir):
        files = []
        if cur_dir.exists():
            for path, _, file_list in os.walk(cur_dir):
                files += [PurePath(PurePath(path).relative_to(cur_dir), file).as_posix() for file in file_list]
        main_conn = self.main_conn
        dirs_info: dict = main_conn.recv_with_decompress()
        self.__makedirs(dirs_info.keys(), cur_dir)
        # 发送已存在的文件名
        main_conn.send_with_compress(files)
        futures = [self.executor.submit(self.__slave_work, conn, cur_dir) for conn in self.connections]
        concurrent.futures.wait(futures)
        for dir_name, times in dirs_info.items():
            cur_dir = PurePath(cur_dir, dir_name)
            try:
                os.utime(path=cur_dir, times=times)
            except Exception as error:
                self.logger.warning(f'Folder {cur_dir} time modification failed, {error}', highlight=1)

    def __recv_small_files(self, conn: ESocket, cur_dir, files_info):
        real_path = Path("")
        try:
            msgs = []
            for filename, file_size, time_info in files_info:
                real_path = Path(cur_dir, filename)
                real_path.write_bytes(conn.recv_data(file_size))
                self.__modify_file_time(str(real_path), *time_info)
                msgs.append(f'[SUCCESS] {get_log_msg("Received")}: {real_path}\n')
            self.logger.success(f'Received small files chunk, number: {len(files_info)}')
            self.logger.silent_write(msgs)
        except ConnectionDisappearedError:
            self.logger.warning(f'Connection was terminated unexpectedly and reception failed: {real_path}')
        except FileNotFoundError:
            self.logger.warning(f'File creation/opening failed that cannot be received: {real_path}', highlight=1)

    def __recv_large_file(self, conn: ESocket, cur_dir, filename, file_size):
        original_file = avoid_filename_duplication(str(PurePath(cur_dir, filename)))
        cur_download_file = f'{original_file}.ftsdownload'
        try:
            with open(cur_download_file, 'ab') as fp:
                conn.send_size(size := os.path.getsize(cur_download_file))
                rest_size = file_size - size
                while rest_size >> 12:
                    rest_size -= len(data := conn.recv())
                    fp.write(data)
                fp.write(conn.recv_data(rest_size))
            os.rename(cur_download_file, original_file)
            self.logger.success(f'Received: {original_file}')
            timestamps = times_struct.unpack(conn.recv_data(times_struct.size))
            self.__modify_file_time(original_file, *timestamps)
        except ConnectionDisappearedError:
            self.logger.warning(f'Connection was terminated unexpectedly and reception failed: {original_file}')
        except PermissionError as err:
            self.logger.warning(f'Failed to rename: {cur_download_file} -> {original_file}, {err}')
        except FileNotFoundError:
            self.logger.warning(f'File creation/opening failed that cannot be received: {original_file}', highlight=1)
            conn.sendall(size_struct.pack(CONTROL.FAIL2OPEN))

    def __slave_work(self, conn: ESocket, cur_dir):
        """
        从连接的工作，只用于处理多文件接收

        @param conn: 从连接
        """
        try:
            while True:
                filename, command, file_size = conn.recv_head()
                if command == COMMAND.SEND_LARGE_FILE:
                    self.__recv_large_file(conn, cur_dir, filename, file_size)
                elif command == COMMAND.SEND_SMALL_FILE:
                    self.__recv_small_files(conn, cur_dir, conn.recv_with_decompress())
                elif command == COMMAND.FINISH:
                    break
        except ConnectionError:
            return
        except Exception as e:
            msg = 'Peer data flow abnormality, connection disconnected' if isinstance(e, UnicodeDecodeError) else str(e)
            self.logger.error(msg, highlight=1)

    def execute(self, filename, command, file_size):
        """
        主连接的工作
        """
        match command:
            case COMMAND.SEND_FILES_IN_FOLDER:
                self.__recv_files_in_folder(Path(self.base_dir, filename))
            case COMMAND.SEND_LARGE_FILE:
                self.__recv_large_file(self.main_conn, self.base_dir, filename, file_size)
            case COMMAND.COMPARE_FOLDER:
                self.__compare_folder(self.main_conn, filename)
            case COMMAND.EXECUTE_COMMAND:
                self.__execute_command(self.main_conn, filename)
            case COMMAND.SYSINFO:
                self.main_conn.send_with_compress(get_sys_info())
            case COMMAND.SPEEDTEST:
                self.__speedtest(self.main_conn, file_size)
            case COMMAND.PULL_CLIPBOARD:
                send_clipboard(self.main_conn, self.logger, ftc=False)
            case COMMAND.PUSH_CLIPBOARD:
                get_clipboard(self.main_conn, self.logger, filename, command, file_size, ftc=False)


if __name__ == '__main__':
    # args = get_args()
    # fts = FTS(base_dir=args.dest, password=args.password)
    # if not create_folder_if_not_exist(args.dest, fts.logger):
    #     sys.exit(-1)
    # fts.start()
    pass
