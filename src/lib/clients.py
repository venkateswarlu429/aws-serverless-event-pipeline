"""Lazily-created boto3 clients.

Clients are built on first use (not at import) so unit tests can set
environment variables and start moto before any client exists. In Lambda the
client is cached on the module for the lifetime of the execution environment,
which is the standard warm-start optimisation.
"""

import boto3

_clients: dict = {}


def get_client(service: str):
    if service not in _clients:
        # AWS_ENDPOINT_URL is honoured automatically by boto3 and lets the
        # same code run against LocalStack/moto-style endpoints locally.
        _clients[service] = boto3.client(service)
    return _clients[service]


def reset_clients() -> None:
    """Test hook: drop cached clients (e.g. after changing env vars)."""
    _clients.clear()
