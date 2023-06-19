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


def get_disk_io():
    disk_io_before = psutil.disk_io_counters()
    time.sleep(1)
    disk_io_now = psutil.disk_io_counters()
    return {"read_count": f'{disk_io_now.read_count - disk_io_before.read_count}次/s',
            "write_count": f'{disk_io_now.write_count - disk_io_before.write_count}次/s',
            "read_bytes": f'{get_size(disk_io_now.read_bytes - disk_io_before.read_bytes)}/s',
            "write_bytes": f'{get_size(disk_io_now.write_bytes - disk_io_before.write_bytes)}/s'}


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
    used = get_size(memory.used)
    total = get_size(memory.total)
    memory_use_percent = str(memory.percent) + ' %'
    # 系统电池使用情况
    battery = psutil.sensors_battery()
    # 系统硬盘使用情况
    disks = []
    for disk_partition in psutil.disk_partitions():
        usage = psutil.disk_usage(disk_partition.mountpoint)
        disk_info = {'device': disk_partition.device.rstrip('\\'), 'fstype': disk_partition.fstype,
                     'total': get_size(usage.total), 'free': get_size(usage.free), 'percent': f'{usage.percent}%'}
        disks.append(disk_info)
    # 异步获取cpu、网络、硬盘的io
    t1 = MyThread(get_net_io, args=())
    t2 = MyThread(get_cpu_percent, args=())
    t3 = MyThread(get_disk_io, args=())
    t1.start()
    t2.start()
    t3.start()
    t1.join()
    t2.join()
    t3.join()
    net_io = t1.get_result()
    cpu_percent = t2.get_result()
    disk_io = t3.get_result()
    # 整合信息
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
        "network": net_io,
        "disks": {'info': disks, 'io': disk_io}
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
    disks = info['disks']
    disks_io = disks['io']
    print(f"用户: {user['username']}, 主机: {user['host']} 的系统信息如下: ")
    print(f"\t系统信息 : {system['platform']} {system['version']} {system['architecture']}")
    print(f"\t运行时间 : {info['boot time']}")
    print(f"\t处理器  : 利用率:{cpu['percentage']} \n\t\t\t {cpu['manufacturer']} {cpu['count']}核 "
          f"{cpu['logic_count']}线程 {cpu['frequency']} {cpu['info']}")
    print(f"\t内存    : {memory['used']}/{memory['total']} 利用率:{memory['percentage']}")
    print(f"\t网络    : {network['download']}⬇ {network['upload']}⬆")
    print(f"\t硬盘    : 读命中 {disks_io['read_count']} 写命中 {disks_io['write_count']} "
          f"读取速度 {disks_io['read_bytes']} 写入速度 {disks_io['write_bytes']}")
    for disk in disks['info']:
        print(f"\t\t\t {disk['device']} 可用 {disk['free']:9}，共{disk['total']:9} "
              f"已使用 {disk['percent']} 类型 {disk['fstype']}")
    print("\t电池    :",
          f"当前电量:{battery['percent']}% {battery['power_plugged']} 剩余使用时间:{battery['secsleft']}"
          if battery else "未检测到电池")
    print()


if __name__ == '__main__':
    print_sysinfo(get_sys_info())
