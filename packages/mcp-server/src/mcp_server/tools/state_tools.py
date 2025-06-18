# state_tools.py
"""
State management tools for development workflows.
Handles state directly without external dependencies.
"""

import os
import json
import logging
import asyncio
from typing import Dict, Optional, Any, List
from datetime import datetime
from pathlib import Path

from .file_tools import ToolConfig, validate_path

log = logging.getLogger(__name__)


class StateTools:
    """Direct state management for MCP tools"""

    @staticmethod
    def _get_state_dir() -> Optional[Path]:
        """Get the state directory"""
        workspace_root = ToolConfig.get_workspace()
        if workspace_root is None:
            return None

        state_dir = Path(workspace_root) / ".devloop"
        state_dir.mkdir(exist_ok=True, parents=True)
        return state_dir

    @staticmethod
    def _read_json(file_path: Path) -> Dict[str, Any]:
        """Read JSON file safely"""
        try:
            if file_path.exists():
                return json.loads(file_path.read_text())
        except Exception as e:
            log.error(f"Error reading {file_path}: {e}")
        return {}

    @staticmethod
    def _write_json(file_path: Path, data: Dict[str, Any]):
        """Write JSON file safely"""
        try:
            file_path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log.error(f"Error writing {file_path}: {e}")


async def write_phase_status(phase: str, status: str = "complete", details: Optional[Dict[str, Any]] = None) -> Dict[str, Optional[str]]:
    """
    Write the status of a development phase.

    Args:
        phase: The phase name (planning, backend, frontend, deployment, testing, review, validation)
        status: Status of the phase (complete, failed, needs_fixes)
        details: Optional dictionary with additional details

    Returns:
        Standard tool response dict
    """
    state_dir = StateTools._get_state_dir()
    if state_dir is None:
        return {"data": None, "error": "Workspace not configured"}

    # Update phases.json
    phases_file = state_dir / "phases.json"
    phases_data = StateTools._read_json(phases_file)

    if "phases" not in phases_data:
        phases_data["phases"] = {}

    phases_data["phases"][phase] = {
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "details": details or {}
    }

    StateTools._write_json(phases_file, phases_data)

    # Also write individual status file for backward compatibility
    status_file = Path(ToolConfig.get_workspace()) / f".status_{phase}.json"
    status_data = {
        "phase": phase,
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "details": details or {}
    }

    try:
        await asyncio.to_thread(status_file.write_text, json.dumps(status_data, indent=2))
        log.info(f"Phase {phase} status written: {status}")
        return {"data": f"Status for {phase} phase recorded as {status}", "error": None}
    except Exception as e:
        log.error(f"Failed to write phase status: {e}")
        return {"data": None, "error": f"Failed to write phase status: {e}"}


async def report_issue(phase: str, issue_type: str, description: str,
                      file_path: Optional[str] = None, fix_suggestion: Optional[str] = None) -> Dict[str, Optional[str]]:
    """
    Report an issue found during review.

    Args:
        phase: Which phase the issue is in (backend, frontend, deployment)
        issue_type: Type of issue (missing_feature, error, spec_violation, service_failure)
        description: Clear description of the issue
        file_path: Optional path to the file with the issue
        fix_suggestion: Optional suggestion for fixing

    Returns:
        Standard tool response dict
    """
    state_dir = StateTools._get_state_dir()
    if state_dir is None:
        return {"data": None, "error": "Workspace not configured"}

    # Validate phase
    valid_phases = ["backend", "frontend", "deployment", "testing", "planning"]
    if phase not in valid_phases:
        log.warning(f"Invalid phase '{phase}' specified. Use one of: {valid_phases}")
        # Auto-correct based on description
        description_lower = description.lower()
        if "backend" in description_lower or "api" in description_lower:
            phase = "backend"
        elif "frontend" in description_lower or "react" in description_lower:
            phase = "frontend"
        elif "docker" in description_lower or "service" in description_lower:
            phase = "deployment"
        else:
            phase = "deployment"
        log.info(f"Auto-corrected phase to: {phase}")

    # Update issues.json in state directory
    issues_file = state_dir / "issues.json"
    issues_data = StateTools._read_json(issues_file)

    if "issues" not in issues_data:
        issues_data["issues"] = []
        issues_data["next_id"] = 1

    issue_id = issues_data.get("next_id", 1)

    new_issue = {
        "id": issue_id,
        "phase": phase,
        "type": issue_type,
        "description": description,
        "file_path": file_path,
        "fix_suggestion": fix_suggestion,
        "timestamp": datetime.now().isoformat(),
        "resolved": False
    }

    issues_data["issues"].append(new_issue)
    issues_data["next_id"] = issue_id + 1

    StateTools._write_json(issues_file, issues_data)

    # Also write to root for backward compatibility
    root_issues_file = Path(ToolConfig.get_workspace()) / ".issues.json"
    try:
        await asyncio.to_thread(root_issues_file.write_text, json.dumps(issues_data, indent=2))
    except:
        pass

    log.info(f"Issue reported for {phase}: {description[:50]}...")
    return {"data": f"Issue #{issue_id} reported for {phase} phase", "error": None}


