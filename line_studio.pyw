"""line_studio.pyw  v0.2.0 — запуск LineStudio двойным щелчком (без консоли)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from line_studio import main  # noqa: E402

main()
