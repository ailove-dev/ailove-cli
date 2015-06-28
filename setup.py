from setuptools import setup

setup(
    name='ailove-cli',
    version='0.2.1',
    url='https://github.com/ailove-dev/ailove-cli',
    license='MIT',
    author='Dmitriy Sokolov',
    author_email='silentsokolov@gmail.com',
    py_modules=['ailove'],
    include_package_data=True,
    install_requires=[
        'click',
        'uwsgi',
        'python-redmine'
    ],
    entry_points='''
        [console_scripts]
        ailove=ailove:cli
    ''',
)