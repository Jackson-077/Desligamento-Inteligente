#!/usr/bin/env python3
# ==========================================================
# Desligamento Inteligente Pro v1.0
# ==========================================================



import tkinter as tk
from tkinter import ttk, messagebox
import os
import json
import subprocess
import datetime
import threading
import time

CONFIG_DIR = os.path.expanduser("~/.config/desligamento-python")
STATE_FILE = os.path.join(CONFIG_DIR, "state.json")

os.makedirs(CONFIG_DIR, exist_ok=True)
# Caminho do ícone para o pacote .deb ou local
ICON_PATH = "/usr/share/desligamento-inteligente/icon.png"
if not os.path.exists(ICON_PATH):
    ICON_PATH = "icon.png" # Tenta local se não estiver instalado

class DesligamentoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Desligamento Inteligente Pro")
        self.root.geometry("500x480")
        self.root.resizable(False, False)
        
        # Tentar carregar ícone da janela
        try:
            if os.path.exists(ICON_PATH):
                self.icon_img = tk.PhotoImage(file=ICON_PATH)
                self.root.iconphoto(True, self.icon_img)
        except:
            pass

        self.bg_color = "#f8f9fa"
        self.primary_color = "#2c3e50"
        self.accent_color = "#e74c3c"
        self.success_color = "#27ae60"
        self.text_color = "#34495e"
        
        self.root.configure(bg=self.bg_color)
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self.target_time = None
        self.is_running = True
        
        self.setup_ui()
        self.load_state()
        self.refresh_display() # Forçar atualização inicial
        
        self.timer_thread = threading.Thread(target=self.update_timer_loop, daemon=True)
        self.timer_thread.start()

    def setup_ui(self):
        # Header
        header_frame = tk.Frame(self.root, bg=self.primary_color, height=80)
        header_frame.pack(fill="x")
        
        tk.Label(header_frame, text="DESLIGAMENTO INTELIGENTE", font=("Segoe UI", 16, "bold"), 
                 bg=self.primary_color, fg="white", pady=10).pack()
        tk.Label(header_frame, text="Painel de Controle Profissional v1.0", font=("Segoe UI", 9),
                 bg=self.primary_color, fg="#bdc3c7").pack(pady=(0, 10))

        # Painel de Status
        status_frame = tk.LabelFrame(self.root, text=" Monitoramento ", font=("Segoe UI", 10, "bold"), 
                                    bg=self.bg_color, fg=self.primary_color, padx=20, pady=10)
        status_frame.pack(fill="x", padx=20, pady=15)

        self.lbl_status = tk.Label(status_frame, text="⚪ Aguardando programação...", 
                                  font=("Segoe UI", 11), bg=self.bg_color, fg=self.text_color)
        self.lbl_status.pack(anchor="w")

        self.lbl_horario = tk.Label(status_frame, text="Agendado para: --:--", 
                                   font=("Segoe UI", 11), bg=self.bg_color, fg=self.text_color)
        self.lbl_horario.pack(anchor="w")

        self.lbl_restante = tk.Label(status_frame, text="00:00:00", 
                                    font=("Consolas", 24, "bold"), bg=self.bg_color, fg=self.primary_color)
        self.lbl_restante.pack(pady=10)

        # Programação Rápida
        quick_frame = tk.LabelFrame(self.root, text=" Atalhos Rápidos ", font=("Segoe UI", 10, "bold"), 
                                   bg=self.bg_color, fg=self.primary_color, padx=20, pady=10)
        quick_frame.pack(fill="x", padx=20, pady=5)

        btn_grid = tk.Frame(quick_frame, bg=self.bg_color)
        btn_grid.pack()

        times = [("30 min", 30), ("1h", 60), ("2h", 120), ("4h", 240)]
        for i, (txt, mins) in enumerate(times):
            btn = tk.Button(btn_grid, text=txt, width=8, command=lambda m=mins: self.programar_relativo(m),
                           bg="#ffffff", activebackground="#dfe6e9", relief="groove", font=("Segoe UI", 9))
            btn.grid(row=0, column=i, padx=5, pady=5)

        # Horário Específico
        manual_frame = tk.LabelFrame(self.root, text=" Agendar Horário ", font=("Segoe UI", 10, "bold"), 
                                    bg=self.bg_color, fg=self.primary_color, padx=20, pady=10)
        manual_frame.pack(fill="x", padx=20, pady=10)

        tk.Label(manual_frame, text="Definir para às:", bg=self.bg_color, font=("Segoe UI", 10)).pack(side="left", padx=5)
        
        self.entry_hora = ttk.Entry(manual_frame, width=10, font=("Segoe UI", 12), justify='center')
        self.entry_hora.pack(side="left", padx=5)
        self.entry_hora.insert(0, datetime.datetime.now().strftime("%H:%M"))

        btn_definir = tk.Button(manual_frame, text="PROGRAMAR", command=self.programar_absoluto,
                               bg=self.primary_color, fg="white", relief="flat", padx=15, font=("Segoe UI", 9, "bold"))
        btn_definir.pack(side="right", padx=10)

        # Rodapé / Ações
        footer_frame = tk.Frame(self.root, bg=self.bg_color)
        footer_frame.pack(fill="x", padx=20, pady=10)

        self.btn_cancelar = tk.Button(footer_frame, text="CANCELAR DESLIGAMENTO", font=("Segoe UI", 10, "bold"),
                                     command=self.cancelar_desligamento, bg="#bdc3c7", fg="white", 
                                     relief="flat", pady=8, state="disabled")
        self.btn_cancelar.pack(fill="x")

    def load_state(self):
        try:
            result = subprocess.run(["busctl", "get-property", "org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager", "ScheduledShutdown"], capture_output=True, text=True)
            if "t" in result.stdout:
                us = int(result.stdout.split()[-1])

                if 0 < us < 18446744073709551615:
                    self.target_time = us / 1_000_000
                    return

            self.target_time = None
        except:
            pass

        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    data = json.load(f)
                    self.target_time = data.get("target_time")
                    if self.target_time and self.target_time <= time.time():
                        self.target_time = None
            except:
                self.target_time = None

    def save_state(self):
        with open(STATE_FILE, 'w') as f:
            json.dump({"target_time": self.target_time}, f)

    def refresh_display(self):
        """Atualiza a interface imediatamente baseada no target_time atual."""
        if self.target_time:
            agora = time.time()
            restante = int(self.target_time - agora)

            if restante <= 0:
                self.target_time = None
                self.save_state()
                self.reset_ui()
                return

            try:
                target_dt = datetime.datetime.fromtimestamp(self.target_time)
            except (OverflowError, ValueError, OSError):
                self.target_time = None
                self.save_state()
                self.reset_ui()
                return

            h = restante // 3600
            m = (restante % 3600) // 60
            s = restante % 60

            horario_str = target_dt.strftime("%H:%M")
            restante_str = f"{h:02d}:{m:02d}:{s:02d}"
            self.update_ui(horario_str, restante_str)
        else:
            self.reset_ui()

    def update_timer_loop(self):
        while self.is_running:
            self.root.after(0, self.refresh_display)
            time.sleep(1)

    def update_ui(self, horario, restante):
        self.lbl_status.config(text="🟢 Sistema Programado", fg=self.success_color)
        self.lbl_horario.config(text=f"Agendado para: {horario}")
        self.lbl_restante.config(text=restante, fg=self.accent_color)
        self.btn_cancelar.config(state="normal", bg=self.accent_color)

    def reset_ui(self):
        self.lbl_status.config(text="⚪ Aguardando programação...", fg=self.text_color)
        self.lbl_horario.config(text="Agendado para: --:--")
        self.lbl_restante.config(text="00:00:00", fg=self.primary_color)
        self.btn_cancelar.config(state="disabled", bg="#bdc3c7")

    def programar_relativo(self, minutos):
        if self.target_time:
            if not messagebox.askyesno("Confirmar", "Deseja substituir o agendamento atual?"):
                return
            subprocess.run(["shutdown", "-c"], capture_output=True)
        
        try:
            subprocess.run(["shutdown", "-h", f"+{minutos}"], check=True, capture_output=True)
            self.target_time = time.time() + (minutos * 60)
            self.save_state()
            self.refresh_display() # Atualizar UI imediatamente
            messagebox.showinfo("Sucesso", f"✅ Desligamento programado para daqui a {minutos} minutos.")
        except Exception:
            messagebox.showerror("Erro", "Erro ao executar. Tente rodar com permissões de administrador (sudo).")

    def programar_absoluto(self):
        horario_str = self.entry_hora.get()
        try:
            h, m = map(int, horario_str.replace('.', ':').split(':'))
            if not (0 <= h <= 23 and 0 <= m <= 59): raise ValueError
            
            agora = datetime.datetime.now()
            alvo = agora.replace(hour=h, minute=m, second=0, microsecond=0)
            if alvo <= agora: alvo += datetime.timedelta(days=1)
            
            if self.target_time:
                if not messagebox.askyesno("Confirmar", "Deseja alterar o horário atual?"): return
                subprocess.run(["shutdown", "-c"], capture_output=True)

            subprocess.run(["shutdown", "-h", f"{h:02d}:{m:02d}"], check=True, capture_output=True)
            self.target_time = alvo.timestamp()
            self.save_state()
            self.refresh_display() # Atualizar UI imediatamente
            messagebox.showinfo("Sucesso", f"✅ Desligamento agendado para às {h:02d}:{m:02d}.")
        except Exception:
            messagebox.showerror("Erro", "Formato inválido! Use HH:MM (ex: 12:55)")

    def cancelar_desligamento(self):
        if messagebox.askyesno("Cancelar", "Tem certeza que deseja cancelar o desligamento?"):
            try:
                subprocess.run(["shutdown", "-c"], check=True)
                self.target_time = None
                self.save_state()
                self.refresh_display() # Atualizar UI imediatamente
                messagebox.showinfo("Cancelado", "Agendamento removido com sucesso.")
            except Exception:
                messagebox.showerror("Erro", "Não foi possível cancelar o agendamento.")

if __name__ == "__main__":
    root = tk.Tk()
    app = DesligamentoApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (setattr(app, 'is_running', False), root.destroy()))
    root.mainloop()
EOF
