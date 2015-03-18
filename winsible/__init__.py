"""Set up processing model and inject transport modules"""

import sys, pkg_resources
assert 'ansible' not in sys.modules, "winsible must be imported before ansible!"

import ansible.constants as C
from peak.util.imports import whenImported, lazyModule

@whenImported('ansible.runner')
def inject_processing_model(runner):
    from ansible.errors import AnsibleError

    if C.PROCESS_MODE == 'gevent':
        if gevent is None:
            raise AnsibleError("'gevent' mode requires winsible.configure()")
        inject_gevent_runner(runner)

    elif C.PROCESS_MODE == 'pool':
        inject_pool_runner(runner)
    elif C.PROCESS_MODE == 'smart':
        raise AnsibleError("'smart' mode requires winsible.configure()")
    elif C.PROCESS_MODE == 'fork':
        pass    # nothing to do!
    else:
        raise AnsibleError('No such processing mode: %r' % C.PROCESS_MODE)

@whenImported('ansible.utils.plugins')
def inject_plugins(plugins):
    # Make our transport modules findable as if they were built-in
    plugins.connection_loader.add_directory(__path__[0])

    # Override default transport types; prioritize pooling transports if
    # we're in a mode where that can help
    plugins.connection_loader.aliases.update(
        _ssh='ssh', _paramiko='paramiko_ssh',
        ssh = 'ssh' if C.PROCESS_MODE == 'fork' else
              'plink' if sys.platform=='cygwin' else 'paramiko_pool',
        paramiko = 'paramiko_pool', paramiko_ssh = 'paramiko_pool'
    )


def wrap(ob, name=None):
    """Replace ob.name w/wrapper, saving original as wrapper.original"""

    def decorate(wrapper):
        attr = name or wrapper.__name__
        wrapper.original = getattr(ob, attr)
        setattr(ob, attr, wrapper)
        return wrapper

    return decorate


def inject_gevent_runner(runner):
    """Patch the runner module to use a gevent pool for tasks"""

    # Use gevent RLocks for flow control instead of lockfiles
    from gevent.lock import RLock
    replace_locks(RLock)

    # And run tasks in a gevent Pool
    @wrap(runner.Runner)
    def _parallel_exec(self, hosts):
        """Run hosts in a gevent pool"""
        from gevent.pool import Pool
        pool = Pool(self.forks)
        return pool.map(lambda host: self._executor(host, sys.stdin), hosts)


class Clone(object):
    """Pickle-able collection of attributes (used for IPC and fcntl)"""
    def __init__(self, data, attrs=None):
        if attrs is not None:
            data = [(attr, getattr(data, attr, None)) for attr in attrs] 
        self.__dict__.update(data)







def inject_pool_runner(runner):
    """Patch the runner module to use a multiprocessing connection pool"""

    import os

    from multiprocessing.managers import SyncManager, BaseProxy

    class PoolManager(SyncManager):
        """Manager for a process that will handle all connections"""

    pool = PoolManager()

    @wrap(runner.Runner)
    def _parallel_exec(self, hosts):
        """Use our pool manager in place of the generic one"""

        # When ansible asks for a Manager, give it the PoolManager instead
        @wrap(runner.multiprocessing)
        def Manager():
            # Put back the regular manager first!
            runner.multiprocessing.Manager = Manager.original
            return pool

        return _parallel_exec.original(self, hosts)

    @wrap(runner.connection)
    class Connector(runner.connection.Connector):
        """Connector that returns proxy connections from the PoolManager"""

        def connect(self, *args, **kw):
            runner_data = Clone(self.runner, [
                'su', 'su_pass', 'sudo', 'sudo_pass', 'sudo_exe',
                'private_key_file', 'module_name', 'timeout',
                'process_lockfile', 'output_lockfile'
            ])
            return pool.Connector(runner_data).connect(*args, **kw)





    # Files can't be passed via IPC, so we need our pre-fork stdin
    try:
        NEW_STDIN = os.fdopen(os.dup(sys.stdin.fileno()))
    except:
        NEW_STDIN = None

    def ConnectorFactory(runner_data):
        """Create a connector in the pool, using a remoted runner object"""
        runner_data._new_stdin = sys.stdin = NEW_STDIN
        return Connector.original(runner_data)

    class ConnectionProxy(BaseProxy):
        """Proxy for talking to pooled connections"""

        _exposed_ = [
            'connect', 'exec_command', 'put_file', 'fetch_file', 'close',
            '__getattribute__'
        ]
    
        def __getattr__(self, attr):
            res = self._callmethod('__getattribute__', [attr])
            setattr(self, attr, res)    # avoid repeated IPC
            return res
    
        for meth in _exposed_:
            locals()[meth] = (
                lambda name: lambda s,*a,**kw: s._callmethod(name, a, kw)
            )(meth)
    
        del __getattribute__

    class Data(object):
        """Pickle-able collection of attributes (used for IPC)"""
        def __init__(self, data):
            self.__dict__.update(data)
    
        @classmethod
        def clone(cls, ob, attrs):
            return cls((attr, getattr(ob, attr, None)) for attr in attrs)


    # Connections and Connectors both have a '.connect()' method
    # that returns a Connection
    connectable = dict(connect='Connection')

    PoolManager.register(
        # pool.Connection returns a ConnectionProxy
        'Connection', None, ConnectionProxy, method_to_typeid = connectable
    )
    PoolManager.register(
        # pool.Connector returns a for a Connector
        'Connector', ConnectorFactory, None, method_to_typeid = connectable
    )

    #from multiprocessing.util import log_to_stderr
    #log_to_stderr(5)

    # Now that our types are registered, we can start the pool process
    pool.start()

    # ...and use its managed lock instances
    replace_locks(pool.RLock)
    



















