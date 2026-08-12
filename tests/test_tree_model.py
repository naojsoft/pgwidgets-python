"""
Tests for the Python-side TreeView / TableView model.

pgwidgets-python is driven from Python and the browser is a rebuildable
view, so every mutation has to be reflected in ``_state`` -- otherwise a
reconnect replays a bulk snapshot that predates it.  These tests cover the
pure model helpers, the widget methods that maintain the model, the
incremental ``update_tree``, and what reconstruction actually replays.
"""

import threading

import pytest

from pgwidgets import tree_model
from pgwidgets.sync.application import Application, Session
from pgwidgets.sync.widget import build_all_widget_classes


# ----- harness (mirrors tests/test_reconstruct.py) ------------------

class RecordingSession(Session):
    def __init__(self, app, session_id):
        super().__init__(app, session_id, ws=None)
        self._recorded = []
        self._recording = False

    def _send(self, msg):
        if self._recording:
            self._recorded.append(dict(msg))
            return {"type": "result", "value": None}
        return None

    def start_recording(self):
        self._recorded = []
        self._recording = True

    def stop_recording(self):
        self._recording = False

    def calls(self, method=None):
        out = [m for m in self._recorded if m.get("type") == "call"]
        if method is not None:
            out = [m for m in out if m.get("method") == method]
        return out


def _make_session():
    app = Application.__new__(Application)
    app._host = "127.0.0.1"
    app._ws_port = 9500
    app._http_port = 9501
    app._use_http_server = False
    app._concurrency = "concurrent"
    app._max_sessions = None
    app._sessions = {}
    app._next_session_id = 1
    app._session_lock = threading.Lock()
    app._on_connect = None
    app._on_disconnect = None
    app._cb_queue = None
    app._loop = None
    app._thread = None
    app._session_semaphore = None
    app._widget_classes = build_all_widget_classes()

    import logging
    logger = logging.getLogger("pgwidgets.test")
    logger.addHandler(logging.NullHandler())
    app._logger = logger

    s = RecordingSession(app, 1)
    s._widget_classes = app._widget_classes
    app._sessions[1] = s
    return s


def _tree():
    return {
        'ob1': {'__values__': {'name': 'ob1'},
                'e1': {'name': 'e1', 'seeing': '0.6'},
                'e2': {'name': 'e2', 'seeing': '0.8'}},
        'ob2': {'__values__': {'name': 'ob2'},
                'e9': {'name': 'e9', 'seeing': '1.0'}},
    }


# ----- pure model helpers ------------------------------------------

class TestNavigation:

    def test_node_at(self):
        t = _tree()
        assert tree_model.node_at(t, []) is t
        assert tree_model.node_at(t, ['ob1', 'e1'])['seeing'] == '0.6'
        assert tree_model.node_at(t, ['nope']) is None
        assert tree_model.node_at(t, ['ob1', 'nope']) is None

    def test_children_excludes_values_sentinel(self):
        node = _tree()['ob1']
        assert sorted(tree_model.children_of(node)) == ['e1', 'e2']

    def test_values_of_interior_and_leaf(self):
        t = _tree()
        assert tree_model.values_of(t['ob1']) == {'name': 'ob1'}
        assert tree_model.values_of(t['ob1']['e1']) == {'name': 'e1',
                                                        'seeing': '0.6'}

    def test_values_of_interior_without_sentinel(self):
        """An interior may carry its values alongside its children."""
        node = {'name': 'ob', 'child': {'name': 'c'}}
        assert tree_model.values_of(node) == {'name': 'ob'}
        assert list(tree_model.children_of(node)) == ['child']


