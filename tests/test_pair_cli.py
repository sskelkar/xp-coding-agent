from xp_agent.pairing.cli import main


def test_pair_cli_rejects_without_contacting_models_or_running_tests(tmp_path):
    class Partner:
        def __init__(self,identity):self.identity=identity
        def reply(self,*a):raise AssertionError('No model before confirmed outcome')
    output=[]
    code=main([str(tmp_path),'--goal','Money','--output',str(tmp_path/'run')],
              read=lambda _: 'reject',write=output.append,
              partners={a:Partner(a) for a in ('A','B')})
    assert code==2
    assert any('Desired outcome: Money' in x for x in output)


def test_pair_cli_help_and_resume_override_guard(tmp_path,capsys):
    import pytest
    with pytest.raises(SystemExit) as exc:main(['--help'])
    assert exc.value.code==0
    assert 'demo-every' in capsys.readouterr().out
    assert main(['--resume',str(tmp_path),'--model','other'],write=lambda _:None)==2


def test_stale_business_response_is_rejected_before_any_partner_call(tmp_path):
    import pytest
    from xp_agent.pairing.session import Session
    class Partner:
        def __init__(self,identity):self.identity=identity
        def reply(self,*a):raise AssertionError('No partner before final goal confirmation')
    project=tmp_path/'project';project.mkdir()
    session=Session.create(tmp_path/'run',project,'Money',partners={a:Partner(a) for a in ('A','B')})
    old=session.advance()
    current=session.advance('Keep originals unchanged',expected_interrupt=old['interrupt_token'])
    assert current['interrupt_token']!=old['interrupt_token']
    with pytest.raises(ValueError,match='Stale'):
        session.advance('confirm',expected_interrupt=old['interrupt_token'])


def test_pair_eval_flag_is_wired_and_legacy_experiment_combination_is_refused(tmp_path,monkeypatch):
    from xp_agent.cli import main as entry
    from xp_agent.pairing import evals
    seen={}
    def evaluate(output,**kwargs):seen.update(kwargs);return {'passed':True,'verification':{'llm_judge_used':False}}
    monkeypatch.setattr(evals,'evaluate',evaluate)
    assert entry(['eval','--pair','--trace','--output',str(tmp_path/'report.json')])==0
    assert seen['trace'] is True and seen['live'] is False
    seen.clear()
    assert entry(['eval','--pair','--experiment'])==2
    assert not seen
