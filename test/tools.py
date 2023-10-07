import os
import random

min_size = 1024 * 5
max_size = 1024 * 500


def create_random_file(file_path, file_size=0):
    # 生成随机文件大小
    if file_size == 0:
        file_size = random.randint(min_size, max_size)

    # 生成随机数据并写入文件
    with open(file_path, 'wb') as file:
        random_data = os.urandom(file_size)
        file.write(random_data)