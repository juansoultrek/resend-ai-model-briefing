from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from pydantic import ValidationError

from ai_model_briefing import __version__
from ai_model_briefing.config import load_settings
from ai_model_briefing.sources import SourceConfigurationError, load_source_catalog


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-model-briefing",
        description="Generate AI model briefings and deliver them with Resend.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("check", help="Validate local configuration.")
    return parser


def check_configuration() -> int:
    try:
        settings = load_settings()
        source_catalog = load_source_catalog(settings.sources_file)
    except (ValidationError, SourceConfigurationError) as error:
        print("Configuration is invalid:", file=sys.stderr)
        if isinstance(error, ValidationError):
            for issue in error.errors(include_url=False, include_input=False):
                field = ".".join(str(part) for part in issue["loc"])
                print(f"- {field}: {issue['msg']}", file=sys.stderr)
        else:
            print(f"- sources: {error}", file=sys.stderr)
        return 2

    print("Configuration is valid.")
    print(f"OpenAI model: {settings.openai_model}")
    print(f"Resend sender: {settings.resend_from}")
    print(f"Resend Segment: {settings.resend_segment_id}")
    print(f"Briefing mode: {settings.briefing_mode}")
    enabled_sources = sum(source.enabled for source in source_catalog.sources)
    print(f"News sources: {enabled_sources} enabled")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "check":
        return check_configuration()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
