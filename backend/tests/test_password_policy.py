import unittest
from pydantic import ValidationError

from app.core.validators import ensure_password_strength
from app.schemas.auth import CreateAccountRequest


class PasswordPolicyTests(unittest.TestCase):
    def test_password_policy_rejects_weak_password(self) -> None:
        with self.assertRaises(ValueError):
            ensure_password_strength('password123')

    def test_password_policy_accepts_strong_password(self) -> None:
        value = ensure_password_strength('Strong@123Password')
        self.assertEqual(value, 'Strong@123Password')

    def test_schema_rejects_weak_password(self) -> None:
        with self.assertRaises(ValidationError):
            CreateAccountRequest(
                email='user@example.com',
                full_name='Valid User',
                password='weakpass',
            )


if __name__ == '__main__':
    unittest.main()
