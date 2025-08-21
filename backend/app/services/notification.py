import app.features.crud as crud
import app.utils as utils


async def notify_user(user_id: str, message: str):
    await crud.notification_user.create(
        user_id=user_id,
        message=message
    )
    if crud.user.allow_send_email(user_id):
        await utils.send_email(user_id, message)