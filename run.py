"""V21 launcher: explicit isolated configuration, no startup migration."""
import sys
from scripts.v21 import main
if __name__ == '__main__':
    sys.argv = [sys.argv[0], 'start']
    main()
