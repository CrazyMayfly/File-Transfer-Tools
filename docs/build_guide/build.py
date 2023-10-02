import os
import shutil
import subprocess

source_dir = './docs/build_guide'
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Build:
    def __init__(self, folder=False, target_dir_name='FTT'):
        self.__bundle_type = '--onedir' if folder else '--onefile'
        self.__target_dir_name = target_dir_name
        self.__output_dir = os.path.join(parent_dir, target_dir_name)
        self.__log_level = 'INFO'

    def package(self):
        processes = []
        for program in ['FTC', 'FTS']:
            cmd = f'pyinstaller.exe {self.__bundle_type} --icon=".{source_dir}/{program}.png" --specpath "./build" --upx-dir "{source_dir}/upx.exe" --log-level {self.__log_level} --distpath "./{self.__target_dir_name}" --console ./{program}.py'
            processes.append(subprocess.Popen(args=cmd, cwd=parent_dir, shell=True))
            print(cmd)
            self.__log_level = 'ERROR'
        for process in processes:
            process.wait()

    def copy_files(self):
        if not os.path.exists(os.path.join(self.__output_dir, 'cert')):
            shutil.copytree(os.path.join(parent_dir, 'cert'), os.path.join(self.__output_dir, 'cert'))
            print('copied cert')
        if not os.path.exists(os.path.join(self.__output_dir, 'config.txt')):
            shutil.copy(os.path.join(parent_dir, 'config.txt'), os.path.join(self.__output_dir, 'config.txt'))
            print('copied config.txt')

    def archive(self):
        print('archiving')
        shutil.make_archive(self.__output_dir, 'zip', self.__output_dir)

    def clean(self):
        print('cleaning')
        shutil.rmtree(self.__output_dir)
        # shutil.rmtree(os.path.join(parent_dir, 'build'))

    def mian(self):
        self.package()
        self.copy_files()
        self.archive()
        self.clean()


if __name__ == '__main__':
    build = Build(folder=False, target_dir_name='FTT')
    build.mian()
