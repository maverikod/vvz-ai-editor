"""Reality checks for ``adapter.feature_flag`` (G-029/T-001/A-008, C-023).

This is the rollback lever for the staged AI Editor migration: an operator flips
``AI_EDITOR_FEATURE_FLAG`` (or the file it can point at) and the process picks a
different engine for a command with no code change. Its failure modes matter more
than its happy path, so this suite pins:

* precedence -- inline env beats the config file beats the in-process default, and
  an unconfigured process is LEGACY (the safe, pre-migration default);
* resolution order inside one config -- ``"command:format_id"`` beats ``"command"``
  beats ``default_mode``;
* every malformed input fails LOUDLY with :class:`FeatureFlagConfigError`, located
  by source and field, never a silent fallback;
* the process-global cache -- ``initialize`` caches, ``force=True`` re-reads,
  ``reset()`` clears -- and passing an explicit ``config=`` never touches it, which
  is what makes concurrent callers with different configs isolated from each other;
* the module is pure stdlib: it imports nothing from ``ai_editor`` or
  ``tree_engine``, which is what lets the flag be read in any process.

No mock of the subject: every test drives the real module functions against real
environment mappings and real files under ``tmp_path``. An autouse fixture snapshots
and restores the module's private cache around every test, so the suite is exactly
as order-independent as the module promises -- proven by running it shuffled (see
the verification note in the commit this file ships with).
"""

from __future__ import annotations

import ast
import json
import threading
from pathlib import Path
from typing import Dict

import pytest

import adapter.feature_flag as feature_flag
from adapter.feature_flag import (
    DEFAULT_MODE,
    ENV_FILE,
    ENV_INLINE,
    FeatureFlagConfig,
    FeatureFlagConfigError,
    FeatureFlagMode,
    current_config,
    effective_mode,
    initialize,
    load_config,
    reset,
    should_run,
)

LEGACY, ADAPTER, COMPARISON = (
    FeatureFlagMode.LEGACY, FeatureFlagMode.ADAPTER, FeatureFlagMode.COMPARISON)


@pytest.fixture(autouse=True)
def _isolated_global_state():
    """Snapshot the module's private cache before the test and restore the EXACT
    pre-test value after it (not always ``None``) -- so a shuffled run never depends
    on which test happened to run before it, and this suite never leaks state into
    tests outside this file either."""
    saved = feature_flag._config
    reset()
    yield
    feature_flag._config = saved


def _cfg(default_mode: FeatureFlagMode, **overrides: FeatureFlagMode) -> FeatureFlagConfig:
    return FeatureFlagConfig(source="test", default_mode=default_mode, overrides=overrides)


# -- default: unconfigured process is legacy ----------------------------------

def test_default_mode_is_legacy_when_no_configuration():
    config = load_config(env={})
    assert config.default_mode == LEGACY
    assert config.overrides == {}
    assert config.source == "in-process-default"


def test_initialize_from_real_environment_defaults_to_legacy(monkeypatch):
    monkeypatch.delenv(ENV_INLINE, raising=False)
    monkeypatch.delenv(ENV_FILE, raising=False)
    config = initialize()
    assert config.default_mode == LEGACY
    assert current_config() is config  # cached: the same object, not a re-read


# -- precedence: inline > file > in-process default ---------------------------

def test_inline_env_beats_file(tmp_path: Path):
    file_path = tmp_path / "flag.json"
    file_path.write_text(json.dumps({"default_mode": "adapter"}), encoding="utf-8")
    env = {ENV_INLINE: json.dumps({"default_mode": "comparison"}), ENV_FILE: str(file_path)}
    config = load_config(env=env)
    assert config.default_mode == COMPARISON
    assert config.source == f"env:{ENV_INLINE}"


def test_inline_env_beats_file_even_when_file_is_missing(tmp_path: Path):
    # Proves the file is never even opened once inline is present.
    env = {ENV_INLINE: json.dumps({"default_mode": "legacy"}),
           ENV_FILE: str(tmp_path / "does_not_exist.json")}
    config = load_config(env=env)
    assert config.default_mode == LEGACY


def test_file_beats_inprocess_default(tmp_path: Path):
    file_path = tmp_path / "flag.json"
    file_path.write_text(json.dumps({"default_mode": "adapter"}), encoding="utf-8")
    config = load_config(env={ENV_FILE: str(file_path)})
    assert config.default_mode == ADAPTER
    assert config.source == f"file:{file_path}"


def test_inprocess_default_when_neither_env_set():
    config = load_config(env={})
    assert config.default_mode == DEFAULT_MODE == LEGACY
    assert config.source == "in-process-default"


# -- global and per-command mode selection -------------------------------------

