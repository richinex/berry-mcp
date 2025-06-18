# packages/mcp-server/src/mcp_server/tools/git_tools.py

import asyncio
import logging
import git # type: ignore
import git.exc
import pathlib
from typing import Dict, Optional, Any, List, Union

log = logging.getLogger(__name__)

# --- Import from file_tools for path validation ---
try:
    from .file_tools import ToolConfig, validate_path
    FILE_TOOLS_IMPORTED = True
except ImportError as e:
    log.critical(
        "CRITICAL IMPORT ERROR: Could not import 'ToolConfig' or 'validate_path' from file_tools. "
        "Git tools path validation WILL NOT WORK and tools may fail or be insecure.",
        exc_info=True
    )
    FILE_TOOLS_IMPORTED = False
    class ToolConfig: # Dummy class
        @staticmethod
        def get_workspace() -> Optional[pathlib.Path]:
            log.error("Using DUMMY ToolConfig (git_tools) - IMPORT FAILED")
            return None
    def validate_path(user_path: str, check_exists: bool = False) -> Optional[pathlib.Path]:
        log.error(f"Using DUMMY validate_path (git_tools) for '{user_path}' - IMPORT FAILED, NO SECURITY!")
        # For clone, the directory might not exist yet, so allow validation if check_exists is False
        if not check_exists and user_path: # Basic dummy validation for clone target
            try:
                return pathlib.Path(user_path) # Highly insecure, only for dummy
            except Exception:
                return None
        return None


# --- Helper to get Git Repo object ---
async def _get_repo(repo_path_str: str) -> Optional[git.Repo]:
    """
    Gets a GitPython Repo object for a given path, validating the path first.
    The path must be a directory within the configured workspace.
    """
    validated_repo_path = validate_path(repo_path_str, check_exists=True) # Repo must exist
    if not validated_repo_path:
        log.error(f"Git repo path '{repo_path_str}' is invalid or outside workspace.")
        return None
    if not validated_repo_path.is_dir():
        log.error(f"Git repo path '{validated_repo_path}' is not a directory.")
        return None

    try:
        repo = await asyncio.to_thread(git.Repo, str(validated_repo_path))
        return repo
    except git.exc.InvalidGitRepositoryError:
        log.warning(f"Path '{validated_repo_path}' is not a valid Git repository.")
        return None
    except git.exc.NoSuchPathError:
        log.warning(f"Path '{validated_repo_path}' does not exist for Git repository.")
        return None
    except Exception as e:
        log.error(f"Unexpected error accessing Git repository at '{validated_repo_path}': {e}", exc_info=True)
        return None

# --- Git Tool Implementations ---

async def git_clone_repository(
    repo_url: str,
    target_directory_relative: str
) -> Dict[str, Any]:
    """
    Clones a Git repository into a specified target directory within the workspace.

    Args:
        repo_url: The URL of the Git repository to clone (e.g., https://github.com/user/repo.git).
        target_directory_relative: The relative path within the workspace where the repo should be cloned.
                                   This directory should ideally not exist or be empty.

    Returns:
        A dictionary indicating success or failure, and the path to the cloned repo.
    """
    log.info(f"Attempting to clone '{repo_url}' into '{target_directory_relative}'")

    # Validate the target directory. It might not exist yet, so check_exists=False.
    # validate_path ensures it's within the workspace.
    validated_target_path = validate_path(target_directory_relative, check_exists=False)
    if not validated_target_path:
        # validate_path logs the reason
        return {"error": f"Invalid or disallowed target directory: '{target_directory_relative}'."}

    # Check if the target path already exists and is a non-empty directory with a .git inside
    if validated_target_path.exists():
        if validated_target_path.is_dir() and any(validated_target_path.iterdir()):
            if (validated_target_path / ".git").is_dir():
                log.warning(f"Target directory '{validated_target_path}' already exists and appears to be a git repo.")
                return {"status": "skipped", "message": "Target directory already exists and is a Git repository.", "path": str(validated_target_path)}
            log.warning(f"Target directory '{validated_target_path}' already exists and is not empty.")
            # return {"error": f"Target directory '{validated_target_path}' already exists and is not empty."}
            # Allow cloning into existing dir, git clone itself will handle it if not empty
        elif not validated_target_path.is_dir():
            return {"error": f"Target path '{validated_target_path}' exists but is not a directory."}


    try:
        log.debug(f"Executing git clone for '{repo_url}' to '{str(validated_target_path)}'")
        cloned_repo = await asyncio.to_thread(git.Repo.clone_from, repo_url, str(validated_target_path))
        log.info(f"Successfully cloned '{repo_url}' to '{cloned_repo.working_dir}'")
        return {
            "status": "success",
            "message": f"Repository cloned successfully to '{cloned_repo.working_dir}'.",
            "path": str(cloned_repo.working_dir)
        }
    except git.exc.GitCommandError as e:
        log.error(f"Git command error during clone: {e.stderr}", exc_info=True)
        return {"error": f"Git clone failed: {e.stderr}"}
    except Exception as e:
        log.error(f"Unexpected error during git clone: {e}", exc_info=True)
        return {"error": f"Unexpected error during clone: {e}"}


