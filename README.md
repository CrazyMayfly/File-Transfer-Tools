# File Transfer Widget

## Introduction

`File Transfer Tools` contains two components: `FTS (File Transfer Server)` and `FTC (File Transfer Client)`. Is a **lightweight**,  **fast**,  **secure**, **versatile** cross-device file transfer script.

### Function

1. File Transfer

- Single file or entire folder can be transferred.
- Security Guarantee: Encrypted transmission (using Secure Sockets Layer Protocol) and plaintext transmission.
- Correctness guarantee: verify the consistency of the files through the Hash value, and judge whether all the files in the folder are transmitted correctly.
- Progress bar display: real-time display of file transfer progress, current network speed, and remaining transfer time.
- Transfer a file with the same name using a new name, avoid duplicate transfer, or overwrite transfer.

2. Provide terminal function, which is similar to ssh, allows you to run commands remotely and return results in real time.
3. Automatically find the service host, or manually specify the connection host.
4. Folder comparison, which can display information such as the same and differences of files in two folders.
5. View the system status and information of the client and server.
6. Output logs to the console and files in real time, and can automatically organize compressed log files.
7. Conveniently test the network bandwidth between the client and the server.
8. You can set a connection password for the server to enhance security.
9. Conveniently synchronize the clipboard content of the client and server.

### Features

1. Fast in launch, run, response.
2. Adopt the minimum default configuration principle, which can be used out of the box, and you can easily modify the configuration by yourself.
2. It can be used in any network environment such as LAN and public network, as long as the two hosts can connect to each other.
3. Multi-threaded transmission with fast transmission speed, measured can run 1000 Mbps bandwidth, due to equipment limitations, no higher bandwidth be tested.
4. The memory usage is small at runtime, and the lazy loading mode is adopted to ensure the minimum occupation of resources.
5. You can launch it immediately when you want to use, and after close it there are no residual processes.
6. Currently compatible with Windows and Linux platforms.

### How to Choose

1. If you want a more powerful file transfer service, choose an FTP server (such as `FileZilla`, `WinSCP`, etc.)
2. If you want stable file synchronization and sharing, recommend using `Resilio Sync`, `Syncthing`, etc.
3. If you only Transfer files **occasionally** and don't like the memory background residue and more resource usage of the above services, or don't need so powerful services, or want to **customize** the function then please select `File Transfer Tools`.

## Install and run

`FTS` occupies ports 2023 and 2021 by default, and FTC occupies port 2022 by default. Among them, port 2023 is used as the TCP listening port of `FTS`, and 2021 and 2022 are used as UDP transmission interfaces between the server and the client.
You can check the detailed configuration information and modify the above configuration at the end of this article.

### Download the executable program

1. Click the `Release` on the right.
2. Download `File Transfer Tools.zip`.
3. Unpacking the folder and double-click `FTC.exe` or `FTS.exe` to run it.
4. Or run the program in the terminal to use the parameters, for example `.\FTC.exe [-h] [-t thread] [-host host] [-p]`.

### Run with the Python interpreter

1. Clone the source code to your project location.
2. Run the `pip install -r requirements.txt` command to install all dependencies.
3. Execute the script using your python interpreter such as `"The dir of your Python interpreter"\Scripts\python.exe "The dir of your project"\FTS.py`.

#### Quick execution method

Taking Windows as an example, you can write the `FTS` and `FTC` run commands as batch files, and then add the batch file directories to your environment variables. In this way, you can simply type `FTS` and `FTC` in the terminal to run the program using the default, simplest command.

For example, you can write the following command to the file `FTS.bat`.

```powershell
@echo off
"The dir of your Python interpreter"\Scripts\python.exe "The dir of your project"\FTS.py %1 %2 %3 %4 %5 %6
```

Write the following command to the file `FTC.bat`

```powershell
@echo off
"The dir of your Python interpreter"\Scripts\python.exe "The dir of your project"\FTC.py %1 %2 %3 %4 %5 %6
```

Then, add the folder where the batch files are located to your environment variables, and finally type the following command in your terminal to run the script quickly.

```powershell
FTC.py [-h] [-t thread] [-host host] [-p password] [--plaintext]
or
FTS.py [-h] [-d base_dir] [-p password] [--plaintext] [--avoid]
```

