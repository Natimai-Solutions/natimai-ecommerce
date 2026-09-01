"""Guard against an unbounded log file in the outbox poller (audit item I8).

Le poller écrit ses logs à deux endroits : stdout, récupéré et tourné par Docker
(anchor ``x-app-logging``), et un fichier ``outbox_poller.log`` que personne ne
tourne. Un service continu qui écrit dans un fichier non borné finit par remplir
la couche inscriptible du conteneur — panne d'exploitation, pas de code, donc
rien ne la signale avant qu'elle n'arrive.

Le contrôle est fait sur le source : la configuration de logging s'exécute à
l'import du module, l'importer ici créerait le fichier dans le répertoire des
tests et l'inspecter après coup dépendrait des handlers que pytest installe.
"""

from __future__ import annotations

import ast
from pathlib import Path

_POLLER = Path(__file__).resolve().parents[2] / "scripts" / "outbox_poller.py"


def _handler_names(source: str) -> list[str]:
    """Noms des handlers de logging instanciés dans le module."""
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            names.append(func.attr)
        elif isinstance(func, ast.Name):
            names.append(func.id)
    return [name for name in names if name.endswith("Handler")]


def test_the_poller_log_file_is_rotated() -> None:
    handlers = _handler_names(_POLLER.read_text(encoding="utf-8"))

    assert "RotatingFileHandler" in handlers
    # `FileHandler` nu = fichier qui grossit indéfiniment : c'est le défaut
    # corrigé, pas une variante acceptable.
    assert "FileHandler" not in handlers


def _calls_named(source: str, name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == name
    ]


def test_the_rotation_is_actually_bounded() -> None:
    """Un RotatingFileHandler sans maxBytes ne tourne jamais (défaut 0)."""
    calls = _calls_named(_POLLER.read_text(encoding="utf-8"), "RotatingFileHandler")

    assert len(calls) == 1
    kwargs = {keyword.arg for keyword in calls[0].keywords}
    assert {"maxBytes", "backupCount"} <= kwargs


def test_the_logging_configuration_is_forced() -> None:
    """Sans `force`, la configuration du poller est un no-op silencieux.

    Un module de bibliothèque (``features/base/crud``) appelle basicConfig à
    l'import : le root logger a déjà un handler quand le poller configure le
    sien, et basicConfig ne fait alors rien du tout — le fichier était créé
    vide puis jamais écrit. Le worker ARQ porte déjà ce `force=True`.
    """
    calls = _calls_named(_POLLER.read_text(encoding="utf-8"), "basicConfig")

    assert len(calls) == 1
    forced = [kw for kw in calls[0].keywords if kw.arg == "force"]
    assert forced, "basicConfig sans force=True ne s'applique pas"
    assert isinstance(forced[0].value, ast.Constant) and forced[0].value.value is True
