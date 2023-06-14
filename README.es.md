# Herramienta de transmisión de archivos

> Advertencia: este artículo está traducido por una máquina, lo que puede dar lugar a una mala calidad o información incorrecta. ¡Lea atentamente!

## Breve introducción

`File Transfer Tools`  Incluir `FTS (File Transfer Server) ` , `FTC (File Transfer Client) ` Dos componentes, sí **Ligero** Así como **rápido** Así como **Seguridad** Así como **Multifunción** Script de transmisión de archivos cruzados.

### Función

1. transferencia de archivos

  - Puede transmitir un solo archivo o toda la carpeta
  - Garantía de seguridad: transmisión cifrada (utilizando un protocolo de capa de conexión de concesión), transmisión explícita
  - Cierta garantía: a través de la consistencia del archivo de verificación de valor hash, determine si todos los archivos en la carpeta se transmiten correctamente
  - Pantalla de la barra de progreso: progreso de transmisión de archivos de pantalla real, velocidad de red actual, duración de la transmisión restante
  - Transmisión recién nombrada, evite la transmisión repetida y la transmisión de cubierta del mismo nombre

2. La línea de comando puede ejecutar fácilmente el comando en el control remoto y devolver el resultado en tiempo real, similar a SSH
3. Encontrar el host de servicio automáticamente, también puede especificar manualmente el host de conexión
4. La comparación de las carpetas puede mostrar información de los archivos en las dos carpetas, las mismas diferencias, etc.
5. Verifique el estado y la información del sistema e información del sistema del cliente y del servidor
6. Registros de salida de tiempo real a la consola y los archivos
7. prueba de velocidad de Internet

### Característica

1. Velocidad rápida de inicio, ejecución y respuesta
2. Se puede utilizar en cualquier entorno de red, como la red de área local y la red pública.
3. La transmisión de múltiples temas, la velocidad de transmisión rápida, puede ejecutarse más de 1000Mbps en el ancho de banda en la medición real. Debido al límite del equipo, no se prueba un mayor ancho de banda
4. La ocupación de la memoria es pequeña durante el tiempo de ejecución
5. Es decir, abrir y apagar el proceso no seguirá siendo el proceso

### como escoger

1. Si desea un servicio de transmisión de archivos más potente, seleccione el servidor FTP y el cliente (como `FileZilla` Así como `WinSCP` esperar)
2. Si desea sincronización y compartir de archivos estables, se recomienda usar `Resilio Sync` Así como `Syncthing` esperar
3. Si simplemente transmite archivos ocasionalmente/no me gusta la retención de fondo de los servicios anteriores, ocupación de recursos/no más poderoso servicio/Si desea personalizar su propia función, elija `File Transfer Tools` 

## Instalación y operación

 `FTS` Occupy Port 2023,2021, FTC Ocupa Port 2022. Entre ellos, el puerto 2023 se utiliza como `FTS` El puerto de escucha TCP, 2021, 2022 como la interfaz de transmisión UDP entre el servidor y el cliente. Puede verificar los detalles al final de este artículo.

### Descargar el programa ejecutable

1. Haga clic a la derecha `Release` 
2. descargar `File Transfer Tools.zip` 
3. Carpeta descifrada, doble clic `FTC.exe`  o  `FTS.exe`  Solo corre
4. O ejecute el programa en el terminal para usar el parámetro del programa, por ejemplo `.\FTC.exe [-h] [-t thread] [-host host] [-p]` 

### Usa el intérprete de Python para ejecutar

1. Clon el código fuente de la ubicación de su proyecto
2. usar `pip install -r requirements.txt` Instalar todas las dependencias
3. Use su intérprete de Python para ejecutar el script

#### Método de práctica

Tomando Windows como ejemplo, puede escribir los comandos en ejecución de FTS y FTCS como archivos por lotes, y luego agregar el directorio del archivo por lotes a su variable de entorno, para que pueda escribir la línea de comandos simplemente en la línea de comandos `FTS` Así como `FTC` Usemos el comando predeterminado y más simple para ejecutar el programa.

Por ejemplo, puede escribir el siguiente comando en el archivo `FTS.bat` medio

```powershell
@echo off
 "The dir of your Python interpreter" \Scripts\python.exe  "The dir of your project" \FTS.py %1 %2 %3 %4 %5 %6
```

Escriba el siguiente comando en el archivo `FTC.bat` medio

```powershell
@echo off
 "The dir of your Python interpreter" \Scripts\python.exe  "The dir of your project" \FTC.py %1 %2 %3 %4 %5 %6
```

