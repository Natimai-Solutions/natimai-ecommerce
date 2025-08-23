from app.outbox.registry import outbox_registry

def outbox_handler(event_type: str):
    """Décorateur pour enregistrer automatiquement un handler."""
    def decorator(func):
        outbox_registry.register_handler(event_type, func)
        return func
    return decorator