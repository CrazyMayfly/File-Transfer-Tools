# Widget de transferencia de archivos

## Introducción

`Herramientas de transferencia de archivos` contiene dos componentes `FTS (Servidor de transferencia de archivos)` y `FTC (Cliente de transferencia de archivos)`, que son **ligeros**, **rápidos**, **seguros** y más. potente secuencia de comandos de transferencia de archivos entre dispositivos.

### Función

1. Transferencia de archivos

- Transferir archivos individuales o carpetas enteras
- Garantía de seguridad: se puede utilizar la transmisión cifrada (mediante el protocolo de capa de sockets seguros) y la transmisión de texto claro
- Garantía de corrección: verifique la consistencia de los archivos a través del valor Hash y juzgue si todos los archivos en la carpeta se transmiten correctamente
- Visualización de la barra de progreso: visualización en tiempo real del progreso de la transferencia de archivos, la velocidad actual de la red y el tiempo de transferencia restante
- Tres métodos para cambiar el nombre del archivo con el mismo nombre, evitar la transferencia duplicada y sobrescribir la transferencia

2. Línea de comandos, que puede ejecutar fácilmente comandos de forma remota y devolver resultados en tiempo real, similar a ssh
3. Encuentre automáticamente el host de servicio o especifique manualmente el host de conexión
4. Comparación de carpetas, que puede mostrar información como lo mismo y las diferencias de archivos en dos carpetas
5. Ver el estado y la información del sistema del cliente y del servidor
6. Salida de registros a la consola y archivos en tiempo real, y puede organizar automáticamente archivos de registro comprimidos
7. Pruebe convenientemente el ancho de banda de la red entre el cliente y el servidor
8. Puede establecer una contraseña de conexión para el servidor para mejorar la seguridad
9. Sincronice convenientemente el contenido del portapapeles del cliente y el servidor

### Características

1. Comience, ejecute y responda rápidamente
2. Adopte el principio de configuración predeterminada mínima, que se puede usar de forma inmediata, y puede modificar fácilmente la configuración usted mismo
2. Se puede utilizar en cualquier entorno de red, como LAN y red pública, siempre que los dos hosts puedan conectarse a la red.
3. Transmisión de subprocesos múltiples, velocidad de transmisión rápida, la prueba real puede funcionar con un ancho de banda de hasta 1000 Mbps, debido a las limitaciones del equipo, no hay prueba para un ancho de banda más alto
4. El uso de la memoria es pequeño en tiempo de ejecución y se adopta el modo de carga diferida para garantizar la ocupación mínima de recursos
5. Abre, cierra y listo al instante, no quedará ningún proceso después de cerrar el programa
6. Actualmente compatible con plataformas Windows y Linux

### como escoger

1. Si desea un servicio de transferencia de archivos más potente, elija un servidor FTP, un cliente (como `FileZilla`, `WinSCP`, etc.)
2. Si desea sincronizar y compartir archivos de forma estable, se recomienda utilizar `Resilio Sync`, `Syncthing`, etc.
3. Si solo transfiere archivos ocasionalmente/no le gusta el almacenamiento en segundo plano y la ocupación de recursos de los servicios anteriores/no necesita un servicio tan potente/quiere personalizar las funciones, elija `Herramientas de transferencia de archivos`

## Instalar y ejecutar

`FTS` ocupa los puertos 2023 y 2021 de forma predeterminada, y FTC ocupa el puerto 2022 de forma predeterminada. Entre ellos, el puerto 2023 se usa como puerto de escucha TCP de `FTS`, y 2021 y 2022 se usan como interfaces de transmisión UDP entre el servidor y el cliente.
Puede consultar la información de configuración detallada y modificar la configuración anterior al final de este artículo.

### Descargar programa ejecutable

1. Haga clic en "Liberar" a la derecha
2. Descargue `Herramientas de transferencia de archivos.zip`
3. Descomprima la carpeta, haga doble clic en `FTC.exe` o `FTS.exe` para ejecutar
4. O ejecute el programa en una terminal para usar los parámetros del programa, como `.\FTC.exe [-h] [-t thread] [-host host] [-p]`

