import requests
import base64
import json
import time

# If the Authentication JWT does not have an exp (expiry) claim, use this value for the number of seconds
# the bearer token is valid.
FALLBACK_TOKEN_EXPIRY_SECONDS = (
    30 * 60
)  # 30 minutes, per the DSpace RestContract documentation.

# The number of seconds before a token expires before we will reauthenticate.
TOKEN_EXPIRY_BUFFER_SECONDS = (
    5 * 60
)  # 5 minutes before the token would expire, reauthenticate and get a new token.


class DSpaceSession(requests.Session):
    """A wrapper around the Request library's Session which makes API calls to DSpace easier to manage.

    This Session handles username and password based authentication, not Shibboleth authentication.

    It handles authentication bearer tokens and CSRF tokens on behalf of the user.

    The endpoint URL should be in the form "https://your.dspace.domain.here.org/server". It
    should present the user with the HAL browser when visiting from a web browser. Most API
    endpoints append "/api/path/here" to the server endpoint, except the actuator endpoints.

    Per the DSpace RestContract documentation:
    "The client MUST store/keep a copy of this CSRF token (usually by watching for the DSPACE-XSRF-TOKEN
    header in every response), and update that stored copy whenever a new token is sent."
    https://github.com/DSpace/RestContract/blob/main/csrf-tokens.md
    In this class, we override the request() method so that on every call to the API,
    the session's X-XSRF-TOKEN request header is updated with new versions of the CSRF token from
    the DSPACE-XSRF-TOKEN response header.

    This class also sends a form-encoded POST request to /api/authn/login with the provided username and password
    on initialization. The API returns a JWT bearer token, which is stored in the session's Authentication header.
    When making a request, this class checks that the stored bearer token isn't within TOKEN_EXPIRY_BUFFER_SECONDS
    of expiring, currently set to 5 minutes. If it is, it sends a POST request to /api/authn/login with no parameters,
    and stores the new bearer token in the session's Authentication header.

    This class will also prepend the provided endpoint to request URL which start with "/".

    Unlike the underlying Session class, this class can raise exceptions on initialization, if the username or
    password arguments are empty or if the server endpoint URL does not start with http:// or https://.
    It may also raise an exception on initialization if the initial authentication request to /api/authn/login
    fails with a non-200 status code.

    Also unlike the underlying Session class, this class will raise exceptions when making requests if the
    authentication token is expired and the request to /api/authn/login to refresh the token fails with
    a non-200 status code.
    """

    def __init__(self, endpoint: str, username: str, password: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
            raise ValueError(
                "The DSpace API endpoint URL must use the http or https scheme."
            )
        # We store a normalized version of the endpoint with no trailing slash.
        self.__endpoint = endpoint.rstrip("/")
        if not username.strip():
            raise ValueError("The username cannot be empty")
        self.username = username
        if not password.strip():
            raise ValueError("The password cannot be empty")
        self.password = password
        self.expiry = None
        self.__get_authentication_token()

    def __get_authentication_token(self):
        # We need to set a valid CSRF token in the session headers.
        # The overloaded request() method takes care of storing the CSRF.
        response = self.get(self.__endpoint + "/api/security/csrf")
        response = self.post(
            self.__endpoint + "/api/authn/login",
            data={"user": self.username, "password": self.password},
        )
        response.raise_for_status()
        self.__process_authentication_token(response)

    def __refresh_authentication_token(self):
        # To ensure our CSRF token is up-to-date, we refresh it manually.
        response = self.get(self.__endpoint + "/api/security/csrf")
        response = self.post(
            self.__endpoint + "/api/authn/login",
        )
        response.raise_for_status()
        self.__process_authentication_token(response)

    def __process_authentication_token(self, response):
        if "Authorization" not in response.headers:
            raise ValueError("Authorization header not in response")
        if "." not in response.headers["Authorization"]:
            raise ValueError("Authorization header is malformed")
        self.headers["Authorization"] = response.headers["Authorization"]
        self.__update_token_expiry()

    def __update_token_expiry(self):
        # We can pull the expiry from the JWT token.
        jwt_payload = self.headers["Authorization"].split(".")[1]
        # From https://dev.to/elwin013/reading-jwt-token-claims-without-a-library-a4l
        # By adding "==" characters to the end of the base64 encoded string,
        # we ensure it has the right amount of padding. Unneeded padding
        # characters are ignored.
        jwt_payload_decoded = str(base64.b64decode(jwt_payload + "=="), "utf-8")
        jwt_payload_dict = json.loads(jwt_payload_decoded)
        if "exp" not in jwt_payload_dict:
            self.expiry = time.time() + FALLBACK_TOKEN_EXPIRY_SECONDS
        else:
            self.expiry = jwt_payload_dict["exp"]

    def request(self, method, url, **kwargs):
        if self.expiry and time.time() + TOKEN_EXPIRY_BUFFER_SECONDS >= self.expiry:
            self.expiry = None
            self.__refresh_authentication_token()
        if url.startswith("/"):
            url = self.__endpoint + url
        response = super().request(method, url, **kwargs)
        if "DSPACE-XSRF-TOKEN" in response.headers:
            self.headers["X-XSRF-TOKEN"] = response.headers["DSPACE-XSRF-TOKEN"]
        return response
