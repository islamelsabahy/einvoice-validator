"""Offline sanity checker for Egyptian Tax Authority (ETA) e-invoice JSON, v1.0 layout."""
from .validator import Issue, validate_document, validate_file

__all__ = ["Issue", "validate_document", "validate_file"]
__version__ = "0.1.0"