Luego, agregue la carpeta por lotes a su variable de entorno y finalmente escriba el siguiente comando en su terminal para ejecutar el código rápidamente

```powershell
FTC [-h] [-t thread] [-host host] [-p]
或
FTS [-h] [-d base_dir] [-p] [--avoid]
```

En el lote anterior de documentos de procesamiento, `%1~%9` Expresar el parámetro del programa ( `%0` Representa la ruta actual)



## uso

### FTC

FTC es un final de envío de archivos, instrucción que envía final, para enviar archivos e instrucciones.

```
usage: FTC.py [-h] [-t thread] [-host host] [-p]

File Transfer Client, used to SEND files.

optional arguments:
  -h, --help       show this help message and exit
  -t thread        threading number (default: 3)
  -host host       destination hostname or ip address
  -p, --plaintext  Use plaintext transfer (default: use ssl)
```

#### Descripción de parámetros

 `-t` : Especifique el número de subprocesos, el valor predeterminado es 3 subprocesos.

 `-host` : Especifique explícitamente el host del lado receptor (usando el nombre de host o la dirección IP). Cuando esta opción no se usa, el cliente encontrará automáticamente **La misma subred** El servidor

 `-p` : Cooperar `-host`  Use, porque las dos partes intercambiarán información automáticamente, por lo que generalmente no es necesario especificar. Solo cuando las dos partes no pueden conectarse normalmente, debe especificarse aparentemente.

#### Instrucciones de comando

Después de la conexión normal, ingrese las instrucciones

1. Ingrese la ruta del archivo (clip), luego ejecute el archivo de envío
2. ingresar `sysinfo` , Mostrará la información del sistema de ambas partes
3. ingresar `speedtest n` , Luego pruebe la velocidad de la red. **Neto** En el medio, 1 GB = 1000 MB = 1000000 KB.
4. ingresar `compare local_dir dest_dir` Comparemos la diferencia entre la carpeta y la carpeta del servidor.
5. Al ingresar a otros contenidos, realice como una instrucción y devuelva los resultados en tiempo real.

#### Ejecutar una captura de pantalla

Las siguientes son capturas de pantalla que se ejecutan en el mismo host.

<img src= "assets/image-20230421175852690.png"  alt= "image-20230421175852690"  style= "zoom:67%;"  />

<img src= "assets/image-20230421174220808.png"  alt= "sysinfo效果（同一台主机展示）"  style= "zoom:60%;"  />

<img src= "assets/image-20230421175214141.png"  alt= "测试1GB数据量"  style= "zoom: 80%;"  />

<img src= "assets/image-20230421175524115.png"  alt= "image-20230421175524115"  style= "zoom:67%;"  />

<img src= "assets/image-20230421175725094.png"  alt= "image-20230421175725094"  style= "zoom:80%;"  />

### Fts

 `FTS` Es el extremo de recepción del archivo, el lado del servidor, que se utiliza para recibir y almacenar archivos, y ejecutar las instrucciones del cliente.

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

#### Descripción de parámetros

 `-d, --dest` : Especifique la posición de almacenamiento del archivo, si no se especifica, se almacena en el usuario actual. **escritorio** Luego luego

 `-p` : Especifique la transmisión explícita y use la transmisión de cifrado SSL de forma predeterminada. Si no tiene un certificado de firma en la actualidad, especifique la transmisión explícita. **Para garantizar la seguridad, utilice su propio certificado de firma.** 

 `--avoid` : En el momento de la apertura, si ya hay archivos del mismo nombre en el directorio, hay dos casos en dos casos. **Prevenir** La transmisión de este archivo, de lo contrario se recibirá y **Sobrescribir** Este archivo; esta función se usa principalmente para transmitir una gran cantidad de archivos después de ser interrumpido. **Usar con cautela** Cuando no se abre, si se nombra el archivo `a.txt` Entonces el archivo transmitido será de acuerdo con `a (1).txt` Así como `a (2).txt` Nombrado en orden.

#### Ejecutar una captura de pantalla

<img src= "assets/image-20230421180254963.png"  alt= "image-20230421180254963"  style= "zoom:70%;"  />

## Configuración

Elemento de configuración `Utils.py` medio

 `log_dir` : Ubicación de la tienda de registros </br>
 `cert_dir` : Tienda de certificados </br>
 `unit`  : Unidad de envío de datos </br>

 `server_port` : Puerto de escucha TCP del servidor </b>
 `server_signal_port` : Puerto de escucha UDP del servidor </br>
 `client_signal_port` : Puerto de audición UDP del cliente </br>

