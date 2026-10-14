from django.core.management.base import BaseCommand
from django.db import connection

from benchapp.models import Item


class Command(BaseCommand):
    help = "Seed bench_item with N rows (ids 1..N) if the table is empty."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=100_000)

    def handle(self, *args, count, **options):
        existing = Item.objects.count()
        if existing:
            self.stdout.write(f"bench_item already has {existing} rows, skipping")
            return
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO bench_item (name, payload, counter, created_at, updated_at)
                SELECT 'item-' || g, repeat(md5(g::text), 6), 0, now(), now()
                FROM generate_series(1, %s) AS g
                """,
                [count],
            )
            cursor.execute("ANALYZE bench_item")
        self.stdout.write(f"seeded {count} rows")
