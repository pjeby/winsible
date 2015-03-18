from setuptools import setup

setup(
    name='winsible',
    version='0.1.0',
    packages=['winsible'],
    description = "A faster `ansible` For The (cyg)Win (and other platforms)",
    author="PJ Eby",
    author_email="peak@eby-sarna.com",
    license="MIT",
    long_description = open('README.md').read().split('How It Works')[0] +
        "For more information on how this works and how to configure it, "
        "check out the docs at https://github.com/pjeby/winsible/.\n"
    ,
    keywords = "ansible ssh cygwin",
    url = "https://github.com/pjeby/winsible",

    package_data = {'winsible':['*.exe', 'sessions/*']},
    include_package_data = True,
    zip_safe = False,    # .exe's have to be run
    
    install_requires = [
        'ansible >= 1.8.4', 'Importing >= 1.10', 'cachetools >= 1.0',
        'paramiko>=1.15.2',
        'setuptools',   # used for pkg_resources calls at runtime 
    ],
    extras_require = dict(gevent = ['gevent >= 1.0.1']),
    
    entry_points = dict( console_scripts = [
            'winsible = winsible:winsible',
            'winsible-playbook = winsible:winsible_playbook',
    ]),
)
