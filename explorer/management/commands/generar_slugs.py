from django.core.management.base import BaseCommand
from django.utils.text import slugify
from explorer.models import Places

class Command(BaseCommand):
    help = 'Genera slugs únicos para todos los lugares sin slug'

    def handle(self, *args, **options):
        lugares_actualizados = 0

        for lugar in Places.objects.all():
            if not lugar.slug:
                base_slug = slugify(lugar.nombre)
                slug = base_slug
                num = 1
                while Places.objects.filter(slug=slug).exclude(pk=lugar.pk).exists():
                    slug = f"{base_slug}-{num}"
                    num += 1
                lugar.slug = slug
                lugar.save()
                lugares_actualizados += 1
                self.stdout.write(self.style.SUCCESS(f'Slug generado: {slug}'))

        if lugares_actualizados == 0:
            self.stdout.write(self.style.WARNING("No hay lugares pendientes por actualizar."))
        else:
            self.stdout.write(self.style.SUCCESS(f'Total de slugs actualizados: {lugares_actualizados}'))
