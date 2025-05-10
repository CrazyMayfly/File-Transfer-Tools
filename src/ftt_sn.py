import concurrent
import os.path
import shutil
import signal
from ftt_lib import *
from concurrent.futures import ThreadPoolExecutor
from ftt_base import FTTBase


@dataclass
class CopyFolderMeta:
    source: str
    target: str
    pbar: PbarManager
    large_files_info: deque[list]
    small_files_info: deque[list]
    finished_files: list[str]


class FTTSn(FTTBase):
    def __init__(self, threads):
        super().__init__(threads, True)
        self.__meta: CopyFolderMeta = ...

    def _boot(self):
        self.logger.info('In Single Node Mode')
        self.logger.info(f'Current threads: {self.threads}')
        threading.Thread(name='ArchThread', target=self._compress_log_files, daemon=True).start()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.threads)

    def _shutdown(self):
        self.logger.close()
        self._history_file.close()
        if package:
            os.system('pause')
        os.kill(os.getpid(), signal.SIGINT)

    def __compare_folder(self, source: str, target: str):
        source_files_info = get_files_info_relative_to_basedir(source, 'source')
        target_files_info = get_files_info_relative_to_basedir(target, 'target')
        compare_result = compare_files_info(source_files_info, target_files_info)
        msgs = print_compare_result(source, target, compare_result)
        self.logger.silent_write(msgs)

        files_info_equal = compare_result[2]
        if not files_info_equal:
            return
        command = input("Continue to compare hash for filename and size both equal set?(y/n): ").lower()
        if command not in ('y', 'yes'):
            return
        source_results = FileHash.parallel_calc_hash(source, files_info_equal, True)
        target_results = FileHash.parallel_calc_hash(target, files_info_equal, True)
        hash_not_matching = [filename for filename in files_info_equal if
                             source_results[filename] != target_results[filename]]
        msg = ["hash not matching: "] + [('\t' + file_name) for file_name in hash_not_matching]
        print('\n'.join(msg))

        files_hash_equal = [filename for filename in files_info_equal if os.path.getsize(
            PurePath(source, filename)) >> SMALL_FILE_CHUNK_SIZE and filename not in hash_not_matching]
        if not files_hash_equal:
            return
        source_results = FileHash.parallel_calc_hash(source, files_info_equal, False)
        target_results = FileHash.parallel_calc_hash(target, files_info_equal, False)
        for filename in files_hash_equal:
            if source_results[filename] != target_results[filename]:
                print('\t' + filename)
                msg.append('\t' + filename)
        if len(msg) == 1:
            print('\t' + 'None')
            msg.append('\t' + 'None')
        msg.append('')
        self.logger.silent_write(['\n'.join(msg)])

    def __prepare_to_send(self, source: str, target: str):
        source_folders, source_files = get_dir_file_name(source, desc_suffix='source')
        target_folders, target_files = get_dir_file_name(target, desc_suffix='target') if os.path.exists(
            target) else ({}, [])

        makedirs(self.logger, set(source_folders.keys()) - set(target_folders.keys()), target)
        # 接收对方已有的文件名并计算出对方没有的文件
        files = set(source_files) - set(target_files)
        self.logger.info(f"{len(source_files) - len(files)} files already exists in target")
        if not files:
            self.logger.info('No files to send', highlight=1)
            return None
        large_files_info, small_files_info, _, pbar = collect_files_info(self.logger, files, source)
        self.__meta = CopyFolderMeta(source, target, PbarManager(pbar), large_files_info, small_files_info, [])
        return files

    def __send_large_files(self, position: int):
        view = memoryview(buf := bytearray(4096))
        while len(self.__meta.large_files_info):
            filename, file_size, time_info = self.__meta.large_files_info.pop()
            source_file = PurePath(self.__meta.source, filename)
            target_file = avoid_filename_duplication(str(PurePath(self.__meta.target, filename)))
            target_temp = f'{target_file}.ftsdownload'
            try:
                with open(source_file, 'rb') as sfp, open(target_temp, 'wb') as tfp:
                    # 服务端已有的文件大小
                    target_size = os.path.getsize(target_temp)
                    sfp.seek(target_size, 0)
                    pbar_width = get_terminal_size().columns / 4
                    with tqdm(total=file_size - target_size, desc=shorten_path(filename, pbar_width), unit='bytes',
                              unit_scale=True, mininterval=0.3, position=position, leave=False, disable=position == 0,
                              unit_divisor=1024) as pbar:
                        copied_size = 0
                        while size := sfp.readinto(buf):
                            tfp.write(view[:size])
                            copied_size += size
                            # 4MB
                            if copied_size >> 22:
                                pbar.update(copied_size)
                                self.__meta.pbar.update(copied_size)
                                copied_size = 0
                        pbar.update(copied_size)
                        self.__meta.pbar.update(copied_size)
                os.rename(target_temp, target_file)
                shutil.copystat(source_file, target_file)
                self.__meta.pbar.update(target_size, decrease=True)
                self.__meta.finished_files.append(filename)
            except FileNotFoundError as e:
                self.logger.error(f'Failed to open: {e.filename}')
                continue
            except PermissionError as err:
                self.logger.warning(f'Failed to rename: {target_temp} -> {target_file}, {err}')
            except Exception as e:
                self.logger.error(f"Failed to copy large file: {e}", highlight=1)

    def __send_small_files(self, position: int):
        idx, files_info = 0, []
        while len(self.__meta.small_files_info):
            try:
                total_size, num, files_info = self.__meta.small_files_info.pop()
                with tqdm(total=total_size, desc=f'{num} small files', unit='bytes', unit_scale=True,
                          mininterval=0.2, position=position, leave=False, unit_divisor=1024) as pbar:
                    for idx, (filename, file_size, _) in enumerate(files_info):
                        shutil.copy2(os.path.join(self.__meta.source, filename),
                                     os.path.join(self.__meta.target, filename))
                        pbar.update(file_size)
                self.__meta.pbar.update(total_size)
            except Exception as e:
                self.logger.error(f"Failed to copy small files: {e}", highlight=1)
            finally:
                self.__meta.finished_files.extend([filename for filename, _, _ in files_info[:idx + 1]])

    def __send_file(self, position: int):
        if position < 3:
            self.__send_large_files(position)
            self.__send_small_files(position)
        else:
            self.__send_small_files(position)
            self.__send_large_files(position)

    def __force_sync_folder(self, source, target):
        """
        强制将本地文件夹的内容同步到对方文件夹，同步后双方文件夹中的文件内容一致
        """
        source_files_info = get_files_info_relative_to_basedir(source, 'source')
        target_files_info = get_files_info_relative_to_basedir(target, 'target')
        files_smaller_than_target, files_smaller_than_source, files_info_equal, files_not_exist_in_target, file_not_exists_in_source = compare_files_info(
            source_files_info, target_files_info)

        source_results = get_files_modified_time(source, files_info_equal, 'source')
        target_results = get_files_modified_time(target, files_info_equal, 'target')
        mtime_not_matching = [filename for filename in files_info_equal if
                              int(source_results[filename]) != int(target_results[filename])]
        msgs = ['\n[INFO   ] ' + get_log_msg(
            f'Force sync files: source folder {source} -> target folder {target}\n')]
        for arg in [("files exist in target but not in source: ", file_not_exists_in_source),
                    ("files in source smaller than target: ", files_smaller_than_target),
                    ("files in target smaller than source: ", files_smaller_than_source)]:
            msgs.append(print_filename_if_exists(*arg, print_if_empty=False))
        msg = ["files modified time not matching: "]
        if mtime_not_matching:
            msg.extend([
                f'\t{filename}: {format_timestamp(source_results[filename])} <-> {format_timestamp(target_results[filename])}'
                for filename in mtime_not_matching])
        else:
            msg.append('\tNone')
        if mtime_not_matching:
            print('\n'.join(msg))
        msg.append('')
        self.logger.silent_write(msgs)

        files_to_remove = files_smaller_than_target + files_smaller_than_source + file_not_exists_in_source + mtime_not_matching
        if len(files_to_remove) != 0:
            command = input(
                f"Continue to force sync files in source folder({source})\n"
                f"    with above files removed in target folder?(y/n): ").lower()
            if command not in ('y', 'yes'):
                return
        self.logger.silent_write([print_filename_if_exists('Files to be removed:', files_to_remove, False)])
        for file_rel_path in tqdm(files_to_remove, delay=0.1, desc='Removing files', unit='files', leave=False):
            try:
                send2trash.send2trash(PurePath(target, file_rel_path))
            except Exception as e:
                self.logger.warning(f'Failed to remove {file_rel_path}, reason: {e}')
        self.__copy_folder(source, target)

    def __copy_folder(self, source: str, target: str):
        if not (files := self.__prepare_to_send(source, target)):
            return
        # 发送文件
        futures = [self.executor.submit(self.__send_file, position) for position in range(1, self.threads + 1)]
        for future in futures:
            while not future.done():
                time.sleep(0.2)

        fails = files - set(self.__meta.finished_files)
        self.__meta.finished_files.clear()
        # 比对发送失败的文件
        self.__meta.pbar.set_status(len(fails) > 0)
        if fails:
            self.logger.error("Failed to copy: ", highlight=1)
            for fail in fails:
                self.logger.warning(fail)
        errors = [future.exception() for future in futures]
        if errors.count(None) != len(errors):
            errors = '\n'.join([f'Thread-{idx}: {exception}' for idx, exception in enumerate(errors) if exception])
            self.logger.error(f"Exceptions occurred during this sending: \n{errors}", highlight=1)

    def execute(self, command):
        if command == sysinfo:
            print_sysinfo(get_sys_info())
        elif command.startswith((compare, force_sync, cp)):
            cmd, source, target = parse_command(command)
            if not cmd:
                self.logger.warning('Invalid command')
                return

            if not os.path.isdir(source) or not os.path.exists(source):
                self.logger.warning('Source folder does not exist')
                return

            if (not os.path.isdir(target) or not os.path.exists(target)) and command.startswith((compare, force_sync)):
                self.logger.warning('Target folder does not exist')
                return

            if cmd == cp:
                self.__copy_folder(source, target)
            elif cmd == compare:
                self.__compare_folder(source, target)
            else:
                self.__force_sync_folder(source, target)

        elif command.startswith(history):
            print_history(int(command.split()[1])) if len(command.split()) > 1 and command.split()[
                1].isdigit() else print_history()
        else:
            self.logger.warning(f'Unknown command: {command}')

    def start(self):
        self._boot()

        try:
            while True:
                command = input('> ').strip()
                if not command:
                    continue
                self._add_history(command)
                if command in ['q', 'quit', 'exit']:
                    break
                self.execute(command)
        except Exception as e:
            self.logger.error(f"Error occurred: {e}", highlight=1)
            print(e)
        finally:
            self._shutdown()
