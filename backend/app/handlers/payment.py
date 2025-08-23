from app.outbox.decorators import outbox_handler

@outbox_handler("CREATE_PAYMENT")
async def create_notification(session, payload) -> None:
    pass