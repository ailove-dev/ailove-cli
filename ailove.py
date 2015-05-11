# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import os
import socket
import click
import subprocess
import ftplib
import fileinput

try:
    from subprocess import DEVNULL
except ImportError:
    import os
    DEVNULL = open(os.devnull, 'wb')


def _debug_process_params(debug=False):
    if not debug:
        return {'stdin': subprocess.PIPE, 'stdout': DEVNULL, 'stderr': subprocess.STDOUT}
    return {}


def _create_directories():
    directories = ['cache', 'conf', 'data', 'repo', 'tmp', 'logs']
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)

    click.echo('Create directories ... {}'.format(
        click.style('Success', fg='green')
    ))


def _clone_project(repo_path, project_name, debug=False):
    click.echo('Clone repo ... ', nl=False)

    if not os.path.exists(os.path.join(repo_path, '.git')):
        subprocess.check_call(
            ['git', 'clone', 'https://factory.ailove.ru/git/{}/'.format(project_name), repo_path],
            **_debug_process_params(debug)
        )
        click.secho('Success', fg='green')
    else:
        click.secho('Already exists', fg='yellow')


def _create_virtualenv(python_path, debug=False):
    click.echo('Create virtualenv ... ', nl=False)

    if not os.path.exists(os.path.join(python_path, 'bin', 'python')):
        subprocess.check_call(
            ['virtualenv', 'python'],
            **_debug_process_params(debug)
        )
        click.secho('Success', fg='green')
    else:
        click.secho('Already exists', fg='yellow')


def _install_packages(python_path, repo_path, debug=False):
    click.echo('Install python requirements ... ', nl=False)

    pip = os.path.join(python_path, 'bin', 'pip')

    if not os.path.exists(pip):
        click.secho('Error: Please install PIP', fg='red')
    else:
        subprocess.check_call(
            [pip, 'install', '-r', os.path.join(repo_path, 'requirements.txt')],
            **_debug_process_params(debug)
        )
        click.secho('Success', fg='green')


def _download_conf(project_name, username, password):
    click.echo('Get settings ... ', nl=False)

    if not os.path.exists('conf'):
        os.mkdir('conf')

    try:
        ftp = ftplib.FTP(
            '{}.dev.ailove.ru'.format(project_name),
            '{}@{}'.format(username, project_name),
            password
        )
        ftp.cwd('conf')

        for conf in ('database', 'memcache', 'redis'):
            if conf in ftp.nlst():
                with open('conf/{}'.format(conf), 'wb') as fhandle:
                    ftp.retrbinary('RETR ' + conf, fhandle.write)

                for line in fileinput.input('conf/{}'.format(conf), inplace=True):
                    print(line.replace('localhost', '{}.dev.ailove.ru'.format(project_name))),

        click.secho('Success', fg='green')
    except ftplib.error_perm as e:
        click.secho('Error: {}'.format(e.message), fg='red')
    except socket.error as e:
        click.secho('Error: {}'.format(e.message), fg='red')


def _download_static(project_name, username, password, debug=False):
    click.echo('Download static ... ', nl=False)
    try:
        subprocess.check_call(
            [
                'wget1',
                '--mirror', 'ftp://{}.dev.ailove.ru/data/static/'.format(project_name),
                '--user', '{}@{}'.format(username, project_name),
                '--password', password,
                '-nH',
            ],
            **_debug_process_params(debug)
        )
        click.secho('Success', fg='green')
    except subprocess.CalledProcessError as e:
        click.secho('Error', fg='red')
    except OSError:
        click.secho('Error: Please install wget', fg='red')

@click.group()
@click.option('--repo', envvar='REPO_PATH', default='repo/dev',
              metavar='PATH', help='Changes the repository folder location.')
@click.option('--python', envvar='PYTHON_PATH', default='python',
              metavar='PATH', help='Changes the python folder location.')
@click.option('--debug/--no-debug', default=False, envvar='DEBUG')
@click.pass_context
def cli(ctx, repo, python, debug):
    ctx.obj = {
        'DEBUG': debug,
        'REPO_PATH': repo,
        'PYTHON_PATH': python,
    }


@cli.command()
@click.pass_context
def upgrade_packages(ctx):
    _install_packages(ctx.obj['PYTHON_PATH'], ctx.obj['REPO_PATH'], ctx.obj['DEBUG'])


@cli.command()
@click.option('--project_name', prompt='Project name')
@click.option('--username', prompt='Your username')
@click.option('--password', prompt=True, hide_input=True)
@click.pass_context
def init(ctx, project_name, username, password):
    if os.path.exists(os.path.join(ctx.obj['REPO_PATH'], '.git')):
        click.echo(click.style('Project already initial', fg='red'))
        return

    _create_directories()
    _clone_project(ctx.obj['REPO_PATH'], project_name, ctx.obj['DEBUG'])
    _create_virtualenv(ctx.obj['PYTHON_PATH'], ctx.obj['DEBUG'])
    _install_packages(ctx.obj['PYTHON_PATH'], ctx.obj['REPO_PATH'], ctx.obj['DEBUG'])
    _download_conf(project_name, username, password)

    click.echo('Download static files? [y/n]')
    c = click.getchar()
    if c == 'y':
        _download_static(project_name, username, password, ctx.obj['DEBUG'])


@cli.command()
@click.option('--project_name', prompt='Project name')
@click.option('--username', prompt='Your username')
@click.option('--password', prompt=True, hide_input=True)
@click.pass_context
def download_static(ctx, project_name, username, password):
    _download_static(project_name, username, password, ctx.obj['DEBUG'])


@cli.command()
@click.option('--host', default='127.0.0.1')
@click.option('--port', default=8000, type=int)
@click.option('--autoreload', default=10)
@click.pass_context
def start_server(ctx, host, port, autoreload):
    click.echo('Start server uWSGI')
    click.echo('Serving on http://{}:{}/'.format(host, port))
    click.echo('Exit Ctrl+C')
    subprocess.check_call(
        [
            'uwsgi',
            '--http', '{}:{}'.format(host, port),
            '--home', os.path.join(os.getcwd(), ctx.obj['PYTHON_PATH']),
            '--chdir', os.path.join(os.getcwd(), ctx.obj['REPO_PATH']),
            '--module', 'app.wsgi',
            '--processes', '1',
            '--threads', '2',
            '--py-autoreload', str(autoreload),
            '--static-map', '/static={}'.format(os.path.join(os.getcwd(), 'data/static/dev')),
            '--static-map', '/={}'.format(os.path.join(os.getcwd(), 'repo/dev/htdocs')),
            '--static-index', 'index.html'
        ],
        **_debug_process_params(ctx.obj['DEBUG'])
    )