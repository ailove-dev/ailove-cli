# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import ConfigParser
import os
import socket
import click
import subprocess
import ftplib
import fileinput
import hashlib

from functools import wraps
from redmine import Redmine, AuthError, ResourceNotFoundError

try:
    from subprocess import DEVNULL
except ImportError:
    import os
    DEVNULL = open(os.devnull, 'wb')

APP_NAME = 'AiLove CLI'
REDMINE_URL = 'https://factory.ailove.ru/'
REQUIRE_CMDS = {
    'wget': True,
    'git': True,
    'virtualenv': True,
    'uwsgi': True,
    'mysql': False,
    'psql': False,
}


def check_command_exists(name):
    try:
        subprocess.Popen([name, '--help'], stdout=DEVNULL, stderr=DEVNULL).communicate()
    except OSError as e:
        if e.errno == os.errno.ENOENT:
            return False
    return True


def run_process(args, debug=False):
    params = {}
    if not debug:
        params = {'stdin': subprocess.PIPE, 'stdout': DEVNULL, 'stderr': subprocess.PIPE}

    process = subprocess.Popen(
        args,
        **params
    )
    process.wait()
    stdout, stderr = process.communicate()

    if process.returncode:
        if debug:
            click.echo(stderr, nl=False)
        else:
            click.secho('Error: Something went wrong.', fg='red')


def login_require(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        app_path = click.get_app_dir(APP_NAME, force_posix=True)
        path_config = os.path.join(app_path, 'config.ini')

        try:
            config = ConfigParser.RawConfigParser()
            config.read(path_config)

            username = config.get('user', 'username')
            password = config.get('user', 'password')

            redmine = Redmine('https://factory.ailove.ru/',
                              username=username, password=password)
            redmine.auth()
        except (AuthError, ConfigParser.NoSectionError, ConfigParser.NoOptionError, OSError):
            raise click.ClickException(click.style('Error: Login/Password incorrect\n'
                                                   'Please use command: ailove login', fg='red'))
        return f(*args, **kwargs)
    return wrapper


def _check_project(project_name, username, password, debug=False):
    redmine = Redmine(REDMINE_URL, username=username, password=password)

    try:
        redmine.project.get(project_name)
        return True
    except ResourceNotFoundError:
        return False


def _set_config(section, key, value):
    path_config = os.path.join(os.getcwd(), '.ailove_config.ini')

    config = ConfigParser.RawConfigParser()

    try:
        config.add_section(section)
    except ConfigParser.DuplicateSectionError:
        pass

    config.set(section, key, value)

    with open(path_config, 'wb') as configfile:
        config.write(configfile)


def _get_config(section, key):
    path_config = os.path.join(os.getcwd(), '.ailove_config.ini')
    config = ConfigParser.RawConfigParser()
    config.read(path_config)

    try:
        return config.get(section, key)
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, OSError):
        return None


def _check_requirements(repo_path):
    file_requirements = os.path.join(repo_path, 'requirements.txt')
    current_hash = hashlib.sha256(open(file_requirements, 'rb').read()).hexdigest()

    if current_hash != _get_config('cache', 'require_hash'):
        return False
    return True


def _create_directories():
    directories = ['cache', 'conf', 'data', 'repo', 'tmp', 'logs']
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)

    click.echo('Create directories ... {}'.format(
        click.style('Success', fg='green')
    ))


def _clone_project(repo_path, project_name, username, password, debug=False):
    click.echo('Clone repo ... ', nl=False)

    if not os.path.exists(os.path.join(repo_path, '.git')):
        run_process(
            ['git', 'clone',
             'https://{}:{}@factory.ailove.ru/git/{}/'.format(
                 username, password, project_name
             ),
             repo_path],
            debug=debug
        )
        click.secho('Success', fg='green')
    else:
        click.secho('Already exists', fg='yellow')


def _create_virtualenv(python_path, debug=False):
    click.echo('Create virtualenv ... ', nl=False)

    if not os.path.exists(os.path.join(python_path, 'bin', 'python')):
        run_process(
            ['virtualenv', 'python'],
            debug=debug
        )
        click.secho('Success', fg='green')
    else:
        click.secho('Already exists', fg='yellow')


