"""Capture one explicit official competition source through the shared lake runtime."""

import argparse
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .cli import resource, timestamp, validate
from .observability import init_sentry, report_exit

# CASSINI publishes a "September - October 2026" window for an EU (Brussels-time)
# programme. As instants: 1 Sep 00:00 CEST (UTC+2) up to 1 Nov 00:00 CET (UTC+1,
# summer time ends 25 Oct 2026). Fixed offsets avoid a tzdata dependency.
CASSINI_WINDOW_OPENS = "2026-09-01T00:00:00+02:00"
CASSINI_WINDOW_ENDS = "2026-11-01T00:00:00+01:00"
# The NASA Space Apps event runs 14-15 November 2026; status stays "open" only
# until the end of 15 November UTC and becomes "unknown" (never "closed") after.
NASA_SPACE_APPS_OPEN_UNTIL = "2026-11-16T00:00:00Z"


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, value):
        if not self.hidden:
            self.parts.append(value)


def _normalize_generic(raw, source, checked_at):
    parser = Text()
    parser.feed(raw.decode("utf-8"))
    text = " ".join(" ".join(parser.parts).split())
    folded = text.casefold()
    markers = source.get("required_markers") or [source["title"]]
    if not all(marker.casefold() in folded for marker in markers):
        raise ValueError("generic competition source drift or challenge page")
    record_id = source["id"]
    item = {
        "id": record_id,
        "title": source["title"],
        "category": source["category"],
        "source_url": source["source_url"],
        "provider": source["provider"],
        "status": source.get("status", "unknown"),
        "deadline": {"kind": source.get("deadline_kind", "unknown"), "at": None},
        "eligible_countries": source.get("eligible_countries", ["GLOBAL"]),
        "eligibility_text": source["eligibility_text"],
        "value": {
            "kind": source.get("value_kind", "unknown"),
            "amount": source.get("value_amount"),
            "currency": source.get("value_currency"),
            "guaranteed": source.get("value_guaranteed"),
        },
        "cost": {"fee_amount": None, "currency": None, "auto_renewal": None, "notes": source["cost_notes"]},
        "terms": {
            "judging_criteria": "Not extracted; review the current official rules before entering.",
            "team_allowed": None,
            "submission_format": "Not extracted; review the current official rules before entering.",
            "ip_terms": "Not extracted; review the current official rules before entering.",
            **source.get("normalized_terms", {}),
        },
        "related_records": [],
        "provenance": {
            "evidence_kind": "captured",
            "source_id": source["id"],
            "source_record_id": record_id,
            "checked_at": checked_at,
            "raw_object_key": None,
            "bronze_manifest_key": None,
        },
    }
    return {
        "schema_version": source["schema_version"],
        "source": source["product"],
        "retrieved_at": checked_at,
        "data_status": "live",
        "items": [item],
    }


