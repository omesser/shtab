from __future__ import absolute_import, print_function

import argparse
import logging
import os
import sys
from importlib import import_module

from . import __version__, complete

log = logging.getLogger(__name__)


def get_main_parser():
    parser = argparse.ArgumentParser(prog="shtab")
    parser.add_argument(
        "parser", help="importable parser (or fuction returning parser)"
    )
    parser.add_argument(
        "--version", action="version", version="%(prog)s " + __version__
    )
    parser.add_argument(
        "-s", "--shell", default="bash", choices=["bash", "zsh"]
    )
    parser.add_argument(
        "--prefix", help="prepended to generated functions to avoid clashes"
    )
    parser.add_argument("--preamble", help="prepended to generated script")
    parser.add_argument(
        "--prog", help="custom program name (overrides `parser.prog`)"
    )
    parser.add_argument(
        "-u",
        "--error-unimportable",
        default=False,
        action="store_true",
        help="raise errors if `parser` is not found in $PYTHONPATH",
    )
    return parser


def main(argv=None):
    parser = get_main_parser()
    args = parser.parse_args(argv)
    log.debug(args)

    module, other_parser = args.parser.rsplit(".", 1)
    if sys.path and sys.path[0]:  # not blank so not searching curdir
        sys.path.insert(1, os.curdir)
    try:
        module = import_module(module)
    except ImportError as err:
        if args.error_unimportable:
            raise
        log.debug(str(err))
        return
    other_parser = getattr(module, other_parser)
    if callable(other_parser):
        other_parser = other_parser()
    if args.prog:
        other_parser.prog = args.prog
    print(
        complete(
            other_parser,
            shell=args.shell,
            root_prefix=args.prefix or args.parser.split(".", 1)[0],
            preamble=args.preamble,
        )
    )
