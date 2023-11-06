# 文件传输小工具

## 简介

`File Transfer Tool` ，是**轻量**、**快速**、**安全**、**多功能**的跨设备文件传输小工具。

### 功能

1. 文件传输

- 可传输单个文件或者整个文件夹，支持断点续传
- 安全性保障：为每次会话生成专属的TLS/SSL安全证书，最大限度保障安全
- 进度条显示：实时显示文件传输进度、当前网络速率、剩余传输时长等信息
- 对小文件 (<1MB) 的传输进行了特别优化

2. 提供简易的类似ssh的功能，可在远端执行命令并实时返回结果
3. 自动寻找服务主机，也可手动指定连接主机
4. 文件夹比较，可显示两个文件夹中的文件的相同、差异等信息
5. 查看双方系统状态、信息
6. 实时输出日志到控制台和文件中，并且可以自动整理压缩日志文件
7. 测试双方之间的网络带宽
8. 可以在两端传输信息，实现简单的聊天功能
9. 同步两端的剪切板内容
10. 可以为服务器设置连接密码，增强安全性

### 特点

1. 启动、运行、响应速度快
2. 采用最小默认配置原则，即开即用，也可以方便地自己修改配置
2. 可在局域网、公网等任意网络环境下使用，只要两台主机可以进行网络连接即可
3. 可以指定线程数，采用多线程传输
4. 对于接收保留文件、文件夹的修改时间、访问时间等信息
5. 即用即开，即关即走，关闭程序后不会残留进程
6. 目前适配Windows和Linux平台

### 如何选择

1. 如果你想要功能更强大的文件传输服务，请选择FTP服务器、客户端（如`FileZilla`、`WinSCP`等）
2. 如果你想要稳定的文件同步和共享，推荐使用`Resilio Sync`、`Syncthing`等
3. 如果你只是偶尔传输文件/不喜欢上述服务的后台存留、资源占用/不需要那么强大的服务/想要自己定制功能那请选择`File Transfer Tools`

## 安装与运行

### 方法一：下载可执行程序

1. 点击右侧`Release`
2. 下载压缩包
3. 解压文件夹，双击`FTT.exe`即可以默认配置运行
4. 或者在终端中运行程序以使用程序参数，例如`.\FTT.exe [-h] [-t thread] [-host host] [-d destination] [-p password] `

### 方法二：使用Python解释器运行

1. 将源代码克隆到你的项目位置
2. 使用`pip install -r requirements.txt`安装所有依赖项
3. 使用你的python解释器执行脚本

## 用法

FTT 可同时为两方提供服务，双方都可以互相传输文件，执行指令。

### 建立连接时需要注意的事项
1. 若未设置密码，FTT 打开后默认自动寻找主机并连接，建议仅在简单局域网环境下使用该方式。
2. 若在复杂网络环境下或者需要连接到公网，一方需设置密码，另一方指定主机名或ip地址和密码进行连接。

#### 参数说明

```
usage: FTT.py [-h] [-t thread] [-host host] [-p password] [-d base_dir]

File Transfer Tool, used to transfer files and execute commands.

options:
  -h, --help            show this help message and exit
  -t thread             Threads (default: cpu count)
  -host host            Destination hostname or ip address
  -p password, --password password
                        Set a password for the host or Use a password to connect host.
  -d base_dir, --dest base_dir
                        File save location (default: ~\Desktop)
```

`-t`: 指定线程数，默认为处理器数量。

`-p`: 显式设置主机密码或指定连接密码（默认情况下没有密码），不使用此选项时，自动寻找**同一子网**下的服务器。

`-host`: 指定对方的主机名(可使用hostname或ip)及端口号(可选)，需搭配`-p`使用。

`-d`: 显式指定文件接收位置，Windows平台默认为**桌面**。



#### 命令说明

连接成功后，输入指令

1. 输入文件（夹）路径，则会发送文件（夹）
2. 输入`sysinfo`，则会显示双方的系统信息
3. 输入`speedtest n`，则会测试网速，其中n为本次测试的数据量，单位MB。注意，在**计算机网络**中，1 GB = 1000 MB = 1000000 KB.
4. 输入`compare local_dir dest_dir`来比较本机文件夹和服务器文件夹中文件的差别。
5. 输入`say`给对方发送信息，可以作为简单聊天服务器使用
6. 输入`setbase`来改变文件接收位置
7. 输入`get clipboard` 或 `send clipboard`来同步客户端和服务器的剪切板内容
8. 输入其他内容时作为指令让服务器执行，并且实时返回结果。

#### 运行截图

以下均为运行在同一台主机上的截图。

程序启动

![startup](assets/startup.png)

传输文件

![file](assets/file.png)

执行命令：sysinfo

![sysinfo](assets/sysinfo.png)

执行命令：speedtest

![speedtest](assets/speedtest.png)

执行命令：compare

![compare](assets/compare.png)

执行命令：clip

![clip](assets/clip.png)

执行命令：say

![say](assets/say.png)

执行命令：setbase

![setbase](assets/setbase.png)

执行命令行命令

![command](assets/cmd.png)


## 配置

配置项在配置文件`config`中，当配置文件不存在时，程序会使用默认配置

### Main 程序的主要配置

`windows_default_path`: Windows平台下默认的文件接收位置

`linux_default_path`: Linux平台下默认的文件接收位置

### Log 日志相关配置

`windows_log_dir`: Windows平台下默认的日志文件存放位置

`linux_log_dir`: Linux平台下默认的日志文件存放位置

`log_file_archive_count`: 当日志文件数超过该大小时归档

`log_file_archive_size`: 当日志文件的总大小(字节)超过该大小时归档

### Port 配置端口相关内容

`server_port`：服务器 TCP 侦听端口

`signal_port`：UDP 侦听端口

