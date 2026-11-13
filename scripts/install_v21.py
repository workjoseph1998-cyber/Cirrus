"""Dependency installation for setup.bat, without CMD batch subroutines."""
from pathlib import Path
import subprocess
import sys


def main():
    if sys.version_info < (3, 11):
        raise RuntimeError('Python 3.11 or newer is required. Install Python with the Python launcher.')
    source = Path(__file__).resolve().parents[1]
    requirements = source / 'requirements.txt'
    if not requirements.is_file():
        raise RuntimeError('requirements.txt is missing. Extract the entire V21 ZIP first.')
    windows_python = source / '.venv' / 'Scripts' / 'python.exe'
    native_python = source / '.venv' / 'bin' / 'python'
    python = windows_python if sys.platform == 'win32' else native_python
    if not python.is_file():
        print('Creating the separate V21 Python environment...', flush=True)
        subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(source / '.venv')], check=True)
    subprocess.run([str(python), '-c', 'import sys; print(sys.version); sys.exit(0 if sys.version_info >= (3,11) else 1)'], check=True)
    probe = subprocess.run([str(python), '-m', 'pip', '--version'], capture_output=True)
    if probe.returncode:
        print('Installing pip...', flush=True)
        subprocess.run([str(python), '-m', 'ensurepip', '--upgrade', '--default-pip'], check=True)
    subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(requirements)], check=True)
    print('Dependencies installed. Returning to V21 account setup.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print('V21 dependency setup failed: ' + str(exc), file=sys.stderr)
        sys.exit(1)
