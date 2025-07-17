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

Unlike the underlying Session class, DSpaceSession can raise exceptions on initialization, if the username or
password arguments are empty or if the server endpoint URL does not start with http:// or https://.
It may also raise an exception on initialization if the initial authentication request to /api/authn/login
fails with a non-200 status code.

Also unlike the underlying Session class, DSpaceSession will raise exceptions when making requests if the
authentication token is expired and the request to /api/authn/login to refresh the token fails with
a non-200 status code.

Since the session knows the server endpoint, you can make requests to URLs like "/actuator/health" or "/api/core/communities",
and the server endpoint will be automatically prepended.

# Examples

## Simple GET to /actuator/info

```python
import pprint
import dspace_requests_wrapper

s = space_requests_wrapper.DSpaceSession("https://your.dspace.here/server", "auserhere", "hunter42")

# Make a GET request to https://your.dspace.here/server/actuator/info with valid CSRF and Authentication headers:
pprint.pprint(s.get("/actuator/info").json())
```

## Perform a search

```python
import dspace_requests_wrapper

s = dspace_requests_wrapper.DSpaceSession("https://your.dspace.here/server", "auserhere", "hunter42")

search_url = "/api/discover/search/objects?query=spiders"
while True:
    response = s.get(search_url) # If the URL starts with /, the server endpoint is appended
    response.raise_for_status()
    results = response.json()
    for result in results["_embedded"]["searchResult"]["_embedded"]["objects"]:
        print(result["hitHighlights"])
        print(result["_links"]["indexableObject"]["href"])
    if "next" in results["_embedded"]["searchResult"]["_links"]:
        search_url = results["_embedded"]["searchResult"]["_links"]["next"]["href"]
    else:
        break
```

## Create an item, add the ORIGINAL bundle and upload a bitstream to that bundle

```python

import json
import pprint
import dspace_requests_wrapper

s = dspace_requests_wrapper.DSpaceSession("https://your.dspace.here/server", "auserhere", "hunter42")

# Create the item
example_item = {
    "name": "Practices of research data curation in institutional repositories: A qualitative view from repository staff",
    "metadata": {
        "dc.contributor.author": [
            {
                "value": "Stvilia, Besiki",
                "language": "en",
                "authority": None,
                "confidence": -1,
            }
        ],
        "dc.title": [
            {
                "value": "Practices of research data curation in institutional repositories: A qualitative view from repository staff",
                "language": "en",
                "authority": None,
                "confidence": -1,
            }
        ],
        "dc.type": [
            {
                "value": "Journal Article",
                "language": "en",
                "authority": None,
                "confidence": -1,
            }
        ],
    },
    "inArchive": True,
    "discoverable": True,
    "withdrawn": False,
    "type": "item",
}
response = s.post(
    "/api/core/items?owningCollection=A_COLLECTION_UUID",
    json=example_item,
)
response.raise_for_status()
print("Response from API when creating the item:")
pprint.pprint(response.json())
print("")
item_uuid = response.json()["uuid"]

# GET the item metadata
response = s.get("/api/core/items/" + item_uuid)
response.raise_for_status()
print("Item JSON data from API:")
pprint.pprint(response.json())
print("")

# Create the bundle
response = s.post(
    "/api/core/items/" + item_uuid + "/bundles",
    json={"name": "ORIGINAL"},
)
response.raise_for_status()
print("Response from API when creating the bundle:")
pprint.pprint(response.json())
print("")
bundle_uuid = response.json()["uuid"]

# GET the bundle metadata
response = s.get("/api/core/bundles/" + bundle_uuid)
response.raise_for_status()
print("Bundle JSON data from API:")
pprint.pprint(response.json())
print("")

# Add a bitstream to the bundle
example_pdf_filepath = "/tmp/example.pdf"
example_pdf_metadata = {
    # The name is optional.
    "name": "example_file_name_in_metadata.pdf",
    # The metadata here is optional as well.
    "metadata": {
        "dc.description": [
            {
                "value": "example file",
                "language": None,
                "authority": None,
                "confidence": -1,
                "place": 0,
            }
        ]
    },
}
# Open the file in binary mode with "rb".
with open(example_pdf_filepath, "rb") as example_pdf:
    # You can just use the open file handle as the value of file. The literal filename on disk will be used.
    # bitstream_data = {"file": example_pdf}
    # You can include the file name and mime type in a tuple. The mimetype doesn't matter, DSpace will assign a format using the extension and the format registry.
    # bitstream_data = {"file": ("example_name_here.pdf", example_pdf, "application/msword")} # application/msword is ignored
    # You can also add bitstream properties as JSON under the properties key.
    # bitstream_data = {"file": example_pdf, "properties": (None, json.dumps(example_pdf_metadata), "application/json")}
    # The filename in the properties 'wins', it will be used instead of the supplied filename in the tuple under the 'file' key.
    # bitstream_data = {"file": ("example_name_here_will_not_be_used.pdf", example_pdf), "properties": (None, json.dumps(example_pdf_metadata), "application/json")}
    # It should be possible to ensure the correct MD5 hash and Content Length by adding headers
    # to that part of the form data, at least according to the RestContract documentation.
    # In practice, we haven't been able to get this working. Incorrect headers here do not trigger a 412 HTTP error.
    # Instead, the JSON response has a "checkSum" field which we check against file hashes manually after upload, which we don't include here in this example.
    # bitstream_data = {"file": ("example.pdf", example_pdf, "application/pdf", {"Content-MD5": "MD5-HERE", "Content-Length": "100"}")}

    # For this example, let's use a simple file handle for the 'file' key and add the properties under 'properties'.
    bitstream_data = {
        "file": example_pdf,
        "properties": (None, json.dumps(example_pdf_metadata), "application/json"),
    }

    response = s.post(
        "/api/core/bundles/" + bundle_uuid + "/bitstreams",
        files=bitstream_data,
    )
    print("Response from API when creating the bitstream:")
    pprint.pprint(response.json())
    print("")
    bitstream_uuid = response.json()["uuid"]

# GET the bitstream metadata
response = s.get("/api/core/bitstreams/" + bitstream_uuid)
response.raise_for_status()
print("Bitstream JSON data from API:")
pprint.pprint(response.json())
```

