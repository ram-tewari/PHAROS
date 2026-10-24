"""HTTP-ish request handlers wiring auth and the cart together."""

from decimal import Decimal

from .auth import TokenSigner, authenticate
from .cart import Cart

SIGNER = TokenSigner(b"fixture-only-secret")
CARTS: dict[int, Cart] = {}


def login_handler(body: dict) -> tuple[int, dict]:
    """POST /login — exchange username and password for a session token."""
    user = authenticate(body.get("username", ""), body.get("password", ""))
    if user is None:
        return 401, {"error": "invalid credentials"}
    return 200, {"token": SIGNER.issue(user["id"])}


def add_to_cart_handler(token: str, body: dict) -> tuple[int, dict]:
    """POST /cart/items — add a product to the caller's cart."""
    user_id = SIGNER.verify(token)
    if user_id is None:
        return 401, {"error": "invalid or expired token"}
    cart = CARTS.setdefault(user_id, Cart())
    cart.add_item(body["sku"], Decimal(str(body["price"])), int(body.get("quantity", 1)))
    return 200, {"total": str(cart.total())}


def checkout_handler(token: str) -> tuple[int, dict]:
    """POST /checkout — charge the cart total and empty the cart."""
    user_id = SIGNER.verify(token)
    if user_id is None:
        return 401, {"error": "invalid or expired token"}
    cart = CARTS.pop(user_id, Cart())
    return 200, {"charged": str(cart.total())}
