# 文件傳輸小工具

> 警告：本文由機器翻譯生成，可能導致質量不佳或信息有誤，請謹慎閱讀！

## 簡介

`File Transfer Tools` 包含`FTS (File Transfer Server) `，`FTC (File Transfer Client) `兩個組件，是**輕量**、**快速**、**安全**、**多功能**的跨設備文件傳輸腳本。

### 功能

1. 文件傳輸

  - 可傳輸單文件或者整個文件夾
  - 安全性保障：加密傳輸（使用安全套接字層協議）、明文傳輸
  - 正確性保障：通過Hash值校驗文件的一致性，判斷文件夾內所有文件是否都正確傳輸
  - 進度條顯示：實時顯示文件傳輸進度、當前網絡速率、剩餘傳輸時長
  - 同名文件新命名傳輸、避免重複傳輸、覆蓋傳輸三種方式

2. 命令行，可以便捷地在遠端執行命令並實時返回結果，類似ssh
3. 自動尋找服務主機，也可手動指定連接主機
4. 文件夾比較，可顯示兩個文件夾中的文件的相同、差異等信息
5. 查看客戶端與服務端系統狀態、信息
6. 實時輸出日誌到控制台和文件中
7. 網速測試

### 特點

1. 啟動、運行、響應速度快
2. 可在局域網、公網等任意網絡環境下使用，只要兩台主機可以連通即可（可以ping通就行）
3. 多線程傳輸，傳輸速度快，實測可以跑滿1000Mbps帶寬，由於設備限制，沒有測試更高帶寬
4. 運行時內存佔用小
5. 即用即開，關閉不會殘留進程

### 如何選擇

1. 如果你想要功能更強大的文件傳輸服務，請選擇FTP服務器、客戶端（如`FileZilla`、`WinSCP`等）
2. 如果你想要穩定的文件同步和共享，推薦使用`Resilio Sync`、`Syncthing`等
3. 如果你只是偶爾傳輸文件/不喜歡上述服務的後台存留、資源佔用/不需要那麼強大的服務/想要自己定制功能那請選擇`File Transfer Tools`

## 安裝與運行

`FTS`佔用2023，2021端口，FTC佔用2022端口。其中2023端口作為`FTS`的TCP偵聽端口，2021、2022作為服務器和客戶端之間UDP傳輸接口。你可以在本文末尾查看詳細信息。

### 下載可執行程序

1. 點擊右側`Release`
2. 下載`File Transfer Tools.zip`
3. 解壓文件夾，雙擊`FTC.exe` 或者 `FTS.exe` 運行即可
4. 或者在終端中運行程序以使用程序參數，例如`.\FTC.exe [-h] [-t thread] [-host host] [-p]`

### 使用Python解釋器運行

1. 將源代碼克隆到你的項目位置
2. 使用`pip install -r requirements.txt`安裝所有依賴項
3. 使用你的python解釋器執行腳本

#### 快捷執行方法

以Windows為例，你可以將FTS、FTC的運行命令分別編寫為批處理文件，然後將批處理文件的目錄添加到你的環境變量中，這樣你就可以通過簡單的在命令行中鍵入`FTS`、`FTC`來使用默認的、最簡單的命令來運行程序了。

例如，你可以將下面命令寫入文件`FTS.bat`中

```powershell
@echo off
"The dir of your Python interpreter"\Scripts\python.exe "The dir of your project"\FTS.py %1 %2 %3 %4 %5 %6
```

將下面命令寫入文件`FTC.bat`中

```powershell
@echo off
"The dir of your Python interpreter"\Scripts\python.exe "The dir of your project"\FTC.py %1 %2 %3 %4 %5 %6
```

然後，將批處理文件夾添加到你的環境變量中，最後在你的終端中鍵入以下命令就可以快捷運行代碼了

```powershell
FTC [-h] [-t thread] [-host host] [-p]
或
FTS [-h] [-d base_dir] [-p] [--avoid]
```

以上批處理文件中，`%1~%9`表示程序傳入的參數（`%0`表示當前路徑）



## 用法

### FTC

FTC是文件發送端，指令發送端，用於發送文件和指令。

```
usage: FTC.py [-h] [-t thread] [-host host] [-p]

File Transfer Client, used to SEND files.

optional arguments:
  -h, --help       show this help message and exit
  -t thread        threading number (default: 3)
  -host host       destination hostname or ip address
  -p, --plaintext  Use plaintext transfer (default: use ssl)
```

#### 參數說明

`-t`: 指定線程數，默認為3個線程。

`-host`: 顯式指定接收端主機（可使用hostname或者ip地址），不使用此選項時，客戶端自動尋找**同一子網**下的服務器

`-p`: 配合`-host` 使用，由於雙方會自動交換信息，所以一般不需要指定，只有在雙方無法正常連接時才需要顯式指定。

#### 命令說明

正常連接後，輸入指令

1. 輸入文件（夾）路徑，則執行發送文件
2. 輸入`sysinfo`，則會顯示雙方的系統信息
3. 輸入`speedtest n`，則會測試網速，其中n為本次測試的數據量，單位MB。注意，在**計網**中，1 GB = 1000 MB = 1000000 KB.
4. 輸入`compare local_dir dest_dir`來比較本機文件夾和服務器文件夾差別。
5. 輸入其他內容時作為指令執行，並且實時返回結果。

#### 運行截圖

以下均為運行在同一台主機上的截圖。

<img src="assets/image-20230421175852690.png" alt="image-20230421175852690" style="zoom:67%;" />

<img src="assets/image-20230421174220808.png" alt="sysinfo效果（同一台主机展示）" style="zoom:60%;" />

<img src="assets/image-20230421175214141.png" alt="测试1GB数据量" style="zoom: 80%;" />

<img src="assets/image-20230421175524115.png" alt="image-20230421175524115" style="zoom:67%;" />

<img src="assets/image-20230421175725094.png" alt="image-20230421175725094" style="zoom:80%;" />

### FTS

`FTS`是文件接收端，服務器端，用於接收並存儲文件，執行客戶端發來的指令。

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

#### 參數說明

`-d, --dest`: 指定文件存儲位置，若不指定則存放到當前用戶的**桌面**。

`-p`: 指定明文傳輸，默認使用ssl加密傳輸。若你當前沒有簽名證書，請指定明文傳輸。**為了確保安全性，請使用自己的自簽名證書。**

`--avoid`：開啟時，如果目錄下已經有同名文件，分兩種情況，若接收端的文件大小大於等於發送端則**阻止**該文件的傳輸，否則接收並**覆寫**該文件；此功能主要用於一次傳輸大量文件被中斷後的重傳，類似斷點重傳，其他情況請**謹慎使用**。未開啟時，如果存在的文件名為`a.txt`，則傳輸過來的文件會按照 `a (1).txt`、`a (2).txt`依次命名。

#### 運行截圖

<img src="assets/image-20230421180254963.png" alt="image-20230421180254963" style="zoom:70%;" />

## 配置

配置項在`Utils.py`中

`log_dir`：日誌存放位置</br>
`cert_dir`：證書存放位置</br>
`unit` ：數據發送單位</br>

`server_port`：服務器 TCP 偵聽端口</br>
`server_signal_port`：服務器 UDP 偵聽端口</br>
`client_signal_port`：客戶端 UDP 偵聽端口</br>

