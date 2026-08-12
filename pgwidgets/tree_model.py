"""Python-side model of TreeView / TableView content.

pgwidgets-python drives the browser over a websocket: the browser is a
*view* that can be discarded and rebuilt at any moment -- a page reload, a
network blip, a second browser attaching to the same session.  Everything
needed to rebuild it therefore has to live on the Python side, which is the
source of truth.

Historically only the bulk calls (``set_tree`` / ``set_rows`` /
``set_columns``) were tracked, and every later mutation -- ``set_cell``,
``add_item``, ``add_tree``, ``delete_tree``, the row and column edits --
was fire-and-forget.  A reconnect then replayed the *original* bulk
snapshot, silently reverting every change made since.  These helpers keep
the model current as those calls go by, so reconstruction replays one
accurate ``set_tree`` / ``set_rows``.

Having the model on hand also makes ``update_tree`` incremental: rather
than shipping the whole tree and having the browser rebuild it (losing
expansion state, cell styles and any open editor), :func:`diff_tree`
computes the minimal set of operations against the model and only those go
over the wire.

Everything here is a pure function over plain dicts and lists, so the sync
and async wrappers share one implementation and it can be tested without a
session or a browser.

Tree shape (mirroring the JS side)
----------------------------------
A tree is a dict keyed by stable string ids.  A node's children are its
dict-valued entries; its own column values are either the ``__values__``
entry, when present, or its primitive entries.  A node with no dict-valued
entries is a leaf, and the dict *is* its column values.
"""

import copy

VALUES_KEY = '__values__'

_MISSING = object()

__all__ = ['VALUES_KEY', 'node_at', 'children_of', 'values_of',
           'values_target', 'copy_tree', 'set_cell', 'add_item',
           'remove_item', 'remove_items', 'merge_tree', 'delete_tree',
           'diff_tree', 'row_set_cell', 'insert_row', 'append_row',
           'delete_row', 'column_key', 'insert_column', 'append_column',
           'delete_column']


# ----- tree navigation ---------------------------------------------

def copy_tree(tree):
    """Return a deep copy, so the model can't be mutated behind our back
    by a caller that keeps and edits the structure it handed us."""
    try:
        return copy.deepcopy(tree)
    except Exception:
        # exotic values (e.g. an unpicklable object stashed in a row)
        # -- fall back to sharing rather than failing the call
        return tree


def node_at(tree, path):
    """Return the node at `path` (a sequence of keys), or None.

    An empty path denotes the root, i.e. `tree` itself.
    """
    node = tree
    for key in (path or ()):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def children_of(node):
    """Return {key: child} for a node's dict-valued entries."""
    if not isinstance(node, dict):
        return {}
    return {k: v for k, v in node.items()
            if k != VALUES_KEY and isinstance(v, dict)}


def values_of(node):
    """Return a node's column values (read-only use)."""
    if not isinstance(node, dict):
        return {}
    vals = node.get(VALUES_KEY)
    if isinstance(vals, dict):
        return vals
    return {k: v for k, v in node.items() if not isinstance(v, dict)}


def values_target(node):
    """Return the dict a node's column values should be *written* to.

    That is ``__values__`` for an interior node that carries one, else the
    node itself (a leaf, or an interior whose values sit alongside its
    children).
    """
    if not isinstance(node, dict):
        return None
    vals = node.get(VALUES_KEY)
    if isinstance(vals, dict):
        return vals
    return node


# ----- tree mutation -----------------------------------------------

def set_cell(tree, path, col_key, value):
    """Write one column value.  Returns True if the path resolved."""
    node = node_at(tree, path)
    target = values_target(node)
    if target is None:
        return False
    target[col_key] = value
    return True


def add_item(tree, parent, key, values):
    """Add/replace a single child under `parent` (None/[] = root)."""
    node = node_at(tree, parent)
    if not isinstance(node, dict):
        return False
    node[key] = copy_tree(values) if isinstance(values, dict) else values
    return True


def remove_item(tree, path):
    """Remove the node at `path` together with its subtree."""
    if not path:
        return False
    parent = node_at(tree, path[:-1])
    if not isinstance(parent, dict) or path[-1] not in parent:
        return False
    del parent[path[-1]]
    return True


def remove_items(tree, paths):
    return sum(1 for p in (paths or []) if remove_item(tree, p))


def merge_tree(tree, subtree, parent=None):
    """Merge `subtree` under `parent`, replacing same-key children
    subtree-deep -- the semantics of the JS ``add_tree``."""
    node = node_at(tree, parent)
    if not isinstance(node, dict) or not isinstance(subtree, dict):
        return False
    for key, value in subtree.items():
        node[key] = copy_tree(value) if isinstance(value, dict) else value
    return True


def delete_tree(tree, spec, prune_empty=True):
    """Delete the nodes named by `spec`, mirroring the JS ``_deleteSpec``.

    A key mapping to an empty dict (or a non-dict) removes that node and
    its whole subtree; a key mapping to a non-empty dict is descended into
    so only the named descendants go.  Keys absent from the tree are
    ignored.  With `prune_empty`, a branch left childless is removed too,
    cascading upward.  Returns the number of nodes removed.
    """
    def _delete(node, sub_spec):
        count = 0
        for key in list(sub_spec.keys()):
            if not isinstance(node, dict) or key not in node:
                continue          # not present; skip
            child = node[key]
            sub = sub_spec[key]
            descend = (isinstance(sub, dict) and len(sub) > 0
                       and len(children_of(child)) > 0)
            if not descend:
                del node[key]
                count += 1
            else:
                count += _delete(child, sub)
                if prune_empty and len(children_of(child)) == 0:
                    del node[key]
                    count += 1
        return count

    return _delete(tree, spec or {})


