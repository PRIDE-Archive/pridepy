import unittest

import pytest

from pridepy.authentication import authentication
from pridepy.files.files import Files
from pridepy.project.project import Project


class TestAuthentication(unittest.TestCase):
    """
    A test class to test Authentication related methods.
    """

    # @pytest.mark.skip(reason="Needs credentials")
    @pytest.mark.skip(reason="Needs credentials")
    def test_get_token(self):
        """
        Test get API AAP token functionality
        :return:
        """
        username = "******"
        password = "******"
        auth = authentication.Authentication()
        api_token = auth.get_token(username, password)
        print(api_token)
        self.assertTrue(len(api_token) > 20, "Token not found!")

    @pytest.mark.skip(reason="Needs credentials")
    def test_validate_token(self):
        """
        Test get API AAP token is valid or expired
        :return:
        """
        username = "******"
        password = "******"
        auth = authentication.Authentication()
        api_token = auth.get_token(username, password)
        print(api_token)
        self.assertTrue(auth.validate_token(api_token), "Token is invalid or expired!")

    @pytest.mark.skip(reason="Needs credentials")
    def test_get_dataset_private(self):
        username = "******"
        password = "******"
        dataset = "******"

        file_handler = Files()
        files = file_handler.download_private_file_name(
            accession=dataset,
            username=username,
            password=password,
            output_folder="./",
            file_name="g00739_Prot_36_06.raw",
        )
        print(files)

    @pytest.mark.skip(reason="Needs credentials")
    def test_list_private_files(self):
        username = "********"
        password = "********"
        dataset = "********"

        project = Project()
        files = project.get_private_files_by_accession(dataset, username, password)
        print(files)


if __name__ == "__main__":
    unittest.main()
