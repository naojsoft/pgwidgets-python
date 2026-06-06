"""
Tests for ``pgwidgets.sync.widget._resolve_kwargs``.

The resolver is on every generated method (``set_color`` /
``add_widget`` / etc.) and is responsible for merging a caller's
``kwargs`` into the positional ``args`` list the protocol layer
expects.  Two notable shapes:

* **Skipped-positional kwargs.** ``set_color(fg='red')`` against
  ``['bg', 'fg']`` should land ``'red'`` in the ``fg`` slot and
  leave ``bg`` as ``None``.  Before commit 60d043f this raised
  ``TypeError`` because the resolver insisted that every kwarg
  match a still-unfilled trailing parameter.
* **Options-bundle pass-through.** When the last declared param
  is ``"options"``, leftover kwargs are bundled into a dict for
  that slot (the ``add_widget(child, title="Tab 1")`` shape).
"""

import pytest

from pgwidgets.sync.widget import _resolve_kwargs


# ----- Skipped-positional kwargs ------------------------------

def test_set_color_fg_only_skips_bg():
    """``set_color(fg='red')`` should resolve to ``(None, 'red')``
    -- the bg slot left as the default."""
    args = _resolve_kwargs(
        'set_color', ['bg', 'fg'], (), {'fg': 'red'})
    assert args == (None, 'red')


def test_set_color_bg_only_pads_remaining_slot():
    """``set_color(bg='blue')`` against ``['bg', 'fg']`` puts
    ``'blue'`` in slot 0; the trailing ``fg`` slot is padded with
    ``None`` so the protocol receives a positional argument for
    every declared parameter."""
    args = _resolve_kwargs(
        'set_color', ['bg', 'fg'], (), {'bg': 'blue'})
    assert args == ('blue', None)


def test_set_color_both_kwargs_order_independent():
    """Kwargs in any order land in the correct positional slots."""
    args = _resolve_kwargs(
        'set_color', ['bg', 'fg'], (), {'fg': 'red', 'bg': 'blue'})
    assert args == ('blue', 'red')


def test_set_color_positional_and_skipped_kwarg():
    """Positional args fill leading slots; kwargs fill trailing
    ones with placeholders in between."""
    args = _resolve_kwargs(
        'set_row_color',
        ['path', 'fg', 'bg', 'bold'],
        ([0],),
        {'bold': True})
    assert args == ([0], None, None, True)


# ----- Options-bundle behaviour -------------------------------

def test_options_bundles_remaining_kwargs():
    """When the last declared param is ``"options"``, leftover
    kwargs end up in the options dict."""
    args = _resolve_kwargs(
        'add_widget',
        ['child', 'options'],
        ('CHILD',),
        {'title': 'Tab 1', 'closable': True})
    assert args[0] == 'CHILD'
    assert args[1] == {'title': 'Tab 1', 'closable': True}


def test_options_merges_existing_dict():
    """If the options slot is already a dict (passed
    positionally), kwargs merge into it."""
    args = _resolve_kwargs(
        'add_widget',
        ['child', 'options'],
        ('CHILD', {'title': 'Pre'}),
        {'closable': True})
    assert args == ('CHILD', {'title': 'Pre', 'closable': True})


def test_options_string_becomes_text_dict():
    """A string in the ``options`` slot (e.g. ``add_action('Save',
    toggle=True)``) is converted into ``{'text': ..., **kwargs}``
    to match the JS side."""
    args = _resolve_kwargs(
        'add_action',
        ['options'],
        ('Save',),
        {'toggle': True})
    assert args == ({'text': 'Save', 'toggle': True},)


def test_bundle_only_triggers_for_literal_options_param():
    """The bundle hook is gated on the *literal* name
    ``"options"`` -- a different name like
    ``text_or_options`` doesn't activate it, and unknown kwargs
    raise."""
    with pytest.raises(TypeError):
        _resolve_kwargs(
            'add_action',
            ['text_or_options'],
            ('Save',),
            {'toggle': True})


# ----- Error paths --------------------------------------------

def test_unknown_kwarg_raises_when_no_options_slot():
    """Unrecognised kwargs that don't match any declared param --
    and there's no ``options`` last-param to absorb them -- raise
    ``TypeError``."""
    with pytest.raises(TypeError) as exc_info:
        _resolve_kwargs(
            'set_color', ['bg', 'fg'], (), {'mystery': 1})
    msg = str(exc_info.value)
    assert 'set_color' in msg
    assert 'mystery' in msg


def test_empty_kwargs_returns_args_unchanged():
    """No kwargs is the common fast path: return positional args
    untouched (preserves the original tuple identity-ish; we just
    care that the value matches)."""
    args = _resolve_kwargs(
        'set_color', ['bg', 'fg'], ('blue', 'red'), {})
    assert args == ('blue', 'red')


def test_no_param_names_no_kwargs():
    """A no-arg method with no kwargs returns the input tuple."""
    args = _resolve_kwargs('clear', [], (), {})
    assert args == ()
