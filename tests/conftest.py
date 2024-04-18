import subprocess
import sys

import hatch_protobuf

# Make sure hatch-protobuf is up to date.
# Do this once here, rather than once per test.
subprocess.run(
    [
        sys.executable,
        "-m",
        "pip",
        "cache",
        "remove",
        hatch_protobuf.__name__,
    ],
    check=True,
)