@pytest.mark.parametrize("mode", [LEGACY, ADAPTER, COMPARISON])
def test_global_mode_selection(mode: FeatureFlagMode):
    config = _cfg(mode)
    assert effective_mode("universal_file_search", config=config) == mode


@pytest.mark.parametrize("mode", [LEGACY, ADAPTER, COMPARISON])
def test_per_command_mode_selection(mode: FeatureFlagMode):
    other = ADAPTER if mode != ADAPTER else COMPARISON
    config = _cfg(other, universal_file_search=mode)
    assert effective_mode("universal_file_search", config=config) == mode
    # An unrelated command is untouched and still gets the global default.
    assert effective_mode("universal_file_open", config=config) == other


def test_per_command_mode_overrides_global_mode():
    config = _cfg(LEGACY, universal_file_write=COMPARISON)
    assert effective_mode("universal_file_write", config=config) == COMPARISON
    assert effective_mode("universal_file_open", config=config) == LEGACY


# -- composite "command:format_id" beats "command" beats default_mode ---------

def test_composite_override_beats_bare_command_override():
    config = _cfg(LEGACY, **{
        "universal_file_search": ADAPTER,
        "universal_file_search:python": COMPARISON,
    })
    assert effective_mode("universal_file_search", "python", config=config) == COMPARISON
    # A different format falls through to the bare-command override.
    assert effective_mode("universal_file_search", "bsl", config=config) == ADAPTER
    # No format_id at all also falls through to the bare-command override.
    assert effective_mode("universal_file_search", config=config) == ADAPTER


def test_bare_command_override_beats_default_mode():
    config = _cfg(LEGACY, universal_file_search=COMPARISON)
    assert effective_mode("universal_file_search", "python", config=config) == COMPARISON


def test_default_mode_used_when_nothing_more_specific_matches():
    config = _cfg(COMPARISON)
    assert effective_mode("unrelated_command", "python", config=config) == COMPARISON


# -- routing: should_run is true for exactly the effective mode ---------------

@pytest.mark.parametrize("mode", [LEGACY, ADAPTER, COMPARISON])
def test_mode_routes_to_exactly_one_implementation(mode: FeatureFlagMode):
    config = _cfg(mode)
    for candidate in FeatureFlagMode:
        assert should_run("universal_file_search", candidate, config=config) == (
            candidate == mode)


def test_should_run_respects_format_id_composite():
    config = _cfg(LEGACY, **{"universal_file_search:python": COMPARISON})
    assert should_run("universal_file_search", COMPARISON, "python", config=config)
    assert not should_run("universal_file_search", COMPARISON, "bsl", config=config)
    assert should_run("universal_file_search", LEGACY, "bsl", config=config)


# -- runtime query of the effective mode ---------------------------------------

def test_effective_mode_queryable_at_runtime_without_dispatch():
    config = _cfg(COMPARISON)
    assert effective_mode("any_command_never_dispatched", config=config) == COMPARISON


def test_effective_mode_respects_global_setting():
    config = _cfg(ADAPTER)
    assert effective_mode("unmapped_command", config=config) == ADAPTER


def test_effective_mode_respects_per_command_setting():
    config = _cfg(LEGACY, universal_file_write=COMPARISON)
    assert effective_mode("universal_file_write", config=config) == COMPARISON
    assert effective_mode("universal_file_open", config=config) == LEGACY


# -- malformed input fails loudly, never silently ------------------------------

def test_invalid_json_raises_located_error():
    with pytest.raises(FeatureFlagConfigError) as excinfo:
        load_config(env={ENV_INLINE: "{not json"})
    message = str(excinfo.value)
    assert ENV_INLINE in message
    assert "invalid JSON" in message


def test_non_object_payload_raises():
    with pytest.raises(FeatureFlagConfigError, match="must be a JSON object"):
        load_config(env={ENV_INLINE: json.dumps([1, 2, 3])})


def test_unknown_top_level_key_raises():
    with pytest.raises(FeatureFlagConfigError) as excinfo:
        load_config(env={ENV_INLINE: json.dumps({"defualt_mode": "legacy"})})
    message = str(excinfo.value)
    assert ENV_INLINE in message
    assert "unknown key" in message


def test_unknown_mode_in_default_mode_raises():
    with pytest.raises(FeatureFlagConfigError) as excinfo:
        load_config(env={ENV_INLINE: json.dumps({"default_mode": "turbo"})})
    message = str(excinfo.value)
    assert "default_mode" in message
    assert "turbo" in message
    assert excinfo.value.details["value"] == "turbo"


def test_unknown_mode_in_override_raises():
    with pytest.raises(FeatureFlagConfigError) as excinfo:
        load_config(env={ENV_INLINE: json.dumps(
            {"overrides": {"universal_file_search": "turbo"}})})
    message = str(excinfo.value)
    assert "overrides" in message
    assert "universal_file_search" in message
    assert "turbo" in message


