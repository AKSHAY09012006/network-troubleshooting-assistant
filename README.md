# Network Troubleshooting Assistant

A Python desktop project for **Computer Communication and Network Security (21ECC402P)**. It guides a user through basic troubleshooting of the computer they are using and exports a readable report.

## What it checks

- Local network addresses assigned to this computer
- Default gateway (router) and whether it responds to a single ping
- DNS resolution for `example.com`
- Basic outbound TCP connectivity to `1.1.1.1` on port 443
- Plain-language suggestions and CSV or text report export

The checks do not scan a subnet or enumerate devices. The DNS and internet tests contact public services. A failed ping does not necessarily mean the router is broken because some routers block ping.

## Requirements

- Python 3.10 or later
- Tkinter (included with most Windows Python installations)
- For full results, an active network connection and the system `ping` utility

## Run on Windows

1. Extract the ZIP.
2. Open the extracted `network-troubleshooting-assistant` folder in File Explorer.
3. Click the address bar, type `cmd`, and press Enter.
4. Run `python network_troubleshooter.py` (or `py network_troubleshooter.py`).

## How to use

Click **Run network check** and review the status and suggested next steps. Click **Save report…** to export the results as CSV or text. Run it on your own computer or a network you are permitted to troubleshoot.

## How it works

The desktop interface uses Tkinter. DNS resolution and TCP connectivity use Python's standard `socket` library. Router discovery uses read-only system route information, and the router test invokes one bounded ping. Checks run in a background thread so the interface remains responsive. No credentials are requested and no scan data is sent to a reporting service.

## Limitations

- This is a basic connectivity helper, not a full network or security audit.
- Local address and gateway detection depend on operating-system configuration and may not find every adapter.
- Firewalls, captive portals, VPNs, and DNS filtering can affect results.
- A successful connection does not prove that a network is secure.

## Project files

```text
network-troubleshooting-assistant/
├── network_troubleshooter.py
└── README.md
```