### Ejecutar con el intérprete de Python

1. Clona el código fuente en la ubicación de tu proyecto
2. Instale todas las dependencias usando `pip install -r requirements.txt`
3. Ejecute el script usando su intérprete de python

#### método de ejecución de atajos

Tomando Windows como ejemplo, puede escribir los comandos de ejecución de FTS y FTC como archivos por lotes, y luego agregar el directorio del archivo por lotes a su variable de entorno, de modo que simplemente pueda escribir `FTS `, `FTC`
Usemos el comando predeterminado y más simple para ejecutar el programa.

Por ejemplo, puede escribir el siguiente comando en el archivo `FTS.bat`

```powershell
@echo apagado
"El directorio de su intérprete de Python"\Scripts\python.exe "El directorio de su proyecto"\FTS.py %1 %2 %3 %4 %5 %6
```

Escribe el siguiente comando en el archivo `FTC.bat`

```powershell
@echo apagado
"El directorio de su intérprete de Python"\Scripts\python.exe "El directorio de su proyecto"\FTC.py %1 %2 %3 %4 %5 %6
```

Luego, agregue la carpeta por lotes a sus variables de entorno y, finalmente, escriba el siguiente comando en su terminal para ejecutar rápidamente el código

```powershell
FTC.py [-h] [-t subproceso] [-host host] [-p contraseña] [--texto sin formato]
o
FTS.py [-h] [-d base_dir] [-p contraseña] [--texto sin formato] [--evitar]
```

En el archivo por lotes anterior, `%1~%9` representa los parámetros pasados ​​por el programa (`%0` representa la ruta actual)
Tenga en cuenta que la ruta de trabajo predeterminada del terminal es el directorio de usuario (~), si necesita modificar el archivo de configuración, modifíquelo en este directorio.

## Uso

###FTC

FTC es el cliente para el envío de archivos e instrucciones.

```
uso: FTC.py [-h] [-t subproceso] [-host host] [-p contraseña] [--texto sin formato]

File Transfer Client, utilizado para ENVIAR archivos e instrucciones.

argumentos opcionales:
   -h, --help muestra este mensaje de ayuda y sale
   -t subprocesos subprocesos (predeterminado: 8)
   -host host destino nombre de host o dirección IP
   -p contraseña, --contraseña contraseña
                         Use una contraseña para conectarse al host.
   --plaintext Usar transferencia de texto sin formato (predeterminado: usar ssl)
```

#### Descripción de parámetros

`-t`: especifica el número de subprocesos, el valor predeterminado es el número de procesadores lógicos.

`-host`: especifique explícitamente el nombre de host del servidor (nombre de host o ip) y el número de puerto (opcional). Cuando no se usa esta opción, el cliente buscará automáticamente un servidor en **misma subred**

`-p`: Especifique explícitamente la contraseña de conexión para el servidor (el servidor no tiene contraseña por defecto).

`--plaintext`: especifique explícitamente los datos de transmisión de texto sin formato, lo que requiere que el servidor también utilice la transmisión de texto sin formato.

#### Descripción del comando

Después de una conexión normal, ingrese el comando

1. Introduzca la ruta del archivo (carpeta) y se enviará el archivo (carpeta)
2. Ingrese `sysinfo`, se mostrará la información del sistema de ambas partes
3. Ingrese `speedtest n` y se probará la velocidad de la red, donde n es la cantidad de datos en esta prueba, en MB. Tenga en cuenta que en **Redes informáticas**, 1 GB = 1000 MB = 1000000 KB.
4. Ingrese `compare local_dir dest_dir` para comparar la diferencia entre los archivos en la carpeta local y la carpeta del servidor.
5. Ingrese `clip pull/push` o `clip get/send` para sincronizar el contenido del portapapeles del cliente y del servidor
6. Cuando se ingresa otro contenido, se usa como una instrucción para que el servidor lo ejecute y el resultado se devuelve en tiempo real.

