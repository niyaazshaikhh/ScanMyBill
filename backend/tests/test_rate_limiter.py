import unittest

from app.core.middleware import _SlidingWindowRateLimiter


class RateLimiterTests(unittest.TestCase):
    def test_rate_limiter_blocks_after_limit(self) -> None:
        limiter = _SlidingWindowRateLimiter()
        key = 'test-client'

        for _ in range(5):
            allowed, retry_after = limiter.allow(key, limit=5)
            self.assertTrue(allowed)
            self.assertEqual(retry_after, 0)

        allowed, retry_after = limiter.allow(key, limit=5)
        self.assertFalse(allowed)
        self.assertGreaterEqual(retry_after, 1)


if __name__ == '__main__':
    unittest.main()
