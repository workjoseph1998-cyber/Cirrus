"""Exercise dependency setup in fresh extracted folders, including spaces."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class WindowsPackageSetup(unittest.TestCase):
    def test_fresh_install_and_repeat_in_folder_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix='cirrus setup test ') as directory:
            root=Path(directory);(root/'scripts').mkdir()
            shutil.copyfile('scripts/install_v21.py',root/'scripts/install_v21.py')
            (root/'requirements.txt').write_text('')
            env=dict(os.environ,PIP_NO_INDEX='1',PIP_DISABLE_PIP_VERSION_CHECK='1')
            for _ in range(2):
                result=subprocess.run([sys.executable,str(root/'scripts/install_v21.py')],env=env,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            python=root/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
            self.assertTrue(python.is_file())

    def test_missing_release_files_fail_without_creating_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'scripts').mkdir()
            shutil.copyfile('scripts/install_v21.py',root/'scripts/install_v21.py')
            result=subprocess.run([sys.executable,str(root/'scripts/install_v21.py')],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('requirements.txt is missing',result.stderr)
            self.assertFalse((root/'.venv').exists())
