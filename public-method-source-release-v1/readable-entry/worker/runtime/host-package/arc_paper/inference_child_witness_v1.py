# SPDX-License-Identifier: MIT-0
"""Actual configured-fleet child custody; source evidence, not isolation attestation."""
from __future__ import annotations
from contextvars import ContextVar
from dataclasses import asdict
from functools import wraps
import hashlib, inspect, json, math, os, sys, threading, types
from pathlib import Path
from .franzen_host_accounting_v2 import HostStopped

_CURRENT=ContextVar('inference_source_child',default=None)
_HOOKS=None
_SOURCE='ARC3-Inference/inference/agent/python_tool_sandbox.py'
_TOOL='ARC3-Inference/inference/agent/tool_agent.py'
MAXIMUM_ROWS=100000
MAXIMUM_ROW_BYTES=32768
MAXIMUM_TOTAL_BYTES=67108864
MODES={
 'B1':('reset_prefix_arm_loader_v1','franzen_fleet_admission_reset_prefix_v1','franzen_host_accounting_reset_prefix_v1','learned-child-witness-runtime-v1'),
 'A1':('reset_prefix_arm_loader_v1','franzen_fleet_admission_reset_prefix_v1','franzen_host_accounting_reset_prefix_v1','learned-child-witness-runtime-v1'),
 'P':('reset_prefix_arm_loader_v1','franzen_fleet_admission_reset_prefix_v1','franzen_host_accounting_reset_prefix_v1','learned-child-witness-runtime-v1'),
 'B0':('b0_runtime_loader_v1','franzen_b0_admission_reset_prefix_v2','franzen_b0_accounting_reset_prefix_v2','b0-child-witness-runtime-v1'),
}
class ChildReceiptError(ValueError):pass
def need(ok,code):
    if not ok:raise ChildReceiptError(code)
