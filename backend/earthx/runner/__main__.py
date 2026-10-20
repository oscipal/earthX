"""``python -m earthx.runner``: the entrypoint of the image stage ``runner`` (adr/0016 §4.2)."""

import sys

from earthx.runner.cli import main

sys.exit(main())
