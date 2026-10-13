import sys
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
BLOG_DIR = TEST_DIR.parent
SCRIPTS_DIR = BLOG_DIR / "scripts"
FIXTURES_DIR = TEST_DIR / "fixtures"

sys.path.insert(0, str(SCRIPTS_DIR))
