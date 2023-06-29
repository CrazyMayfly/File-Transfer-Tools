# Widget de transferência de arquivos

## Introdução

`File Transfer Tools` contém `FTS (File Transfer Server)` e `FTC (File Transfer Client)` dois componentes, que são **leves**, **rápidos**, **seguros** e muito mais. poderoso script de transferência de arquivos entre dispositivos.

### Função

1. Transferência de arquivos

- Transfira arquivos individuais ou pastas inteiras
- Garantia de segurança: transmissão criptografada (usando protocolo Secure Sockets Layer) e transmissão de texto não criptografado podem ser usadas
- Garantia de exatidão: verifique a consistência dos arquivos através do valor Hash e julgue se todos os arquivos da pasta foram transmitidos corretamente
- Exibição da barra de progresso: exibição em tempo real do progresso da transferência de arquivos, velocidade atual da rede e tempo restante de transferência
- Três métodos para renomear o arquivo com o mesmo nome, evitando transferência duplicada e sobrescrevendo a transferência

2. Linha de comando, que pode facilmente executar comandos remotamente e retornar resultados em tempo real, semelhante ao ssh
3. Encontre automaticamente o host de serviço ou especifique manualmente o host de conexão
4. Comparação de pastas, que pode exibir informações como as mesmas e as diferenças de arquivos em duas pastas
5. Visualize o status e as informações do sistema cliente e servidor
6. Logs de saída para o console e arquivos em tempo real, e pode organizar automaticamente arquivos de log compactados
7. Teste convenientemente a largura de banda da rede entre o cliente e o servidor
8. Você pode definir uma senha de conexão para o servidor para aumentar a segurança
9. Sincronize convenientemente o conteúdo da área de transferência do cliente e do servidor

### Características

1. Inicie, execute e responda rapidamente
2. Adote o princípio de configuração padrão mínimo, que pode ser usado imediatamente, e você pode modificar facilmente a configuração sozinho
2. Pode ser usado em qualquer ambiente de rede, como LAN e rede pública, desde que os dois hosts possam se conectar à rede
3. Transmissão multi-thread, velocidade de transmissão rápida, o teste real pode executar até 1000 Mbps de largura de banda, devido a limitações do equipamento, nenhum teste para largura de banda maior
4. O uso de memória é pequeno em tempo de execução e o modo de carregamento lento é adotado para garantir a ocupação mínima de recursos
5. Abra, feche e pronto instantaneamente, nenhum processo permanecerá após o fechamento do programa
6. Atualmente compatível com plataformas Windows e Linux

### como escolher

1. Se você deseja um serviço de transferência de arquivos mais poderoso, escolha um servidor FTP, cliente (como `FileZilla`, `WinSCP`, etc.)
2. Se você deseja sincronização e compartilhamento de arquivos estáveis, é recomendável usar `Resilio Sync`, `Syncthing`, etc.
3. Se você apenas transfere arquivos ocasionalmente/não gosta do armazenamento em segundo plano e da ocupação de recursos dos serviços acima/não precisa de um serviço tão poderoso/deseja personalizar funções, escolha `Ferramentas de transferência de arquivo`

## Instalar e executar

`FTS` ocupa as portas 2023 e 2021 por padrão, e FTC ocupa a porta 2022 por padrão. Entre eles, a porta 2023 é usada como porta de escuta TCP do `FTS`, e 2021 e 2022 são usadas como interfaces de transmissão UDP entre o servidor e o cliente.
Você pode verificar as informações de configuração detalhadas e modificar a configuração acima no final deste artigo.

### Baixar programa executável

1. Clique em `Liberar` à direita
2. Baixe `File Transfer Tools.zip`
3. Descompacte a pasta, clique duas vezes em `FTC.exe` ou `FTS.exe` para executar
4. Ou execute o programa em um terminal para usar os parâmetros do programa, como `.\FTC.exe [-h] [-t thread] [-host host] [-p]`

### Execute com o interpretador Python

1. Clone o código-fonte no local do seu projeto
2. Instale todas as dependências usando `pip install -r requirements.txt`
3. Execute o script usando seu interpretador python

#### método de execução de atalho

Tomando o Windows como exemplo, você pode escrever os comandos em execução de FTS e FTC como arquivos em lote e, em seguida, adicionar o diretório do arquivo em lote à sua variável de ambiente, para que você possa simplesmente digitar `FTS `, `FTC`
Vamos usar o comando padrão e mais simples para executar o programa.

Por exemplo, você pode escrever o seguinte comando no arquivo `FTS.bat`

```powershell
@echo off
"O diretório do seu interpretador Python"\Scripts\python.exe "O diretório do seu projeto"\FTS.py %1 %2 %3 %4 %5 %6
```

Escreva o seguinte comando no arquivo `FTC.bat`

```powershell
@echo off
"O diretório do seu interpretador Python"\Scripts\python.exe "O diretório do seu projeto"\FTC.py %1 %2 %3 %4 %5 %6
```

Em seguida, adicione a pasta batch às suas variáveis ​​de ambiente e, finalmente, digite o seguinte comando em seu terminal para executar rapidamente o código

```powershell
FTC.py [-h] [-t thread] [-host host] [-p password] [--plaintext]
ou
FTS.py [-h] [-d base_dir] [-p password] [--plaintext] [--avoid]
```

No arquivo batch acima, `%1~%9` representa os parâmetros passados ​​pelo programa (`%0` representa o caminho atual)
Observe que o caminho de trabalho padrão do terminal é o diretório do usuário (~), se você precisar modificar o arquivo de configuração, modifique-o neste diretório.

