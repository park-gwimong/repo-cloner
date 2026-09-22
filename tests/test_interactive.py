from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import repo_cloner as app


class InteractiveTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / 'repositories.json'
        self.source = {'name': 'team', 'provider': 'bitbucket-cloud',
                       'workspace': 'w', 'project': 'A', 'token': 'secret'}
        self.output = io.StringIO()

    def run_config(self, dry_run=False):
        self.config.write_text(json.dumps({'sources': [self.source]}), encoding='utf-8')
        with redirect_stdout(self.output), redirect_stderr(self.output), \
                patch.object(app.shutil, 'which', return_value='git'):
            return app.run(self.config, dry_run=dry_run, interactive=True)

    def test_selection_ranges_duplicates_retry_and_cancel(self):
        with redirect_stdout(self.output), patch('builtins.input', side_effect=['', '0', '4', '3-1', '2,1-3,2']):
            self.assertEqual(app._select_indices('Choose', ['a', 'b', 'c']), [0, 1, 2])
        for answer, expected in [('all', [0, 1]), ('none', [])]:
            with redirect_stdout(self.output), patch('builtins.input', return_value=answer):
                self.assertEqual(app._select_indices('Choose', ['a', 'b']), expected)
        for effect in (['q'], EOFError):
            with redirect_stdout(self.output), patch('builtins.input', side_effect=effect):
                with self.assertRaises(KeyboardInterrupt):
                    app._select_indices('Choose', ['a'])

    def test_select_project_and_repository_then_confirm(self):
        repo = app.Repository('chosen', 'git@example.com:p/chosen.git')
        other = app.Repository('other', 'git@example.com:p/other.git')
        with patch.object(app, 'available_projects', return_value=[('A', 'Alpha'), ('B', 'Beta')]), \
                patch.object(app, 'repositories', return_value=[repo, other]) as listing, \
                patch('builtins.input', side_effect=['2', '1', 'y']), \
                patch.object(app, 'clone', return_value='cloned') as clone:
            self.assertEqual(self.run_config(), 0)
        self.assertEqual(listing.call_args.args[0]['project'], 'B')
        clone.assert_called_once_with(repo, self.root / 'clones/team/B', False)
        self.assertIn('cloned=1 updated=0 unchanged=0 skipped=1', self.output.getvalue())
        self.assertNotIn('secret', self.output.getvalue())

    def test_original_single_project_keeps_existing_path_and_dry_run_does_not_confirm(self):
        repo = app.Repository('repo', 'git@example.com:p/repo.git')
        with patch.object(app, 'available_projects', return_value=[('A', 'Alpha')]), \
                patch.object(app, 'repositories', return_value=[repo]), \
                patch('builtins.input', side_effect=['all', 'all']) as prompt, \
                patch.object(app, 'clone', return_value='planned') as clone:
            self.assertEqual(self.run_config(dry_run=True), 0)
        clone.assert_called_once_with(repo, self.root / 'clones/team', True)
        self.assertEqual(prompt.call_count, 2)

    def test_decline_or_eof_cannot_start_execution(self):
        repo = app.Repository('repo', 'git@example.com:p/repo.git')
        for final in ('', 'n', EOFError()):
            with self.subTest(final=final), \
                    patch.object(app, 'available_projects', return_value=[('A', 'Alpha')]), \
                    patch.object(app, 'repositories', return_value=[repo]), \
                    patch('builtins.input', side_effect=['1', '1', final]), \
                    patch.object(app, 'clone') as clone:
                if isinstance(final, EOFError):
                    with self.assertRaises(KeyboardInterrupt):
                        self.run_config()
                else:
                    self.assertEqual(self.run_config(), 0)
                clone.assert_not_called()
        self.assertFalse((self.root / 'clones').exists())

    def test_no_projects_means_no_prompt_or_clone(self):
        with patch.object(app, 'available_projects', return_value=[]), \
                patch('builtins.input') as prompt, patch.object(app, 'clone') as clone:
            self.assertEqual(self.run_config(), 0)
        prompt.assert_not_called()
        clone.assert_not_called()

    def test_choose_source_and_discovery_failure_continues(self):
        sources = [dict(self.source, name='one'), dict(self.source, name='two'),
                   {'name': 'three', 'provider': 'git'}]
        with redirect_stdout(self.output), redirect_stderr(self.output), \
                patch('builtins.input', side_effect=['1,3']), \
                patch.object(app, 'available_projects', side_effect=app.ClonerError('failure')) as discovery:
            expanded, failed = app._interactive_sources(sources)
        discovery.assert_called_once_with(sources[0])
        self.assertEqual(failed, 1)
        self.assertEqual(expanded, [(sources[2], ('three',))])

    def test_cloud_discovery_paginates_and_deduplicates(self):
        next_url = 'https://api.bitbucket.org/2.0/next'
        with patch.object(app.Api, 'get', side_effect=[
            {'values': [{'project': {'key': 'B', 'name': 'Beta'}}], 'next': next_url},
            {'values': [{'project': {'key': 'A', 'name': 'Alpha'}},
                        {'project': {'key': 'B', 'name': 'Beta'}}]},
        ]) as get:
            self.assertEqual(app.available_projects(self.source), [('A', 'Alpha'), ('B', 'Beta')])
        query = parse_qs(urlsplit(get.call_args_list[0].args[0]).query)
        self.assertNotIn('q', query)
        self.assertEqual(query['fields'], ['values.project.key,values.project.name,next'])
        self.assertEqual(get.call_args.args[0], next_url)

    def test_discovery_rejects_repeated_page_and_unsafe_key(self):
        for data in ({'values': [], 'next': 'https://api.bitbucket.org/2.0/next'},
                     {'values': [{'project': {'key': '../escape'}}]}):
            with patch.object(app.Api, 'get', return_value=data), self.assertRaises(app.ClonerError):
                app.available_projects(self.source)

    def test_server_discovery_paginates(self):
        with patch.object(app.Api, 'get', side_effect=[
            {'values': [{'key': 'A', 'name': 'Alpha'}], 'isLastPage': False, 'nextPageStart': 17},
            {'values': [{'key': 'B', 'name': 'Beta'}], 'isLastPage': True},
        ]) as get:
            self.assertEqual(app.available_projects({'provider': 'bitbucket-server',
                             'baseUrl': 'https://example.com'}), [('A', 'Alpha'), ('B', 'Beta')])
        self.assertIn('start=17', get.call_args.args[0])

    def test_cli_passes_interactive_flag(self):
        with patch('sys.argv', ['repo_cloner.py', '-i', '--dry-run']), patch.object(app, 'run', return_value=0) as run:
            self.assertEqual(app.main(), 0)
        run.assert_called_once_with(Path('repositories.json'), True, None, interactive=True)
