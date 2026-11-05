# SPDX-License-Identifier: Apache-2.0
"""Tests of the I-JSON reader against SPEC-v0 section 3.1 items 1 and 5, and RFC 7493."""

import json
import time
from decimal import Decimal, Inexact, InvalidOperation, Rounded, localcontext

import pytest

from home_mandate_spec.ijson import (
    MAX_DEPTH,
    MAX_MANDATE_BYTES,
    MAX_SAFE_INTEGER,
    IJSONError,
    exact_int,
    parse,
)

# Accepted input


def test_object_with_every_type() -> None:
    value = parse('{"s": "a", "n": 1, "t": true, "f": false, "z": null, "a": [], "o": {}}')
    assert value == {
        "s": "a",
        "n": Decimal(1),
        "t": True,
        "f": False,
        "z": None,
        "a": [],
        "o": {},
    }


def test_numbers_are_decimal_with_their_exact_value() -> None:
    value = parse("[10, 10.0, 1e1, 2.1e3, -0, 0.5]")
    assert value == [
        Decimal(10),
        Decimal("10.0"),
        Decimal("1e1"),
        Decimal("2.1e3"),
        Decimal("-0"),
        Decimal("0.5"),
    ]
    assert isinstance(value, list)
    assert all(type(n) is Decimal for n in value)


def test_a_string_is_never_a_number() -> None:
    assert parse('"50"') == "50"


def test_json_white_space_around_the_value() -> None:
    # SPEC-v0 conformance d37: white space around the mandate does not change it.
    assert parse(' \t\r\n{"a": 1}\n') == {"a": Decimal(1)}


def test_escapes_are_decoded() -> None:
    # Conformance d38: escaped slashes; d06: \u escapes.
    assert (
        parse('"https:\\/\\/example.org \\u00e9 \\ud83d\\ude00"')
        == "https://example.org \u00e9 \U0001f600"
    )


def test_bytes_in_utf8() -> None:
    assert parse('{"name": "\u00e9"}'.encode()) == {"name": "\u00e9"}


def test_a_large_integer_is_kept_exactly() -> None:
    # The standard int conversion stops at 4300 digits; a Decimal does not.
    digits = "9" * 5000
    assert parse(digits) == Decimal(digits)
    huge = "9" * (MAX_MANDATE_BYTES + 1)
    assert parse(huge, max_bytes=None) == Decimal(huge)


def test_replacement_character_is_allowed() -> None:
    assert parse('"\\ufffd"') == "\ufffd"


# I-JSON: exactly one JSON value (SPEC-v0 section 3.1 item 1)


@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        "{} {}",  # conformance i25: two values
        '{"a": 1',  # conformance i19: truncated
        "{'a': 1}",
        '{"a": 1,}',
        "[1,]",
        "01",
        "1.",
        ".5",
        "+1",
        "0x10",
        "\u0661",  # an Arabic-Indic digit is not a JSON digit
        "\ufeff{}",  # conformance i116: a byte order mark is not JSON
        '"a\u0001"',  # a raw control character inside a string
        '"\\x41"',
        "\u00a0{}",  # a no-break space is not JSON white space
    ],
)
def test_not_one_json_value(text: str) -> None:
    with pytest.raises(IJSONError):
        parse(text)


def test_byte_order_mark_in_bytes() -> None:
    with pytest.raises(IJSONError):
        parse(b"\xef\xbb\xbf{}")


# I-JSON: no duplicate keys


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1, "a": 1}',
        '{"decision": "deny", "decision": "allow"}',  # conformance i06
        '{"r": [{"category": "light", "category": "lock"}]}',  # conformance i20, nested
        '{"a": 1, "\\u0061": 2}',  # the same name, once escaped
    ],
)
def test_duplicate_key(text: str) -> None:
    with pytest.raises(IJSONError, match="duplicate key"):
        parse(text)


def test_keys_that_differ_only_in_case_are_distinct() -> None:
    assert parse('{"a": 1, "A": 2}') == {"a": Decimal(1), "A": Decimal(2)}


# I-JSON: numbers that JSON does not have


@pytest.mark.parametrize("text", ["NaN", "Infinity", "-Infinity", "[1, NaN]"])
def test_no_nan_or_infinity(text: str) -> None:
    with pytest.raises(IJSONError):
        parse(text)


@pytest.mark.parametrize("trap_invalid", [True, False])
@pytest.mark.parametrize(
    "literal",
    [
        "1e9999999999999999999",
        "-1e9999999999999999999",
        "1e-9999999999999999999",
        "-1e-9999999999999999999",
        "0.5e9999999999999999999",
        "0.0001e-9999999999999999999",
    ],
)
def test_unrepresentable_numbers_raise_ijson_error(literal: str, trap_invalid: bool) -> None:
    with localcontext() as context:
        context.traps[InvalidOperation] = trap_invalid
        for text in (literal, '{"value": ' + literal + "}"):
            with pytest.raises(IJSONError, match="representable range"):
                parse(text)