## Uso

### FTC

FTC é o cliente para envio de arquivos e instruções.

```
uso: FTC.py [-h] [-t thread] [-host host] [-p password] [--plaintext]

Cliente de Transferência de Arquivos, usado para ENVIAR arquivos e instruções.

argumentos opcionais:
   -h, --help mostra esta mensagem de ajuda e sai
   -t threads (padrão: 8)
   -host host nome do host de destino ou endereço IP
   -p senha, --password senha
                         Use uma senha para conectar o host.
   --plaintext Usa transferência de texto simples (padrão: usa ssl)
```

#### Descrição do Parâmetro

`-t`: Especifica o número de threads, o padrão é o número de processadores lógicos.

`-host`: Especifique explicitamente o nome do host do servidor (hostname ou ip) e o número da porta (opcional). Quando esta opção não for usada, o cliente procurará automaticamente por um servidor na **mesma sub-rede**

`-p`: Especifique explicitamente a senha de conexão para o servidor (o servidor não possui senha por padrão).

`--plaintext`: Especifique explicitamente os dados de transmissão de texto simples, exigindo que o servidor também use a transmissão de texto simples.

#### Descrição do comando

Após uma conexão normal, digite o comando

1. Digite o caminho do arquivo (pasta) e o arquivo (pasta) será enviado
2. Digite `sysinfo`, as informações do sistema de ambas as partes serão exibidas
3. Digite `speedtest n`, e a velocidade da rede será testada, onde n é a quantidade de dados neste teste, em MB. Observe que em **Rede de Computadores**, 1 GB = 1.000 MB = 1.000.000 KB.
4. Digite `compare local_dir dest_dir` para comparar a diferença entre os arquivos na pasta local e a pasta do servidor.
5. Digite `clip pull/push` ou `clip get/send` para sincronizar o conteúdo da área de transferência do cliente e do servidor
6. Quando outro conteúdo é inserido, ele é usado como uma instrução para o servidor executar e o resultado é retornado em tempo real.

#### Executar captura de tela

A seguir estão as capturas de tela em execução no mesmo host.

início do programa

![inicialização](assets/startup.png)

transferir arquivos
![arquivo](assets/file.png)

Comando de execução: sysinfo

![sysinfo](assets/sysinfo.png)

Execute o comando: teste de velocidade

![speedtest](assets/speedtest.png)

Execute o comando: compare

![compare](assets/compare.png)

Execute o comando: clipe

![clip](assets/clip.png)

Executar comandos de linha de comando

![comando](assets/cmd.png)

### FTS

`FTS` é o lado do servidor, usado para receber e armazenar arquivos, e executar as instruções enviadas pelo cliente.

```
uso: FTS.py [-h] [-d base_dir] [-p senha] [--plaintext] [--avoid]

Servidor de transferência de arquivos, usado para RECEBER arquivos e EXECUTAR instruções.

argumentos opcionais:
   -h, --help mostra esta mensagem de ajuda e sai
   -d base_dir, --dest base_dir
                         Local de armazenamento do arquivo (padrão: C:\Users\admin/Desktop)
   -p senha, --password senha
                         Defina uma senha para o host.
   --plaintext Usa transferência de texto simples (padrão: usa ssl)
   --avoid Não continue a transferência quando o nome do arquivo for repetido.
```

#### Descrição do Parâmetro

`-d, --dest`: especifique explicitamente o local de recebimento do arquivo, o padrão é o valor do item de configuração "platform_default_path" (o padrão da plataforma Windows é **desktop**).

`-p, --password`: Defina uma senha para o servidor para evitar conexões maliciosas.

`--plaintext`: Especifique explicitamente a transmissão de dados em texto simples e use a transmissão criptografada SSL por padrão.

`--avoid`: Quando ativado, se já houver um arquivo com o mesmo nome no diretório, há dois casos. Se o tamanho do arquivo no lado receptor for maior ou igual ao lado remetente, ** bloqueie** a transmissão do arquivo, caso contrário, receba e **sobrescreva* *Este arquivo; esta função é usada principalmente para retransmissão depois que um grande número de arquivos é interrompido de uma só vez, semelhante à retransmissão do ponto de interrupção, por favor **use com cuidado ** Em outros casos. Quando não ativado, se o nome do arquivo existente for `a.txt`, os arquivos transferidos serão nomeados de acordo com `a (1).txt`, `a (2).txt` em sequência.

#### Execute a captura de tela

![FTS](assets/FTS.png)

## configuração

Os itens de configuração estão no arquivo de configuração `config.txt`, quando o arquivo de configuração não existir, o programa criará automaticamente o arquivo de configuração padrão

### A configuração principal do programa Principal
`windows_default_path`: O arquivo padrão que recebe o local na plataforma Windows

`linux_default_path`: O arquivo padrão que recebe o local na plataforma Linux

`cert_dir`: O local de armazenamento do arquivo de certificado

### Configuração relacionada ao registro
`windows_log_dir`: O local padrão de armazenamento do arquivo de log na plataforma Windows

`linux_log_dir`: O local padrão de armazenamento do arquivo de log na plataforma Linux

`log_file_archive_count`: Arquive quando o número de arquivos de log exceder este tamanho

`log_file_archive_size`: Arquivo quando o tamanho total (bytes) do arquivo de log excede esse tamanho

### Conteúdo relacionado à porta de configuração de porta
`server_port`: porta de escuta TCP do servidor

`server_signal_port`: porta de escuta UDP do servidor

`client_signal_port`: porta de escuta UDP do cliente