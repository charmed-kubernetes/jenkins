""" some helpers to write out html snippets
"""

import os
from pathlib import Path
from jinja2 import Environment, FileSystemLoader


def template(name):
    """Returns a template from jobs/templates/<name>"""
    files_p = str(Path(os.environ.get("WORKSPACE")) / "jobs/templates")
    env = Environment(loader=FileSystemLoader(files_p))
    _tmpl = env.get_template(name)
    return _tmpl
