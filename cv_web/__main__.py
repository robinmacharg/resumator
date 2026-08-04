"""
Architecture role:
- Layer: package execution entrypoint.
- Responsibility: invoke the HTTP server bootstrap when running `python -m cv_web`.

Plain-language purpose:
- This module makes the CV web server runnable as a Python module.
"""

from .server import run_server


if __name__ == "__main__":
    run_server()