class TestMutation:

    def test_set_cell_interior_uses_values_sentinel(self):
        t = _tree()
        assert tree_model.set_cell(t, ['ob1'], 'name', 'renamed')
        assert t['ob1']['__values__']['name'] == 'renamed'
        assert 'name' not in tree_model.children_of(t['ob1'])

    def test_set_cell_leaf(self):
        t = _tree()
        assert tree_model.set_cell(t, ['ob1', 'e1'], 'seeing', '1.4')
        assert t['ob1']['e1']['seeing'] == '1.4'

    def test_set_cell_unknown_path(self):
        t = _tree()
        assert not tree_model.set_cell(t, ['nope'], 'seeing', '1.4')

    def test_add_and_remove_item(self):
        t = _tree()
        tree_model.add_item(t, ['ob1'], 'e3', {'name': 'e3'})
        assert 'e3' in t['ob1']
        assert tree_model.remove_item(t, ['ob1', 'e1'])
        assert 'e1' not in t['ob1']
        assert not tree_model.remove_item(t, ['ob1', 'e1'])

    def test_add_item_copies(self):
        """The model must not alias a caller's dict."""
        t = _tree()
        values = {'name': 'e3'}
        tree_model.add_item(t, ['ob1'], 'e3', values)
        values['name'] = 'mutated'
        assert t['ob1']['e3']['name'] == 'e3'

    def test_merge_tree_replaces_same_key_subtree_deep(self):
        t = _tree()
        tree_model.merge_tree(t, {'ob1': {'__values__': {'name': 'new'}}})
        assert 'e1' not in t['ob1']
        assert t['ob1']['__values__']['name'] == 'new'

    def test_merge_tree_under_parent(self):
        t = _tree()
        tree_model.merge_tree(t, {'e3': {'name': 'e3'}}, ['ob1'])
        assert t['ob1']['e3']['name'] == 'e3'
        assert 'e1' in t['ob1']

    def test_delete_tree_removes_named_subtree(self):
        t = _tree()
        assert tree_model.delete_tree(t, {'ob2': {}}) == 1
        assert 'ob2' not in t

    def test_delete_tree_descends(self):
        t = _tree()
        tree_model.delete_tree(t, {'ob1': {'e1': {}}}, prune_empty=False)
        assert 'e1' not in t['ob1']
        assert 'e2' in t['ob1']

    def test_delete_tree_prunes_emptied_parent(self):
        t = _tree()
        tree_model.delete_tree(t, {'ob2': {'e9': {}}}, prune_empty=True)
        assert 'ob2' not in t

    def test_delete_tree_keeps_emptied_parent_without_prune(self):
        t = _tree()
        tree_model.delete_tree(t, {'ob2': {'e9': {}}}, prune_empty=False)
        assert 'ob2' in t
        assert tree_model.children_of(t['ob2']) == {}

    def test_delete_tree_ignores_absent_keys(self):
        t = _tree()
        assert tree_model.delete_tree(t, {'nope': {}}) == 0


class TestDiff:

    def test_no_change_is_no_ops(self):
        assert tree_model.diff_tree(_tree(), _tree()) == []

    def test_changed_cell(self):
        old, new = _tree(), _tree()
        new['ob1']['e1']['seeing'] = '1.4'
        assert tree_model.diff_tree(old, new) == [
            ('set_cell', ['ob1', 'e1'], 'seeing', '1.4')]

    def test_added_child(self):
        old, new = _tree(), _tree()
        new['ob1']['e3'] = {'name': 'e3'}
        assert tree_model.diff_tree(old, new) == [
            ('add_tree', {'e3': {'name': 'e3'}}, ['ob1'])]

    def test_added_root_node(self):
        old, new = _tree(), _tree()
        new['ob3'] = {'__values__': {'name': 'ob3'}}
        ops = tree_model.diff_tree(old, new)
        assert ops == [('add_tree',
                        {'ob3': {'__values__': {'name': 'ob3'}}}, None)]

    def test_removals_come_first(self):
        old, new = _tree(), _tree()
        del new['ob2']
        new['ob1']['e1']['seeing'] = '1.4'
        ops = tree_model.diff_tree(old, new)
        assert ops[0] == ('remove_items', [['ob2']])

    def test_interior_values_change(self):
        old, new = _tree(), _tree()
        new['ob1']['__values__']['name'] = 'renamed'
        assert tree_model.diff_tree(old, new) == [
            ('set_cell', ['ob1'], 'name', 'renamed')]

    def test_wholesale_change_falls_back(self):
        """A diff bigger than the tree should signal 'just resend'."""
        old = _tree()
        new = {f'x{i}': {'name': f'x{i}'} for i in range(20)}
        assert tree_model.diff_tree(old, new) is None


# ----- widget methods maintain the model ----------------------------