def _install_packages(python_path, repo_path, debug=False):
    click.echo('Install python requirements ... ', nl=False)

    pip = os.path.join(python_path, 'bin', 'pip')

    if not os.path.exists(pip):
        click.secho('Error: Please install PIP.', fg='red')
    else:
        run_process(
            [pip, 'install', '-r', os.path.join(repo_path, 'requirements.txt')],
            debug=debug
        )
        # set new hash
        file_requirements = os.path.join(repo_path, 'requirements.txt')
        current_hash = hashlib.sha256(open(file_requirements, 'rb').read()).hexdigest()
        _set_config('cache', 'require_hash', current_hash)

        click.secho('Success', fg='green')


def _download_conf(project_name, username, password):
    click.echo('Get settings ... ', nl=False)

    if not os.path.exists('conf'):
        os.mkdir('conf')

    try:
        ftp = ftplib.FTP(
            '{}.dev.ailove.ru'.format(project_name),
            '{}@{}'.format(username, project_name),
            password,
            timeout=60
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
        click.secho('{}'.format(e.message), fg='red')
    except socket.error as e:
        click.secho('{}'.format(e.message), fg='red')


def _download_static(project_name, username, password, debug=False):
    click.echo('Download static ... ', nl=False)
    try:
        run_process(
            [
                'wget',
                '--mirror', 'ftp://{}.dev.ailove.ru/data/static/'.format(project_name),
                '--user', '{}@{}'.format(username, project_name),
                '--password', password,
                '-nH',
            ],
            debug=debug
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
    app_path = click.get_app_dir(APP_NAME, force_posix=True)
    path_config = os.path.join(app_path, 'config.ini')

    try:
        config = ConfigParser.RawConfigParser()
        config.read(path_config)
        username = config.get('user', 'username')
        password = config.get('user', 'password')
    except:
        username = None
        password = None

    ctx.obj = {
        'DEBUG': debug,
        'REPO_PATH': repo,
        'PYTHON_PATH': python,
        'username': username,
        'password': password
    }


@cli.command()
@click.option('--username', prompt='Your username')
@click.option('--password', prompt=True, hide_input=True)
def login(username, password):
    err = False
    for cmd_name, required in REQUIRE_CMDS.items():
        click.echo('Check command: {} ... '.format(cmd_name), nl=False)
        if not check_command_exists(cmd_name) and required:
            err = True
            click.secho('requires installation', fg='red')
        elif not check_command_exists(cmd_name) and not required:
            click.secho('desirable to install', fg='yellow')
        else:
            click.secho('OK', fg='green')

    if err:
        click.secho('Please install the required packages', fg='red')
        return

    try:
        redmine = Redmine(REDMINE_URL,
                          username=username, password=password)
        redmine.auth()
    except AuthError:
        click.secho('Error: Login/Password incorrect', fg='red')
        return

    app_path = click.get_app_dir(APP_NAME, force_posix=True)
    if not os.path.exists(app_path):
        os.makedirs(app_path)

    config = ConfigParser.RawConfigParser()
    path_config = os.path.join(app_path, 'config.ini')

    config.add_section('user')
    config.set('user', 'username', username)
    config.set('user', 'password', password)

    with open(path_config, 'wb') as configfile:
        config.write(configfile)


@cli.command()
@click.pass_context
def upgrade_packages(ctx):
    _install_packages(ctx.obj['PYTHON_PATH'], ctx.obj['REPO_PATH'], ctx.obj['DEBUG'])


@cli.command()
@click.option('--project_name', prompt='Project name')
@click.pass_context
@login_require
def init(ctx, project_name):
    if os.path.exists(os.path.join(ctx.obj['REPO_PATH'], '.git')):
        click.echo(click.style('Error: Project already initial.', fg='red'))
        return

    if not _check_project(project_name, ctx.obj['username'], ctx.obj['password']):
        click.echo(click.style('Error: Project does not exists.', fg='red'))
        return

    _create_directories()
    _clone_project(ctx.obj['REPO_PATH'],
                   project_name,
                   ctx.obj['username'],
                   ctx.obj['password'],
                   ctx.obj['DEBUG'])
    _create_virtualenv(ctx.obj['PYTHON_PATH'],
                       ctx.obj['DEBUG'])
    _install_packages(ctx.obj['PYTHON_PATH'],
                      ctx.obj['REPO_PATH'],
                      ctx.obj['DEBUG'])
    _download_conf(project_name,
                   ctx.obj['username'],
                   ctx.obj['password'])

    click.echo('Download static files? [y/n]')
    c = click.getchar()
    if c == 'y':
        _download_static(project_name,
                         ctx.obj['username'],
                         ctx.obj['password'],
                         ctx.obj['DEBUG'])


@cli.command()
@click.option('--project_name', prompt='Project name')
@click.pass_context
@login_require
def download_static(ctx, project_name):
    _download_static(project_name,
                     ctx.obj['username'],
                     ctx.obj['password'],
                     ctx.obj['DEBUG'])


@cli.command()
@click.option('--host', default='127.0.0.1')
@click.option('--port', default=8000, type=int)
@click.option('--htdocs', default='repo/dev/htdocs')
@click.option('--static', default='data/static/dev')
@click.option('--autoreload', default=10)
@click.pass_context
def webserver(ctx, host, port, htdocs, static, autoreload):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    errno = s.connect_ex(('127.0.0.1', 8000))

    if not errno:
        click.secho('Error: That port is already in use.'.format(port), fg='red')
        return

    if not _check_requirements(ctx.obj['REPO_PATH']):
        click.secho('requirements.txt changed, need upgrade python packages.'.format(port), fg='yellow')
        click.echo('Do it now? [y/n]')
        c = click.getchar()
        if c == 'y':
            _install_packages(ctx.obj['PYTHON_PATH'], ctx.obj['REPO_PATH'], ctx.obj['DEBUG'])

    click.echo('Start server uWSGI')
    click.echo('Serving on http://{}:{}/'.format(host, port))
    click.echo('Exit Ctrl+C')
    run_process(
        [
            'uwsgi',
            '--http', '{}:{}'.format(host, port),
            '--home', os.path.join(os.getcwd(), ctx.obj['PYTHON_PATH']),
            '--chdir', os.path.join(os.getcwd(), ctx.obj['REPO_PATH']),
            '--module', 'app.wsgi',
            '--processes', '1',
            '--threads', '2',
            '--py-autoreload', str(autoreload),
            '--static-map', '/static={}'.format(os.path.join(os.getcwd(), static)),
            '--static-map', '/={}'.format(os.path.join(os.getcwd(), htdocs)),
            '--static-index', 'index.html'
        ],
        debug=ctx.obj['DEBUG']
    )


@cli.command()
@click.option('--host', default='127.0.0.1')
@click.option('--port', default=8000, type=int)
@click.pass_context
@login_require
def devserver(ctx, host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    errno = s.connect_ex(('127.0.0.1', 8000))

    if not errno:
        click.secho('Error: That port is already in use.'.format(port), fg='red')
        return

    if not _check_requirements(ctx.obj['REPO_PATH']):
        click.secho('requirements.txt changed, need upgrade python packages.'.format(port), fg='yellow')
        click.echo('Do it now? [y/n]')
        c = click.getchar()
        if c == 'y':
            _install_packages(ctx.obj['PYTHON_PATH'], ctx.obj['REPO_PATH'], ctx.obj['DEBUG'])

    click.echo('Start server Django server')
    click.echo('Serving on http://{}:{}/'.format(host, port))
    click.echo('Exit Ctrl+C')

    run_process(
        [
            os.path.join(os.getcwd(), os.path.join(ctx.obj['PYTHON_PATH'], 'bin/python')),
            os.path.join(os.getcwd(), os.path.join(ctx.obj['REPO_PATH'], 'manage.py')),
            'runserver',
            '{}:{}'.format(host, port)
        ],
        debug=ctx.obj['DEBUG']
    )
