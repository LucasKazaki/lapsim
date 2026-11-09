"""One-shot bounded RAW development replay worker. No OS/provider registration.

Fresh predicate provenance and complete source/environment observation remain
external requirements. Pins and successful replay prove consistency only. The
worker never returns a live consumer or an OwnedChunkResult/cleanup receipt.
"""
from dataclasses import dataclass
from hashlib import sha256
from threading import Event,Lock
from time import monotonic

from . import fsg_checkpoint as cp,fsg_event as ev
from .input_contracts import decode,encode,exact,is_sha256,require

SCHEMA='lapsim.fsg-development-replay-request.v1'
MAX_REQUEST=16384

@dataclass(frozen=True,slots=True)
class RawFsgWorkerResult:
    record: ev.FsgRawInterval
    child_checkpoint_raw: bytes | None
    replay_ticks: int
    new_ticks: int
    replay_work: int
    extension_work: int
    actual_worker_work: int
    outcome: str
    @property
    def qualification_or_execution_authority(self):return False

class ReplayWorkerDeadlineExceeded(RuntimeError):
    pass

class FsgReplayCancelled(RuntimeError):
    """A cooperative cancellation is raw cessation, never successful continuation."""
    pass

class FsgReplayRejected(RuntimeError):
    """A returned numerical rejection keeps precedence over pending cancellation."""
    def __init__(self,record):
        super().__init__('Returned FSG interval is invalid; raw numerical rejection retained')
        self.raw_record=record


def prepare_request(checkpoint_raw,*,expected_identity,expected_checkpoint_raw_sha256,
        requested_ticks,extension_work_cap,maximum_total_plant_work,maximum_wall_s):
    b=cp.validate_checkpoint(checkpoint_raw,expected_raw_sha256=expected_checkpoint_raw_sha256,
        expected_identity=expected_identity)
    raw=encode({'schema':SCHEMA,'family':cp.FAMILY,'identity':expected_identity,
        'checkpoint_raw_sha256':expected_checkpoint_raw_sha256,'origin_context_sha256':
            cp.snapshot(b['origin_utf8'].encode(),clean=True)['context_sha256'],
        'requested_ticks':requested_ticks,'extension_work_cap':extension_work_cap,
        'maximum_total_plant_work':maximum_total_plant_work,'maximum_wall_s':maximum_wall_s,
        'qualification_or_execution_authority':False,'native_admission':False})
    _request(raw,checkpoint_raw,sha256(raw).hexdigest())
    return raw


def _request(raw,checkpoint_raw,expected_sha256):
    require(type(raw) is bytes and is_sha256(expected_sha256) and sha256(raw).hexdigest()==expected_sha256,
        'Exact pinned raw development request required')
    r=decode(raw,MAX_REQUEST,canonical=True)
    exact(r,{'schema','family','identity','checkpoint_raw_sha256','origin_context_sha256','requested_ticks',
        'extension_work_cap','maximum_total_plant_work','maximum_wall_s','qualification_or_execution_authority','native_admission'},'FSG development request')
    require(r['schema']==SCHEMA and r['family']==cp.FAMILY and r['qualification_or_execution_authority'] is False and
        r['native_admission'] is False and type(r['requested_ticks']) is int and 1<=r['requested_ticks']<=ev.MAX_ADVANCE_TICKS and
        type(r['extension_work_cap']) is int and 1<=r['extension_work_cap']<=ev.MAX_ADVANCE_WORK and
        type(r['maximum_total_plant_work']) is int and 1<=r['maximum_total_plant_work']<=16*ev.MAX_ADVANCE_WORK and
        type(r['maximum_wall_s']) in (int,float) and 0<r['maximum_wall_s']<=40,'Finite development request caps/profile required')
    b=cp.validate_checkpoint(checkpoint_raw,expected_raw_sha256=r['checkpoint_raw_sha256'],expected_identity=r['identity'])
    require(b['segment_count']<cp.MAX_SEGMENTS and b['logical_tick']+r['requested_ticks']<=cp.MAX_TICKS and
        cp.snapshot(b['origin_utf8'].encode(),clean=True)['context_sha256']==r['origin_context_sha256'],
        'Origin context or remaining development profile capacity differs')
    require(r['extension_work_cap']<=r['maximum_total_plant_work'],'Extension cap exceeds aggregate worker cap')
    return r,b


