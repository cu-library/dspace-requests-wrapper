import pytest
import requests  # noqa: F401
import dspace_requests_wrapper

JWT_EXP_9000000000 = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMiwiZXhwIjo5MDAwMDAwMDAwfQ.tZNitMGrpzYmc5C3Z4OMmef7IM93ksnqn1mEozVDVBQ"

JWT_EXP_9111111111 = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMiwiZXhwIjo5MTExMTExMTExfQ.5UVwt_chPu3HAUjZAGfY3p92-SaTbWWkJ9A-F1iLh58"


def test_endpoint_scheme():
    with pytest.raises(ValueError):
        dspace_requests_wrapper.DSpaceSession("ftp://nope", "x", "y")


def test_session_init(requests_mock):
    with pytest.raises(ValueError):
        dspace_requests_wrapper.DSpaceSession(
            "https://mydspace.com/server", "", "p@ssw0rd"
        )
    with pytest.raises(ValueError):
        dspace_requests_wrapper.DSpaceSession(
            "https://server.com/api", "    ", "p@ssw0rd"
        )
    with pytest.raises(ValueError):
        dspace_requests_wrapper.DSpaceSession(
            "https://server.com/api", "username", "   "
        )
    requests_mock.get(
        "https://mydspace.com/server/api/security/csrf",
        headers={"DSPACE-XSRF-TOKEN": "CSRF-HERE"},
    )
    requests_mock.post(
        "https://mydspace.com/server/api/authn/login",
        headers={"Authorization": JWT_EXP_9000000000},
    )
    s = dspace_requests_wrapper.DSpaceSession(
        "https://mydspace.com/server", "username", "p@ssw0rd"
    )
    assert s.username == "username"
    assert s.password == "p@ssw0rd"
    assert s.expiry == 9000000000
    assert s.headers["Authorization"] == JWT_EXP_9000000000
    assert s.headers["X-XSRF-TOKEN"] == "CSRF-HERE"


def test_csrf_refresh(requests_mock):
    requests_mock.get(
        "https://mydspace.com/server/api/security/csrf",
        headers={"DSPACE-XSRF-TOKEN": "1"},
    )
    requests_mock.post(
        "https://mydspace.com/server/api/authn/login",
        headers={"Authorization": JWT_EXP_9000000000},
    )
    s = dspace_requests_wrapper.DSpaceSession(
        "https://mydspace.com/server", "username", "p@ssw0rd"
    )
    assert s.headers["X-XSRF-TOKEN"] == "1"
    requests_mock.get(
        "https://mydspace.com/server/api/hello",
        headers={"DSPACE-XSRF-TOKEN": "2"},
    )
    # Did the new XSRF token get stored?
    s.get("/api/hello")
    assert s.headers["X-XSRF-TOKEN"] == "2"


def test_authentication_token_refresh(requests_mock, mocker):
    requests_mock.get(
        "https://mydspace.com/server/api/security/csrf",
        headers={"DSPACE-XSRF-TOKEN": "1"},
    )
    requests_mock.post(
        "https://mydspace.com/server/api/authn/login",
        headers={"Authorization": JWT_EXP_9000000000},
    )
    s = dspace_requests_wrapper.DSpaceSession(
        "https://mydspace.com/server", "username", "p@ssw0rd"
    )
    requests_mock.get(
        "https://mydspace.com/server/api/security/csrf",
        headers={"DSPACE-XSRF-TOKEN": "2"},
    )
    requests_mock.post(
        "https://mydspace.com/server/api/authn/login",
        headers={"Authorization": JWT_EXP_9111111111},
    )
    requests_mock.get("https://mydspace.com/server/api/hello")

    mocker.patch("time.time", return_value=1700000000)
    # During this call, our expiry is well into the future. The token should not be refreshed.
    s.get("/api/hello")
    assert s.headers["X-XSRF-TOKEN"] == "1"
    assert s.expiry == 9000000000

    mocker.patch(
        "time.time",
        return_value=9000000000
        - (dspace_requests_wrapper.TOKEN_EXPIRY_BUFFER_SECONDS + 1),
    )
    # During this call, our expiry is TOKEN_EXPIRY_BUFFER_SECONDS+1 seconds in the future.
    # The token should not be refreshed.
    s.get("/api/hello")
    assert s.headers["X-XSRF-TOKEN"] == "1"
    assert s.expiry == 9000000000

    mocker.patch(
        "time.time",
        return_value=9000000000 - (dspace_requests_wrapper.TOKEN_EXPIRY_BUFFER_SECONDS),
    )
    # During this call, our expiry is TOKEN_EXPIRY_BUFFER_SECONDS seconds in the future.
    # The token should not be refreshed.
    s.get("/api/hello")
    assert s.headers["X-XSRF-TOKEN"] == "2"
    assert s.expiry == 9111111111
