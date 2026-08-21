"""WSGI entry point for PythonAnywhere.

In the PythonAnywhere **Web** tab, point the "WSGI configuration file" at this
module.  The stock generated file works if you replace its contents with:

    import sys
    path = '/home/YOURUSERNAME/EliteMinus/backend'
    if path not in sys.path:
        sys.path.insert(0, path)

    from wsgi import application     # noqa: F401

Environment variables come from a ``.env`` file in the same directory (loaded by
``config.py``), so no extra configuration is needed in the web UI.
"""
import os
import sys

# Make sure this directory is importable no matter how the server starts us.
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from app import create_app  # noqa: E402

application = create_app()
