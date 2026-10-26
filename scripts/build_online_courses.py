"""Build five inspected public-map approximations, without a network dependency.

Raw reference images stay in ignored work/. Checked-in pixel traces and source
digests make the geometry reproducible; they do not confer survey accuracy.
"""
from hashlib import sha256
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from build_course_library import build, manifest, rounded_polygon

IDS=('fsae_michigan_2019_image','fsae_michigan_2022_image','fsae_michigan_2023_image','fsae_electric_2024_image','fs_east_2017_image')


def online_courses():
    source=ROOT/'configs/courses/online_image_traces.json'
    traces=json.loads(source.read_text(encoding='utf-8'))
    if traces['schema']!='lapsim.image-traces.v1' or tuple(r['id'] for r in traces['courses'])!=IDS:
        raise ValueError('Unsupported frozen image traces')
    for row in traces['courses']:
        scale=row.get('meters_per_pixel',1.)
        points=[(x*scale,-y*scale) for x,y in row['points']]
        track,audit=rounded_polygon(points)
        if 'target_length_m' in row:
            scale=row['target_length_m']/track.length_m
            track,audit=rounded_polygon([(x*scale,-y*scale) for x,y in row['points']])
        method=f"Manually inspected race-route pixel vertices; y inverted, uniform scale {scale:.12g} m/pixel, tangent circular fillets; no endpoint correction. "+row['scale_basis']
        digest=row.get('image_sha256')
        if not digest or len(digest)!=64:
            raise ValueError('Pinned inspected reference image digest required')
        description='IMAGE-DERIVED APPROXIMATION. '+row['scale_basis']+' Assumed 6 m uniform width; no surveyed boundaries or calibrated vehicle. '+row['direction']
        bundle=manifest(row['id'],row['label'],description,track,row['image_url'],digest,method)
        yield bundle,{'classification':'map_derived_approximation','source_url':row['source_url'],
            'image_url':row['image_url'],'reference_image_sha256':digest,'event':row['event'],'year':row['year'],
            'license':'Reference image rights retained by its source; image not redistributed. Original approximate geometry under unchanged repository license.',
            'scale_m_per_pixel':scale,'scale_basis':row['scale_basis'],'direction_assumption':row['direction'],
            'assumed_width_m':row['assumed_width_m'],'trace_sha256':sha256(json.dumps(row,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'audit':audit}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    schema,original=build();courses=[*original,*online_courses(),*gnss_course()]
    catalog={'schema':schema,'courses':[]};payloads={}
    for bundle,extra in courses:
        payloads[bundle.course_id+'.json']=bundle.to_dict()
        catalog['courses'].append({'id':bundle.course_id,'label':bundle.label,'description':bundle.description,
            'path':'configs/courses/'+bundle.course_id+'.json','length_m':bundle.track.length_m,'geometry_sha256':bundle.geometry_sha256,**extra})
    payloads['catalog.json']=catalog
    for name,value in payloads.items():
        path=ROOT/'configs/courses'/name;text=json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n'
        if args.check:
            if path.read_text(encoding='utf-8')!=text:raise ValueError('Generated course differs: '+name)
        else:path.write_text(text,encoding='utf-8',newline='\n')
    print(json.dumps([{'id':b.course_id,'length_m':b.track.length_m,'cells':b.track.cell_count,'minimum_radius_m':e['audit']['minimum_radius_m']} for b,e in courses]))


def gnss_course():
    source=ROOT/'configs/courses/gnss_imu_trajectory_trace.json'
    row=json.loads(source.read_text(encoding='utf-8'))
    if row['schema']!='lapsim.gnss-trajectory-trace.v1':raise ValueError('Unsupported GNSS trace')
    track,audit=rounded_polygon(row['points_m'])
    bundle=manifest('fused_gnss_imu_trajectory_approx','Fused GNSS/IMU trajectory — APPROXIMATION',row['scope'],track,row['source_url'],row['source_sha256'],row['scope'])
    yield bundle,{'classification':'trajectory_derived_approximation','source_url':row['source_url'],'license':'Derived from data already in public repository; repository license unchanged.',
        'trajectory_source':True,'source_sha256':row['source_sha256'],'source_rows':row['source_rows'],
        'original_reported_length_m':row['original_reported_length_m'],'original_closure_error_m':row['original_closure_error_m'],
        'assumed_width_m':6.,'audit':audit}


if __name__=='__main__':main()
