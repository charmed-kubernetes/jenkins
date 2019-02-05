""" Validation tools
"""
import click
import sh
import os
import base64
from pathlib import Path

@click.group()
def cli():
    pass

if __name__ == "__main__":
    cli()
