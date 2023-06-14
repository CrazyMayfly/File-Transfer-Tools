# Ferramenta de transmissão de arquivos

> Aviso: Este artigo é traduzido por máquina, o que pode levar a má qualidade ou informações incorretas, leia com atenção!

## Breve introdução

 `File Transfer Tools`  Incluir `FTS (File Transfer Server) ` ,, `FTC (File Transfer Client) ` Dois componentes, sim **Leve** Assim como **rápido** Assim como **Segurança** Assim como **Multifuncional** Script de transmissão de arquivo de device cruzado.

### Função

1. transferência de arquivo

  - Pode transmitir um único arquivo ou a pasta inteira
  - Garantia de segurança: transmissão criptografada (usando protocolo de camada de concessão de concessão), transmissão explícita
  - Certa garantia: Através da consistência do arquivo de verificação do valor do hash, determine se todos os arquivos na pasta são transmitidos corretamente
  - Exibição da barra de progresso: Real -Time Exibir Progresso da transmissão de arquivo, taxa de rede atual, duração restante da transmissão
  - Transmissão recém -nomeada, evite transmissão repetida e cubra a transmissão de mesmo nome

2. A linha de comando pode executar facilmente o comando no controle remoto e retornar o resultado em tempo real, semelhante ao ssh
3. Encontrando o host de serviço automaticamente, você também pode especificar manualmente o host de conexão
4. A comparação de pastas pode exibir informações dos arquivos nas duas pastas, as mesmas, diferenças etc.
5. Verifique o status e as informações do sistema e do sistema de servidor e informações
6. Real -Time Output Logs para console e arquivos
7. Teste de velocidade da Internet

### Característica

1. Velocidade rápida de partida, corrida e resposta
2. Pode ser usado em qualquer ambiente de rede, como a rede local da área e a rede pública.
3. Transmissão multi -threaded, velocidade de transmissão rápida, pode ocorrer mais de largura de banda de 1000 Mbps na medição real. Devido ao limite do equipamento, nenhuma largura de banda mais alta é testada
4. A ocupação da memória é pequena durante o tempo de execução
5. Isto é, aberto e desligar o processo não permanecerá o processo

### como escolher

1. Se você deseja um serviço de transmissão de arquivos mais poderoso, selecione o servidor e o cliente FTP (como `FileZilla` Assim como `WinSCP` espere)
2. Se você deseja sincronização e compartilhamento de arquivos estáveis, é recomendável usar `Resilio Sync` Assim como `Syncthing` espere
3. Se você apenas transmitir arquivos ocasionalmente/eu não gosto da retenção de fundo dos serviços acima, ocupação de recursos/Não é mais poderoso serviço/se você deseja personalizar sua própria função, escolha `File Transfer Tools` 

## Instalação e operação

 `FTS` Occupy Port 2023.2021, FTC ocupa o porto 2022. Entre eles, o porto 2023 é usado como `FTS` A porta de escuta do TCP, 2021, 2022 como a interface de transmissão UDP entre o servidor e o cliente. Você pode verificar os detalhes no final deste artigo.

### Baixe o programa executável

1. Clique na direita `Release` 
2. download `File Transfer Tools.zip` 
3. Pasta descompacente, clique duplo `FTC.exe`  ou  `FTS.exe`  Apenas corra
4. Ou execute o programa no terminal para usar o parâmetro do programa, por exemplo `.\FTC.exe [-h] [-t thread] [-host host] [-p]` 

### Use o intérprete Python para executar

1. Clone o código -fonte para o local do seu projeto
2. usar `pip install -r requirements.txt` Instalar todas as dependências
3. Use seu intérprete Python para executar o script

#### Método da prática

Tomando o Windows como exemplo, você pode escrever os comandos em execução do FTS e FTCS como arquivos em lote e, em seguida, adicionar o diretório do arquivo em lote à sua variável de ambiente, para que você possa digitar a linha de comando simplesmente na linha de comando `FTS` Assim como `FTC` Vamos usar o comando padrão e mais simples para executar o programa.

Por exemplo, você pode escrever o seguinte comando para o arquivo `FTS.bat` meio

```powershell
@echo off
 "The dir of your Python interpreter" \Scripts\python.exe  "The dir of your project" \FTS.py %1 %2 %3 %4 %5 %6
```

Escreva o seguinte comando para o arquivo `FTC.bat` meio

```powershell
@echo off
 "The dir of your Python interpreter" \Scripts\python.exe  "The dir of your project" \FTC.py %1 %2 %3 %4 %5 %6
```

