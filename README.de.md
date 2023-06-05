# Dateiübertragungswerkzeug

> Achtung: Dieser Artikel wurde maschinell übersetzt, was zu schlechter Qualität oder falschen Informationen führen kann, bitte sorgfältig lesen!

## Kurze Einleitung

`File Transfer Tools` Enthalten`FTS (File Transfer Server) `,,,,`FTC (File Transfer Client) `Zwei Komponenten, ja**Leicht**Ebenso gut wie**schnell**Ebenso gut wie**Sicherheit**Ebenso gut wie**Multifunktion**Cross -Device -Dateiübertragungsskript.

### Funktion

1. Datei Übertragung

  - Kann eine einzelne Datei oder den gesamten Ordner übertragen
  - Sicherheitsgarantie: verschlüsseltes Übertrag
  - Bestimmte Garantie: Bestimmen Sie durch die Konsistenz der Hash -Wert -Überprüfungsdatei
  - Fortschrittsleiste Anzeige: Real -Time Display -Dateiübertragungsfortschritt, aktuelle Netzwerkrate, verbleibende Übertragungsdauer
  - Neu benanntes Getriebe, vermeiden Sie wiederholtes Getriebe und Deckung der gleichnamigen Übertragung

2. Die Befehlszeile kann bequem sein, den Befehl am Remote -Ende auszuführen und das Ergebnis in Echtzeit zurückzugeben, ähnlich wie SSH
3. Wenn Sie den Service -Host automatisch finden, können Sie auch den Verbindungshost manuell angeben
4. Mit Vergleich von Ordnern können Sie Informationen zu den Dateien in den beiden Ordnern gleich anzeigen, Unterschiede usw.
5. Überprüfen Sie den Status und die Informationen des Client- und Server -Systemsystems und der Informationen
6. Real -Time -Ausgabebotungsprotokolle für Konsole und Dateien
7. Internetgeschwindigkeitstest

### Charakteristisch

1. Schnelle Startgeschwindigkeit, Laufen und Reaktion
2. Es kann in jeder Netzwerkumgebung wie LAN und öffentlichen Netzwerken verwendet werden.
3. Multi -Thread -Getriebe, schnelle Übertragungsgeschwindigkeit kann in der tatsächlichen Messung über eine Bandbreite von über 1000 Mbit / s ausführen. Aufgrund von Ausrüstungsbeschränkungen wird keine höhere Bandbreite getestet
4. Der Speicherberuf ist während der Laufzeit klein
5. Das heißt, offen und ausschalten, den Prozess wird den Prozess nicht verlassen

### wie man wählt

1. Wenn Sie einen leistungsstärkeren Dateiübertragungsdienst wünschen, wählen Sie FTP Server, Client (z. B.`FileZilla`Ebenso gut wie`WinSCP`Warten)
2. Wenn Sie eine stabile Dateisynchronisation und -freigabe wünschen, wird empfohlen, die Verwendung zu verwenden`Resilio Sync`Ebenso gut wie`Syncthing`Warten
3. Wenn Sie nur gelegentlich Dateien übertragen/ich mag die Hintergrundbehebung der oben genannten Dienste, den Ressourcenbeobachtung/kein leistungsfähigerer Service/Wenn Sie Ihre eigene Funktion anpassen möchten, wählen Sie bitte auswählen`File Transfer Tools`

## Installation und Betrieb

`FTS`Occupy Port 2023.2021, FTC nimmt Port 2022 ein. Unter ihnen wird Port 2023 als verwendet als`FTS`Der TCP -Hörport 2021 und 2022 als UDP -Übertragungsschnittstelle zwischen dem Server und dem Client. Sie können die Details am Ende dieses Artikels anzeigen.

### Laden Sie das ausführbare Programm herunter

1. Klicken Sie auf rechts`Release`
2. herunterladen`File Transfer Tools.zip`
3. Den Ordner entpacken, doppeltklick`FTC.exe` oder `FTS.exe` Lauf einfach
4. Oder führen Sie das Programm im Terminal aus, um zum Beispiel den Programmparameter zu verwenden`.\FTC.exe [-h] [-t thread] [-host host] [-p]`

### Verwenden Sie Python Interpreter, um zu laufen

1. Klonen Sie den Quellcode an Ihren Projektort
2. verwenden`pip install tqdm==4.65.0`TQDM installieren
3. Verwenden Sie Ihren Python -Interpreter, um das Skript auszuführen

#### Übungsmethode

Wenn Sie Windows als Beispiel nehmen, können Sie die laufenden Befehle von FTS und FTCs als Batch -Dateien schreiben und dann das Verzeichnis der Batch -Datei zu Ihrer Umgebungsvariablen hinzufügen, damit Sie die Befehlszeile einfach in der Befehlszeile eingeben können`FTS`Ebenso gut wie`FTC`Verwenden wir den Standard- und einfachsten Befehl, um das Programm auszuführen.

Zum Beispiel können Sie den folgenden Befehl in die Datei schreiben`FTS.bat`Mitte

```powershell
@echo off
"The dir of your Python interpreter"\Scripts\python.exe "The dir of your project"\FTS.py %1 %2 %3 %4 %5 %6
```

Schreiben Sie den folgenden Befehl in die Datei`FTC.bat`Mitte

