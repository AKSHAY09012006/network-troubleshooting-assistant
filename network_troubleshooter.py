"""Network Troubleshooting Assistant: guided, read-only checks for your device."""
from __future__ import annotations

import csv
import datetime as dt
import ipaddress
import platform
import queue
import re
import socket
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


class Check:
    def __init__(self, name: str, status: str, details: str, advice: str = "") -> None:
        self.name, self.status, self.details, self.advice = name, status, details, advice


def run_command(args: list[str], timeout: int = 5) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                                errors="replace", shell=False)
        return (result.stdout or "") + (result.stderr or "")
    except (OSError, subprocess.TimeoutExpired):
        return ""


def get_gateway() -> str | None:
    system = platform.system()
    if system == "Windows":
        output = run_command(["ipconfig"])
        for line in output.splitlines():
            if "Default Gateway" in line:
                match = re.search(r"(?:\d{1,3}\.){3}\d{1,3}", line)
                if match and match.group() != "0.0.0.0":
                    return match.group()
    elif system == "Linux":
        output = run_command(["ip", "route", "show", "default"])
        match = re.search(r"\bdefault via ([0-9a-fA-F:.]+)", output)
        if match:
            return match.group(1)
    elif system == "Darwin":
        output = run_command(["route", "-n", "get", "default"])
        match = re.search(r"gateway:\s*([0-9a-fA-F:.]+)", output)
        if match:
            return match.group(1)
    return None


