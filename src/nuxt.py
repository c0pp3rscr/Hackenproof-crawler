"""Decoder for Nuxt 3's ``__NUXT_DATA__`` payload.

Nuxt serialises server state with `devalue`, which produces a *flat* JSON array.
Every value in the tree is stored once in that array; references between values
are encoded as integer indices into the array. A handful of two-element arrays
whose first element is a string tag (``["Reactive", 5]`` and friends) are
reactivity wrappers that we transparently unwrap.

The public helpers here take the raw HTML of a page and hand back an ordinary
nested ``dict``/``list`` structure.
"""

from __future__ import annotations

import json
import re
from typing import Any

# Reactivity wrappers emitted by Nuxt whose payload is the value at index[1].
_WRAPPER_TAGS = {
    "Reactive",
    "ShallowReactive",
    "Ref",
    "ShallowRef",
    "EmptyRef",
    "EmptyShallowRef",
}

_NUXT_RE = re.compile(
    r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)


class NuxtDataNotFound(ValueError):
    """Raised when a page contains no ``__NUXT_DATA__`` script block."""


def extract_nuxt_array(html: str) -> list:
    """Return the raw devalue array embedded in ``html``.

    Raises :class:`NuxtDataNotFound` if the marker is missing (which usually
    means we were served a Cloudflare challenge page rather than the app).
    """
    match = _NUXT_RE.search(html)
    if not match:
        raise NuxtDataNotFound("no __NUXT_DATA__ script block in response")
    return json.loads(match.group(1))


def _resolve(arr: list, idx: Any, cache: dict) -> Any:
    """Resolve a single devalue reference into a concrete Python value."""
    # Only plain integers are references; bools are ints in Python so exclude them.
    if isinstance(idx, bool) or not isinstance(idx, int):
        return idx
    if idx == -1:  # devalue encodes ``undefined`` as -1
        return None
    if idx in cache:
        return cache[idx]

    node = arr[idx]

    if isinstance(node, dict):
        out: dict = {}
        cache[idx] = out  # seed cache first so cycles terminate
        for key, ref in node.items():
            out[key] = _resolve(arr, ref, cache)
        return out

    if isinstance(node, list):
        if node and isinstance(node[0], str):
            tag = node[0]
            if tag in _WRAPPER_TAGS:
                value = _resolve(arr, node[1], cache)
                cache[idx] = value
                return value
            if tag == "Set":
                out_list = [_resolve(arr, ref, cache) for ref in node[1:]]
                cache[idx] = out_list
                return out_list
            if tag == "Map":
                items = node[1:]
                out_map = {
                    _resolve(arr, items[i], cache): _resolve(arr, items[i + 1], cache)
                    for i in range(0, len(items) - 1, 2)
                }
                cache[idx] = out_map
                return out_map
            # Unknown string-led array: fall through and treat as a plain list.
        out_list = []
        cache[idx] = out_list
        for ref in node:
            out_list.append(_resolve(arr, ref, cache))
        return out_list

    # Primitive literal (str / number / bool / None).
    cache[idx] = node
    return node


def parse_nuxt_data(html: str) -> Any:
    """Extract and fully resolve the ``__NUXT_DATA__`` tree from ``html``."""
    arr = extract_nuxt_array(html)
    return _resolve(arr, 0, {})
