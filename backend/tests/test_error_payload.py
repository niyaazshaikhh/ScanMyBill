import json
import unittest

from app.core.errors import error_response


class ErrorPayloadTests(unittest.TestCase):
    def test_error_response_format(self) -> None:
        response = error_response(status_code=400, code='BAD_REQUEST', message='Invalid input')
        payload = json.loads(response.body.decode('utf-8'))

        self.assertEqual(
            payload,
            {
                'success': False,
                'error': {
                    'code': 'BAD_REQUEST',
                    'message': 'Invalid input',
                },
            },
        )


if __name__ == '__main__':
    unittest.main()
