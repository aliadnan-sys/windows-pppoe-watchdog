# Windows PPPoE Watchdog

A lightweight Python watchdog for Windows that automatically monitors and reconnects a PPPoE connection if it goes down.

## Features

- Automatically checks PPPoE connection status
- Reconnects when the connection drops
- Runs silently in the background
- Can start automatically with Windows
- Stores PPPoE credentials in Windows Credential Manager
- Rotating log files
- Very low CPU usage

## Requirements

- Windows 10 or Windows 11
- Python 3
- pywin32

## Installation

Download or clone this repository.

Place it in:

```text
C:\PPPoE-Watchdog
```

Install the required Python package:

```cmd
python -m pip install -r requirements.txt
```

## Configure Connection Name

Press:

```text
Win + R
```

Run:

```text
ncpa.cpl
```

Find the name of your PPPoE connection.

Then edit this line inside `pppoe_watchdog.py`:

```python
CONNECTION_NAME = "Broadband Connection"
```

Use the exact name of your connection.

## Save PPPoE Credentials

Run:

```cmd
python "C:\PPPoE-Watchdog\pppoe_watchdog.py" --setup
```

Enter your PPPoE username and password.

The password is stored using Windows Credential Manager and is not stored in the Python source code.

## Run Manually

```cmd
python "C:\PPPoE-Watchdog\pppoe_watchdog.py"
```

To run only one check:

```cmd
python "C:\PPPoE-Watchdog\pppoe_watchdog.py" --once
```

## Start Automatically With Windows

Open Task Scheduler:

```text
Win + R
```

Run:

```text
taskschd.msc
```

Create a new task.

### General

```text
Name: PPPoE Watchdog

Run whether user is logged on or not

Run with highest privileges
```

### Trigger

```text
At startup

Delay task for: 1 minute
```

### Find Python Location

Run:

```cmd
python -c "import sys; print(sys.executable)"
```

Example:

```text
C:\Users\User\AppData\Local\Programs\Python\Python313\python.exe
```

Use the same path but replace:

```text
python.exe
```

with:

```text
pythonw.exe
```

### Task Action

Program:

```text
C:\Users\User\AppData\Local\Programs\Python\Python313\pythonw.exe
```

Arguments:

```text
"C:\PPPoE-Watchdog\pppoe_watchdog.py"
```

Start in:

```text
C:\PPPoE-Watchdog
```

### Task Settings

Set:

```text
If the task is already running:
Do not start a new instance
```

Save the task.

Windows may ask for your Windows account password.

After this, the watchdog will start automatically whenever Windows starts.

## Logs

Logs are stored in:

```text
C:\PPPoE-Watchdog\logs\
```

The log files rotate automatically and will not grow forever.

## Security

PPPoE credentials are not stored directly inside the Python script.

Credentials are stored using Windows Credential Manager.

## License

MIT License
