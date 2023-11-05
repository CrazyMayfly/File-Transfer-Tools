import platform
import time
import psutil
from threading import Thread

username = psutil.users()[0].name
cpu_count = psutil.cpu_count(logical=False)
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
    return f"{psutil.cpu_percent(interval=1)}%"


def get_disk_io():
    disk_io_before = psutil.disk_io_counters()
    time.sleep(1)
    disk_io_now = psutil.disk_io_counters()
    return {"read_count": f'{disk_io_now.read_count - disk_io_before.read_count} times/s',
            "write_count": f'{disk_io_now.write_count - disk_io_before.write_count} times/s',
            "read_bytes": f'{get_size(disk_io_now.read_bytes - disk_io_before.read_bytes)}/s',
            "write_bytes": f'{get_size(disk_io_now.write_bytes - disk_io_before.write_bytes)}/s'}


class MyThread(Thread):
    def __init__(self, func, args=()):
        super(MyThread, self).__init__()
        self.func = func
        self.args = args
        self.result = None

    def run(self):
        self.result = self.func(*self.args)

    def get_result(self):
        self.join()
        return self.result


def get_sys_info():
    def format_time(time_second):
        minutes, seconds = divmod(time_second, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        return f"{days}d {hours}h {minutes}m {seconds}s"

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
    threads = [MyThread(method) for method in (get_net_io, get_cpu_percent, get_disk_io)]
    for thread in threads:
        thread.start()
    net_io, cpu_percent, disk_io = [thread.get_result() for thread in threads]
    # 整合信息
    info = {
        "user": {"username": username, 'host': host},
        "system": {"platform": platform.system(), "version": platform.version(),
                   "architecture": platform.architecture()[0]
                   },
        "boot time": format_time(int(time.time() - psutil.boot_time())),
        "cpu": {"count": cpu_count, "logic_count": psutil.cpu_count(logical=True),
                "percentage": cpu_percent, 'info': platform.processor(),
                "manufacturer": platform.machine(),
                "frequency": f'{psutil.cpu_freq().current / 1000:.2f}Ghz'},
        "memory": {"used": used, "total": total, "percentage": memory_use_percent},
        "network": net_io,
        "disks": {'info': disks, 'io': disk_io}
    }
    battery_info = None
    if battery:
        if battery.secsleft == -1:
            secs_left = 'UNKNOWN'
        elif battery.secsleft == -2:
            secs_left = 'UNLIMITED'
        else:
            secs_left = format_time(battery.secsleft)
        battery_info = {"percent": battery.percent, "secsleft": secs_left,
                        "power_plugged": "on" if battery.power_plugged else "off"}
    info.update({"battery": battery_info})
    return info


def print_sysinfo(info):
    user, system, cpu, memory, network, battery, disks, disks_io = info['user'], info['system'], info['cpu'], info[
        'memory'], info['network'], info['battery'], info['disks'], info['disks']['io']
    diskinfo, blank = [], '       '
    for disk in disks['info']:
        diskinfo.append(
            f"{blank}{disk['device']} available {disk['free']:9}, total {disk['total']:9}, used {disk['percent']}, type {disk['fstype']}")
    diskinfo = ('\n' + blank).join(diskinfo)
    battery_info = f"percent: {battery['percent']}%, power plugged: {battery['power_plugged']}, time left: {battery['secsleft']}" if battery else "Battery not detected"
    msg = f"""User: {user['username']}, host: {user['host']}:
      System   : {system['platform']} {system['version']} {system['architecture']}
      Boot time: {info['boot time']}
      Processor: {cpu['percentage']}, {cpu['manufacturer']}, {cpu['count']} cores, {cpu['logic_count']} threads, {cpu['frequency']}, {cpu['info']}
      Memory   : {memory['used']}/{memory['total']} usage: {memory['percentage']}
      Network  : {network['download']}↓ {network['upload']}↑
      Disk     : read hit: {disks_io['read_count']}, write hit: {disks_io['write_count']}, read speed: {disks_io['read_bytes']}, write speed: {disks_io['write_bytes']}
       {diskinfo}
      Battery  : {battery_info}
"""
    print(msg)
    return msg


if __name__ == '__main__':
    print_sysinfo(get_sys_info())
