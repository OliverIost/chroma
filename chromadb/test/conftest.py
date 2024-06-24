import multiprocessing
from multiprocessing.connection import Connection, wait
from multiprocessing.context import SpawnProcess
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from typing import (
    Any,
    Generator,
    Iterator,
    List,
    Optional,
    Sequence,
    Tuple,
    Callable,
    cast,
)
from uuid import UUID

import hypothesis
import pytest
import uvicorn
from httpx import ConnectError
from typing_extensions import Protocol

from chromadb.api.async_fastapi import AsyncFastAPI
from chromadb.api.fastapi import FastAPI
import chromadb.server.fastapi
from chromadb.api import ClientAPI, ServerAPI
from chromadb.config import Settings, System
from chromadb.db.mixins import embeddings_queue
from chromadb.ingest import Producer
from chromadb.types import SeqId, OperationRecord
from chromadb.api.client import Client as ClientCreator, AdminClient
from chromadb.api.async_client import (
    AsyncAdminClient,
    AsyncClient as AsyncClientCreator,
)
from chromadb.utils.async_to_sync import async_class_to_sync

VALID_PRESETS = ["fast", "normal", "slow"]
CURRENT_PRESET = os.getenv("PROPERTY_TESTING_PRESET", "fast")

if CURRENT_PRESET not in VALID_PRESETS:
    raise ValueError(
        f"Invalid property testing preset: {CURRENT_PRESET}. Must be one of {VALID_PRESETS}."
    )

hypothesis.settings.register_profile(
    "base",
    deadline=45000,
    suppress_health_check=[
        hypothesis.HealthCheck.data_too_large,
        hypothesis.HealthCheck.large_base_example,
        hypothesis.HealthCheck.function_scoped_fixture,
    ],
)

hypothesis.settings.register_profile(
    "fast", hypothesis.settings.get_profile("base"), max_examples=50
)
# Hypothesis's default max_examples is 100
hypothesis.settings.register_profile(
    "normal", hypothesis.settings.get_profile("base"), max_examples=100
)
hypothesis.settings.register_profile(
    "slow", hypothesis.settings.get_profile("base"), max_examples=200
)

hypothesis.settings.load_profile(CURRENT_PRESET)


def reset(api: ServerAPI) -> None:
    api.reset()
    if not NOT_CLUSTER_ONLY:
        time.sleep(MEMBERLIST_SLEEP)


def override_hypothesis_profile(
    fast: Optional[hypothesis.settings] = None,
    normal: Optional[hypothesis.settings] = None,
    slow: Optional[hypothesis.settings] = None,
) -> Optional[hypothesis.settings]:
    """Override Hypothesis settings for specific profiles.

    For example, to override max_examples only when the current profile is 'fast':

    override_hypothesis_profile(
        fast=hypothesis.settings(max_examples=50),
    )

    Settings will be merged with the default/active profile.
    """

    allowable_override_keys = [
        "deadline",
        "max_examples",
        "stateful_step_count",
        "suppress_health_check",
    ]

    override_profiles = {
        "fast": fast,
        "normal": normal,
        "slow": slow,
    }

    overriding_profile = override_profiles.get(CURRENT_PRESET)

    if overriding_profile is not None:
        overridden_settings = {
            key: value
            for key, value in overriding_profile.__dict__.items()
            if key in allowable_override_keys
        }

        return hypothesis.settings(hypothesis.settings.default, **overridden_settings)

    return hypothesis.settings.default


NOT_CLUSTER_ONLY = os.getenv("CHROMA_CLUSTER_TEST_ONLY") != "1"
MEMBERLIST_SLEEP = 5
COMPACTION_SLEEP = 120


def skip_if_not_cluster() -> pytest.MarkDecorator:
    return pytest.mark.skipif(
        NOT_CLUSTER_ONLY,
        reason="Requires Kubernetes to be running with a valid config",
    )


def generate_self_signed_certificate(output_directory: Path) -> Tuple[Path, Path]:
    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "openssl.cnf"
    )
    print(f"Config path: {config_path}")  # Debug print to verify path
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at {config_path}")

    serverkey_path = output_directory / "serverkey.pem"
    servercert_path = output_directory / "servercert.pem"

    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:4096",
            "-keyout",
            str(serverkey_path),
            "-out",
            str(servercert_path),
            "-days",
            "365",
            "-nodes",
            "-subj",
            "/CN=localhost",
            "-config",
            config_path,
        ],
        check=True,
    )

    return serverkey_path, servercert_path


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]  # type: ignore


