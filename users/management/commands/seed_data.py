import random
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from parcels.models import Order, Parcel, Consolidation
from faker import Faker
from datetime import timedelta

User = get_user_model()
fake = Faker('fr_FR') # Utiliser Faker pour générer des données réalistes en français

class Command(BaseCommand):
    help = 'Peuple la base de données avec des données de test spécifiques pour les utilisateurs, commandes et colis.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Suppression des données existantes (sauf superutilisateurs)...'))
        Consolidation.objects.all().delete()
        Parcel.objects.all().delete()
        Order.objects.all().delete()
        User.objects.filter(is_superuser=False).delete() # Ne supprime pas les superutilisateurs existants

        self.stdout.write(self.style.SUCCESS('Données existantes supprimées.'))

        # --- Création des utilisateurs spécifiques ---
        self.stdout.write(self.style.WARNING('Création des 3 utilisateurs (1 admin, 2 clients)...'))
        
        # 1. Administrateur
        admin_user = None
        if not User.objects.filter(email='admin@bujito.com').exists():
            admin_user = User.objects.create_superuser(
                email='admin@bujito.com',
                password='adminpassword',
                full_name='Admin Bujito',
                phone_number='+33601020304'
            )
            self.stdout.write(self.style.SUCCESS(f'Superutilisateur créé: {admin_user.email}'))
        else:
            admin_user = User.objects.get(email='admin@bujito.com')
            self.stdout.write(self.style.SUCCESS(f'Superutilisateur existant: {admin_user.email}'))

        # 2. Client 1
        client1 = None
        if not User.objects.filter(email='client1@bujito.com').exists():
            client1 = User.objects.create_user(
                email='client1@bujito.com',
                password='clientpassword',
                full_name='Client Un',
                phone_number='+33611223344',
                role='user'
            )
            self.stdout.write(self.style.SUCCESS(f'Client créé: {client1.email}'))
        else:
            client1 = User.objects.get(email='client1@bujito.com')
            self.stdout.write(self.style.SUCCESS(f'Client existant: {client1.email}'))

        # 3. Client 2
        client2 = None
        if not User.objects.filter(email='client2@bujito.com').exists():
            client2 = User.objects.create_user(
                email='client2@bujito.com',
                password='clientpassword',
                full_name='Client Deux',
                phone_number='+33655667788',
                role='user'
            )
            self.stdout.write(self.style.SUCCESS(f'Client créé: {client2.email}'))
        else:
            client2 = User.objects.get(email='client2@bujito.com')
            self.stdout.write(self.style.SUCCESS(f'Client existant: {client2.email}'))

        all_users = [admin_user, client1, client2]
        self.stdout.write(self.style.SUCCESS('Utilisateurs spécifiques créés.'))

        # --- Création de beaucoup de données pour les colis ---
        self.stdout.write(self.style.WARNING('Création de nombreuses commandes et colis pour les tests...'))
        
        num_orders_per_client = 20 # Chaque client aura 20 commandes
        num_parcels_per_order = 3 # Chaque commande aura 3 colis

        for user in [client1, client2]: # L'admin n'a pas de commandes par défaut dans ce seeder
            self.stdout.write(self.style.WARNING(f'Création de données pour {user.email}...'))
            for i in range(num_orders_per_client):
                order_date = fake.date_time_between(start_date='-2y', end_date='now')
                order_status = random.choice([choice[0] for choice in Order.STATUS_CHOICES])
                
                order = Order.objects.create(
                    user=user,
                    order_date=order_date,
                    status=order_status,
                    total_amount=random.uniform(50.0, 1000.0)
                )
                
                for j in range(num_parcels_per_order):
                    tracking_number = f'TRACK-{user.id}-{order.id}-{j}-{fake.unique.random_number(digits=5)}'
                    parcel_status = random.choice([choice[0] for choice in Parcel.PARCEL_STATUS_CHOICES])
                    last_updated = fake.date_time_between(start_date=order_date, end_date='now')
                    
                    # Assurer que la date de mise à jour n'est pas antérieure à la date de commande
                    if last_updated < order_date:
                        last_updated = order_date + timedelta(days=random.randint(0, 30))

                    Parcel.objects.create(
                        order=order,
                        tracking_number=tracking_number,
                        status=parcel_status,
                        current_location=fake.address(),
                        description=fake.sentence(),
                        last_updated=last_updated
                    )
        
        # --- Création de quelques groupages pour les clients ---
        self.stdout.write(self.style.WARNING('Création de quelques groupages pour les clients...'))
        for user in [client1, client2]:
            # Récupérer des colis éligibles pour le groupage (pending ou in_transit)
            eligible_parcels = Parcel.objects.filter(
                order__user=user,
                status__in=['pending', 'in_transit']
            ).order_by('?')[:random.randint(2, 5)] # Sélectionne 2 à 5 colis aléatoirement

            if eligible_parcels.count() >= 2:
                consolidation = Consolidation.objects.create(user=user, status='completed')
                consolidation.parcels.set(eligible_parcels)
                for parcel in eligible_parcels:
                    parcel.status = 'consolidated'
                    parcel.save()
                self.stdout.write(self.style.SUCCESS(f'Groupage créé pour {user.email} avec {eligible_parcels.count()} colis.'))
            else:
                self.stdout.write(self.style.WARNING(f'Pas assez de colis éligibles pour créer un groupage pour {user.email}.'))


        self.stdout.write(self.style.SUCCESS('Base de données peuplée avec succès avec les nouvelles données de test !'))