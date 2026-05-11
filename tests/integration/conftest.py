import sys
from pathlib import Path

# Make `import config` resolve to demos/config.py, which calls nori.configure()
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "demos"))

import config  # noqa: F401, E402 — side-effect: nori.configure() with grok-4.3
