
import tkinter as tk
from tkinter import ttk, scrolledtext
import subprocess
import threading
import os
import shlex

def load_services(file_path):
    services = {}
    stop_commands = {}
    if not os.path.exists(file_path):
        return services, stop_commands
    with open(file_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ";" not in line:
                continue
            name, cmd = line.split(";", 1)
            name = name.strip()
            cmd = cmd.strip()
            if not name or not cmd:
                continue
            if name.startswith("_"):
                stop_commands[name[1:].strip()] = cmd
            else:
                services[name] = cmd
    return services, stop_commands

def find_bash():
    # Try common Git Bash locations
    possible_paths = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\usr\bin\bash.exe"
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

def win_to_bash_path(win_path):
    # Converts C:\Workdir\bin\mysql_start to /c/Workdir/bin/mysql_start
    drive, rest = os.path.splitdrive(win_path)
    drive_letter = drive.rstrip(':').lower()
    rest = rest.replace('\\', '/')
    if rest.startswith('/'):
        rest = rest[1:]
    return f'/{drive_letter}/{rest}'

def bash_to_win_path(bash_path):
    if len(bash_path) >= 3 and bash_path[0] == "/" and bash_path[2] == "/":
        drive_letter = bash_path[1].upper()
        rest = bash_path[3:]
        return f"{drive_letter}:\\{rest.replace('/', '\\')}"
    return bash_path

def normalize_command(cmd):
    if not cmd:
        return cmd
    parts = cmd.split(None, 1)
    first = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    if len(first) >= 3 and first[1] == ":" and (first[2] == "\\" or first[2] == "/"):
        first = win_to_bash_path(first)
        return f"{first} {rest}".rstrip()
    return cmd

def extract_exe_path(cmd):
    if not cmd:
        return None
    try:
        parts = shlex.split(cmd, posix=True)
    except ValueError:
        parts = cmd.split()
    if not parts:
        return None
    exe = parts[0]
    if exe.startswith("/"):
        exe = bash_to_win_path(exe)
    elif len(exe) >= 3 and exe[1] == ":":
        exe = exe.replace("/", "\\")
    return exe

def escape_powershell_string(value):
    return value.replace("'", "''")

def is_process_running_for_cmd(cmd):
    exe = extract_exe_path(cmd)
    if not exe:
        return False
    exe_name = os.path.basename(exe)
    if not exe_name:
        return False

    if os.path.isabs(exe) and os.path.exists(exe):
        exe_escaped = escape_powershell_string(exe)
        ps_cmd = f"Get-Process | Where-Object {{ $_.Path -eq '{exe_escaped}' }} | Select-Object -First 1"
    else:
        name_no_ext = os.path.splitext(exe_name)[0]
        name_escaped = escape_powershell_string(name_no_ext)
        ps_cmd = f"Get-Process -Name '{name_escaped}' -ErrorAction SilentlyContinue | Select-Object -First 1"

    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False
    )
    return bool(result.stdout.strip())

