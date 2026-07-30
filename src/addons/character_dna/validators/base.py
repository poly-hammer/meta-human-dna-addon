# standard library imports
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(Enum):
    """Severity level of a validation issue."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class ValidationIssue:
    """A single problem found while validating."""

    code: str
    severity: Severity
    message: str
    expected: Any = None
    actual: Any = None


@dataclass
class ValidationReport:
    """The collected result of a validation pass."""

    db_name: str
    issues: list[ValidationIssue] = field(default_factory=list)

    def add(
        self,
        code: str,
        severity: Severity,
        message: str,
        expected: Any = None,
        actual: Any = None,
    ) -> None:
        self.issues.append(
            ValidationIssue(code=code, severity=severity, message=message, expected=expected, actual=actual)
        )

    @property
    def errors(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity is Severity.WARNING]

    @property
    def is_valid(self) -> bool:
        """``True`` when there are no error-severity issues."""
        return not self.errors

    def summary(self, severity: Severity | None = Severity.ERROR) -> str:
        """Return the issue messages as newline separated text.

        Args:
            severity: Only include issues of this severity, or ``None`` for all.

        Returns:
            One message per line, in the order the issues were added.
        """
        issues = self.issues if severity is None else [issue for issue in self.issues if issue.severity is severity]
        return "\n".join(issue.message for issue in issues)
