# standard library imports
import logging
import time

from dataclasses import dataclass, field
from enum import Enum

# third party imports
import bpy


logger = logging.getLogger(__name__)


class ToastLevel(Enum):
    """Toast notification severity levels."""

    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class Toast:
    """A single toast notification."""

    message: str
    level: ToastLevel = ToastLevel.INFO
    created_at: float = field(default_factory=time.time)
    duration: float = 3.0  # seconds

    @property
    def is_expired(self) -> bool:
        """Check if the toast has exceeded its display duration."""
        return time.time() - self.created_at > self.duration

    @property
    def age(self) -> float:
        """Get the age of the toast in seconds."""
        return time.time() - self.created_at

    @property
    def opacity(self) -> float:
        """Calculate opacity based on age for fade-out effect."""
        remaining = self.duration - self.age
        if remaining > 1.0:
            return 1.0
        if remaining > 0:
            return remaining
        return 0.0

    @property
    def color(self) -> tuple[float, float, float, float]:
        """Get the color based on toast level with opacity."""
        base_colors = {
            ToastLevel.INFO: (0.4, 0.7, 1.0),  # Blue
            ToastLevel.SUCCESS: (0.3, 0.9, 0.4),  # Green
            ToastLevel.WARNING: (1.0, 0.8, 0.2),  # Yellow
            ToastLevel.ERROR: (1.0, 0.4, 0.3),  # Red
        }
        r, g, b = base_colors.get(self.level, (1.0, 1.0, 1.0))
        return (r, g, b, self.opacity)


class ToastManager:
    """
    Manages toast notifications for viewport display.

    This is a singleton-style manager that stores and manages toast notifications.
    Toasts automatically expire after their duration and are removed during cleanup.
    Uses a timer to continuously redraw the viewport while toasts are visible.
    """

    _instance: "ToastManager | None" = None
    _timer_running: bool = False

    def __init__(self) -> None:
        # Only initialize instance variables if not already done
        if not hasattr(self, "_initialized"):
            self._toasts: list[Toast] = []
            self._max_visible: int = 5
            self._initialized = True

    def __new__(cls) -> "ToastManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get(cls) -> "ToastManager":
        """Get the singleton instance."""
        return cls()

    def _start_timer(self) -> None:
        """Start the redraw timer if not already running."""
        if ToastManager._timer_running:
            return
        ToastManager._timer_running = True
        bpy.app.timers.register(self._timer_callback, first_interval=0.05)
        logger.debug("Toast timer started")

    def _timer_callback(self) -> float | None:
        """Timer callback that triggers viewport redraws."""
        # Cleanup expired toasts
        self.cleanup()

        # If no more toasts, stop the timer
        if not self._toasts:
            ToastManager._timer_running = False
            logger.debug("Toast timer stopped - no more toasts")
            return None  # Stop the timer

        # Trigger viewport redraw
        self._request_redraw()

        # Continue timer at 20fps for smooth fade
        return 0.05

    def add(
        self,
        message: str,
        level: ToastLevel = ToastLevel.INFO,
        duration: float = 3.0,
    ) -> Toast:
        """
        Add a new toast notification.

        Args:
            message: The message to display.
            level: The severity level of the toast.
            duration: How long the toast should be visible (seconds).

        Returns:
            The created Toast object.
        """
        toast = Toast(message=message, level=level, duration=duration)
        self._toasts.append(toast)
        logger.debug(f"Toast added: [{level.value}] {message}")

        # Start the timer to handle fade and cleanup
        self._start_timer()

        # Trigger immediate viewport redraw
        self._request_redraw()

        return toast

    def info(self, message: str, duration: float = 3.0) -> Toast:
        """Add an info-level toast."""
        return self.add(message, ToastLevel.INFO, duration)

    def success(self, message: str, duration: float = 3.0) -> Toast:
        """Add a success-level toast."""
        return self.add(message, ToastLevel.SUCCESS, duration)

    def warning(self, message: str, duration: float = 3.0) -> Toast:
        """Add a warning-level toast."""
        return self.add(message, ToastLevel.WARNING, duration)

    def error(self, message: str, duration: float = 3.0) -> Toast:
        """Add an error-level toast."""
        return self.add(message, ToastLevel.ERROR, duration)

    def cleanup(self) -> None:
        """Remove expired toasts."""
        before_count = len(self._toasts)
        self._toasts = [t for t in self._toasts if not t.is_expired]
        if len(self._toasts) != before_count:
            self._request_redraw()

    def clear(self) -> None:
        """Clear all toasts."""
        self._toasts.clear()

    def get_visible_toasts(self) -> list[Toast]:
        """Get the list of currently visible (non-expired) toasts."""
        self.cleanup()
        return self._toasts[-self._max_visible :]

    def has_toasts(self) -> bool:
        """Check if there are any active toasts."""
        self.cleanup()
        return len(self._toasts) > 0

    def _request_redraw(self) -> None:
        """Request a viewport redraw to show updated toasts."""
        for area in bpy.context.screen.areas if bpy.context.screen else []:
            if area.type == "VIEW_3D":
                area.tag_redraw()


# Module-level convenience functions
_toast_manager: ToastManager | None = None


def get_toast_manager() -> ToastManager:
    """Get the global toast manager instance."""
    global _toast_manager
    if _toast_manager is None:
        _toast_manager = ToastManager.get()
    return _toast_manager


def toast_info(message: str, duration: float = 3.0) -> Toast:
    """Add an info toast."""
    return get_toast_manager().info(message, duration)


def toast_success(message: str, duration: float = 3.0) -> Toast:
    """Add a success toast."""
    return get_toast_manager().success(message, duration)


def toast_warning(message: str, duration: float = 3.0) -> Toast:
    """Add a warning toast."""
    return get_toast_manager().warning(message, duration)


def toast_error(message: str, duration: float = 3.0) -> Toast:
    """Add an error toast."""
    return get_toast_manager().error(message, duration)


def clear_toasts() -> None:
    """Clear all toasts."""
    get_toast_manager().clear()
