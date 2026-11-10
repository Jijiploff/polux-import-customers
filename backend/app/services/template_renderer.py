"""Renderizado de plantillas con marcadores {{variable}}.

Deliberadamente simple y seguro: sólo sustituye `{{ nombre_variable }}` por
valores del diccionario; las variables ausentes se reemplazan por cadena vacía
para evitar fugas de texto literal al cliente.
"""
from __future__ import annotations

import re
from typing import Mapping

_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")


class TemplateRenderer:
    @staticmethod
    def render(template: str, variables: Mapping[str, object]) -> str:
        def _sub(match: re.Match[str]) -> str:
            key = match.group(1)
            value = variables.get(key, "")
            if value is None:
                return ""
            return str(value)

        return _PATTERN.sub(_sub, template)