"""
Tests for the custom-font API on ``Application``.

Exercises the in-memory registry, the message-shape produced for
the JS side, the HTTP-route byte lookup, and ``set_default_font``
state transitions.  These are pure unit tests -- no server is
started; we poke at the underlying methods directly so the tests
stay fast and platform-independent.
"""

from pgwidgets.sync.application import Application


# ----- Test fixture: a synthetic font ------------------------

# Real TTF magic-number prefix so the bytes look like a font to
# anyone snooping the wire.  We don't actually parse it -- the
# Application stores opaque bytes and the JS side hands them to
# the browser's FontFace API.
SYNTHETIC_FONT_BYTES = b'\x00\x01\x00\x00' + b'fake-ttf-payload' * 64


def _make_app():
    """Build a minimal Application without starting any servers.
    All the font methods we test are sync and operate on
    in-memory state, so they don't need a running event loop."""
    return Application(http_server=False)


# ----- register_font: registry + message shape ---------------

def test_register_font_stores_bytes_and_returns_id():
    app = _make_app()
    fid = app.register_font('Roboto', SYNTHETIC_FONT_BYTES)
    assert isinstance(fid, int)
    assert fid > 0
    assert len(app._fonts) == 1
    assert app._fonts[0]['family'] == 'Roboto'
    assert app._fonts[0]['bytes'] == SYNTHETIC_FONT_BYTES


def test_register_font_default_weight_and_style():
    """Defaults are 'normal' / 'normal' when no kwargs given."""
    app = _make_app()
    app.register_font('Roboto', SYNTHETIC_FONT_BYTES)
    entry = app._fonts[0]
    assert entry['weight'] == 'normal'
    assert entry['style'] == 'normal'


def test_register_font_accepts_weight_and_style():
    app = _make_app()
    app.register_font(
        'Roboto', SYNTHETIC_FONT_BYTES,
        weight='bold', style='italic')
    entry = app._fonts[0]
    assert entry['weight'] == 'bold'
    assert entry['style'] == 'italic'


def test_register_font_assigns_unique_ids():
    """Successive registrations get monotonically increasing
    ids; this is the path component of the URL the JS side
    fetches from, so two registrations must not collide."""
    app = _make_app()
    fid1 = app.register_font('A', SYNTHETIC_FONT_BYTES)
    fid2 = app.register_font('B', SYNTHETIC_FONT_BYTES + b'\x00')
    assert fid1 != fid2
    assert fid2 > fid1


def test_register_font_same_family_multiple_faces():
    """Same family with different weights / styles produces
    distinct entries (each one becomes its own ``@font-face``)."""
    app = _make_app()
    app.register_font('Roboto', SYNTHETIC_FONT_BYTES)
    app.register_font('Roboto', SYNTHETIC_FONT_BYTES + b'\x01',
                      weight='bold')
    app.register_font('Roboto', SYNTHETIC_FONT_BYTES + b'\x02',
                      style='italic')
    assert len(app._fonts) == 3
    weights = {e['weight'] for e in app._fonts}
    styles = {e['style'] for e in app._fonts}
    assert weights == {'normal', 'bold'}
    assert styles == {'normal', 'italic'}


def test_register_font_message_shape():
    """The ``register-font`` message broadcast to the JS side has
    the expected keys and URL form."""
    app = _make_app()
    fid = app.register_font('Roboto', SYNTHETIC_FONT_BYTES,
                            weight='bold', style='italic')
    msg = app._font_register_msg(app._fonts_by_id[fid])
    assert msg['type'] == 'register-font'
    assert msg['id'] == fid
    assert msg['family'] == 'Roboto'
    assert msg['weight'] == 'bold'
    assert msg['style'] == 'italic'
    assert msg['url'] == f'/_pgwidgets/font/{fid}'


# ----- HTTP-route byte lookup --------------------------------

def test_get_font_bytes_returns_bytes_and_mime():
    """``_get_font_bytes(id)`` is the HTTP handler's lookup
    function -- it returns the raw bytes and a content-type."""
    app = _make_app()
    fid = app.register_font('Roboto', SYNTHETIC_FONT_BYTES)
    data, mime = app._get_font_bytes(fid)
    assert data == SYNTHETIC_FONT_BYTES
    assert mime == 'font/ttf'


def test_get_font_bytes_unknown_id_returns_none():
    """An unknown id yields ``(None, None)`` so the HTTP handler
    can return a 404 cleanly."""
    app = _make_app()
    data, mime = app._get_font_bytes(99999)
    assert data is None
    assert mime is None


def test_get_font_bytes_mime_from_path_extension(tmp_path):
    """Loading from a path picks the MIME from the file
    extension."""
    app = _make_app()
    woff_path = tmp_path / 'face.woff2'
    woff_path.write_bytes(SYNTHETIC_FONT_BYTES)
    fid = app.register_font('Roboto', str(woff_path))
    _data, mime = app._get_font_bytes(fid)
    assert mime == 'font/woff2'


# ----- set_default_font: state + message ---------------------

def test_set_default_font_stores_state():
    app = _make_app()
    app.set_default_font('Roboto', size=14, weight='bold')
    d = app._default_font
    assert d['family'] == 'Roboto'
    assert d['size'] == 14.0
    assert d['weight'] == 'bold'
    assert d['style'] is None  # unset


def test_set_default_font_clear_with_none_family():
    """``family=None`` clears the default."""
    app = _make_app()
    app.set_default_font('Roboto', size=14)
    assert app._default_font is not None
    app.set_default_font(None)
    assert app._default_font is None


def test_set_default_font_message_shape():
    app = _make_app()
    app.set_default_font('Roboto', size=14)
    msg = app._font_default_msg()
    assert msg['type'] == 'set-default-font'
    assert msg['font']['family'] == 'Roboto'
    assert msg['font']['size'] == 14.0


def test_set_default_font_cleared_message_shape():
    """When the default is cleared, the message carries
    ``font: None`` so the JS handler removes the managed
    ``<style>`` element."""
    app = _make_app()
    app.set_default_font(None)
    msg = app._font_default_msg()
    assert msg['type'] == 'set-default-font'
    assert msg['font'] is None