# I-JSON: valid UTF-8, no lone surrogates, no noncharacters (RFC 7493 section 2.1)


@pytest.mark.parametrize(
    "data",
    [
        b'"\xff"',
        b'"\xc0\xaf"',  # an overlong encoding of "/"
        b'"\xed\xa0\x80"',  # a surrogate encoded as if it were a character (CESU-8)
        b'"\xf4\x90\x80\x80"',  # above U+10FFFF
        b'"\xe2\x82"',  # a truncated sequence
        '{"a": 1}'.encode("utf-16"),
        '{"a": 1}'.encode("utf-32"),
    ],
)
def test_not_utf8(data: bytes) -> None:
    with pytest.raises(IJSONError):
        parse(data)


@pytest.mark.parametrize(
    "text",
    [
        '"Ung\\ud800"',  # conformance i24
        '"\\udc00"',
        '"\\ude00\\ud83d"',  # a pair in the wrong order is two lone surrogates
        '["ok", "\\ud800"]',
        '{"\\ud800": 1}',
        '{"a": {"b": ["\\udfff"]}}',
    ],
)
def test_lone_surrogate_escaped(text: str) -> None:
    with pytest.raises(IJSONError, match="surrogate"):
        parse(text)


def test_lone_surrogate_in_the_text_itself() -> None:
    with pytest.raises(IJSONError, match="UTF-8"):
        parse('"\ud800"')


@pytest.mark.parametrize(
    "code_point",
    [*range(0xFDD0, 0xFDF0)]
    + [plane * 0x10000 + suffix for plane in range(17) for suffix in (0xFFFE, 0xFFFF)],
)
def test_noncharacter(code_point: int) -> None:
    character = chr(code_point)
    for value in (character, {character: 1}, [character]):
        for ensure_ascii in (True, False):
            with pytest.raises(IJSONError, match="noncharacter"):
                parse(json.dumps(value, ensure_ascii=ensure_ascii))


def test_noncharacter_escaped() -> None:
    with pytest.raises(IJSONError, match="noncharacter"):
        parse('"\\uffff"')


@pytest.mark.parametrize("code_point", [0xFDCF, 0xFDF0, 0xFFFD, 0x1FFFD, 0x10FFFD])
def test_next_to_a_noncharacter_is_allowed(code_point: int) -> None:
    assert parse(f'"{chr(code_point)}"') == chr(code_point)


# Size (SPEC-v0 section 3.1 item 5): counted in UTF-8 bytes as received


def _string_of_bytes(size: int) -> str:
    return '"' + "a" * (size - 2) + '"'


def test_size_at_the_limit() -> None:
    parse(_string_of_bytes(MAX_MANDATE_BYTES), max_bytes=MAX_MANDATE_BYTES)


def test_size_over_the_limit() -> None:
    with pytest.raises(IJSONError, match="larger than"):
        parse(_string_of_bytes(MAX_MANDATE_BYTES + 1), max_bytes=MAX_MANDATE_BYTES)


def test_size_counts_bytes_not_characters() -> None:
    text = '"' + "\u00e9" * 4 + '"'  # 6 characters, 10 bytes
    parse(text, max_bytes=10)
    with pytest.raises(IJSONError):
        parse(text, max_bytes=9)


def test_size_counts_white_space() -> None:
    with pytest.raises(IJSONError):
        parse("{}" + " " * 10, max_bytes=11)


# Nesting depth (SPEC-v0 section 3.1)


def test_depth_at_the_limit() -> None:
    parse("[" * MAX_DEPTH + "]" * MAX_DEPTH, max_depth=MAX_DEPTH)


def test_depth_over_the_limit() -> None:
    depth = MAX_DEPTH + 1
    with pytest.raises(IJSONError, match="nesting"):
        parse("[" * depth + "]" * depth, max_depth=MAX_DEPTH)


def test_brackets_inside_strings_do_not_count() -> None:
    text = '["' + "[{" * 100 + '\\"[" ]'
    assert parse(text, max_depth=1) == ["[{" * 100 + '"[']


def test_very_deep_input_without_a_limit_is_an_error_not_a_crash() -> None:
    depth = 200_000
    with pytest.raises(IJSONError):
        parse("[" * depth + "]" * depth, max_depth=None)


# exact_int: whether a number is an integer within the limit


