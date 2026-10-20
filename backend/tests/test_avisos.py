from app.engine.calculo import calcular, distribuir_perimetro

from .test_motor import CATALOGO, proyecto_base


def test_avisos_de_ppm_agrupados():
    p = proyecto_base(400, 400, central_xy=(0, 200))
    p["elementos"] = distribuir_perimetro(p, CATALOGO, {})
    p["parametros"] = {"ppm_minimo": 1000}
    avisos = [a for a in calcular(p, CATALOGO)["advertencias"] if "PPM" in a]
    assert len(avisos) == 1 and " más." in avisos[0]  # una sola línea aunque fallen todas