def get_local_addresses() -> list[str]:
    found: set[str] = set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, type=socket.SOCK_DGRAM):
            address = item[4][0].split("%", 1)[0]
            ip = ipaddress.ip_address(address)
            if not ip.is_loopback and not ip.is_link_local:
                found.add(address)
    except OSError:
        pass
    # A UDP route lookup discovers the chosen local interface without sending data.
    for destination in ("1.1.1.1", "2606:4700:4700::1111"):
        sock = socket.socket(socket.AF_INET6 if ":" in destination else socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect((destination, 53))
            found.add(sock.getsockname()[0])
        except OSError:
            pass
        finally:
            sock.close()
    return sorted(found)


def ping(host: str) -> tuple[bool, str]:
    args = ["ping", "-n", "1", "-w", "1500", host] if platform.system() == "Windows" else ["ping", "-c", "1", "-W", "2", host]
    output = run_command(args, timeout=4)
    ok = bool(re.search(r"TTL=|bytes from|time[=<]\s*\d", output, re.IGNORECASE))
    short = next((line.strip() for line in output.splitlines() if re.search(r"TTL=|bytes from|time[=<]", line, re.I)), "")
    return ok, short or ("Reply received." if ok else "No ping reply (the device may block ping).")


def perform_checks() -> list[Check]:
    checks: list[Check] = []
    addresses = get_local_addresses()
    checks.append(Check("This device", "PASS" if addresses else "WARN",
                        ", ".join(addresses) if addresses else "Could not determine a local network address.",
                        "Check that Wi-Fi or Ethernet is enabled." if not addresses else ""))

    gateway = get_gateway()
    checks.append(Check("Default gateway", "PASS" if gateway else "WARN",
                        gateway or "No default gateway was found.",
                        "Reconnect to your router and check the network adapter settings." if not gateway else ""))
    if gateway:
        ok, detail = ping(gateway)
        checks.append(Check("Router response", "PASS" if ok else "WARN", detail,
                            "The router may block ping. If websites work, this warning can be ignored." if not ok else ""))
    else:
        checks.append(Check("Router response", "SKIP", "Skipped because no gateway was found."))

    try:
        results = socket.getaddrinfo("example.com", 443, type=socket.SOCK_STREAM)
        resolved = sorted({entry[4][0] for entry in results})
        checks.append(Check("DNS lookup", "PASS", "example.com resolved to " + ", ".join(resolved[:3])))
    except socket.gaierror as exc:
        checks.append(Check("DNS lookup", "FAIL", f"Name lookup failed: {exc}",
                            "Check router DNS settings, then try reconnecting. A temporary DNS outage is also possible."))

    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=3):
            checks.append(Check("Internet connection", "PASS", "A TCP connection to 1.1.1.1 on port 443 succeeded."))
    except OSError as exc:
        checks.append(Check("Internet connection", "FAIL", f"Could not connect to 1.1.1.1:443 ({exc}).",
                            "Check the router's internet/WAN connection. A firewall may also block this check."))
    return checks


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Network Troubleshooting Assistant")
        self.geometry("850x620")
        self.minsize(760, 540)
        self.configure(bg="#f3f6fa")
        self.results: list[Check] = []
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._build()
        self.after(100, self._poll)

    def _build(self) -> None:
        root = ttk.Frame(self, padding=22)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="Network Troubleshooting Assistant", font=("Segoe UI", 21, "bold")).pack(anchor="w")
        ttk.Label(root, text="A guided health check for this computer's connection.", foreground="#4b5563").pack(anchor="w", pady=(3, 12))
        notice = ttk.LabelFrame(root, text="What this checks", padding=10)
        notice.pack(fill="x", pady=(0, 12))
        ttk.Label(notice, text="Local address • router response • DNS lookup • basic internet reachability\n"
                              "Checks are read-only and do not scan other devices. DNS and internet checks contact public services.",
                  justify="left").pack(anchor="w")
        controls = ttk.Frame(root)
        controls.pack(fill="x", pady=(0, 10))
        self.run_button = ttk.Button(controls, text="Run network check", command=self._start)
        self.run_button.pack(side="left")
        self.save_button = ttk.Button(controls, text="Save report…", command=self._save, state="disabled")
        self.save_button.pack(side="left", padx=8)
        self.status = tk.StringVar(value="Ready. Run checks on this computer or a network you are allowed to use.")
        ttk.Label(controls, textvariable=self.status).pack(side="left", padx=8)

        columns = ("check", "status", "details")
        self.tree = ttk.Treeview(root, columns=columns, show="headings", height=9)
        self.tree.heading("check", text="Check")
        self.tree.heading("status", text="Result")
        self.tree.heading("details", text="Details")
        self.tree.column("check", width=175, stretch=False)
        self.tree.column("status", width=90, stretch=False, anchor="center")
        self.tree.column("details", width=500)
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("PASS", foreground="#166534")
        self.tree.tag_configure("WARN", foreground="#92400e")
        self.tree.tag_configure("FAIL", foreground="#b91c1c")
        self.tree.tag_configure("SKIP", foreground="#6b7280")

        ttk.Label(root, text="Recommended next steps", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(13, 5))
        self.advice = tk.Text(root, height=5, wrap="word", font=("Segoe UI", 10), relief="solid", bd=1,
                              bg="#ffffff", fg="#1f2937", padx=9, pady=7)
        self.advice.pack(fill="x")
        self.advice.configure(state="disabled")

    def _start(self) -> None:
        self.run_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self.status.set("Checking this device…")
        self.tree.delete(*self.tree.get_children())
        self._set_advice("Checks are running. This usually takes a few seconds.")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        try:
            self.events.put(("done", perform_checks()))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _poll(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "done":
                    self.results = value  # type: ignore[assignment]
                    for result in self.results:
                        self.tree.insert("", "end", values=(result.name, result.status, result.details), tags=(result.status,))
                    tips = [f"{r.name}: {r.advice}" for r in self.results if r.advice]
                    if not tips:
                        tips = ["All checks passed. This is a basic connectivity check, not a full security audit."]
                    self._set_advice("\n".join("• " + tip for tip in tips))
                    self.status.set("Check complete.")
                    self.save_button.configure(state="normal")
                    self.run_button.configure(state="normal")
                else:
                    self.status.set("A check could not be completed.")
                    self._set_advice(str(value))
                    self.run_button.configure(state="normal")
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _set_advice(self, text: str) -> None:
        self.advice.configure(state="normal")
        self.advice.delete("1.0", "end")
        self.advice.insert("1.0", text)
        self.advice.configure(state="disabled")

    def _save(self) -> None:
        if not self.results:
            return
        path = filedialog.asksaveasfilename(title="Save network check report", defaultextension=".csv",
                                            filetypes=[("CSV report", "*.csv"), ("Text report", "*.txt")],
                                            initialfile="network_check_report.csv")
        if not path:
            return
        try:
            if path.lower().endswith(".txt"):
                with open(path, "w", encoding="utf-8") as file:
                    file.write("NETWORK TROUBLESHOOTING REPORT\n")
                    file.write(f"Created: {dt.datetime.now().astimezone().isoformat(timespec='seconds')}\n")
                    file.write(f"Computer: {platform.node()} ({platform.system()})\n\n")
                    for item in self.results:
                        file.write(f"{item.name} — {item.status}\n{item.details}\n")
                        if item.advice:
                            file.write(f"Suggested action: {item.advice}\n")
                        file.write("\n")
            else:
                with open(path, "w", newline="", encoding="utf-8-sig") as file:
                    writer = csv.writer(file)
                    writer.writerow(["Created", dt.datetime.now().astimezone().isoformat(timespec="seconds")])
                    writer.writerow(["Computer", platform.node(), "Operating system", platform.system()])
                    writer.writerow([])
                    writer.writerow(["Check", "Result", "Details", "Suggested action"])
                    for item in self.results:
                        writer.writerow([item.name, item.status, item.details, item.advice])
            messagebox.showinfo("Report saved", f"Report saved to:\n{path}", parent=self)
        except OSError as exc:
            messagebox.showerror("Could not save report", str(exc), parent=self)


if __name__ == "__main__":
    App().mainloop()
