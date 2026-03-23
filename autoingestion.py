#!/usr/bin/env python3
"""
gitlab_catalog_scanner.py
─────────────────────────────────────────────────────────────────────────────
Phase 2 helper: scans every repo in a GitLab group and reports which ones
are missing a catalog-info.yaml.

Optionally generates a stub catalog-info.yaml and opens an MR automatically
(set CREATE_MRS=true env var).

Usage:
    pip install python-gitlab
    export GITLAB_TOKEN=your_pat
    export GITLAB_HOST=gitlab.com          # or your self-hosted host
    export GITLAB_GROUP=your-top-group
    export CREATE_MRS=false                # set true to auto-open MRs
    python gitlab_catalog_scanner.py
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
import base64
import json
from datetime import datetime

try:
    import gitlab
except ImportError:
    print("ERROR: run `pip install python-gitlab` first")
    sys.exit(1)

# ── Config from environment ────────────────────────────────────────────────
GITLAB_TOKEN = os.environ["GITLAB_TOKEN"]
GITLAB_HOST  = os.getenv("GITLAB_HOST", "gitlab.com")
GITLAB_GROUP = os.environ["GITLAB_GROUP"]   # e.g. "my-org" or "my-org/subgroup"
CREATE_MRS   = os.getenv("CREATE_MRS", "false").lower() == "true"
BRANCH_NAME  = "add-backstage-catalog-info"
TARGET_FILE  = "catalog-info.yaml"


def build_stub_yaml(project) -> str:
    """Generate a minimal catalog-info.yaml for a project."""
    name  = project.path.lower().replace("_", "-")
    group = project.namespace["path"]
    return f"""\
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: {name}
  title: "{project.name}"
  description: "TODO: add a description"
  annotations:
    {GITLAB_HOST}/project-slug: {group}/{project.path}
spec:
  type: service
  lifecycle: production
  owner: team-unknown   # TODO: set the correct owner
"""


def get_all_projects(gl, group_path: str):
    """Recursively fetch all projects under a group."""
    group = gl.groups.get(group_path)
    projects = list(group.projects.list(include_subgroups=True, all=True))
    # projects.list returns GroupProject objects; get full Project for file ops
    return [gl.projects.get(p.id) for p in projects]


def file_exists(project, filepath: str, branch: str = "main") -> bool:
    """Return True if filepath exists in the repo on the given branch."""
    # Try main, then master as fallback
    for b in [branch, "master", project.default_branch]:
        try:
            project.files.get(file_path=filepath, ref=b)
            return True
        except Exception:
            continue
    return False


def create_mr_with_stub(project, stub_yaml: str):
    """Commit a stub catalog-info.yaml to a new branch and open an MR."""
    default = project.default_branch or "main"

    # Create branch
    try:
        project.branches.create({"branch": BRANCH_NAME, "ref": default})
    except Exception:
        pass  # branch may already exist

    # Commit the file
    project.files.create({
        "file_path": TARGET_FILE,
        "branch": BRANCH_NAME,
        "content": stub_yaml,
        "commit_message": "chore: add Backstage catalog-info.yaml",
        "author_name": "Backstage Bot",
        "author_email": "backstage-bot@yourcompany.com",
    })

    # Open MR
    mr = project.mergerequests.create({
        "source_branch": BRANCH_NAME,
        "target_branch": default,
        "title": "chore: add Backstage catalog-info.yaml",
        "description": (
            "This MR adds a `catalog-info.yaml` so this service is "
            "discoverable in the internal Service Catalog (Backstage).\n\n"
            "**Action required**: update `owner` and `description` fields, "
            "then approve and merge."
        ),
        "labels": ["backstage", "platform-engineering"],
        "remove_source_branch": True,
    })
    return mr.web_url


def main():
    print(f"Connecting to {GITLAB_HOST}...")
    gl = gitlab.Gitlab(f"https://{GITLAB_HOST}", private_token=GITLAB_TOKEN)
    gl.auth()

    print(f"Scanning group: {GITLAB_GROUP}")
    projects = get_all_projects(gl, GITLAB_GROUP)
    print(f"Found {len(projects)} projects\n")

    missing = []
    with_catalog = []

    for p in projects:
        has_file = file_exists(p, TARGET_FILE)
        status = "✅" if has_file else "❌"
        print(f"  {status}  {p.path_with_namespace}")
        if has_file:
            with_catalog.append(p)
        else:
            missing.append(p)

    print(f"\n── Summary ─────────────────────────────────")
    print(f"  Has catalog-info.yaml : {len(with_catalog)}")
    print(f"  Missing               : {len(missing)}")
    print(f"────────────────────────────────────────────\n")

    if not missing:
        print("All repos are onboarded! 🎉")
        return

    # Save report
    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "group": GITLAB_GROUP,
        "total": len(projects),
        "onboarded": len(with_catalog),
        "missing": [p.path_with_namespace for p in missing],
    }
    with open("catalog_scan_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print("Report saved to catalog_scan_report.json")

    if CREATE_MRS:
        print("\nCreating MRs for missing repos...")
        for p in missing:
            try:
                stub = build_stub_yaml(p)
                mr_url = create_mr_with_stub(p, stub)
                print(f"  📬  MR opened: {mr_url}")
            except Exception as e:
                print(f"  ⚠️   Failed for {p.path_with_namespace}: {e}")
    else:
        print("\nTo auto-create MRs, set CREATE_MRS=true and re-run.")
        print("Missing repos:")
        for p in missing:
            print(f"  - {p.web_url}")


if __name__ == "__main__":
    main()