def _sha(raw):return hashlib.sha256(raw).hexdigest()
def _encoded(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def _method(raw,path,cls,name):
    code=compile(raw,str(path),'exec')
    if cls is not None:code=next(c for c in code.co_consts if isinstance(c,types.CodeType) and c.co_name==cls)
    return next(c for c in code.co_consts if isinstance(c,types.CodeType) and c.co_name==name)
def _ename(error):
    name=type(error).__name__ if error is not None else None
    return name if name in ('HostStopped','KeyboardInterrupt','SystemExit','OSError','ChildReceiptError','AccountingError','BoundsFailure','ValueError','RuntimeError') else ('other_exception' if error is not None else None)
def _now(hooks):
    value=hooks.clock();need(type(value) in (int,float) and math.isfinite(value) and value>=0,'child_clock_invalid')
    return round(value*1e9)
def _process_identity(pid, *, allow_zombie=False):
    """Host /proc only. Never accept identity from child protocol or logger."""
    need(type(pid) is int and pid>0,'child_pid_invalid')
    with Path('/proc/'+str(pid)+'/stat').open('rb') as stream:raw=stream.read(4097)
    end=raw.rfind(b')');fields=raw[end+2:].split()
    need(len(raw)<=4096 and end>0 and int(raw[:raw.index(b' ')])==pid
         and len(fields)>=20 and fields[0] != b'X' and (fields[0] != b'Z' or allow_zombie),'host_process_identity_unavailable')
    value=dict(pid=pid,parent_pid=int(fields[1]),start_time=int(fields[19]))
    need(value['parent_pid']>0 and value['start_time']>0,'host_process_identity_unavailable')
    return value
def _write_exclusive(path,raw):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        view=memoryview(raw)
        while view:
            count=os.write(fd,view);need(count>0,'child_short_write');view=view[count:]
        os.fsync(fd)
    finally:os.close(fd)
    fd=os.open(str(path.parent),os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

class Installation:
    def __init__(self,solver,loader):
        configuration=getattr(solver,'_arc_paper_common_configuration',None)
        need(type(configuration) is tuple and len(configuration)==5,'child_actual_configuration_required')
        config,root,hard_stop,models,fleet=configuration
        mode=config.arm
        need(type(mode) is str and mode in MODES,'child_explicit_mode_required')
        loader_name,admission_name,accounting_name,profile=MODES[mode]
        module=loader.checked_module('arc_paper.'+loader_name)
        admission=loader.checked_module('arc_paper.'+admission_name)
        accounting=loader.checked_module('arc_paper.'+accounting_name)
        need(type(loader) is module.RuntimeLoader and loader.prepared
             and loader.runtime['profile']==profile and loader.runtime['arm']==mode
             and type(config) is admission.CommonFleetConfig and fleet is accounting._FLEET
             and fleet.stop_event is solver._stop_event and callable(hard_stop), 'child_actual_owner_or_profile_changed')
        if mode=='B0':need(models is None,'b0_child_models_forbidden')
        config.validate();loader.verify()
        self.solver,self.loader,self.fleet,self.mode=solver,loader,fleet,mode
        self.admission_type=admission.FleetAdmission
        self.clock=fleet.common_clock(solver,config)
        self.source=loader.source
        self.manifest_sha=_sha((loader.trusted/'runtime-manifest.json').read_bytes())
        self.profile_sha=_sha((loader.trusted/'runtime-profiles'/f'{mode}.json').read_bytes())
        self.config_sha=_sha(_encoded(asdict(config)))
        self.source_pins={name:loader.final_source[name] for name in (_SOURCE,_TOOL)}
        self._lock=threading.RLock();self._child_count=0;self._child_rows=[];self._written=0
        root=Path(root)
        need(root.is_absolute() and root.resolve()==root and not root.is_symlink(),'private_child_journal_root_required')
        root.mkdir(parents=True,exist_ok=True,mode=0o700)
        need(root.is_dir(),'private_child_journal_root_required')
        self.path=root/'child-invocations.jsonl'
        self._fd=os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
        record=dict(schema_version=1,namespace='inference-source-child-installation-v1',arm=mode,
            configured_fleet=True,common_config=asdict(config),common_config_sha256=self.config_sha,
            runtime_manifest_sha256=self.manifest_sha,runtime_profile_sha256=self.profile_sha,
            source_sha256=self.source_pins,maximum_rows=MAXIMUM_ROWS,maximum_total_bytes=MAXIMUM_TOTAL_BYTES,
            isolation_certified=False,source_owned_not_external_native=True)
        try:_write_exclusive(root/'child-witness-installation.json',_encoded(record))
        except BaseException:os.close(self._fd);raise
        self.loader.verify()
    def _fail(self,reason):
        self.solver._stop_event.set()
        try:self.fleet.fail(reason)
        except BaseException:pass
    def _next_child_invocation(self):
        with self._lock:
            need(self._child_count<MAXIMUM_ROWS,'child_invocation_bound')
            self._child_count+=1;return self._child_count
    def _record_child(self,row):
        try:
            with self._lock:
                need(len(self._child_rows)<MAXIMUM_ROWS,'child_journal_row_bound')
                row=dict(row,child_journal_sequence=len(self._child_rows)+1)
                self._child_rows.append(row) # Known facts survive a failed sink.
                raw=_encoded(row)
                need(len(raw)<=MAXIMUM_ROW_BYTES and self._written+len(raw)<=MAXIMUM_TOTAL_BYTES,'child_journal_byte_bound')
                view=memoryview(raw)
                while view:
                    count=os.write(self._fd,view);need(count>0,'child_journal_short_write');view=view[count:]
                os.fsync(self._fd);self._written+=len(raw)
        except BaseException:self._fail('child_journal_failed');raise
    def verify(self):
        self.loader.verify()
        need(self.solver._arc_paper_common_configuration[4] is self.fleet,'child_fleet_replaced')
    def close_journal(self):
        with self._lock:
            if self._fd is not None:os.fsync(self._fd);os.close(self._fd);self._fd=None

def install_for_configured_fleet(solver,*,loader):
    global _HOOKS
    need(_HOOKS is None,'child_installation_not_fresh')
    hooks=Installation(solver,loader)
    _HOOKS=hooks
    return dict(installed=True,arm=hooks.mode,common_config_sha256=hooks.config_sha,
        runtime_profile_sha256=hooks.profile_sha,source_manifest_sha256=hooks.manifest_sha)
def _hooks():
    need(_HOOKS is not None,'child_observer_not_installed');return _HOOKS
def _join(hooks,agent,*,pre_spawn=False):
    hooks.verify()
    fleet=hooks.fleet;binding=fleet.binding_for_agent(agent);fleet.identity(binding)
    admission=getattr(hooks.solver,'_arc_paper_fleet_admission',None)
    need(type(admission) is hooks.admission_type and admission.solver is hooks.solver and admission.accounting is fleet
         and admission.config is hooks.solver._arc_paper_common_configuration[0]
         and admission.config.arm==hooks.mode,'child_coordinator_changed')
    sid,owner=admission._joined_owner(binding)
    need(fleet._tool_depth.get(id(agent))==1,'child_not_actual_python_tool')
    logical=fleet._logical[id(agent)];ledger=binding.ledger
    need(logical['sequence']>0 and not logical['pending'] and not ledger.totals.pending_request
         and ledger._action is None,'child_unsettled_request_or_action')
    with admission.gate._cv:
        active=admission.gate._owned(owner.lease)
        need(active.begun and owner.lease.session_id==sid
             and active.ticket.boundary.features_sha256==owner.feature_sha256
             and active.ticket.boundary.model_sha256==admission.allocation_sha256,'child_without_begun_lease')
        binding_sha=active.ticket.boundary.binding_sha256
    if pre_spawn and binding.session.should_stop():raise HostStopped('child_public_runtime_stop')
    return binding,sid,owner,logical['sequence'],binding_sha


class _Invocation:
    def __init__(self,hooks,agent,original):
        self.hooks,self.agent=hooks,agent
        path=hooks.loader.source/_TOOL
        need(original.__code__==_method(path.read_bytes(),path,'ToolAgent','_run_python_tool')
             and Path(original.__globals__['__file__']).resolve()==path.resolve(),'child_tool_source_changed')
        self.binding,self.sid,owner,self.logical,self.binding_sha=_join(hooks,agent)
        self.lease='lease-'+str(owner.lease.lease_id);self.thread=threading.current_thread()
        path=hooks.loader.source/_SOURCE
        self.source_code=_method(path.read_bytes(),path,None,'run_sandboxed_python')
        self.sequence=hooks._next_child_invocation();self.invocation_id=self.binding.session_id+'-tool-'+str(self.sequence)
        self.stage='tool';self.process=None;self.spawn_intent_recorded=False;self.terminal=False;self.last_ns=0
        self.child_identity=None;self.worker_identity=None
        self.retained=[];self._emit('tool_entered',logical_sequence=self.logical,lease_id=self.lease,
            accounting_sequence=len(self.binding.ledger.events),accepted_tokens=self.binding.ledger.totals.known_accepted_target_tokens,
            sdk_calls=self.binding.ledger.totals.post_start_sdk_calls_executed,thread_ident=threading.get_ident())
    def _emit(self,event,**facts):
        now=_now(self.hooks);need(now>=self.last_ns,'child_clock_regressed');self.last_ns=now
        row=dict(schema_version=1,namespace='inference-tool-child-receipt-v1',event=event,
            invocation_id=self.invocation_id,invocation_ordinal=self.sequence,run_id=self.binding.anchor.run_id,
            accounting_session_id=self.binding.session_id,planned_session_id=self.sid,binding_sha256=self.binding_sha,
            source_manifest_sha256=self.hooks.manifest_sha,common_config_sha256=self.hooks.config_sha,
            runtime_profile_sha256=self.hooks.profile_sha,arm=self.hooks.mode,monotonic_ns=now,**facts)
        self.retained.append(row)  # Known physical facts precede any durable sink.
        self.hooks._record_child(row)
    def _source(self):
        need(threading.current_thread() is self.thread and _CURRENT.get() is self
             and inspect.currentframe().f_back.f_back.f_code==self.source_code,'child_observer_foreign_source')
    def observe(self,event,**facts):
        self._source()
        try:
            if event=='sandbox_entered':
                need(self.stage=='tool' and set(facts)=={'timeout_seconds','profile_sha256','bootstrap_sha256'},'child_sandbox_entry_changed')
                self.stage='sandbox';self._emit(event,**facts)
            elif event=='spawn_intent':
                need(self.stage=='sandbox' and not facts,'child_spawn_intent_changed')
                actual=_join(self.hooks,self.agent,pre_spawn=True)
                need(actual[0] is self.binding and actual[1]==self.sid and actual[3]==self.logical and actual[4]==self.binding_sha,'child_scope_stale')
                self.stage='spawn';self.spawn_intent_recorded=True;self._emit(event)
            elif event=='spawn_returned':
                need(self.stage=='spawn' and set(facts)=={'process'},'child_spawn_return_changed')
                process=facts['process'];need(type(process.pid) is int and process.pid>0,'child_pid_invalid')
                self.process=process;self.stage='running'
                try:
                    self.worker_identity=_process_identity(os.getpid())
                    self.child_identity=_process_identity(process.pid)
                    need(self.child_identity['parent_pid']==self.worker_identity['pid'],'child_parent_identity_changed')
                except BaseException as error:
                    self._emit(event,pid=process.pid,host_identity_status='unavailable',child_identity=None,
                        worker_identity=self.worker_identity,exception_type=_ename(error),process_handle_observed=True)
                    self.hooks._fail('child_host_identity_unverified')
                    raise ChildReceiptError('child_host_identity_unverified') from error
                self._emit(event,pid=process.pid,host_identity_status='observed_alive',
                    child_identity=self.child_identity,worker_identity=self.worker_identity,
                    parent_worker_pid=os.getpid(),start_new_session=True,close_fds=True,stdio_pipes=True)
            elif event=='spawn_failed':
                need(self.stage=='spawn' and set(facts)=={'error'},'child_spawn_failure_changed')
                error=facts['error'];self.stage='failed'
                self._emit(event,exception_type=_ename(error),errno=error.errno if type(getattr(error,'errno',None)) is int else None,
                    process_handle_observed=False,process_created=None)
            elif event=='setup_observed':
                need(self.stage=='running' and set(facts)=={'gate_passed','status','setup'},'child_setup_changed')
                need(type(facts['gate_passed']) is bool and type(facts['status']) is str and len(facts['status'])<=80,'child_setup_type')
                if facts['gate_passed']:
                    try:
                        need(self.child_identity is not None and _process_identity(self.process.pid, allow_zombie=True)==self.child_identity
                             and _process_identity(os.getpid())==self.worker_identity,'child_ready_identity_changed')
                    except BaseException as error:
                        self._emit('setup_identity_unverified',pid=self.process.pid,exception_type=_ename(error))
                        raise ChildReceiptError('child_ready_identity_unverified') from error
                setup=facts['setup'];need(setup is None or type(setup) is dict,'child_setup_type')
                # Trusted source validator supplies this object; fixed nested keys
                # are selected below, never arbitrary child response fields.
                selected=None
                if setup is not None:
                    selected={k:setup.get(k) for k in ('resource_limits','policy_version','phase','library','libseccomp_version','native_arch_token',
                        'descriptor_setup','no_new_privs_verified_before_load')}
                    resources=setup.get('resource_limits') or {}
                    selected['resource_limits']={'verified':resources.get('verified'),'limits':{name:{k:entry.get(k) for k in ('requested_maximum','soft','hard')} for name,entry in (resources.get('limits') or {}).items()}}
                    selected['descriptor_setup']={k:(setup.get('descriptor_setup') or {}).get(k) for k in ('closed_fd_count','remaining_fd_above_2','stdio_verified_as_pipes','single_thread_verified')}
                self._emit(event,gate_passed=facts['gate_passed'],status=facts['status'],setup=selected,
                    host_identity_rechecked=bool(facts['gate_passed']),child_identity=self.child_identity,isolation_certified=False)
            elif event=='sandbox_finished':
                need(not self.terminal and set(facts)=={'cleanup','channel','error_type','gate_passed','status','resource_failure','elapsed_seconds','cleanup_error_type'},'child_finish_changed')
                cleanup=facts['cleanup'];channel=facts['channel']
                need(cleanup is None or (type(cleanup) is dict and set(cleanup).issubset({'reaped','pipes_closed','returncode','stdout_bytes','stderr_bytes'})),'child_cleanup_shape')
                self.terminal=True
                self._emit(event,spawn_intent_recorded=self.spawn_intent_recorded,process_handle_observed=self.process is not None,
                    pid=self.process.pid if self.process is not None else None,
                    child_identity=self.child_identity,worker_identity=self.worker_identity,
                    cleanup={k:cleanup.get(k) for k in ('reaped','pipes_closed','returncode','stdout_bytes','stderr_bytes')} if cleanup is not None else None,
                    channel_pre_cleanup=channel,error_type=facts['error_type'] if facts['error_type'] in ('HostStopped','KeyboardInterrupt','SystemExit','OSError','ChildReceiptError','AccountingError','BoundsFailure','ValueError','RuntimeError',None) else 'other_exception',
                    cleanup_error_type=facts['cleanup_error_type'] if facts['cleanup_error_type'] in ('OSError','KeyboardInterrupt','SystemExit','RuntimeError','ValueError',None) else 'other_exception',gate_passed=facts['gate_passed'],status=facts['status'],
                    resource_failure=facts['resource_failure'],elapsed_seconds=facts['elapsed_seconds'],isolation_certified=False)
                if facts['cleanup_error_type'] is not None or self.process is not None and (cleanup is None or cleanup.get('reaped') is not True or cleanup.get('pipes_closed') is not True or facts['gate_passed'] is not True):
                    self.hooks._fail('child_setup_or_cleanup_unverified')
                    raise ChildReceiptError('child_setup_or_cleanup_unverified')
            else:raise ChildReceiptError('child_unknown_source_event')
        except HostStopped:raise
        except BaseException:
            self.hooks._fail('child_receipt_failed');raise
    def finished(self,error,*,refused=False):
        need(threading.current_thread() is self.thread and _CURRENT.get() is self,'child_tool_context_changed')
        if self.stage=='tool':
            self._emit('tool_refused_before_sandbox',exception_type=_ename(error),spawn_intent_recorded=False,process_handle_observed=False)
        self._emit('tool_finished',sandbox_reached=self.stage!='tool',sandbox_terminal_observed=self.terminal,
            spawn_intent_recorded=self.spawn_intent_recorded,process_handle_observed=self.process is not None,
            refused_before_spawn=not self.spawn_intent_recorded,exception_type=_ename(error) if error is not None else None,
            accounting_sequence=len(self.binding.ledger.events),accepted_tokens=self.binding.ledger.totals.known_accepted_target_tokens,
            sdk_calls=self.binding.ledger.totals.post_start_sdk_calls_executed)

def current_child_observer(agent):
    value=_CURRENT.get();need(type(value) is _Invocation and value.agent is agent,'missing_private_child_context');return value

def child_recorded_python(original):
    @wraps(original)
    def wrapped(agent,*args,**kwargs):
        hooks=_hooks();scope=None;token=None;error=None
        try:
            need(_CURRENT.get() is None,'child_context_reentered')
            scope=_Invocation(hooks,agent,original);token=_CURRENT.set(scope)
            return original(agent,*args,**kwargs)
        except HostStopped as caught:
            error=caught;raise
        except BaseException as caught:
            error=caught;hooks._fail('child_tool_failed');raise
        finally:
            if scope is not None:
                try:scope.finished(error,refused=isinstance(error,HostStopped))
                except BaseException:
                    hooks._fail('child_terminal_receipt_failed')
                    if error is None:raise
                finally:_CURRENT.reset(token)
    return wrapped

def verify_child_observer(observer):
    need(type(observer) is _Invocation,'missing_source_child_observer')
    observer._source()
    return observer
