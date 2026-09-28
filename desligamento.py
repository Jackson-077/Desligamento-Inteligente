#!/usr/bin/env python3
# ==========================================================
# Desligamento Inteligente Pro v1.1
# ==========================================================

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter import font as tkfont

APP_ID = "desligamento-inteligente"
VERSION = "1.3"

CONFIG_DIR = os.path.expanduser("~/.config/desligamento-python")
STATE_FILE = os.path.join(CONFIG_DIR, "state.json")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_CANDIDATES = [
    f"/usr/share/{APP_ID}/icon.png",
    os.path.join(BASE_DIR, "icon.png"),
]

# /usr/sbin nem sempre está no PATH quando o app abre pelo menu (.desktop)
SEARCH_PATH = os.environ.get("PATH", "") + os.pathsep + "/usr/sbin:/sbin:/usr/bin:/bin"

SYNC_EVERY = 5  # segundos entre consultas ao systemd
FORCED_UNIT = "desligamento-inteligente-agendado"  # timer do systemd usado quando há bloqueios


class ShutdownError(Exception):
    """Falha ao executar o comando de desligamento."""


class AuthCancelled(ShutdownError):
    """Usuário fechou/negou a janela de autenticação."""


class InhibitorBlocked(ShutdownError):
    """Algum programa mantém um bloqueio (inhibitor) impedindo o desligamento."""

    def __init__(self, msg, blockers=""):
        super().__init__(msg)
        self.blockers = blockers


# ----------------------------------------------------------
# Camada de sistema (systemd-logind)
# ----------------------------------------------------------
def find_bin(name):
    return shutil.which(name, path=SEARCH_PATH)


