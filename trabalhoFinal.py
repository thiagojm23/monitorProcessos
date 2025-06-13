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
# Para Linux/macOS, psutil.Process.nice() usa valores inteiros.
# Esta implementação foca mais no modelo Windows para as classes de prioridade nomeadas.


def limpar_tela():
    """Limpa o terminal."""
    os.system("cls" if os.name == "nt" else "clear")


def obter_nome_prioridade_windows(pid):
    """Retorna o nome amigável da prioridade para Windows."""
    if os.name == "nt":
        try:
            p = psutil.Process(pid)
            return PRIORIDADES_WINDOWS_MAP.get(p.nice(), "Desconhecida")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return "N/A"
    else:  # Linux/macOS
        try:
            p = psutil.Process(pid)
            return f"Nice: {p.nice()}"
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return "N/A"


# --- Thread de Coleta de Dados ---
def thread_coleta_dados():
    """Thread que coleta informações dos processos periodicamente."""
    global DADOS_PROCESSOS_COMPARTILHADOS, CONTINUAR_EXECUCAO, PID_MONITORAMENTO_DETALHADO, DADOS_MONITORAMENTO_DETALHADO

    while CONTINUAR_EXECUCAO:
        lista_temp_processos = []
        # Considerar apenas os top N processos por uso de memória para simplificar a exibição
        processos_ordenados = sorted(
            psutil.process_iter(
                ["pid", "name", "memory_info", "cpu_percent", "num_threads"]
            ),
            key=lambda p: p.info["memory_info"].rss if p.info["memory_info"] else 0,
            reverse=True,
        )

        for p in processos_ordenados[:20]:  # Pega os top 20
            try:
                info = p.info
                mem_rss = (
                    info["memory_info"].rss / (1024 * 1024)
                    if info["memory_info"]
                    else 0
                )  # MB
                cpu_percent = (
                    info["cpu_percent"] if info["cpu_percent"] is not None else 0.0
                )  # Requer chamar uma vez antes para ter valor
                num_threads = (
                    info["num_threads"] if info["num_threads"] is not None else "N/A"
                )

                lista_temp_processos.append(
                    {
                        "pid": info["pid"],
                        "nome": info["name"],
                        "mem_rss_mb": mem_rss,
                        "cpu_percent": cpu_percent,
                        "prioridade_nome": obter_nome_prioridade_windows(info["pid"]),
                        "num_threads": num_threads,
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError):
                # Processo pode ter terminado ou acesso negado
                continue

        with LOCK_DADOS:
            DADOS_PROCESSOS_COMPARTILHADOS = lista_temp_processos

            # Se houver um PID para monitoramento detalhado
            if PID_MONITORAMENTO_DETALHADO:
                try:
                    proc_detalhe = psutil.Process(PID_MONITORAMENTO_DETALHADO)
                    proc_detalhe.cpu_percent(
                        interval=None
                    )  # Chamar para preparar a próxima leitura
                    time.sleep(0.1)  # Pequeno intervalo para cpu_percent funcionar
                    DADOS_MONITORAMENTO_DETALHADO = {
                        "pid": proc_detalhe.pid,
                        "nome": proc_detalhe.name(),
                        "cpu_percent": proc_detalhe.cpu_percent(interval=None),
                        "mem_rss_mb": proc_detalhe.memory_info().rss / (1024 * 1024),
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
                    # PID_MONITORAMENTO_DETALHADO = None # Opcional: parar monitoramento se der erro

        time.sleep(2)  # Intervalo de atualização da lista principal


# --- Funções de Interação com Processos ---
def alterar_prioridade_processo(pid):
    limpar_tela()
    print(f"--- Alterar Prioridade do PID: {pid} ---")
    if os.name != "nt":
        print("Alteração de prioridade via 'nice' (Linux/macOS):")
        try:
            p = psutil.Process(pid)
            atual_nice = p.nice()
            print(f"Valor 'nice' atual: {atual_nice}")
            novo_nice_str = input(
                f"Digite o novo valor 'nice' (ex: -10, 0, 10) ou 'c' para cancelar: "
            )
            if novo_nice_str.lower() == "c":
                return
            novo_nice = int(novo_nice_str)
            p.nice(novo_nice)
            print(f"Prioridade 'nice' do processo {pid} alterada para {novo_nice}.")
        except ValueError:
            print("Valor inválido.")
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            print(f"Erro: {e}")
        input("Pressione Enter para continuar...")
        return

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


def obter_input_com_timeout(prompt="> ", timeout=10):
    """
    Obtém input do usuário com timeout. Usa msvcrt no Windows e select em outros SOs.
    Retorna uma string vazia em caso de timeout.
    """
    print(prompt, end="", flush=True)
    start_time = time.time()
    buffer = []
    while True:
        # Verifica se o timeout ocorreu
        if time.time() - start_time > timeout:
            print("\n[Auto-refresh após 10s de inatividade]")
            return ""

        # Verifica se uma tecla foi pressionada
        if msvcrt.kbhit():
            char = msvcrt.getch()
            # Tecla Enter
            if char == b"\r":
                print()  # Pula para a próxima linha no console
                return "".join(buffer)
            # Tecla Backspace
            elif char == b"\x08":
                if buffer:
                    buffer.pop()
                    # Apaga o último caractere da tela
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            # Caracteres normais
            else:
                try:
                    decoded_char = char.decode("utf-8", errors="ignore")
                    buffer.append(decoded_char)
                    sys.stdout.write(decoded_char)
                    sys.stdout.flush()
                except UnicodeDecodeError:
                    pass  # Ignora caracteres não decodificáveis

        time.sleep(0.05)  # Evita uso excessivo de CPU


# --- Thread de Interface com Usuário ---
def thread_interface_usuario():
    global CONTINUAR_EXECUCAO, PID_MONITORAMENTO_DETALHADO, DADOS_MONITORAMENTO_DETALHADO

    processo_selecionado_local = (
        None  # Para manter o processo selecionado entre atualizações
    )

    while CONTINUAR_EXECUCAO:
        limpar_tela()
        print("--- Monitor de Processos Python ---")
        print(
            f"{'#':<3} {'PID':<7} {'Nome':<30} {'Mem (MB)':<10} {'CPU (%)':<8} {'Prioridade':<17} {'Threads':<7}"
        )
        print("-" * 90)

        with LOCK_DADOS:
            copia_dados_processos = list(
                DADOS_PROCESSOS_COMPARTILHADOS
            )  # Faz uma cópia superficial

        if not copia_dados_processos:
            print("Coletando dados...")
        else:
            for i, p_info in enumerate(copia_dados_processos):
                print(
                    f"{i+1:<3} {p_info['pid']:<7} {p_info['nome'][:28]:<30} {p_info['mem_rss_mb']:<10.2f} ",
                    end="",
                )
                print(
                    f"{p_info['cpu_percent']:<8.1f} {str(p_info['prioridade_nome']):<17} {str(p_info['num_threads']):<7}"
                )

        print("-" * 90)

        # Se estiver no modo de monitoramento detalhado
        if PID_MONITORAMENTO_DETALHADO:
            print(
                f"\n--- Monitoramento Detalhado PID: {PID_MONITORAMENTO_DETALHADO} ---"
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

        print("\nOpções:")
        print("Digite o '#' do processo para interagir, 's' para sair.")
        print(
            "Digite o 'Enter' sem digitar nada para atualizar a listagem de processos."
        )
        if PID_MONITORAMENTO_DETALHADO:
            print("'p' para PARAR monitoramento detalhado.")
        else:
            print("'m <#>' para INICIAR monitoramento detalhado (ex: m 1).")

        try:
            print("Aguardando comando (timeout em 10s)...")

            escolha_usuario = obter_input_com_timeout().lower()

            if not escolha_usuario:  # Input vazio, apenas atualiza a tela
                time.sleep(0.5)  # Pequena pausa antes de redesenhar
                continue

            if escolha_usuario == "s":
                CONTINUAR_EXECUCAO = False
                break
            elif escolha_usuario.startswith("m ") and not PID_MONITORAMENTO_DETALHADO:
                try:
                    idx_proc_monitorar = int(escolha_usuario.split(" ")[1]) - 1
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
            elif escolha_usuario == "p" and PID_MONITORAMENTO_DETALHADO:
                PID_MONITORAMENTO_DETALHADO = None
                DADOS_MONITORAMENTO_DETALHADO = {}

            elif escolha_usuario.isdigit():
                idx_selecionado = int(escolha_usuario) - 1
                if 0 <= idx_selecionado < len(copia_dados_processos):
                    processo_selecionado_local = copia_dados_processos[idx_selecionado]
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
                        acao = input("Escolha uma ação: ")

                        if acao == "1":
                            alterar_prioridade_processo(pid_alvo)
                        elif acao == "2":
                            definir_afinidade_processador(pid_alvo)
                        elif acao == "3":
                            listar_threads_do_processo(pid_alvo)
                        elif acao == "4":
                            encerrar_processo_selecionado(pid_alvo)
                            # Se encerrou, sair do menu de ações
                            if not psutil.pid_exists(pid_alvo):
                                break
                        elif acao == "5":
                            PID_MONITORAMENTO_DETALHADO = pid_alvo
                            DADOS_MONITORAMENTO_DETALHADO = {}
                            print(
                                f"Monitoramento detalhado iniciado para PID {pid_alvo}. Retornando à tela principal."
                            )
                            time.sleep(1.5)
                            break  # Volta para a tela principal para ver o monitoramento
                        elif acao == "0":
                            break
                        else:
                            print("Opção inválida.")
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
    time.sleep(2)

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
