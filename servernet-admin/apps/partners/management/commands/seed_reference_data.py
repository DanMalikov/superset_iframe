from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Role
from apps.partners.models import Partner


class Command(BaseCommand):
    help = "Создать исходные роли и партнёров без изменения существующих записей"

    @transaction.atomic
    def handle(self, *args, **options):
        partners = [(1, "Партнер один"), (2, "Партнер два")]
        for partner_id, name in partners:
            existing_by_name = Partner.objects.filter(name=name).first()
            if existing_by_name and existing_by_name.pk != partner_id:
                raise CommandError(f"Партнёр с именем {name} уже имеет другой ID")
            Partner.objects.get_or_create(id=partner_id, defaults={"name": name})

        for code, name in [("analyst", "Аналитик"), ("director", "Директор")]:
            Role.objects.get_or_create(code=code, defaults={"name": name})

        self.stdout.write(self.style.SUCCESS("Справочники проверены"))
