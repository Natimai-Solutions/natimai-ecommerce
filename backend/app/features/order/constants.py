"""Constantes pour les statuts de commande."""


class OrderStatusCode:
    """Codes des statuts de commande."""

    PENDING = "PENDING"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    PROCESSING = "PROCESSING"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
