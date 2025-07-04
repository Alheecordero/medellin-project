from django.contrib.gis.geos import MultiPoint, Point, GEOSGeometry
from django.contrib.gis.measure import D
from explorer.models import Places, ZonaCubierta

def crear_zona_cubierta(nombre, lat, lng, radio_km=0.5):
    centro = Point(lng, lat, srid=4326)
    lugares = Places.objects.filter(ubicacion__distance_lte=(centro, D(km=radio_km)))

    if lugares.count() < 3:
        print("No hay suficientes lugares para crear un polígono.")
        return None

    puntos = [l.ubicacion for l in lugares]
    multipunto = MultiPoint(puntos)
    poligono = multipunto.convex_hull

    zona = ZonaCubierta.objects.create(nombre=nombre, poligono=poligono)
    return zona
