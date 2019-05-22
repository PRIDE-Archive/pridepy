import unittest

import authentication.authentication


class TestAuthentication(unittest.TestCase):
    """
    A test class to test Authentication related methods.
    """

    def test_get_token(self):
        """
        Test get API AAP token functionality
        :return:
        """
        username = "sureshhewabi@gmail.com"
        password = "***********"
        auth = authentication.authentication.Authentication()
        api_token = auth.getToken(username, password)
        print(api_token)
        self.assertTrue(len(api_token) > 20, "Token not found!")

    def test_validate_token(self):
        """
        Test get API AAP token is valid or expired
        :return:
        """
        username = "sureshhewabi@gmail.com"
        password = "***********"
        auth = authentication.authentication.Authentication()
        api_token = auth.getToken(username, password)
        print(api_token)
        self.assertTrue(auth.validateToken(api_token), "Token is invalid or expired!")


if __name__ == '__main__':
    unittest.main()
