import os
import shutil
import subprocess
from pathlib import Path, PurePath
import platform

parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
resource_dir = os.path.normcase(os.path.join(parent_dir, 'docs/build_guide'))
src_dir = os.path.normcase(os.path.join(parent_dir, 'src'))


class Build:
    def __init__(self, folder=False, target_dir_name='FTT', version=''):
        self.__bundle_type = '--onedir' if folder else '--onefile'
        self.__target_dir_name = target_dir_name
        self.__output_dir: Path = Path(parent_dir, target_dir_name)
        self.__version = version
        self.__build_dir: Path = Path(parent_dir, 'build')

    def package(self):
        if not self.__build_dir.exists():
            self.__build_dir.mkdir()
        cmd = f'pyinstaller {self.__bundle_type} --icon="{resource_dir}/FTT.png" --specpath "./build" --upx-dir="{resource_dir}/" --distpath "./{self.__target_dir_name}" --console --log-level INFO  ./src/FTT.py'
        print(cmd)
        subprocess.call(args=cmd, cwd=parent_dir, shell=True)

    def copy_files(self):
        if not Path(self.__output_dir, 'config').exists():
            shutil.copy(PurePath(parent_dir, 'config'), PurePath(self.__output_dir, 'config'))
            print('copied config')

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


def get_size(size, factor=1024, suffix="B"):
    """
    Scale bytes to its proper format
    e.g:
        1253656 => '1.20MB'
        1253656678 => '1.17GB'
    """
    for data_unit in ["", "K", "M", "G", "T", "P"]:
        if size < factor:
            return f"{size:.2f}{data_unit}{suffix}"
        size /= factor


if __name__ == '__main__':
    # version = '2.4.0'
    build = Build(folder=False, target_dir_name='FTT', version='')
    build.main()
