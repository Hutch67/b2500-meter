"""
Web-based configuration editor for AstraMeter.

Provides helpers and an HTML page for reading and editing config.ini via a browser.
"""

import configparser
import contextlib
import errno
import importlib.resources
import json
import os
import shutil
import tempfile
import threading
from collections import OrderedDict

from configupdater import ConfigUpdater


def _load_config_editor_html() -> str:
    """Load the config editor HTML from the bundled static file."""
    return (
        importlib.resources.files("astrameter")
        .joinpath("static/config_editor.html")
        .read_text("utf-8")
    )


CONFIG_EDITOR_HTML: str = _load_config_editor_html()


def read_config_as_dict(config_path: str) -> tuple[dict, list]:
    """
    Read config.ini and return (sections_dict, ordered_section_list).

    The sections_dict maps section names to dicts of key->value.
    Case of keys is preserved.
    """
    cfg = configparser.RawConfigParser(dict_type=OrderedDict)
    cfg.optionxform = str  # type: ignore[assignment]  # preserve key case
    if os.path.exists(config_path):
        cfg.read(config_path)
    sections: dict[str, dict[str, str]] = {}
    order = []
    for section in cfg.sections():
        sections[section] = dict(cfg.items(section))
        order.append(section)
    return sections, order


_CONFIG_WRITE_LOCK = threading.Lock()


def _atomic_write_lines(config_path: str, lines: list) -> None:
    """Write *lines* to *config_path* atomically via a temp-file + os.replace.

    Container environments (Docker bind-mounts, overlayfs) can block rename(2)
    with EBUSY/EACCES even when the file is otherwise writable.  Two fallbacks
    are tried in order:

    1. ``shutil.copyfile`` — overwrites the destination in-place.  Handles the
       common Docker bind-mount case where rename is blocked but the file is
       open-for-write accessible.
    2. ``os.unlink`` + ``os.replace`` — removes the destination first (creating
       an overlayfs whiteout), then renames the temp file into place.  Handles
       overlayfs setups where the file lives only in the read-only lower layer.

    If all strategies fail a :exc:`PermissionError` is raised with an
    actionable message.
    """
    dir_name = os.path.dirname(config_path) or "."
    with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False) as tmp:
        tmp.writelines(lines)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = tmp.name
    # errno values that indicate a filesystem/mount restriction rather than a
    # genuine logic error.  EBUSY = mount point, EPERM/EACCES = permission
    # denied (different kernels/filesystems use different codes for the same
    # bind-mount restriction).
    _RETRYABLE = (errno.EBUSY, errno.EPERM, errno.EACCES)

    try:
        os.replace(tmp_path, config_path)
        return
    except OSError as exc:
        if exc.errno not in _RETRYABLE:
            raise

    # rename(2) was blocked — common on Docker bind-mounts and overlayfs.
    # Try strategies in order, stopping as soon as one succeeds.
    transferred = False
    # temp_consumed tracks whether os.replace() has moved the temp file into
    # place (consuming it).  Strategy 1 (copyfile) leaves the temp file on disk
    # and lets the finally block remove it; Strategy 2 (unlink+replace) renames
    # the temp file, so the finally block must skip the unlink.
    temp_consumed = False
    try:
        # Strategy 1: overwrite in-place (open destination for writing).
        try:
            shutil.copyfile(tmp_path, config_path)
            transferred = True
        except OSError as exc2:
            if exc2.errno not in _RETRYABLE:
                raise
        # Strategy 2: unlink the bind-mounted file then rename the temp file.
        # Works on overlayfs where the destination cannot be opened for writing
        # but can be removed (a whiteout is created in the upper layer).
        if not transferred:
            try:
                os.unlink(config_path)
                os.replace(tmp_path, config_path)
                temp_consumed = True
                transferred = True
            except OSError as exc3:
                if exc3.errno not in _RETRYABLE:
                    raise
        if not transferred:
            raise PermissionError(
                f"Cannot write to {config_path!r}: the file is not writable. "
                "Check that the add-on has write access to the config file "
                "(e.g. the mapped volume is not read-only)."
            )
    finally:
        if not temp_consumed:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)