async def git_pull_latest(repo_path_relative: str, remote_name: str = "origin") -> Dict[str, Any]:
    """
    Pulls the latest changes from a specified remote for the current branch of a local repository.

    Args:
        repo_path_relative: Relative path to the local Git repository within the workspace.
        remote_name: The name of the remote to pull from (default: 'origin').

    Returns:
        A dictionary indicating success or failure, including any messages from Git.
    """
    log.info(f"Attempting to pull latest changes for repo '{repo_path_relative}' from remote '{remote_name}'")
    repo = await _get_repo(repo_path_relative)
    if not repo:
        return {"error": f"Could not access repository at '{repo_path_relative}'."}

    try:
        if repo.is_dirty():
            log.warning(f"Repository at '{repo.working_dir}' has uncommitted changes. Pull might fail or lead to conflicts.")
            # return {"error": "Repository has uncommitted changes. Please commit or stash them first."}

        current_branch = await asyncio.to_thread(lambda: repo.active_branch.name)
        log.debug(f"Current branch: {current_branch}. Pulling from {remote_name}/{current_branch}")

        remote = await asyncio.to_thread(lambda: repo.remote(name=remote_name))
        pull_info_list = await asyncio.to_thread(remote.pull) # Pulls current branch

        messages = []
        for info in pull_info_list:
            messages.append(f"Remote: {info.remote_name}, Ref: {info.ref.name}, Flags: {info.flags}, Note: {info.note or 'No specific note'}")
            if info.flags & git.remote.FetchInfo.ERROR:
                 log.error(f"Error flag set during pull: {info.note}")
                 # return {"error": f"Pull encountered an error: {info.note}", "details": messages}
            if info.flags & git.remote.FetchInfo.REJECTED:
                 log.warning(f"Pull rejected: {info.note}")
                 # return {"error": f"Pull was rejected: {info.note}", "details": messages}

        log.info(f"Successfully pulled latest changes for '{repo.working_dir}'.")
        return {"status": "success", "message": "Pull successful.", "details": messages}

    except git.exc.GitCommandError as e:
        log.error(f"Git command error during pull: {e.stderr}", exc_info=True)
        if "Merge conflict" in e.stderr or "merge conflict" in e.stderr.lower():
            return {"error": "Pull failed due to merge conflicts. Please resolve them manually.", "details": e.stderr}
        return {"error": f"Git pull failed: {e.stderr}"}
    except Exception as e:
        log.error(f"Unexpected error during git pull: {e}", exc_info=True)
        return {"error": f"Unexpected error during pull: {e}"}


