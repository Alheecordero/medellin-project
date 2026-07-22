# Permite búsqueda sin tildes en admin (nombre/place_id en PendingPlace, etc.)
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('explorer', '0027_add_pending_place'),
    ]

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS unaccent;",
            reverse_sql="DROP EXTENSION IF EXISTS unaccent;",
        ),
    ]