class TestWidgetModel:

    def _tree_widget(self):
        s = _make_session()
        W = s.get_widgets()
        tree = W.TreeView()
        tree.set_columns([{'label': 'Name', 'key': 'name'},
                          {'label': 'Seeing', 'key': 'seeing'}])
        tree.set_tree(_tree())
        return s, tree

    def test_set_tree_copies(self):
        s = _make_session()
        tree = s.get_widgets().TreeView()
        data = _tree()
        tree.set_tree(data)
        data['ob1']['e1']['seeing'] = 'mutated'
        assert tree._state['tree']['ob1']['e1']['seeing'] == '0.6'

    def test_set_cell_updates_model(self):
        s, tree = self._tree_widget()
        tree.set_cell(['ob1', 'e1'], 'seeing', '1.4')
        assert tree._state['tree']['ob1']['e1']['seeing'] == '1.4'

    def test_structural_edits_update_model(self):
        s, tree = self._tree_widget()
        tree.add_item(['ob1'], 'e3', {'name': 'e3'})
        tree.add_tree({'ob3': {'__values__': {'name': 'ob3'}}})
        tree.remove_item(['ob1', 'e1'])
        tree.delete_tree({'ob2': {}})
        model = tree._state['tree']
        assert 'e3' in model['ob1']
        assert 'ob3' in model
        assert 'e1' not in model['ob1']
        assert 'ob2' not in model

    def test_table_row_edits_update_model(self):
        s = _make_session()
        table = s.get_widgets().TableView()
        table.set_columns([{'label': 'A', 'key': 'a'}])
        table.set_rows([{'a': 'one'}, {'a': 'two'}])
        table.append_row({'a': 'three'})
        table.insert_row(0, {'a': 'zero'})
        table.set_cell(2, 'a', 'CHANGED')
        table.delete_row(1)
        assert table._state['rows'] == [{'a': 'zero'}, {'a': 'CHANGED'},
                                        {'a': 'three'}]

    def test_column_edits_update_model(self):
        s, tree = self._tree_widget()
        tree.append_column({'label': 'Note', 'key': 'note'})
        tree.insert_column({'label': 'Grade', 'key': 'grade'}, 'seeing')
        tree.delete_column('name')
        keys = [c['key'] for c in tree._state['columns']]
        assert keys == ['grade', 'seeing', 'note']

    def test_bulk_set_drops_row_level_styles(self):
        """The JS clear() before a bulk load empties the cell/row style
        maps but keeps the column and table layers."""
        s, tree = self._tree_widget()
        tree.set_cell_color(['ob1', 'e1'], 'seeing', fg='red')
        tree.set_row_color(['ob1'], bg='grey')
        tree.set_column_color('name', fg='#333')
        tree.set_table_color(fg='#000')
        tree.set_tree(_tree())
        assert '_cell_styles' not in tree._state
        assert '_row_styles' not in tree._state
        assert '_column_styles' in tree._state
        assert '_table_style' in tree._state

    def test_all_null_colour_clears_that_entry(self):
        s, tree = self._tree_widget()
        tree.set_cell_color(['ob1', 'e1'], 'seeing', fg='red')
        assert len(tree._state['_cell_styles']) == 1
        tree.set_cell_color(['ob1', 'e1'], 'seeing')
        assert tree._state['_cell_styles'] == {}

    def test_clear_all_colors_drops_every_layer(self):
        s, tree = self._tree_widget()
        tree.set_cell_color(['ob1', 'e1'], 'seeing', fg='red')
        tree.set_column_color('name', fg='#333')
        tree.set_table_color(fg='#000')
        tree.clear_all_colors()
        for key in ('_cell_styles', '_row_styles', '_column_styles',
                    '_table_style'):
            assert key not in tree._state


