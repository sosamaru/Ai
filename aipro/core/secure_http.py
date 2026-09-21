"""Credentialed clients never forward requests through HTTP redirects."""
from urllib import request
from urllib.error import HTTPError


class NoCredentialRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "credentialed redirect blocked", headers, None)


def open_credentialed(req, *, timeout):
    return request.build_opener(NoCredentialRedirect()).open(req, timeout=timeout)


def read_bounded(response, limit=8_000_000):
    raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("provider response exceeded byte limit")
    return raw
