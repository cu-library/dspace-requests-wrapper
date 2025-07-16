# DSpace Requests Wrapper

A wrapper around the Request library's Session which makes API calls to DSpace easier to manage.

This library provides a class, DSpaceSession, which handles username and password based authentication, not Shibboleth authentication.

It handles authentication bearer tokens and CSRF tokens on behalf of the user.

The endpoint URL should be in the form "https://your.dspace.domain.here.org/server". It should present the user with the HAL browser 
when visiting from a web browser. Most API endpoints append "/api/path/here" to the server endpoint, except the actuator endpoints.

Per the DSpace RestContract documentation:
"The client MUST store/keep a copy of this CSRF token (usually by watching for the DSPACE-XSRF-TOKEN header in every response), and 
update that stored copy whenever a new token is sent." 
https://github.com/DSpace/RestContract/blob/main/csrf-tokens.md
In this class, we override the request() method so that on every call to the API, the session's X-XSRF-TOKEN request header is updated
with new versions of the CSRF token from the DSPACE-XSRF-TOKEN response header.

This class also sends a form-encoded POST request to /api/authn/login with the provided username and password on initialization.
The API returns a JWT bearer token, which is stored in the session's Authentication header.
When making a request, this class checks that the stored bearer token isn't within 5 minutes of expiring.
If it is, it sends a POST request to /api/authn/login with no parameters, and stores the new bearer token in the session's
Authentication header.

Since the session knows the server endpoint, you can make requests to URLs like "/actuator/health" or "/api/core/communities",
and the server endpoint will be automatically prepended.

## Example

```python
import pprint
import dspace_requests_wrapper

s = space_requests_wrapper.DSpaceSession("https://your.dspace.here/server", "auserhere", "hunter42")
# Make a GET request to https://your.dspace.here/server/actuator/info with valid CSRF and Authentication headers:
pprint.pprint(s.get("/actuator/info").json())
```

## Large File Transfers using chunked encoding

```python
import dspace_requests_wrapper
from requests_toolbelt.multipart import encoder

file = "testfile.bin"

with open(file, 'rb') as file_handle:

    s = space_requests_wrapper.DSpaceSession("https://your.dspace.here/server", "auserhere", "hunter42")
    files = {'file': (file, file_handle, 'application/octet-stream')}

    e = encoder.MultipartEncoder(files)
    m = encoder.MultipartEncoderMonitor(e, lambda a: print(a.bytes_read, end='\r'))

    # A generator function, which yields 16384 byte chunks of the underlying file.
    def gen():
        a = m.read(16384)
        while a:
            yield a
            a = m.read(16384)

    r = s.post("/api/core/bundles/EXISTING_BUNDLE_UUID_HERE/bitstreams", data=gen(),  headers={'Content-Type': m.content_type})
    r.raise_for_status()
    print(r.status_code)

```

