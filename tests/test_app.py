import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import app  # noqa: E402


class AppSecretsTest(unittest.TestCase):
    def test_missing_secrets_are_reported(self):
        values, missing = app.load_secrets({})

        self.assertEqual(values, {})
        self.assertEqual(missing, list(app.REQUIRED_SECRETS))

    def test_configured_secrets_are_returned(self):
        configured = {
            "APP_PASSWORD": "example-password",
            "QUALTRICS_API_TOKEN": "example-token",
            "QUALTRICS_DATACENTER": "example-datacenter",
        }

        values, missing = app.load_secrets(configured)

        self.assertEqual(values, configured)
        self.assertEqual(missing, [])

    def test_empty_secret_is_reported_as_missing(self):
        configured = {
            "APP_PASSWORD": "",
            "QUALTRICS_API_TOKEN": "example-token",
            "QUALTRICS_DATACENTER": "example-datacenter",
        }

        values, missing = app.load_secrets(configured)

        self.assertEqual(values, {
            "QUALTRICS_API_TOKEN": "example-token",
            "QUALTRICS_DATACENTER": "example-datacenter",
        })
        self.assertEqual(missing, ["APP_PASSWORD"])


if __name__ == "__main__":
    unittest.main()