def _run_server(
    conn: Connection,  # used to send the selected port back to the parent process
    settings: Settings,
    chroma_server_ssl_certfile: Optional[str] = None,
    chroma_server_ssl_keyfile: Optional[str] = None,
) -> None:
    app_server = chromadb.server.fastapi.FastAPI(settings)

    config = uvicorn.Config(
        app_server.app(),
        # Bind to first available port (we would prefer to pass a socket here so we know the port in advance, but uvicorn doesn't support that)
        port=0,
        host="0.0.0.0",
        log_level="error",
        timeout_keep_alive=30,
        ssl_keyfile=chroma_server_ssl_keyfile,
        ssl_certfile=chroma_server_ssl_certfile,
    )
    server = uvicorn.Server(config)

    # Hacky, but seems to be the best way to obtain the port
    orig_log_started_message = server._log_started_message

    def patch_log_started_message(listeners) -> None:
        orig_log_started_message(listeners)
        port = server.servers[0].sockets[0].getsockname()[1]
        conn.send(port)

    server._log_started_message = patch_log_started_message

    server.run()


def spawn_server(
    is_persistent: bool = False,
    persist_directory: Optional[str] = None,
    chroma_server_authn_provider: Optional[str] = None,
    chroma_server_authn_credentials_file: Optional[str] = None,
    chroma_server_authn_credentials: Optional[str] = None,
    chroma_auth_token_transport_header: Optional[str] = None,
    chroma_server_authz_provider: Optional[str] = None,
    chroma_server_authz_config_file: Optional[str] = None,
    chroma_server_ssl_certfile: Optional[str] = None,
    chroma_server_ssl_keyfile: Optional[str] = None,
    chroma_overwrite_singleton_tenant_database_access_from_auth: Optional[bool] = False,
) -> Tuple[int, SpawnProcess]:
    """Run a Chroma server locally. Returns a tuple of the port and spawned process. The server is ready to accept requests when this function returns."""

    if is_persistent and persist_directory:
        settings = Settings(
            chroma_api_impl="chromadb.api.segment.SegmentAPI",
            chroma_sysdb_impl="chromadb.db.impl.sqlite.SqliteDB",
            chroma_producer_impl="chromadb.db.impl.sqlite.SqliteDB",
            chroma_consumer_impl="chromadb.db.impl.sqlite.SqliteDB",
            chroma_segment_manager_impl="chromadb.segment.impl.manager.local.LocalSegmentManager",
            is_persistent=is_persistent,
            persist_directory=persist_directory,
            allow_reset=True,
            chroma_server_authn_provider=chroma_server_authn_provider,
            chroma_server_authn_credentials_file=chroma_server_authn_credentials_file,
            chroma_server_authn_credentials=chroma_server_authn_credentials,
            chroma_auth_token_transport_header=chroma_auth_token_transport_header,
            chroma_server_authz_provider=chroma_server_authz_provider,
            chroma_server_authz_config_file=chroma_server_authz_config_file,
            chroma_overwrite_singleton_tenant_database_access_from_auth=chroma_overwrite_singleton_tenant_database_access_from_auth,
        )
    else:
        settings = Settings(
            chroma_api_impl="chromadb.api.segment.SegmentAPI",
            chroma_sysdb_impl="chromadb.db.impl.sqlite.SqliteDB",
            chroma_producer_impl="chromadb.db.impl.sqlite.SqliteDB",
            chroma_consumer_impl="chromadb.db.impl.sqlite.SqliteDB",
            chroma_segment_manager_impl="chromadb.segment.impl.manager.local.LocalSegmentManager",
            is_persistent=False,
            allow_reset=True,
            chroma_server_authn_provider=chroma_server_authn_provider,
            chroma_server_authn_credentials_file=chroma_server_authn_credentials_file,
            chroma_server_authn_credentials=chroma_server_authn_credentials,
            chroma_auth_token_transport_header=chroma_auth_token_transport_header,
            chroma_server_authz_provider=chroma_server_authz_provider,
            chroma_server_authz_config_file=chroma_server_authz_config_file,
            chroma_overwrite_singleton_tenant_database_access_from_auth=chroma_overwrite_singleton_tenant_database_access_from_auth,
        )

    r, w = multiprocessing.Pipe()
    ctx = multiprocessing.get_context("spawn")
    proc = ctx.Process(
        target=_run_server,
        args=(w, settings, chroma_server_ssl_keyfile, chroma_server_ssl_certfile),
        daemon=True,
    )
    proc.start()
    w.close()
    r = wait([r], timeout=5)  # type: ignore
    port = r[0].recv()  # type: ignore
    return (port, proc)


