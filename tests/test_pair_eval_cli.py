import json
from xp_agent.pair_evals.__main__ import main
from test_pair_contracts import trace


def test_catalog_is_not_a_runtime_qualification(capsys):
    assert main(['catalog']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['runtime_ready'] is False
    assert len(report['scenarios']) == 5
    assert all(s['status'] == 'not_run' for s in report['scenarios'])


def test_offline_grade_reports_validity_without_claiming_runtime_verification(tmp_path, capsys):
    evidence = tmp_path/'evidence.json'
    evidence.write_text(json.dumps(trace()))
    assert main(['grade', str(evidence)]) == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result['passed']
    assert not result['runtime_verified']
    assert 'snapshots' not in result
    assert '# 1-red' not in output


def test_empty_grade_and_invalid_json_exit_nonzero(tmp_path, capsys):
    p = tmp_path/'bad.json'
    p.write_text('{}')
    assert main(['grade', str(p)]) == 2
    p.write_text('{broken')
    assert main(['grade', str(p)]) == 2
    assert 'blocked' in capsys.readouterr().out


def test_report_file_is_written_and_partial_evidence_is_not_a_pass(tmp_path, capsys):
    value = trace();value['events'] = value['events'][:2];value['status'] = 'blocked'
    p = tmp_path/'partial.json';p.write_text(json.dumps(value))
    output = tmp_path/'reports/result.json'
    assert main(['grade', str(p), '--output', str(output)]) == 2
    assert json.loads(output.read_text())['status'] == 'valid_partial'


def test_case_gate_refuses_missing_duplicate_unknown_or_false_results():
    from xp_agent.pair_evals.scenarios import suite_gate
    valid = [{'id': x, 'status': 'passed'} for x in ('a', 'b')]
    assert suite_gate(valid, required=('a','b'))
    for invalid in ([], valid[:1], valid + valid[:1], valid + [{'id':'unknown','status':'passed'}],
                    [valid[0], {'id':'b','status':'not_run'}],
                    [valid[0], {'id':'b','status':'failed'}]):
        assert not suite_gate(invalid, required=('a','b'))


def test_suite_gate_rejects_empty_requirements_and_malformed_case_ids():
    from xp_agent.pair_evals.scenarios import suite_gate
    assert not suite_gate([], required=())
    assert not suite_gate([{'id': [], 'status': 'passed'}], required=('a',))
