import sys
from pathlib import Path

# Add the signaling-server root to sys.path so 'app' imports resolve correctly
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

# Remove any other 'app' modules that might be in sys.modules
if 'app' in sys.modules:
    del sys.modules['app']
if 'app.main' in sys.modules:
    del sys.modules['app.main']
if 'app.models' in sys.modules:
    del sys.modules['app.models']
if 'app.session_manager' in sys.modules:
    del sys.modules['app.session_manager']
