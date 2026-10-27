"""Standalone, simulation-only profile/controller entry point."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from .profile import canonical,example_profile,load_profile,require,PROFILE_FILES
from .session import replay,read_trace
from .adapter import validate
from .export import export_source,write_json


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    example=sub.add_parser('example');example.add_argument('--output',type=Path)
    example.add_argument('--experimental',action='store_true');example.add_argument('--architecture',choices=tuple(PROFILE_FILES),default=next(iter(PROFILE_FILES)))
    for command in ('run','validate','export'):
        item=sub.add_parser(command);item.add_argument('--profile',type=Path,required=True)
        item.add_argument('--output',type=Path,required=True)
        if command=='run':
            item.add_argument('--trace',type=Path,required=True)
            group=item.add_mutually_exclusive_group();group.add_argument('--full-lap',action='store_true',help='Explicit v2 trace, bounded to 6001 frames');group.add_argument('--ten-lap',action='store_true',help='Explicit v3 trace, bounded to 60001 frames / 600 s')
        else:item.add_argument('--duration-ms',type=int,default=300)
    serve=sub.add_parser('serve');serve.add_argument('--port',type=int,default=8768)
    verify=sub.add_parser('verify');verify.add_argument('--package',type=Path,required=True);verify.add_argument('--output',type=Path,required=True)
    compare=sub.add_parser('compare');compare.add_argument('--profile',type=Path,required=True);compare.add_argument('--reference',type=Path,required=True)
    compare.add_argument('--duration-ms',type=int,default=1000);compare.add_argument('--course',choices=('stadium','autocross'),default='stadium');compare.add_argument('--output',type=Path,required=True)
    group=compare.add_mutually_exclusive_group();group.add_argument('--full-lap',action='store_true',help='Synthetic one-lap acceptance');group.add_argument('--ten-lap',action='store_true',help='Ten continuous laps / at most 600000 ms')
    saved=sub.add_parser('compare-saved',help='Assemble two source-matched full-lap baseline receipts without rerunning the plant')
    saved.add_argument('--baseline',type=Path,action='append',required=True);saved.add_argument('--output',type=Path,required=True)
    reproduce=sub.add_parser('reproduce-result');reproduce.add_argument('--package',type=Path,required=True);reproduce.add_argument('--output',type=Path,required=True)
    selected=sub.add_parser('export-result');selected.add_argument('--study',type=Path,required=True);selected.add_argument('--run-id',required=True);selected.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='serve':
            from lapsim.experiments.tournament_server import main as serve_simulator
            from lapsim.resources import repository_root
            require(1024<=args.port<=65535,'Choose an unprivileged loopback port')
            require((repository_root()/'web/torque-configurator.html').is_file(),
                    'UI assets are unavailable in this source-only export; use the run/validate CLI')
            serve_simulator(['--port',str(args.port)],page='web/torque-configurator.html')
            return 0
        if args.command=='example':
            from .policy import experimental_profile
            value=(experimental_profile(args.architecture) if args.experimental else example_profile(args.architecture)).to_dict()
            if args.output:write_json(args.output,value)
            else:print(json.dumps(value,indent=2))
            return 0
        if args.command=='verify':
            from .verify import verify_package
            value=verify_package(args.package)
            write_json(args.output,value)
            print(json.dumps(value,indent=2));return 0
        if args.command=='reproduce-result':
            from .comparison import reproduce_package
            value=reproduce_package(args.package);write_json(args.output,value);print(json.dumps(value,indent=2));return 0
        if args.command=='export-result':
            from .comparison import export_selected,STUDY_BYTE_LIMIT
            from .verify import bounded_json
            require(not args.output.exists(),'Export directory already exists; prior output is preserved')
            value=export_selected(bounded_json(args.study,limit=STUDY_BYTE_LIMIT),args.run_id,args.output)
            print(json.dumps(value,indent=2));return 0
        if args.command in ('compare','compare-saved'):
            from .comparison import compare as run_comparison,compare_saved_baselines,save_comparison
            require(not args.output.exists(),'Comparison directory already exists; prior results are preserved')
            value=compare_saved_baselines(args.baseline) if args.command=='compare-saved' else run_comparison(
                [load_profile(args.profile),load_profile(args.reference)],duration_ms=args.duration_ms,course=args.course,full_lap=args.full_lap,ten_lap=args.ten_lap)
            save_comparison(value,args.output)
            result={'fingerprint':value['fingerprint'],'runs':len(value['runs']),'output':str(args.output)}
            if value.get('configured_study'):
                result['viewer_url']='/web/tournament.html?configured='+value['configured_study'].split('-')[-1]
            print(json.dumps(result,indent=2));return 0
        profile=load_profile(args.profile)
        if args.command=='export':
            print(json.dumps(export_source(profile,args.output,args.duration_ms),indent=2));return 0
        if args.command=='validate':value=validate(profile,args.duration_ms)
        else:
            outputs=replay(profile,read_trace(profile,args.trace,full_lap=args.full_lap,ten_lap=args.ten_lap),full_lap=args.full_lap,ten_lap=args.ten_lap)
            value={'schema':'lapsim.torque-output.v3' if args.ten_lap else 'lapsim.torque-output.v2' if args.full_lap else 'lapsim.torque-output.v1','profile_sha256':profile.sha256,'outputs':outputs,
                   'outputs_sha256':sha256(canonical(outputs).encode()).hexdigest(),'simulation_only':True}
        write_json(args.output,value)
        print(json.dumps({k:v for k,v in value.items() if k in ('schema','profile_sha256','outputs_sha256','equivalent','repeat_exact','cycles')},indent=2))
        return 0
    except (ValueError,OSError,TypeError,KeyError) as error:
        parser.exit(2,str(error)+'\n')


if __name__=='__main__':raise SystemExit(main())