class TestIncrementalUpdateTree:

    def _widget(self):
        s = _make_session()
        tree = s.get_widgets().TreeView()
        tree.set_columns([{'label': 'Name', 'key': 'name'},
                          {'label': 'Seeing', 'key': 'seeing'}])
        tree.set_tree(_tree())
        return s, tree

    def test_sends_only_deltas(self):
        s, tree = self._widget()
        new = _tree()
        del new['ob2']
        new['ob1']['e1']['seeing'] = '1.4'
        new['ob1']['e3'] = {'name': 'e3'}

        s.start_recording()
        tree.update_tree(new)
        s.stop_recording()

        methods = [m['method'] for m in s.calls()]
        assert 'set_tree' not in methods
        assert methods == ['remove_items', 'add_tree', 'set_cell']

    def test_model_matches_after_update(self):
        s, tree = self._widget()
        new = _tree()
        new['ob1']['e1']['seeing'] = '1.4'
        tree.update_tree(new)
        assert tree._state['tree'] == new

    def test_first_update_without_model_sends_set_tree(self):
        s = _make_session()
        tree = s.get_widgets().TreeView()
        s.start_recording()
        tree.update_tree(_tree())
        s.stop_recording()
        assert [m['method'] for m in s.calls()] == ['set_tree']

    def test_wholesale_change_sends_set_tree(self):
        s, tree = self._widget()
        s.start_recording()
        tree.update_tree({f'x{i}': {'name': f'x{i}'} for i in range(20)})
        s.stop_recording()
        assert [m['method'] for m in s.calls()] == ['set_tree']

    def test_incremental_update_keeps_cell_styles(self):
        """The point of diffing: styles survive because the browser
        never clears."""
        s, tree = self._widget()
        tree.set_cell_color(['ob1', 'e1'], 'seeing', fg='red')
        new = _tree()
        new['ob1']['e1']['seeing'] = '1.4'
        tree.update_tree(new)
        assert len(tree._state['_cell_styles']) == 1


# ----- what a reconnect replays -------------------------------------

class TestReconstruction:

    def test_mutations_survive_reconnect(self):
        """Regression: reconstruction used to replay the original bulk
        snapshot, silently reverting every mutation since."""
        s = _make_session()
        W = s.get_widgets()
        tree = W.TreeView()
        tree.set_columns([{'label': 'Name', 'key': 'name'},
                          {'label': 'Seeing', 'key': 'seeing'}])
        tree.set_tree(_tree())
        tree.add_item(['ob1'], 'e3', {'name': 'e3', 'seeing': '0.7'})
        tree.remove_item(['ob1', 'e1'])
        tree.set_cell(['ob1', 'e2'], 'seeing', '1.9')

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        set_tree, = s.calls('set_tree')
        replayed = set_tree['args'][0]
        assert 'e1' not in replayed['ob1']
        assert replayed['ob1']['e3']['seeing'] == '0.7'
        assert replayed['ob1']['e2']['seeing'] == '1.9'

    def test_colours_survive_reconnect(self):
        s = _make_session()
        tree = s.get_widgets().TreeView()
        tree.set_columns([{'label': 'Name', 'key': 'name'},
                          {'label': 'Seeing', 'key': 'seeing'}])
        tree.set_tree(_tree())
        tree.set_cell_color(['ob1', 'e1'], 'seeing', 'red', None, None)
        tree.set_row_color(['ob2'], None, 'yellow', None)
        tree.set_column_color('name', '#333', None, None)
        tree.set_table_color('#000', None, None)

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        # replayed as one batch, not one call per coloured cell
        assert s.calls('set_cell_color') == []
        batch, = s.calls('set_colors')
        spec, = batch['args']
        assert spec['cells'] == [{'path': ['ob1', 'e1'], 'col_key': 'seeing',
                                  'fg': 'red', 'bg': None, 'bold': None}]
        assert spec['rows'] == [{'path': ['ob2'], 'fg': None,
                                 'bg': 'yellow', 'bold': None}]
        assert spec['columns'] == [{'col_key': 'name', 'fg': '#333',
                                    'bg': None, 'bold': None}]
        assert spec['table'] == {'fg': '#000', 'bg': None, 'bold': None}

    def test_colours_replay_after_the_data(self):
        """A colour applied before its row exists would be dropped by the
        browser, so the data has to land first."""
        s = _make_session()
        tree = s.get_widgets().TreeView()
        tree.set_columns([{'label': 'Name', 'key': 'name'}])
        tree.set_tree(_tree())
        tree.set_cell_color(['ob1', 'e1'], 'name', fg='red')

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        methods = [m['method'] for m in s.calls()]
        assert methods.index('set_tree') < methods.index('set_colors')

    def test_table_rows_survive_reconnect(self):
        s = _make_session()
        table = s.get_widgets().TableView()
        table.set_columns([{'label': 'A', 'key': 'a'}])
        table.set_rows([{'a': 'one'}, {'a': 'two'}])
        table.set_cell(1, 'a', 'CHANGED')
        table.append_row({'a': 'three'})

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        set_rows, = s.calls('set_rows')
        assert set_rows['args'][0] == [{'a': 'one'}, {'a': 'CHANGED'},
                                       {'a': 'three'}]


