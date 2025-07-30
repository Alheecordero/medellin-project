# Generated manually to convert SRID from 4326 to 3857
from django.db import migrations
import django.contrib.gis.db.models as gis_models


def transform_geometries_to_3857(apps, schema_editor):
    """Transforma las geometrías existentes de SRID 4326 a 3857"""
    RegionOSM = apps.get_model('explorer', 'RegionOSM')
    
    # Actualizar todas las geometrías existentes usando SQL directo
    with schema_editor.connection.cursor() as cursor:
        # Transformar las geometrías de 4326 a 3857
        cursor.execute("""
            UPDATE explorer_regionosm 
            SET geom = ST_Transform(geom, 3857)
            WHERE geom IS NOT NULL
        """)
        
        # Cambiar el SRID de la columna
        cursor.execute("""
            ALTER TABLE explorer_regionosm 
            ALTER COLUMN geom TYPE geometry(Polygon, 3857) 
            USING ST_Transform(geom, 3857)
        """)


def reverse_transform_geometries_to_4326(apps, schema_editor):
    """Revierte las geometrías de SRID 3857 a 4326"""
    RegionOSM = apps.get_model('explorer', 'RegionOSM')
    
    with schema_editor.connection.cursor() as cursor:
        # Revertir transformación de 3857 a 4326
        cursor.execute("""
            UPDATE explorer_regionosm 
            SET geom = ST_Transform(geom, 4326)
            WHERE geom IS NOT NULL
        """)
        
        # Cambiar el SRID de vuelta a 4326
        cursor.execute("""
            ALTER TABLE explorer_regionosm 
            ALTER COLUMN geom TYPE geometry(Polygon, 4326) 
            USING ST_Transform(geom, 4326)
        """)


class Migration(migrations.Migration):

    dependencies = [
        ('explorer', '0007_alter_regionosm_geom_alter_regionosm_id'),
    ]

    operations = [
        # Primero transformar los datos existentes
        migrations.RunPython(
            transform_geometries_to_3857,
            reverse_transform_geometries_to_4326
        ),
        
        # Luego actualizar el modelo
        migrations.AlterField(
            model_name='regionosm',
            name='geom',
            field=gis_models.PolygonField(srid=3857),
        ),
    ] 