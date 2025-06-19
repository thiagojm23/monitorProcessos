# Monitor de Processos Python Avançado para Windows

## Executável está dentro da pasta dist (rodar como adm)

## Descrição

Este é um script Python avançado para monitoramento e interação com processos do sistema operacional Windows em tempo real, diretamente do terminal. Ele foi projetado para fornecer uma visão detalhada dos processos em execução, similar ao Gerenciador de Tarefas do Windows, mas com funcionalidades adicionais e uma interface de usuário interativa no console.

O script utiliza a biblioteca `psutil` para coletar informações dos processos e `threading` para realizar a coleta de dados e a atualização da interface de forma assíncrona, garantindo que a UI permaneça responsiva.

## Funcionalidades Principais

*   **Listagem de Processos em Tempo Real:** Exibe uma lista dos processos que mais consomem memória, atualizada automaticamente a cada 5 segundos.
*   **Informações Detalhadas por Processo:**
    *   PID (ID do Processo)
    *   Nome do Processo
    *   Uso de Memória RAM (MB) = RSS (Resident Set Size)
    *   Pico de Uso de Memória RAM (MB) desde o início do monitoramento
    *   Uso de Memória Virtual (MB) = VMS (Virtual Memory Size)
    *   Uso de CPU (%)
    *   Prioridade do Processo (com nomes amigáveis para Windows)
    *   Número de Threads
    *   **Detalhes Específicos (para Chrome):** Identifica processos do Google Chrome, distinguindo entre o processo principal, abas (com tentativa de extrair URL ou App ID), processos de GPU e utilitários.
*   **Monitoramento do Próprio Script:** O script se auto-monitora, aparecendo fixo na lista (após os 20 principais) para avaliação de seu próprio consumo de recursos.
*   **Interface Interativa no Console (Windows):**
    *   **Preservação de Input:** O campo de comando preserva o texto digitado mesmo durante as atualizações automáticas da tela.
    *   **Navegação no Input:** Suporte para teclas de seta (esquerda/direita) para movimentar o cursor no campo de comando.
    *   **Comandos Intuitivos:** Permite selecionar processos pelo número na lista para realizar ações.
*   **Ações Interativas sobre Processos (Windows):**
    *   **Alterar Prioridade:** Modifica a prioridade de um processo selecionado.
    *   **Definir Afinidade de CPU:** Define em quais núcleos da CPU um processo selecionado pode ser executado.
    *   **Listar Threads:** Exibe informações sobre as threads de um processo selecionado (ID, tempo de usuário, tempo de sistema).
    *   **Encerrar Processo:** Permite encerrar um processo selecionado (com tentativa de terminação graciosa e, se necessário, forçada).
    *   **Monitoramento Detalhado:** Inicia um modo de monitoramento focado em um único processo, exibindo informações adicionais como status, uso de memória RAM e Virtual, e um pseudo-gráfico de uso de CPU.
*   **Foco no Windows:**
    *   Utiliza `os.system("cls")` para limpar a tela.
    *   A leitura de input com timeout e teclas especiais usa `msvcrt`.
    *   O mapeamento de prioridades é específico para as constantes do Windows.

## Requisitos

*   Python 3.x (para Windows)
*   `psutil`: Biblioteca para obter informações do sistema e dos processos.
    ```bash
    pip install psutil
    ```

## Como Executar

1.  Certifique-se de ter o Python e a biblioteca `psutil` instalados no seu ambiente Windows.
2.  Salve o código como um arquivo Python (ex: `monitor_processos_windows.py`).
3.  Execute o script a partir do terminal (Prompt de Comando ou PowerShell):
    ```bash
    python monitor_processos_windows.py
    ```
4.  **Observação:** Para realizar algumas ações como alterar prioridade, definir afinidade ou encerrar certos processos, pode ser necessário executar o script com privilégios de administrador (clique com o botão direito no Prompt de Comando/PowerShell e selecione "Executar como administrador").

## Uso da Interface

Ao iniciar, o script exibirá uma tabela com os processos. Abaixo da tabela, você encontrará as opções de comando:

*   **Entrada de Comando:** Um prompt `Comando (auto-refresh em 5s):` aparecerá.
    *   A tela e a lista de processos serão atualizadas automaticamente a cada 5 segundos.
    *   O que você estiver digitando no campo de comando será preservado durante essas atualizações.
    *   Use as setas Esquerda/Direita para mover o cursor no texto que está digitando.
*   **Selecionar Processo:** Digite o número (`#`) correspondente ao processo na lista e pressione Enter. Isso abrirá um menu de ações para o processo selecionado.
*   **Menu de Ações do Processo:**
    1.  `Alterar Prioridade`
    2.  `Definir Afinidade de CPU`
    3.  `Listar Threads do Processo`
    4.  `Encerrar Processo`
    5.  `Iniciar/Atualizar Monitoramento Detalhado deste Processo`
    0.  `Voltar à lista principal`
*   **Monitoramento Detalhado:**
    *   Para iniciar: Digite `m <#>` (ex: `m 1`) e pressione Enter.
    *   Para parar: Digite `p` e pressione Enter.
*   **Sair:** Digite `s` e pressione Enter.

## Componentes Chave do Código

*   **`thread_coleta_dados()`:** Uma thread dedicada que roda em segundo plano, coletando e atualizando as informações dos processos a cada 2 segundos. Ela também gerencia os picos de memória, a memória virtual e os detalhes específicos do Chrome.
*   **`thread_interface_usuario()`:** A thread principal da interface do usuário. Ela é responsável por:
    *   Limpar a tela e redesenhar a tabela de processos e o menu.
    *   Chamar `obter_input_com_timeout()` para capturar a entrada do usuário.
    *   Processar os comandos do usuário e invocar as funções de ação apropriadas.
*   **`obter_input_com_timeout()`:** Função customizada para leitura de input do console com as seguintes características:
    *   Timeout para permitir o refresh automático da tela.
    *   Preservação do buffer de input entre os timeouts.
    *   Manipulação de teclas de seta (esquerda/direita) e backspace.
    *   Uso de `msvcrt` para detecção de teclas não bloqueante no Windows.
*   **Funções de Ação (`alterar_prioridade_processo`, `definir_afinidade_processador`, etc.):** Funções específicas que são chamadas para interagir com os processos selecionados.
*   **Variáveis Globais e Locks:**
    *   `DADOS_PROCESSOS_COMPARTILHADOS`: Lista compartilhada entre as threads contendo os dados dos processos a serem exibidos (incluindo memória RSS e VMS).
    *   `PICOS_MEMORIA_MB`: Dicionário para rastrear o uso máximo de memória RSS por PID.
    *   `LOCK_DADOS`: Um `threading.Lock()` para sincronizar o acesso a `DADOS_PROCESSOS_COMPARTILHADOS` e `DADOS_MONITORAMENTO_DETALHADO`.
    *   `CONTINUAR_EXECUCAO`: Flag booleana para controlar o loop principal das threads.
    *   `PID_MONITORAMENTO_DETALHADO` e `DADOS_MONITORAMENTO_DETALHADO`: Para o modo de monitoramento detalhado.
