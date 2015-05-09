# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import os
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


def create_directories():
    directories = ['cache', 'conf', 'data', 'repo', 'tmp', 'logs']
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)

    message = click.style('Success', fg='green')
    click.echo('Create directories ... {}'.format(message))


def clone_project(repo_path, project_name, debug=False):
    if not os.path.exists(os.path.join(repo_path, '.git')):
        click.echo('Clone repo ...')
        subprocess.check_call(
            ['git', 'clone', 'https://factory.ailove.ru/git/{}/'.format(project_name), repo_path],
            **_debug_process_params(debug)
        )
        message = click.style('Success', fg='green')
    else:
        message = click.style('Already exists', fg='yellow')
    click.echo('Clone repo ... {}'.format(message))


def create_virtualenv(python_path, debug=False):
    if not os.path.exists(os.path.join(python_path, 'bin', 'python')):
        subprocess.check_call(
            ['virtualenv', 'python'],
            **_debug_process_params(debug)
        )
        message = click.style('Success', fg='green')
    else:
        message = click.style('Already exists', fg='yellow')
    click.echo('Create virtualenv ... {}'.format(message))


def install_packages(python_path, repo_path, debug=False):
    pip = os.path.join(python_path, 'bin', 'pip')
    if not os.path.exists(pip):
        click.echo(click.style('Please install PIP', fg='red'))
    else:
        click.echo('Install python requirements ...')
        subprocess.check_call(
            [pip, 'install', '-r', os.path.join(repo_path, 'requirements.txt')],
            **_debug_process_params(debug)
        )
        click.echo('Install python requirements ... {}'.format(click.style('Success', fg='green')))


def download_conf(project_name, username, password):
    message = click.style('Success', fg='green')
    try:
        ftp = ftplib.FTP(
            '{}.dev.ailove.ru'.format(project_name),
            '{}@{}'.format(username, project_name),
            password
        )
        ftp.cwd('conf')
        with open('conf/database', 'wb') as fhandle:
            ftp.retrbinary('RETR ' + 'database', fhandle.write)

        for line in fileinput.input('conf/database', inplace=True):
            print(line.replace('localhost', '{}.dev.ailove.ru'.format(project_name))),
    except IOError:
        message = click.style('File does not exists', fg='reg')
    except ftplib.error_perm:
        message = click.style('Login/Password incorrect', fg='red')

    click.echo('Create database connect ... {}'.format(message))


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
    install_packages(ctx.obj['PYTHON_PATH'], ctx.obj['REPO_PATH'], ctx.obj['DEBUG'])


@cli.command()
@click.option('--project_name', prompt='Project name please')
@click.option('--username', prompt='Your username please')
@click.option('--password', prompt=True, hide_input=True)
@click.pass_context
def init(ctx, project_name, username, password):
    if os.path.exists(os.path.join(ctx.obj['REPO_PATH'], '.git')):
        click.echo(click.style('Project already initial', fg='red'))
        return

    create_directories()
    clone_project(ctx.obj['REPO_PATH'], project_name, ctx.obj['DEBUG'])
    create_virtualenv(ctx.obj['PYTHON_PATH'], ctx.obj['DEBUG'])
    install_packages(ctx.obj['PYTHON_PATH'], ctx.obj['REPO_PATH'], ctx.obj['DEBUG'])
    download_conf(project_name, username, password)


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


if __name__ == '__main__':
    cli()