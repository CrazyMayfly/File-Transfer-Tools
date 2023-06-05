# 파일 전송 도구

> 경고: 이 기사는 기계 번역으로 생성되어 품질이 좋지 않거나 잘못된 정보로 이어질 수 있으므로 주의 깊게 읽으십시오!

## 간단한 소개

`File Transfer Tools` 포함하다`FTS (File Transfer Server) `,,`FTC (File Transfer Client) `두 가지 구성 요소, 예**가벼운 중량**게다가**빠른**게다가**안전**게다가**다기능**크로스 -디바이스 파일 전송 스크립트.

### 기능

1. 파일 전송

  - 단일 파일 또는 전체 폴더를 전송할 수 있습니다
  - 안전 보증 : 암호화 된 전송 (양보 -연결 레이어 프로토콜 사용), 명시 적 전송
  - 특정 보증 : 해시 값 확인 파일의 일관성을 통해 폴더의 모든 파일이 올바르게 전송되는지 확인하십시오.
  - Progress Bar Display : 실시간 디스플레이 파일 전송 진행, 현재 네트워크 속도, 나머지 전송 기간
  - 새로 이름이 지정된 전송, 반복 전송을 피하고 같은 이름의 전송을 덮으십시오.

2. 명령 줄은 원격 끝에서 명령을 실행하고 SSH와 유사한 실시간으로 결과를 반환하는 데 편리 할 수 ​​있습니다.
3. 서비스 호스트를 자동으로 찾으면 연결 호스트를 수동으로 지정할 수도 있습니다.
4. 폴더를 비교하면 두 폴더에 파일의 정보를 동일하게 표시 할 수 있습니다.
5. 클라이언트 및 서버 시스템 및 정보의 상태 및 정보를 확인하십시오.
6. 콘솔 및 파일에 실시간 출력 로그
7. 인터넷 속도 테스트

### 특성

1. 시작, 실행 및 응답의 빠른 속도
2. LAN 및 공개 네트워크와 같은 모든 네트워크 환경에서 사용할 수 있습니다.
3. 멀티 스레드 변속기, 빠른 변속기 속도는 실제 측정에서 1000Mbps 이상 대역폭을 실행할 수 있습니다. 장비 제한으로 인해 더 높은 대역폭이 테스트되지 않습니다.
4. 런타임 중에 메모리 직업이 작습니다
5. 즉, 열려 있고 프로세스를 끄면 프로세스가 떠나지 않습니다.

### 선택하는 방법

1. 보다 강력한 파일 전송 서비스를 원한다면 FTP 서버, 클라이언트 (예 :`FileZilla`게다가`WinSCP`기다리다)
2. 안정적인 파일 동기화 및 공유를 원한다면 사용하는 것이 좋습니다.`Resilio Sync`게다가`Syncthing`기다리다
3. 파일을 가끔 전송하는 경우/위의 서비스, 자원 직업/더 강력한 서비스의 배경 유지가 마음에 들지 않으면 자신의 기능을 사용자 정의하려면 선택하십시오.`File Transfer Tools`

## 설치 및 작동

`FTS`포트 2023,2021, FTC는 포트 2022 년을 점유합니다. 그 중에서도 포트 2023은 다음과 같이 사용됩니다.`FTS`서버와 클라이언트 간의 UDP 전송 인터페이스로서 2021 년과 2022 년 TCP 청취 포트.이 기사의 끝에서 세부 사항을 볼 수 있습니다.

### 실행 프로그램을 다운로드하십시오

1. 오른쪽을 클릭하십시오`Release`
2. 다운로드`File Transfer Tools.zip`
3. 폴더를 압축 해제하고 두 번 클릭하십시오`FTC.exe` 또는 `FTS.exe` 그냥 실행
4. 또는 프로그램 매개 변수를 사용하려면 터미널에서 프로그램을 실행하십시오.`.\FTC.exe [-h] [-t thread] [-host host] [-p]`

### Python 통역사를 사용하여 실행하십시오

1. 소스 코드를 프로젝트 위치로 복제하십시오
2. 사용`pip install tqdm==4.65.0`TQDM을 설치하십시오
3. Python 통역사를 사용하여 스크립트를 실행하십시오

#### 연습 방법

Windows를 예로 들어 FTS 및 FTC의 실행중인 명령을 배치 파일로 작성한 다음 배치 파일의 디렉토리를 환경 변수에 추가하여 명령 줄에 명령 줄을 입력 할 수 있습니다.`FTS`게다가`FTC`기본 및 단순한 명령을 사용하여 프로그램을 실행합시다.

예를 들어 파일에 다음 명령을 쓸 수 있습니다.`FTS.bat`가운데

```powershell
@echo off
"The dir of your Python interpreter"\Scripts\python.exe "The dir of your project"\FTS.py %1 %2 %3 %4 %5 %6
```

파일에 다음 명령을 씁니다`FTC.bat`가운데

