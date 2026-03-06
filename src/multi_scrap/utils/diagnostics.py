from __future__ import annotations

import re


def classify_error(raw_error: str) -> str:
    lowered = (raw_error or "").casefold()
    if "winerror 5" in lowered or "access is denied" in lowered:
        return "RENDERER_PERMISSION_DENIED"
    if "proxyerror" in lowered or "unable to connect to proxy" in lowered:
        return "PROXY_CONNECTION_FAILED"
    if "connecttimeout" in lowered or "timed out" in lowered:
        return "NETWORK_TIMEOUT"
    if "name or service not known" in lowered or "getaddrinfo failed" in lowered:
        return "DNS_RESOLUTION_FAILED"
    if "ssl" in lowered or "certificate" in lowered:
        return "TLS_NEGOTIATION_FAILED"
    if "http 404" in lowered:
        return "UPSTREAM_NOT_FOUND"
    if "http 403" in lowered:
        return "UPSTREAM_FORBIDDEN"
    if "http 429" in lowered:
        return "UPSTREAM_RATE_LIMITED"
    if re.search(r"http\s+5\d\d", lowered):
        return "UPSTREAM_SERVER_ERROR"
    return "UNCLASSIFIED_ERROR"


def _label(code: str) -> str:
    labels = {
        "RENDERER_PERMISSION_DENIED": "Browser renderer launch blocked by OS permissions.",
        "PROXY_CONNECTION_FAILED": "Network proxy refused outbound connection.",
        "NETWORK_TIMEOUT": "Upstream request timed out before response.",
        "DNS_RESOLUTION_FAILED": "Domain name could not be resolved.",
        "TLS_NEGOTIATION_FAILED": "TLS/SSL handshake failed.",
        "UPSTREAM_NOT_FOUND": "Requested upstream endpoint returned 404.",
        "UPSTREAM_FORBIDDEN": "Upstream endpoint returned 403.",
        "UPSTREAM_RATE_LIMITED": "Upstream endpoint returned 429 (rate limited).",
        "UPSTREAM_SERVER_ERROR": "Upstream endpoint returned 5xx server error.",
        "UNCLASSIFIED_ERROR": "Unhandled runtime failure.",
        "EXTRACTION_EMPTY": "No event entities matched current selectors.",
        "VALIDATION_DROP_ALL": "Parsed candidates were all invalid after normalization.",
    }
    return labels.get(code, "Unhandled runtime failure.")


def format_error(scope: str, raw_error: str) -> str:
    code = classify_error(raw_error)
    detail = " ".join((raw_error or "").split())
    return f"[{code}] {_label(code)} | scope={scope} | detail={detail}"


def format_info(code: str, scope: str, detail: str = "") -> str:
    msg = f"[{code}] {_label(code)} | scope={scope}"
    if detail:
        msg = f"{msg} | detail={detail}"
    return msg

