# Generated manually for show_in_home optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('explorer', '0017_places_tags'),
    ]

    operations = [
        migrations.AddField(
            model_name='places',
            name='show_in_home',
            field=models.BooleanField(default=False, db_index=True, help_text='Mostrar en página de inicio para máximo rendimiento'),
        ),
    ] 