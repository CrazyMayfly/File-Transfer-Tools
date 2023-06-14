# File Transfer Tools
## Introduction

`File Transfer Tools` contains two components: `FTS (File Transfer Server)` and `FTC (File Transfer Client)`. Is a **lightweight**,  **fast**,  **secure**, **versatile** cross-device file transfer script.

### Function

1. File transfer
- Single file or entire folder can be transferred
- Security: encrypted transmission (using Secure Sockets Layer protocol) and plaintext transmission
- Correctness guarantee: Verify file consistency using the Hash value to check whether all files in the folder are correctly transferred
- Progress bar display: Displays the file transfer progress, current network rate, and remaining transfer duration in real time
- Transfer a file with the same name using a new name, avoid duplicate transfer, or overwrite transfer

2. Provide terminal function, which is similar to ssh, allows you to run commands remotely and return results in real time

3. Automatically search for a service host or manually specify a host to connect to

4. Folder comparison displays information about the same and different files in two folders

5. View the system status and information of the client and server

6. Output logs to the console and files in real time

7. Internet speed test

 

### characteristic

1. Fast in launch, run, response speed.

2. Can be used in any network environment such as LAN, the Internet, as long as two hosts can be connected (`ping` is effective).

3. Multi-threaded transmission with fast transmission speed, measured can run 1000 Mbps bandwidth, due to equipment limitations, no higher bandwidth be tested.

4. Small memory usage during running.

5. You can launch it immediately  when you want to use, and after close it there are no  residual processes.

 

### How to Choose

1. If you want a more powerful file transfer service, choose an FTP server (such as `FileZilla`, `WinSCP`, etc.)
2. If you want stable file synchronization and sharing, recommend using `Resilio Sync`, `Syncthing`, etc
3. If you only Transfer files **occasionally** and don't like the memory background residue and more resource usage of the above services, or don't need so powerful services, or want to **customize** the function then please select `File Transfer Tools`.

## Installation and Operation

`FTS` occupies ports 2023,2021, and `FTC` occupies ports 2022. Ports 2023 serve as TCP listening ports of `FTS`, and 2021 and 2022 serve as UDP transmission interfaces between the server and client. You can change them in the `Untils.py` mentioned at the end of the introduction.

### Download the executable program

1. Click the `Release` on the right
2. Download `File Transfer Tools.zip`
3. Unpacking the folder and double-click `FTC.exe` or `FTS.exe` to run it
4. Or run the program in the terminal to use the parameters, for example `.\FTC.exe [-h] [-t thread] [-host host] [-p]`

### Run with the Python interpreter

1. Clone the source code to your project location
2. Run the `pip install -r requirements.txt` command to install all dependencies.
3. Execute the script using your python interpreter such as `"The dir of your Python interpreter"\Scripts\python.exe "The dir of your project"\FTS.py`

#### Quick execution method

Taking Windows as an example, you can write the `FTS` and `FTC` run commands as batch files, and then add the batch file directories to your environment variables. In this way, you can simply type `FTS` and `FTC` in the terminal to run the program using the default, simplest command.

For example, you can write the following command to the file `FTS.bat`

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
FTC [-h] [-t thread] [-host host] [-p]
或
FTS [-h] [-d base_dir] [-p] [--avoid]
```

In the above batch file, %1~%9 indicates the parameters passed by the program (where %0 indicates the current path).



## Usage

### FTC

FTC is the file sending end, instruction sending end, used to send files and instructions.

```
usage: FTC.py [-h] [-t thread] [-host host] [-p]

File Transfer Client, used to SEND files.

optional arguments:
  -h, --help       show this help message and exit
  -t thread        threading number (default: 3)
  -host host       destination hostname or ip address
  -p, --plaintext  Use plaintext transfer (default: use ssl)
```

#### Parameters

`-t`: Specifies the number of threads. Default 3.

`-host`: Specify the receiver host explicitly (`hostname` or `ip address` can be used). If this option is not used, the client automatically searches for the server on the **same subnet**.

`-p`: This parameter is used with `-host`. Because the two ends automatically exchange information, you do not need to specify this parameter in normal circumstances. You just need to do it explicitly only when the two ends cannot connect to each other in normal and exchange their information.

#### Commands description

Once connected, enter instructions

1. Enter the `file (folder) path` to send the file (folder).
2. Enter `sysinfo` to display the system information of the two ends.
3. Enter `speedtest n` to test the network speed, where `n` is the data amount of the test (unit: MB). Note that in the **computer network**, 1 GB = 1000 MB = 1000000 KB.
4. Enter` compare local_dir dest_dir` to compare the local folder and server folder.
5. Input other content as the command execution, and real-time return results.

#### Screenshots of the runtime

The following are screenshots running on the same host.

<img src="assets/image-20230421175852690.png" alt="image-20230421175852690" style="zoom:67%;" />

<img src="assets/image-20230421174220808.png" alt="sysinfo效果（同一台主机展示）" style="zoom:60%;" />

<img src="assets/image-20230421175214141.png" alt="测试1GB数据量" style="zoom: 80%;" />

<img src="assets/image-20230421175524115.png" alt="image-20230421175524115" style="zoom:67%;" />

<img src="assets/image-20230421175725094.png" alt="image-20230421175725094" style="zoom:80%;" />

### FTS

`FTS` is a file receiving end and a server end, which is used to receive and store files and execute instructions sent by clients.

```
usage: FTS.py [-h] [-d base_dir] [-p] [--avoid]

File Transfer Server, used to RECEIVE files.

optional arguments:
  -h, --help            show this help message and exit
  -d base_dir, --dest base_dir
                        File storage location (default: C:\Users\admin\Desktop)
  -p, --plaintext       Use plaintext transfer (default: use ssl)
  --avoid               Do not continue the transfer when the file name is repeated.
```

#### Parameters

`-d, --dest`: Specify where files to be located. Default is the current user's **desktop**.

`-p`: Specifies plaintext transmission. SSL encryption is used by default. If you do not currently have a signed certificate, specify plaintext transmission. **To ensure security, use your own self-signed certificate.**

`--avoid`：When this option is open, If the file with the same name already exists in the directory, there are two cases: If the size of the file on the receiving end is greater than or equal to that on the sending end, transmission of the file will be **prevented**; otherwise, the file is received and **overwritten**. This function is mainly used for retransmission of a large number of files that are interrupted at a time. It is similar to breakpoint retransmission. In other situations, please **use this function with caution**. When this function is not enabled, if the file name is `a.txt`, the transferred files are named after `a (1).txt` and `a (2).txt` and so on.

#### Screenshots of the runtime

<img src="assets/image-20230421180254963.png" alt="image-20230421180254963" style="zoom:70%;" />

## Configuration

The configuration items are in `Utils.py`

`log_dir`：Log storage location</br>
`cert_dir`：Certificate deposit location</br>
`unit` ：Data sending unit</br>

`server_port`：TCP listening port of the server</br>
`server_signal_port`：UDP listening port of the server</br>
`client_signal_port`：UDP listening port of the client</br>

 