class ServiceProcess:
    def __init__(self, name, cmd, stop_cmd=None):
        self.name = name
        self.cmd = cmd
        self.stop_cmd = stop_cmd
        self.process = None
        self.output = ""
        self.running = False
        self.bash_path = find_bash()

    def _run_one_shot(self, cmd):
        bash_cmd = normalize_command(cmd)
        shell_cmd = [self.bash_path, "-c", bash_cmd]
        try:
            result = subprocess.run(
                shell_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False
            )
            if result.stdout:
                self.output += result.stdout
        except Exception as exc:
            self.output += f"[ERROR] Failed to run stop command: {exc}\n"

    def start(self):
        if not self.running:
            if not self.bash_path:
                self.output += "[ERROR] Git Bash (bash.exe) not found. Please install Git Bash.\n"
                return
            bash_cmd = normalize_command(self.cmd)
            shell_cmd = [self.bash_path, "-c", bash_cmd]
            self.process = subprocess.Popen(
                shell_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            self.running = True
            threading.Thread(target=self._read_output, daemon=True).start()

    def _read_output(self):
        while self.running and self.process and self.process.poll() is None:
            line = self.process.stdout.readline()
            if line:
                self.output += line
        self.running = False

    def stop(self):
        if not self.bash_path:
            self.output += "[ERROR] Git Bash (bash.exe) not found. Please install Git Bash.\n"
            return
        if self.stop_cmd:
            threading.Thread(target=self._run_one_shot, args=(self.stop_cmd,), daemon=True).start()
        if self.running and self.process:
            self.process.terminate()
            self.running = False

    def is_running(self):
        if self.running and self.process and self.process.poll() is None:
            return True
        return is_process_running_for_cmd(self.cmd)

class ServiceManagerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Service Manager")
        self.geometry("800x500")
        services_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "services.txt")
        self.services_def, self.stop_commands = load_services(services_path)
        self.services = {
            name: ServiceProcess(name, cmd, self.stop_commands.get(name))
            for name, cmd in self.services_def.items()
        }
        self.command_boxes = {}
        self.create_widgets()
        self.after(1000, self.update_status)

    def create_widgets(self):
        notebook = ttk.Notebook(self)
        self.tab1 = ttk.Frame(notebook)
        self.tab2 = ttk.Frame(notebook)
        notebook.add(self.tab1, text="Services")
        notebook.add(self.tab2, text="Service Status")
        notebook.pack(expand=1, fill="both")

        self.tab1.columnconfigure(0, weight=1)

        row = 0
        for name in self.services_def:
            row_frame = ttk.Frame(self.tab1)
            row_frame.grid(row=row, column=0, sticky="w", padx=10, pady=2)

            label = ttk.Label(row_frame, text=name, width=12)
            label.pack(side="left")

            start_btn = ttk.Button(row_frame, text="Start", command=lambda n=name: self.start_service(n))
            start_btn.pack(side="left", padx=5)

            stop_btn = ttk.Button(row_frame, text="Stop", command=lambda n=name: self.stop_service(n))
            stop_btn.pack(side="left", padx=5)

            cmd_box = scrolledtext.ScrolledText(self.tab1, height=2, wrap="word")
            cmd_box.grid(row=row + 1, column=0, sticky="we", padx=20, pady=2)
            cmd_box.insert(tk.END, "")
            self.command_boxes[name] = cmd_box

            row += 2

        # Tab 2: Service Status
        self.status_tree = ttk.Treeview(self.tab2, columns=("Service", "Status"), show="headings")
        self.status_tree.heading("Service", text="Service")
        self.status_tree.heading("Status", text="Status")
        self.status_tree.column("Service", width=120)
        self.status_tree.column("Status", width=100)
        self.status_tree.pack(side="left", fill="y", padx=10, pady=10)
        self.status_tree.bind("<<TreeviewSelect>>", self.on_service_select)

        self.output_text = scrolledtext.ScrolledText(self.tab2, width=60, height=20, state="normal")
        self.output_text.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        self.output_text.config(state="disabled")
        self.output_text.bind("<1>", lambda event: self.output_text.focus_set())

        for name in self.services_def:
            self.status_tree.insert("", "end", iid=name, values=(name, "Stopped"))

    def set_command_box(self, name, cmd):
        box = self.command_boxes.get(name)
        if not box:
            return
        box.delete("1.0", tk.END)
        if cmd:
            box.insert(tk.END, cmd)

    def start_service(self, name):
        service = self.services.get(name)
        if not service:
            return
        cmd = normalize_command(service.cmd)
        self.set_command_box(name, cmd)
        service.start()

    def stop_service(self, name):
        service = self.services.get(name)
        if not service:
            return
        cmd = normalize_command(service.stop_cmd) if service.stop_cmd else "No stop command configured."
        self.set_command_box(name, cmd)
        service.stop()

    def update_status(self):
        for name, service in self.services.items():
            status = "Running" if service.is_running() else "Stopped"
            self.status_tree.set(name, "Status", status)
            self.status_tree.set(name, "Service", name)
        self.after(1000, self.update_status)

    def on_service_select(self, event):
        selected = self.status_tree.selection()
        if selected:
            name = selected[0]
            output = self.services[name].output
            self.output_text.config(state="normal")
            self.output_text.delete(1.0, tk.END)
            self.output_text.insert(tk.END, output)
            self.output_text.config(state="normal")  # Always keep selectable

if __name__ == "__main__":
    app = ServiceManagerApp()
    app.mainloop()