async def mark_issue_resolved(issue_id: int) -> Dict[str, Optional[str]]:
    """
    Mark an issue as resolved.

    Args:
        issue_id: The ID of the issue to mark as resolved

    Returns:
        Standard tool response dict
    """
    state_dir = StateTools._get_state_dir()
    if state_dir is None:
        return {"data": None, "error": "Workspace not configured"}

    issues_file = state_dir / "issues.json"
    issues_data = StateTools._read_json(issues_file)

    if "issues" not in issues_data:
        return {"data": None, "error": "No issues found"}

    issue_found = False
    for issue in issues_data["issues"]:
        if issue.get("id") == issue_id:
            issue["resolved"] = True
            issue["resolved_at"] = datetime.now().isoformat()
            issue_found = True
            break

    if not issue_found:
        return {"data": None, "error": f"Issue #{issue_id} not found"}

    StateTools._write_json(issues_file, issues_data)

    # Update root file too
    root_issues_file = Path(ToolConfig.get_workspace()) / ".issues.json"
    try:
        await asyncio.to_thread(root_issues_file.write_text, json.dumps(issues_data, indent=2))
    except:
        pass

    log.info(f"Issue #{issue_id} marked as resolved")
    return {"data": f"Issue #{issue_id} marked as resolved", "error": None}


async def get_current_issues(phase: Optional[str] = None, unresolved_only: bool = True) -> Dict[str, Any]:
    """
    Get current issues, optionally filtered by phase and resolution status.

    Args:
        phase: Optional phase to filter by
        unresolved_only: If True, only return unresolved issues

    Returns:
        Standard tool response dict with issues list
    """
    state_dir = StateTools._get_state_dir()
    if state_dir is None:
        return {"data": None, "error": "Workspace not configured"}

    issues_file = state_dir / "issues.json"
    issues_data = StateTools._read_json(issues_file)

    all_issues = issues_data.get("issues", [])

    # Filter issues
    filtered_issues = []
    for issue in all_issues:
        if unresolved_only and issue.get("resolved", False):
            continue
        if phase and issue.get("phase") != phase:
            continue
        filtered_issues.append(issue)

    result = {
        "total": len(filtered_issues),
        "phase_filter": phase,
        "unresolved_only": unresolved_only,
        "issues": filtered_issues
    }

    return {"data": result, "error": None}


async def clear_all_state() -> Dict[str, Optional[str]]:
    """
    Clear all state files. Useful for starting fresh.

    Returns:
        Standard tool response dict
    """
    workspace_root = ToolConfig.get_workspace()
    if workspace_root is None:
        return {"data": None, "error": "Workspace not configured"}

    try:
        cleared_files = []

        # Clear state directory
        state_dir = StateTools._get_state_dir()
        if state_dir and state_dir.exists():
            for file in state_dir.glob("*.json"):
                await asyncio.to_thread(file.unlink)
                cleared_files.append(str(file.name))

            # Reinitialize with empty state
            phases_data = {
                "phases": {
                    phase: {"status": "pending"}
                    for phase in ["planning", "backend", "frontend", "deployment", "testing", "review", "validation"]
                }
            }
            StateTools._write_json(state_dir / "phases.json", phases_data)

            issues_data = {"issues": [], "next_id": 1}
            StateTools._write_json(state_dir / "issues.json", issues_data)

        # Clear root status files for backward compatibility
        workspace_path = Path(workspace_root)
        for phase in ["planning", "backend", "frontend", "deployment", "testing", "review", "validation"]:
            status_file = workspace_path / f".status_{phase}.json"
            if status_file.exists():
                await asyncio.to_thread(status_file.unlink)
                cleared_files.append(status_file.name)

        # Clear root issues file
        issues_file = workspace_path / ".issues.json"
        if issues_file.exists():
            await asyncio.to_thread(issues_file.unlink)
            cleared_files.append(issues_file.name)

        log.info(f"Cleared {len(cleared_files)} state files")
        return {"data": f"Cleared {len(cleared_files)} state files", "error": None}

    except Exception as e:
        log.error(f"Failed to clear state: {e}")
        return {"data": None, "error": f"Failed to clear state: {e}"}


async def get_workflow_summary() -> Dict[str, Any]:
    """
    Get a summary of the current workflow state including all phases and issues.

    Returns:
        Standard tool response dict with workflow summary
    """
    state_dir = StateTools._get_state_dir()
    if state_dir is None:
        return {"data": None, "error": "Workspace not configured"}

    try:
        # Read phases
        phases_file = state_dir / "phases.json"
        phases_data = StateTools._read_json(phases_file)
        phases = phases_data.get("phases", {})

        # Ensure all phases exist
        for phase in ["planning", "backend", "frontend", "deployment", "testing", "review", "validation"]:
            if phase not in phases:
                phases[phase] = {"status": "pending"}

        # Read issues
        issues_file = state_dir / "issues.json"
        issues_data = StateTools._read_json(issues_file)
        all_issues = issues_data.get("issues", [])

        # Calculate summary
        summary = {
            "phases": phases,
            "issues": {
                "total": len(all_issues),
                "unresolved": sum(1 for i in all_issues if not i.get("resolved", False)),
                "by_phase": {}
            }
        }

        # Group unresolved issues by phase
        for issue in all_issues:
            if not issue.get("resolved", False):
                phase = issue.get("phase", "unknown")
                if phase not in summary["issues"]["by_phase"]:
                    summary["issues"]["by_phase"][phase] = []
                summary["issues"]["by_phase"][phase].append({
                    "id": issue.get("id"),
                    "type": issue.get("type"),
                    "description": issue.get("description"),
                    "file_path": issue.get("file_path"),
                    "fix_suggestion": issue.get("fix_suggestion")
                })

        return {"data": summary, "error": None}

    except Exception as e:
        log.error(f"Failed to get workflow summary: {e}")
        return {"data": None, "error": f"Failed to get workflow summary: {e}"}