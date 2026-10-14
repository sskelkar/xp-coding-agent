from xp_agent.reporting import render_report, source_divergence


def test_report_does_not_claim_rejected_candidate_was_delivered():
    plan = {'approval_id': 'approved', 'acceptance': ['Double inputs']}
    state = {'status': 'blocked', 'reason': 'Attempts exhausted', 'attempts': {'red': 2},
             'changes': [], 'rejections': [{'phase': 'red', 'attempt': 2, 'reason': 'Premature green'}],
             'evidence': [{'phase': 'red', 'accepted': False, 'passed': ['zero'], 'failed': [],
                           'errors': [], 'skipped': [], 'code_hash': 'abc'}]}
    report = render_report(plan, state, 'xp/test', {'changed': [], 'unknown': []})
    assert 'No accepted coding changes' in report
    assert 'Premature green' in report
    assert 'rejected' in report
    assert 'Human product acceptance: pending' in report
    assert 'No plan amendments' in report


def test_divergence_reports_changes_without_reading_unselected_files(tmp_path):
    (tmp_path / 'same.py').write_text('same')
    (tmp_path / 'changed.py').write_text('new')
    (tmp_path / 'added.py').write_text('added')
    (tmp_path / 'unselected.py').write_text('ignore')
    plan = {'project': str(tmp_path), 'files': {'same.py': 'same', 'changed.py': 'old', 'gone.py': 'old'},
            'missing_paths': ['added.py']}
    result = source_divergence(plan)
    assert result['changed'] == ['added.py', 'changed.py', 'gone.py']
    assert not result['unknown']


def test_divergence_cannot_report_symlink_as_unchanged(tmp_path):
    (tmp_path / 'real.py').write_text('same')
    (tmp_path / 'link.py').symlink_to(tmp_path / 'real.py')
    result = source_divergence({'project': str(tmp_path), 'files': {'link.py': 'same'}, 'missing_paths': []})
    assert result['unknown'] == ['link.py']
