""" interface to canonical sso
"""

import requests


class CanonicalIdentityProvider:
    """ provider class to sso
    """

    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.host = "https://login.ubuntu.com"

    def get_discharge(self, caveat_id):
        """ Pass in the caveat_id to get a discharged
        macaroon
        """
        api_path = "/api/v2/tokens/discharge"
        api_path = f"{self.host}{api_path}"
        data = {"email": self.email, "password": self.password, "caveat_id": caveat_id}

        response = requests.post(api_path, json=data)
        return response
