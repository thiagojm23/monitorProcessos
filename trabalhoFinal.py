import psutil
import time
import os
import threading
import sys
import msvcrt

# --- Configurações e Variáveis Globais ---
DADOS_PROCESSOS_COMPARTILHADOS = []
LOCK_DADOS = threading.Lock()
CONTINUAR_EXECUCAO = True
PID_MONITORAMENTO_DETALHADO = None
DADOS_MONITORAMENTO_DETALHADO = {}
PICOS_MEMORIA_MB = {}  # Nova variável global para picos de memória
NUM_ATUALIZACOES = 0

# Mapeamento de prioridades para nomes amigáveis (Windows)
# As constantes reais de psutil são usadas ao definir.
PRIORIDADES_WINDOWS_MAP = {
    psutil.REALTIME_PRIORITY_CLASS: "Tempo Real",
    psutil.HIGH_PRIORITY_CLASS: "Alta",
    psutil.ABOVE_NORMAL_PRIORITY_CLASS: "Acima do Normal",
    psutil.NORMAL_PRIORITY_CLASS: "Normal",
    psutil.BELOW_NORMAL_PRIORITY_CLASS: "Abaixo do Normal",
    psutil.IDLE_PRIORITY_CLASS: "Ociosa",
}
# Esta implementação foca mais no modelo Windows para as classes de prioridade nomeadas.


def limpar_tela():
    global NUM_ATUALIZACOES
    NUM_ATUALIZACOES += 1
    """Limpa o terminal."""
    os.system("cls")
    print("Num atualizacoes: ", NUM_ATUALIZACOES)


def obter_nome_prioridade_windows(pid):
    """Retorna o nome amigável da prioridade para Windows."""
    if os.name == "nt":
        try:
            p = psutil.Process(pid)
            return PRIORIDADES_WINDOWS_MAP.get(p.nice(), "Desconhecida")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return "N/A"


