# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: notification.proto
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x12notification.proto\x12\x07\x66\x64l_svc\"\xa2\x01\n\x17UserNotificationMessage\x12=\n\trequester\x18\x01 \x01(\x0b\x32*.fdl_svc.UserNotificationMessage.Requester\x12\x0f\n\x07zipfile\x18\x02 \x01(\t\x12\r\n\x05\x66iles\x18\x03 \x03(\t\x1a(\n\tRequester\x12\r\n\x05\x65mail\x18\x01 \x01(\t\x12\x0c\n\x04name\x18\x02 \x01(\tb\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'notification_pb2', _globals)
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  _globals['_USERNOTIFICATIONMESSAGE']._serialized_start=32
  _globals['_USERNOTIFICATIONMESSAGE']._serialized_end=194
  _globals['_USERNOTIFICATIONMESSAGE_REQUESTER']._serialized_start=154
  _globals['_USERNOTIFICATIONMESSAGE_REQUESTER']._serialized_end=194
# @@protoc_insertion_point(module_scope)