def normalize(raw, source, checked_at):
    if source.get("generic_html"):
        return _normalize_generic(raw, source, checked_at)
    if source["id"] not in {"nasa-space-apps-2026", "cassini-challenges-2026"}:
        raise ValueError("unknown competition source")
    parser = Text()
    parser.feed(raw.decode("utf-8"))
    text = " ".join(" ".join(parser.parts).split())
    # Strict RFC3339 with an offset: a naive clock would compare host-local time
    # as if it were UTC (or raise TypeError against the aware window bounds).
    now = timestamp(checked_at)
    if source["id"] == "cassini-challenges-2026":
        required: tuple[str, ...] = (
            "CASSINI Challenges 2026",
            "12 winners get a €100,000 prize award",
            "Technology Readiness Level (TRL) ≥ 5",
            "Commercial Readiness Level (CRL) ≥ 4",
            "September - October 2026",
            "Rules of contest",
        )
        if not all(marker.casefold() in text.casefold() for marker in required):
            raise ValueError("CASSINI source drift or challenge page")
        # The page publishes a September–October application window but no
        # exact timestamp. Keep the deadline unknown rather than inventing one.
        deadline: dict[str, Any] = {"kind": "unknown", "at": None}
        opens, ends = timestamp(CASSINI_WINDOW_OPENS), timestamp(CASSINI_WINDOW_ENDS)
        status = "open" if opens <= now < ends else "unknown"
        title = "CASSINI Challenges 2026"
        countries: list[str] = []
        eligibility = (
            "Space entrepreneurs using EU Space data or technology must meet the "
            "current CASSINI Rules of contest; the published page describes an MVP "
            "threshold of TRL 5 and CRL 4. Verify eligibility, exclusions and the "
            "application window before entering."
        )
        value = {"kind": "cash", "amount": 100000, "currency": "EUR", "guaranteed": False}
        cost = {
            "fee_amount": None,
            "currency": None,
            "auto_renewal": None,
            "notes": "No entry fee is extracted; verify the current Rules of contest before applying.",
        }
        terms = {
            "judging_criteria": "Technological excellence and proven commercial readiness; the page states minimum TRL 5 and CRL 4 for the MVP.",
            "team_allowed": True,
            "submission_format": "Submit an application during the published September–October 2026 window; exact deadline and required materials are defined by the current Rules of contest.",
            "ip_terms": "Intellectual-property, exclusion and award terms are in the official Rules of contest and are not inferred by this adapter.",
        }
    else:
        required = (
            "2026 NASA Space Apps Challenge",
            "Register now",
            "November 14-15, 2026",
            "anyone with an interest in space and science",
        )
        if not all(marker.casefold() in text.casefold() for marker in required):
            raise ValueError("NASA Space Apps source drift or challenge page")

        # The NASA directory confirms registration is open, but does not publish a
        # submission cutoff or prize amount on this page. Keep both unknown rather
        # than turning the event end date into an invented deadline.
        deadline = {"kind": "rolling", "at": None}
        status = "open" if now < timestamp(NASA_SPACE_APPS_OPEN_UNTIL) else "unknown"
        title = "2026 NASA Space Apps Challenge"
        countries = ["GLOBAL"]
        eligibility = "NASA describes this as an open global hackathon for anyone interested in space and science; verify registration and local-event requirements before entering."
        value = {"kind": "unknown", "amount": None, "currency": None, "guaranteed": None}
        cost = {
            "fee_amount": None,
            "currency": None,
            "auto_renewal": None,
            "notes": "The captured directory page does not state an entry fee or prize amount; verify the current participant guide.",
        }
        terms = {
            "judging_criteria": "Projects are evaluated through the NASA Space Apps judging process; detailed criteria are not included on this directory page.",
            "team_allowed": True,
            "submission_format": "Hackathon project submitted through the official Space Apps participant flow during the November 14-15, 2026 event; verify the current guide.",
            "ip_terms": "Intellectual-property and submission-display terms are not stated on this directory page; review the official participant terms before entering.",
        }

    item = {
        "id": source["id"],
        "title": title,
        "category": source["category"],
        "source_url": source["source_url"],
        "provider": source["provider"],
        "status": status,
        "deadline": deadline,
        "eligible_countries": countries,
        "eligibility_text": eligibility,
        "value": value,
        "cost": cost,
        "terms": terms,
        "related_records": [],
        "provenance": {
            "evidence_kind": "captured",
            "source_id": source["id"],
            "source_record_id": source["id"],
            "checked_at": checked_at,
            "raw_object_key": None,
            "bronze_manifest_key": None,
        },
    }
    return {
        "schema_version": source["schema_version"],
        "source": source["product"],
        "retrieved_at": checked_at,
        "data_status": "live",
        "items": [item],
    }


def source_config(source_id=None):
    if source_id is None:
        return resource("source.json")
    if not re.fullmatch(r"[a-z0-9-]+", source_id):
        raise ValueError("invalid source id")
    base = resource("source.json")
    if base["id"] == source_id:
        return base
    try:
        return resource("source-" + source_id + ".json")
    except FileNotFoundError:
        raise ValueError("unknown source id") from None


def main(argv=None):
    selector = argparse.ArgumentParser(add_help=False)
    selector.add_argument("--source-id")
    selected, remaining = selector.parse_known_args(argv)
    root = os.environ.get("SOLO_DATA_LAKE_ROOT")
    if not root:
        print("Set SOLO_DATA_LAKE_ROOT to the local shared capture/lake runtime.", file=sys.stderr)
        return 2
    runtime = Path(root).resolve() / "infra/scripts"
    if not (runtime / "discovery/capture_runtime.py").is_file():
        print("Shared discovery runtime is unavailable.", file=sys.stderr)
        return 2
    sys.path.insert(0, str(runtime))
    from discovery.capture_runtime import VERSION, run

    if VERSION != 1:
        raise RuntimeError("unsupported shared capture runtime")
    source = source_config(selected.source_id)
    sentry = init_sentry(source["id"])
    return report_exit(sentry, source["id"], run(source, normalize, validate, remaining))


if __name__ == "__main__":
    raise SystemExit(main())