# --- Thread de Coleta de Dados ---
def thread_coleta_dados():
    """Thread que coleta informações dos processos periodicamente."""
    global DADOS_PROCESSOS_COMPARTILHADOS, CONTINUAR_EXECUCAO, PID_MONITORAMENTO_DETALHADO, DADOS_MONITORAMENTO_DETALHADO, PICOS_MEMORIA_MB
    script_pid = os.getpid()  # Obtém o PID do script atual

    while CONTINUAR_EXECUCAO:
        lista_temp_processos = []

        # 1. Coleta todos os outros processos
        outros_processos_candidatos_info = []
        for p_obj in psutil.process_iter(
            ["pid", "name", "memory_info", "cpu_percent", "num_threads", "cmdline"]
        ):
            try:
                info = p_obj.info  # Acessa o atributo .info
                if info["pid"] == script_pid:
                    continue  # Pula o próprio script nesta parte da coleta
                outros_processos_candidatos_info.append(info)
            except (
                psutil.NoSuchProcess,
                psutil.AccessDenied,
                TypeError,
                AttributeError,
            ):
                # O processo pode ter terminado, acesso negado ou informações incompletas durante a iteração
                continue

        # 2. Ordena os outros processos por memória e pega os top 20
        processos_para_exibir_info = sorted(
            outros_processos_candidatos_info,
            key=lambda p_info: (
                p_info["memory_info"].rss if p_info.get("memory_info") else 0
            ),
            reverse=True,
        )[:20]

        # 3. Processa esses top 20 outros processos
        for info in processos_para_exibir_info:
            try:
                pid = info["pid"]
                mem_info_obj = info.get("memory_info")
                mem_rss_mb = mem_info_obj.rss / (1024 * 1024) if mem_info_obj else 0
                mem_vms_mb = (  # Adicionado para memória virtual
                    mem_info_obj.vms / (1024 * 1024) if mem_info_obj else 0
                )

                PICOS_MEMORIA_MB[pid] = max(PICOS_MEMORIA_MB.get(pid, 0), mem_rss_mb)
                pico_mem_rss_mb_atual = PICOS_MEMORIA_MB[pid]

                cpu_percent_val = (
                    info["cpu_percent"] if info.get("cpu_percent") is not None else 0.0
                )
                num_threads_val = (
                    info["num_threads"]
                    if info.get("num_threads") is not None
                    else "N/A"
                )

                detalhes_processo = "N/A"
                process_name = info.get("name", "")
                if process_name and process_name.lower() == "chrome.exe":
                    cmdline = info.get("cmdline")
                    if cmdline:
                        is_renderer = any("--type=renderer" in arg for arg in cmdline)
                        is_gpu = any("--type=gpu-process" in arg for arg in cmdline)
                        is_utility = any("--type=utility" in arg for arg in cmdline)
                        is_extension = any(
                            "--extension-process" in arg for arg in cmdline
                        )

                        if is_renderer:
                            detalhes_processo = "Chrome Tab/Ext"
                            for arg in cmdline:
                                if arg.startswith("http:") or arg.startswith("https"):
                                    url_part = arg.split("?")[0]
                                    if len(url_part) > 18:
                                        url_part = url_part[:15] + "..."

                                    detalhes_processo += f": {url_part}"
                                    break
                                elif "--app-id=" in arg:
                                    app_id = arg.split("=")[1]
                                    detalhes_processo += f": App({app_id[:10]})"
                                    break
                        elif is_gpu:
                            detalhes_processo = "Chrome GPU"
                        elif is_extension:
                            detalhes_processo = "Chrome Extension"
                        elif is_utility:
                            detalhes_processo = "Chrome Utility"
                            if any(
                                "--service-sandbox-type=network" in arg
                                for arg in cmdline
                            ):
                                detalhes_processo = "Chrome Network Service"
                            elif any("crashpad-handler" in arg for arg in cmdline):
                                detalhes_processo = "Chrome Crashpad"
                        elif not any(
                            arg.startswith("--type=") for arg in cmdline
                        ) and not any(
                            arg.startswith("--extension-process") for arg in cmdline
                        ):
                            try:
                                parent_proc = psutil.Process(pid)
                                children = parent_proc.children(recursive=False)
                                if any(
                                    child.name().lower() == "chrome.exe"
                                    for child in children
                                ):
                                    detalhes_processo = "Chrome Principal"
                                else:
                                    detalhes_processo = "Chrome (Outro)"
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                detalhes_processo = "Chrome (Principal?)"
                        else:
                            detalhes_processo = "Chrome (Outro)"
                    else:
                        detalhes_processo = "Chrome (sem cmdline)"

                lista_temp_processos.append(
                    {
                        "pid": pid,
                        "nome": process_name,
                        "mem_rss_mb": mem_rss_mb,
                        "mem_vms_mb": mem_vms_mb,
                        "pico_mem_rss_mb": pico_mem_rss_mb_atual,
                        "cpu_percent": cpu_percent_val,
                        "prioridade_nome": obter_nome_prioridade_windows(pid),
                        "num_threads": num_threads_val,
                        "detalhes_processo": detalhes_processo,
                    }
                )
            except (TypeError, AttributeError, KeyError) as e:
                # print(f"Pulando processo devido a erro: {e} - Info: {info}") # Debug opcional
                continue

        # 4. Processa o script atual
        try:
            p_script = psutil.Process(script_pid)
            script_cpu_val = p_script.cpu_percent(interval=None)
            script_mem_info = p_script.memory_info()
            mem_rss_mb_script = (
                script_mem_info.rss / (1024 * 1024) if script_mem_info else 0
            )
            mem_vms_mb_script = (
                script_mem_info.vms / (1024 * 1024) if script_mem_info else 0
            )

            PICOS_MEMORIA_MB[script_pid] = max(
                PICOS_MEMORIA_MB.get(script_pid, 0), mem_rss_mb_script
            )
            pico_mem_script_atual = PICOS_MEMORIA_MB[script_pid]

            lista_temp_processos.append(
                {
                    "pid": script_pid,
                    "nome": p_script.name(),
                    "mem_rss_mb": mem_rss_mb_script,
                    "mem_vms_mb": mem_vms_mb_script,
                    "pico_mem_rss_mb": pico_mem_script_atual,
                    "cpu_percent": (
                        script_cpu_val if script_cpu_val is not None else 0.0
                    ),
                    "prioridade_nome": obter_nome_prioridade_windows(script_pid),
                    "num_threads": p_script.num_threads(),
                    "detalhes_processo": "Este Script Python :)",
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
            # O processo do próprio script não pôde ser acessado (deve ser raro)
            pass

        # 5. Atualiza os dados compartilhados
        with LOCK_DADOS:
            DADOS_PROCESSOS_COMPARTILHADOS = lista_temp_processos
            # Se houver um PID para monitoramento detalhado (lógica permanece a mesma)
            if PID_MONITORAMENTO_DETALHADO:
                try:
                    proc_detalhe = psutil.Process(PID_MONITORAMENTO_DETALHADO)
                    # É uma boa prática chamar cpu_percent no objeto específico
                    # se você quiser seu uso de CPU relativo à última chamada.
                    proc_detalhe.cpu_percent(interval=None)
                    time.sleep(0.1)  # Intervalo para cpu_percent
                    DADOS_MONITORAMENTO_DETALHADO = {
                        "pid": proc_detalhe.pid,
                        "nome": proc_detalhe.name(),
                        "cpu_percent": proc_detalhe.cpu_percent(interval=None),
                        "mem_rss_mb": proc_detalhe.memory_info().rss / (1024 * 1024),
                        "mem_vms_mb": proc_detalhe.memory_info().vms / (1024 * 1024),
                        "num_threads": proc_detalhe.num_threads(),
                        "status": proc_detalhe.status(),
                        "threads_info": [
                            {
                                "id": t.id,
                                "user_time": t.user_time,
                                "system_time": t.system_time,
                            }
                            for t in proc_detalhe.threads()
                        ],
                    }
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    DADOS_MONITORAMENTO_DETALHADO = {
                        "erro": "Processo não encontrado ou acesso negado."
                    }
        time.sleep(2)


# --- Funções de Interação com Processos ---
def alterar_prioridade_processo(pid):
    limpar_tela()
    print(f"--- Alterar Prioridade do PID: {pid} ---")

    # Lógica para Windows
    print("Prioridades Disponíveis (Windows):")
    opcoes_prioridade = list(PRIORIDADES_WINDOWS_MAP.items())
    for i, (const, nome) in enumerate(opcoes_prioridade):
        print(f"{i+1}. {nome}")
    print("0. Cancelar")

    try:
        escolha = input("Escolha a nova prioridade: ")
        if escolha == "0":
            return
        escolha_idx = int(escolha) - 1
        if 0 <= escolha_idx < len(opcoes_prioridade):
            nova_prioridade_const = opcoes_prioridade[escolha_idx][0]
            p = psutil.Process(pid)
            p.nice(
                nova_prioridade_const
            )  # Em Windows, nice() com constantes de prioridade
            print(
                f"Prioridade do processo {pid} alterada para {opcoes_prioridade[escolha_idx][1]}."
            )
        else:
            print("Opção inválida.")
    except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied) as e:
        print(f"Erro ao alterar prioridade: {e}")
    input("Pressione Enter para continuar...")


def definir_afinidade_processador(pid):
    limpar_tela()
    print(f"--- Definir Afinidade de CPU do PID: {pid} ---")
    try:
        p = psutil.Process(pid)
        num_cpus = psutil.cpu_count()
        if num_cpus is None:
            print("Erro: Não foi possível determinar o número de CPUs.")
            input("Pressione Enter para continuar...")
            return
        print(f"Sistema possui {num_cpus} CPUs (0 a {num_cpus - 1}).")
        afinidade_atual = p.cpu_affinity()
        print(f"Afinidade atual: {afinidade_atual}")

        nova_afinidade_str = input(
            f"Digite os novos núcleos (ex: 0,2 ou 0-3) ou 'c' para cancelar: "
        )
        if nova_afinidade_str.lower() == "c":
            return

        nova_afinidade = []
        if "-" in nova_afinidade_str:
            inicio, fim = map(int, nova_afinidade_str.split("-"))
            nova_afinidade = list(range(inicio, fim + 1))
        else:
            nova_afinidade = [int(x.strip()) for x in nova_afinidade_str.split(",")]

        # Validar CPUs
        for cpu_idx in nova_afinidade:
            if not (0 <= cpu_idx < num_cpus):
                print(f"Índice de CPU inválido: {cpu_idx}")
                input("Pressione Enter para continuar...")
                return

        p.cpu_affinity(nova_afinidade)
        print(f"Afinidade do processo {pid} definida para {nova_afinidade}.")
    except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied) as e:
        print(f"Erro ao definir afinidade: {e}")
    input("Pressione Enter para continuar...")