def test_non_string_mode_value_raises():
    with pytest.raises(FeatureFlagConfigError, match="must be a string"):
        load_config(env={ENV_INLINE: json.dumps({"default_mode": 1})})


def test_overrides_not_an_object_raises():
    with pytest.raises(FeatureFlagConfigError, match="overrides must be a JSON object"):
        load_config(env={ENV_INLINE: json.dumps({"overrides": ["legacy"]})})


def test_missing_config_file_raises_located_error(tmp_path: Path):
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(FeatureFlagConfigError) as excinfo:
        load_config(env={ENV_FILE: str(missing)})
    message = str(excinfo.value)
    assert str(missing) in message
    assert "could not read config file" in message


def test_unreadable_config_file_raises(tmp_path: Path):
    # A real, unreadable-as-a-file path: a directory where the config was expected.
    directory_as_file = tmp_path / "flag_dir.json"
    directory_as_file.mkdir()
    with pytest.raises(FeatureFlagConfigError, match="could not read config file"):
        load_config(env={ENV_FILE: str(directory_as_file)})


# -- mode changes need no call-site modification -------------------------------

def test_mode_change_requires_no_call_site_modification():
    """The call site is one line, ``effective_mode(command)``, with no branching on
    where the config came from; switching only the GLOBAL config changes what that
    same call returns."""
    def call_site() -> FeatureFlagMode:
        return effective_mode("universal_file_search")

    initialize(env={ENV_INLINE: json.dumps({"default_mode": "legacy"})})
    assert call_site() == LEGACY

    initialize(env={ENV_INLINE: json.dumps({"default_mode": "comparison"})}, force=True)
    assert call_site() == COMPARISON


# -- cache: initialize caches, force re-reads, reset clears --------------------

def test_configuration_cached_across_invocations_until_forced(tmp_path: Path):
    file_path = tmp_path / "flag.json"
    file_path.write_text(json.dumps({"default_mode": "legacy"}), encoding="utf-8")
    env = {ENV_FILE: str(file_path)}
    first = initialize(env=env)
    assert first.default_mode == LEGACY
    # Mutate the file after the first read: a cached read must NOT see this.
    file_path.write_text(json.dumps({"default_mode": "adapter"}), encoding="utf-8")
    assert current_config() is first
    assert current_config().default_mode == LEGACY
    # force=True re-reads and picks up the change.
    refreshed = initialize(env=env, force=True)
    assert refreshed.default_mode == ADAPTER
    assert refreshed is not first


def test_reset_clears_cache_for_next_query():
    initialize(env={ENV_INLINE: json.dumps({"default_mode": "comparison"})})
    assert current_config().default_mode == COMPARISON
    reset()
    refreshed = initialize(env={ENV_INLINE: json.dumps({"default_mode": "legacy"})})
    assert refreshed.default_mode == LEGACY


def test_current_config_initializes_lazily_on_first_use(monkeypatch):
    monkeypatch.setenv(ENV_INLINE, json.dumps({"default_mode": "adapter"}))
    # No initialize() call at all -- the very first current_config() must do it.
    assert current_config().default_mode == ADAPTER


# -- isolation between concurrent, explicitly-configured callers --------------

def test_mode_isolation_between_concurrent_calls():
    """Concurrent callers each pass their OWN config explicitly; ``effective_mode``
    must never let one thread's config leak into another's answer."""
    configs = {"legacy": _cfg(LEGACY), "adapter": _cfg(ADAPTER), "comparison": _cfg(COMPARISON)}
    results: Dict[str, FeatureFlagMode] = {}
    errors = []

    def worker(name: str, config: FeatureFlagConfig) -> None:
        try:
            for _ in range(200):
                mode = effective_mode("universal_file_search", config=config)
                if mode != config.default_mode:
                    errors.append((name, mode))
            results[name] = effective_mode("universal_file_search", config=config)
        except Exception as exc:  # pragma: no cover - failure path only
            errors.append((name, exc))

    threads = [threading.Thread(target=worker, args=(name, config))
               for name, config in configs.items()]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert errors == []
    assert results == {name: config.default_mode for name, config in configs.items()}


# -- shape and purity of the module itself -------------------------------------

def test_feature_flag_mode_values():
    assert {mode.value for mode in FeatureFlagMode} == {"legacy", "adapter", "comparison"}


def test_module_imports_nothing_from_ai_editor_or_tree_engine():
    """Pure stdlib by design -- this is what lets the flag be read in any process,
    including one that never loads either engine."""
    source = Path(feature_flag.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    banned = {"ai_editor", "tree_engine", "mcp_proxy", "code_analysis_server"}
    assert roots.isdisjoint(banned)