class TestIncrementalUpdateData:
    """update_data / update_rows: the browser diffs the array it is
    given, so the whole array goes over the wire but only the differing
    rows are touched.  The model still has to record the new contents."""

    def _table(self):
        s = _make_session()
        table = s.get_widgets().TableView()
        table.set_columns([{'label': 'A', 'key': 'a'}])
        table.set_rows([{'a': 'one'}, {'a': 'two'}])
        return s, table

    def test_update_rows_records_the_model(self):
        s, table = self._table()
        table.update_rows([{'a': 'one'}, {'a': 'CHANGED'}, {'a': 'three'}])
        assert table._state['rows'] == [{'a': 'one'}, {'a': 'CHANGED'},
                                        {'a': 'three'}]

    def test_update_rows_survives_reconnect(self):
        s, table = self._table()
        table.update_rows([{'a': 'one'}, {'a': 'CHANGED'}])
        s.start_recording()
        s.reconstruct()
        s.stop_recording()
        set_rows, = s.calls('set_rows')
        assert set_rows['args'][0] == [{'a': 'one'}, {'a': 'CHANGED'}]

    def test_update_rows_keeps_row_styles(self):
        """No clear() happens, so the row-level colour layers stay."""
        s, table = self._table()
        table.set_cell_color([0], 'a', fg='red')
        table.update_rows([{'a': 'one'}, {'a': 'CHANGED'}])
        assert len(table._state['_cell_styles']) == 1

    def test_update_data_fills_whichever_bulk_key_was_used(self):
        s, table = self._table()      # populated via set_rows -> 'rows'
        table.update_data([{'a': 'x'}])
        assert table._state['rows'] == [{'a': 'x'}]
        assert 'data' not in table._state

    def test_update_data_copies(self):
        s, table = self._table()
        rows = [{'a': 'x'}]
        table.update_data(rows)
        rows[0]['a'] = 'mutated'
        assert table._state['rows'] == [{'a': 'x'}]