def encerrar_processo_selecionado(pid):
    limpar_tela()
    print(f"--- Encerrar Processo PID: {pid} ---")
    try:
        p = psutil.Process(pid)
        nome_processo = p.name()
        confirmacao = input(
            f"Tem certeza que deseja encerrar o processo '{nome_processo}' (PID: {pid})? (s/N): "
        ).lower()
        if confirmacao == "s":
            p.terminate()  # Tenta terminar graciosamente
            time.sleep(0.5)  # Dá um tempo para o processo terminar
            if p.is_running():
                print("Processo não encerrou com terminate(), tentando kill()...")
                p.kill()
            print(
                f"Processo {pid} ({nome_processo}) encerrado (ou solicitação enviada)."
            )
        else:
            print("Operação cancelada.")
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        print(f"Erro ao encerrar processo: {e}")
    input("Pressione Enter para continuar...")


def listar_threads_do_processo(pid):
    limpar_tela()
    print(f"--- Threads do Processo PID: {pid} ---")
    try:
        p = psutil.Process(pid)
        print(f"Processo: {p.name()}")
        threads = p.threads()
        if not threads:
            print("Nenhuma thread encontrada ou acesso negado às threads.")
        else:
            print(f"{'ID da Thread':<15} {'User Time':<15} {'System Time':<15}")
            print("-" * 45)
            for thread_info in threads:
                print(
                    f"{thread_info.id:<15} {thread_info.user_time:<15.2f} {thread_info.system_time:<15.2f}"
                )
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        print(f"Erro ao listar threads: {e}")
    input("Pressione Enter para continuar...")