In the above batch file, %1~%9 indicates the parameters passed by the program (where %0 indicates the current path).
Note that the default working path of the terminal is the user directory (~), if you need to modify the configuration file, please modify it in this directory.

## Usage

### FTC

FTC is the client for sending files and instructions.

```
usage: FTC.py [-h] [-t thread] [-host host] [-p password] [--plaintext]

File Transfer Client, used to SEND files and instructions.

optional arguments:
   -h, --help show this help message and exit
   -t thread threads (default: 8)
   -host host destination hostname or ip address
   -p password, --password password
                         Use a password to connect host.
   --plaintext Use plaintext transfer (default: use ssl)
```

#### Parameters Description

`-t`: Specify the number of threads, the default is the number of logical processors.

`-host`: Explicitly specify the server hostname (hostname or ip) and port number (optional). When this option is not used, the client will automatically search for a server under **same subnet**.

`-p`: Explicitly specify the connection password for the server (the server has no password by default).

`--plaintext`: Explicitly specify plaintext transmission data, requiring the server to also use plaintext transmission.

#### Command Description

After a normal connection, enter the command.

1. Enter the file (folder) path, and the file (folder) will be sent.
2. Enter `sysinfo` to display the system information of the two ends.
3. Enter `speedtest n` to test the network speed, where `n` is the data amount of the test (unit: MB). Note that in the **computer network**, 1 GB = 1000 MB = 1000000 KB.
4. Enter `compare local_dir dest_dir` to compare the difference between the files in the local folder and the server folder.
5. Enter `clip pull/push` or `clip get/send` to synchronize the client and server clipboard content.
6. When other content is entered, it is used as an instruction for the server to execute, and the result is returned in real time.

#### Screenshots of the runtime

The following are screenshots running on the same host.

program start

![startup](assets/startup.png)

transfer files
![file](assets/file.png)

Execute the command: sysinfo

![sysinfo](assets/sysinfo.png)

Execute the command: speedtest

![speedtest](assets/speedtest.png)

Execute the command: compare

![compare](assets/compare.png)

Execute the command: clip

![clip](assets/clip.png)

Execute command line commands

![command](assets/cmd.png)

### FTS

`FTS` is the server, used to receive and store files, and execute the instructions sent by the client.

```
usage: FTS.py [-h] [-d base_dir] [-p password] [--plaintext] [--avoid]

File Transfer Server, used to RECEIVE files and EXECUTE instructions.

optional arguments:
   -h, --help show this help message and exit
   -d base_dir, --dest base_dir
                         File storage location (default: C:\Users\admin/Desktop)
   -p password, --password password
                         Set a password for the host.
   --plaintext Use plaintext transfer (default: use ssl)
   --avoid Do not continue the transfer when the file name is repeated.
```

#### Parameters Description

`-d, --dest`: Explicitly specify the file receiving location, the default is the value of the configuration item "platform_default_path" (Windows platform defaults to user's **Desktop**).

`-p, --password`: Set a password for the server to prevent malicious connections.

`--plaintext`: Explicitly specify data transmission in plain text, and use ssl encrypted transmission by default.

`--avoid`: When this option is open, If the file with the same name already exists in the directory, there are two cases: If the size of the file on the receiving end is greater than or equal to that on the sending end, transmission of the file will be **prevented**; otherwise, the file is received and **overwritten**. This function is mainly used for retransmission of a large number of files that are interrupted at a time. It is similar to breakpoint retransmission. In other situations, please **use this function with caution**. When this function is not enabled, if the file name is `a.txt`, the transferred files are named after `a (1).txt` and `a (2).txt` and so on.

#### Screenshots of the runtime

![FTS](assets/FTS.png)

## Configuration

The configuration items are in the configuration file `config.txt`, when the configuration file does not exist, the program will automatically create the default configuration file.

### Main configuration
`windows_default_path`: The default file receiving location under the Windows platform
`linux_default_path`: The default file receiving location under the Linux platform
`cert_dir`: The storage location of the certificate file

### Log related configuration
`windows_log_dir`: The default log file storage location under the Windows platform
`linux_log_dir`: The default log file storage location under the Linux platform
`log_file_archive_count`: Archive when the number of log files exceeds this size
`log_file_archive_size`: Archive when the total size (bytes) of the log file exceeds this size

### Port related configuration
`server_port`: server TCP listening port
`server_signal_port`: server UDP listening port
`client_signal_port`: client UDP listening port