#### Ejecuta la captura de pantalla

Las siguientes son capturas de pantalla que se ejecutan en el mismo host.

inicio del programa

![inicio](assets/startup.png)

transferir archivos
![archivo](assets/file.png)

Comando de ejecución: sysinfo

![info del sistema](assets/sysinfo.png)

Ejecute el comando: prueba de velocidad

![prueba de velocidad](assets/speedtest.png)

Ejecute el comando: comparar

![comparar](assets/compare.png)

Ejecute el comando: recortar

![clip](assets/clip.png)

Ejecutar comandos de línea de comandos

![comando](assets/cmd.png)

### FTS

`FTS` es el lado del servidor, utilizado para recibir y almacenar archivos y ejecutar las instrucciones enviadas por el cliente.

```
uso: FTS.py [-h] [-d base_dir] [-p contraseña] [--texto sin formato] [--evitar]

Servidor de transferencia de archivos, utilizado para RECIBIR archivos y EJECUTAR instrucciones.

argumentos opcionales:
   -h, --help muestra este mensaje de ayuda y sale
   -d directorio_base, --dest directorio_base
                         Ubicación de almacenamiento de archivos (predeterminada: C:\Users\admin/Desktop)
   -p contraseña, --contraseña contraseña
                         Establezca una contraseña para el host.
   --plaintext Usar transferencia de texto sin formato (predeterminado: usar ssl)
   --evitar No continuar la transferencia cuando se repite el nombre del archivo.
```

#### Descripción de parámetros

`-d, --dest`: especifique explícitamente la ubicación de recepción del archivo, el valor predeterminado es el valor del elemento de configuración "platform_default_path" (la plataforma de Windows tiene como valor predeterminado **escritorio**).

`-p, --password`: establezca una contraseña para el servidor para evitar conexiones maliciosas.

`--plaintext`: especifique explícitamente la transmisión de datos en texto sin formato y utilice la transmisión cifrada SSL de forma predeterminada.

`--evitar`: cuando está habilitado, si ya hay un archivo con el mismo nombre en el directorio, hay dos casos.Si el tamaño del archivo en el extremo receptor es mayor o igual que el extremo emisor, ** bloquear** la transmisión del archivo, de lo contrario, recibir y **sobrescribir* *Este archivo; esta función se usa principalmente para la retransmisión después de que una gran cantidad de archivos se interrumpen a la vez, similar a la retransmisión de punto de interrupción, por favor **use con precaución ** en otros casos. Cuando no está habilitado, si el nombre del archivo existente es `a.txt`, los archivos transferidos se nombrarán de acuerdo con `a (1).txt`, `a (2).txt` en secuencia.

#### Ejecutar captura de pantalla

![FTS](assets/FTS.png)

## configuración

Los elementos de configuración están en el archivo de configuración `config.txt`, cuando el archivo de configuración no existe, el programa creará automáticamente el archivo de configuración predeterminado

### La configuración principal del programa Principal
`windows_default_path`: la ubicación predeterminada de recepción de archivos en la plataforma Windows
`linux_default_path`: la ubicación de recepción de archivos predeterminada en la plataforma Linux
`cert_dir`: la ubicación de almacenamiento del archivo de certificado

### Configuración relacionada con el registro
`windows_log_dir`: la ubicación de almacenamiento de archivos de registro predeterminada en la plataforma Windows
`linux_log_dir`: la ubicación de almacenamiento de archivos de registro predeterminada en la plataforma Linux
`log_file_archive_count`: archivar cuando el número de archivos de registro exceda este tamaño
`log_file_archive_size`: Archivar cuando el tamaño total (bytes) del archivo de registro excede este tamaño

### Configuración del puerto contenido relacionado con el puerto
`server_port`: puerto de escucha TCP del servidor
`server_signal_port`: puerto de escucha UDP del servidor
`client_signal_port`: puerto de escucha UDP del cliente