def obter_input_com_timeout(prompt_text="> ", timeout=5, initial_buffer_str=""):
    """
    Obtém input do usuário com timeout, preservando e exibindo um buffer inicial,
    e permitindo movimento do cursor com as teclas de seta esquerda/direita.
    Retorna (string_final, True_se_timeout_False_se_enter).
    """
    buffer = list(initial_buffer_str)
    cursor_idx = len(buffer)  # Posição do cursor dentro do conteúdo do buffer (base 0)

    # Exibição inicial: prompt + conteúdo atual do buffer
    # O cursor estará naturalmente no final desta impressão inicial.
    sys.stdout.write(prompt_text + "".join(buffer))
    sys.stdout.flush()

    start_time = time.time()
    # Mantém o controle do comprimento da linha exibida anteriormente para limpá-la corretamente
    last_displayed_line_len = len(prompt_text) + len(buffer)

    while True:
        # Verifica se o timeout ocorreu
        if time.time() - start_time > timeout:
            return "".join(buffer), True  # Timeout ocorreu

        # Verifica se uma tecla foi pressionada
        if msvcrt.kbhit():
            char_code = msvcrt.getch()
            needs_redisplay = False

            if (
                char_code == b"\xe0"
            ):  # Prefixo para teclas especiais (como teclas de seta)
                second_char_code = msvcrt.getch()
                if second_char_code == b"K":  # Seta para esquerda
                    cursor_idx = max(0, cursor_idx - 1)
                    needs_redisplay = True
                elif second_char_code == b"M":  # Seta para direita
                    cursor_idx = min(len(buffer), cursor_idx + 1)
                    needs_redisplay = True
                # Outras teclas especiais (Home, End, Del) poderiam ser tratadas aqui
            elif char_code == b"\r":  # Tecla Enter
                sys.stdout.write("\n")  # Pula para a próxima linha no console
                sys.stdout.flush()
                return "".join(buffer), False  # Retorna buffer final e flag de Enter
            elif char_code == b"\x08":  # Tecla Backspace
                if cursor_idx > 0:
                    buffer.pop(cursor_idx - 1)
                    cursor_idx -= 1
                    needs_redisplay = True
            else:  # Caracteres normais
                try:
                    decoded_char = char_code.decode("utf-8", errors="ignore")
                    if decoded_char:  # Se a decodificação resultar em algo
                        buffer.insert(cursor_idx, decoded_char)
                        cursor_idx += 1
                        needs_redisplay = True
                except UnicodeDecodeError:
                    pass  # Ignora caracteres não decodificáveis

            if needs_redisplay:
                # 1. Move o cursor para o início da linha atual do console
                sys.stdout.write("\r")

                # 2. Prepara o novo conteúdo da linha
                current_buffer_str = "".join(buffer)
                full_new_line = prompt_text + current_buffer_str

                # 3. Escreve a nova linha
                sys.stdout.write(full_new_line)

                # 4. Limpa quaisquer caracteres restantes se a nova linha for mais curta que a anterior
                clear_len = last_displayed_line_len - len(full_new_line)
                if clear_len > 0:
                    sys.stdout.write(" " * clear_len)

                # 5. Reposiciona o cursor:
                #    Move de volta para o início da linha, então escreve o conteúdo até o cursor_idx.
                sys.stdout.write("\r")
                sys.stdout.write(prompt_text + "".join(buffer[:cursor_idx]))

                sys.stdout.flush()
                last_displayed_line_len = len(
                    full_new_line
                )  # Atualiza para a próxima iteração

        time.sleep(0.05)  # Evita uso excessivo de CPU


