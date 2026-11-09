"""Reglas de las guías que no necesitan base: zonas, numeración, contadores y correcciones editoriales.

  python manage.py test explorer.test_guias
"""

from datetime import date
from types import SimpleNamespace

from django.test import SimpleTestCase

from explorer.models import CuratedGuideItem, lugar_de_centro, parada_visible
from explorer.utils.guias import (
    CAMPOS_TEXTO_GUIA,
    CAMPOS_TEXTO_PARADA,
    Parada,
    campos_importables,
    nombre_base,
    numerar,
    revisar,
)
from explorer.utils.place_classify import classify_place

BUENA = "Bar de salsa y son cubano, como se presenta en su web."


def codigos(avisos, slug=None):
    return {a.codigo for a in avisos if slug is None or a.slug == slug}


class NumeracionTests(SimpleTestCase):
    def items(self, *posiciones):
        return [SimpleNamespace(posicion=p) for p in posiciones]

    def test_ranking_numera_seguido_aunque_falten_posiciones(self):
        # La guía de rooftops saltaba de 6 a 8 porque la parada 7 estaba cerrada.
        items = numerar(self.items(1, 2, 3, 4, 5, 6, 8, 9, 10, 11), "ranking")
        self.assertEqual([i.numero for i in items], list(range(1, 11)))

    def test_ruta_numera(self):
        self.assertEqual([i.numero for i in numerar(self.items(3, 7), "ruta")], [1, 2])

    def test_seleccion_no_lleva_numero(self):
        self.assertEqual([i.numero for i in numerar(self.items(1, 2, 3), "seleccion")], [None, None, None])


class ZonaTests(SimpleTestCase):
    def test_lugar_fuera_de_la_zona_avisa(self):
        avisos = revisar([Parada("dancefree", "DANCEFREE", comuna="El Poblado", en_zona=False, comentario=BUENA)], zona="Laureles-Estadio")
        self.assertIn("fuera_de_zona", codigos(avisos))

    def test_excepcion_explicada_no_avisa(self):
        parada = Parada("x", "X", comuna="Envigado", en_zona=False, comentario=BUENA,
                        fuera_de_zona_motivo="Está a una cuadra del límite y es el único de su tipo.")
        self.assertNotIn("fuera_de_zona", codigos(revisar([parada], zona="El Poblado")))

    def test_guia_sin_zona_no_revisa_zona(self):
        self.assertNotIn("fuera_de_zona", codigos(revisar([Parada("x", "X", en_zona=None, comentario=BUENA)])))

    def test_sugiere_la_sede_que_si_esta_en_la_zona(self):
        parada = Parada("restaurante-hatoviejo", "Restaurante Hatoviejo Palmas", comuna="Buenos Aires", en_zona=False,
                        sedes_en_zona=["restaurante-hatoviejo-centro"], comentario=BUENA)
        aviso = next(a for a in revisar([parada], zona="La Candelaria") if a.codigo == "fuera_de_zona")
        self.assertIn("restaurante-hatoviejo-centro", aviso.mensaje)


class RevisionTests(SimpleTestCase):
    def test_parada_oculta_avisa(self):
        self.assertIn("oculta", codigos(revisar([Parada("panorama", "Panorama", visible=False)])))

    def test_recomendacion_generica(self):
        for texto in ("Japonés.", "Mariscos.", "Nota muy alta.", "Terraza con vista y muchas reseñas."):
            with self.subTest(texto=texto):
                self.assertIn("generico", codigos(revisar([Parada("x", "X", comentario=texto)])))

    def test_recomendacion_con_contenido_no_avisa(self):
        self.assertEqual(codigos(revisar([Parada("x", "X", comentario=BUENA)])), set())

    def test_pocas_resenas_y_mudanza(self):
        parada = Parada("purple-club", "Purple Club", comentario=BUENA, total_reviews=3,
                        resenas_recientes=["su nueva ubicación en Zero es aún mejor", "No esta ahi"])
        self.assertTrue({"evidencia", "mudanza"} <= codigos(revisar([parada])))

    def test_misma_marca_dos_veces(self):
        paradas = [Parada("a", "Restaurante Hatoviejo Palmas", comentario=BUENA),
                   Parada("b", "Restaurante Hatoviejo Centro", comentario=BUENA)]
        self.assertIn("duplicado", codigos(revisar(paradas), "b"))

    def test_lugares_distintos_con_sustantivo_comun_no_son_duplicado(self):
        paradas = [Parada("a", "Parque Explora", comentario=BUENA), Parada("b", "Parque Norte", comentario=BUENA),
                   Parada("c", "Museo El Castillo", comentario=BUENA), Parada("d", "Museo Casa de la Memoria", comentario=BUENA)]
        self.assertNotIn("duplicado", codigos(revisar(paradas)))

    def test_tipo_distinto_al_de_maps(self):
        parada = Parada("la-matriarca", "La Matriarca", comentario=BUENA, tipo="dog_cafe", tipo_maps="restaurant")
        self.assertIn("tipo", codigos(revisar([parada])))

    def test_dato_variable_sin_fecha(self):
        parada = Parada("x", "X", comentario=BUENA, presupuesto="$40.000 – $80.000")
        self.assertIn("sin_fuente", codigos(revisar([parada])))
        parada.verificado_en = date(2026, 11, 9)
        self.assertNotIn("sin_fuente", codigos(revisar([parada])))

    def test_publicada_sin_revision(self):
        self.assertIn("sin_revision", codigos(revisar([], publicada=True, revisada=False)))
        self.assertNotIn("sin_revision", codigos(revisar([], publicada=True, revisada=True)))

    def test_nombre_base(self):
        self.assertEqual(nombre_base("Restaurante Hatoviejo - Centro Comercial Viva Envigado"), "hatoviejo")
        self.assertEqual(nombre_base("Despecho Medellín"), "despecho")


