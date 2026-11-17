"""Keep the durable-run journal out of the developer's home directory."""

import os
import tempfile

if not os.environ.get("NORI_STATE_PATH"):
    os.environ["NORI_STATE_PATH"] = os.path.join(
        tempfile.mkdtemp(prefix="nori-runs-"), "runs.db"
    )
