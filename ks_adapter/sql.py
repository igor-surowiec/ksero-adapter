"""SQL helpers: identifier quoting, read-only enforcement and filters."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .errors import ColumnNotFound, InvalidRequest, QueryNotAllowed

_FIRST_KEYWORD = re.compile(r"^\s*([A-Za-z]+)")
_FORBIDDEN_KEYWORDS = (
    "insert",
    "update",
    "delete",
    "merge",
    "execute",
    "create",
    "alter",
    "drop",
    "recreate",
    "grant",
    "revoke",
    "commit",
    "rollback",
    "savepoint",
    "connect",
    "disconnect",
    "declare",
    "post_event",
    "begin",
    "set",
)

#: Firebird derives a parameter's length from the column it is compared with, so
#: a long ``LIKE`` pattern overflows the buffer of a short column (e.g. ``KOD``).
#: Casting the bind parameter keeps it wide enough for any pattern.
_LIKE_PARAMETER = "CAST(? AS VARCHAR(1024))"

#: Wire size of one ``_LIKE_PARAMETER``: the 1024 bytes of payload plus the
#: 2-byte length prefix of a ``VARCHAR``.
LIKE_PARAMETER_BYTES = 1024 + 2

#: Firebird 2.5 refuses to prepare a statement whose parameter or description
#: message is wider than this and answers with ``-204 Implementation limit
#: exceeded - block size exceeds implementation restriction``.  It is the reason
#: the curated endpoints search a hand-picked list of columns instead of every
#: text column of a wide table: each ``LIKE`` predicate costs a full
#: ``_LIKE_PARAMETER``, so a single ``WHERE`` can only carry
#: :data:`MAX_SEARCH_COLUMNS` of them.  Measured against Firebird 2.5: 63
#: predicates prepare fine (64 638 bytes), 64 fail (65 664 bytes).
MAX_MESSAGE_BYTES = 65535

#: Maximum number of columns ``build_search`` may combine in one statement.
MAX_SEARCH_COLUMNS = MAX_MESSAGE_BYTES // LIKE_PARAMETER_BYTES


def quote_identifier(name: str) -> str:
    """Quote a Firebird identifier, escaping embedded double quotes."""
    if not isinstance(name, str) or not name:
        raise InvalidRequest("Identifier must be a non-empty string")
    return '"' + name.replace('"', '""') + '"'


def ensure_read_only(sql: str) -> str:
    """Validate that ``sql`` is a single read-only SELECT/WITH statement.

    String literals and comments are stripped before validation so keywords
    hidden inside them cannot trigger false positives (and vice versa).  The
    original statement (without a trailing semicolon) is returned for execution.
    """
    if not isinstance(sql, str) or not sql.strip():
        raise QueryNotAllowed("SQL statement must not be empty")

    cleaned = sql.strip()
    while cleaned.endswith(";"):
        cleaned = cleaned[:-1].rstrip()
    if not cleaned:
        raise QueryNotAllowed("SQL statement must not be empty")

    sanitized = strip_sql_literals(cleaned)
    statements = [part.strip() for part in sanitized.split(";") if part.strip()]
    if len(statements) != 1:
        raise QueryNotAllowed("Only a single SQL statement is allowed")

    statement = statements[0]
    match = _FIRST_KEYWORD.match(statement)
    keyword = match.group(1).lower() if match else ""
    if keyword not in {"select", "with"}:
        raise QueryNotAllowed(
            "Only read-only SELECT or WITH statements are allowed"
        )

    lowered = statement.lower()
    for forbidden in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{forbidden}\b", lowered):
            raise QueryNotAllowed(
                f"The SQL statement contains a forbidden keyword: {forbidden.upper()}"
            )
    return cleaned


def strip_sql_literals(sql: str) -> str:
    """Replace comments and string/identifier literals with a single space."""
    output: list[str] = []
    index = 0
    length = len(sql)
    while index < length:
        char = sql[index]
        following = sql[index + 1] if index + 1 < length else ""
        if char == "-" and following == "-":
            newline = sql.find("\n", index + 2)
            output.append(" ")
            if newline == -1:
                break
            index = newline + 1
            continue
        if char == "/" and following == "*":
            end = sql.find("*/", index + 2)
            if end == -1:
                raise QueryNotAllowed("Unterminated block comment in SQL")
            output.append(" ")
            index = end + 2
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            while index < length:
                current = sql[index]
                if current == quote:
                    if index + 1 < length and sql[index + 1] == quote:
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            else:
                raise QueryNotAllowed("Unterminated quoted literal in SQL")
            output.append(" ")
            continue
        output.append(char)
        index += 1
    return "".join(output)


@dataclass(frozen=True)
class Filter:
    """A single column filter parsed from the ``filters`` query parameter."""

    column: str
    operator: str = "eq"
    value: Any = None


_COMPARISON_OPERATORS = {
    "eq": "=",
    "ne": "<>",
    "gt": ">",
    "ge": ">=",
    "lt": "<",
    "le": "<=",
}
_PATTERN_OPERATORS = {"contains", "startswith", "endswith"}
_OPERATORS = set(_COMPARISON_OPERATORS) | _PATTERN_OPERATORS | {
    "like",
    "in",
    "isnull",
    "notnull",
}


def parse_filters(raw: str | None) -> list[Filter]:
    """Parse the ``filters`` query parameter.

    The value is a JSON object mapping column names to either a plain value
    (equality) or an operator specification, e.g.::

        {"NAZWA": "Kowalski", "TYP": {"op": "in", "value": [1, 2]}}

    Supported operators: eq, ne, gt, ge, lt, le, like, contains, startswith,
    endswith, in, isnull, notnull.
    """
    if raw is None or not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidRequest(
            f"'filters' is not valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})"
        ) from exc
    if payload is None:
        return []
    if not isinstance(payload, dict):
        raise InvalidRequest(
            "'filters' must be a JSON object, e.g. "
            '{"COLUMN": value} or {"COLUMN": {"op": "eq", "value": 1}}'
        )

    filters: list[Filter] = []
    for column, spec in payload.items():
        if not isinstance(column, str) or not column.strip():
            raise InvalidRequest("'filters' keys must be non-empty column names")
        if isinstance(spec, dict):
            if "op" not in spec:
                raise InvalidRequest(
                    f"Filter for column '{column}' is missing the 'op' key"
                )
            extra = set(spec) - {"op", "value"}
            if extra:
                raise InvalidRequest(
                    f"Unknown key(s) in filter for column '{column}': "
                    + ", ".join(sorted(extra))
                )
            operator = str(spec.get("op")).strip().lower()
            value = spec.get("value")
        else:
            operator, value = "eq", spec
        if operator not in _OPERATORS:
            raise InvalidRequest(
                f"Unsupported filter operator '{operator}' for column '{column}'. "
                "Supported operators: " + ", ".join(sorted(_OPERATORS))
            )
        filters.append(Filter(column=column, operator=operator, value=value))
    return filters


def build_where(
    filters: Sequence[Filter], columns: Mapping[str, str]
) -> tuple[str, list[Any]]:
    """Build a parameterised ``WHERE`` clause.

    ``columns`` maps upper-cased column names to their canonical spelling, which
    both validates the request and prevents SQL injection through identifiers.
    """
    fragments: list[str] = []
    params: list[Any] = []

    for item in filters:
        canonical = columns.get(item.column.upper())
        if canonical is None:
            raise ColumnNotFound(f"Unknown column '{item.column}'")
        identifier = quote_identifier(canonical)
        operator = item.operator
        value = item.value

        if operator in {"isnull", "notnull"}:
            fragment = f"{identifier} IS NULL" if operator == "isnull" else (
                f"{identifier} IS NOT NULL"
            )
            fragments.append(fragment)
            continue

        if operator in _COMPARISON_OPERATORS:
            if value is None:
                if operator == "eq":
                    fragments.append(f"{identifier} IS NULL")
                    continue
                if operator == "ne":
                    fragments.append(f"{identifier} IS NOT NULL")
                    continue
                raise InvalidRequest(
                    f"Filter '{item.column}' with operator '{operator}' requires a value"
                )
            fragments.append(f"{identifier} {_COMPARISON_OPERATORS[operator]} ?")
            params.append(_scalar(value, item.column))
            continue

        if operator == "in":
            if not isinstance(value, (list, tuple)) or not value:
                raise InvalidRequest(
                    f"Filter '{item.column}' with operator 'in' requires a "
                    "non-empty JSON array"
                )
            params.extend(_scalar(entry, item.column) for entry in value)
            fragments.append(
                f"{identifier} IN ({', '.join('?' for _ in value)})"
            )
            continue

        if not isinstance(value, str):
            raise InvalidRequest(
                f"Filter '{item.column}' with operator '{operator}' requires a string value"
            )
        if operator == "like":
            fragments.append(f"{identifier} LIKE {_LIKE_PARAMETER}")
            params.append(value)
        else:
            fragments.append(f"{identifier} LIKE {_LIKE_PARAMETER} ESCAPE '\\'")
            params.append(_like_pattern(operator, value))

    if not fragments:
        return "", []
    return " WHERE " + " AND ".join(fragments), params


def build_search(
    term: str | None,
    columns: Mapping[str, str],
    candidates: Sequence[str],
) -> tuple[str, list[Any]]:
    """Build an ``OR``-ed ``LIKE`` clause searching ``term`` in ``candidates``.

    ``columns`` maps upper-cased column names to their canonical spelling (as
    stored in :class:`~ks_adapter.schema.TableInfo`), which validates the
    identifiers and prevents SQL injection.  Candidates missing from the table
    are skipped so a schema change cannot break the endpoint.  The search term
    is bound as a parameter and LIKE wildcards are escaped, so the term is
    always matched literally.

    Firebird sizes the parameter message from the number of predicates, so a
    list longer than :data:`MAX_SEARCH_COLUMNS` is refused here instead of
    failing later with an opaque "Implementation limit exceeded".
    """
    if term is None:
        return "", []
    if not isinstance(term, str):
        raise InvalidRequest("'search' must be a string")
    value = term.strip()
    if not value:
        return "", []

    pattern = _like_pattern("contains", value)
    fragments: list[str] = []
    params: list[Any] = []
    for candidate in candidates:
        canonical = columns.get(candidate.upper())
        if canonical is None:
            continue
        fragments.append(
            f"{quote_identifier(canonical)} LIKE {_LIKE_PARAMETER} ESCAPE '\\'"
        )
        params.append(pattern)
    if not fragments:
        return "", []
    if len(fragments) > MAX_SEARCH_COLUMNS:
        raise InvalidRequest(
            f"'search' would span {len(fragments)} columns, but Firebird allows "
            f"at most {MAX_SEARCH_COLUMNS} LIKE parameters per statement"
        )
    return " WHERE (" + " OR ".join(fragments) + ")", params


def _scalar(value: Any, column: str) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise InvalidRequest(
        f"Filter value for column '{column}' must be a string, number, boolean or null"
    )


def _like_pattern(operator: str, value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    if operator == "contains":
        return f"%{escaped}%"
    if operator == "startswith":
        return f"{escaped}%"
    return f"%{escaped}"

