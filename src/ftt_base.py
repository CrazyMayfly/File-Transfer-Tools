import tarfile

from ftt_lib import *
from send2trash import send2trash


class FTTBase:
    def __init__(self, threads: int, single_mode: bool):
        self.threads: int = threads
        self.executor: concurrent.futures.ThreadPoolExecutor = ...
        self._history_file: TextIO = open(read_line_setup(single_mode), 'a', encoding=utf8)
        self.logger: Logger = Logger(PurePath(config.log_dir, f'{datetime.now():%Y_%m_%d}_ftt.log'))

    def _add_history(self, command: str):
        readline.add_history(command)
        self._history_file.write(command + '\n')
        self._history_file.flush()

    def create_folder_if_not_exist(self, folder: Path) -> bool:
        """
        创建文件夹
        @param folder: 文件夹路径
        @return: 是否创建成功
        """
        if folder.exists():
            return True
        try:
            folder.mkdir(parents=True)
        except OSError as error:
            self.logger.error(f'Failed to create {folder}, {error}', highlight=1)
            return False
        self.logger.info(f'Created {folder}')
        return True

    def _compress_log_files(self):
        """
        压缩日志文件
        @return:
        """
        base_dir = config.log_dir
        if not os.path.exists(base_dir):
            return
        # 获取非今天的日志文件名
        today = datetime.now().strftime('%Y_%m_%d')
        pattern = r'^\d{4}_\d{2}_\d{2}_ftt.log'
        files = [entry for entry in os.scandir(base_dir) if entry.is_file() and re.match(pattern, entry.name)
                 and not entry.name.startswith(today)]
        total_size = sum([file.stat().st_size for file in files])
        if len(files) < config.log_file_archive_count and total_size < config.log_file_archive_size:
            return
        dates = [datetime.strptime(file.name[0:10], '%Y_%m_%d') for file in files]
        max_date, min_date = max(dates), min(dates)
        # 压缩后的输出文件名
        output_file = PurePath(base_dir, f'{min_date:%Y%m%d}_{max_date:%Y%m%d}.ftt.tar.gz')
        # 创建一个 tar 归档文件对象
        with tarfile.open(output_file, 'w:gz') as tar:
            # 逐个添加文件到归档文件中
            for file in files:
                tar.add(file.path, arcname=file.name)
        # 若压缩文件完整则将日志文件移入回收站
        if tarfile.is_tarfile(output_file):
            for file in files:
                try:
                    send2trash(PurePath(file.path))
                except Exception as error:
                    self.logger.warning(f'{error}: {file.name} failed to be sent to the recycle bin, delete it.')
                    os.remove(file.path)

        self.logger.success(f'Logs archiving completed: {min_date:%Y/%m/%d} to {max_date:%Y/%m/%d}, '
                            f'{get_size(total_size)} -> {get_size(os.path.getsize(output_file))}')

    def _boot(self):
        pass

    def _shutdown(self):
        pass

    def start(self):
        pass
