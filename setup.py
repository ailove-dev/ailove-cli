from setuptools import setup

setup(
    name='ailove-cli',
    version='0.1',
    url='https://github.com/ailove-dev/ailove-cli',
    license='MIT',
    author='Dmitriy Sokolov',
    author_email='silentsokolov@gmail.com',
    py_modules=['ailove'],
    include_package_data=True,
    install_requires=[
        'click',
        'uwsgi',
    ],
    entry_points='''
        [console_scripts]
        ailove=ailove:cli
    ''',
)