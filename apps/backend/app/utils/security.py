from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

ph = PasswordHasher()

def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(hashed: str, plain: str) -> bool:
    try:
        ph.verify(hashed, plain)
        return True
    except VerifyMismatchError:
        return False
