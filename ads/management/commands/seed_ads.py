import re
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand

from ads.models import Advertisement

SEED_DIR = Path(__file__).resolve().parents[2] / 'seed_images'
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp'}


def _sort_key(path: Path):
    match = re.search(r'(\d+)', path.stem)
    return (int(match.group(1)) if match else 10**9, path.name.lower())


class Command(BaseCommand):
    help = (
        'Importe les affiches depuis ads/seed_images/ vers media/ads/ '
        'et crée les lignes Advertisement (écran home par défaut).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Supprime toutes les affiches existantes avant le seed.',
        )
        parser.add_argument(
            '--screen',
            default='home',
            help='Écran cible JSON (défaut: home). Ex: home ou home,orders',
        )

    def handle(self, *args, **options):
        if not SEED_DIR.is_dir():
            self.stderr.write(self.style.ERROR(f'Dossier introuvable: {SEED_DIR}'))
            return

        files = sorted(
            (p for p in SEED_DIR.iterdir() if p.suffix.lower() in IMAGE_EXTS),
            key=_sort_key,
        )
        if not files:
            self.stderr.write(self.style.ERROR(f'Aucune image dans {SEED_DIR}'))
            return

        if options['flush']:
            count = Advertisement.objects.count()
            Advertisement.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'{count} affiche(s) supprimée(s).'))

        screens = [
            s.strip().lower()
            for s in str(options['screen']).split(',')
            if s.strip()
        ] or ['home']

        created = 0
        for index, path in enumerate(files):
            title = f'Affiche {index + 1}'
            if Advertisement.objects.filter(title=title, sort_order=index).exists():
                self.stdout.write(f'Déjà présent: {title}')
                continue

            ad = Advertisement(
                title=title,
                sort_order=index,
                is_active=True,
                screens=screens,
            )
            with path.open('rb') as fh:
                ad.image.save(path.name, File(fh), save=True)
            created += 1
            self.stdout.write(self.style.SUCCESS(f'Créée: {title} <- {path.name}'))

        self.stdout.write(
            self.style.SUCCESS(
                f'Terminé: {created} créée(s), total={Advertisement.objects.count()}'
            )
        )
