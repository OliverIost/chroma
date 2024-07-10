# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
"""Client and server classes corresponding to protobuf-defined services."""
import grpc
import warnings

from chromadb.proto import debug_pb2 as chromadb_dot_proto_dot_debug__pb2
from google.protobuf import empty_pb2 as google_dot_protobuf_dot_empty__pb2

<<<<<<< HEAD
GRPC_GENERATED_VERSION = '1.64.1'
GRPC_VERSION = grpc.__version__
EXPECTED_ERROR_RELEASE = '1.65.0'
SCHEDULED_RELEASE_DATE = 'June 25, 2024'
=======
GRPC_GENERATED_VERSION = "1.64.1"
GRPC_VERSION = grpc.__version__
EXPECTED_ERROR_RELEASE = "1.65.0"
SCHEDULED_RELEASE_DATE = "June 25, 2024"
>>>>>>> 9c9da226 (fix linter issues)
_version_not_supported = False

try:
    from grpc._utilities import first_version_is_lower
<<<<<<< HEAD
    _version_not_supported = first_version_is_lower(GRPC_VERSION, GRPC_GENERATED_VERSION)
=======

    _version_not_supported = first_version_is_lower(
        GRPC_VERSION, GRPC_GENERATED_VERSION
    )
>>>>>>> 9c9da226 (fix linter issues)
except ImportError:
    _version_not_supported = True

if _version_not_supported:
    warnings.warn(
<<<<<<< HEAD
        f'The grpc package installed is at version {GRPC_VERSION},'
        + f' but the generated code in chromadb/proto/debug_pb2_grpc.py depends on'
        + f' grpcio>={GRPC_GENERATED_VERSION}.'
        + f' Please upgrade your grpc module to grpcio>={GRPC_GENERATED_VERSION}'
        + f' or downgrade your generated code using grpcio-tools<={GRPC_VERSION}.'
        + f' This warning will become an error in {EXPECTED_ERROR_RELEASE},'
        + f' scheduled for release on {SCHEDULED_RELEASE_DATE}.',
        RuntimeWarning
=======
        f"The grpc package installed is at version {GRPC_VERSION},"
        + f" but the generated code in chromadb/proto/debug_pb2_grpc.py depends on"
        + f" grpcio>={GRPC_GENERATED_VERSION}."
        + f" Please upgrade your grpc module to grpcio>={GRPC_GENERATED_VERSION}"
        + f" or downgrade your generated code using grpcio-tools<={GRPC_VERSION}."
        + f" This warning will become an error in {EXPECTED_ERROR_RELEASE},"
        + f" scheduled for release on {SCHEDULED_RELEASE_DATE}.",
        RuntimeWarning,
>>>>>>> 9c9da226 (fix linter issues)
    )


class DebugStub(object):
    """Missing associated documentation comment in .proto file."""

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.GetInfo = channel.unary_unary(
<<<<<<< HEAD
                '/chroma.Debug/GetInfo',
                request_serializer=google_dot_protobuf_dot_empty__pb2.Empty.SerializeToString,
                response_deserializer=chromadb_dot_proto_dot_debug__pb2.GetInfoResponse.FromString,
                _registered_method=True)
        self.TriggerPanic = channel.unary_unary(
                '/chroma.Debug/TriggerPanic',
                request_serializer=google_dot_protobuf_dot_empty__pb2.Empty.SerializeToString,
                response_deserializer=google_dot_protobuf_dot_empty__pb2.Empty.FromString,
                _registered_method=True)
=======
            "/chroma.Debug/GetInfo",
            request_serializer=google_dot_protobuf_dot_empty__pb2.Empty.SerializeToString,
            response_deserializer=chromadb_dot_proto_dot_debug__pb2.GetInfoResponse.FromString,
            _registered_method=True,
        )
        self.TriggerPanic = channel.unary_unary(
            "/chroma.Debug/TriggerPanic",
            request_serializer=google_dot_protobuf_dot_empty__pb2.Empty.SerializeToString,
            response_deserializer=google_dot_protobuf_dot_empty__pb2.Empty.FromString,
            _registered_method=True,
        )
>>>>>>> 9c9da226 (fix linter issues)


class DebugServicer(object):
    """Missing associated documentation comment in .proto file."""

    def GetInfo(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
<<<<<<< HEAD
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')
=======
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")
>>>>>>> 9c9da226 (fix linter issues)

    def TriggerPanic(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
<<<<<<< HEAD
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')
=======
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")
>>>>>>> 9c9da226 (fix linter issues)


def add_DebugServicer_to_server(servicer, server):
    rpc_method_handlers = {
<<<<<<< HEAD
            'GetInfo': grpc.unary_unary_rpc_method_handler(
                    servicer.GetInfo,
                    request_deserializer=google_dot_protobuf_dot_empty__pb2.Empty.FromString,
                    response_serializer=chromadb_dot_proto_dot_debug__pb2.GetInfoResponse.SerializeToString,
            ),
            'TriggerPanic': grpc.unary_unary_rpc_method_handler(
                    servicer.TriggerPanic,
                    request_deserializer=google_dot_protobuf_dot_empty__pb2.Empty.FromString,
                    response_serializer=google_dot_protobuf_dot_empty__pb2.Empty.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'chroma.Debug', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_registered_method_handlers('chroma.Debug', rpc_method_handlers)


 # This class is part of an EXPERIMENTAL API.
=======
        "GetInfo": grpc.unary_unary_rpc_method_handler(
            servicer.GetInfo,
            request_deserializer=google_dot_protobuf_dot_empty__pb2.Empty.FromString,
            response_serializer=chromadb_dot_proto_dot_debug__pb2.GetInfoResponse.SerializeToString,
        ),
        "TriggerPanic": grpc.unary_unary_rpc_method_handler(
            servicer.TriggerPanic,
            request_deserializer=google_dot_protobuf_dot_empty__pb2.Empty.FromString,
            response_serializer=google_dot_protobuf_dot_empty__pb2.Empty.SerializeToString,
        ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
        "chroma.Debug", rpc_method_handlers
    )
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_registered_method_handlers("chroma.Debug", rpc_method_handlers)


# This class is part of an EXPERIMENTAL API.
>>>>>>> 9c9da226 (fix linter issues)
class Debug(object):
    """Missing associated documentation comment in .proto file."""

    @staticmethod
<<<<<<< HEAD
    def GetInfo(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/chroma.Debug/GetInfo',
=======
    def GetInfo(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        insecure=False,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/chroma.Debug/GetInfo",
>>>>>>> 9c9da226 (fix linter issues)
            google_dot_protobuf_dot_empty__pb2.Empty.SerializeToString,
            chromadb_dot_proto_dot_debug__pb2.GetInfoResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
<<<<<<< HEAD
            _registered_method=True)

    @staticmethod
    def TriggerPanic(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/chroma.Debug/TriggerPanic',
=======
            _registered_method=True,
        )

    @staticmethod
    def TriggerPanic(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        insecure=False,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/chroma.Debug/TriggerPanic",
>>>>>>> 9c9da226 (fix linter issues)
            google_dot_protobuf_dot_empty__pb2.Empty.SerializeToString,
            google_dot_protobuf_dot_empty__pb2.Empty.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
<<<<<<< HEAD
            _registered_method=True)
=======
            _registered_method=True,
        )
>>>>>>> 9c9da226 (fix linter issues)
