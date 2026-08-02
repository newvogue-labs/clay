"""Guard: путь аудит-журнала резолвится через XDG_STATE_HOME (D-45).

Все три ветки охранника обязательны:
  (a) XDG_STATE_HOME задан → журнал уходит в override, а не в ~/.local/state;
  (b) XDG_STATE_HOME пуст или не задан → дефолт ~/.local/state;
  (c) в backend/src нет захардкоженного ~/.local/state/clay/audit.jsonl
      в обход единого резолвера — запись/чтение журнала идут через
      resolve_audit_journal_path().

Hermetic: только локальные tmp-директории, без сети, без ключей.
"""

from __future__ import annotations

import pathlib

from clay.config.paths import resolve_audit_journal_path

_REPO = pathlib.Path(__file__).resolve().parents[3]
_SRC = _REPO / "backend" / "src"


class TestResolveAuditJournalPath:
    def test_a_xdg_state_home_overrides_default(self, tmp_path, monkeypatch) -> None:
        xdg = tmp_path / "xdgtest"
        home = tmp_path / "home"
        monkeypatch.setenv("XDG_STATE_HOME", str(xdg))
        monkeypatch.setenv("HOME", str(home))

        journal = resolve_audit_journal_path()

        assert journal == xdg / "clay" / "audit.jsonl"
        assert not str(journal).startswith(str(home / ".local"))

    def test_b_empty_xdg_state_home_falls_back_to_local_state(
        self, tmp_path, monkeypatch
    ) -> None:
        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("XDG_STATE_HOME", "")

        journal = resolve_audit_journal_path()

        assert journal == home / ".local/state" / "clay" / "audit.jsonl"

    def test_b_missing_xdg_state_home_falls_back_to_local_state(
        self, tmp_path, monkeypatch
    ) -> None:
        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)

        journal = resolve_audit_journal_path()

        assert journal == home / ".local/state" / "clay" / "audit.jsonl"


class TestNoHardcodedJournalPath:
    def test_c_no_full_path_anywhere_in_src(self) -> None:
        """Ни одна строка в backend/src не содержит полного пути журнала.

        Полный путь можно получить ТОЛЬКО через резолвер: имя файла
        собирается в одном месте, дефолтная база — в другом; они никогда
        не склеены в одной строке с ``.local/state``.
        """
        for path in sorted(_SRC.rglob("*.py")):
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                assert "local/state/clay" not in line, (
                    f"захардкоженный путь журнала в обход резолвера: "
                    f"{path}:{lineno}: {line}"
                )
                assert not (".local/state" in line and "audit.jsonl" in line), (
                    f"имя файла журнала склеено с базой в одной строке: "
                    f"{path}:{lineno}: {line}"
                )

    def test_c_bootstrap_builds_writer_via_resolver(self) -> None:
        """bootstrap передаёт AuditWriter путь из резолвера, не из paths.state_dir."""
        text = (_SRC / "clay" / "bootstrap.py").read_text(encoding="utf-8")
        assert "resolve_audit_journal_path" in text
        assert "audit_journal_path.parent" in text
        # между AuditWriter( и его закрывающей скобкой не должно быть
        # config_loader.paths.state_dir.
        head, _, rest = text.partition("AuditWriter(")
        del head
        call_head, _, _ = rest.partition(")")
        assert "config_loader.paths.state_dir" not in call_head
