"""Legacy setup.py for compatibility.

This setup.py is provided for legacy compatibility. All configuration
is handled in pyproject.toml. This file simply defers to setuptools.
"""

from setuptools import setup

if __name__ == "__main__":
    setup()
