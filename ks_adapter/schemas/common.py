"""Shared wire-model types."""

from __future__ import annotations

#: ``NUMERIC``/``DECIMAL`` columns are serialised as floats, or as strings when
#: ``api.decimal_as_string`` is enabled (see ``serialization.to_jsonable``), so
#: both variants have to be accepted by the response models.
DecimalValue = float | str