Em seguida, adicione a pasta em lote à sua variável de ambiente e, finalmente, digite o seguinte comando em seu terminal para executar o código rapidamente

```powershell
FTC [-h] [-t thread] [-host host] [-p]
或
FTS [-h] [-d base_dir] [-p] [--avoid]
```

No lote acima de documentos de processamento, `%1~%9` Expressar o parâmetro do programa ( `%0` Representa o caminho atual)



## uso

### Ftc

FTC é um final de envio de arquivo, final de envio de instruções, para enviar arquivos e instruções.

```
usage: FTC.py [-h] [-t thread] [-host host] [-p]

File Transfer Client, used to SEND files.

optional arguments:
  -h, --help       show this help message and exit
  -t thread        threading number (default: 3)
  -host host       destination hostname or ip address
  -p, --plaintext  Use plaintext transfer (default: use ssl)
```

#### Descrição do parâmetro

 `-t` : Especifique o número de threads, o padrão é de 3 threads.

 `-host` : Especifique explicitamente o host do lado receptor (usando o nome do host ou o endereço IP). Quando esta opção não for usada, o cliente encontrará automaticamente **A mesma sub -rede** O servidor

 `-p` : Colaborar `-host`  Use, porque as duas partes trocam informações automaticamente, geralmente não precisam ser especificadas. Somente quando as duas partes não podem se conectar normalmente, elas precisam ser aparentemente especificadas.

#### Instruções de comando

Após a conexão normal, insira as instruções

1. Digite o caminho do arquivo (clipe) e execute o arquivo de envio
2. digitar `sysinfo` , Exibirá as informações do sistema de ambas as partes
3. digitar `speedtest n` , Então teste a velocidade da rede. **Líquido** No meio, 1 GB = 1000 MB = 1000000 KB.
4. digitar `compare local_dir dest_dir` Vamos comparar a diferença entre a pasta e a pasta do servidor.
5. Ao inserir outros conteúdos, execute -o como uma instrução e retorne os resultados em tempo real.

#### Execute uma captura de tela

A seguir, são apresentadas capturas de tela em execução no mesmo host.

<img src= "assets/image-20230421175852690.png"  alt= "image-20230421175852690"  style= "zoom:67%;"  />

<img src= "assets/image-20230421174220808.png"  alt= "sysinfo效果（同一台主机展示）"  style= "zoom:60%;"  />

<img src= "assets/image-20230421175214141.png"  alt= "测试1GB数据量"  style= "zoom: 80%;"  />

<img src= "assets/image-20230421175524115.png"  alt= "image-20230421175524115"  style= "zoom:67%;"  />

<img src= "assets/image-20230421175725094.png"  alt= "image-20230421175725094"  style= "zoom:80%;"  />

### Fts

 `FTS` É a extremidade do recebimento do arquivo, o lado do servidor, que é usado para receber e armazenar arquivos e executar as instruções do cliente.

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

#### Descrição do parâmetro

 `-d, --dest` : Especifique a posição de armazenamento do arquivo, se não for especificada, ele é armazenado no usuário atual. **Área de Trabalho** Então então

 `-p` : Especifique a transmissão explícita e use a transmissão de criptografia SSL por padrão. Se você não tiver um certificado de assinatura atualmente, especifique a transmissão explícita. **Para garantir a segurança, use seu próprio certificado de assinatura.** 

 `--avoid` : No momento da abertura, se já houver arquivos de mesmo nome no diretório, há dois casos em dois casos. **Evitar** A transmissão deste arquivo, caso contrário, será recebido e **Substituir** Este arquivo; esta função é usada principalmente para transmitir um grande número de arquivos após ser interrompido. **Use cautelosamente** Quando não for aberto, se o arquivo for nomeado `a.txt` Então o arquivo transmitido será de acordo com `a (1).txt` Assim como `a (2).txt` Nomeado em ordem.

#### Execute uma captura de tela

<img src= "assets/image-20230421180254963.png"  alt= "image-20230421180254963"  style= "zoom:70%;"  />

## Configuração

Item de configuração `Utils.py` meio

 `log_dir` : Localização da loja de log </br>
 `cert_dir` : Loja de certificados </br>
 `unit`  : Unidade de envio de dados </br>

 `server_port` : Porta de escuta do servidor TCP </b>
 `server_signal_port` : Porta de escuta UDP do servidor </br>
 `client_signal_port` : Porta de audição UDP do cliente </br>

