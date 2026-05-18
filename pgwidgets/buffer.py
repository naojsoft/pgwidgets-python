"""Typed binary buffer descriptors for the remote interface.

When a method on the browser side expects a typed n-dimensional array
(image pixels, scientific data, vertex buffers, …) the Python side can
wrap the raw bytes in a :class:`Buffer` so the receiver gets a typed
view with shape/dtype information without each method re-implementing
its own ad-hoc convention.

Example::

    from pgwidgets import Buffer

    pixels = bytes(...)            # 2048 * 2048 * 4 bytes
    buf = Buffer(pixels,
                 shape=(2048, 2048, 4),
                 dtype="uint8")
    viewer.load_buffer(buf, [2048, 2048], cache)

A widget method's binding can recognize :class:`Buffer` args and ship
them via the chunked binary transport, attaching ``shape`` and
``dtype`` to the chunk announce so the JavaScript receiver builds the
correct typed array (``Uint8Array``, ``Float32Array``, …) before
dispatching to the method.
"""

from typing import Sequence, Union


# Subset of NumPy / DLPack dtype names mapped to the JavaScript
# TypedArray constructor on the receiving side.
_DTYPES = frozenset({
    "uint8", "uint16", "uint32",
    "int8", "int16", "int32",
    "float32", "float64",
})

_DTYPE_BYTES = {
    "uint8":   1,
    "int8":    1,
    "uint16":  2,
    "int16":   2,
    "uint32":  4,
    "int32":   4,
    "float32": 4,
    "float64": 8,
}


class Buffer:
    """Raw bytes plus shape + dtype, addressable as a typed array.

    Parameters
    ----------
    data : bytes-like
        ``bytes``, ``bytearray``, ``memoryview``, or anything that
        exposes ``__bytes__`` / the buffer protocol.  Converted to
        ``bytes`` at construction time.
    shape : tuple of int
        Logical dimensions of the array, e.g. ``(height, width, 4)``
        for an RGBA8 image.  Each entry must be a positive integer.
    dtype : str
        One of ``"uint8"``, ``"uint16"``, ``"uint32"``, ``"int8"``,
        ``"int16"``, ``"int32"``, ``"float32"``, ``"float64"``.
        Default ``"uint8"``.

    Raises
    ------
    TypeError
        If ``data`` is not bytes-like.
    ValueError
        If ``dtype`` is unsupported, ``shape`` contains non-positive
        entries, or the byte length disagrees with
        ``prod(shape) * itemsize`` (rounded up for non-evenly divisible
        cases).
    """

    __slots__ = ("data", "shape", "dtype")

    def __init__(self,
                 data: Union[bytes, bytearray, memoryview],
                 shape: Sequence[int],
                 dtype: str = "uint8") -> None:
        if dtype not in _DTYPES:
            raise ValueError(
                f"Buffer: unsupported dtype {dtype!r}; "
                f"supported: {sorted(_DTYPES)}")
        try:
            data = bytes(data)
        except TypeError as e:
            raise TypeError(
                f"Buffer: data must be bytes-like, got "
                f"{type(data).__name__}") from e
        shape_tuple = tuple(int(d) for d in shape)
        if not shape_tuple or any(d <= 0 for d in shape_tuple):
            raise ValueError(
                f"Buffer: shape must be a non-empty tuple of "
                f"positive ints, got {shape!r}")
        itemsize = _DTYPE_BYTES[dtype]
        expected = itemsize
        for d in shape_tuple:
            expected *= d
        if len(data) != expected:
            raise ValueError(
                f"Buffer: data length {len(data)} bytes does not "
                f"match shape {shape_tuple} * dtype {dtype} "
                f"(expected {expected} bytes)")
        self.data = data
        self.shape = shape_tuple
        self.dtype = dtype

    def __len__(self) -> int:
        return len(self.data)

    def __repr__(self) -> str:
        return (f"Buffer(<{len(self.data)} bytes>, "
                f"shape={self.shape}, dtype={self.dtype!r})")


def is_buffer(obj) -> bool:
    """Return True if *obj* is a :class:`Buffer` instance.

    Convenience for code that branches on whether an argument carries
    binary-payload metadata.
    """
    return isinstance(obj, Buffer)
