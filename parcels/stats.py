"""Compteurs colis reçus / envoyés (statuts métier)."""

# Arrivés à l'entrepôt Chine (reçus) — pas encore partis.
PARCEL_RECEIVED_STATUSES = ('pending', 'consolidated')

# Partis vers le client / en livraison (envoyés).
PARCEL_SENT_STATUSES = ('in_transit', 'out_for_delivery', 'delivered')