def query_scheduled_shutdown():
    """
    Pergunta ao systemd-logind se há desligamento agendado.
    Retorna o timestamp (segundos) ou None. Retorna False se não foi possível consultar.
    """
    busctl = find_bin("busctl")
    if not busctl:
        return False
    try:
        r = subprocess.run(
            [busctl, "get-property", "org.freedesktop.login1", "/org/freedesktop/login1",
             "org.freedesktop.login1.Manager", "ScheduledShutdown"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if r.returncode != 0:
        return False

    # Saída esperada:  (st) "poweroff" 1785000000000000
    m = re.search(r'"([^"]*)"\s+(\d+)', r.stdout)
    if not m:
        return False
    kind, usec = m.group(1), int(m.group(2))
    if kind not in ("poweroff", "halt") or not (0 < usec < 2**63):
        return None
    return usec / 1_000_000


def run_shutdown(args):
    """
    Executa `shutdown` com as opções dadas.
    Tenta como usuário comum; se o systemd negar, tenta de novo via pkexec (polkit).
    """
    exe = find_bin("shutdown")
    if not exe:
        raise ShutdownError("Comando 'shutdown' não encontrado no sistema.")

    first_err = ""
    try:
        r = subprocess.run([exe, *args], capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return
        first_err = (r.stderr or r.stdout).strip()
    except (OSError, subprocess.SubprocessError) as e:
        first_err = str(e)
    if "inhibitor" in first_err.lower():
        raise InhibitorBlocked(first_err, list_blockers())

    pkexec = find_bin("pkexec")
    if not pkexec:
        raise ShutdownError(first_err or "Permissão negada e 'pkexec' não está instalado.")

    try:
        r = subprocess.run([pkexec, exe, *args], capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as e:
        raise ShutdownError(str(e))
    if r.returncode == 0:
        return
    if r.returncode in (126, 127):
        raise AuthCancelled("Autenticação cancelada ou negada.")
    err = (r.stderr or r.stdout).strip() or first_err or "Falha desconhecida."
    if "inhibitor" in err.lower():
        raise InhibitorBlocked(err, list_blockers())
    raise ShutdownError(err)


def _inhibit_rows():
    """Lê `systemd-inhibit --list` usando as posições das colunas do cabeçalho."""
    exe = find_bin("systemd-inhibit")
    if not exe:
        return []
    try:
        r = subprocess.run([exe, "--list", "--no-pager"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return []
    lines = r.stdout.splitlines()
    header = next((ln for ln in lines if ln.startswith("WHO")), None)
    if not header:
        return []
    names = ["WHO", "UID", "USER", "PID", "COMM", "WHAT", "WHY", "MODE"]
    starts = [header.find(n) for n in names]
    if any(x < 0 for x in starts) or starts != sorted(starts):
        return []
    rows = []
    for ln in lines[lines.index(header) + 1:]:
        cells = [ln[a:b].strip() for a, b in zip(starts, starts[1:] + [None])]
        if cells[-1] in ("block", "delay"):
            rows.append(dict(zip(names, cells)))
    return rows


def _gdbus_session(method, path="/org/gnome/SessionManager"):
    gdbus = find_bin("gdbus")
    if not gdbus:
        return ""
    iface = "org.gnome.SessionManager" + (".Inhibitor" if path != "/org/gnome/SessionManager" else "")
    try:
        r = subprocess.run([gdbus, "call", "--session", "--dest", "org.gnome.SessionManager",
                            "--object-path", path, "--method", f"{iface}.{method}"],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def gnome_session_inhibitors():
    """Aplicativos que pediram ao GNOME para não encerrar a sessão (flag 'logout')."""
    out = []
    for path in re.findall(r"'(/org/gnome/SessionManager/Inhibitor\d+)'", _gdbus_session("GetInhibitors")):
        flags = re.search(r"uint32 (\d+)", _gdbus_session("GetFlags", path))
        if not flags or not (int(flags.group(1)) & 1):
            continue
        app = re.search(r"'([^']*)'", _gdbus_session("GetAppId", path))
        why = re.search(r"'([^']*)'", _gdbus_session("GetReason", path))
        out.append("• " + (app.group(1) if app and app.group(1) else "aplicativo desconhecido")
                   + (f" — {why.group(1)}" if why and why.group(1) else ""))
    return out


def list_blockers():
    """Texto com quem está bloqueando o desligamento (mode 'block') agora."""
    linhas = []
    for row in _inhibit_rows():
        if row["MODE"] != "block" or "shutdown" not in row["WHAT"].split(":"):
            continue
        item = f"• {row['COMM']} — {row['WHY']}"
        if row["COMM"].startswith("gnome-session"):
            detalhes = gnome_session_inhibitors()
            item = "• Sessão do GNOME — algum aplicativo aberto pediu para não encerrar" + (
                ":\n    " + "\n    ".join(detalhes) if detalhes else "")
        if item not in linhas:
            linhas.append(item)
    return "\n".join(linhas)


def forced_timer_active():
    sc = find_bin("systemctl")
    if not sc:
        return False
    try:
        return subprocess.run([sc, "is-active", "--quiet", FORCED_UNIT + ".timer"],
                              timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _pkexec_sh(script, *args):
    pkexec, sh = find_bin("pkexec"), find_bin("sh")
    if not pkexec or not sh:
        raise ShutdownError("'pkexec' não está instalado.")
    try:
        r = subprocess.run([pkexec, sh, "-c", script, "sh", *args],
                           capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as e:
        raise ShutdownError(str(e))
    if r.returncode == 0:
        return
    if r.returncode in (126, 127):
        raise AuthCancelled("Autenticação cancelada ou negada.")
    raise ShutdownError((r.stderr or r.stdout).strip() or "Falha desconhecida.")


def schedule_forced(secs):
    """Agenda via timer transitório do systemd, desligando mesmo com bloqueios ativos."""
    sc, sysrun, sd = find_bin("systemctl"), find_bin("systemd-run"), find_bin("shutdown")
    if not (sc and sysrun):
        raise ShutdownError("systemctl/systemd-run não encontrados.")
    script = ('"$1" stop "$2.timer" >/dev/null 2>&1; '
              '[ -n "$5" ] && "$5" -c >/dev/null 2>&1; '
              'exec "$3" --collect --unit="$2" --on-active="$4" '
              '--timer-property=AccuracySec=1s "$1" poweroff -i')
    _pkexec_sh(script, sc, FORCED_UNIT, sysrun, str(int(secs)), sd or "")


def cancel_forced():
    sc = find_bin("systemctl")
    if not sc:
        raise ShutdownError("systemctl não encontrado.")
    _pkexec_sh('"$1" stop "$2.timer"', sc, FORCED_UNIT)


# ----------------------------------------------------------
# Interface
# ----------------------------------------------------------
class DesligamentoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Desligamento Inteligente Pro")
        self.root.geometry("500x500")
        self.root.resizable(False, False)

        self._load_icon()

        self.bg_color = "#f8f9fa"
        self.primary_color = "#2c3e50"
        self.accent_color = "#e74c3c"
        self.success_color = "#27ae60"
        self.text_color = "#34495e"

        families = set(tkfont.families())
        self.font_ui = next((f for f in ("Ubuntu", "Noto Sans", "DejaVu Sans", "Segoe UI")
                             if f in families), "TkDefaultFont")
        self.font_mono = next((f for f in ("Ubuntu Mono", "DejaVu Sans Mono", "Liberation Mono", "Consolas")
                               if f in families), "TkFixedFont")

        self.root.configure(bg=self.bg_color)
        ttk.Style().theme_use("clam")

        self.target_time = None
        self.mode = None  # "logind" (shutdown normal) ou "timer" (ignora bloqueios)
        self.busy = False
        self._ticks = 0

        self.setup_ui()
        self.load_state()
        self.refresh_display()
        self.root.after(1000, self.tick)

    def _load_icon(self):
        for path in ICON_CANDIDATES:
            if os.path.exists(path):
                try:
                    self.icon_img = tk.PhotoImage(file=path)
                    self.root.iconphoto(True, self.icon_img)
                except tk.TclError:
                    pass
                return

    def setup_ui(self):
        f = self.font_ui
        header = tk.Frame(self.root, bg=self.primary_color, height=80)
        header.pack(fill="x")
        tk.Label(header, text="DESLIGAMENTO INTELIGENTE", font=(f, 16, "bold"),
                 bg=self.primary_color, fg="white", pady=10).pack()
        tk.Label(header, text=f"Painel de Controle Profissional v{VERSION}", font=(f, 9),
                 bg=self.primary_color, fg="#bdc3c7").pack(pady=(0, 10))

        status = tk.LabelFrame(self.root, text=" Monitoramento ", font=(f, 10, "bold"),
                               bg=self.bg_color, fg=self.primary_color, padx=20, pady=10)
        status.pack(fill="x", padx=20, pady=15)

        self.lbl_status = tk.Label(status, text="⚪ Aguardando programação...",
                                   font=(f, 11), bg=self.bg_color, fg=self.text_color)
        self.lbl_status.pack(anchor="w")
        self.lbl_horario = tk.Label(status, text="Agendado para: --:--",
                                    font=(f, 11), bg=self.bg_color, fg=self.text_color)
        self.lbl_horario.pack(anchor="w")
        self.lbl_restante = tk.Label(status, text="00:00:00", font=(self.font_mono, 24, "bold"),
                                     bg=self.bg_color, fg=self.primary_color)
        self.lbl_restante.pack(pady=10)

        quick = tk.LabelFrame(self.root, text=" Atalhos Rápidos ", font=(f, 10, "bold"),
                              bg=self.bg_color, fg=self.primary_color, padx=20, pady=10)
        quick.pack(fill="x", padx=20, pady=5)
        grid = tk.Frame(quick, bg=self.bg_color)
        grid.pack()

        self.action_buttons = []
        for i, (txt, mins) in enumerate([("30 min", 30), ("1h", 60), ("2h", 120), ("4h", 240)]):
            btn = tk.Button(grid, text=txt, width=8, command=lambda m=mins: self.programar_relativo(m),
                            bg="#ffffff", activebackground="#dfe6e9", relief="groove", font=(f, 9))
            btn.grid(row=0, column=i, padx=5, pady=5)
            self.action_buttons.append(btn)

        manual = tk.LabelFrame(self.root, text=" Agendar Horário ", font=(f, 10, "bold"),
                               bg=self.bg_color, fg=self.primary_color, padx=20, pady=10)
        manual.pack(fill="x", padx=20, pady=10)
        tk.Label(manual, text="Definir para às:", bg=self.bg_color, font=(f, 10)).pack(side="left", padx=5)

        self.entry_hora = ttk.Entry(manual, width=10, font=(f, 12), justify="center")
        self.entry_hora.pack(side="left", padx=5)
        self.entry_hora.insert(0, datetime.datetime.now().strftime("%H:%M"))
        self.entry_hora.bind("<Return>", lambda e: self.programar_absoluto())

        self.btn_definir = tk.Button(manual, text="PROGRAMAR", command=self.programar_absoluto,
                                     bg=self.primary_color, fg="white", relief="flat", padx=15,
                                     font=(f, 9, "bold"))
        self.btn_definir.pack(side="right", padx=10)
        self.action_buttons.append(self.btn_definir)

        footer = tk.Frame(self.root, bg=self.bg_color)
        footer.pack(fill="x", padx=20, pady=10)
        self.btn_cancelar = tk.Button(footer, text="CANCELAR DESLIGAMENTO", font=(f, 10, "bold"),
                                      command=self.cancelar_desligamento, bg="#bdc3c7", fg="white",
                                      relief="flat", pady=8, state="disabled")
        self.btn_cancelar.pack(fill="x")

    # ------------------------------------------------------
    # Estado
    # ------------------------------------------------------
    def _read_state_file(self):
        try:
            with open(STATE_FILE, "r") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    def load_state(self):
        """A fonte da verdade é o systemd; o arquivo só complementa (timer forçado) ou serve de reserva."""
        ts = query_scheduled_shutdown()
        if ts:
            self.target_time, self.mode = ts, "logind"
            return
        data = self._read_state_file()
        t = data.get("target_time")
        futuro = isinstance(t, (int, float)) and t > time.time()
        if futuro and data.get("forced") and forced_timer_active():
            self.target_time, self.mode = t, "timer"
            return
        if ts is None:  # systemd respondeu: nada agendado
            self.target_time, self.mode = None, None
            return
        # systemd não pôde ser consultado: usa o arquivo
        self.target_time = t if futuro else None
        self.mode = "logind" if futuro else None

    def save_state(self):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            tmp = STATE_FILE + ".tmp"
            with open(tmp, "w") as fh:
                json.dump({"target_time": self.target_time, "forced": self.mode == "timer"}, fh)
            os.replace(tmp, STATE_FILE)
        except OSError:
            pass

    def sync_after_action(self):
        """Depois de agendar/cancelar, confirma no sistema o que realmente ficou valendo."""
        self.load_state()
        self.save_state()
        self.refresh_display()

    # ------------------------------------------------------
    # Atualização da tela (tudo na thread principal)
    # ------------------------------------------------------
    def tick(self):
        self._ticks += 1
        if not self.busy and self._ticks % SYNC_EVERY == 0:
            old = self.target_time
            self.load_state()
            if old != self.target_time:
                self.save_state()
        self.refresh_display()
        self.root.after(1000, self.tick)

    def refresh_display(self):
        if not self.target_time:
            self.reset_ui()
            return
        restante = int(self.target_time - time.time())
        if restante <= 0:
            self.target_time, self.mode = None, None
            self.save_state()
            self.reset_ui()
            return
        try:
            horario = datetime.datetime.fromtimestamp(self.target_time)
        except (OverflowError, ValueError, OSError):
            self.target_time = None
            self.reset_ui()
            return
        if horario.date() != datetime.date.today():
            horario_str = horario.strftime("%H:%M (%d/%m)")
        else:
            horario_str = horario.strftime("%H:%M")
        h, rem = divmod(restante, 3600)
        m, s = divmod(rem, 60)
        self.update_ui(horario_str, f"{h:02d}:{m:02d}:{s:02d}")

    def update_ui(self, horario, restante):
        texto = "🟢 Programado (ignora bloqueios)" if self.mode == "timer" else "🟢 Sistema Programado"
        self.lbl_status.config(text=texto, fg=self.success_color)
        self.lbl_horario.config(text=f"Agendado para: {horario}")
        self.lbl_restante.config(text=restante, fg=self.accent_color)
        self.btn_cancelar.config(state="disabled" if self.busy else "normal", bg=self.accent_color)

    def reset_ui(self):
        self.lbl_status.config(text="⚪ Aguardando programação...", fg=self.text_color)
        self.lbl_horario.config(text="Agendado para: --:--")
        self.lbl_restante.config(text="00:00:00", fg=self.primary_color)
        self.btn_cancelar.config(state="disabled", bg="#bdc3c7")

    # ------------------------------------------------------
    # Execução assíncrona (a janela não trava durante a senha do polkit)
    # ------------------------------------------------------
    def set_busy(self, busy):
        self.busy = busy
        for b in self.action_buttons:
            b.config(state="disabled" if busy else "normal")
        self.refresh_display()

    def run_async(self, work, on_success, on_error):
        self.set_busy(True)
        box = {}

        def worker():
            try:
                work()
                box["ok"] = True
            except Exception as e:  # noqa: BLE001 - repassado para a UI
                box["err"] = e

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            if not box:
                self.root.after(100, poll)
                return
            self.set_busy(False)
            if "ok" in box:
                on_success()
            else:
                on_error(box["err"])

        self.root.after(100, poll)

    def show_error(self, e, titulo_padrao):
        if isinstance(e, AuthCancelled):
            messagebox.showwarning("Cancelado", "Autenticação cancelada. Nada foi alterado.")
            return
        detalhe = str(e).strip()
        msg = titulo_padrao + (f"\n\nDetalhes:\n{detalhe}" if detalhe else "")
        messagebox.showerror("Erro", msg)

    # ------------------------------------------------------
    # Ações
    # ------------------------------------------------------
    def _agendar(self, when_arg, alvo_ts, msg_ok):
        # O systemd substitui um agendamento existente, então não há janela sem proteção.
        def work():
            if forced_timer_active():  # evita sobrar um timer antigo que desligaria depois
                cancel_forced()
            run_shutdown(["-P", when_arg])

        def on_success():
            self.sync_after_action()
            messagebox.showinfo("Sucesso", msg_ok)

        def on_error(e):
            self.sync_after_action()
            if isinstance(e, InhibitorBlocked):
                self._oferecer_forcar(e, alvo_ts, msg_ok)
            else:
                self.show_error(e, "Não foi possível agendar o desligamento.")

        self.run_async(work, on_success, on_error)

    def _oferecer_forcar(self, e, alvo_ts, msg_ok):
        lista = e.blockers or "(não foi possível identificar qual programa)"
        ok = messagebox.askyesno(
            "Desligamento bloqueado",
            "Há programas pedindo ao sistema para não desligar:\n\n"
            f"{lista}\n\n"
            "Agendar mesmo assim, ignorando o bloqueio?\n"
            "Na hora marcada o computador desliga com esses programas abertos "
            "e o que não estiver salvo será perdido.",
            icon="warning", default="no")
        if not ok:
            return

        def on_success():
            self.target_time, self.mode = alvo_ts, "timer"
            self.save_state()
            self.sync_after_action()
            messagebox.showinfo("Sucesso", msg_ok)

        def on_error(err):
            self.sync_after_action()
            self.show_error(err, "Não foi possível agendar o desligamento.")

        self.run_async(lambda: schedule_forced(max(5, int(alvo_ts - time.time()))), on_success, on_error)

    def programar_relativo(self, minutos):
        if self.target_time and not messagebox.askyesno("Confirmar", "Deseja substituir o agendamento atual?"):
            return
        self._agendar(f"+{minutos}", time.time() + minutos * 60,
                      f"✅ Desligamento programado para daqui a {minutos} minutos.")

    def programar_absoluto(self):
        txt = self.entry_hora.get().strip().replace(".", ":")
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", txt)
        if not m or not (0 <= int(m.group(1)) <= 23 and 0 <= int(m.group(2)) <= 59):
            messagebox.showerror("Erro", "Formato inválido! Use HH:MM (ex: 12:55)")
            return
        h, mi = int(m.group(1)), int(m.group(2))

        agora = datetime.datetime.now()
        alvo = agora.replace(hour=h, minute=mi, second=0, microsecond=0)
        if alvo <= agora:
            alvo += datetime.timedelta(days=1)

        if self.target_time and not messagebox.askyesno("Confirmar", "Deseja alterar o horário atual?"):
            return

        # Hoje: "HH:MM" exato. Amanhã: "+minutos" (o systemd só aceita hora do dia ou minutos relativos).
        dia = "hoje" if alvo.date() == agora.date() else "amanhã"
        if dia == "hoje":
            quando = f"{h:02d}:{mi:02d}"
        else:
            quando = f"+{max(1, round((alvo - agora).total_seconds() / 60))}"
        self._agendar(quando, alvo.timestamp(), f"✅ Desligamento agendado para {h:02d}:{mi:02d} ({dia}).")

    def cancelar_desligamento(self):
        if not messagebox.askyesno("Cancelar", "Tem certeza que deseja cancelar o desligamento?"):
            return

        modo = self.mode

        def work():
            if modo == "timer":
                cancel_forced()
            else:
                run_shutdown(["-c"])

        def on_success():
            self.sync_after_action()
            messagebox.showinfo("Cancelado", "Agendamento removido com sucesso.")

        def on_error(e):
            self.sync_after_action()
            self.show_error(e, "Não foi possível cancelar o agendamento.")

        self.run_async(work, on_success, on_error)


def main():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        root = tk.Tk(className=APP_ID)
    except tk.TclError as e:
        print(f"Não foi possível abrir a interface gráfica: {e}", file=sys.stderr)
        sys.exit(1)
    DesligamentoApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
