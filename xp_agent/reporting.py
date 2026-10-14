"""Human-readable session reports derived from controller records, without a model call."""
from pathlib import Path
from .policy import PolicyError, discover


def source_divergence(plan):
    """Compare only approved paths; never retain newly read source in the report."""
    root = Path(plan['project'])
    changed, unknown = [], []
    for path in sorted(set(plan['files']) | set(plan['missing_paths'])):
        try:
            current = discover(root, [path])[path]
        except PolicyError as exc:
            if isinstance(exc.__cause__, FileNotFoundError):
                if path in plan['files']:
                    changed.append(path)
            else:
                unknown.append(path)
        except OSError:
            unknown.append(path)
        else:
            if path not in plan['files'] or current != plan['files'][path]:
                changed.append(path)
    return {'changed': changed, 'unknown': unknown}


def render_report(plan, state, branch, divergence):
    lines = [f'# Run result: {state["status"]}', '', state['reason'], '',
             f'Branch: `{branch or "unavailable"}`', '',
             f'Approved plan ID: `{plan["approval_id"]}`', '',
             'Review [the original plan](plan.md), [patch](changes.patch), '
             '[accepted workspace](workspace/), and [recorded evidence](state.json).', '',
             '## Accepted work', '']
    for change in state.get('changes', []):
        paths = ', '.join(change['paths']) or 'no file changes'
        lines.append(f'- {change["phase"]} (attempt {change["attempt"]}): {paths}. '
                     f'Proposal rationale: {change["rationale"]}')
    if not state.get('changes'):
        lines.append('No accepted coding changes.')
    lines += ['', 'Rationales describe the model’s intent; review the patch for actual behavior.', '',
              '## Verification', '',
              '| Phase | Gate | Passed | Failed | Errors | Skipped |',
              '|---|---|---:|---:|---:|---:|']
    for entry in state['evidence']:
        gate = 'accepted' if entry.get('accepted') else 'rejected'
        counts = ' | '.join(str(len(entry[key])) for key in ('passed', 'failed', 'errors', 'skipped'))
        lines.append(f'| {entry["phase"]} | {gate} | {counts} |')
    if not state['evidence']:
        lines.append('| No test run completed | unverified | 0 | 0 | 0 | 0 |')
    lines += ['', 'An accepted red gate requires assertion failures; it does not mean the tests passed.',
              'Human product acceptance: pending. No independent task-specific acceptance oracle was run by this command.', '',
              'Acceptance criteria to review:', '']
    lines += ['- ' + criterion for criterion in plan['acceptance']]
    lines += ['', '## Deviations and observations', '',
              'No plan amendments or additional human-approved scope changes are supported in this version. '
              'Accepted edits remain within the original file/phase scope. Supporting tests and source '
              'refactoring are listed above; their semantic relevance still needs review.', '']
    for rejection in state.get('rejections', []):
        lines.append(f'- Rejected {rejection["phase"]} attempt {rejection["attempt"]}: {rejection["reason"]}')
    if not state.get('rejections'):
        lines.append('No rejected proposals recorded.')
    lines += ['', 'Test refactoring is restricted: accepted tests cannot be changed after red. '
              'The agent does not automatically discover or resolve general technical debt.', '',
              '## Original project divergence', '']
    if divergence['changed']:
        lines.append('Changed or removed approved files / newly present selected paths: ' + ', '.join(divergence['changed']))
    if divergence['unknown']:
        lines.append('Could not safely compare: ' + ', '.join(divergence['unknown']))
    if not any(divergence.values()):
        lines.append('No differences detected in the selected paths at completion.')
    lines += ['', 'This is a point-in-time comparison of approved paths only. Verification applies to the '
              'snapshot; changes in the original project do not invalidate that evidence. Review compatibility '
              'and run project checks before integrating the patch. The agent does not edit the original project.', '']
    return '\n'.join(lines)
