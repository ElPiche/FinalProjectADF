# utils.py - Utility functions for KB-MCP

import logging
import sys
from typing import Optional

class StructuredLogger:
    """Structured logger for KB-MCP operations."""

    def __init__(self, component: str = "KB-MCP"):
        self.component = component
        self.logger = logging.getLogger(component)
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def log(self, level: str, method: str, message: str, **kwargs):
        """Log a structured message."""
        log_level = getattr(logging, level.upper(), logging.INFO)
        extra = {
            'component': self.component,
            'method': method,
            **kwargs
        }
        self.logger.log(log_level, f"{method}: {message}", extra=extra)

# Global logger instance
structured_logger = StructuredLogger()

def log_message(level: str, component: str, method: str, message: str, **kwargs):
    """Convenience function for logging."""
    logger = StructuredLogger(component)
    logger.log(level, method, message, **kwargs)