from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import repo_cloner as app


class ProjectProgressTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / 'repositories.json'
        self.output = io.StringIO()
        self.source = {'name': 'team', 'provider': 'bitbucket-cloud',
                       'workspace': 'workspace', 'projects': ['A', 'B'], 'token': 'secret'}

    def run_config(self, **kwargs):
        self.config.write_text(json.dumps({'sources': [self.source]}), encoding='utf-8')
        with redirect_stdout(self.output), redirect_stderr(self.output):
            return app.run(self.config, **kwargs)

    def test_lists_all_projects_and_displays_all_targets_before_cloning(self):
        calls = []

        def listing(source, protocol):
            calls.append(source['project'])
            self.assertEqual(source['token'], 'secret')
            return [app.Repository('same', 'git@example.com:p/repo.git')]

        def clone(repo, parent, dry_run):
            self.assertEqual(calls, ['A', 'B'])
            self.assertIn('team/A/same', self.output.getvalue())
            self.assertIn('team/B/same', self.output.getvalue())
            return 'planned'

        with patch.object(app, 'repositories', side_effect=listing), \
                patch.object(app, 'clone', side_effect=clone) as operation:
            self.assertEqual(self.run_config(dry_run=True), 0)
        self.assertEqual([call.args[1] for call in operation.call_args_list],
                         [self.root / 'clones/team/A', self.root / 'clones/team/B'])
        self.assertIn('Progress: 0/2 (0%)', self.output.getvalue())
        self.assertIn('Progress: 2/2 (100%)', self.output.getvalue())
        self.assertNotIn('secret', self.output.getvalue())

    def test_listing_and_clone_failures_do_not_stop_other_projects(self):
        self.source['projects'] = ['A', 'B', 'C']
        repo = app.Repository('repo', 'git@example.com:p/repo.git')
        with patch.object(app, 'repositories', side_effect=[app.ClonerError('listing'), [repo], [repo]]), \
                patch.object(app, 'clone', side_effect=[app.ClonerError('clone'), 'planned']):
            self.assertEqual(self.run_config(dry_run=True), 1)
        self.assertIn('Progress: 2/2 (100%)', self.output.getvalue())
        self.assertIn('planned=1 failed=2', self.output.getvalue())

    def test_invalid_project_lists_fail_before_listing(self):
        for projects in ([], 'A', None, ['A', 'a'], ['../escape'], [1], ['']):
            self.source['projects'] = projects
            with self.subTest(projects=projects), patch.object(app, 'repositories') as listing:
                with self.assertRaises(app.ClonerError):
                    self.run_config(dry_run=True)
                listing.assert_not_called()
        self.source['projects'] = ['A']
        self.source['project'] = 'B'
        with self.assertRaises(app.ClonerError):
            self.run_config(dry_run=True)

    def test_empty_plan_has_no_division_by_zero_or_clone(self):
        with patch.object(app, 'repositories', return_value=[]), patch.object(app, 'clone') as clone:
            self.assertEqual(self.run_config(dry_run=True), 0)
        clone.assert_not_called()
        self.assertIn('Targets: 0 repositories', self.output.getvalue())

    def test_duplicate_destinations_are_not_executed_twice(self):
        self.source['projects'] = ['A']
        repo = app.Repository('same', 'git@example.com:p/repo.git')
        with patch.object(app, 'repositories', return_value=[repo, repo]), \
                patch.object(app, 'clone', return_value='planned') as clone:
            self.assertEqual(self.run_config(dry_run=True), 1)
        clone.assert_called_once()
        self.assertIn('planned=1 failed=1', self.output.getvalue())

    def test_both_bitbucket_providers_query_each_project(self):
        for provider in ('bitbucket-cloud', 'bitbucket-server'):
            source = dict(self.source, provider=provider, baseUrl='https://example.com')
            with self.subTest(provider=provider), patch.object(app.Api, 'get',
                    return_value={'values': [], 'isLastPage': True}) as get:
                for child, parts in app._project_sources(source):
                    list(app.repositories(child, 'ssh'))
                self.assertEqual(get.call_count, 2)
                urls = [call.args[0] for call in get.call_args_list]
                if provider == 'bitbucket-cloud':
                    self.assertIn('project.key%3D%22A%22', urls[0])
                    self.assertIn('project.key%3D%22B%22', urls[1])
                else:
                    self.assertIn('/projects/A/repos', urls[0])
                    self.assertIn('/projects/B/repos', urls[1])

    def test_heartbeat_is_live_while_clone_is_running_and_stops_on_failure(self):
        reported = threading.Event()
        lines = []

        def print_line(text, **kwargs):
            lines.append(text)
            if len(lines) > 1:
                reported.set()

        def clone(*args):
            self.assertTrue(reported.wait(5), 'No live progress while clone was running')
            raise app.ClonerError('failure')

        with patch('builtins.print', side_effect=print_line), patch.object(app, 'clone', side_effect=clone):
            with self.assertRaises(app.ClonerError):
                app._run_with_progress(app.Repository('repo', 'git@example.com:p/repo.git'),
                                       self.root, False, 0, 1, 'team/repo')
        self.assertGreaterEqual(len(lines), 2)
        self.assertIn('RUNNING team/repo', lines[-1])
