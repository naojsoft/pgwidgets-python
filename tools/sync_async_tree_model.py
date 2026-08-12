#!/usr/bin/env python3
"""Regenerate the async mirror of the tree/table model methods.

``pgwidgets/sync/widget.py`` and ``pgwidgets/async_/widget.py`` hold the
same class-factory logic, one synchronous and one awaiting.  The
model-maintaining generators added for the TreeView/TableView state
(``_pad`` through ``_add_colour_override_methods``) are pure bookkeeping
around ``self._call``, so rather than maintain two hand-written copies --
which drift -- the async side is derived from the sync side by turning the
*generated* methods into coroutines.  The ``make_*`` factories and the
module-level helpers stay synchronous.

Run this after editing that region in sync/widget.py:

    python tools/sync_async_tree_model.py

It is idempotent: the previously generated region is replaced.
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SYNC = ROOT / 'pgwidgets' / 'sync' / 'widget.py'
ASYNC = ROOT / 'pgwidgets' / 'async_' / 'widget.py'

CALL_LINE = "    _add_tree_model_methods(attrs, all_methods)\n"
REGION_START = "def _pad(args, n):"
ASYNC_ANCHOR = "\ndef _init_params(pos_names, opt_names):"
BANNER = ("# ---- generated from sync/widget.py by "
          "tools/sync_async_tree_model.py ----\n")


def build_async_region(sync_src):
    start = sync_src.index(CALL_LINE)
    end = sync_src.index("def build_widget_class(js_class, defn):")
    block = sync_src[start:end]
    _, helpers = block.split("\n\n\n", 1)

    # only the generated methods become coroutines
    helpers = re.sub(r"(\n\s*)def (method|\w+_method)\(",
                     r"\1async def \2(", helpers)
    helpers = helpers.replace("return self._call(", "return await self._call(")
    helpers = helpers.replace("result = self._call(",
                              "result = await self._call(")
    return BANNER + helpers


def main():
    sync_src = SYNC.read_text()
    region = build_async_region(sync_src)

    dst = ASYNC.read_text()

    if CALL_LINE not in dst:
        anchor = ('        collapse_all_method.__name__ = "collapse_all"\n'
                  '        attrs["collapse_all"] = collapse_all_method\n')
        if anchor not in dst:
            sys.exit("could not find the tree-view method block in "
                     f"{ASYNC}")
        dst = dst.replace(anchor, anchor + "\n" + CALL_LINE, 1)

    if "from pgwidgets import tree_model" not in dst:
        dst = dst.replace(
            "from pgwidgets.defs import WIDGETS",
            "from pgwidgets import tree_model\nfrom pgwidgets.defs import "
            "WIDGETS", 1)

    # replace any previously generated region, else insert a fresh one
    if BANNER in dst:
        head = dst[:dst.index(BANNER)]
        tail = dst[dst.index(ASYNC_ANCHOR):]
        dst = head + region + tail
    else:
        idx = dst.index(REGION_START) if REGION_START in dst else None
        if idx is not None:
            head = dst[:idx]
            tail = dst[dst.index(ASYNC_ANCHOR):]
            dst = head + region + tail
        else:
            dst = dst.replace(ASYNC_ANCHOR, "\n" + region + ASYNC_ANCHOR, 1)

    ASYNC.write_text(dst)
    print(f"regenerated the async tree-model region in {ASYNC}")


if __name__ == '__main__':
    main()