async def git_create_branch(
    repo_path_relative: str,
    branch_name: str,
    base_branch: Optional[str] = None,
    checkout: bool = True
) -> Dict[str, Any]:
    """
    Creates a new branch in a local repository, optionally checking it out.

    Args:
        repo_path_relative: Relative path to the local Git repository within the workspace.
        branch_name: The name for the new branch.
        base_branch: Optional name of an existing branch to base the new branch on.
                     If None, bases off the current HEAD.
        checkout: If True (default), checks out the new branch after creation.

    Returns:
        A dictionary indicating success or failure.
    """
    log.info(f"Attempting to create branch '{branch_name}' in repo '{repo_path_relative}'")
    repo = await _get_repo(repo_path_relative)
    if not repo:
        return {"error": f"Could not access repository at '{repo_path_relative}'."}

    try:
        # Check if branch already exists
        if branch_name in await asyncio.to_thread(lambda: [b.name for b in repo.branches]):
            log.warning(f"Branch '{branch_name}' already exists in '{repo.working_dir}'.")
            if checkout:
                await asyncio.to_thread(lambda: repo.git.checkout(branch_name))
                log.info(f"Checked out existing branch '{branch_name}'.")
                return {"status": "skipped", "message": f"Branch '{branch_name}' already exists. Checked out existing branch."}
            return {"status": "skipped", "message": f"Branch '{branch_name}' already exists."}

        if base_branch:
            if base_branch not in await asyncio.to_thread(lambda: [b.name for b in repo.branches] + [t.name for t in repo.tags] + ['HEAD']):
                return {"error": f"Base branch or ref '{base_branch}' not found."}
            new_branch = await asyncio.to_thread(repo.create_head, branch_name, base_branch)
            log.info(f"Created new branch '{branch_name}' from '{base_branch}'.")
        else:
            new_branch = await asyncio.to_thread(repo.create_head, branch_name)
            log.info(f"Created new branch '{branch_name}' from current HEAD.")

        if checkout:
            await asyncio.to_thread(new_branch.checkout)
            log.info(f"Checked out new branch '{branch_name}'.")
            current_active_branch = await asyncio.to_thread(lambda: repo.active_branch.name)
            if current_active_branch != branch_name:
                 log.error(f"Failed to checkout branch {branch_name} after creation. Current branch is {current_active_branch}")
                 return {"error": f"Branch {branch_name} created, but checkout failed. Current branch: {current_active_branch}"}

        return {"status": "success", "message": f"Branch '{branch_name}' created{' and checked out' if checkout else ''}."}
    except git.exc.GitCommandError as e:
        log.error(f"Git command error creating branch: {e.stderr}", exc_info=True)
        return {"error": f"Failed to create branch: {e.stderr}"}
    except Exception as e:
        log.error(f"Unexpected error creating branch: {e}", exc_info=True)
        return {"error": f"Unexpected error creating branch: {e}"}

async def git_checkout_branch(repo_path_relative: str, branch_name: str) -> Dict[str, Any]:
    """
    Checks out an existing branch in a local repository.

    Args:
        repo_path_relative: Relative path to the local Git repository within the workspace.
        branch_name: The name of the branch to checkout.

    Returns:
        A dictionary indicating success or failure.
    """
    log.info(f"Attempting to checkout branch '{branch_name}' in repo '{repo_path_relative}'")
    repo = await _get_repo(repo_path_relative)
    if not repo:
        return {"error": f"Could not access repository at '{repo_path_relative}'."}

    try:
        if repo.is_dirty(['--untracked-files=no']): # Check only tracked files for checkout conflicts
            log.warning(f"Repository '{repo.working_dir}' has uncommitted changes to tracked files. Checkout might fail or overwrite.")
            # return {"error": "Repository has uncommitted changes. Please commit or stash them first."}

        if branch_name not in await asyncio.to_thread(lambda: [b.name for b in repo.branches]):
            return {"error": f"Branch '{branch_name}' not found."}

        await asyncio.to_thread(repo.git.checkout, branch_name)
        current_active_branch = await asyncio.to_thread(lambda: repo.active_branch.name)
        if current_active_branch != branch_name:
            log.error(f"Failed to checkout branch {branch_name}. Current branch is {current_active_branch}")
            return {"error": f"Checkout command issued, but current branch is {current_active_branch}. Expected {branch_name}."}

        log.info(f"Successfully checked out branch '{branch_name}' in '{repo.working_dir}'.")
        return {"status": "success", "message": f"Checked out branch '{branch_name}'."}
    except git.exc.GitCommandError as e:
        log.error(f"Git command error during checkout: {e.stderr}", exc_info=True)
        if "did not match any file(s) known to git" in e.stderr:
             return {"error": f"Branch '{branch_name}' not found or invalid ref: {e.stderr}"}
        return {"error": f"Checkout failed: {e.stderr}"}
    except Exception as e:
        log.error(f"Unexpected error during checkout: {e}", exc_info=True)
        return {"error": f"Unexpected error during checkout: {e}"}


