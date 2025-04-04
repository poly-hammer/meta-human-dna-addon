import sys
from .constants import PLATFORM_NAMES


class UnsupportedPlatformError(Exception):
    def __init__(self, message=None):
        if not message:
            self.message = (
                f'The platform "{sys.platform}" is not supported. Please check our '
                'documentation to see what platform and versions of blender are '
                'supported.'
            )
        else:
            self.message = message

    def __str__(self):
        return "UnsupportedPlatformError: " + self.message


class UnsupportedPythonVersionError(Exception):
    def __init__(self, message=None):
        platform_name = PLATFORM_NAMES.get(sys.platform, sys.platform)
        if not message:
            self.message = (
                f'There is currently no support for python '
                f'{sys.version_info.major}.{sys.version_info.minor} on {platform_name}'
            )
        else:
            self.message = message

    def __str__(self):
        return "UnsupportedPythonVersionError: " + self.message
