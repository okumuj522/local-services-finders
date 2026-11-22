# Local Services Finder

A Python desktop app using Tkinter and MySQL.

Features include provider search, map-selected coordinates and nearby sorting, ratings and reviews, favorites, provider verification, admin password changes, service requests with tracking codes, new-request alerts while the app is open, request privacy consent and deletion, WhatsApp messaging for providers and customers, reports, and database backup/restore.

## Requirements

- Python 3.10 or newer
- A running MySQL server
- A MySQL database named `local_services` (or set `MYSQL_DATABASE`)

Create the database and a limited app account once. Run this from PowerShell and enter your MySQL administrator password when prompted. It is not saved by the setup script:

```powershell
python setup_mysql_user.py
```

The setup creates the `local_services` database and a `local_services_app` account with access only to that database. The app creates its tables the first time it connects.

## Run from Python

Install the database connector:

```powershell
python -m pip install -r requirements.txt
```

Set the app account password you chose during setup for this PowerShell session, then start the app:

```powershell
$env:MYSQL_USER = "local_services_app"
$env:MYSQL_PASSWORD = "your-app-database-password"
$env:MYSQL_DATABASE = "local_services"
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
