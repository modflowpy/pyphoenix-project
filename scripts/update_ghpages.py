#!/usr/bin/env python3
"""Update gh-pages content: sync/execute notebooks or add a dev doc to the TOC.

Default (no flags): sync and re-execute all paired example notebooks.
  For each docs/examples/*.py that has a paired .ipynb:
    1. jupytext --sync <script>      # push py changes into notebook structure
    2. jupyter nbconvert --execute   # re-run all cells and update output

--example: sync/execute a single notebook; creates the .ipynb if it doesn't
  exist yet. Note: a newly created notebook must be added to docs/_toc.yml
  manually (or via --add-dev-doc) before it appears in the published docs.

--add-dev-doc: only update docs/_toc.yml, do not touch notebooks.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
EXAMPLES = DOCS / "examples"
TOC = DOCS / "_toc.yml"


def execute(nb_file: Path) -> bool:
    result = subprocess.run(
        [
            "jupyter",
            "nbconvert",
            "--to",
            "notebook",
            "--execute",
            "--inplace",
            "--ExecutePreprocessor.timeout=1800",
            str(nb_file),
        ],
        env={**os.environ, "MF6_EXTENDED": "1"},
    )
    if result.returncode != 0:
        print("ERROR: nbconvert failed", file=sys.stderr)
        return False
    return True


def sync_and_execute(py_file: Path) -> bool:
    nb_file = py_file.with_suffix(".ipynb")

    print(f"\n--- {py_file.name} ---")
    result = subprocess.run(["jupytext", "--sync", str(py_file)])
    if result.returncode != 0:
        print("ERROR: jupytext --sync failed", file=sys.stderr)
        return False

    return execute(nb_file)


def create_and_execute(py_file: Path) -> bool:
    nb_file = py_file.with_suffix(".ipynb")

    print(f"\n--- {py_file.name} (creating {nb_file.name}) ---")
    result = subprocess.run(["jupytext", "--to", "notebook", str(py_file)])
    if result.returncode != 0:
        print("ERROR: jupytext --to notebook failed", file=sys.stderr)
        return False

    return execute(nb_file)


def add_dev_doc(filename: str) -> None:
    name = filename.removesuffix(".md")
    if name.startswith("dev/"):
        name = name[4:]

    toc_text = TOC.read_text()
    if f"dev/{name}" in toc_text:
        print(f"dev/{name} is already in _toc.yml, skipping.")
        return

    md_file = DOCS / "dev" / f"{name}.md"
    if not md_file.exists():
        print(f"ERROR: {md_file} does not exist.", file=sys.stderr)
        sys.exit(1)

    lines = toc_text.splitlines()
    insert_idx = None
    in_dev_notes = False
    for i, line in enumerate(lines):
        if "Developer Notes" in line:
            in_dev_notes = True
        if in_dev_notes and line.strip().startswith("- file:"):
            insert_idx = i

    if insert_idx is None:
        print("ERROR: Could not find Developer Notes section in _toc.yml", file=sys.stderr)
        sys.exit(1)

    lines.insert(insert_idx + 1, f"      - file: dev/{name}")
    TOC.write_text("\n".join(lines) + "\n")
    print(f"Added dev/{name} to _toc.yml")


def main():
    sys.argv = [sys.argv[0]] + [a for a in sys.argv[1:] if a != "--"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--example",
        metavar="NAME",
        help=(
            "Sync and execute a single example notebook (e.g. twri). "
            "Creates the .ipynb if it does not already exist. "
            "Does not affect other notebooks."
        ),
    )
    parser.add_argument(
        "--add-dev-doc",
        metavar="FILENAME",
        help=(
            "Add a dev doc to _toc.yml under Developer Notes and exit "
            "(e.g. dfn-schema-plan or dfn-schema-plan.md). "
            "Does not sync or execute notebooks."
        ),
    )
    args = parser.parse_args()

    if args.add_dev_doc:
        add_dev_doc(args.add_dev_doc)
        return

    if args.example:
        name = Path(args.example).stem
        py_file = EXAMPLES / f"{name}.py"
        if not py_file.exists():
            print(f"ERROR: {py_file} does not exist.", file=sys.stderr)
            sys.exit(1)
        nb_file = py_file.with_suffix(".ipynb")
        ok = sync_and_execute(py_file) if nb_file.exists() else create_and_execute(py_file)
        if not ok:
            sys.exit(1)
        if not nb_file.exists():
            print(
                f"\nNote: {nb_file.name} is new — add it to docs/_toc.yml to publish it.",
                file=sys.stderr,
            )
        return

    failed = []
    for py_file in sorted(EXAMPLES.glob("*.py")):
        if py_file.with_suffix(".ipynb").exists():
            if not sync_and_execute(py_file):
                failed.append(py_file.name)

    if failed:
        print(f"\nFailed: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)

    print("\nAll notebooks updated.")


if __name__ == "__main__":
    main()
