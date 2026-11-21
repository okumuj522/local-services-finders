# Local Services Finder

A Python desktop app using Tkinter and MySQL.

## Requirements

- Python 3.10 or newer
- A running MySQL server
- A MySQL database named `local_services` (or set `MYSQL_DATABASE`)

Create the database once in MySQL:

```sql
CREATE DATABASE local_services;
```

The app creates its tables the first time it connects.

## Run from Python

Install the database connector:

```powershell
python -m pip install -r requirements.txt
```

Set the MySQL login for this PowerShell session, then start the app:

```powershell
$env:MYSQL_USER = "root"
$env:MYSQL_PASSWORD = "your-MySQL-password"
python app.py
```

The app also accepts `MYSQL_HOST`, `MYSQL_PORT`, and `MYSQL_DATABASE`. Defaults are `localhost`, `3306`, and `local_services`.

## Build a Windows app

From PowerShell in this folder, run:

```powershell
python build_windows.py
```

The script installs PyInstaller and builds:

```text
dist\Local Services Finder\Local Services Finder.exe
```

Run the executable from the same PowerShell session where the `MYSQL_*` settings are available. The first app launch creates the admin account. Back up the project data regularly using **Backup / restore** in the app.
