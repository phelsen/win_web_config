import tkinter as tk
from tkinter import ttk, scrolledtext
import subprocess
import threading
import os

def load_services(file_path):
    services = {}
    if not os.path.exists(file_path):
        return services
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
            if name and cmd:
                services[name] = cmd
    return services

def find_bash():
    # Try common Git Bash locations
    possible_paths = [
        r"C:\\Program Files\\Git\\bin\\bash.exe",
        r"C:\\Program Files\\Git\\usr\\bin\\bash.exe",
        r"C:\\Program Files (x86)\\Git\\bin\\bash.exe",
        r"C:\\Program Files (x86)\\Git\\usr\\bin\\bash.exe"
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

class ServiceProcess:
    def __init__(self, name, cmd):
        self.name = name
        self.cmd = cmd
        self.process = None
        self.output = ""
        self.running = False
        self.bash_path = find_bash()

    def start(self):
        if not self.running:
            if not self.bash_path:
                self.output += "[ERROR] Git Bash (bash.exe) not found. Please install Git Bash.\n"
                return
            bash_cmd = normalize_command(self.cmd)
            shell_cmd = [self.bash_path, '-c', bash_cmd]
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
        if self.running and self.process:
            self.process.terminate()
            self.running = False

    def is_running(self):
        return self.running and self.process and self.process.poll() is None

class ServiceManagerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Service Manager")
        self.geometry("700x400")
        services_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "services.txt")
        self.services_def = load_services(services_path)
        self.services = {name: ServiceProcess(name, cmd) for name, cmd in self.services_def.items()}
        self.create_widgets()
        self.after(1000, self.update_status)

    def create_widgets(self):
        notebook = ttk.Notebook(self)
        self.tab1 = ttk.Frame(notebook)
        self.tab2 = ttk.Frame(notebook)
        notebook.add(self.tab1, text="Start Services")
        notebook.add(self.tab2, text="Service Status")
        notebook.pack(expand=1, fill="both")

        # Tab 1: Start Services
        self.check_vars = {}
        # Use link-style buttons for select all/none
        select_all_btn = tk.Label(self.tab1, text="Select All", fg="blue", cursor="hand2")
        select_all_btn.grid(row=0, column=0, padx=5, pady=2, sticky="w")
        select_all_btn.bind("<Button-1>", lambda e: self.select_all())
        select_none_btn = tk.Label(self.tab1, text="Select None", fg="blue", cursor="hand2")
        select_none_btn.grid(row=0, column=1, padx=5, pady=2, sticky="w")
        select_none_btn.bind("<Button-1>", lambda e: self.select_none())

        # Use checkboxes for service selection (multiple can be selected)
        for i, name in enumerate(self.services_def):
            var = tk.BooleanVar(value=True)
            chk = tk.Checkbutton(self.tab1, text=name, variable=var)
            chk.grid(row=i+1, column=0, columnspan=2, sticky="w", padx=10, pady=2)
            self.check_vars[name] = var

        start_btn = tk.Button(self.tab1, text="Start Selected", command=self.start_selected)
        start_btn.grid(row=len(self.services_def)+2, column=0, padx=10, pady=10, sticky="w")

        stop_btn = tk.Button(self.tab1, text="Stop All", command=self.stop_all)
        stop_btn.grid(row=len(self.services_def)+3, column=0, padx=10, pady=10, sticky="w")

        # Tab 2: Service Status
        self.status_tree = ttk.Treeview(self.tab2, columns=("Service", "Status"), show="headings")
        self.status_tree.heading("Service", text="Service")
        self.status_tree.heading("Status", text="Status")
        self.status_tree.column("Service", width=120)
        self.status_tree.column("Status", width=100)
        self.status_tree.pack(side="left", fill="y", padx=10, pady=10)
        self.status_tree.bind("<<TreeviewSelect>>", self.on_service_select)

        self.output_text = scrolledtext.ScrolledText(self.tab2, width=60, height=20, state='normal')
        self.output_text.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        self.output_text.config(state='disabled')
        self.output_text.bind("<1>", lambda event: self.output_text.focus_set())

        for name in self.services_def:
            self.status_tree.insert("", "end", iid=name, values=(name, "Stopped"))

    def select_all(self):
        for var in self.check_vars.values():
            var.set(True)

    def select_none(self):
        for var in self.check_vars.values():
            var.set(False)

    def start_selected(self):
        for name, var in self.check_vars.items():
            if var.get():
                self.services[name].start()

    def stop_all(self):
        for service in self.services.values():
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
            self.output_text.config(state='normal')
            self.output_text.delete(1.0, tk.END)
            self.output_text.insert(tk.END, output)
            self.output_text.config(state='normal')  # Always keep selectable

if __name__ == "__main__":
    app = ServiceManagerApp()
    app.mainloop()