#### Lock Management

# Ansible uses fcntl.lockf() for flow control, so we have to patch it  :-(
import fcntl as fcntl_module
fcntl = sys.modules['fcntl'] = Clone(fcntl_module.__dict__)

@wrap(fcntl)
def lockf(fd, operation, *args, **kw):
    if hasattr(fd, 'acquire'):
        if operation & fcntl.LOCK_UN:
            return fd.release()
        else:
            return fd.acquire(not (operation & fcntl.LOCK_NB))    
    return lockf.original(fd, operation, *args, **kw)


def replace_locks(locktype):
    """Make ansible use flow-control locks of type `locktype` throughout"""

    @whenImported('ansible.runner')
    @whenImported('ansible.callbacks')
    def change_locks(module):
        for key, val in module.__dict__.items():
            if key.endswith('_LOCK') or key.endswith('_LOCKFILE'):
                if hasattr(val, 'fileno'):
                    setattr(module, key, locktype())
        return module














#### Setup default transport and process model

if sys.platform=='cygwin':
    # Make the standard ssh transport functional by default
    C.ANSIBLE_SSH_ARGS = C.get_config(
        C.p, 'ssh_connection', 'ssh_args', 'ANSIBLE_SSH_ARGS', '-o ControlMaster=no'
    )

C.PROCESS_MODE = C.get_config(
    C.p, C.DEFAULTS, 'processing_mode', 'ANSIBLE_PROCESS_MODE', 'smart'
)

gevent = None

def configure(is_playbook):
    if not is_playbook:
        # no point in using 'smart' transport; always default to ssh since the
        # connections won't persist anyway
        C.DEFAULT_TRANSPORT = C.get_config(
            C.p, C.DEFAULTS, 'transport', 'ANSIBLE_TRANSPORT', 'ssh'
        )

    if C.PROCESS_MODE == 'smart':
        """Pick a processing model based on platform and gevent availability"""
        if is_playbook:
            C.PROCESS_MODE = 'gevent'
            try:
                pkg_resources.require('gevent>=1.0.1')
            except pkg_resources.ResolutionError:                
                C.PROCESS_MODE = 'pool'    
        else:
            C.PROCESS_MODE = 'fork'
    
    if C.PROCESS_MODE == 'gevent':
        global gevent   
        import gevent.monkey
        gevent.monkey.patch_all()




#### Script Wrappers

def wrap_script(script_name, is_playbook):
    configure(is_playbook)
    maindict = sys.modules['__main__'].__dict__ 
    maindict.clear(); maindict['__name__'] = '__main__'
    return pkg_resources.require('ansible')[0].run_script(script_name, maindict)

def winsible():             return wrap_script('ansible', False)
def winsible_playbook():    return wrap_script('ansible-playbook', True)































