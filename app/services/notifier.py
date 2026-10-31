import logging
from app.config import settings

logger = logging.getLogger(__name__)

class DesktopNotifier:
    @staticmethod
    def send_notification(title: str, message: str):
        """
        Sends a native desktop toast notification on Windows.
        """
        try:
            from plyer import notification
            notification.notify(
                title=title,
                message=message,
                app_name="Job Finder Assistant",
                timeout=8
            )
        except Exception as e:
            logger.warning(f"Desktop notification failed: {e}")

desktop_notifier = DesktopNotifier()
