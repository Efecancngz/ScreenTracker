import sys
from pathlib import Path

import pytest

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


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """app.main.rate_limiter is a module-level singleton shared by every
    TestClient(app) across the whole test session — without this, one
    test's failed join attempts accumulate into another test's lockout."""
    from app.main import rate_limiter

    rate_limiter.clear()
    yield
    rate_limiter.clear()
