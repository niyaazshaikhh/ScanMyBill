import unittest

from app import main


class ProductionSecurityConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_values = {
            "environment": main.settings.environment,
            "secret_key": main.settings.secret_key,
            "debug": main.settings.debug,
            "enable_docs": main.settings.enable_docs,
            "cookie_secure": main.settings.cookie_secure,
            "enforce_https": main.settings.enforce_https,
            "expose_password_reset_token": main.settings.expose_password_reset_token,
            "seed_default_admin": main.settings.seed_default_admin,
            "database_url_override": main.settings.database_url_override,
            "postgres_password": main.settings.postgres_password,
            "cors_origins": main.settings.cors_origins,
            "trusted_hosts": main.settings.trusted_hosts,
        }

    def tearDown(self) -> None:
        for key, value in self.original_values.items():
            setattr(main.settings, key, value)

    def _set_secure_base(self) -> None:
        main.settings.environment = "production"
        main.settings.secret_key = "a" * 48
        main.settings.debug = False
        main.settings.enable_docs = False
        main.settings.cookie_secure = True
        main.settings.enforce_https = True
        main.settings.expose_password_reset_token = False
        main.settings.seed_default_admin = False
        main.settings.database_url_override = "postgresql+psycopg2://user:pass@example-db/scanmybill"
        main.settings.postgres_password = "StrongPassword123!"
        main.settings.cors_origins = ["https://app.example.com"]
        main.settings.trusted_hosts = ["api.example.com", "app.example.com"]

    def test_production_validation_rejects_local_hosts(self) -> None:
        self._set_secure_base()
        main.settings.cors_origins = ["http://localhost:3000"]
        main.settings.trusted_hosts = ["localhost", "api.example.com"]

        with self.assertRaises(RuntimeError) as context:
            main._validate_security_configuration()

        self.assertIn("CORS_ORIGINS cannot include localhost", str(context.exception))
        self.assertIn("TRUSTED_HOSTS cannot include localhost", str(context.exception))

    def test_production_validation_requires_https_enforcement(self) -> None:
        self._set_secure_base()
        main.settings.enforce_https = False

        with self.assertRaises(RuntimeError) as context:
            main._validate_security_configuration()

        self.assertIn("ENFORCE_HTTPS must be true", str(context.exception))

    def test_production_validation_accepts_explicit_secure_config(self) -> None:
        self._set_secure_base()

        main._validate_security_configuration()


if __name__ == "__main__":
    unittest.main()
