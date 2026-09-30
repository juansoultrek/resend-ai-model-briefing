from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import ValidationError

from ai_model_briefing import __version__
from ai_model_briefing.briefing import BriefingGenerationError, generate_briefing
from ai_model_briefing.collector import CollectionResult, collect_recent_articles
from ai_model_briefing.config import (
    load_generation_settings,
    load_settings,
    load_subscriber_settings,
)
from ai_model_briefing.delivery import DeliveryError, deliver_broadcast
from ai_model_briefing.email import render_email
from ai_model_briefing.sources import SourceConfigurationError, load_source_catalog
from ai_model_briefing.subscribers import (
    SubscriberError,
    subscribe,
    unsubscribe,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-model-briefing",
        description="Generate AI model briefings and deliver them with Resend.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("check", help="Validate local configuration.")
    preview_parser = subparsers.add_parser(
        "preview", help="Generate a local HTML preview without contacting Resend."
    )
    preview_parser.add_argument(
        "--output",
        type=Path,
        default=Path("briefing-preview.html"),
        help="HTML file to write (default: briefing-preview.html).",
    )
    subparsers.add_parser("run", help="Generate and send a briefing with Resend.")
    subscribe_parser = subparsers.add_parser(
        "subscribe", help="Add a consenting contact to the configured Resend Segment."
    )
    subscribe_parser.add_argument("email", help="Contact email address.")
    subscribe_parser.add_argument(
        "--consent-confirmed",
        action="store_true",
        required=True,
        help="Confirm that the contact explicitly agreed to receive this briefing.",
    )
    unsubscribe_parser = subparsers.add_parser(
        "unsubscribe", help="Globally unsubscribe an existing Resend contact."
    )
    unsubscribe_parser.add_argument("email", help="Contact email address.")
    return parser


def check_configuration() -> int:
    try:
        settings = load_settings()
        source_catalog = load_source_catalog(settings.sources_file)
    except (ValidationError, SourceConfigurationError) as error:
        _print_configuration_error(error)
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
    if arguments.command == "preview":
        return execute_preview(arguments.output)
    if arguments.command == "run":
        return execute_run()
    if arguments.command == "subscribe":
        return execute_subscribe(arguments.email, arguments.consent_confirmed)
    if arguments.command == "unsubscribe":
        return execute_unsubscribe(arguments.email)
    parser.print_help()
    return 0


def execute_preview(output_path: Path) -> int:
    try:
        settings = load_generation_settings()
        catalog = load_source_catalog(settings.sources_file)
        collection = collect_recent_articles(catalog, settings.briefing_mode)
        _report_collection(collection)
        briefing = generate_briefing(
            collection.articles,
            settings.briefing_mode,
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )
        email = render_email(briefing)
        _write_preview(output_path, email.html)
    except (ValidationError, SourceConfigurationError) as error:
        _print_configuration_error(error)
        return 2
    except (BriefingGenerationError, OSError) as error:
        print(f"Preview failed: {error}", file=sys.stderr)
        return 1

    print(f"Preview written to {output_path}")
    return 0


def execute_run() -> int:
    try:
        settings = load_settings()
        catalog = load_source_catalog(settings.sources_file)
        collection = collect_recent_articles(catalog, settings.briefing_mode)
        _report_collection(collection)
        briefing = generate_briefing(
            collection.articles,
            settings.briefing_mode,
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )
        email = render_email(briefing)
        receipt = deliver_broadcast(
            email,
            api_key=settings.resend_api_key,
            from_address=settings.resend_from,
            segment_id=settings.resend_segment_id,
            send=True,
        )
    except (ValidationError, SourceConfigurationError) as error:
        _print_configuration_error(error)
        return 2
    except (BriefingGenerationError, DeliveryError) as error:
        print(f"Run failed: {error}", file=sys.stderr)
        return 1

    print(f"Broadcast sent: {receipt.broadcast_id}")
    return 0


def execute_subscribe(email: str, consent_confirmed: bool) -> int:
    try:
        settings = load_subscriber_settings()
        receipt = subscribe(
            email,
            api_key=settings.resend_api_key,
            segment_id=settings.resend_segment_id,
            consent_confirmed=consent_confirmed,
        )
    except ValidationError as error:
        _print_configuration_error(error)
        return 2
    except SubscriberError as error:
        print(f"Subscribe failed: {error}", file=sys.stderr)
        return 1

    print(f"Contact subscribed: {receipt.contact_id}")
    return 0


def execute_unsubscribe(email: str) -> int:
    try:
        settings = load_subscriber_settings()
        receipt = unsubscribe(email, api_key=settings.resend_api_key)
    except ValidationError as error:
        _print_configuration_error(error)
        return 2
    except SubscriberError as error:
        print(f"Unsubscribe failed: {error}", file=sys.stderr)
        return 1

    print(f"Contact unsubscribed: {receipt.contact_id}")
    return 0


def _report_collection(collection: CollectionResult) -> None:
    for issue in collection.issues:
        print(f"Warning: {issue.source_id} failed during {issue.stage}.", file=sys.stderr)


def _print_configuration_error(error: ValidationError | SourceConfigurationError) -> None:
    print("Configuration is invalid:", file=sys.stderr)
    if isinstance(error, ValidationError):
        for issue in error.errors(include_url=False, include_input=False):
            field = ".".join(str(part) for part in issue["loc"])
            print(f"- {field}: {issue['msg']}", file=sys.stderr)
    else:
        print(f"- sources: {error}", file=sys.stderr)


def _write_preview(path: Path, html: str) -> None:
    parent = path.parent.resolve(strict=True)
    target = parent / path.name
    if target.is_dir():
        raise OSError(f"preview path is a directory: {path}")

    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(html)
        temporary_path.chmod(0o600)
        os.replace(temporary_path, target)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