class TestBatchedColours:
    """Colours are replayed in batches: a single set_*_color call is a
    blocking round-trip *and* a full browser re-render, so a few hundred
    coloured cells replayed one at a time is slow and visibly
    iterative."""

    def _tree_with_colours(self, n_cells):
        s = _make_session()
        tree = s.get_widgets().TreeView()
        tree.set_columns([{'label': 'Name', 'key': 'name'},
                          {'label': 'Seeing', 'key': 'seeing'}])
        rows = {f'ob{i}': {'name': f'ob{i}'} for i in range(n_cells)}
        tree.set_tree(rows)
        for i in range(n_cells):
            tree.set_cell_color([f'ob{i}'], 'seeing', fg='red')
        return s, tree

    def test_reconnect_sends_one_call_for_many_cells(self):
        s, tree = self._tree_with_colours(50)
        s.start_recording()
        s.reconstruct()
        s.stop_recording()
        assert len(s.calls('set_colors')) == 1
        assert s.calls('set_cell_color') == []
        spec, = s.calls('set_colors')[0]['args']
        assert len(spec['cells']) == 50

    def test_large_sets_are_chunked(self):
        from pgwidgets.method_types import COLOUR_BATCH_SIZE
        n = COLOUR_BATCH_SIZE * 2 + 10
        s, tree = self._tree_with_colours(n)
        s.start_recording()
        s.reconstruct()
        s.stop_recording()
        batches = s.calls('set_colors')
        assert len(batches) == 3
        total = sum(len(b['args'][0]['cells']) for b in batches)
        assert total == n

    def test_no_colours_sends_nothing(self):
        s = _make_session()
        tree = s.get_widgets().TreeView()
        tree.set_columns([{'label': 'Name', 'key': 'name'}])
        tree.set_tree(_tree())
        s.start_recording()
        s.reconstruct()
        s.stop_recording()
        assert s.calls('set_colors') == []

    def test_batch_call_folds_into_the_model(self):
        """A batch has to update the same maps the single calls do, or
        the next reconnect loses it."""
        s = _make_session()
        tree = s.get_widgets().TreeView()
        tree.set_columns([{'label': 'Name', 'key': 'name'},
                          {'label': 'Seeing', 'key': 'seeing'}])
        tree.set_tree(_tree())
        tree.set_colors({
            'cells': [{'path': ['ob1', 'e1'], 'col_key': 'seeing',
                       'fg': 'red'}],
            'rows': [{'path': ['ob2'], 'bg': 'yellow'}],
            'columns': [{'col_key': 'name', 'fg': '#333'}],
            'table': {'fg': '#000'},
        })
        assert tree._state['_cell_styles'][(('ob1', 'e1'), 'seeing')] == (
            ['ob1', 'e1'], 'seeing', 'red', None, None)
        assert tree._state['_row_styles'][('ob2',)] == (
            ['ob2'], None, 'yellow', None)
        assert tree._state['_column_styles']['name'] == (
            'name', '#333', None, None)
        assert tree._state['_table_style'] == ('#000', None, None)

    def test_batch_clear_resets_every_layer(self):
        s = _make_session()
        tree = s.get_widgets().TreeView()
        tree.set_columns([{'label': 'Name', 'key': 'name'}])
        tree.set_tree(_tree())
        tree.set_cell_color(['ob1'], 'name', fg='red')
        tree.set_table_color(fg='#000')
        tree.set_colors({'clear': True})
        assert '_cell_styles' not in tree._state
        assert '_table_style' not in tree._state

    def test_batch_entry_with_no_channels_clears_it(self):
        s = _make_session()
        tree = s.get_widgets().TreeView()
        tree.set_columns([{'label': 'Name', 'key': 'name'}])
        tree.set_tree(_tree())
        tree.set_cell_color(['ob1'], 'name', fg='red')
        tree.set_colors({'cells': [{'path': ['ob1'], 'col_key': 'name'}]})
        assert tree._state['_cell_styles'] == {}


class TestBatchContextManager:
    """``with session.batch():`` coalesces a burst of updates into one
    message, which the browser applies with rendering suspended."""

    def _tree(self):
        s = _make_session()
        tree = s.get_widgets().TreeView()
        tree.set_columns([{'label': 'Name', 'key': 'name'},
                          {'label': 'Seeing', 'key': 'seeing'}])
        tree.set_tree(_tree())
        return s, tree

    def test_calls_are_coalesced_into_one_message(self):
        s, tree = self._tree()
        s.start_recording()
        with s.batch():
            tree.set_cell(['ob1', 'e1'], 'seeing', '1.4')
            tree.set_cell(['ob1', 'e2'], 'seeing', '1.5')
            tree.set_cell_color(['ob1', 'e1'], 'seeing', fg='red')
        s.stop_recording()

        assert s.calls() == []          # nothing sent as a plain call
        batch, = [m for m in s._recorded if m.get('type') == 'batch']
        assert [c['method'] for c in batch['calls']] == [
            'set_cell', 'set_cell', 'set_cell_color']

    def test_widget_batch_is_the_session_batch(self):
        s, tree = self._tree()
        s.start_recording()
        with tree.batch():
            tree.set_cell(['ob1', 'e1'], 'seeing', '1.4')
        s.stop_recording()
        assert len([m for m in s._recorded if m.get('type') == 'batch']) == 1

    def test_model_is_updated_immediately(self):
        """Only the traffic defers -- the model must stay correct, so a
        reconnect landing mid-batch reconstructs properly."""
        s, tree = self._tree()
        with s.batch():
            tree.set_cell(['ob1', 'e1'], 'seeing', '1.4')
            assert tree._state['tree']['ob1']['e1']['seeing'] == '1.4'

    def test_flushes_even_when_the_body_raises(self):
        """The calls are already in the model; dropping them would leave
        the browser diverged from it."""
        s, tree = self._tree()
        s.start_recording()
        with pytest.raises(RuntimeError):
            with s.batch():
                tree.set_cell(['ob1', 'e1'], 'seeing', '1.4')
                raise RuntimeError("boom")
        s.stop_recording()
        batch, = [m for m in s._recorded if m.get('type') == 'batch']
        assert len(batch['calls']) == 1

    def test_nesting_flushes_once_at_the_outermost_exit(self):
        s, tree = self._tree()
        s.start_recording()
        with s.batch():
            tree.set_cell(['ob1', 'e1'], 'seeing', '1.4')
            with s.batch():
                tree.set_cell(['ob1', 'e2'], 'seeing', '1.5')
            assert [m for m in s._recorded if m.get('type') == 'batch'] == []
        s.stop_recording()
        batch, = [m for m in s._recorded if m.get('type') == 'batch']
        assert len(batch['calls']) == 2

    def test_empty_batch_sends_nothing(self):
        s, tree = self._tree()
        s.start_recording()
        with s.batch():
            pass
        s.stop_recording()
        assert s._recorded == []

    def test_a_call_needing_a_result_flushes_first(self):
        """Ordering has to hold: the queued writes must land before the
        query that has to go now."""
        s, tree = self._tree()
        s.start_recording()
        with s.batch():
            tree.set_cell(['ob1', 'e1'], 'seeing', '1.4')
            tree.get_row_count()
        s.stop_recording()
        kinds = [(m.get('type'), m.get('method')) for m in s._recorded]
        assert kinds[0][0] == 'batch'
        assert kinds[1] == ('call', 'get_row_count')

    def test_batch_survives_no_browser(self):
        """With nothing connected the calls are dropped, as usual, but
        the model still updates."""
        s, tree = self._tree()
        with s.batch():
            tree.set_cell(['ob1', 'e1'], 'seeing', '9.9')
        assert tree._state['tree']['ob1']['e1']['seeing'] == '9.9'


