""" Various helpers
"""

from contextlib import contextmanager
import os


@contextmanager
def cd(path):
    old_dir = os.getcwd()
    os.chdir(path)
    yield
    os.chdir(old_dir)
