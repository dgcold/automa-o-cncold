from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CoilGeometry:
    tube_count: int
    tube_outer_diameter_m: float
    tube_length_m: float
    fin_count: int
    fin_height_m: float
    fin_width_m: float
    fin_thickness_m: float
    rows: int = 1
    circuits: int = 1


@dataclass(frozen=True)
class CoilResult:
    tube_external_area_m2: float
    gross_fin_area_m2: float
    tube_hole_area_m2: float
    effective_fin_area_m2: float
    total_exchange_area_m2: float
    fin_density_per_m: float
    fpi: float
    formula: tuple[str, ...]


class FinnedCoilCalculator:
    @staticmethod
    def calculate(data: CoilGeometry) -> CoilResult:
        numeric = (data.tube_outer_diameter_m, data.tube_length_m, data.fin_height_m,
                   data.fin_width_m, data.fin_thickness_m)
        if data.tube_count <= 0 or data.fin_count <= 0 or min(numeric) <= 0 or data.rows <= 0 or data.circuits <= 0:
            raise ValueError("Todas as dimensões, contagens, fileiras e circuitos devem ser positivos.")
        tube_area = math.pi * data.tube_outer_diameter_m * data.tube_length_m * data.tube_count
        gross_fin = 2.0 * data.fin_height_m * data.fin_width_m * data.fin_count
        holes = 2.0 * math.pi * (data.tube_outer_diameter_m / 2.0) ** 2 * data.tube_count * data.fin_count
        effective = max(0.0, gross_fin - holes)
        density = data.fin_count / data.tube_length_m
        return CoilResult(tube_area, gross_fin, holes, effective, tube_area + effective, density, density * 0.0254,
            ("A_tubos = π × D_externo × L_tubo × número_de_tubos",
             "A_aletas_bruta = 2 × altura × largura × número_de_aletas",
             "A_furos = 2 × π × (D_externo/2)² × tubos × aletas",
             "A_aletas_efetiva = A_aletas_bruta − A_furos",
             "A_total = A_tubos + A_aletas_efetiva", "FPI = (aletas/comprimento_em_m) × 0,0254"))
