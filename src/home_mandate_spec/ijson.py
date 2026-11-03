# SPDX-License-Identifier: Apache-2.0
"""Strict reading of JSON text as I-JSON (RFC 7493), SPEC-v0 section 3.1 items 1 and 5.

The standard library's ``json`` accepts more than I-JSON: duplicate keys (the last one wins),
``NaN`` and ``Infinity``, lone surrogates and noncharacters in strings, and bytes in UTF-16 or
UTF-32. ``parse`` rejects all of these and reads every number by its exact value.

Numbers come back as ``decimal.Decimal``, built from the literal as written, so that ``10``,
``10.0`` and ``1e1`` are the same value and fractions are kept exactly. A zero is read as
zero whatever its exponent; any other number outside Decimal's representable range is rejected
rather than rounded or replaced by NaN.
Whether a number is allowed in a place (a mandate permits only integers up to 2^53 - 1, a
request parameter that is not an integer is ``invalid_request``) is not decided here but by
the code that reads the value; ``exact_int`` is the helper for it.
"""

import json
import re
from decimal import Decimal, InvalidOperation
from typing import NoReturn

type JSONValue = None | bool | Decimal | str | list[JSONValue] | dict[str, JSONValue]

#: Largest magnitude of a number in a mandate or a request (SPEC-v0 sections 3.1 and 4.5).
MAX_SAFE_INTEGER = 2**53 - 1

#: Largest mandate, in bytes of its UTF-8 encoding as received (SPEC-v0 section 3.1 item 5).
MAX_MANDATE_BYTES = 262_144

#: Nesting depth beyond which input may be rejected before validation (SPEC-v0 section 3.1).
MAX_DEPTH = 32

# Code points that I-JSON forbids in member names and string values (RFC 7493 section 2.1):
# surrogates, and the noncharacters U+FDD0 to U+FDEF and the last two of every plane.
_FORBIDDEN = re.compile(
    "["
    + "\ud800-\udfff"
    + "﷐-﷯"
    + "".join(chr(plane * 0x10000 + 0xFFFE) + chr(plane * 0x10000 + 0xFFFF) for plane in range(17))
    + "]"
)


class IJSONError(ValueError):
    """The text is not I-JSON, or is larger or deeper than the limits given."""


def _reject_constant(name: str) -> NoReturn:
    raise IJSONError(f"{name} is not a JSON number")


def _number(literal: str) -> Decimal:
    try:
        value = Decimal(literal)
    except InvalidOperation:
        value = Decimal("NaN")
    # With InvalidOperation trapping disabled, Decimal returns NaN instead of raising.
    if value.is_finite():
        return value
    # A zero is zero whatever its exponent (SPEC-v0 section 3.2: numbers by their value).
    # Any other number outside the range is never an integer within 2^53 - 1, so no place
    # in a mandate could accept it.
    if not any(digit in "123456789" for digit in literal.partition("e")[0].partition("E")[0]):
        return Decimal("-0") if literal.startswith("-") else Decimal(0)
    raise IJSONError("number outside Decimal's representable range")


def _object(pairs: list[tuple[str, JSONValue]]) -> JSONValue:
    obj: dict[str, JSONValue] = {}
    for key, value in pairs:
        if key in obj:
            raise IJSONError(f"duplicate key {key!r}")
        obj[key] = value
    return obj


def _check_depth(text: str, max_depth: int) -> None:
    # Counts brackets outside strings, so that deep input is rejected before the decoder
    # recurses into it. Malformed input may be counted wrongly; the decoder rejects it anyway.
    depth = 0
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in "[{":
            depth += 1
            if depth > max_depth:
                raise IJSONError(f"nesting deeper than {max_depth}")
        elif ch in "]}":
            depth -= 1


def _check_strings(value: JSONValue) -> None:
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            if _FORBIDDEN.search(item):
                raise IJSONError("string contains a surrogate or a noncharacter")
        elif isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, dict):
            for key, member in item.items():
                if _FORBIDDEN.search(key):
                    raise IJSONError("key contains a surrogate or a noncharacter")
                stack.append(member)


def parse(
    data: str | bytes, *, max_bytes: int | None = None, max_depth: int | None = None
) -> JSONValue:
    """Reads exactly one JSON value from ``data`` and checks that it is I-JSON.

    ``bytes`` must be UTF-8. A ``str`` is counted and checked in its UTF-8 encoding, so a
    lone surrogate in it is rejected as invalid UTF-8. ``max_bytes`` bounds the size of that
    encoding before anything is parsed, ``max_depth`` the nesting of arrays and objects.

    Raises ``IJSONError`` for any input that is not accepted, including numbers outside
    Decimal's representable range.
    """
    if isinstance(data, bytes):
        raw = data
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            raise IJSONError("not valid UTF-8") from e
    else:
        text = data
        try:
            raw = text.encode("utf-8")
        except UnicodeEncodeError as e:
            raise IJSONError("not valid UTF-8") from e
    if max_bytes is not None and len(raw) > max_bytes:
        raise IJSONError(f"larger than {max_bytes} bytes")
    if max_depth is not None:
        _check_depth(text, max_depth)
    try:
        value: JSONValue = json.loads(
            text,
            parse_float=_number,
            parse_int=_number,
            parse_constant=_reject_constant,
            object_pairs_hook=_object,
        )
    except IJSONError:
        raise
    except RecursionError as e:
        raise IJSONError("nesting too deep") from e
    except ValueError as e:
        raise IJSONError(f"not JSON: {e}") from e
    _check_strings(value)
    return value


def exact_int(value: Decimal, limit: int = MAX_SAFE_INTEGER) -> int | None:
    """The value as an ``int`` if it is an integer of magnitude at most ``limit``, else None.

    ``Decimal("10.0")`` and ``Decimal("1e1")`` give 10, ``Decimal("-0")`` gives 0. The checks
    never round and never expand a large exponent: ``Decimal.normalize()`` and ``abs()`` round
    to the precision of the decimal context, which would turn
    ``50.000000000000000000000000000001`` into 50.
    """
    if not value.is_finite():
        return None
    if value.is_zero():
        return 0
    if value.copy_abs() > limit:
        return None
    integral = value.to_integral_value()
    if integral != value:
        return None
    return int(integral)
