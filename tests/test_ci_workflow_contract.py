"""Regression checks for event-specific CI whitespace ranges."""

from pathlib import Path


def test_whitespace_gate_covers_pull_request_push_and_manual_ranges() -> None:
    """Keep each GitHub event on its intended complete and valid revision range."""
    workflow = (
        Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")
    whitespace_step = workflow.split(
        "      - name: Check revision whitespace\n", maxsplit=1
    )[1].split("\n  tests:\n", maxsplit=1)[0]

    assert "fetch-depth: 0" in workflow
    assert 'case "$EVENT_NAME" in' in whitespace_step
    assert "pull_request)" in whitespace_step
    assert 'PR_BASE_SHA: ${{ github.event.pull_request.base.sha || \'\' }}' in workflow
    assert 'PR_HEAD_SHA: ${{ github.event.pull_request.head.sha || \'\' }}' in workflow
    assert 'git diff --check "${PR_BASE_SHA}...${PR_HEAD_SHA}"' in whitespace_step
    assert 'PUSH_BEFORE: ${{ github.event.before || \'\' }}' in workflow
    assert '[[ -z "$PUSH_BEFORE" ]]' in whitespace_step
    assert 'git diff --check "${PUSH_BEFORE}..${CURRENT_SHA}"' in whitespace_step
    assert '[[ "$PUSH_BEFORE" =~ ^0+$ ]]' in whitespace_step
    assert 'git rev-list --reverse "$CURRENT_SHA"' in whitespace_step
    assert "workflow_dispatch)" in whitespace_step
    assert 'git diff --check "${CURRENT_SHA}^1" "$CURRENT_SHA"' in whitespace_step
    assert 'git diff-tree --check --root -r "$CURRENT_SHA"' in whitespace_step
    assert "git diff --check HEAD^1 HEAD" not in whitespace_step
