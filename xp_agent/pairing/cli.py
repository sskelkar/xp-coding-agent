"""Interactive outcome agreement, graph-controlled coding and business demos."""
import argparse
import json
import os
from pathlib import Path
import uuid
from .. import tracing
from .session import Session


def main(argv=None,*,read=input,write=print,partners=None,runner=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project',nargs='?',type=Path,default=Path.cwd())
    parser.add_argument('--goal')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--resume',type=Path)
    parser.add_argument('--provider',choices=('codex','claude'))
    parser.add_argument('--model')
    parser.add_argument('--auth',choices=('cli','api-key','oauth-token'))
    parser.add_argument('--budget',type=int,default=900)
    parser.add_argument('--attempts',type=int,default=2)
    parser.add_argument('--max-cycles',type=int,default=12)
    parser.add_argument('--demo-every',type=int,default=2)
    parser.add_argument('--trace',action=argparse.BooleanOptionalAction,default=False)
    args=parser.parse_args(argv)
    try:
        if args.resume:
            if args.provider or args.model or args.auth or args.goal or args.output:
                raise ValueError('Resume retains the agreed provider, goal and resource limits; do not override them')
            session=Session(args.resume,partners,runner)
        else:
            goal=args.goal or read('What outcome should the pair achieve? ').strip()
            base=Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'xp-coding-agent/pairs'
            session=Session.create(args.output or base/uuid.uuid4().hex[:12],args.project,goal,
                partners=partners,runner=runner,provider=args.provider or 'codex',model=args.model,auth=args.auth or 'cli',
                budget=args.budget,attempts=args.attempts,max_cycles=args.max_cycles,demo_every=args.demo_every)
        write('Pair session: '+str(session.path))
        write('Partners A and B; provider '+session.manifest['provider']['provider']+'; model '+session.manifest['provider']['model'])
        def advance(answer=None,expected_interrupt=None):
            with tracing.operation('xp.execute',enabled=args.trace,directory=session.path/'traces',
                session_id=session.manifest['id'],write=write,mode='pair',**session.manifest['provider']):
                result=session.advance(answer,expected_interrupt=expected_interrupt)
                tracing.annotate(status='verified' if result['status']=='accepted' else 'ready' if result['interrupts'] else 'blocked')
                return result
        result=advance()
        while result['interrupts']:
            event=result['interrupts'][0]
            if event['kind']=='confirm_goal':
                write('Desired outcome: '+event['goal'])
                answer=read('Type confirm, reject, or a clarification: ').strip()
            else:
                write(event.get('message','Business feedback required'))
                for example in event.get('examples',[]):
                    write(f"  {example['label']}: observed {example['actual']!r}; expected {example['expected']!r}")
                answer=read('Type accept (working demo only), continue, or a clarification: ').strip()
            result=advance(answer,result['interrupt_token'])
        write('Pair result: '+result['status']+'; workspace: '+result['workspace'])
        if result['status']!='accepted':
            state=json.loads((session.path/'pair-state.json').read_text());write('Reason: '+state.get('reason','Stopped before acceptance'))
        return 0 if result['status']=='accepted' else 2
    except (EOFError,KeyboardInterrupt):
        write('Paused. Reopen with --resume SESSION_PATH; saved work and budgets are retained.')
        return 130
    except (ValueError,RuntimeError,OSError,KeyError) as exc:
        write('Pair blocked: '+str(exc));return 2
