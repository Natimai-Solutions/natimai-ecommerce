import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import settings

# bcrypt ne prend en compte que les 72 premiers octets du mot de passe.
# passlib tronquait au-delà **en silence** : les empreintes déjà en base ont
# donc été calculées sur ces 72 octets uniquement. bcrypt >= 5 lève une
# ValueError à la place, si bien que reproduire la troncature à l'identique
# n'est pas un détail : sans elle, tout compte dont le mot de passe dépasse
# 72 octets deviendrait invérifiable — l'utilisateur serait enfermé dehors.
#
# La troncature porte sur les OCTETS et non les caractères, exactement comme
# avant : un mot de passe accentué peut donc être coupé au milieu d'un
# caractère UTF-8. bcrypt travaille sur des octets, cela lui est indifférent,
# et c'est ce qui rend les anciennes empreintes reproductibles.
_BCRYPT_MAX_BYTES = 72


def _bcrypt_input(password: str) -> bytes:
    """Le mot de passe sous la forme exacte qui était donnée à bcrypt."""
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


ALGORITHM = "HS256"


def create_access_token(subject: str | Any, expires_delta: timedelta) -> str:
    """Create access token."""
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {"exp": expire, "sub": str(subject), "type": "access"}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(
    subject: str | Any, expires_delta: timedelta, jti: str | None = None
) -> str:
    """Create refresh token."""
    expire = datetime.now(timezone.utc) + expires_delta
    refresh_jti = jti or str(uuid.uuid4())
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "type": "refresh",
        "jti": refresh_jti,
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> dict[str, Any]:
    """Execute decode token."""
    # jwt.decode est déjà typé dict[str, Any] : le cast était redondant.
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie un mot de passe contre son empreinte bcrypt."""
    try:
        return bcrypt.checkpw(
            _bcrypt_input(plain_password), hashed_password.encode("utf-8")
        )
    except ValueError:
        # Empreinte illisible (colonne vide, tronquée, autre format) :
        # c'est un échec d'authentification, pas une erreur 500.
        return False


def get_password_hash(password: str) -> str:
    """Empreinte bcrypt du mot de passe (coût 12, inchangé)."""
    return bcrypt.hashpw(_bcrypt_input(password), bcrypt.gensalt()).decode("utf-8")


def hash_reset_token(token: str) -> str:
    """Condensat d'un jeton de reprise de compte (mot de passe oublié,
    invitation). SHA-256 suffit : le jeton est déjà aléatoire (32 octets
    d'entropie), un bcrypt ne protégerait que d'une attaque par dictionnaire
    qui n'a pas de sens ici. Déterministe, donc recherchable en base.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