def _await_server(api: ServerAPI, attempts: int = 0) -> None:
    try:
        api.heartbeat()
    except ConnectError as e:
        if attempts > 15:
            raise e
        else:
            time.sleep(4)
            _await_server(api, attempts + 1)


def _fastapi_fixture(
    is_persistent: bool = False,
    chroma_api_impl: str = "chromadb.api.fastapi.FastAPI",
    chroma_server_authn_provider: Optional[str] = None,
    chroma_client_auth_provider: Optional[str] = None,
    chroma_server_authn_credentials_file: Optional[str] = None,
    chroma_server_authn_credentials: Optional[str] = None,
    chroma_client_auth_credentials: Optional[str] = None,
    chroma_auth_token_transport_header: Optional[str] = None,
    chroma_server_authz_provider: Optional[str] = None,
    chroma_server_authz_config_file: Optional[str] = None,
    chroma_server_ssl_certfile: Optional[str] = None,
    chroma_server_ssl_keyfile: Optional[str] = None,
    chroma_overwrite_singleton_tenant_database_access_from_auth: Optional[bool] = False,
) -> Generator[System, None, None]:
    """Fixture generator that launches a server in a separate process, and yields a
    fastapi client connect to it"""

    args: Tuple[
        bool,
        Optional[str],
        Optional[str],
        Optional[str],
        Optional[str],
        Optional[str],
        Optional[str],
        Optional[str],
        Optional[str],
        Optional[str],
        Optional[bool],
    ] = (
        False,
        None,
        chroma_server_authn_provider,
        chroma_server_authn_credentials_file,
        chroma_server_authn_credentials,
        chroma_auth_token_transport_header,
        chroma_server_authz_provider,
        chroma_server_authz_config_file,
        chroma_server_ssl_certfile,
        chroma_server_ssl_keyfile,
        chroma_overwrite_singleton_tenant_database_access_from_auth,
    )

    def run(args: Any) -> Generator[System, None, None]:
        (port, proc) = spawn_server(*args)
        settings = Settings(
            chroma_api_impl=chroma_api_impl,
            chroma_server_host="localhost",
            chroma_server_http_port=port,
            allow_reset=True,
            chroma_client_auth_provider=chroma_client_auth_provider,
            chroma_client_auth_credentials=chroma_client_auth_credentials,
            chroma_auth_token_transport_header=chroma_auth_token_transport_header,
            chroma_server_ssl_verify=chroma_server_ssl_certfile,
            chroma_server_ssl_enabled=True if chroma_server_ssl_certfile else False,
            chroma_overwrite_singleton_tenant_database_access_from_auth=chroma_overwrite_singleton_tenant_database_access_from_auth,
        )
        system = System(settings)
        system.start()
        yield system
        system.stop()
        proc.kill()
        proc.join()

    if is_persistent:
        persist_directory = tempfile.TemporaryDirectory()
        args = (
            is_persistent,
            persist_directory.name,
            chroma_server_authn_provider,
            chroma_server_authn_credentials_file,
            chroma_server_authn_credentials,
            chroma_auth_token_transport_header,
            chroma_server_authz_provider,
            chroma_server_authz_config_file,
            chroma_server_ssl_certfile,
            chroma_server_ssl_keyfile,
            chroma_overwrite_singleton_tenant_database_access_from_auth,
        )

        yield from run(args)

        try:
            persist_directory.cleanup()

        # (Older versions of Python throw NotADirectoryError sometimes instead of PermissionError)
        # (when we drop support for Python < 3.10, we should use ignore_cleanup_errors=True with the context manager instead)
        except (PermissionError, NotADirectoryError) as e:
            # todo: what's holding onto directory contents on Windows?
            if os.name == "nt":
                pass
            else:
                raise e

    else:
        yield from run(args)


