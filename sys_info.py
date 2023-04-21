import platform
import time
from threading import Thread

import psutil


def stringify_time(time_second):
    minutes, seconds = divmod(time_second, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    return f"{days}天{hours}小时{minutes}分钟{seconds}秒"


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

def get_net_io():
    net_io_before = psutil.net_io_counters()
    time.sleep(1)
    net_io_now = psutil.net_io_counters()
    return {"upload": get_size(net_io_now.bytes_sent - net_io_before.bytes_sent) + '/s',
            "download": get_size(net_io_now.bytes_recv - net_io_before.bytes_recv) + '/s'}


def get_cpu_percent():
    return f"{psutil.cpu_percent(interval=1)} %"


class MyThread(Thread):
    def __init__(self, func, args):
        super(MyThread, self).__init__()
        self.func = func
        self.args = args
        self.result = None

    def run(self):
        self.result = self.func(*self.args)

    def get_result(self):
        return self.result


def get_sys_info():
    username = psutil.users()[0].name
    host = platform.node()
    # 系统的内存利用率
    memory = psutil.virtual_memory()
    used = str(round(memory.used / (1024.0 * 1024.0 * 1024.0), 2)) + 'GB'
    total = str(round(memory.total / (1024.0 * 1024.0 * 1024.0), 2)) + 'GB'
    memory_use_percent = str(memory.percent) + ' %'
    battery = psutil.sensors_battery()
    t1 = MyThread(get_net_io, args=())
    t2 = MyThread(get_cpu_percent, args=())
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    net_io = t1.get_result()
    cpu_percent = t2.get_result()

    info = {
        "user": {"username": username, 'host': host},
        "system": {"platform": platform.system(), "version": platform.version(),
                   "architecture": platform.architecture()[0]
                   },
        "boot time": stringify_time(int(time.time() - psutil.boot_time())),
        "cpu": {"count": psutil.cpu_count(logical=False), "logic_count": psutil.cpu_count(logical=True),
                "percentage": cpu_percent, 'info': platform.processor(),
                "manufacturer": platform.machine(),
                "frequency": str(round(psutil.cpu_freq().current / 1000, 2)) + "Ghz"},
        "memory": {"used": used, "total": total, "percentage": memory_use_percent},
        "network": net_io
    }
    if battery:
        if battery.secsleft == -1:
            secsleft = 'POWER_TIME_UNKNOWN'
        elif battery.secsleft == -2:
            secsleft = 'POWER_TIME_UNLIMITED'
        else:
            secsleft = stringify_time(battery.secsleft)
        info.update({"battery": {"percent": battery.percent,
                                 "power_plugged": "已接通电源" if battery.power_plugged else "未接通电源",
                                 "secsleft": secsleft}})
    else:
        info.update({"battery": None})
    return info


def print_sysinfo(info):
    user = info['user']
    system = info['system']
    cpu = info['cpu']
    memory = info['memory']
    network = info['network']
    battery = info['battery']
    print(f"用户: {user['username']}, 主机: {user['host']} 的系统信息如下: ")
    print(f"\t系统信息 : {system['platform']} {system['version']} {system['architecture']}")
    print(f"\t运行时间 : {info['boot time']}")
    print(
        f"\t处理器  : 利用率:{cpu['percentage']} {cpu['manufacturer']} {cpu['count']}核 {cpu['logic_count']}线程 {cpu['frequency']} {cpu['info']}")
    print(f"\t内存    : {memory['used']}/{memory['total']} 利用率:{memory['percentage']}")
    print(f"\t网络    : {network['download']}⬇ {network['upload']}⬆")
    if battery:
        print(
            f"\t电池    : 当前电量:{battery['percent']}% {battery['power_plugged']} 剩余使用时间:{battery['secsleft']}")
    else:
        print("\t电池    : 未检测到电池")
    print()


if __name__ == '__main__':
    print_sysinfo(get_sys_info())
