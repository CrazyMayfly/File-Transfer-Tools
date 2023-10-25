import os
import shutil
import subprocess
from pathlib import Path, PurePath
import platform

parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
resource_dir = os.path.normcase(os.path.join(parent_dir, 'docs/build_guide'))


class Build:
    def __init__(self, folder=False, target_dir_name='FTT', version=''):
        self.__bundle_type = '--onedir' if folder else '--onefile'
        self.__target_dir_name = target_dir_name
        self.__output_dir: Path = Path(parent_dir, target_dir_name)
        self.__log_level = 'INFO'
        self.__version = version
        self.__build_dir: Path = Path(parent_dir, 'build')

    def package(self):
        if not self.__build_dir.exists():
            self.__build_dir.mkdir()
        processes = []
        for program in ['FTC', 'FTS']:
            cmd = f'pyinstaller {self.__bundle_type} --icon="{resource_dir}/{program}.png" --specpath "./build" --upx-dir="{resource_dir}/" --distpath "./{self.__target_dir_name}" --console --log-level {self.__log_level}  ./{program}.py'
            processes.append(subprocess.Popen(args=cmd, cwd=parent_dir, shell=True))
            print(cmd)
            self.__log_level = 'ERROR'
        for process in processes:
            process.wait()
            if process.returncode != 0:
                raise Exception('package failed!')

    def copy_files(self):
        if not Path(self.__output_dir, 'config').exists():
            shutil.copy(PurePath(parent_dir, 'config'), PurePath(self.__output_dir, 'config'))
            print('copied config')

        if self.__bundle_type == '--onedir':
            # 源目录和目标目录的路径
            target_dir = Path(parent_dir, self.__target_dir_name)
            ftc_dir = Path(target_dir, 'FTC')
            fts_dir = Path(target_dir, 'FTS')
            # 获取源目录下的所有文件和子目录
            dirs, fts_names = get_dir_file_name(fts_dir)
            _, ftc_names = get_dir_file_name(ftc_dir)
            file_diff = set(fts_names) - set(ftc_names)
            for item in os.listdir(ftc_dir):
                shutil.move(Path(ftc_dir, item), Path(target_dir, item))
            for item in dirs:
                path = Path(target_dir, item)
                if not path.exists():
                    path.mkdir(parents=True)
            for item in file_diff:
                shutil.move(Path(fts_dir, item), Path(target_dir, item))
            shutil.rmtree(ftc_dir)
            shutil.rmtree(fts_dir)
            print('merge succeed')

    def archive(self):
        system, machine = platform.system().lower(), platform.machine().lower()
        print('archiving')
        if self.__version:
            output_file = f'{self.__output_dir}-{self.__version}-{system}-{machine}'
        else:
            output_file = f'{self.__output_dir}-{system}-{machine}'
        shutil.make_archive(output_file, 'zip', self.__output_dir)
        output_file = output_file + '.zip'
        print(f'Output file {output_file}, size: {get_size(os.path.getsize(output_file))}')
        os.startfile(self.__output_dir.parent, 'explore')

    def clean(self):
        print('cleaning')
        if self.__output_dir.exists():
            shutil.rmtree(self.__output_dir)
        if self.__build_dir.exists():
            shutil.rmtree(self.__build_dir)

    def main(self):
        try:
            self.package()
            self.copy_files()
            self.archive()
        except Exception as error:
            print(error)
        finally:
            self.clean()


def get_size(bytes, factor=1024, suffix="B"):
    """
    Scale bytes to its proper format
    e.g:
        1253656 => '1.20MB'
        1253656678 => '1.17GB'
    """
    for data_unit in ["", "K", "M", "G", "T", "P"]:
        if bytes < factor:
            return f"{bytes:.2f}{data_unit}{suffix}"
        bytes /= factor


def get_dir_file_name(filepath):
    """
    获取某文件路径下的所有文件夹和文件的相对路径
    :param filepath: 文件路径
    :return :返回该文件路径下的所有文件夹、文件的相对路径
    """
    all_dir_name = set()
    all_file_name = []
    # 获取上一级文件夹名称
    for path, _, file_list in os.walk(filepath):
        # 获取相对路径
        path = os.path.relpath(path, filepath)
        all_dir_name.add(path)
        # 去除重复的路径，防止多次创建，降低效率
        all_dir_name.discard(os.path.dirname(path))
        all_file_name += [Path(path, file).as_posix() for file in file_list]
    return all_dir_name, all_file_name


if __name__ == '__main__':
    # version = '2.4.0'
    build = Build(folder=True, target_dir_name='FTT', version='')
    build.main()
