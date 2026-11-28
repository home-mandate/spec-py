# SPDX-License-Identifier: Apache-2.0
"""Tests of the canonical form and the digest against SPEC-v0 section 3.2 and RFC 8785."""

import base64
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from home_mandate_spec.ijson import MAX_DEPTH, MAX_SAFE_INTEGER, JSONValue, parse
from home_mandate_spec.jcs import JCSError, canonicalize, digest

SPEC = Path(__file__).parent / "data" / "spec-v0.2.0"


def _canonical(text: str) -> str:
    return canonicalize(parse(text)).decode("utf-8")


# The digest cases of the specification (conformance/digest-v0.json)


def _digest_cases() -> list[dict[str, Any]]:
    # Read with Decimal so that an inline mandate keeps its numbers as written.
    text = (SPEC / "conformance" / "digest-v0.json").read_text(encoding="utf-8")
    cases: list[dict[str, Any]] = json.loads(text, parse_float=Decimal, parse_int=Decimal)["cases"]
    return cases


def _mandate_of(case: dict[str, Any]) -> JSONValue:
    if "mandate" in case:
        return parse((SPEC / case["mandate"]).read_bytes())
    if "mandate_raw" in case:
        return parse(case["mandate_raw"])
    if "mandate_base64" in case:
        return parse(base64.b64decode(case["mandate_base64"], validate=True))
    inline: JSONValue = case["mandate_inline"]
    return inline


@pytest.mark.parametrize("case", _digest_cases(), ids=lambda case: str(case["id"]))
def test_digest_case(case: dict[str, Any]) -> None:
    assert digest(_mandate_of(case)) == case["digest"], case["why"]


def test_all_digest_cases_are_read() -> None:
    cases = _digest_cases()
    assert len(cases) == 66
    assert len({case["id"] for case in cases}) == len(cases)


# The form of the digest


def test_digest_is_sha256_of_the_canonical_form_in_lower_case_hex() -> None:
    value = parse('{"b": 1, "a": [true, null, "x"]}')
    expected = hashlib.sha256(b'{"a":[true,null,"x"],"b":1}').hexdigest()
    assert digest(value) == "sha256:" + expected
    assert len(expected) == 64
    assert expected == expected.lower()


# Members: sorted by name as UTF-16 code units, no white space


def test_members_sorted_and_no_white_space() -> None:
    assert _canonical('{ "b" : 2 , "a" : { "d" : [ 1 , 2 ] , "c" : 3 } }') == (
        '{"a":{"c":3,"d":[1,2]},"b":2}'
    )


def test_arrays_keep_their_order() -> None:
    assert _canonical('[3, 1, 2, "b", "a"]') == '[3,1,2,"b","a"]'


def test_names_compare_by_utf16_code_units_not_code_points() -> None:
    # U+10000 is the surrogate pair D800 DC00, so it sorts before U+FFFD (FFFD) in UTF-16,
    # while code point order would put it after.
    assert _canonical('{"\\ufffd": 1, "\\ud800\\udc00": 2}') == '{"\U00010000":2,"\ufffd":1}'


def test_names_compare_case_sensitively() -> None:
    assert _canonical('{"b": 1, "B": 2, "a": 3, "A": 4}') == '{"A":4,"B":2,"a":3,"b":1}'


def test_empty_containers() -> None:
    assert _canonical('{"a": {}, "b": []}') == '{"a":{},"b":[]}'


# Strings (RFC 8785 section 3.2.2.2)


@pytest.mark.parametrize(
    ("text", "canonical"),
    [
        ('"\\u0022"', '"\\""'),
        ('"\\\\"', '"\\\\"'),
        ('"\\/"', '"/"'),
        ('"\\b\\t\\n\\f\\r"', '"\\b\\t\\n\\f\\r"'),
        ('"\\u0000\\u001f\\u000B"', '"\\u0000\\u001f\\u000b"'),
        ('"\\u007f"', '"\x7f"'),
        ('"\\u00e9\\u20ac"', '"\u00e9\u20ac"'),
        ('"\\u2028\\u2029"', '"\u2028\u2029"'),
        ('"\\ud83d\\ude00"', '"\U0001f600"'),
        ('"\\u0041\\u0062"', '"Ab"'),
    ],
)
def test_strings(text: str, canonical: str) -> None:
    assert _canonical(text) == canonical


def test_output_is_utf8() -> None:
    assert canonicalize(parse('"\\u00e9"')) == b'"\xc3\xa9"'


def test_no_unicode_normalization() -> None:
    # e with a combining acute accent stays two code points; it is not turned into U+00E9.
    assert _canonical('"e\\u0301"') == '"e\u0301"'


# Numbers: integers by their value (SPEC-v0 section 3.2)


@pytest.mark.parametrize(
    ("literal", "canonical"),
    [
        ("10", "10"),
        ("10.0", "10"),
        ("1e1", "10"),
        ("1E+1", "10"),
        ("2.1e3", "2100"),
        ("2100.0", "2100"),
        ("-0", "0"),
        ("-0.0E+5", "0"),
        ("0e99999999999999999999", "0"),
        ("-1600", "-1600"),
        (str(MAX_SAFE_INTEGER), str(MAX_SAFE_INTEGER)),
        ("-9.007199254740991E+15", str(-MAX_SAFE_INTEGER)),
        ("900719925474099.1e1", str(MAX_SAFE_INTEGER)),
    ],
)
def test_integers(literal: str, canonical: str) -> None:
    assert _canonical(literal) == canonical
    assert _canonical(f'{{"n": {literal}}}') == f'{{"n":{canonical}}}'


@pytest.mark.parametrize(
    "literal",
    [
        "0.5",
        "1e-1",
        "10.000000000000000000000000000001",
        str(MAX_SAFE_INTEGER + 1),
        str(-MAX_SAFE_INTEGER - 1),
        "1e999999999",
    ],
)
def test_other_numbers_have_no_canonical_form(literal: str) -> None:
    with pytest.raises(JCSError, match="integer"):
        canonicalize(parse(literal))
    with pytest.raises(JCSError):
        canonicalize(parse(f"[{literal}]"))


def test_literals() -> None:
    assert _canonical("[true, false, null]") == "[true,false,null]"


def test_a_boolean_is_not_a_number() -> None:
    # bool is a subclass of int in Python; the canonical form keeps them apart.
    assert _canonical('{"a": true, "b": 1}') == '{"a":true,"b":1}'


# Nesting depth (SPEC-v0 section 3.1: deeper than 32 has no canonical form)


def test_depth_at_the_limit() -> None:
    text = "[" * MAX_DEPTH + "]" * MAX_DEPTH
    assert _canonical(text) == text


def test_depth_over_the_limit() -> None:
    depth = MAX_DEPTH + 1
    value = parse("[" * depth + "]" * depth, max_depth=None)
    with pytest.raises(JCSError, match="nesting"):
        canonicalize(value)


# Values that are not JSON


@pytest.mark.parametrize("value", [1, 1.5, (1, 2), {1: "a"}, b"x", object()])
def test_not_a_json_value(value: object) -> None:
    with pytest.raises(JCSError):
        canonicalize([value])  # type: ignore[list-item]


def test_a_name_that_is_not_a_string() -> None:
    with pytest.raises(JCSError):
        canonicalize({1: "a"})  # type: ignore[dict-item]


def test_lone_surrogate() -> None:
    with pytest.raises(JCSError, match="surrogate"):
        canonicalize(["\ud800"])