```powershell
@echo off
"The dir of your Python interpreter"\Scripts\python.exe "The dir of your project"\FTC.py %1 %2 %3 %4 %5 %6
```

Fügen Sie dann den Batch -Ordner Ihrer Umgebungsvariablen hinzu und geben Sie schließlich den folgenden Befehl in Ihr Terminal ein, um den Code schnell auszuführen

```powershell
FTC [-h] [-t thread] [-host host] [-p]
或
FTS [-h] [-d base_dir] [-p] [--avoid]
```

In der obigen Stapel von Verarbeitungsdokumenten,,`%1~%9`Den Parameter des Programms ausdrücken (`%0`Repräsentiert den aktuellen Pfad)



## Verwendung

### Ftc

FTC ist eine Datei, die das Ende sendet, Anweisungen zum Senden von Ende, zum Senden von Dateien und Anweisungen.

```
usage: FTC.py [-h] [-t thread] [-host host] [-p]

File Transfer Client, used to SEND files.

optional arguments:
  -h, --help       show this help message and exit
  -t thread        threading number (default: 3)
  -host host       destination hostname or ip address
  -p, --plaintext  Use plaintext transfer (default: use ssl)
```

#### Parameterbeschreibung

`-t`: Geben Sie die Anzahl der Threads an, die Standardeinstellung beträgt 3 Threads.

`-host`: Differential Angabe des empfangenden Seitenhosts (mithilfe von Hostname oder IP -Adresse). Wenn diese Option nicht verwendet wird, findet der Client automatisch**Das gleiche Subnetz**Der Kellner

`-p`: Kooperieren`-host` Verwenden Sie, da die beiden Parteien Informationen automatisch austauschen, sodass im Allgemeinen nicht angegeben werden muss. Nur wenn die beiden Parteien normalerweise keine Verbindung herstellen können, können sie normalerweise explizit angegeben werden.

#### Befehlsanweisungen

Geben Sie nach der normalen Verbindung Anweisungen ein

1. Geben Sie den Pfad der Datei (Clip) ein und führen Sie die Sendendatei aus
2. eingeben`sysinfo`Zeigt die Systeminformationen beider Parteien an
3. eingeben`speedtest n`, Wird die Geschwindigkeit des Netzwerks testen, n ist das Datenvolumen dieses Tests, Einheit mb. Hinweis, in der**Netz**In 1 GB = 1000 MB = 1000000 kb.
4. eingeben`compare local_dir dest_dir`Vergleichen wir den Unterschied zwischen dem Ordner und dem Serverordner.
5. Wenn Sie andere Inhalte als Anweisungen eingeben, und die Ergebnisse in Echtzeit zurückgeben.

#### Führen Sie einen Screenshot aus

Im Folgenden werden Screenshots auf demselben Host ausgeführt.

<img src="assets/image-20230421175852690.png" alt="image-20230421175852690" style="zoom:67%;" />

<img src="assets/image-20230421174220808.png" alt="sysinfo效果（同一台主机展示）" style="zoom:60%;" />

<img src="assets/image-20230421175214141.png" alt="测试1GB数据量" style="zoom: 80%;" />

<img src="assets/image-20230421175524115.png" alt="image-20230421175524115" style="zoom:67%;" />

<img src="assets/image-20230421175725094.png" alt="image-20230421175725094" style="zoom:80%;" />

### Fts

`FTS`Es ist die Datei empfängt das Ende, die Serverseite, mit der Dateien empfangen und gespeichert werden und die Anweisung vom Client ausgeführt werden.

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

#### Parameterbeschreibung

`-d, --dest`: Geben Sie den Speicherort der Datei an, wenn sie nicht angegeben ist, wird sie an den aktuellen Benutzer gespeichert**Desktop**Dann dann

`-p`: Geben Sie die explizite Übertragung an und verwenden Sie standardmäßig die SSL -Verschlüsselungsübertragung. Wenn Sie derzeit kein Signaturzertifikat haben, geben Sie bitte die explizite Übertragung an.**Um die Sicherheit zu gewährleisten, verwenden Sie bitte Ihr eigenes Signaturzertifikat.**

`--avoid`: Zum Zeitpunkt der Öffnung gibt es zwei Fälle, wenn bereits in dem Verzeichnis gleichnamigen Dateien vorhanden sind.**Verhindern**Die Übertragung dieser Datei, sonst wird sie empfangen und**Überschreiben**Diese Datei; diese Funktion wird hauptsächlich zur Übertragung einer großen Anzahl von Dateien verwendet, nachdem sie unterbrochen wurden.**Vorsichtig benutzen**Wenn es nicht geöffnet wird, wenn die vorhandene Datei benannt ist`a.txt`Dann wird die übertragene Datei nach entsprechen`a (1).txt`Ebenso gut wie`a (2).txt`In der Reihenfolge benannt.

#### Führen Sie einen Screenshot aus

<img src="assets/image-20230421180254963.png" alt="image-20230421180254963" style="zoom:70%;" />

## Aufbau

Konfigurationselement`Utils.py`Mitte

`log_dir`: Protokollspeicherort </br>
`cert_dir`: Zertifikat Store </br>
`unit` : Daten senden Einheit </br>

`server_port`: Server TCP Hörport </b>
`server_signal_port`: Server UDP -Hörport </br>
`client_signal_port`: Client UDP -Auditionsport </br>

 
