import unittest
from unittest.mock import Mock

from checkin import Doc2XClient


class TestDoc2XClient(unittest.TestCase):
    def test_get_checkin_status_returns_empty_list_when_api_returns_none(self):
        client = Doc2XClient("13800000000", "password")
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "code": "success",
            "data": {"checkin_dates": None},
        }
        client.session.get = Mock(return_value=mock_resp)

        ok, dates = client.get_checkin_status()

        self.assertTrue(ok)
        self.assertEqual(dates, [])

    def test_get_checkin_status_returns_dates_list(self):
        client = Doc2XClient("13800000000", "password")
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "code": "success",
            "data": {"checkin_dates": ["2026-11-01"]},
        }
        client.session.get = Mock(return_value=mock_resp)

        ok, dates = client.get_checkin_status()

        self.assertTrue(ok)
        self.assertEqual(dates, ["2026-11-01"])


if __name__ == "__main__":
    unittest.main()
