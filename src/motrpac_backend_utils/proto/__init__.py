"""Protocol buffer definitions for the MoTrPAC backend utility function package."""

from .file_download_pb2 import FileDownloadMessage
from .notification_pb2 import UserNotificationMessage

__all__ = ["FileDownloadMessage", "UserNotificationMessage"]