## Large bitstream uploads using chunked encoding

```python
import json
import pprint
import dspace_requests_wrapper
from requests_toolbelt.multipart import encoder

s = dspace_requests_wrapper.DSpaceSession("https://your.dspace.here/server", "auserhere", "hunter42")

# Let's say this is a large file, so large that it should not be held in memory by requests.
large_file_filepath = "/tmp/bigfile.mp4"
# We can use requests_toolbelt.multipart to chunk the request.
# This allows us to continue to use the properties field.
large_file_metadata = {
    "metadata": {
        "dc.description": [
            {
                "value": "example large file",
                "language": None,
                "authority": None,
                "confidence": -1,
                "place": 0,
            }
        ]
    },
}

with open(large_file_filepath, "rb") as large_file:
    files = {
        # "file": large_file, # This does NOT work! You MUST use a tuple here with the filename.
        "file": ("bigfile.mp4", large_file),
        "properties": (None, json.dumps(large_file_metadata), "application/json"),
    }

    encoder = encoder.MultipartEncoder(files)
    # You can monitor the upload by using the MultipartEncoderMonitor instead of the encoder as the data
    # parameter value.
    #monitor = encoder.MultipartEncoderMonitor(e, lambda a: print(a.bytes_read, end="\r"))

    response = s.post(
        "/api/core/bundles/A_BUNDLE_UUID/bitstreams",
        data=encoder,
        #data=monitor,
        headers={"Content-Type": e.content_type},
    )

    # A possible workaround (?) for the hardcoded read size mentioned here:
    # https://toolbelt.readthedocs.io/en/latest/uploading-data.html#requests_toolbelt.multipart.encoder.MultipartEncoder
    # In practice, our upload speed was the same with or without using the generator. YMMV

    # A generator function, which yields 16384 byte chunks of the underlying file.
    #def gen():
    #    a = e.read(16384)
    #    while a:
    #        yield a
    #        a = e.read(16384)
    #
    #response = s.post(
    #    "/api/core/bundles/A_BUNDLE_UUID/bitstreams",
    #    data=gen(),
    #    headers={"Content-Type": e.content_type},
    #)
    response.raise_for_status()
    print("Response from API when creating the bitstream:")
    pprint.pprint(response.json())
    print("")
    bitstream_uuid = response.json()["uuid"]

response = s.get("/api/core/bitstreams/" + bitstream_uuid)
response.raise_for_status()
print("Bitstream JSON data from API:")
pprint.pprint(response.json())
```
