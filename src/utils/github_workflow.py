from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)

GITHUB_API_BASE = "https://api.github.com"


async def _record_audit(
    db: Optional[Any],
    entity_type: str,
    entity_id: str,
    event_type: str,
    payload: Optional[dict] = None,
) -> None:
    """Helper to record an audit event when db session is available."""
    if db is None:
        return
    try:
        from src.models.audit import AuditEvent

        audit = AuditEvent(
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            payload_json=payload,
        )
        db.add(audit)
        await db.flush()
    except Exception as e:
        logger.warning(
            "audit_record_failed",
            entity_type=entity_type,
            entity_id=entity_id,
            error=str(e),
        )


class GitHubWorkflowService:
    """GitHub PR workflow service for rule set changes and model promotion."""

    def __init__(
        self,
        settings: Optional[Any] = None,
        db: Optional[Any] = None,
    ):
        self.settings = settings or get_settings()
        self.db = db
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> Optional[httpx.AsyncClient]:
        if not self.settings.github_token:
            logger.warning("github_token_missing", message="GITHUB_TOKEN not configured")
            return None
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=GITHUB_API_BASE,
                headers={
                    "Authorization": f"Bearer {self.settings.github_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=30.0,
            )
        return self._client

    async def create_rule_change_pr(
        self,
        rule_id: str,
        rule_name: str,
        old_config: dict,
        new_config: dict,
        author: str,
    ) -> Optional[str]:
        """
        Create a PR for a rule config change. Returns PR URL or None on failure.
        """
        client = self._get_client()
        if not client:
            return None

        repo = self.settings.github_repo
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        branch_name = f"rule-change/{rule_id}-{timestamp}"

        try:
            # Get default branch
            repo_resp = await client.get(f"/repos/{repo}")
            if repo_resp.status_code != 200:
                logger.warning("github_repo_fetch_failed", status=repo_resp.status_code)
                return None
            default_branch = repo_resp.json().get("default_branch", "main")

            # Get latest commit on default branch
            ref_resp = await client.get(
                f"/repos/{repo}/git/ref/heads/{default_branch}"
            )
            if ref_resp.status_code != 200:
                logger.warning("github_ref_fetch_failed", status=ref_resp.status_code)
                return None
            base_sha = ref_resp.json()["object"]["sha"]

            # Get tree sha from base commit
            base_commit_resp = await client.get(
                f"/repos/{repo}/git/commits/{base_sha}"
            )
            if base_commit_resp.status_code != 200:
                logger.warning(
                    "github_commit_fetch_failed",
                    status=base_commit_resp.status_code,
                )
                return None
            base_tree_sha = base_commit_resp.json()["tree"]["sha"]

            # Create branch
            await client.post(
                f"/repos/{repo}/git/refs",
                json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
            )

            # Create blob and tree for rule config file
            file_path = f"rules/{rule_id}.json"
            content = json.dumps(new_config, indent=2)
            blob_resp = await client.post(
                f"/repos/{repo}/git/blobs",
                json={"content": content, "encoding": "utf-8"},
            )
            if blob_resp.status_code != 201:
                logger.warning("github_blob_failed", status=blob_resp.status_code)
                return None

            blob_sha = blob_resp.json()["sha"]

            tree_resp = await client.post(
                f"/repos/{repo}/git/trees",
                json={
                    "base_tree": base_tree_sha,
                    "tree": [
                        {
                            "path": file_path,
                            "mode": "100644",
                            "type": "blob",
                            "sha": blob_sha,
                        }
                    ],
                },
            )
            if tree_resp.status_code != 201:
                logger.warning("github_tree_failed", status=tree_resp.status_code)
                return None

            tree_sha = tree_resp.json()["sha"]

            # Create commit
            commit_resp = await client.post(
                f"/repos/{repo}/git/commits",
                json={
                    "message": f"Rule change: {rule_name} ({rule_id})",
                    "tree": tree_sha,
                    "parents": [base_sha],
                    "author": {
                        "name": author,
                        "email": f"{author}@users.noreply.github.com",
                    },
                },
            )
            if commit_resp.status_code != 201:
                logger.warning("github_commit_failed", status=commit_resp.status_code)
                return None

            commit_sha = commit_resp.json()["sha"]

            # Update branch ref
            await client.patch(
                f"/repos/{repo}/git/refs/heads/{branch_name}",
                json={"sha": commit_sha},
            )

            # Open PR
            desc_lines = [
                f"## Rule change: {rule_name} (`{rule_id}`)",
                "",
                "### Changes",
                "```diff",
                f"- {json.dumps(old_config, indent=2)}",
                f"+ {json.dumps(new_config, indent=2)}",
                "```",
                "",
                f"**Author:** {author}",
            ]

            pr_resp = await client.post(
                f"/repos/{repo}/pulls",
                json={
                    "title": f"Rule change: {rule_name} ({rule_id})",
                    "head": branch_name,
                    "base": default_branch,
                    "body": "\n".join(desc_lines),
                },
            )
            if pr_resp.status_code != 201:
                logger.warning("github_pr_failed", status=pr_resp.status_code)
                return None

            pr_data = pr_resp.json()
            pr_url = pr_data.get("html_url")

            await _record_audit(
                self.db,
                entity_type="rule_change",
                entity_id=rule_id,
                event_type="pr_created",
                payload={
                    "pr_url": pr_url,
                    "rule_name": rule_name,
                    "author": author,
                },
            )

            return pr_url

        except httpx.HTTPError as e:
            logger.warning("github_rule_change_pr_failed", error=str(e))
            return None

    async def create_model_promotion_pr(
        self,
        model_version: str,
        metrics: dict,
        approved_by: str,
    ) -> Optional[str]:
        """
        Create a PR for model promotion with eval metrics. Requires explicit approval.
        """
        client = self._get_client()
        if not client:
            return None

        repo = self.settings.github_repo
        branch_name = f"model-promote/{model_version}"

        try:
            repo_resp = await client.get(f"/repos/{repo}")
            if repo_resp.status_code != 200:
                return None
            default_branch = repo_resp.json().get("default_branch", "main")

            ref_resp = await client.get(
                f"/repos/{repo}/git/ref/heads/{default_branch}"
            )
            if ref_resp.status_code != 200:
                return None
            base_sha = ref_resp.json()["object"]["sha"]

            base_commit_resp = await client.get(
                f"/repos/{repo}/git/commits/{base_sha}"
            )
            if base_commit_resp.status_code != 200:
                return None
            base_tree_sha = base_commit_resp.json()["tree"]["sha"]

            # Create branch
            await client.post(
                f"/repos/{repo}/git/refs",
                json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
            )

            file_path = f"models/{model_version}/promotion.json"
            content = json.dumps(
                {"model_version": model_version, "metrics": metrics, "approved_by": approved_by},
                indent=2,
            )
            blob_resp = await client.post(
                f"/repos/{repo}/git/blobs",
                json={"content": content, "encoding": "utf-8"},
            )
            if blob_resp.status_code != 201:
                return None

            tree_resp = await client.post(
                f"/repos/{repo}/git/trees",
                json={
                    "base_tree": base_tree_sha,
                    "tree": [
                        {
                            "path": file_path,
                            "mode": "100644",
                            "type": "blob",
                            "sha": blob_resp.json()["sha"],
                        }
                    ],
                },
            )
            if tree_resp.status_code != 201:
                return None

            model_commit_resp = await client.post(
                f"/repos/{repo}/git/commits",
                json={
                    "message": f"Model promotion: {model_version}",
                    "tree": tree_resp.json()["sha"],
                    "parents": [base_sha],
                    "author": {
                        "name": approved_by,
                        "email": f"{approved_by}@users.noreply.github.com",
                    },
                },
            )
            if model_commit_resp.status_code != 201:
                return None

            await client.patch(
                f"/repos/{repo}/git/refs/heads/{branch_name}",
                json={"sha": model_commit_resp.json()["sha"]},
            )

            metrics_body = "\n".join(
                f"- **{k}**: {v}" for k, v in metrics.items()
            )
            body = f"""## Model Promotion: {model_version}

### Eval Metrics
{metrics_body}

---
**Approved by:** {approved_by}
**Requires explicit review before merge.**
"""

            pr_resp = await client.post(
                f"/repos/{repo}/pulls",
                json={
                    "title": f"Model promotion: {model_version}",
                    "head": branch_name,
                    "base": default_branch,
                    "body": body,
                },
            )
            if pr_resp.status_code != 201:
                return None

            pr_url = pr_resp.json().get("html_url")

            await _record_audit(
                self.db,
                entity_type="model_promotion",
                entity_id=model_version,
                event_type="pr_created",
                payload={
                    "pr_url": pr_url,
                    "approved_by": approved_by,
                    "metrics": metrics,
                },
            )

            return pr_url

        except httpx.HTTPError as e:
            logger.warning("github_model_promotion_pr_failed", error=str(e))
            return None

    async def check_pr_approved(self, pr_number: int) -> bool:
        """Check if a PR has been approved."""
        client = self._get_client()
        if not client:
            return False

        repo = self.settings.github_repo
        try:
            rev_resp = await client.get(
                f"/repos/{repo}/pulls/{pr_number}/reviews"
            )
            if rev_resp.status_code != 200:
                return False

            reviews = rev_resp.json()
            approved = any(r.get("state") == "APPROVED" for r in reviews)
            return approved
        except httpx.HTTPError as e:
            logger.warning("github_check_pr_approved_failed", error=str(e))
            return False

    async def list_pending_prs(self) -> list[dict]:
        """List open PRs for the configured repo."""
        client = self._get_client()
        if not client:
            return []

        repo = self.settings.github_repo
        try:
            resp = await client.get(f"/repos/{repo}/pulls", params={"state": "open"})
            if resp.status_code != 200:
                return []

            prs = resp.json()
            return [
                {
                    "number": pr["number"],
                    "title": pr["title"],
                    "state": pr["state"],
                    "html_url": pr["html_url"],
                }
                for pr in prs
            ]
        except httpx.HTTPError as e:
            logger.warning("github_list_prs_failed", error=str(e))
            return []
