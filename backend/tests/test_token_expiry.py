from datetime import timedelta
import unittest

from app.core.security import create_access_token, decode_token, is_token_close_to_expiry


class TokenExpiryTests(unittest.TestCase):
    def test_access_token_close_to_expiry_detection(self) -> None:
        token = create_access_token(subject='user-1', expires_delta=timedelta(seconds=30))
        payload = decode_token(token)

        self.assertTrue(is_token_close_to_expiry(payload, threshold_seconds=60))
        self.assertFalse(is_token_close_to_expiry(payload, threshold_seconds=1))


if __name__ == '__main__':
    unittest.main()
