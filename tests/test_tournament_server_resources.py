"""Local HTTP/path tests with installed-layout assets and untrusted job doubles.

No child worker, rollout, source export, native provider or model inference runs.
"""
from contextlib import contextmanager, redirect_stdout
from functools import partial
from html.parser import HTMLParser
import http.client
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

from lapsim.experiments import tournament_server as server
from lapsim.torque_configurator import api


class InstalledServerResourcesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.assets = self.base/'site-packages/lapsim/_resources'
        (self.assets/'web').mkdir(parents=True)
        (self.assets/'build-info.json').write_text('{}')
        (self.assets/'web/tournament.html').write_text('installed controller page')
        (self.assets/'web/torque-configurator.html').write_text('installed configurator page')
        (self.assets/'web/tournament.css').write_text('installed style')
        self.work = api.resolve_work_directory(self.base/'owned-work', resource_root=self.assets, create=True)
        self.addCleanup(patch.stopall)
        patch.object(server, 'JOB', None).start()

    @contextmanager
    def http_server(self, assets=None):
        handler = partial(server.Handler, resource_root=self.assets if assets is None else assets,
                          work_dir=self.work)
        host = server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = Thread(target=host.serve_forever, kwargs={'poll_interval':.01}, daemon=True)
        thread.start()
        try:
            yield host.server_port
        finally:
            host.shutdown()
            host.server_close()
            thread.join(2)
            self.assertFalse(thread.is_alive())

    def request(self, port, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
        try:
            connection.request('GET' if body is None else 'POST', path,
                               body=None if body is None else json.dumps(body), headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def profile_double(self):
        profile = SimpleNamespace(sha256='unit-profile', to_dict=lambda:{'schema':'lapsim.torque-profile.v1',
                                                                    'architecture':'unit-architecture'})
        patch.object(api.VehicleProfile, 'from_dict', return_value=profile).start()
        patch.object(api, 'example_profile', return_value=profile).start()
        return profile

    def test_installed_requires_explicit_external_work_directory_before_binding(self):
        with patch.object(server, 'ROOT', self.assets), patch.object(server, 'ThreadingHTTPServer') as host:
            with self.assertRaisesRegex(ValueError, 'explicit absolute --work-dir'):
                server.main([])
            host.assert_not_called()
        self.assertFalse((self.assets/'work').exists())

    def test_work_root_rejects_installed_tree_relative_paths_and_aliases(self):
        for target in (self.assets/'work', self.assets.parent/'mutable', self.assets.parent.parent/'mutable', Path('relative')):
            with self.subTest(target=target), self.assertRaises(ValueError):
                api.resolve_work_directory(target, resource_root=self.assets, create=True)
        alias = self.base/'work-link'
        try:
            alias.symlink_to(self.work, target_is_directory=True)
        except OSError:
            return
        with self.assertRaisesRegex(ValueError, 'Aliased'):
            api.resolve_work_directory(alias, resource_root=self.assets)

    def test_checkout_default_remains_work_subdirectory(self):
        checkout = self.base/'checkout'
        checkout.mkdir()
        self.assertEqual(api.resolve_work_directory(resource_root=checkout, create=True), checkout/'work')
        with self.assertRaises(ValueError):
            api.resolve_work_directory(checkout/'src/outputs', resource_root=checkout, create=True)

    def test_http_serves_two_mounts_and_preserves_query_paths(self):
        (self.work/'result.json').write_text('{"local_result":true}')
        with self.http_server() as port:
            self.assertEqual(self.request(port, '/web/tournament.html'), (200,b'installed controller page'))
            self.assertEqual(self.request(port, '/web/tournament.css?v=1'), (200,b'installed style'))
            self.assertEqual(self.request(port, '/work/result.json'), (200,b'{"local_result":true}'))
            for path in ('/', '/web/', '/work/', '/build-info.json', '/src/lapsim/resources.py',
                         '/web/../build-info.json', '/work/%2e%2e/site-packages/lapsim/_resources/build-info.json',
                         '/work/a%5cb', '/work/file%3Astream', '/work/.private', '/work/NUL', '/work/CON.txt'):
                with self.subTest(path=path):
                    self.assertEqual(self.request(port, path)[0], 404)

    def test_http_does_not_follow_work_or_asset_symlinks(self):
        secret = self.base/'not-served.txt'
        secret.write_text('not a selected result or asset')
        try:
            (self.work/'link.txt').symlink_to(secret)
            (self.assets/'web/link.txt').symlink_to(secret)
        except OSError as error:
            self.skipTest(str(error))
        with self.http_server() as port:
            self.assertEqual(self.request(port, '/work/link.txt')[0], 404)
            self.assertEqual(self.request(port, '/web/link.txt')[0], 404)

    def test_http_configurator_action_receives_same_work_root_and_keeps_origin_check(self):
        with patch.object(api, 'action', return_value={'unit':True}) as action, self.http_server() as port:
            code, data = self.request(port, '/api/torque/validate', {'profile':{}},
                                      {'Origin':f'http://127.0.0.1:{port}'})
            self.assertEqual(code, 200)
            self.assertEqual(json.loads(data), {'unit':True})
            action.assert_called_once_with('validate', {'profile':{}}, work_dir=self.work)
            self.assertEqual(self.request(port, '/api/torque/validate', {'profile':{}},
                                          {'Origin':'http://unrelated.invalid'})[0], 403)
            self.assertEqual(action.call_count, 1)

    def test_all_configurator_outputs_and_selected_reads_use_explicit_work_root(self):
        self.profile_double()
        import lapsim.torque_configurator.comparison as comparison
        with patch.object(api, 'repository_root', return_value=self.assets), \
             patch.object(comparison, 'compare', return_value={'runs':{},'fingerprint':'unit'}) as compare, \
             patch.object(comparison, 'save_comparison') as save, \
             patch.object(api, 'export_source', return_value={}) as export:
            with self.assertRaisesRegex(ValueError, 'explicit absolute --work-dir'):
                api.action('compare', {'profile':{},'reference_architecture':'unit'})
            compare.assert_not_called()
            compared = api.action('compare', {'profile':{},'reference_architecture':'unit'}, work_dir=self.work)
            self.assertEqual(save.call_args.args[1], self.work/Path(compared['directory']).name)
            self.assertEqual(save.call_args.args[0]['configured_study'], compared['directory'])
            exported = api.action('export', {'profile':{}}, work_dir=self.work)
            self.assertEqual(export.call_args.args[1], self.work/Path(exported['directory']).name)
        directory = self.work/Path(compared['directory']).name
        directory.mkdir()
        (directory/'replay.json').write_text('{"synthetic_study":true}')
        with patch.object(api, 'repository_root', return_value=self.assets), \
             patch.object(comparison, 'export_selected', return_value={}) as selected:
            result = api.action('export-result', {'study':compared['directory'],'run_id':'unit'}, work_dir=self.work)
            self.assertEqual(selected.call_args.args[0], {'synthetic_study':True})
            self.assertEqual(selected.call_args.args[2], self.work/Path(result['directory']).name)
            with self.assertRaises(ValueError):
                api.action('export-result', {'study':'work/../../private','run_id':'unit'}, work_dir=self.work)
        self.assertFalse((self.assets/'work').exists())

    def test_selected_study_read_cannot_follow_a_symlink(self):
        name = 'torque-comparison-'+'a'*12
        directory = self.work/name
        directory.mkdir()
        secret = self.base/'not-a-study.json'
        secret.write_text('{}')
        try:
            (directory/'replay.json').symlink_to(secret)
        except OSError as error:
            self.skipTest(str(error))
        with self.assertRaisesRegex(ValueError, 'Aliased'):
            api.action('export-result', {'study':'work/'+name,'run_id':'unit'}, work_dir=self.work)

    def start_body(self):
        return {'kind':'search','population':4,'generations':1,'laps':1}

    def test_installed_job_double_uses_installed_interpreter_and_external_work(self):
        import lapsim.experiments.controller_tournament as tournament
        spec = dict(seed=1,population=4,generations=1,profile='synthetic_awd')
        process = SimpleNamespace(poll=lambda:None)
        with patch.object(tournament, 'specification', return_value=spec), \
             patch.object(server.subprocess, 'Popen', return_value=process) as launch, \
             patch.dict(os.environ, {'PYTHONPATH':'incorrect/checkout/src'}), self.http_server() as port:
            code, data = self.request(port, '/api/run', self.start_body())
            self.assertEqual(code, 200)
            response = json.loads(data)
            self.assertTrue(response['output'].startswith('work/gui-'))
            args, kwargs = launch.call_args
            self.assertEqual(args[0][:5], [server.sys.executable,'-I','-u','-m','lapsim.experiments.controller_tournament'])
            self.assertEqual(kwargs['cwd'], self.work)
            self.assertNotIn('PYTHONPATH', kwargs['env'])
            self.assertTrue(kwargs['stdout'].closed)
            output = self.work/Path(response['output']).name
            self.assertTrue((output/'request.json').is_file())
            self.assertEqual(self.request(port, '/'+response['output']+'/request.json')[0], 200)
            self.assertEqual(self.request(port, '/api/run', self.start_body())[0], 400)
        self.assertFalse((self.assets/'work').exists())

    def test_spawn_failure_closes_log_without_claiming_job_started(self):
        import lapsim.experiments.controller_tournament as tournament
        with patch.object(tournament, 'specification', return_value=dict(seed=1,population=4,generations=1,profile='synthetic_awd')), \
             patch.object(server.subprocess, 'Popen', side_effect=OSError('unit launch failure')) as launch, self.http_server() as port:
            code, data = self.request(port, '/api/run', self.start_body())
            self.assertEqual(code, 400)
            self.assertIn('unit launch failure', json.loads(data)['error'])
            self.assertTrue(launch.call_args.kwargs['stdout'].closed)
            self.assertIsNone(server.JOB)

    def test_status_and_cancel_use_the_selected_work_mount(self):
        output = self.work/'gui-unit'
        output.mkdir()
        checkpoint = output/'checkpoint.json'
        checkpoint.write_text(json.dumps({'status':'running','runs':{'completed-unit':{}},'total':2}))
        process = Mock()
        process.poll.return_value = None
        with patch.object(server, 'JOB', {'process':process,'kind':'search','output':output,'relative':'work/gui-unit'}), \
             patch.object(server, 'stop_owned_worker') as stop, self.http_server() as port:
            code,data = self.request(port, '/api/status')
            self.assertEqual(code, 200)
            self.assertEqual(json.loads(data)['completed'], 1)
            code,data = self.request(port, '/api/cancel', {})
            self.assertEqual(code, 200)
            stop.assert_called_once_with(process)
            saved=json.loads(checkpoint.read_text())
            self.assertEqual(saved['status'], 'cancelled')
            self.assertEqual(saved['runs'], {'completed-unit':{}})
        self.assertFalse((self.assets/'work').exists())

    def test_frozen_app_cannot_be_spawned_as_an_installed_python_worker(self):
        with patch.object(server.sys, 'frozen', True, create=True), \
             patch.object(server.subprocess, 'Popen') as launch, self.http_server() as port:
            code,data = self.request(port, '/api/run', self.start_body())
            self.assertEqual(code, 400)
            self.assertIn('no frozen-app module worker', json.loads(data)['error'])
            launch.assert_not_called()
            self.assertFalse(list(self.work.glob('gui-*')))

    def test_checkout_child_source_path_is_absolute_when_verified(self):
        import lapsim.experiments.controller_tournament as tournament
        with patch.object(tournament, 'specification', return_value=dict(seed=1,population=4,generations=1,profile='synthetic_awd')), \
             patch.object(server.subprocess, 'Popen', return_value=SimpleNamespace(poll=lambda:None)) as launch, \
             self.http_server(assets=server.ROOT) as port:
            self.assertEqual(self.request(port, '/api/run', self.start_body())[0], 200)
            self.assertEqual(launch.call_args.kwargs['env']['PYTHONPATH'], str(server.ROOT/'src'))

    def test_serve_forwarding_preserves_explicit_work_directory(self):
        from lapsim.torque_configurator.__main__ import main
        with patch.object(server, 'main') as serve:
            self.assertEqual(main(['serve','--port','8768','--work-dir',str(self.work)]), 0)
            serve.assert_called_once_with(['--port','8768','--work-dir',str(self.work)],page='web/torque-configurator.html')

    def test_http_listener_closes_even_when_owned_stop_raises(self):
        host = Mock(server_port=8765)
        host.serve_forever.side_effect = RuntimeError('unit serve stop')
        with patch.object(server, 'ThreadingHTTPServer', return_value=host), \
             patch.object(server, 'JOB', {'process':SimpleNamespace(poll=lambda:None)}), \
             patch.object(server, 'stop_owned_worker', side_effect=RuntimeError('unit cleanup stop')), \
             redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'unit cleanup stop'):
                server.main(['--work-dir',str(self.work)])
            host.server_close.assert_called_once()

    def test_static_page_links_reference_actual_sources_only(self):
        class Links(HTMLParser):
            def __init__(self):
                super().__init__()
                self.values=[]
            def handle_starttag(self, tag, attrs):
                values=dict(attrs)
                if tag=='script' and values.get('src'):self.values.append(values['src'])
                if tag in ('link','a') and values.get('href'):self.values.append(values['href'])
        web=server.ROOT/'web'
        for page in ('tournament.html','torque-configurator.html'):
            parser=Links()
            parser.feed((web/page).read_text())
            for value in parser.values:
                parsed=urlsplit(value)
                if parsed.scheme or not parsed.path:continue
                self.assertTrue((web/parsed.path).is_file(), (page,value))


if __name__=='__main__':
    unittest.main()