def fastapi() -> Generator[System, None, None]:
    return _fastapi_fixture(is_persistent=False)


def async_fastapi() -> Generator[System, None, None]:
    return _fastapi_fixture(
        is_persistent=False,
        chroma_api_impl="chromadb.api.async_fastapi.AsyncFastAPI",
    )


def fastapi_persistent() -> Generator[System, None, None]:
    return _fastapi_fixture(is_persistent=True)


def fastapi_ssl() -> Generator[System, None, None]:
    cert_dir = Path(tempfile.mkdtemp())
    (serverkey_path, servercert_path) = generate_self_signed_certificate(cert_dir)
    return _fastapi_fixture(
        is_persistent=False,
        chroma_server_ssl_certfile=str(servercert_path),
        chroma_server_ssl_keyfile=str(serverkey_path),
    )


def basic_http_client() -> Generator[System, None, None]:
    settings = Settings(
        chroma_api_impl="chromadb.api.fastapi.FastAPI",
        chroma_server_http_port=8000,
        chroma_server_host="localhost",
        allow_reset=True,
    )
    system = System(settings)
    api = system.instance(ServerAPI)
    _await_server(api)
    system.start()
    yield system
    system.stop()


def fastapi_server_basic_auth_valid_cred_single_user() -> Generator[System, None, None]:
    # This (and similar usage below) should use the delete_on_close parameter
    # instead of delete=False, but it's only available in Python 3.12 and later.
    # We must explicitly close the file before spawning a subprocess to avoid
    # file locking issues on Windows.
    with tempfile.NamedTemporaryFile("w", suffix=".htpasswd", delete=False) as f:
        f.write("admin:$2y$05$e5sRb6NCcSH3YfbIxe1AGu2h5K7OOd982OXKmd8WyQ3DRQ4MvpnZS\n")
        f.close()

        for item in _fastapi_fixture(
            is_persistent=False,
            chroma_server_authn_provider="chromadb.auth.basic_authn.BasicAuthenticationServerProvider",
            chroma_server_authn_credentials_file=f.name,
            chroma_client_auth_provider="chromadb.auth.basic_authn.BasicAuthClientProvider",
            chroma_client_auth_credentials="admin:admin",
        ):
            yield item


def fastapi_server_basic_auth_valid_cred_multiple_users() -> (
    Generator[System, None, None]
):
    creds = {
        "user": "$2y$10$kY9hn.Wlfcj7n1Cnjmy1kuIhEFIVBsfbNWLQ5ahoKmdc2HLA4oP6i",
        "user2": "$2y$10$CymQ63tic/DRj8dD82915eoM4ke3d6RaNKU4dj4IVJlHyea0yeGDS",
        "admin": "$2y$05$e5sRb6NCcSH3YfbIxe1AGu2h5K7OOd982OXKmd8WyQ3DRQ4MvpnZS",
    }
    with tempfile.NamedTemporaryFile("w", suffix=".htpasswd", delete=False) as f:
        for user, cred in creds.items():
            f.write(f"{user}:{cred}\n")
        f.close()

        for item in _fastapi_fixture(
            is_persistent=False,
            chroma_server_authn_provider="chromadb.auth.basic_authn.BasicAuthenticationServerProvider",
            chroma_server_authn_credentials_file=f.name,
            chroma_client_auth_provider="chromadb.auth.basic_authn.BasicAuthClientProvider",
            chroma_client_auth_credentials="admin:admin",
        ):
            yield item


def fastapi_server_basic_auth_invalid_cred() -> Generator[System, None, None]:
    with tempfile.NamedTemporaryFile("w", suffix=".htpasswd", delete=False) as f:
        f.write("admin:$2y$05$e5sRb6NCcSH3YfbIxe1AGu2h5K7OOd982OXKmd8WyQ3DRQ4MvpnZS\n")
        f.close()

        for item in _fastapi_fixture(
            is_persistent=False,
            chroma_server_authn_provider="chromadb.auth.basic_authn.BasicAuthenticationServerProvider",
            chroma_server_authn_credentials_file=f.name,
            chroma_client_auth_provider="chromadb.auth.basic_authn.BasicAuthClientProvider",
            chroma_client_auth_credentials="admin:admin1",
        ):
            yield item