def _validate_config_payload(sections: dict, order: list) -> None:
    """Raise ValueError if any section name, key, or value would corrupt the INI."""
    if not isinstance(order, list) or any(not isinstance(s, str) for s in order):
        raise ValueError("'order' must be a list of section names")
    if len(order) != len(set(order)):
        raise ValueError("'order' contains duplicate section names")
    for section, pairs in sections.items():
        if (
            not isinstance(section, str)
            or not section
            or any(ch in section for ch in "\r\n]")
        ):
            raise ValueError(f"Invalid section name: {section!r}")
        if not isinstance(pairs, dict):
            raise ValueError(f"Section {section!r} must map to an object")
        for key, value in pairs.items():
            if not isinstance(key, str) or not key or any(ch in key for ch in "\r\n"):
                raise ValueError(f"Invalid key in section {section!r}: {key!r}")
            if not isinstance(value, str) or any(ch in value for ch in "\r\n"):
                raise ValueError(f"Invalid value for {section!r}.{key!r}")


def write_config_from_dict(config_path: str, sections: dict, order: list) -> None:
    """
    Write config.ini from the provided sections dict, preserving existing comments.

    If *config_path* already exists, comment lines (``#`` / ``;``) and blank
    lines are kept in their original positions while key values are updated
    in-place.  Keys absent from *sections* are removed; keys that are new are
    appended at the end of their section.  Sections absent from *sections* are
    dropped.  If the file does not yet exist it is written from scratch.

    ``sections`` maps section names to dicts of key->value.
    ``order`` controls the section order; sections not listed are appended last.
    """
    _validate_config_payload(sections, order)
    write_order = list(order) + [s for s in sections if s not in order]

    with _CONFIG_WRITE_LOCK:
        updater = ConfigUpdater()
        updater.optionxform = str  # type: ignore[assignment]  # preserve key case

        if os.path.exists(config_path):
            updater.read(config_path)

        # Update existing sections and add new keys / remove stale keys.
        for section_name, new_pairs in sections.items():
            if updater.has_section(section_name):
                for key in set(updater.options(section_name)) - new_pairs.keys():
                    updater.remove_option(section_name, key)
            else:
                updater.add_section(section_name)
            for key, value in new_pairs.items():
                updater.set(section_name, key, value)

        # Remove sections not present in the incoming payload.
        for section_name in list(updater.sections()):
            if section_name not in sections:
                updater.remove_section(section_name)

        # Re-order sections to match *write_order* by rebuilding from
        # detached copies.  Only needed when the order actually differs.
        current_order = updater.sections()
        desired = [s for s in write_order if s in sections]
        if current_order != desired:
            detached = {
                name: updater[name].detach() for name in list(updater.sections())
            }
            for name in desired:
                updater.add_section(detached[name])

        _atomic_write_lines(config_path, [str(updater)])


def validate_config(config_path: str) -> None:
    """Trial-load the config file the same way the main service does.

    Raises on any parse or semantic error (bad section, missing required
    key, invalid value, etc.) so the caller can roll back before the
    service tries to restart with a broken config.
    """
    import configparser as _cp
    from collections import OrderedDict

    from astrameter.config.config_loader import read_all_powermeter_configs

    cfg = _cp.ConfigParser(dict_type=OrderedDict, interpolation=None)
    if not cfg.read(config_path):
        raise ValueError(f"Cannot read config file: {config_path}")
    read_all_powermeter_configs(cfg)


def config_to_json(config_path: str) -> str:
    """Return the config as a JSON string suitable for the web UI."""
    sections, order = read_config_as_dict(config_path)
    return json.dumps({"sections": sections, "order": order})
