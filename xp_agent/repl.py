"""Human-facing REPL using the same session controller exercised by evals."""
import json
import os
from pathlib import Path
import uuid
from .backend import create_backend
from . import tracing
from .policy import PolicyError
from .project import render_plan, write_json
from .process import run
from .sandbox import DockerRunner
from .session import prepare, start, run_session, load_session


def shell(project=None, *, backend=None, image=None, provider=None, model=None, auth=None,
          budget=600, attempts=2, trace=None, output_root=None, runner_factory=DockerRunner, read=input, write=print):
    project = Path(project or Path.cwd()).resolve()
    output_root = Path(output_root or Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state')) / 'xp-coding-agent/sessions').resolve()
    config_path = output_root.parent / 'settings.json'
    settings = json.loads(config_path.read_text()) if config_path.exists() else {}
    trace_enabled=trace if trace is not None else settings.get('trace',False) is True
    chosen_provider = provider or settings.get('provider','codex')
    same_provider = chosen_provider == settings.get('provider')
    partner = backend or create_backend(chosen_provider,
                                        model or (settings.get('model') if same_provider else None),
                                        auth or (settings.get('auth','cli') if same_provider else 'cli'),
                                        status=lambda seconds: write(f'Worker active for {seconds:.0f}s'))
    hints, last, pending_task = [], None, None
    write(f'XP Coding Agent — {project}\nProvider: {partner.provider}; model: {partner.model}; auth: {partner.auth}\nDescribe your task. /help lists commands. Ctrl-C cancels the current operation.')
    def save_preferences():
        write_json(config_path,{'provider':partner.provider,'model':partner.model,'auth':partner.auth,'trace':trace_enabled})
    def execute_session(path,p,worker,identity,previous=None,*,create=False):
        with tracing.operation('xp.execute',enabled=trace_enabled,directory=path,session_id=identity,
                               write=write,previous_trace_id=previous,provider=p['provider'],model=p['model'],auth=p['auth'],mode='single') as active:
            if create: start(p,path,trace_session_id=identity)
            record=run_session(path,worker,runner_factory(p['image'],scratch=path/'scratch'),progress=write)
            tracing.annotate(status=record['status'])
        if active:
            from .session import save_session
            record=load_session(path)
            record['previous_trace_id']=active.trace_id
            save_session(path,record)
    def test_image():
        if image: return image
        result = run(['docker','image','inspect','xp-agent-tests:0.1','--format','{{.Id}}'], timeout=10)
        if result.returncode: raise PolicyError('Start Docker and build Dockerfile.tests first')
        return result.stdout.strip()
    while True:
        try:
            text = read('xp> ').strip()
            if not text: continue
            if text in {'/quit','/exit'}: return 0
            if text == '/new':
                pending_task, hints = None, []
                write('Ready for a new goal.'); continue
            if text.startswith('/trace'):
                if text not in {'/trace on','/trace off'}: raise PolicyError('Use /trace on or /trace off')
                trace_enabled=text=='/trace on'
                save_preferences()
                write('Local metadata tracing '+('on' if trace_enabled else 'off')+'.'); continue
            if text == '/help':
                write('Enter a task in plain language. Commands: /hint PATH, /provider codex|claude MODEL AUTH, /trace on|off, /status, /resume [SESSION_PATH], /new, /quit. Approve a displayed plan with approve; other replies reject it. Multiple approved increments run automatically.')
                continue
            if text.startswith('/hint '):
                hints.append(text[6:].strip()); write('Starting point recorded; dependencies will be discovered.'); continue
            if text.startswith('/provider '):
                parts = text.split()[1:]
                partner = create_backend(parts[0], parts[1] if len(parts)>1 else None, parts[2] if len(parts)>2 else 'cli')
                save_preferences()
                write(f'New plans use {partner.provider}/{partner.model}/{partner.auth}; existing sessions keep their approved provider.'); continue
            if text == '/status':
                write(f'Latest session: {last or "none"}; provider: {partner.provider}/{partner.model}'); continue
            if text.startswith('/resume'):
                target = text.partition(' ')[2].strip()
                selected = Path(target).expanduser().resolve() if target else last
                if not selected: raise PolicyError('Select a session with /resume SESSION_PATH')
                record = load_session(selected)
                if Path(record['plan']['project']) != project: raise PolicyError('Session belongs to another project')
                p = record['plan']
                resumed_backend = backend or create_backend(p['provider'],p['model'],p['auth'])
                write(f'Resuming approved {p["provider"]}/{p["model"]} session with preserved attempt/time budgets.')
                last = selected
                execute_session(selected,p,resumed_backend,record.get('trace_session_id') or uuid.uuid4().hex,record.get('previous_trace_id'))
                continue
            if text.startswith('/'):
                raise PolicyError('Unknown command; use /help')
            task = text if pending_task is None else pending_task + '\nHuman clarification: ' + text
            pending_task = task
            identity=uuid.uuid4().hex
            with tracing.operation('xp.plan',enabled=trace_enabled,directory=output_root.parent/'traces',session_id=identity,write=write,provider=partner.provider,model=partner.model,auth=partner.auth,mode='single') as planning:
                plan = prepare(project,task,partner,image=test_image(),hints=hints,budget=budget,attempts=attempts,progress=write)
                write(render_plan(plan))
                write(f'Workspace: {plan["workspace_kind"]}. Runtime snapshot: {len(plan["files"])} files. Model context: {len(plan["context_paths"])} files. Excluded: {", ".join(plan["excluded_paths"]) or "none"}.')
                approval = read('Review the plan. Type approve to execute, or describe the correction/rejection: ').strip()
                tracing.annotate(status='ready' if approval.lower()=='approve' else 'rejected')
                if approval.lower() != 'approve':
                    if approval.lower() == 'reject': pending_task = None
                    else: pending_task = task + '\nRequested plan correction: ' + approval
                    write('Plan rejected; no workspace created and no tests executed. Enter a revised task.'); continue
            pending_task = None
            last = output_root / uuid.uuid4().hex[:12]
            execute_session(last,plan,partner,identity,planning.trace_id if planning else None,create=True)
        except EOFError:
            return 0
        except KeyboardInterrupt:
            write('Operation cancelled. Use /resume for the selected session; accepted work is preserved.')
        except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
            write(f'Blocked: {exc}')