def fastapi_server_basic_authn_rbac_authz() -> Generator[System, None, None]:
    with tempfile.NamedTemporaryFile(
        "w", suffix=".htpasswd", delete=False
    ) as server_authn_file:
        server_authn_file.write(
            "admin:$2y$05$e5sRb6NCcSH3YfbIxe1AGu2h5K7OOd982OXKmd8WyQ3DRQ4MvpnZS\n"
        )
        server_authn_file.close()

        with tempfile.NamedTemporaryFile(
            "w", suffix=".authz", delete=False
        ) as server_authz_file:
            server_authz_file.write(
                """
roles_mapping:
    admin:
        actions:
            [
                "system:reset",
                "tenant:create_tenant",
                "tenant:get_tenant",
                "db:create_database",
                "db:get_database",
                "db:list_collections",
                "db:create_collection",
                "db:get_or_create_collection",
                "collection:get_collection",
                "collection:delete_collection",
                "collection:update_collection",
                "collection:add",
                "collection:delete",
                "collection:get",
                "collection:query",
                "collection:peek",
                "collection:update",
                "collection:upsert",
                "collection:count",
            ]
users:
- id: admin
  role: admin
    """
            )
            server_authz_file.close()

            for item in _fastapi_fixture(
                is_persistent=False,
                chroma_client_auth_provider="chromadb.auth.basic_authn.BasicAuthClientProvider",
                chroma_client_auth_credentials="admin:admin",
                chroma_server_authn_provider="chromadb.auth.basic_authn.BasicAuthenticationServerProvider",
                chroma_server_authn_credentials_file=server_authn_file.name,
                chroma_server_authz_provider="chromadb.auth.simple_rbac_authz.SimpleRBACAuthorizationProvider",
                chroma_server_authz_config_file=server_authz_file.name,
            ):
                yield item


def fastapi_fixture_admin_and_singleton_tenant_db_user() -> (
    Generator[System, None, None]
):
    with tempfile.NamedTemporaryFile("w", suffix=".authn", delete=False) as f:
        f.write(
            """
users:
  - id: admin
    tokens:
      - admin-token
  - id: singleton_user
    tenant: singleton_tenant
    databases:
      - singleton_database
    tokens:
      - singleton-token
"""
        )
        f.close()

        for item in _fastapi_fixture(
            is_persistent=False,
            chroma_overwrite_singleton_tenant_database_access_from_auth=True,
            chroma_client_auth_provider="chromadb.auth.token_authn.TokenAuthClientProvider",
            chroma_client_auth_credentials="admin-token",
            chroma_server_authn_provider="chromadb.auth.token_authn.TokenAuthenticationServerProvider",
            chroma_server_authn_credentials_file=f.name,
        ):
            yield item


def integration() -> Generator[System, None, None]:
    """Fixture generator for returning a client configured via environmenet
    variables, intended for externally configured integration tests
    """
    settings = Settings(allow_reset=True)
    system = System(settings)
    system.start()
    yield system
    system.stop()


def sqlite() -> Generator[System, None, None]:
    """Fixture generator for segment-based API using in-memory Sqlite"""
    settings = Settings(
        chroma_api_impl="chromadb.api.segment.SegmentAPI",
        chroma_sysdb_impl="chromadb.db.impl.sqlite.SqliteDB",
        chroma_producer_impl="chromadb.db.impl.sqlite.SqliteDB",
        chroma_consumer_impl="chromadb.db.impl.sqlite.SqliteDB",
        chroma_segment_manager_impl="chromadb.segment.impl.manager.local.LocalSegmentManager",
        is_persistent=False,
        allow_reset=True,
    )
    system = System(settings)
    system.start()
    yield system
    system.stop()


def sqlite_persistent() -> Generator[System, None, None]:
    """Fixture generator for segment-based API using persistent Sqlite"""
    save_path = tempfile.TemporaryDirectory()
    settings = Settings(
        chroma_api_impl="chromadb.api.segment.SegmentAPI",
        chroma_sysdb_impl="chromadb.db.impl.sqlite.SqliteDB",
        chroma_producer_impl="chromadb.db.impl.sqlite.SqliteDB",
        chroma_consumer_impl="chromadb.db.impl.sqlite.SqliteDB",
        chroma_segment_manager_impl="chromadb.segment.impl.manager.local.LocalSegmentManager",
        allow_reset=True,
        is_persistent=True,
        persist_directory=save_path.name,
    )
    system = System(settings)
    system.start()
    yield system
    system.stop()

    try:
        save_path.cleanup()

    # (Older versions of Python throw NotADirectoryError sometimes instead of PermissionError)
    # (when we drop support for Python < 3.10, we should use ignore_cleanup_errors=True with the context manager instead)
    except (PermissionError, NotADirectoryError) as e:
        # todo: what's holding onto directory contents on Windows?
        if os.name == "nt":
            pass
        else:
            raise e