class FsgReplayWorker:
    def __init__(self,request_raw,checkpoint_raw,*,expected_request_raw_sha256):
        _request(request_raw,checkpoint_raw,expected_request_raw_sha256)
        self._request_raw,self._checkpoint_raw=request_raw,checkpoint_raw
        self._pin=expected_request_raw_sha256;self._lock=Lock();self._started=self._finished=False
        self._phase='constructed';self._record=None;self._snapshot_raw=None;self._child=None;self._quarantined_child=None
        self._actual_work=self._replay_work=self._extension_work=0;self._work_complete=True;self._error=None
        self._capture_error=None;self._quarantined_interval_raw=None
        self._lifecycle_lock=Lock();self._cancel=Event();self._active_consumer=None

    def snapshot(self):
        require(self._lock.acquire(blocking=False),'Worker snapshot requires a returned/raised attempt')
        try:return {'phase':self._phase,'started':self._started,'finished':self._finished,
            'last_record':self._record,'last_snapshot_raw':self._snapshot_raw,'child_checkpoint_raw':self._child,
            'quarantined_child_checkpoint_raw':self._quarantined_child,'actual_worker_work':self._actual_work,
            'replay_work':self._replay_work,'extension_work':self._extension_work,
            'actual_work_is_lower_bound':not self._work_complete,'error':self._error,
            'capture_error':self._capture_error,'quarantined_interval_raw':self._quarantined_interval_raw,
            'cancellation_requested':self._cancel.is_set(),
            'qualification_or_execution_authority':False}
        finally:self._lock.release()

    def _publish_child(self,candidate):self._child=candidate

    def request_cancel(self):
        """Accept before terminal sealing; never wait for the execution lock.

        The current numerical tick may finish. This cannot interrupt a blocked
        dependency or replace original native containment/Stop/cleanup.
        """
        with self._lifecycle_lock:
            if self._finished:return False
            self._cancel.set()
            consumer=self._active_consumer
        if consumer is not None:consumer.request_cancel()
        return True

    def _check_cancel(self):
        if self._cancel.is_set():raise FsgReplayCancelled('Cooperative FSG replay cancellation requested')

    def _attach_consumer(self,consumer):
        with self._lifecycle_lock:
            self._active_consumer=consumer
            pending=self._cancel.is_set()
        if pending:consumer.request_cancel()
        self._check_cancel()

    def _seal_result(self,candidate,deadline):
        # Same short lock as request_cancel: accepted cancellation and successful
        # terminal publication have one ordering, with no check-to-return gap.
        with self._lifecycle_lock:
            if monotonic()>=deadline:
                self._quarantined_child=candidate;self._phase='quarantined_finalization'
                raise ReplayWorkerDeadlineExceeded('Worker deadline exhausted before result sealing')
            if self._cancel.is_set():
                self._quarantined_child=candidate
                raise FsgReplayCancelled('Cooperative FSG cancellation accepted before result sealing')
            self._publish_child(candidate)
            if monotonic()>=deadline:
                self._quarantined_child=candidate;self._phase='quarantined_finalization'
                raise ReplayWorkerDeadlineExceeded('Worker deadline exhausted during result sealing')
            self._phase='raw_result_ready';self._active_consumer=None;self._finished=True

    def execute(self,*,course,residual_regen_rule):
        require(self._lock.acquire(blocking=False),'Concurrent worker attempt refused')
        claimed=False;consumer=None;extension=False
        try:
            require(not self._started and not self._finished,'Worker attempt already consumed; no retry')
            claimed=True;self._started=True;self._phase='validating'
            # The already bounded immutable request supplies one absolute deadline.
            start=monotonic()
            initial=decode(self._request_raw,MAX_REQUEST,canonical=True)
            deadline=start+initial['maximum_wall_s']
            r,b=_request(self._request_raw,self._checkpoint_raw,self._pin)
            self._check_cancel()
            require(cp.identity_for(course,source_manifest_sha256=r['identity']['source_manifest_sha256'],
                environment_sha256=r['identity']['environment_sha256'],residual_rule_sha256=r['identity']['residual_rule_sha256'])==r['identity'],
                'Actual course differs from declared replay identity')
            origin=cp.snapshot(b['origin_utf8'].encode(),clean=True);context=origin['context']
            self._phase='initializing'
            require(monotonic()<deadline,'Worker deadline exhausted before initialization')
            self._check_cancel()
            consumer=ev.FsgDevelopmentConsumer(course,policy_id=context['policy']['id'],residual_regen_rule=residual_regen_rule,
                residual_regen_rule_sha256=r['identity']['residual_rule_sha256'],maximum_ticks=context['maximum_ticks'],maximum_work=context['maximum_work'])
            self._attach_consumer(consumer)
            self._snapshot_raw=consumer.snapshot()
            self._check_cancel()
            require(self._snapshot_raw==b['origin_utf8'].encode(),'Computed initial state/context differs from checkpoint origin')
            require(monotonic()<deadline,'Worker deadline exhausted during initialization')

            def call(ticks,cap):
                self._check_cancel()
                require(monotonic()<deadline,'Worker enclosing deadline exhausted before numerical work')
                require(cap<=r['maximum_total_plant_work']-self._actual_work,'Recorded call cap exceeds remaining aggregate worker work')
                self._work_complete=False  # An unreturned call cannot claim complete accounting.
                record=consumer.advance_with_snapshots(ticks=ticks,maximum_new_work=cap,
                    work_wall_s=min(10.,deadline-monotonic()))
                self._record=record  # Retain RAW bytes BEFORE comparisons/acceptance.
                self._snapshot_raw=record.after_raw
                end=cp.snapshot(record.after_raw)
                self._actual_work=end['attempted_numerical_work']
                self._work_complete=not end['attempted_numerical_work_is_lower_bound']
                if extension:self._extension_work=self._actual_work-self._replay_work
                else:self._replay_work=self._actual_work
                if end['status']=='invalid':raise FsgReplayRejected(record)
                require(self._actual_work<=r['maximum_total_plant_work'],'Aggregate replay/extension work exceeded')
                require(monotonic()<deadline,'Worker enclosing deadline exhausted after numerical work')
                self._check_cancel()  # RAW bytes/work are retained before cancellation is classified.
                return record

            for item in b['segments']:
                self._phase='replaying'
                actual=call(item['requested_ticks'],item['maximum_new_work'])
                expected=cp.record_from_segment(item)
                require(actual==expected,'Replay diverged; retain generated record, never extend or restore copied state')
            self._phase='extending';extension=True
            actual=call(r['requested_ticks'],r['extension_work_cap'])
            cp.segment(actual)
            end=cp.snapshot(actual.after_raw)
            candidate=None
            if end['status']=='running':
                candidate=cp.extend_checkpoint(self._checkpoint_raw,actual,
                    expected_parent_raw_sha256=r['checkpoint_raw_sha256'],expected_identity=r['identity'])
            result=RawFsgWorkerResult(actual,candidate,b['logical_tick'],end['tick']-b['logical_tick'],
                self._replay_work,self._extension_work,self._actual_work,'raw_running' if candidate is not None else 'raw_terminal')
            if monotonic()>=deadline:
                self._quarantined_child=candidate
                self._phase='quarantined_finalization'
                raise ReplayWorkerDeadlineExceeded('Final worker validation exceeded enclosing deadline; no eligible checkpoint returned')
            self._seal_result(candidate,deadline)
            return result
        except BaseException as exc:
            if claimed:
                if self._child is not None:self._quarantined_child=self._child;self._child=None
                if self._phase!='quarantined_finalization':
                    self._phase='cancelled' if isinstance(exc,FsgReplayCancelled) else 'failed'
                self._error=type(exc).__name__+': '+ev._error_text(exc)
                if isinstance(exc,ev.FsgDevelopmentDeadlineExceeded):
                    if exc.raw_record is not None:self._record=exc.raw_record
                    self._quarantined_interval_raw=exc.raw_interval
                if consumer is not None:
                    try:
                        self._snapshot_raw=consumer.snapshot()
                        state=cp.snapshot(self._snapshot_raw)
                        self._actual_work=state['attempted_numerical_work']
                        self._work_complete=not state['attempted_numerical_work_is_lower_bound']
                        if extension:self._extension_work=self._actual_work-self._replay_work
                        else:self._replay_work=self._actual_work
                    except BaseException as recovery:
                        self._capture_error=type(recovery).__name__
                        self._work_complete=False  # Preserve prior work as an explicit lower bound.
            raise
        finally:
            if claimed:
                with self._lifecycle_lock:
                    self._active_consumer=None;self._finished=True
            self._lock.release()
