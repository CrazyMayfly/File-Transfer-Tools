import os
import shutil
import subprocess

parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
resource_dir = os.path.normcase(os.path.join(parent_dir, 'docs/build_guide'))


class Build:
    def __init__(self, folder=False, target_dir_name='FTT'):
        self.__bundle_type = '--onedir' if folder else '--onefile'
        self.__target_dir_name = target_dir_name
        self.__output_dir = os.path.join(parent_dir, target_dir_name)
        self.__log_level = 'INFO'
        self.__build_dir = os.path.join(parent_dir, 'build')

    def package(self):
        if not os.path.exists(self.__build_dir):
            os.mkdir(self.__build_dir)
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
        if not os.path.exists(os.path.join(self.__output_dir, 'cert')):
            shutil.copytree(os.path.join(parent_dir, 'cert'), os.path.join(self.__output_dir, 'cert'))
            print('copied cert')
        if not os.path.exists(os.path.join(self.__output_dir, 'config.txt')):
            shutil.copy(os.path.join(parent_dir, 'config.txt'), os.path.join(self.__output_dir, 'config.txt'))
            print('copied config.txt')

        if self.__bundle_type == '--onedir':
            # 源目录和目标目录的路径
            target_dir = os.path.join(parent_dir, self.__target_dir_name)
            ftc_dir = os.path.join(target_dir, 'FTC')
            fts_dir = os.path.join(target_dir, 'FTS')
            # 获取源目录下的所有文件和子目录
            for item in os.listdir(ftc_dir):
                shutil.move(os.path.join(ftc_dir, item), os.path.join(target_dir, item))
            file_diff = set(get_all_relative_file_name(fts_dir)) - set(get_all_relative_file_name(ftc_dir))
            for item in file_diff:
                shutil.move(os.path.join(fts_dir, item), os.path.join(target_dir, item))
            shutil.rmtree(ftc_dir)
            shutil.rmtree(fts_dir)
            print('merge succeed')

    def archive(self):
        print('archiving')
        shutil.make_archive(self.__output_dir, 'zip', self.__output_dir)
        output_file = self.__output_dir + '.zip'
        print(f'Output file {output_file}, size: {get_size(os.path.getsize(output_file))}')

    def clean(self):
        print('cleaning')
        if os.path.exists(self.__output_dir):
            shutil.rmtree(self.__output_dir)
        if os.path.exists(self.__build_dir):
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


def get_all_relative_file_name(filepath):
    """
    获取某文件路径下的所有文件夹和文件的相对路径
    :param filepath: 文件路径
    :return :返回该文件路径下的所有文件夹、文件的相对路径
    """
    all_file_name = []
    for path, _, file_list in os.walk(filepath):
        # 获取相对路径
        path = os.path.relpath(path, filepath)
        all_file_name += [os.path.join(path, file) for file in file_list]
    return all_file_name


if __name__ == '__main__':
    build = Build(folder=True, target_dir_name='FTT')
    build.main()
