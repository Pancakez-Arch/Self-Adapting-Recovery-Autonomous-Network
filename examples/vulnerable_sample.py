"""A deliberately flawed module used by the demo.

SARAN's scanners flag the issues below and its healing loop can repair the
mechanically-fixable ones. Do not use this code for anything real.
"""

import hashlib
import yaml


def load_config(raw):
    # Unsafe: yaml.load can construct arbitrary Python objects.
    return yaml.load(raw)


def checksum(data):
    # Weak hash for a security-sensitive checksum.
    return hashlib.md5(data).hexdigest()


def risky_parse(text):
    try:
        return int(text)
    except:  # noqa - bare except swallows everything
        return None
