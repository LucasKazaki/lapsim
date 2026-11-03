"""Fixed accepted-producer reference binding; no solver/native calls on import."""
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite,hypot
from pathlib import Path
from lapsim.courses.spatial_track import SpatialTrack
import racing_geometry as g
import line_generator
import producer_receipts
HERE=Path(__file__).resolve().parent
class LineUnavailable(ValueError):pass

def verify_producer_receipts(audit,artifact_raw,*,promotion_raw=None,reviewed_promotion_sha256=None,evidence=None):
    """Check a bundle against a digest pinned by the reviewed consumer action.

    A local audit JSON's self-asserted booleans are not proof of execution.
    A separately reviewed producer must bind the exact supported-tool terminal,
    owned worker output and lease/cleanup receipts before this gate can open.
    """
    if promotion_raw is None or reviewed_promotion_sha256 is None or evidence is None:
        raise LineUnavailable('Externally reviewed promotion anchor and raw receipt bundle are not supplied')
    if (type(evidence) is not dict or evidence.get('line-artifact.json')!=artifact_raw or
            decode(evidence.get('independent-audit.json',b''))!=audit):
        raise LineUnavailable('Producer audit/artifact bundle differs')
    # This is a consistency check, not authentication of the tool event.
    # The consumer action's independently reviewed source identity must pin
    # reviewed_promotion_sha256; its reviewer must directly establish the real
    # supported-tool exit and all referenced cleanup before issuing that pin.
    result=producer_receipts.verify_bundle(promotion_raw,reviewed_promotion_sha256,evidence)
    if result.get('status')!='BUNDLE_CONSISTENCY_ONLY':
        raise LineUnavailable('Producer bundle consistency was not established')
    return result

def read(path,maximum):
    for p in (path,*path.parents):
        if p.exists():g.require(not p.is_symlink() and not getattr(p.stat(),'st_file_attributes',0)&1024,'No reference aliases')
    with path.open('rb') as stream:raw=stream.read(maximum+1)
    g.require(len(raw)<=maximum,'Reference input bound');return raw
def decode(raw):
    def pairs(items):
        out={}
        for k,v in items:g.require(k not in out,'Duplicate reference JSON');out[k]=v
        return out
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
@dataclass(frozen=True)
class BoundReference:
    track:SpatialTrack
    source_track:SpatialTrack
    frame:dict
    gate:dict
    parameters:dict
    provenance:dict
    def __getattr__(self,name):return getattr(self.track,name)