@pytest.mark.parametrize(
    ("literal", "expected"),
    [
        ("10", 10),
        ("10.0", 10),
        ("1e1", 10),
        ("1.0e2", 100),
        ("2.1e3", 2100),
        ("2100.000", 2100),
        ("-0", 0),
        ("-0.0", 0),
        ("0e5", 0),
        ("-1600", -1600),
        (str(MAX_SAFE_INTEGER), MAX_SAFE_INTEGER),
        (str(-MAX_SAFE_INTEGER), -MAX_SAFE_INTEGER),
        ("9.007199254740991e15", MAX_SAFE_INTEGER),
    ],
)
def test_exact_int(literal: str, expected: int) -> None:
    number = parse(literal)
    assert isinstance(number, Decimal)
    result = exact_int(number)
    assert result == expected
    assert type(result) is int


@pytest.mark.parametrize(
    "literal",
    [
        "0.5",
        "1.5e0",
        "1e-1",
        str(MAX_SAFE_INTEGER + 1),
        str(-MAX_SAFE_INTEGER - 1),
        "9.007199254740992e15",
        # 50 and a tiny fraction: normalize() or abs() would round this to 50.
        "50.000000000000000000000000000001",
        "50." + "0" * 1000 + "1",
        "1e999999999",
        "-1e999999999",
        "1e-999999999",
        "9" * 5000,
    ],
)
def test_not_an_exact_int(literal: str) -> None:
    number = parse(literal)
    assert isinstance(number, Decimal)
    assert exact_int(number) is None


def test_exact_int_with_another_limit() -> None:
    assert exact_int(Decimal(100), limit=100) == 100
    assert exact_int(Decimal(101), limit=100) is None


def test_numbers_stay_exact_in_a_low_precision_context() -> None:
    with localcontext() as context:
        context.prec = 1
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        for literal, expected in (
            (str(MAX_SAFE_INTEGER), MAX_SAFE_INTEGER),
            ("10.0", 10),
            ("-0", 0),
            ("0.5", None),
            ("50.000000000000000000000000000001", None),
            ("1e999999999", None),
            ("1e-999999999", None),
        ):
            number = parse(literal)
            assert isinstance(number, Decimal)
            assert number == Decimal(literal)
            assert exact_int(number) == expected


def test_exact_int_does_not_expand_a_huge_exponent() -> None:
    start = time.monotonic()
    assert exact_int(Decimal("1e999999999999999")) is None
    assert exact_int(Decimal("1e-999999999999999")) is None
    assert time.monotonic() - start < 1


@pytest.mark.parametrize("trap_invalid", [True, False])
@pytest.mark.parametrize(
    "literal",
    [
        "0e9999999999999999999",
        "0e-9999999999999999999",
        "-0e9999999999999999999",
        "0.000E+9999999999999999999",
        "-0.0e-9999999999999999999",
    ],
)
def test_zero_with_a_huge_exponent_is_zero(literal: str, trap_invalid: bool) -> None:
    # SPEC-v0 section 3.2: numbers are canonicalized by their value.
    with localcontext() as context:
        context.traps[InvalidOperation] = trap_invalid
        number = parse(literal)
        assert isinstance(number, Decimal)
        assert number.is_zero()
        assert exact_int(number) == 0
        assert parse('{"min": ' + literal + "}") == {"min": Decimal(0)}


# Defaults and input types


def test_the_limits_of_a_mandate_apply_by_default() -> None:
    with pytest.raises(IJSONError, match="larger than"):
        parse(_string_of_bytes(MAX_MANDATE_BYTES + 1))
    depth = MAX_DEPTH + 1
    with pytest.raises(IJSONError, match="nesting"):
        parse("[" * depth + "]" * depth)


def test_none_lifts_a_limit() -> None:
    parse(_string_of_bytes(MAX_MANDATE_BYTES + 1), max_bytes=None)
    depth = MAX_DEPTH + 1
    parse("[" * depth + "]" * depth, max_depth=None)


def test_a_large_array_is_rejected_before_it_is_read() -> None:
    # Without the default limit, a 10 MB array was read in full first.
    with pytest.raises(IJSONError, match="larger than"):
        parse("[" + "0," * 5_000_000 + "0]")


def test_bytearray() -> None:
    assert parse(bytearray(b'{"a": 1}')) == {"a": Decimal(1)}
    with pytest.raises(IJSONError, match="UTF-8"):
        parse(bytearray(b'"\xff"'))


@pytest.mark.parametrize("data", [None, 1, [], {}, memoryview(b"{}")])
def test_other_types_are_an_ijson_error(data: object) -> None:
    with pytest.raises(IJSONError, match="expected str or bytes"):
        parse(data)  # type: ignore[arg-type]
