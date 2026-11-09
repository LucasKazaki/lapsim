"""Closed, bounded development replay checkpoints; no native admission or restore.

Every continuation is reconstructed by actual numerical replay, not by assigning
saved physics/event flags. Declared source/environment pins remain unobserved and
unauthenticated. This short-history profile is not a full-event continuation ABI.
"""
from hashlib import sha256
from . import fsg_event as ev
from .input_contracts import decode,digest,encode,exact,is_sha256,require

SCHEMA='lapsim.fsg-development-replay-checkpoint.v1'
FAMILY='lapsim.fsg-development-replay-worker.v1'
MAX_BYTES=4*1024*1024
MAX_SEGMENTS=16
MAX_TICKS=1000
IDENTITY_FIELDS={'source_manifest_sha256','environment_sha256','residual_rule_sha256','course_record_sha256'}
FLAGS={'qualification_or_execution_authority':False,'native_admission':False,'source_environment_authenticated':False}


def identity_for(course,*,source_manifest_sha256,environment_sha256,residual_rule_sha256):
    require(type(course) is ev.FsgNumericalCourse,'Exact verified development course required')
    value={'source_manifest_sha256':source_manifest_sha256,'environment_sha256':environment_sha256,
        'residual_rule_sha256':residual_rule_sha256,'course_record_sha256':sha256(course.raw).hexdigest()}
    validate_identity(value);return value


def validate_identity(identity):
    exact(identity,IDENTITY_FIELDS,'declared replay identity')
    require(all(is_sha256(v) for v in identity.values()),'Exact declared replay pins required; not authentication')


def snapshot(raw,*,clean=False):
    value=decode(raw,ev.MAX_RAW_BYTES,canonical=True)
    require(value.get('schema')==ev.SNAPSHOT_SCHEMA and value.get('family')==ev.FAMILY and
        value.get('qualification_or_execution_authority') is False and
        value.get('checkpoint_restore_or_continuation_authority') is False and value.get('awards') is None,
        'Distinct unqualified FSG snapshot required')
    require(type(value.get('tick')) is int and 0<=value['tick']<=MAX_TICKS and
        type(value.get('attempted_numerical_work')) is int and value['attempted_numerical_work']>=0 and
        value.get('state_sha256')==digest(value.get('state')) and
        value.get('context_sha256')==digest(value.get('context')),'Snapshot counts/context/state digest differ')
    if clean:
        require(value.get('status')=='running' and value.get('attempted_numerical_work_is_lower_bound') is False and
            value.get('cancellation_requested') is False and value.get('rejected_attempt') is None and
            value.get('quarantined_interval_sha256') is None and value.get('violation') is None and
            value.get('finish') is None,'Only clean running complete-accounting prefixes are eligible for replay')
    return value


def segment(record):
    require(type(record) is ev.FsgRawInterval,'Literal FSG endpoint record required')
    before,after=snapshot(record.before_raw,clean=True),snapshot(record.after_raw)
    value=decode(record.interval_raw,ev.MAX_RAW_BYTES,canonical=True)
    require(value.get('schema')==ev.INTERVAL_SCHEMA and value.get('family')==ev.FAMILY and
        value.get('qualification_or_execution_authority') is False and value.get('awards') is None and
        value.get('start_snapshot_sha256')==sha256(record.before_raw).hexdigest() and
        value.get('end_snapshot_sha256')==sha256(record.after_raw).hexdigest() and
        value.get('context_sha256')==before['context_sha256']==after['context_sha256'] and
        before['context']==after['context'] and value.get('start_tick')==before['tick'] and
        value.get('end_tick')==after['tick'] and value.get('status')==after['status'],
        'Interval must bind literal unchanged-context endpoints')
    ticks,cap=value.get('requested_ticks'),value.get('maximum_new_work')
    require(type(ticks) is int and 1<=ticks<=ev.MAX_ADVANCE_TICKS and
        type(cap) is int and 1<=cap<=ev.MAX_ADVANCE_WORK and
        type(value.get('attempted_work_delta')) is int and
        value['attempted_work_delta']==after['attempted_numerical_work']-before['attempted_numerical_work'] and
        0<=value['attempted_work_delta']<=cap,'Interval schedule/attempted-work accounting differs')
    return {'before_utf8':record.before_raw.decode(),'interval_utf8':record.interval_raw.decode(),
        'after_utf8':record.after_raw.decode(),'requested_ticks':ticks,'maximum_new_work':cap}


def record_from_segment(value):
    exact(value,{'before_utf8','interval_utf8','after_utf8','requested_ticks','maximum_new_work'},'replay segment')
    require(all(type(value[k]) is str for k in ('before_utf8','interval_utf8','after_utf8')),'Literal UTF8 endpoint strings required')
    require(type(value['requested_ticks']) is int and type(value['maximum_new_work']) is int,
        'Replay schedule counters must not be Boolean aliases')
    record=ev.FsgRawInterval(*(value[k].encode('utf-8') for k in ('before_utf8','interval_utf8','after_utf8')))
    require(segment(record)==value,'Replay segment differs from exact raw schedule')
    return record


def _wrap(body):
    raw=encode({'checkpoint':body,'checkpoint_sha256':digest(body)})
    require(len(raw)<=MAX_BYTES,'Replay checkpoint byte capacity exceeded')
    return raw


