# state_manager.py
"""
Single source of truth for all state management.
Simple, elegant, bulletproof.
"""
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum


class Phase(Enum):
    """Development phases"""
    PLANNING = "planning"
    BACKEND = "backend"
    FRONTEND = "frontend"
    DEPLOYMENT = "deployment"
    TESTING = "testing"
    REVIEW = "review"
    VALIDATION = "validation"


class StateManager:
    """
    Centralized state management.
    One place, one truth, no confusion.
    """

    def __init__(self, workspace_root: str):
        self.workspace = Path(workspace_root).resolve()
        self.state_dir = self.workspace / ".devloop"
        self.state_dir.mkdir(exist_ok=True)

        # Define all state files in one place
        self.phase_file = self.state_dir / "phases.json"
        self.issues_file = self.state_dir / "issues.json"
        self.config_file = self.state_dir / "config.json"

        # Initialize if needed
        self._initialize()

    def _initialize(self):
        """Initialize state files if they don't exist"""
        if not self.phase_file.exists():
            self.phase_file.write_text(json.dumps({
                "phases": {phase.value: {"status": "pending"} for phase in Phase}
            }, indent=2))

        if not self.issues_file.exists():
            self.issues_file.write_text(json.dumps({
                "issues": [],
                "next_id": 1
            }, indent=2))

    def _read_json(self, file_path: Path) -> Dict[str, Any]:
        """Read JSON file safely"""
        try:
            return json.loads(file_path.read_text())
        except:
            return {}

    def _write_json(self, file_path: Path, data: Dict[str, Any]):
        """Write JSON file safely"""
        file_path.write_text(json.dumps(data, indent=2))

    # Phase Management
    def set_phase_status(self, phase: str, status: str = "complete", details: Optional[Dict] = None) -> bool:
        """Set phase status - single source of truth"""
        data = self._read_json(self.phase_file)
        data["phases"][phase] = {
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "details": details or {}
        }
        self._write_json(self.phase_file, data)
        return True

    def get_phase_status(self, phase: str) -> Dict[str, Any]:
        """Get phase status"""
        data = self._read_json(self.phase_file)
        return data.get("phases", {}).get(phase, {"status": "pending"})

    def is_phase_complete(self, phase: str) -> bool:
        """Check if phase is complete"""
        return self.get_phase_status(phase).get("status") == "complete"

    # Issue Management
    def add_issue(self, phase: str, issue_type: str, description: str,
                  file_path: Optional[str] = None, fix_suggestion: Optional[str] = None) -> int:
        """Add an issue and return its ID"""
        data = self._read_json(self.issues_file)
        issue_id = data.get("next_id", 1)

        issue = {
            "id": issue_id,
            "phase": phase,
            "type": issue_type,
            "description": description,
            "file_path": file_path,
            "fix_suggestion": fix_suggestion,
            "timestamp": datetime.now().isoformat(),
            "resolved": False
        }

        data["issues"].append(issue)
        data["next_id"] = issue_id + 1
        self._write_json(self.issues_file, data)
        return issue_id

    def resolve_issue(self, issue_id: int) -> bool:
        """Mark issue as resolved"""
        data = self._read_json(self.issues_file)
        for issue in data.get("issues", []):
            if issue["id"] == issue_id:
                issue["resolved"] = True
                issue["resolved_at"] = datetime.now().isoformat()
                self._write_json(self.issues_file, data)
                return True
        return False

    def get_issues(self, phase: Optional[str] = None, unresolved_only: bool = True) -> List[Dict]:
        """Get issues with filters"""
        data = self._read_json(self.issues_file)
        issues = data.get("issues", [])

        if phase:
            issues = [i for i in issues if i["phase"] == phase]
        if unresolved_only:
            issues = [i for i in issues if not i.get("resolved", False)]

        return issues

    # Workflow Management
    def get_next_phase(self) -> Optional[str]:
        """Determine next phase to execute"""
        # First, check for unresolved issues
        unresolved = self.get_issues(unresolved_only=True)
        if unresolved:
            # Group by phase and return the earliest phase with issues
            phases_with_issues = set(issue["phase"] for issue in unresolved)
            for phase in Phase:
                if phase.value in phases_with_issues:
                    # Reset that phase so it runs again
                    self.set_phase_status(phase.value, "pending")
                    return phase.value

        # Then check phases in order
        for phase in Phase:
            if not self.is_phase_complete(phase.value):
                return phase.value

        return None

    def get_summary(self) -> Dict[str, Any]:
        """Get complete workflow summary"""
        phases_data = self._read_json(self.phase_file)
        issues_data = self._read_json(self.issues_file)

        all_issues = issues_data.get("issues", [])

        return {
            "phases": phases_data.get("phases", {}),
            "issues": {
                "total": len(all_issues),
                "unresolved": len([i for i in all_issues if not i.get("resolved", False)]),
                "by_phase": self._group_issues_by_phase(all_issues)
            },
            "workspace": str(self.workspace),
            "ready": self._is_project_ready()
        }

    def _group_issues_by_phase(self, issues: List[Dict]) -> Dict[str, List[Dict]]:
        """Group unresolved issues by phase"""
        grouped = {}
        for issue in issues:
            if not issue.get("resolved", False):
                phase = issue["phase"]
                if phase not in grouped:
                    grouped[phase] = []
                grouped[phase].append(issue)
        return grouped

    def _is_project_ready(self) -> bool:
        """Check if project is ready for deployment"""
        # All phases complete
        for phase in Phase:
            if not self.is_phase_complete(phase.value):
                return False

        # No unresolved issues
        if self.get_issues(unresolved_only=True):
            return False

        # Validation phase marked it as ready
        validation_status = self.get_phase_status(Phase.VALIDATION.value)
        return validation_status.get("details", {}).get("project_ready", False)

    def reset(self):
        """Complete reset - start fresh"""
        self.phase_file.unlink(missing_ok=True)
        self.issues_file.unlink(missing_ok=True)
        self._initialize()


# Global instance for easy access
_state_manager: Optional[StateManager] = None


def init_state_manager(workspace_root: str) -> StateManager:
    """Initialize the global state manager"""
    global _state_manager
    _state_manager = StateManager(workspace_root)
    return _state_manager


def get_state_manager() -> StateManager:
    """Get the global state manager"""
    if _state_manager is None:
        raise RuntimeError("State manager not initialized. Call init_state_manager() first.")
    return _state_manager