def system_fixtures() -> List[Callable[[], Generator[System, None, None]]]:
    fixtures = [fastapi, async_fastapi, fastapi_persistent, sqlite, sqlite_persistent]
    if "CHROMA_INTEGRATION_TEST" in os.environ:
        fixtures.append(integration)
    if "CHROMA_INTEGRATION_TEST_ONLY" in os.environ:
        fixtures = [integration]
    if "CHROMA_CLUSTER_TEST_ONLY" in os.environ:
        fixtures = [basic_http_client]
    return fixtures


def system_fixtures_auth() -> List[Callable[[], Generator[System, None, None]]]:
    fixtures = [
        fastapi_server_basic_auth_valid_cred_single_user,
        fastapi_server_basic_auth_valid_cred_multiple_users,
    ]
    return fixtures


def system_fixtures_authn_rbac_authz() -> (
    List[Callable[[], Generator[System, None, None]]]
):
    fixtures = [fastapi_server_basic_authn_rbac_authz]
    return fixtures


def system_fixtures_root_and_singleton_tenant_db_user() -> (
    List[Callable[[], Generator[System, None, None]]]
):
    fixtures = [fastapi_fixture_admin_and_singleton_tenant_db_user]
    return fixtures


def system_fixtures_wrong_auth() -> List[Callable[[], Generator[System, None, None]]]:
    fixtures = [fastapi_server_basic_auth_invalid_cred]
    return fixtures


def system_fixtures_ssl() -> List[Callable[[], Generator[System, None, None]]]:
    fixtures = [fastapi_ssl]
    return fixtures


@pytest.fixture(scope="module", params=system_fixtures_wrong_auth())
def system_wrong_auth(
    request: pytest.FixtureRequest,
) -> Generator[ServerAPI, None, None]:
    yield from request.param()


@pytest.fixture(scope="module", params=system_fixtures_authn_rbac_authz())
def system_authn_rbac_authz(
    request: pytest.FixtureRequest,
) -> Generator[ServerAPI, None, None]:
    yield from request.param()


@pytest.fixture(scope="module", params=system_fixtures())
def system(request: pytest.FixtureRequest) -> Generator[ServerAPI, None, None]:
    yield from request.param()


@pytest.fixture(scope="module", params=system_fixtures_ssl())
def system_ssl(request: pytest.FixtureRequest) -> Generator[ServerAPI, None, None]:
    yield from request.param()


@pytest.fixture(scope="module", params=system_fixtures_auth())
def system_auth(request: pytest.FixtureRequest) -> Generator[ServerAPI, None, None]:
    yield from request.param()


@async_class_to_sync
class AsyncClientCreatorSync(AsyncClientCreator):
    pass


@async_class_to_sync
class AsyncAdminClientSync(AsyncAdminClient):
    pass


@pytest.fixture(scope="function")
def api(system: System) -> Generator[ServerAPI, None, None]:
    system.reset_state()
    api = system.instance(ServerAPI)

    if isinstance(api, AsyncFastAPI):
        transformed = async_class_to_sync(api)
        yield transformed
    else:
        yield api