def origin_checkpoint(consumer,identity):
    require(type(consumer) is ev.FsgDevelopmentConsumer,'Exact development consumer required')
    validate_identity(identity);raw=consumer.snapshot();s=snapshot(raw,clean=True)
    require(s['tick']==s['attempted_numerical_work']==0 and
        s['context']['residual_regen_rule_input_pin']==identity['residual_rule_sha256'] and
        digest(s['context']['course'])==identity['course_record_sha256'],'Exact consistent replay origin required')
    return _wrap({'schema':SCHEMA,'family':FAMILY,'identity':identity,'origin_utf8':raw.decode(),
        'segments':[],'tip_snapshot_sha256':sha256(raw).hexdigest(),'segment_count':0,
        'logical_tick':0,'logical_attempted_work':0,'parent_checkpoint_raw_sha256':None,**FLAGS})


def validate_checkpoint(raw,*,expected_raw_sha256,expected_identity):
    validate_identity(expected_identity)
    require(type(raw) is bytes and sha256(raw).hexdigest()==expected_raw_sha256,'Exact pinned replay checkpoint bytes required')
    envelope=decode(raw,MAX_BYTES,canonical=True);exact(envelope,{'checkpoint','checkpoint_sha256'},'FSG replay envelope')
    b=envelope['checkpoint'];exact(b,{'schema','family','identity','origin_utf8','segments','tip_snapshot_sha256',
        'segment_count','logical_tick','logical_attempted_work','parent_checkpoint_raw_sha256',*FLAGS},'FSG replay checkpoint')
    require(b['schema']==SCHEMA and b['family']==FAMILY and b['identity']==expected_identity and
        envelope['checkpoint_sha256']==digest(b) and all(b[k] is v for k,v in FLAGS.items()) and
        type(b['segments']) is list and len(b['segments'])<=MAX_SEGMENTS and
        type(b['segment_count']) is int and b['segment_count']==len(b['segments']) and type(b['origin_utf8']) is str,
        'Replay profile/schema/identity/count differs; no legacy or authenticated substitution')
    last=b['origin_utf8'].encode();origin=snapshot(last,clean=True)
    require(origin['tick']==origin['attempted_numerical_work']==0 and
        origin['context']['residual_regen_rule_input_pin']==expected_identity['residual_rule_sha256'] and
        digest(origin['context']['course'])==expected_identity['course_record_sha256'],'Replay origin identity differs')
    for item in b['segments']:
        rec=record_from_segment(item);end=snapshot(rec.after_raw,clean=True)
        start=snapshot(rec.before_raw,clean=True)
        require(rec.before_raw==last and end['tick']-start['tick']==item['requested_ticks'],
            'Replay prefix must contain complete contiguous successful requested calls')
        last=rec.after_raw
    tip=snapshot(last,clean=True)
    require(type(b['logical_tick']) is int and b['logical_tick']==tip['tick'] and
        type(b['logical_attempted_work']) is int and b['logical_attempted_work']==tip['attempted_numerical_work'] and
        b['tip_snapshot_sha256']==sha256(last).hexdigest(),'Replay tip differs from complete history')
    if not b['segments']:require(b['parent_checkpoint_raw_sha256'] is None,'Origin cannot name a parent')
    else:
        parent=dict(b);parent['segments']=b['segments'][:-1];previous=record_from_segment(b['segments'][-1]).before_raw
        ps=snapshot(previous,clean=True);parent.update(segment_count=len(parent['segments']),logical_tick=ps['tick'],
            logical_attempted_work=ps['attempted_numerical_work'],tip_snapshot_sha256=sha256(previous).hexdigest())
        # Each prefix's parent pin is the canonical checkpoint for its own prefix.
        parent['parent_checkpoint_raw_sha256']=None
        for i in range(1,len(parent['segments'])+1):
            prefix=dict(parent);prefix['segments']=parent['segments'][:i-1]
            prior=b['origin_utf8'].encode() if i==1 else record_from_segment(parent['segments'][i-2]).after_raw
            pv=snapshot(prior,clean=True);prefix.update(segment_count=i-1,logical_tick=pv['tick'],logical_attempted_work=pv['attempted_numerical_work'],tip_snapshot_sha256=sha256(prior).hexdigest())
            parent['parent_checkpoint_raw_sha256']=sha256(_wrap(prefix)).hexdigest()
        require(b['parent_checkpoint_raw_sha256']==sha256(_wrap(parent)).hexdigest(),'Checkpoint parent-prefix lineage differs')
    return b


def extend_checkpoint(parent_raw,record,*,expected_parent_raw_sha256,expected_identity):
    b=validate_checkpoint(parent_raw,expected_raw_sha256=expected_parent_raw_sha256,expected_identity=expected_identity)
    require(len(b['segments'])<MAX_SEGMENTS,'No replay segment capacity remains')
    item=segment(record);end=snapshot(record.after_raw,clean=True)
    start=b['origin_utf8'].encode() if not b['segments'] else record_from_segment(b['segments'][-1]).after_raw
    require(record.before_raw==start and end['tick']-snapshot(start,clean=True)['tick']==item['requested_ticks'],
        'Extension must use exact parent endpoint and complete requested interval')
    child={**b,'segments':b['segments']+[item],'segment_count':len(b['segments'])+1,
        'tip_snapshot_sha256':sha256(record.after_raw).hexdigest(),'logical_tick':end['tick'],
        'logical_attempted_work':end['attempted_numerical_work'],'parent_checkpoint_raw_sha256':sha256(parent_raw).hexdigest()}
    result=_wrap(child);validate_checkpoint(result,expected_raw_sha256=sha256(result).hexdigest(),expected_identity=expected_identity)
    return result