# ----- tree diffing -------------------------------------------------

def _count_nodes(tree):
    total = 0
    for child in children_of(tree).values():
        total += 1 + _count_nodes(child)
    return total


def diff_tree(old, new, max_ops=None):
    """Return the operations that turn `old` into `new`.

    Each operation is a tuple ``(method_name, *args)`` ready to dispatch
    at the browser: ``remove_items``, ``add_tree`` and ``set_cell``.
    Deletions are emitted first so additions never collide with a node on
    its way out.

    Returns None when the trees differ so broadly that replacing the whole
    thing is cheaper than patching it -- the caller should fall back to
    ``set_tree``.  `max_ops` defaults to the node count of `new`.
    """
    removals = []
    additions = []
    updates = []

    def walk(old_node, new_node, path):
        old_children = children_of(old_node)
        new_children = children_of(new_node)

        for key in old_children:
            if key not in new_children:
                removals.append(list(path) + [key])

        for key, new_child in new_children.items():
            old_child = old_children.get(key, _MISSING)
            if old_child is _MISSING:
                additions.append((list(path), key, new_child))
            else:
                walk(old_child, new_child, tuple(path) + (key,))

        if path:      # the root has no column values of its own
            old_vals = values_of(old_node)
            new_vals = values_of(new_node)
            for col_key, value in new_vals.items():
                if old_vals.get(col_key, _MISSING) != value:
                    updates.append((list(path), col_key, value))

    walk(old if isinstance(old, dict) else {},
         new if isinstance(new, dict) else {}, ())

    if max_ops is None:
        max_ops = max(_count_nodes(new), 1)
    if len(removals) + len(additions) + len(updates) > max_ops:
        return None       # wholesale replacement is cheaper

    ops = []
    if removals:
        ops.append(('remove_items', removals))
    for parent, key, node in additions:
        ops.append(('add_tree', {key: node}, parent or None))
    for path, col_key, value in updates:
        ops.append(('set_cell', path, col_key, value))
    return ops


# ----- flat rows (TableView) ----------------------------------------

def column_key(column, index=None):
    """Extract a column's key from any descriptor form."""
    if isinstance(column, dict):
        return column.get('key') or column.get('label') or (
            f'col{index}' if index is not None else None)
    if isinstance(column, (list, tuple)):
        return column[1] if len(column) > 1 else column[0]
    return column


def row_set_cell(rows, columns, row, col, value):
    """Write one cell of a flat row list.

    `row` is an index; `col` is a column key or index.  Rows may be dicts
    (keyed by column key) or positional sequences.
    """
    if not isinstance(rows, list) or not isinstance(row, int):
        return False
    if not (0 <= row < len(rows)):
        return False
    keys = [column_key(c, i) for i, c in enumerate(columns or [])]
    target = rows[row]
    if isinstance(target, dict):
        key = col if not isinstance(col, int) else (
            keys[col] if 0 <= col < len(keys) else None)
        if key is None:
            return False
        target[key] = value
        return True
    if isinstance(target, list):
        idx = col if isinstance(col, int) else (
            keys.index(col) if col in keys else None)
        if idx is None or not (0 <= idx < len(target)):
            return False
        target[idx] = value
        return True
    return False


def insert_row(rows, index, values):
    if not isinstance(rows, list):
        return False
    if not isinstance(index, int) or index < 0 or index > len(rows):
        index = len(rows)          # out of range clamps to append, as in JS
    rows.insert(index, copy_tree(values))
    return True


def append_row(rows, values):
    if not isinstance(rows, list):
        return False
    rows.append(copy_tree(values))
    return True


def delete_row(rows, index):
    if not isinstance(rows, list) or not isinstance(index, int):
        return False
    if not (0 <= index < len(rows)):
        return False
    del rows[index]
    return True


# ----- columns -------------------------------------------------------

def insert_column(columns, column, before=None, index=None):
    """Insert a column.

    TreeView names the insertion point by column key (`before`); TableView
    by position (`index`).  Pass whichever the caller supplied.
    """
    if not isinstance(columns, list):
        return False
    if index is None and before is not None:
        keys = [column_key(c, i) for i, c in enumerate(columns)]
        index = keys.index(before) if before in keys else len(columns)
    if not isinstance(index, int) or index < 0 or index > len(columns):
        index = len(columns)
    columns.insert(index, copy_tree(column))
    return True


def append_column(columns, column):
    if not isinstance(columns, list):
        return False
    columns.append(copy_tree(column))
    return True


def delete_column(columns, col):
    """Delete by column key (TreeView) or by index (TableView)."""
    if not isinstance(columns, list):
        return False
    if isinstance(col, int):
        if not (0 <= col < len(columns)):
            return False
        del columns[col]
        return True
    keys = [column_key(c, i) for i, c in enumerate(columns)]
    if col not in keys:
        return False
    del columns[keys.index(col)]
    return True