class TestBatchFallback:
    """A browser older than the server -- typically a page loaded before
    the server was upgraded -- doesn't know the 'batch' message.  That
    must degrade to individual calls, not fail the caller's update."""

    class _OldBrowserSession(RecordingSession):
        """Rejects 'batch' the way the JS dispatcher's default case
        does, and records everything else."""

        def _send(self, msg):
            if msg.get("type") == "batch":
                raise RuntimeError("Unknown message type: batch")
            return super()._send(msg)

    def _old_browser_tree(self):
        s = _make_session()
        old = self._OldBrowserSession(s._app, 2)
        old._widget_classes = s._app._widget_classes
        s._app._sessions[2] = old
        tree = old.get_widgets().TreeView()
        tree.set_columns([{'label': 'Name', 'key': 'name'},
                          {'label': 'Seeing', 'key': 'seeing'}])
        tree.set_tree(_tree())
        return old, tree

    def test_falls_back_to_individual_calls(self):
        s, tree = self._old_browser_tree()
        s.start_recording()
        with s.batch():
            tree.set_cell(['ob1', 'e1'], 'seeing', '1.4')
            tree.set_cell(['ob1', 'e2'], 'seeing', '1.5')
        s.stop_recording()
        assert [m['method'] for m in s.calls()] == ['set_cell', 'set_cell']

    def test_gives_up_after_the_first_rejection(self):
        """Otherwise every batch costs a failed round-trip first."""
        s, tree = self._old_browser_tree()
        with s.batch():
            tree.set_cell(['ob1', 'e1'], 'seeing', '1.4')
        assert s._batch_supported is False

    def test_reconnect_re_enables_batching(self):
        """The reloaded page may be a current client."""
        s, tree = self._old_browser_tree()
        with s.batch():
            tree.set_cell(['ob1', 'e1'], 'seeing', '1.4')
        assert s._batch_supported is False
        s.add_connection(object())
        assert s._batch_supported is True

    def test_other_errors_still_propagate(self):
        s, tree = self._old_browser_tree()

        def _boom(msg):
            raise RuntimeError("something else went wrong")
        s._send = _boom
        with pytest.raises(RuntimeError, match="something else"):
            with s.batch():
                tree.set_cell(['ob1', 'e1'], 'seeing', '1.4')

    def test_the_model_is_correct_either_way(self):
        s, tree = self._old_browser_tree()
        with s.batch():
            tree.set_cell(['ob1', 'e1'], 'seeing', '1.4')
        assert tree._state['tree']['ob1']['e1']['seeing'] == '1.4'


