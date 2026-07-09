# /// script
# requires-python = ">=3.11"
# dependencies = ["python-dotenv"]
# ///
"""Merge dotenv files and print KEY=VALUE for the requested keys.

Later files override earlier ones (same as the old tail -1 bash merge).
python-dotenv handles quoting/escapes/inline-# correctly, which the old
sed-based parser did not. Keys absent from every file are simply omitted;
the caller decides whether that is an error.

usage: read_env.py --name KEY [--name KEY ...] <env-file> [<env-file> ...]
"""
import argparse

from dotenv import dotenv_values

parser = argparse.ArgumentParser()
parser.add_argument("--name", action="append", required=True, dest="names")
parser.add_argument("files", nargs="+")
args = parser.parse_args()

merged: dict[str, str | None] = {}
for f in args.files:
    merged.update(dotenv_values(f))

for name in args.names:
    value = merged.get(name)
    if value:
        print(f"{name}={value}")