class DatosVariablesTests(SimpleTestCase):
    def test_presupuesto_y_aviso_solo_con_fecha(self):
        item = CuratedGuideItem(presupuesto="$50.000", advertencia="Abre de jueves a sábado.")
        self.assertEqual((item.presupuesto_publico, item.advertencia_publica), ("", ""))
        item.verificado_en = date(2026, 11, 9)
        self.assertEqual((item.presupuesto_publico, item.advertencia_publica), ("$50.000", "Abre de jueves a sábado."))


class PreservacionEditorialTests(SimpleTestCase):
    def test_sin_revision_el_importador_escribe_todo(self):
        guia = SimpleNamespace(revisado_en=None)
        nuevos = {"titulo": "Nuevo", "orden": 3}
        self.assertEqual(campos_importables(guia, nuevos, CAMPOS_TEXTO_GUIA), nuevos)

    def test_guia_revisada_conserva_su_texto(self):
        guia = SimpleNamespace(revisado_en=date(2026, 11, 9))
        cambios = campos_importables(guia, {"titulo": "Del JSON", "descripcion": "Del JSON", "orden": 3}, CAMPOS_TEXTO_GUIA)
        self.assertEqual(cambios, {"orden": 3})

    def test_parada_verificada_conserva_su_texto(self):
        item = SimpleNamespace(verificado_en=date(2026, 11, 9))
        cambios = campos_importables(item, {"comentario": "Del JSON", "posicion": 4}, CAMPOS_TEXTO_PARADA)
        self.assertEqual(cambios, {})


class ContadoresTests(SimpleTestCase):
    """El índice cuenta desde la guía o el centro; la página, desde los lugares. Mismo criterio."""

    def condiciones(self, q, prefijo=""):
        hojas = []
        for hijo in q.children:
            if isinstance(hijo, tuple):
                hojas.append((hijo[0].removeprefix(prefijo), hijo[1], q.negated))
            else:
                hojas += self.condiciones(hijo, prefijo)
        return sorted(hojas, key=str)

    def test_paradas_visibles_mismo_criterio(self):
        self.assertEqual(self.condiciones(parada_visible("items__"), "items__"), self.condiciones(parada_visible()))

    def test_centro_comercial_mismo_criterio(self):
        self.assertEqual(self.condiciones(lugar_de_centro("lugares__"), "lugares__"), self.condiciones(lugar_de_centro()))

    def test_parada_visible_exige_ficha_publicada(self):
        self.assertIn(("lugar__tiene_fotos", True, False), self.condiciones(parada_visible()))


class ClasificacionTests(SimpleTestCase):
    def test_tipo_de_nicho_del_barrido_no_gana_a_restaurante(self):
        # La Matriarca: el barrido traía dog_cafe y la categoría de Maps no se reconocía.
        tipo = classify_place(scan_types=["dog_cafe", "restaurant"])["tipo"]
        self.assertEqual(tipo, "restaurant")

    def test_tipo_especifico_sigue_ganando_a_generico(self):
        self.assertEqual(classify_place(scan_types=["restaurant", "seafood_restaurant"])["tipo"], "seafood_restaurant")
