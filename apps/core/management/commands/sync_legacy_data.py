"""
Idempotent top-up from the legacy PHP database into an ALREADY-imported
Django database: business settings, currency rates, suppliers, field staff,
reviews, incidents, and the per-user columns/password hashes the first
import skipped. Safe to run repeatedly — everything is matched by a natural
key (setting key, currency code, username, supplier/staff name).

    python manage.py sync_legacy_data --dry-run
    python manage.py sync_legacy_data
    python manage.py sync_legacy_data --keep-settings   # don't overwrite settings already edited in Django
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User
from apps.core import legacy


class Command(BaseCommand):
    help = 'Idempotently sync settings, currencies, suppliers, staff and user details/passwords from the legacy PHP database.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--keep-settings', action='store_true', help='Only add missing settings; never overwrite existing ones.')
        parser.add_argument('--no-passwords', action='store_true', help='Do not migrate legacy password hashes.')

    def handle(self, *args, **opts):
        if opts['dry_run']:
            for t in ('settings', 'currency_rates', 'suppliers', 'staff', 'reviews', 'incidents', 'admin_users'):
                self.stdout.write(f'{t:16s} {next(legacy.rows(t, "COUNT(*) AS n"))["n"]}')
            return
        with transaction.atomic():
            report = {
                'settings': legacy.import_settings(overwrite=not opts['keep_settings']),
                'currencies': legacy.import_currencies(),
                'suppliers': legacy.import_suppliers(),
                'staff': legacy.import_staff(),
                'reviews': legacy.import_reviews(),
            }
            created = updated = migrated = 0
            for r in legacy.rows('admin_users'):
                user = User.objects.filter(username=r['username']).first()
                if user is None:
                    user = User(username=r['username'])
                    user.set_unusable_password()
                    created += 1
                else:
                    updated += 1
                if legacy.apply_user_fields(user, r, set_password=not opts['no_passwords']):
                    migrated += 1
                user.save()
            by_legacy_id = {r['id']: User.objects.filter(username=r['username']).first() for r in legacy.rows('admin_users', 'id, username')}
            report['incidents'] = legacy.import_incidents(by_legacy_id)
        self.stdout.write(self.style.SUCCESS(
            'Synced: ' + ', '.join(f'{k} {v}' for k, v in report.items())
            + f', users {updated} updated / {created} created, {migrated} legacy passwords migrated'))
        if migrated:
            self.stdout.write('Migrated users keep their old PHP-app passwords; each hash upgrades to PBKDF2 on next login.')
