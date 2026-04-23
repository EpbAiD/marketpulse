#!/usr/bin/env python3
"""
Real-Time Logger for GitHub Actions
====================================
Writes progress logs to a file that gets committed during the run,
allowing real-time monitoring of workflow execution.
"""

import os
import sys
from datetime import datetime
from pathlib import Path


class RealTimeLogger:
    """Logger that writes to both console and a log file for real-time monitoring."""

    def __init__(self, log_file="WORKFLOW_LOG.md"):
        """
        Initialize the real-time logger.

        Args:
            log_file: Path to the log file (relative to project root)
        """
        self.log_file = Path(__file__).parent.parent / log_file
        self.start_time = datetime.now()

        # Initialize log file with header
        with open(self.log_file, 'w') as f:
            f.write(f"# Workflow Execution Log\n\n")
            f.write(f"**Started**: {self.start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n")
            f.write("---\n\n")

    def log(self, message, level="INFO"):
        """
        Log a message to both console and file.

        Args:
            message: The message to log
            level: Log level (INFO, SUCCESS, WARNING, ERROR, etc.)
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        elapsed = (datetime.now() - self.start_time).total_seconds() / 60

        # Format with emoji based on level
        icons = {
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "START": "🚀",
            "COMPLETE": "🎉",
            "STAGE": "📍"
        }
        icon = icons.get(level, "•")

        # Console output
        print(f"[{timestamp}] {icon} {message}")
        sys.stdout.flush()

        # File output
        with open(self.log_file, 'a') as f:
            f.write(f"**[{timestamp}]** ({elapsed:.1f}min) {icon} **{level}**: {message}\n\n")

    def stage(self, stage_name):
        """Log the start of a pipeline stage."""
        self.log(f"Starting stage: {stage_name}", "STAGE")

    def success(self, message):
        """Log a success message."""
        self.log(message, "SUCCESS")

    def warning(self, message):
        """Log a warning message."""
        self.log(message, "WARNING")

    def error(self, message):
        """Log an error message."""
        self.log(message, "ERROR")

    def info(self, message):
        """Log an info message."""
        self.log(message, "INFO")

    def complete(self):
        """Mark the workflow as complete."""
        elapsed = (datetime.now() - self.start_time).total_seconds() / 60
        self.log(f"Workflow completed in {elapsed:.1f} minutes", "COMPLETE")

    def commit_to_github(self):
        """Commit the log file to GitHub immediately for real-time visibility."""
        import subprocess
        try:
            # Configure git
            subprocess.run(["git", "config", "--local", "user.email", "github-actions[bot]@users.noreply.github.com"], check=False)
            subprocess.run(["git", "config", "--local", "user.name", "GitHub Actions Bot"], check=False)

            # Add and commit the log
            subprocess.run(["git", "add", str(self.log_file)], check=False)

            # Check if there are changes to commit
            result = subprocess.run(["git", "diff", "--staged", "--quiet"], capture_output=True)
            if result.returncode != 0:  # There are changes
                timestamp = datetime.now().strftime("%H:%M:%S")
                subprocess.run(["git", "commit", "-m", f"📝 Update workflow log [{timestamp}]", "--no-verify"], check=False)

                # Stash any unstaged changes (from concurrent pipeline stages
                # generating outputs, __pycache__, etc.) so pull --rebase
                # doesn't abort with "cannot pull with rebase".
                stash_res = subprocess.run(
                    ["git", "stash", "push", "-u", "-m", "auto-stash-before-log-push"],
                    capture_output=True, text=True,
                )
                stashed = "No local changes to save" not in (stash_res.stdout + stash_res.stderr)

                subprocess.run(["git", "pull", "--rebase", "origin", "main", "--no-verify"], check=False)
                subprocess.run(["git", "push", "origin", "main", "--no-verify"], check=False)

                if stashed:
                    subprocess.run(["git", "stash", "pop"], check=False)

                print(f"✓ Log committed to GitHub at {timestamp}")
        except Exception as e:
            print(f"⚠️ Could not commit log: {e}")


# Global logger instance
_logger = None

def get_logger(log_file="WORKFLOW_LOG.md"):
    """Get or create the global logger instance."""
    global _logger
    if _logger is None:
        _logger = RealTimeLogger(log_file)
    return _logger