class ClientFactories:
    """This allows consuming tests to be parameterized by async/sync versions of the client and papers over the async implementation.
    If you don't need to manually construct clients, use the `client` fixture instead.
    """

    _system: System
    # Need to track created clients so we can call .clear_system_cache() during teardown
    _created_clients: List[ClientAPI] = []

    def __init__(self, system: System):
        self._system = system

    def create_client(self, *args: Any, **kwargs: Any) -> ClientCreator:
        if kwargs.get("settings") is None:
            kwargs["settings"] = self._system.settings

        if (
            self._system.settings.chroma_api_impl
            == "chromadb.api.async_fastapi.AsyncFastAPI"
        ):
            client = cast(ClientCreator, AsyncClientCreatorSync.create(*args, **kwargs))
            self._created_clients.append(client)
            return client

        client = ClientCreator(*args, **kwargs)
        self._created_clients.append(client)
        return client

    def create_admin_client(self, *args: Any, **kwargs: Any) -> AdminClient:
        if (
            self._system.settings.chroma_api_impl
            == "chromadb.api.async_fastapi.AsyncFastAPI"
        ):
            return cast(AdminClient, AsyncAdminClientSync(*args, **kwargs))

        return AdminClient(*args, **kwargs)

    def create_admin_client_from_system(self) -> AdminClient:
        if (
            self._system.settings.chroma_api_impl
            == "chromadb.api.async_fastapi.AsyncFastAPI"
        ):
            return cast(AdminClient, AsyncAdminClientSync.from_system(self._system))

        return AdminClient.from_system(self._system)


@pytest.fixture(scope="function")
def client_factories(system: System) -> Generator[ClientFactories, None, None]:
    system.reset_state()

    factories = ClientFactories(system)
    yield factories

    while len(factories._created_clients) > 0:
        client = factories._created_clients.pop()
        client.clear_system_cache()
        del client


@pytest.fixture(scope="function")
def client(system: System) -> Generator[ClientAPI, None, None]:
    system.reset_state()

    if system.settings.chroma_api_impl == "chromadb.api.async_fastapi.AsyncFastAPI":
        client = cast(Any, AsyncClientCreatorSync.from_system_async(system))
        yield client
        client.clear_system_cache()
    else:
        client = ClientCreator.from_system(system)
        yield client
        client.clear_system_cache()


@pytest.fixture(scope="function")
def client_ssl(system_ssl: System) -> Generator[ClientAPI, None, None]:
    system_ssl.reset_state()
    client = ClientCreator.from_system(system_ssl)
    yield client
    client.clear_system_cache()


@pytest.fixture(scope="function")
def api_wrong_cred(
    system_wrong_auth: System,
) -> Generator[ServerAPI, None, None]:
    system_wrong_auth.reset_state()
    api = system_wrong_auth.instance(ServerAPI)
    yield api


@pytest.fixture(scope="function")
def api_with_authn_rbac_authz(
    system_authn_rbac_authz: System,
) -> Generator[ServerAPI, None, None]:
    system_authn_rbac_authz.reset_state()
    api = system_authn_rbac_authz.instance(ServerAPI)
    yield api


@pytest.fixture(scope="function")
def api_with_server_auth(system_auth: System) -> Generator[ServerAPI, None, None]:
    _sys = system_auth
    _sys.reset_state()
    api = _sys.instance(ServerAPI)
    yield api


# Producer / Consumer fixtures #


class ProducerFn(Protocol):
    def __call__(
        self,
        producer: Producer,
        collection_id: UUID,
        embeddings: Iterator[OperationRecord],
        n: int,
    ) -> Tuple[Sequence[OperationRecord], Sequence[SeqId]]:
        ...


def produce_n_single(
    producer: Producer,
    collection_id: UUID,
    embeddings: Iterator[OperationRecord],
    n: int,
) -> Tuple[Sequence[OperationRecord], Sequence[SeqId]]:
    submitted_embeddings = []
    seq_ids = []
    for _ in range(n):
        e = next(embeddings)
        seq_id = producer.submit_embedding(collection_id, e)
        submitted_embeddings.append(e)
        seq_ids.append(seq_id)
    return submitted_embeddings, seq_ids


def produce_n_batch(
    producer: Producer,
    collection_id: UUID,
    embeddings: Iterator[OperationRecord],
    n: int,
) -> Tuple[Sequence[OperationRecord], Sequence[SeqId]]:
    submitted_embeddings = []
    seq_ids: Sequence[SeqId] = []
    for _ in range(n):
        e = next(embeddings)
        submitted_embeddings.append(e)
    seq_ids = producer.submit_embeddings(collection_id, submitted_embeddings)
    return submitted_embeddings, seq_ids


def produce_fn_fixtures() -> List[ProducerFn]:
    return [produce_n_single, produce_n_batch]


@pytest.fixture(scope="module", params=produce_fn_fixtures())
def produce_fns(
    request: pytest.FixtureRequest,
) -> Generator[ProducerFn, None, None]:
    yield request.param


def pytest_configure(config):  # type: ignore
    embeddings_queue._called_from_test = True