```powershell
@echo off
"The dir of your Python interpreter"\Scripts\python.exe "The dir of your project"\FTC.py %1 %2 %3 %4 %5 %6
```

그런 다음 배치 폴더를 환경 변수에 추가하고 마지막으로 터미널에 다음 명령을 입력하여 코드를 빠르게 실행하십시오.

```powershell
FTC [-h] [-t thread] [-host host] [-p]
或
FTS [-h] [-d base_dir] [-p] [--avoid]
```

위의 처리 문서 배치에서`%1~%9`프로그램의 매개 변수를 표현합니다 (`%0`현재 경로를 나타냅니다)



## 용법

### ftc

FTC는 파일 및 지침을 보내기위한 파일 보내기 종료, 명령어 보내기 종료입니다.

```
usage: FTC.py [-h] [-t thread] [-host host] [-p]

File Transfer Client, used to SEND files.

optional arguments:
  -h, --help       show this help message and exit
  -t thread        threading number (default: 3)
  -host host       destination hostname or ip address
  -p, --plaintext  Use plaintext transfer (default: use ssl)
```

#### 매개 변수 설명

`-t`: 스레드 수를 지정하고 기본값은 3 개의 스레드입니다.

`-host`: 수신 사이드 호스트를 지정하는 차별 (호스트 이름 또는 IP 주소 사용).이 옵션을 사용하지 않으면 클라이언트가 자동으로 찾을 수 있습니다.**동일한 서브넷**서버

`-p`: 협력`-host` 두 당사자는 정보를 자동으로 교환하므로 일반적으로 지정할 필요가 없기 때문에 사용합니다. 두 당사자가 정상적으로 연결할 수없는 경우에만 명시 적으로 지정할 수 있습니다.

#### 명령 지침

정상 연결 후 지침을 입력하십시오

1. 파일 (클립) 경로를 입력 한 다음 파일 보내기를 실행합니다.
2. 입력하다`sysinfo`, 양 당사자의 시스템 정보를 표시합니다
3. 입력하다`speedtest n`, 네트워크의 속도를 테스트합니다. n은이 테스트의 데이터 볼륨, 단위 MB. 참고입니다.**그물**1GB = 1000MB = 10000000 KB.
4. 입력하다`compare local_dir dest_dir`폴더와 서버 폴더의 차이점을 비교해 봅시다.
5. 다른 내용을 지침으로 입력하고 결과를 실시간으로 반환 할 때.

#### 스크린 샷을 실행하십시오

다음은 동일한 호스트에서 실행되는 스크린 샷입니다.

<img src="assets/image-20230421175852690.png" alt="image-20230421175852690" style="zoom:67%;" />

<img src="assets/image-20230421174220808.png" alt="sysinfo效果（同一台主机展示）" style="zoom:60%;" />

<img src="assets/image-20230421175214141.png" alt="测试1GB数据量" style="zoom: 80%;" />

<img src="assets/image-20230421175524115.png" alt="image-20230421175524115" style="zoom:67%;" />

<img src="assets/image-20230421175725094.png" alt="image-20230421175725094" style="zoom:80%;" />

### fts

`FTS`파일을 수신하는 파일 인 서버 쪽입니다.이 파일은 파일을 수신하고 저장하고 클라이언트에서 명령을 실행하는 데 사용됩니다.

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

#### 매개 변수 설명

`-d, --dest`: 파일의 스토리지 위치를 지정하고 지정되지 않은 경우 현재 사용자에게 저장됩니다.**데스크탑**그러면

`-p`: 명시 적 전송을 지정하고 기본적으로 SSL 암호화 전송을 사용하십시오. 현재 서명 인증서가없는 경우 명시 적 전송을 지정하십시오.**보안을 보장하려면 자신의 서명 인증서를 사용하십시오.**

`--avoid`: 개방 시점에서 디렉토리에 이미 동일한 이름의 파일이있는 경우 두 가지 경우가 있습니다.**예방하다**이 파일의 전송, 그렇지 않으면 수신되고**덮어 쓰기**이 파일;이 기능은 주로 중단 된 후 많은 파일을 전송하는 데 사용됩니다.**조심스럽게 사용하십시오**열리지 않으면 기존 파일의 이름이 지정된 경우`a.txt`전송 된 파일은 다음과 같습니다`a (1).txt`게다가`a (2).txt`순서대로 지명되었습니다.

#### 스크린 샷을 실행하십시오

<img src="assets/image-20230421180254963.png" alt="image-20230421180254963" style="zoom:70%;" />

## 구성

구성 항목`Utils.py`가운데

`log_dir`: 로그 상점 위치 </br>
`cert_dir`: 인증서 상점 </br>
`unit` : 데이터 전송 단위 </br>

`server_port`: 서버 TCP 청취 포트 </b>
`server_signal_port`: 서버 UDP 청취 포트 </br>
`client_signal_port`: 클라이언트 UDP 오디션 포트 </br>

 
