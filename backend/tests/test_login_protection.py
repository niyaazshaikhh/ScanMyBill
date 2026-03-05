from datetime import datetime, timezone
import unittest

from app.core.login_protection import is_account_locked, next_failed_login_state


class LoginProtectionTests(unittest.TestCase):
    def test_login_lock_after_threshold(self) -> None:
        now = datetime.now(timezone.utc)
        attempts, locked_until = next_failed_login_state(
            failed_attempts=4,
            now=now,
            max_failed_attempts=5,
            lockout_minutes=15,
        )

        self.assertEqual(attempts, 0)
        self.assertIsNotNone(locked_until)
        assert locked_until is not None
        self.assertGreater(locked_until, now)
        self.assertTrue(is_account_locked(locked_until=locked_until, now=now))

    def test_login_attempts_increment_before_threshold(self) -> None:
        now = datetime.now(timezone.utc)
        attempts, locked_until = next_failed_login_state(
            failed_attempts=2,
            now=now,
            max_failed_attempts=5,
            lockout_minutes=15,
        )

        self.assertEqual(attempts, 3)
        self.assertIsNone(locked_until)


if __name__ == '__main__':
    unittest.main()
