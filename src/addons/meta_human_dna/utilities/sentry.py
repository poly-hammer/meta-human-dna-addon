# standard library imports
import hashlib
import logging
import os
import sys
import time

from typing import Any

# third party imports
import bpy

# local imports
from ..constants import SENTRY_DSN, ToolInfo
from .misc import get_addon_preferences, get_addon_version


logger = logging.getLogger(__name__)


# --- Sentry client-side deduplication ---
_recent_events: dict[str, float] = {}
_recent_transactions: dict[str, float] = {}
_DEDUP_COOLDOWN_SECONDS = 300.0  # 5 minutes between identical events


def _compute_event_fingerprint(event: dict[str, Any]) -> str:
    """Compute a fingerprint for deduplication of error events."""
    exception = event.get("exception")
    if exception and exception.get("values"):
        parts: list[str] = []
        for exc_val in exception["values"]:
            parts.append(exc_val.get("type", ""))
            parts.append(exc_val.get("value", ""))
            stacktrace = exc_val.get("stacktrace")
            if stacktrace and stacktrace.get("frames"):
                top_frame = stacktrace["frames"][-1]
                parts.append(top_frame.get("filename", ""))
                parts.append(str(top_frame.get("lineno", "")))
        return hashlib.sha256("|".join(parts).encode()).hexdigest()
    return ""


def _is_rate_limited(fingerprint: str, cache: dict[str, float]) -> bool:
    """Check if an event with this fingerprint was recently sent."""
    if not fingerprint:
        return False
    now = time.monotonic()
    last_sent = cache.get(fingerprint)
    if last_sent and (now - last_sent) < _DEDUP_COOLDOWN_SECONDS:
        return True
    cache[fingerprint] = now
    # Prune expired entries
    expired = [k for k, v in cache.items() if (now - v) >= _DEDUP_COOLDOWN_SECONDS]
    for k in expired:
        del cache[k]
    return False


def _event_originates_from_addon(event: dict[str, Any]) -> bool:
    """Check if any exception in the event originated from our addon code."""
    exception = event.get("exception")
    if not exception or not exception.get("values"):
        return False

    for exception_value in exception["values"]:
        stacktrace = exception_value.get("stacktrace")
        if stacktrace and stacktrace.get("frames"):
            # Walk from the top of the stack (where the error was raised) backwards
            # to determine if the error originated in our addon code
            for frame in reversed(stacktrace["frames"]):
                module_name = frame.get("module", "")
                abs_path = frame.get("abs_path", "")
                if module_name and module_name.endswith(ToolInfo.NAME):
                    return True
                if abs_path and ToolInfo.NAME in abs_path:
                    return True
                # Hit a non-addon frame at the top of the stack — error did not originate from us
                if module_name:
                    break
    return False


def init_sentry():
    """Initialize the Sentry SDK for error tracking and performance monitoring."""
    # Don't collect metrics when in dev mode
    if os.environ.get("CHARACTER_DNA_DEV"):
        return

    if not bpy.context.preferences:
        return

    # Don't collect metrics if the user has disabled online access
    if not bpy.app.online_access:
        return

    addon_preferences = get_addon_preferences()
    if not addon_preferences:
        return

    # Don't collect metrics if the user has disabled it
    if not addon_preferences.metrics_collection:
        return

    addon_version = get_addon_version()
    default_tags = {
        "blender_version": bpy.app.version_string,
        "addon_version": addon_version,
        "platform": sys.platform,
    }

    try:
        import sentry_sdk

        from sentry_sdk.types import Event, Hint

        def before_send(event: Event, hint: Hint) -> Event | None:  # noqa: ARG001
            # Filter based on module origin. We only want to send errors related
            # to the Character DNA addon.
            if not _event_originates_from_addon(event):  # type: ignore[arg-type]
                return None

            # Client-side deduplication: skip if we recently sent an identical event
            fingerprint = _compute_event_fingerprint(event)  # type: ignore[arg-type]
            if _is_rate_limited(fingerprint, _recent_events):
                return None

            # Add tags to the event
            if "tags" not in event:
                event["tags"] = default_tags

            event["tags"]["blender_mode"] = bpy.context.mode

            return event

        def before_send_transaction(event: Event, hint: Hint) -> Event | None:  # noqa: ARG001
            # Only send transactions that originate from our addon code
            spans = event.get("spans", [])
            transaction_name = event.get("transaction", "")

            # Check if the transaction name references our addon
            is_addon_transaction = ToolInfo.NAME in transaction_name

            # Check if any span references our addon
            if not is_addon_transaction:
                for span in spans:  # type: ignore[union-attr]
                    description = span.get("description", "")
                    op = span.get("op", "")
                    if ToolInfo.NAME in description or ToolInfo.NAME in op:
                        is_addon_transaction = True
                        break

            if not is_addon_transaction:
                return None

            # Client-side deduplication for transactions
            tx_fingerprint = hashlib.sha256(transaction_name.encode()).hexdigest()
            if _is_rate_limited(tx_fingerprint, _recent_transactions):
                return None

            return event

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            release=addon_version,
            # Set traces_sample_rate to 1.0 to capture 100%
            # of transactions for performance monitoring.
            sample_rate=0.1,
            traces_sample_rate=0.05,
            # Dont send personal identifiable information
            send_default_pii=False,
            # Profiling disabled to reduce server load
            profiles_sample_rate=0.0,
            # Do some client-side filtering to avoid sending
            # events that are not relevant to us.
            before_send=before_send,
            before_send_transaction=before_send_transaction,
        )
        sentry_sdk.metrics.count("addon.initialized", 1, attributes=default_tags)
    except ImportError:
        logger.warning("The sentry-sdk package is not installed. Un-able to use the Sentry error tracking service.")
    except Exception as error:
        logger.error(error)
