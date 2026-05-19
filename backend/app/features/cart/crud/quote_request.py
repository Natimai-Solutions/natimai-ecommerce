from sqlmodel import col

from app.features.base.crud import CrudBase
from app.features.cart.models.quote_request import (
    QuoteRequest,
    QuoteRequestCreate,
    QuoteRequestUpdate,
)


class QuoteRequestCrud(CrudBase[QuoteRequest, QuoteRequestCreate, QuoteRequestUpdate]):
    """Represents quote request crud."""


crud_quote_request = QuoteRequestCrud(
    model=QuoteRequest,
    schema_create=QuoteRequestCreate,
    schema_update=QuoteRequestUpdate,
    order_by=col(QuoteRequest.created_at).desc(),
)