async def git_commit_changes(
    repo_path_relative: str,
    commit_message: str,
    add_all_tracked_modified: bool = True,
    specific_files_relative: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Commits changes in a local repository.

    Args:
        repo_path_relative: Relative path to the local Git repository within the workspace.
        commit_message: The commit message.
        add_all_tracked_modified: If True (default), stages all modified/deleted tracked files (`git add -u`).
                                  Untracked files are NOT added with this option.
        specific_files_relative: Optional list of file paths (relative to repo root) to stage specifically.
                                 If provided, `add_all_tracked_modified` is ignored for staging,
                                 but unstaging of other files does not occur.
                                 These paths are validated to be within the repo.

    Returns:
        A dictionary indicating success (with commit SHA) or failure.
    """
    log.info(f"Attempting to commit changes in repo '{repo_path_relative}' with message: '{commit_message[:50]}...'")
    repo = await _get_repo(repo_path_relative)
    if not repo:
        return {"error": f"Could not access repository at '{repo_path_relative}'."}

    try:
        # Staging
        staged_something = False
        repo_root_abs = pathlib.Path(repo.working_dir)

        if specific_files_relative:
            files_to_add_abs = []
            for rel_file_path_str in specific_files_relative:
                # Validate each file path string relative to the *workspace root*
                # This implies file_tools.validate_path needs to know the repo_root_abs
                # to construct the correct full relative path for validation.
                # For simplicity, assume paths are given relative to repo root for now.
                abs_file_path = repo_root_abs.joinpath(rel_file_path_str).resolve()
                # Basic check: is it within the repo?
                if not str(abs_file_path).startswith(str(repo_root_abs)):
                    return {"error": f"File path '{rel_file_path_str}' is outside the repository '{repo_path_relative}'."}
                # A more robust validation would use validate_path on the (workspace_root_relative_path_to_file)
                files_to_add_abs.append(str(abs_file_path))

            if files_to_add_abs:
                log.debug(f"Staging specific files: {files_to_add_abs}")
                await asyncio.to_thread(repo.index.add, items=files_to_add_abs)
                staged_something = True
        elif add_all_tracked_modified:
            log.debug("Staging all tracked modified/deleted files ('git add -u').")
            # 'git add -u' stages modified and deleted tracked files.
            # GitPython's repo.index.add('*') can be too broad.
            # We'll use repo.git.add(update=True)
            await asyncio.to_thread(repo.git.add, update=True)
            # Check if anything was actually staged by this command
            # diff an empty tree with the index; if there's a diff, then something is staged
            if await asyncio.to_thread(lambda: repo.index.diff("HEAD")): # Diff against current HEAD
                staged_something = True
            elif not await asyncio.to_thread(lambda: repo.head.is_valid()): # If no HEAD (initial commit)
                if await asyncio.to_thread(lambda: repo.index.diff(None)): # Diff against empty tree
                     staged_something = True


        # Check if there's anything to commit
        # This diffs the index (staging area) against the current commit (HEAD)
        diff_to_commit = await asyncio.to_thread(repo.index.diff, repo.head.commit if repo.head.is_valid() else None)
        if not diff_to_commit and not staged_something: # Double check if nothing was staged effectively
             # Could also check repo.is_dirty() again, but diff is more precise for what *will* be committed.
            log.info("No changes staged for commit.")
            return {"status": "skipped", "message": "No changes staged for commit."}

        commit = await asyncio.to_thread(repo.index.commit, commit_message)
        commit_sha = commit.hexsha
        log.info(f"Successfully committed changes. SHA: {commit_sha}")
        return {"status": "success", "message": "Commit successful.", "commit_sha": commit_sha}

    except git.exc.GitCommandError as e:
        log.error(f"Git command error during commit: {e.stderr}", exc_info=True)
        if "nothing to commit" in e.stderr.lower() or "no changes added to commit" in e.stderr.lower():
            return {"status": "skipped", "message": "No changes to commit or nothing staged."}
        return {"error": f"Commit failed: {e.stderr}"}
    except Exception as e:
        log.error(f"Unexpected error during commit: {e}", exc_info=True)
        return {"error": f"Unexpected error during commit: {e}"}


async def git_push_changes(
    repo_path_relative: str,
    remote_name: str = "origin",
    branch_name: Optional[str] = None, # If None, pushes current active branch
    force: bool = False,
    set_upstream: bool = False # If true, uses --set-upstream remote branch
) -> Dict[str, Any]:
    """
    Pushes committed changes from a local branch to a remote repository.

    Args:
        repo_path_relative: Relative path to the local Git repository within the workspace.
        remote_name: The name of the remote to push to (default: 'origin').
        branch_name: The specific local branch to push. If None, uses the current active branch.
        force: If True, performs a force push (`--force`). Use with extreme caution. (CRITICAL)
        set_upstream: If True, sets the upstream branch on the remote (`-u` or `--set-upstream`).

    Returns:
        A dictionary indicating success or failure, including messages from Git.
    """
    log.info(f"Attempting to push changes for repo '{repo_path_relative}' to '{remote_name}'")
    repo = await _get_repo(repo_path_relative)
    if not repo:
        return {"error": f"Could not access repository at '{repo_path_relative}'."}

    try:
        target_branch = branch_name if branch_name else await asyncio.to_thread(lambda: repo.active_branch.name)
        log.debug(f"Pushing branch '{target_branch}' to '{remote_name}'. Force: {force}, Set Upstream: {set_upstream}")

        remote = await asyncio.to_thread(lambda: repo.remote(name=remote_name))
        push_kwargs = {}
        if force:
            push_kwargs['force'] = True
        if set_upstream:
            push_kwargs['set_upstream'] = True

        push_info_list = await asyncio.to_thread(remote.push, refspec=target_branch, **push_kwargs)

        messages = []
        success = True
        for info in push_info_list:
            messages.append(f"Remote: {info.remote_name}, Ref: {info.local_ref.name if info.local_ref else 'N/A'} -> {info.remote_ref_string if info.remote_ref_string else 'N/A'}, Flags: {info.flags}, Summary: {info.summary}")
            if info.flags & git.remote.PushInfo.ERROR:
                log.error(f"Error flag set during push: {info.summary}")
                success = False
            if info.flags & git.remote.PushInfo.REJECTED:
                log.warning(f"Push rejected: {info.summary}")
                success = False # Rejection is a failure from user perspective for standard push

        if success:
            log.info(f"Successfully pushed branch '{target_branch}' to '{remote_name}'.")
            return {"status": "success", "message": f"Push successful for branch '{target_branch}'.", "details": messages}
        else:
            # Check for common "non-fast-forward" rejection
            for msg_detail in messages:
                if "rejected" in msg_detail.lower() and ("non-fast-forward" in msg_detail.lower() or "fetch first" in msg_detail.lower()):
                    return {"error": "Push rejected (non-fast-forward). Try pulling latest changes first or use force push.", "details": messages}
            return {"error": "Push operation encountered errors or rejections.", "details": messages}

    except git.exc.GitCommandError as e:
        log.error(f"Git command error during push: {e.stderr}", exc_info=True)
        if "src refspec" in e.stderr and "does not match any" in e.stderr:
             return {"error": f"Branch '{branch_name or 'current'}' not found locally or invalid refspec: {e.stderr}"}
        return {"error": f"Git push failed: {e.stderr}"}
    except Exception as e:
        log.error(f"Unexpected error during git push: {e}", exc_info=True)
        return {"error": f"Unexpected error during push: {e}"}


async def git_get_status(repo_path_relative: str) -> Dict[str, Any]:
    """
    Gets the status of a local Git repository (changed files, untracked files, current branch).

    Args:
        repo_path_relative: Relative path to the local Git repository within the workspace.

    Returns:
        A dictionary with status details or an error.
    """
    log.info(f"Getting Git status for repo '{repo_path_relative}'")
    repo = await _get_repo(repo_path_relative)
    if not repo:
        return {"error": f"Could not access repository at '{repo_path_relative}'."}

    try:
        changed_files = await asyncio.to_thread(lambda: [item.a_path for item in repo.index.diff(None)]) # Staged changes
        modified_files = await asyncio.to_thread(lambda: [item.a_path for item in repo.index.diff(repo.head.commit if repo.head.is_valid() else None)]) # Unstaged changes to tracked files

        # More direct way to get modified (unstaged), added (staged for add), deleted (staged for delete)
        # repo.git.status('--porcelain') gives a good summary
        status_output = await asyncio.to_thread(lambda: repo.git.status(porcelain=True))

        staged = [] # Files staged for commit (added, modified, deleted)
        unstaged_modified = [] # Files modified but not staged
        untracked_files = []

        for line in status_output.splitlines():
            if not line: continue
            parts = line.split()
            status_code = parts[0]
            filename = " ".join(parts[1:]) # Handle filenames with spaces

            if status_code.startswith('??'): # Untracked
                untracked_files.append(filename)
            else: # Tracked files
                # Index status (staged)
                if status_code[0] in ['A', 'M', 'D', 'R', 'C']:
                    staged.append(f"{status_code[0]}: {filename}")
                # Working tree status (unstaged)
                if len(status_code) > 1 and status_code[1] in ['M', 'D']:
                     unstaged_modified.append(f"{status_code[1]}: {filename}")


        current_branch = await asyncio.to_thread(lambda: repo.active_branch.name)
        is_dirty = await asyncio.to_thread(repo.is_dirty)

        return {
            "status": "success",
            "current_branch": current_branch,
            "is_dirty": is_dirty, # General dirty flag
            "staged_changes": staged, # Previously `changed_files`
            "unstaged_modified_tracked_files": unstaged_modified, # Previously `modified_files`
            "untracked_files": await asyncio.to_thread(lambda: repo.untracked_files)
        }
    except Exception as e:
        log.error(f"Unexpected error getting git status: {e}", exc_info=True)
        return {"error": f"Unexpected error getting status: {e}"}

async def git_get_commit_history(
    repo_path_relative: str,
    branch_or_ref: Optional[str] = None, # If None, uses current HEAD
    max_count: int = 10,
    since_date: Optional[str] = None # e.g., "2 weeks ago", "2023-01-01"
) -> Dict[str, Any]:
    """
    Retrieves the commit history for a specified branch or reference.

    Args:
        repo_path_relative: Relative path to the local Git repository.
        branch_or_ref: The branch name, tag, or commit SHA. Defaults to current HEAD.
        max_count: Maximum number of commits to retrieve.
        since_date: Retrieve commits more recent than this date/time string.

    Returns:
        A list of commit details (SHA, author, date, message) or an error.
    """
    log.info(f"Getting commit history for '{repo_path_relative}', ref='{branch_or_ref or 'HEAD'}', count={max_count}")
    repo = await _get_repo(repo_path_relative)
    if not repo:
        return {"error": f"Could not access repository at '{repo_path_relative}'."}

    try:
        kwargs = {'max_count': max_count}
        if since_date:
            kwargs['since'] = since_date

        target_ref = branch_or_ref
        if not target_ref: # Default to current HEAD
            target_ref = await asyncio.to_thread(lambda: repo.head.reference)

        commits_iter = await asyncio.to_thread(repo.iter_commits, rev=target_ref, **kwargs)

        history = []
        for commit in commits_iter:
            history.append({
                "sha": commit.hexsha,
                "author_name": commit.author.name,
                "author_email": commit.author.email,
                "date": commit.authored_datetime.isoformat(),
                "message": commit.message.strip(),
            })
        return {"status": "success", "commits": history}
    except git.exc.GitCommandError as e:
        log.error(f"Git command error getting commit history: {e.stderr}", exc_info=True)
        return {"error": f"Failed to get commit history: {e.stderr}"}
    except Exception as e:
        log.error(f"Unexpected error getting commit history: {e}", exc_info=True)
        return {"error": f"Unexpected error getting commit history: {e}"}