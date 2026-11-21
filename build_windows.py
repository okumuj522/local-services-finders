"""Build a Windows desktop folder for Local Services Finder."""

import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent


def main():
    print("Installing the app and Windows build dependencies...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(PROJECT_DIR / "requirements-build.txt")],
        cwd=PROJECT_DIR,
        check=True,
    )
    print("Building Local Services Finder...")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--windowed",
            "--name",
            "Local Services Finder",
            "app.py",
        ],
        cwd=PROJECT_DIR,
        check=True,
    )
    exe_path = PROJECT_DIR / "dist" / "Local Services Finder" / "Local Services Finder.exe"
    print(f"Build complete: {exe_path}")
    print("Run the .exe from the same PowerShell session where your MYSQL_* variables are set.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(f"Build failed with exit code {error.returncode}.")
        raise SystemExit(error.returncode)
