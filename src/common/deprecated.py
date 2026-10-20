"""Deprecated ``pseudo-*`` console-script aliases (STOMP was formerly PSEUDO).

Each alias warns on stderr and forwards to its ``stomp-*`` replacement.
Remove this module and the alias entries in pyproject.toml in STOMP 0.3.0.
"""
import importlib

import click

ALIASES = {
    "pseudo-debias": ("stomp-debias", "debias.cli:debias_cli"),
    "pseudo-quantify": ("stomp-quantify", "quantify.cli:quantify_cli"),
    "pseudo-analyse": ("stomp-analyse", "analyse.cli:analyse_cli"),
    "pseudo-screen-report": ("stomp-screen-report", "analyse.cli:screen_report_cli"),
}


def _forward(old):
    new, target = ALIASES[old]

    def alias(args=None):
        click.echo(
            f"Warning: '{old}' is deprecated and will be removed in STOMP 0.3.0; "
            f"use '{new}' instead.",
            err=True,
        )
        module, attr = target.split(":")
        command = getattr(importlib.import_module(module), attr)
        command.main(args=args, prog_name=old)

    alias.__name__ = old.replace("-", "_")
    return alias


debias_alias = _forward("pseudo-debias")
quantify_alias = _forward("pseudo-quantify")
analyse_alias = _forward("pseudo-analyse")
screen_report_alias = _forward("pseudo-screen-report")