class TestColourCoalescing:
    """Runs of colour calls inside a batch are folded into a single
    set_colors.  Sending them as separate calls re-renders the widget
    once per cell even when they arrive in one message -- which is why
    the reconnect path (which uses set_colors) is instant while a
    batched per-cell loop was not."""

    def _tree(self):
        s = _make_session()
        tree = s.get_widgets().TreeView()
        tree.set_columns([{'label': 'Name', 'key': 'name'},
                          {'label': 'Seeing', 'key': 'seeing'}])
        tree.set_tree(_tree())
        return s, tree

    def test_a_run_becomes_one_set_colors(self):
        s, tree = self._tree()
        s.start_recording()
        with s.batch():
            tree.set_cell_color(['ob1', 'e1'], 'seeing', fg='red')
            tree.set_cell_color(['ob1', 'e2'], 'seeing', fg='green')
            tree.set_row_color(['ob2'], bg='grey')
        s.stop_recording()
        batch, = [m for m in s._recorded if m.get('type') == 'batch']
        assert [c['method'] for c in batch['calls']] == ['set_colors']
        spec, = batch['calls'][0]['args']
        assert len(spec['cells']) == 2
        assert spec['rows'] == [{'path': ['ob2'], 'fg': None,
                                 'bg': 'grey', 'bold': None}]

    def test_single_colour_call_is_left_alone(self):
        s, tree = self._tree()
        s.start_recording()
        with s.batch():
            tree.set_cell(['ob1', 'e1'], 'seeing', '1.4')
            tree.set_cell_color(['ob1', 'e1'], 'seeing', fg='red')
        s.stop_recording()
        batch, = [m for m in s._recorded if m.get('type') == 'batch']
        assert [c['method'] for c in batch['calls']] == [
            'set_cell', 'set_cell_color']

    def test_interleaved_call_splits_the_runs(self):
        """Ordering against non-colour calls has to be preserved."""
        s, tree = self._tree()
        s.start_recording()
        with s.batch():
            tree.set_cell_color(['ob1', 'e1'], 'seeing', fg='red')
            tree.set_cell_color(['ob1', 'e2'], 'seeing', fg='red')
            tree.set_cell(['ob1', 'e1'], 'seeing', '1.4')
            tree.set_cell_color(['ob2', 'e9'], 'seeing', fg='blue')
            tree.set_cell_color(['ob2'], 'name', fg='blue')
        s.stop_recording()
        batch, = [m for m in s._recorded if m.get('type') == 'batch']
        assert [c['method'] for c in batch['calls']] == [
            'set_colors', 'set_cell', 'set_colors']

    def test_different_widgets_are_not_merged(self):
        s, tree = self._tree()
        other = s.get_widgets().TreeView()
        other.set_columns([{'label': 'Name', 'key': 'name'}])
        other.set_tree(_tree())
        s.start_recording()
        with s.batch():
            tree.set_cell_color(['ob1', 'e1'], 'seeing', fg='red')
            other.set_cell_color(['ob1'], 'name', fg='red')
        s.stop_recording()
        batch, = [m for m in s._recorded if m.get('type') == 'batch']
        assert [c['method'] for c in batch['calls']] == [
            'set_cell_color', 'set_cell_color']

    def test_table_layer_folds_in(self):
        s, tree = self._tree()
        s.start_recording()
        with s.batch():
            tree.set_column_color('name', fg='#333')
            tree.set_table_color(fg='#000')
            tree.set_cell_color(['ob1', 'e1'], 'seeing', fg='red')
        s.stop_recording()
        batch, = [m for m in s._recorded if m.get('type') == 'batch']
        spec, = batch['calls'][0]['args']
        assert spec['columns'] == [{'col_key': 'name', 'fg': '#333',
                                    'bg': None, 'bold': None}]
        assert spec['table'] == {'fg': '#000', 'bg': None, 'bold': None}
        assert len(spec['cells']) == 1

    def test_model_is_unaffected_by_coalescing(self):
        """The maps are filled as each call is made, before the flush
        rewrites the wire form -- so a later reconnect is unchanged."""
        s, tree = self._tree()
        with s.batch():
            tree.set_cell_color(['ob1', 'e1'], 'seeing', fg='red')
            tree.set_cell_color(['ob1', 'e2'], 'seeing', fg='green')
        assert len(tree._state['_cell_styles']) == 2
