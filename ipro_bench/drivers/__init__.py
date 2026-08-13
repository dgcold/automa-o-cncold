"""Drivers desacoplados dos módulos comuns da plataforma CNCold."""

from .registry import ControllerRegistry, build_default_registry

__all__ = ["ControllerRegistry", "build_default_registry"]
