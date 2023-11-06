import os.path
import tempfile
import ipaddress

from FTC import *
from FTS import *
from OpenSSL import crypto
from functools import cache
from argparse import Namespace, ArgumentParser


def get_args() -> Namespace:
    """
    获取命令行参数解析器
    """
    default_path = Path(config.default_path).expanduser()
    parser = ArgumentParser(description='File Transfer Tool, used to transfer files and execute commands.')
    parser.add_argument('-t', metavar='thread', type=int,
                        help=f'Threads (default: {cpu_count})', default=cpu_count)
    parser.add_argument('-host', metavar='host',
                        help='Destination hostname or ip address', default='')
    parser.add_argument('-p', '--password', metavar='password', type=str,
                        help='Set a password for the host or Use a password to connect host.', default='')
    parser.add_argument('-d', '--dest', metavar='base_dir', type=Path,
                        help='File save location (default: {})'.format(default_path), default=default_path)
    return parser.parse_args()


@cache
def get_matches(line):
    matches = [command + ' ' for command in commands if command.startswith(line)]
    if not line:
        return matches
    path, remainder = os.path.split(line)
    if remainder == '..':
        matches += [remainder + os.sep]
    else:
        folders, files = [], []
        path = path or '.'
        try:
            for entry in os.scandir(path):
                if (name := entry.name).startswith(remainder):
                    folders.append(name + os.sep) if entry.is_dir() else files.append(name)
            matches += folders + files
        except (FileNotFoundError, PermissionError):
            pass
    return matches


def completer(_, state):
    matches = get_matches(readline.get_line_buffer())
    return matches[state] if state < len(matches) else None


def read_line_setup() -> Path:
    """
    设置readline的补全和历史记录功能
    """
    readline.set_completer(completer)
    readline.set_history_length(1000)
    readline.parse_and_bind('tab: complete')
    history_filename = Path(config.log_dir, 'history.txt')
    if history_filename.exists():
        readline.read_history_file(history_filename)
    return history_filename


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


def compact_ip(ip, appendix=''):
    return str(socket.inet_aton(ip).hex()) + appendix


def get_ip() -> str:
    st = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        st.connect(('10.255.255.255', 1))
        ip = st.getsockname()[0]
    except OSError:
        ip = '127.0.0.1'
    finally:
        st.close()
    return ip


def broadcast_to_all_interfaces(sk: socket.socket, content: bytes):
    interface_stats = psutil.net_if_stats()
    for interface, addresses in psutil.net_if_addrs().items():
        if not interface_stats[interface].isup:
            continue
        for addr in addresses:
            if addr.family == socket.AF_INET and addr.netmask:
                broadcast_address = ipaddress.IPv4Network(f"{addr.address}/{addr.netmask}",
                                                          strict=False).broadcast_address
                if broadcast_address.is_loopback:
                    continue
                try:
                    sk.sendto(content, (str(broadcast_address), config.signal_port))
                except OSError:
                    pass
