"""JSON encoding helper for the remote protocol.

The wire format between Python and the browser is JSON.  The stdlib
encoder has two issues for scientific data:

1. It rejects numpy scalars other than ``np.float64`` (which inherits
   from float), numpy arrays, and similar buffer-protocol objects —
   silently dropping a TreeView payload that happens to contain
   ``np.int64`` cell values.

2. It writes the literal tokens ``NaN`` / ``Infinity`` / ``-Infinity``
   for non-finite floats, which browsers' ``JSON.parse`` reject — a
   single masked / missing cell in a float column makes the whole
   payload silently fail to parse on the JS side.

``JsonEncoder`` handles both: ``.item()`` / ``.tolist()`` fall-backs
for numpy/pandas types, and a pre-walk that replaces non-finite floats
with ``None`` (encoded as JSON ``null``).  Use it via
``json.dumps(obj, cls=JsonEncoder)``.
"""

import json
import math


def _scrub_nan(obj):
    """Recursively replace non-finite floats with None so the result
    is RFC-8259-valid JSON when re-encoded.  Cheap walk: O(n) and
    only visits dicts/lists/tuples/floats."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _scrub_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_scrub_nan(v) for v in obj]
    return obj


def _coerce_scalar(v):
    """If *v* is a float, replace non-finite values with None."""
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


class JsonEncoder(json.JSONEncoder):
    def default(self, obj):
        item = getattr(obj, "item", None)
        if callable(item):
            try:
                return _coerce_scalar(item())
            except (TypeError, ValueError):
                pass
        tolist = getattr(obj, "tolist", None)
        if callable(tolist):
            try:
                return _scrub_nan(tolist())
            except (TypeError, ValueError):
                pass
        return super().default(obj)

    def iterencode(self, o, _one_shot=False):
        return super().iterencode(_scrub_nan(o), _one_shot=_one_shot)