def load(source_track,*,reviewed_promotion_sha256):
    """Load only the producer bundle bound by an independently reviewed action.

    The digest must be inherited from the consumer's externally reviewed source
    identity. It must never be manufactured from these local files by a caller
    that has not first checked the whole source identity against its fixed action.
    """
    path=HERE/'line-artifact.json';audit_path=HERE/'line-artifact-admission.json'
    promotion_path=HERE/'producer-promotion-manifest.json'
    if not path.exists() or not audit_path.exists() or not promotion_path.exists():
        raise LineUnavailable('No independently reviewed producer bundle; no centreline fallback')
    raw=read(path,2*1048576);value=decode(raw);audit_raw=read(audit_path,1048576);audit=decode(audit_raw)
    promotion_raw=read(promotion_path,producer_receipts.MAX_ITEM)
    evidence={}
    for name in producer_receipts.NAMES:
        evidence[name]=(raw if name=='line-artifact.json' else audit_raw if name=='independent-audit.json'
            else read(HERE/'producer-receipts'/name,producer_receipts.MAX_ITEM))
    verify_producer_receipts(audit,raw,promotion_raw=promotion_raw,
        reviewed_promotion_sha256=reviewed_promotion_sha256,evidence=evidence)
    expected_producer_sources={name:sha256(read(Path(name),262144)).hexdigest() for name in
        (producer_receipts.GENERATOR,producer_receipts.GEOMETRY)}
    g.require(all(sha256(read(HERE/Path(name).name,262144)).hexdigest()==identity
        for name,identity in expected_producer_sources.items()),
        'Consumer geometry must match the original pinned producer bytes')
    source_bundle=read(HERE.parents[1]/'lapsim-aero-fidelity-20261028/configs/courses/amz_fssim_fsi_approx.json',2*1048576)
    raw_cones=read(HERE.parents[1]/'lapsim-aero-fidelity-20261028/configs/courses/upstream/amz-fssim/FSI.yaml',32768)
    g.require(sha256(source_bundle).hexdigest()=='46ce29a898f4491d3dc6456f42325769474fa7790ce4227a86a8ab537dcc373e',
        'Immutable source bundle changed')
    g.require(audit['schema']=='ev.awd-line-producer-independent-audit.v1' and audit['accepted_geometry'] is True and
        audit['material_findings']==[] and audit['actual_supported_tool_exit_observed'] is True and
        audit['artifact_sha256']==sha256(raw).hexdigest() and audit['owned_cleanup_verified'] is True and
        audit['original_lease_released'] is True and value['producer_source_sha256']==expected_producer_sources and
        value['raw_boundary_sha256']==value['frame']['raw_sha256']==sha256(raw_cones).hexdigest() and
        value['frame']['LF_sha256']==g.RAW_LF_SHA and
        value['source_bundle_payload_sha256']==g.digest(decode(source_bundle)) and
        audit['numeric_observation_scope']=='before_after_snapshots_only' and
        audit['transient_loads_excluded'] is False and audit['os_thread_count_hard_limit_claimed'] is False and
        audit['numerical_configuration_verified'] is True and audit['one_cpu_affinity_verified'] is True and
        audit['backend_fingerprint_sha256']==value['numerical_backend_fingerprint_sha256']==g.digest(value['numerical_backend']),
        'Actual producer exit,source,geometry and cleanup audit required')
    g.require(value['schema']=='ev.awd-fsi-frozen-racing-reference.v6' and
        value['status']=='GEOMETRY_SCREENED_DYNAMIC_REPLAY_UNRUN' and value['minimum_time_proven'] is False and
        value['role']=='development' and value['heldout_used'] is False and value['shared_across_techniques'] is True and
        value['source_geometry_sha256']==g.SOURCE_GEOMETRY_SHA and value['parameters']==line_generator.PARAMETERS and
        value['frame_sha256']==g.digest(value['frame']) and value['reference_geometry_sha256']==g.digest(value['geometry']) and
        value['clearance']['floating_point_continuous_rectangle_screen'] is True and
        value['topology']['adjacent_tangent_projection_screen']['joins_screened']>0 and
        value['geometric_curvature']['floating_point_bound_per_m']<=value['geometric_curvature']['limit_per_m'],
        'Frozen common development line identity differs')
    optimization=producer_receipts.validate_optimization(value)
    geometry=value['geometry'];g.require(geometry['model']=='sampled_polyline' and geometry['closed'] is True,'Explicit sampled reference')
    track=SpatialTrack(distance_m=tuple(geometry['distance_m']),x_m=tuple(geometry['x_m']),y_m=tuple(geometry['y_m']),
        curvature_per_m=tuple(geometry['curvature_per_m']),closed=True)
    g.require(8<=track.cell_count<=5000 and track.x_m[0]==track.y_m[0]==0 and
        hypot(track.x_m[-1]-track.x_m[0],track.y_m[-1]-track.y_m[0])<=1e-8 and
        all(abs(hypot(b-a,d-c)-(s1-s0))<=1e-8 for a,b,c,d,s0,s1 in
            zip(track.x_m,track.x_m[1:],track.y_m,track.y_m[1:],track.distance_m,track.distance_m[1:])),
        'Reference closure/chord stations; no inherited source distance')
    gate=value['gate'];g.require(gate['origin_xy_m']==[0.,0.] and gate['forward_unit']==[1.,0.],'Physical source gate must stay fixed')
    provenance={'artifact_sha256':sha256(raw).hexdigest(),'producer_audit_sha256':sha256(audit_raw).hexdigest(),
        'reviewed_promotion_sha256':reviewed_promotion_sha256,
        'reference_geometry_sha256':value['reference_geometry_sha256'],'source_geometry_sha256':g.SOURCE_GEOMETRY_SHA,
        'frame_sha256':value['frame_sha256'],'source_length_m':source_track.length_m,'reference_length_m':track.length_m,
        'reference_model':'sampled_polyline','physical_course':'original transformed simulator cone polylines',
        'line_claim':('Solver-converged geometric proposal;dynamic replay not yet qualified;no optimum proven' if optimization['converged'] else
            'Nonconverged or scaled geometric proposal;dynamic replay not yet qualified;not an optimum'),
        'solver_converged':optimization['solver_converged'],
        'selected_line_converged':optimization['converged'],
        'selected_fraction':optimization['selection']['selected_fraction'],
        'clearance_claim':'Continuous planned rectangle screening;actual trajectory sampled separately',
        'method':value['method']}
    return BoundReference(track,source_track,value['frame'],gate,value['parameters'],provenance)