# --- Thread de Interface com Usuário ---
def thread_interface_usuario():
    global CONTINUAR_EXECUCAO, PID_MONITORAMENTO_DETALHADO, DADOS_MONITORAMENTO_DETALHADO
    current_user_input_str = ""

    processo_selecionado_local = None

    while CONTINUAR_EXECUCAO:
        limpar_tela()
        print("--- Monitor de Processos Python ---")
        # Ajuste de largura: Detalhes de 30 para 20. Mem Pico adicionado com 14. Mem Virtual adicionada com 18
        # Nome: 25, Detalhes: 20, Mem (MB): 10, Mem Pico (MB): 15, Mem Virtual (MB): 18
        # Total: 3+7+25+20+10+15+18+8+17+7 = 130. Separador para 137 (considerando espaços).
        print(
            f"{'#':<3} {'PID':<7} {'Nome':<25} {'Detalhes':<20} {'Mem (MB)':<10} {'Mem Pico (MB)':<15} {'Mem Virtual (MB)':<18} {'CPU (%)':<8} {'Prioridade':<17} {'Threads':<7}"
        )
        print("-" * 137)  # Ajustado o separador

        with LOCK_DADOS:
            copia_dados_processos = list(DADOS_PROCESSOS_COMPARTILHADOS)

        if not copia_dados_processos:
            print("Coletando dados...")
        else:
            for i, p_info in enumerate(copia_dados_processos):
                # Ajuste de truncamento para Nome e Detalhes
                nome_display = (p_info["nome"] or "")[:23]
                detalhes_display = (p_info.get("detalhes_processo", "N/A") or "")[:18]

                print(
                    f"{i+1:<3} {p_info['pid']:<7} {nome_display:<25} {detalhes_display:<20} {p_info['mem_rss_mb']:<10.2f} {p_info.get('pico_mem_rss_mb', 0.0):<15.2f} {p_info.get('mem_vms_mb', 0.0):<18.2f} ",
                    end="",
                )
                print(
                    f"{p_info['cpu_percent']:<8.1f} {str(p_info['prioridade_nome']):<17} {str(p_info['num_threads']):<7}"
                )

        print("-" * 137)  # Ajustado o separador

        # Se estiver no modo de monitoramento detalhado
        if PID_MONITORAMENTO_DETALHADO:
            print(
                f"\\n--- Monitoramento Detalhado PID: {PID_MONITORAMENTO_DETALHADO} ---"
            )
            with LOCK_DADOS:
                detalhes = DADOS_MONITORAMENTO_DETALHADO.copy()

            if "erro" in detalhes:
                print(detalhes["erro"])
                PID_MONITORAMENTO_DETALHADO = None  # Para de monitorar se deu erro
            elif detalhes:
                print(
                    f"Nome: {detalhes.get('nome', 'N/A')}, CPU: {detalhes.get('cpu_percent', 0.0):.1f}%, ",
                    end="",
                )
                print(
                    f"Mem: {detalhes.get('mem_rss_mb', 0.0):.2f}MB, Threads: {detalhes.get('num_threads', 'N/A')}, Status: {detalhes.get('status', 'N/A')}"
                )
                # Pseudo-gráfico simples de CPU
                cpu_val = int(detalhes.get("cpu_percent", 0.0))
                barra_cpu = (
                    "["
                    + "#" * (cpu_val // 5)
                    + " " * (20 - (cpu_val // 5))
                    + f"] {cpu_val}%"
                )
                print(f"CPU Usage: {barra_cpu}")
            print("Pressione 'p' para parar monitoramento detalhado.")
            print("-" * 90)

        print("\\nOpções:")
        print("Digite o '#' do processo para interagir, 's' para sair.")
        # A mensagem "Digite o 'Enter' sem digitar nada para atualizar..." é removida pois o refresh é automático.
        if PID_MONITORAMENTO_DETALHADO:
            print("'p' para PARAR monitoramento detalhado.")
        else:
            print("'m <#>' para INICIAR monitoramento detalhado (ex: m 1).")
        try:
            escolha_usuario_str, timed_out = obter_input_com_timeout(
                prompt_text=f"Comando (auto-refresh em 5s): ",
                timeout=5,
                initial_buffer_str=current_user_input_str,
            )

            if timed_out:
                current_user_input_str = escolha_usuario_str  # Preserve buffer
                continue  # Refresh screen
            else:
                # Enter was pressed
                comando_processar = escolha_usuario_str.lower()
                current_user_input_str = ""  # Reset buffer for next command

                if (
                    not comando_processar.strip()
                ):  # User pressed Enter on an empty or whitespace line
                    time.sleep(0.05)  # Pequena pausa antes de redesenhar
                    continue

                if comando_processar == "s":
                    CONTINUAR_EXECUCAO = False
                    break
                elif (
                    comando_processar.startswith("m ")
                    and not PID_MONITORAMENTO_DETALHADO
                ):
                    try:
                        idx_proc_monitorar = int(comando_processar.split(" ")[1]) - 1
                        if 0 <= idx_proc_monitorar < len(copia_dados_processos):
                            PID_MONITORAMENTO_DETALHADO = copia_dados_processos[
                                idx_proc_monitorar
                            ]["pid"]
                            DADOS_MONITORAMENTO_DETALHADO = {}  # Limpa dados antigos
                        else:
                            print("Índice inválido para monitoramento.")
                            time.sleep(1)
                    except (IndexError, ValueError):
                        print("Formato inválido para monitoramento (ex: m 1).")
                        time.sleep(1)
                elif comando_processar == "p" and PID_MONITORAMENTO_DETALHADO:
                    PID_MONITORAMENTO_DETALHADO = None
                    DADOS_MONITORAMENTO_DETALHADO = {}

                elif comando_processar.isdigit():
                    idx_selecionado = int(comando_processar) - 1
                    if 0 <= idx_selecionado < len(copia_dados_processos):
                        processo_selecionado_local = copia_dados_processos[
                            idx_selecionado
                        ]
                        pid_alvo = processo_selecionado_local["pid"]
                        # Menu de Ações para o Processo Selecionado
                        while True:
                            limpar_tela()
                            print(
                                f"--- Ações para PID: {pid_alvo} ({processo_selecionado_local['nome']}) ---"
                            )
                            print("1. Alterar Prioridade")
                            print("2. Definir Afinidade de CPU")
                            print("3. Listar Threads do Processo")
                            print("4. Encerrar Processo")
                            print(
                                "5. Iniciar/Atualizar Monitoramento Detalhado deste Processo"
                            )
                            print("0. Voltar à lista principal")

                            # Input para o menu de ações não precisa de preservação complexa,
                            # pois é uma interação mais direta e curta.
                            # Usamos input() padrão aqui.
                            acao_prompt = f"Escolha uma ação para PID {pid_alvo}: "
                            current_action_input = ""  # Reset for this specific prompt

                            # For this sub-menu, we can use a simpler input or a modified one if needed.
                            # For now, using standard input() for simplicity as it's a nested menu.
                            # If input preservation is also needed here, this part would need similar logic.
                            # However, the main request was for the primary command input.
                            acao = input(acao_prompt)

                            if acao == "1":
                                alterar_prioridade_processo(pid_alvo)
                            elif acao == "2":
                                definir_afinidade_processador(pid_alvo)
                            elif acao == "3":
                                listar_threads_do_processo(pid_alvo)
                            elif acao == "4":
                                encerrar_processo_selecionado(pid_alvo)
                                if not psutil.pid_exists(pid_alvo):
                                    # Se o processo foi encerrado, limpar o input do menu de ação
                                    # e sair do menu de ações para voltar à lista principal.
                                    current_user_input_str = (
                                        ""  # Limpa o input principal também
                                    )
                                    break
                            elif acao == "5":
                                PID_MONITORAMENTO_DETALHADO = pid_alvo
                                DADOS_MONITORAMENTO_DETALHADO = {}
                                print(
                                    f"Monitoramento detalhado iniciado para PID {pid_alvo}. Retornando à tela principal."
                                )
                                current_user_input_str = ""  # Limpa o input principal
                                time.sleep(1.5)
                                break
                            elif acao == "0":
                                break
                            else:
                                print("Opção inválida.")
                                time.sleep(1)
                    else:
                        print("Número do processo inválido.")
                        time.sleep(1)
                else:
                    print("Comando não reconhecido.")
                    time.sleep(1)

        except Exception as e:
            print(f"Ocorreu um erro na interface: {e}")
            time.sleep(2)  # Pausa para o usuário ver o erro
        if PID_MONITORAMENTO_DETALHADO:
            time.sleep(0.3)  # Atualiza mais rápido se monitorando
        else:
            time.sleep(0.5)  # Pequena pausa antes de redesenhar


# --- Ponto de Entrada Principal ---
if __name__ == "__main__":
    print("Iniciando o monitor de processos...")
    print("Lembre-se: para algumas ações (alterar prioridade, afinidade, encerrar),")
    print("o script pode precisar ser executado com privilégios de administrador.")
    print("Pressione Enter para continuar")
    input()

    # Inicializa a primeira chamada de cpu_percent para todos os processos
    # para que os próximos resultados sejam mais precisos.
    for proc in psutil.process_iter():
        try:
            proc.cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass  # Ignora processos que não podem ser acessados

    coletor_thread = threading.Thread(target=thread_coleta_dados)
    interface_thread = threading.Thread(target=thread_interface_usuario)

    coletor_thread.start()
    interface_thread.start()

    coletor_thread.join()
    interface_thread.join()

    print("Monitor de processos finalizado.")
