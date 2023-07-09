import os
import stat

from pywintypes import Time  # 可以忽视这个 Time 报错（运行程序还是没问题的）
from pywintypes import error
from win32file import CreateFile, SetFileTime, CloseHandle
from win32file import GENERIC_READ, GENERIC_WRITE, OPEN_EXISTING


def modifyFileTime(file_path, logger, create_timestamp, modify_timestamp, access_timestamp):
    """
    用来修改任意文件的相关时间属性，时间格式：YYYY-MM-DD HH:MM:SS 例如：2019-02-02 00:01:02
    :param file_path: 文件路径名
    :param logger: 日志答应对象
    :param create_timestamp: 创建时间戳
    :param modify_timestamp: 修改时间戳
    :param access_timestamp: 访问时间戳
    """
    readOnly = False
    # 不可写则改变文件读写权限
    if not os.access(file_path, os.W_OK):
        os.chmod(file_path, stat.S_IWRITE)
        logger.warning(f"将{file_path}读写权限改变为可写")
        readOnly = True
    try:
        # 获取时间元组
        createTime = Time(create_timestamp)
        accessTime = Time(access_timestamp)
        modifyTime = Time(modify_timestamp)
        # 调用文件处理器对时间进行修改
        fileHandler = CreateFile(file_path, GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, 0)
        SetFileTime(fileHandler, createTime, accessTime, modifyTime)
        CloseHandle(fileHandler)
    except error as e:
        if e.funcname == 'CreateFile':
            logger.error('文件权限不足，请检查文件是否只读')
        else:
            logger.error(f'{file_path}修改失败')
    except (OverflowError, Exception) as e:
        logger.error(f'{file_path}修改失败，{e}')
    finally:
        # 还原文件的读写权限
        if readOnly:
            os.chmod(file_path, stat.S_IREAD)
            logger.info(f"将{file_path}文件权限还原为只读")


def get_file_time_details(filePath: str) -> tuple[float, float, float]:
    """
    获取并返回一个文件(夹)的创建、修改、访问时间的时间戳
    """
    return os.path.getctime(filePath), os.path.getmtime(filePath), os.path.getatime(filePath)
