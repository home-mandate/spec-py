# SPDX-License-Identifier: Apache-2.0
"""Canonical JSON (RFC 8785) and the digest of a mandate, SPEC-v0 section 3.2.

``canonicalize`` writes a value read by ``ijson.parse`` in the canonical form of RFC 8785:
object members sorted by their names as UTF-16 code units, no white space, strings with the
fixed set of escapes of section 3.2.2.2, and the literals ``true``, ``false`` and ``null``.

Numbers are the one place where this is narrower than RFC 8785. The specification allows
only integers of magnitude at most 2^53 - 1 in mandates and audit log entries (section 3.1),
so a number is written in decimal notation without fraction and exponent, and ``-0`` as
``0``. Any other number has no canonical form here and is refused, instead of being
serialized as an IEEE 754 double the way RFC 8785 would.

Nesting deeper than 32 has no canonical form either (section 3.1): valid mandates never
reach it.
"""

import hashlib
from decimal import Decimal

from home_mandate_spec.ijson import MAX_DEPTH, MAX_SAFE_INTEGER, JSONValue, exact_int


class JCSError(ValueError):
    """The value has no canonical form under the rules of the specification."""


# RFC 8785 section 3.2.2.2: '"' and '\' are escaped, the control characters U+0000 to
# U+001F get the short forms where JSON has one and \u00xx (lower case) otherwise. Every
# other character is written as itself, including U+007F, U+2028 and U+2029.
_SHORT = {"\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r"}
_ESCAPES = {code: _SHORT.get(chr(code), f"\\u{code:04x}") for code in range(0x20)}
_ESCAPES[ord('"')] = '\\"'
_ESCAPES[ord("\\")] = "\\\\"


def _string(text: str, out: list[str]) -> None:
    out.append('"')
    out.append(text.translate(_ESCAPES))
    out.append('"')


def _utf16(name: str) -> bytes:
    # Big-endian UTF-16 compares byte by byte in the order of its code units.
    return name.encode("utf-16-be", "surrogatepass")


def _write(value: JSONValue, out: list[str], depth: int) -> None:
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif type(value) is Decimal:
        number = exact_int(value, MAX_SAFE_INTEGER)
        if number is None:
            raise JCSError(f"not an integer of magnitude at most 2^53 - 1: {value}")
        out.append(str(number))
    elif type(value) is str:
        _string(value, out)
    elif type(value) is list:
        if depth >= MAX_DEPTH:
            raise JCSError(f"nesting deeper than {MAX_DEPTH}")
        out.append("[")
        for index, item in enumerate(value):
            if index:
                out.append(",")
            _write(item, out, depth + 1)
        out.append("]")
    elif type(value) is dict:
        if depth >= MAX_DEPTH:
            raise JCSError(f"nesting deeper than {MAX_DEPTH}")
        if any(type(name) is not str for name in value):
            raise JCSError("a member name is not a string")
        out.append("{")
        for index, name in enumerate(sorted(value, key=_utf16)):
            if index:
                out.append(",")
            _string(name, out)
            out.append(":")
            _write(value[name], out, depth + 1)
        out.append("}")
    else:
        raise JCSError(f"not a JSON value: {type(value).__name__}")


def canonicalize(value: JSONValue) -> bytes:
    """The canonical form of ``value`` (RFC 8785 as narrowed by SPEC-v0 section 3.2), UTF-8.

    ``value`` is what ``ijson.parse`` returns: numbers are ``Decimal``. Raises ``JCSError``
    for a number that is not an integer of magnitude at most 2^53 - 1, for nesting deeper
    than 32, and for anything that is not a JSON value.
    """
    out: list[str] = []
    _write(value, out, 0)
    try:
        return "".join(out).encode("utf-8")
    except UnicodeEncodeError as e:
        raise JCSError("a string contains a lone surrogate") from e


def digest(value: JSONValue) -> str:
    """``"sha256:"`` and the lower-case hex SHA-256 of the canonical form (SPEC-v0 section 3.2).

    The specification defines the digest over a valid mandate; this function does not
    validate, it only computes.
    """
    return "sha256:" + hashlib.sha256(canonicalize(value)).hexdigest()
