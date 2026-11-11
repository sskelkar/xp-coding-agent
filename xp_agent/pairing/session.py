"""Durable private pair sessions, serialized writers and snapshot delivery."""
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import sqlite3
import uuid
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from ..policy import discover, digest, PolicyError
from ..project import git, write_files, write_json
from ..session import inventory
from ..sandbox import DockerRunner
from .graph import build_graph
from .operations import Operations
from .partners import Partner


def capture(project):
    project=Path(project).resolve();names,is_git=inventory(project)
    if is_git:
        from ..session import require_safe_checkout
        require_safe_checkout(project)
        if git(project,'status','--porcelain','--untracked-files=no').strip():raise PolicyError('Commit tracked project work before starting')
    files={}
    for name in names:
        try:files.update(discover(project,[name]))
        except PolicyError:continue
    if sum(len(v.encode()) for v in files.values())>400_000:raise PolicyError('Snapshot exceeds 400 KB')
    return files


class Session:
    def __init__(self,path,partners=None,runner=None):
        self.path=Path(path).resolve()
        self.manifest=json.loads((self.path/'pair-manifest.json').read_text())
        if self.manifest.get('version')!=1:raise ValueError('Unsupported pair session version')
        self.partners=partners or {a:Partner(a,**self.manifest['provider']) for a in ('A','B')}
        self.runner=runner or DockerRunner(scratch=self.path/'scratch')
        self.config={'configurable':{'thread_id':self.manifest['id']},'recursion_limit':500}

    @classmethod
    def create(cls,path,project,goal,*,partners=None,runner=None,provider='codex',model=None,auth='cli',
               budget=900,attempts=2,max_cycles=12,demo_every=2):
        if not goal.strip():raise ValueError('A goal is required')
        root=Path(path).resolve()
        if root.exists():raise ValueError('Use a new session directory; existing work is never overwritten')
        from ..backend import create_backend
        selected=create_backend(provider,model,auth)
        files=capture(project)
        root.mkdir(parents=True,mode=0o700);workspace=root/'workspace';workspace.mkdir(mode=0o700)
        write_files(workspace,files)
        git(workspace,'init','--template=','-b','xp/pair-'+uuid.uuid4().hex[:10])
        if files:git(workspace,'add','--',*files)
        git(workspace,'commit','--allow-empty','-m','Baseline: pair session snapshot')
        write_json(root/'pair-manifest.json',dict(version=1,id=uuid.uuid4().hex,goal=goal,
                    provider=dict(provider=provider,model=selected.model,auth=auth),files=files,
                    base_revision=git(workspace,'rev-parse','HEAD').strip(),
                    limits=dict(budget=budget,attempts=attempts,max_cycles=max_cycles,demo_every=demo_every)))
        return cls(root,partners,runner)

    @contextmanager
    def graph(self):
        lock=(self.path/'writer.lock').open('a')
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            connection=sqlite3.connect(self.path/'checkpoints.sqlite',check_same_thread=False)
            try:
                (self.path/'checkpoints.sqlite').chmod(0o600)
                ops=Operations(self.partners,self.runner,self.path/'workspace',self.manifest['goal'],
                               self.manifest['files'],**self.manifest['limits'])
                yield build_graph(ops,SqliteSaver(connection))
            finally:connection.close()
        finally:lock.close()

    def advance(self,answer=None,*,expected_interrupt=None):
        with self.graph() as graph:
            snapshot=graph.get_state(self.config)
            if snapshot.values and not snapshot.next:return self._save(snapshot.values)
            if snapshot.next and not any(t.interrupts for t in snapshot.tasks):
                # Pending non-human work after an interrupted process: graph reconciles
                # workspace before accepted writes; external model calls may repeat.
                value=graph.invoke(None,self.config)
            elif snapshot.next:
                payloads=[i.value for t in snapshot.tasks for i in t.interrupts]
                if expected_interrupt is not None and expected_interrupt!=digest(payloads[0]):
                    raise ValueError('Stale business response; inspect the current interrupt before replying')
                if answer is None:return self._save(snapshot.values, [i.value for t in snapshot.tasks for i in t.interrupts])
                value=graph.invoke(Command(resume=answer),self.config)
            else:value=graph.invoke({},self.config)
            snapshot=graph.get_state(self.config)
            return self._save(snapshot.values,[i.value for t in snapshot.tasks for i in t.interrupts])

    def _save(self,state,interrupts=None):
        state=dict(state)
        write_json(self.path/'pair-state.json',state)
        evidence={'version':2,'status':'completed' if state['status']=='accepted' else 'waiting' if interrupts else 'blocked',
                  'events':state['records'],'snapshots':state['snapshots']}
        write_json(self.path/'pair-evidence.json',evidence)
        from ..pair_evals.contracts import grade_contract
        contract=grade_contract(evidence)
        write_json(self.path/'pair-contract-grade.json',contract)
        result={'status':state['status'],'phase':state['phase'],'cycle':state['cycle'],
                'remaining_seconds':state['remaining'],'agreement_revision':state['agreement'],
                'code_hash':digest(state['files']),'interrupts':interrupts or [],
                'workspace':str(self.path/'workspace'),'contract_grade':contract['status'],
                'interrupt_token':digest(interrupts[0]) if interrupts else None}
        if state['status']=='accepted':
            workspace=self.path/'workspace'
            names=list(state['files'])
            if names:git(workspace,'add','--',*names)
            # Verify before committing and preserve the baseline patch on repeated reads.
            ops=Operations(self.partners,self.runner,workspace,self.manifest['goal'],self.manifest['files'],**self.manifest['limits'])
            ops._sync(state['files'],state['files'])
            patch=git(workspace,'diff',self.manifest['base_revision'],'--no-ext-diff','--no-textconv','--binary')
            (self.path/'changes.patch').write_text(patch)
            if git(workspace,'diff','--cached','--stat').strip():git(workspace,'commit','-m','Implement agreed behavior through XP pairing')
            result['commit']=git(workspace,'rev-parse','HEAD').strip()
        write_json(self.path/'pair-result.json',result)
        (self.path/'result.md').write_text('# Pair result\n\n'+json.dumps(result,indent=2)+'\n\nBusiness acceptance does not replace normal integration review.\n')
        return result
