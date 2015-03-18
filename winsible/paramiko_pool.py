from ansible.runner.connection_plugins.paramiko_ssh import Connection as Base
from cachetools import TTLCache
from ansible.constants import get_config, p as ansible_cfg

CACHE_SIZE = get_config(ansible_cfg, 'paramiko_connection', 'max_connections',
    'ANSIBLE_PARAMIKO_MAX_CONNECTIONS', 50, integer=True
)

TTL = get_config(ansible_cfg, 'paramiko_connection', 'max_ttl',
    'ANSIBLE_PARAMIKO_MAX_TTL', 60, integer=True
)

class Uncloseable(object):
    """Proxy that keeps ansible from closing a connection prematurely"""

    def __init__(self, ssh):
        self.__ssh = ssh

    def __getattr__(self, attr):
        return getattr(self.__ssh, attr)

    def close(self): pass

class ConnectionCache(TTLCache):
    """LRU/TTL cache for paramiko connections"""

    def get(self, conn):
        """Retrieve or create a connection"""
        key = (conn.host, conn.port, conn.user)
        ssh = TTLCache.get(self, key) or Uncloseable(conn._connect_uncached())
        self[key] = ssh     # Mark as recently used
        return ssh

    def put(self, conn):
        """Save a connection as recently used"""
        self[conn.host, conn.port, conn.user] = conn.ssh

SSH_CONNECTION_CACHE = ConnectionCache(CACHE_SIZE, TTL) 



class Connection(Base):

    def connect(self):
        self.ssh = SSH_CONNECTION_CACHE.get(self)
        return self

    def close(self):
        Base.close(self)

        # Don't re-write the hosts file after every command!
        for hostname, keys in self.ssh._host_keys.iteritems():
            for keytype, key in keys.iteritems():
                key._added_by_ansible_this_time = False

        # Mark connection as recently used
        SSH_CONNECTION_CACHE.put(self)








'''
try:
    NEW_STDIN = os.fdopen(os.dup(sys.stdin.fileno()))
except:
    NEW_STDIN = None

from multiprocessing.managers import SyncManager, BaseProxy

Connector = connection.Connector

def proxied_connector(dummy_runner):
    dummy_runner.process_lockfile = PROCESS_LOCKFILE
    dummy_runner.output_lockfile  = OUTPUT_LOCKFILE
    dummy_runner._new_stdin       = sys.stdin = NEW_STDIN
    return Connector(dummy_runner)

class ConnectionProxy(BaseProxy):
    _exposed_ = 'connect exec_command put_file fetch_file close __getattribute__'.split()

    def __getattr__(self, *args):
        return self._callmethod('__getattribute__', args)

    for meth in _exposed_:
        locals()[meth] = (lambda name: lambda s,*a: s._callmethod(name, a))(meth)

    del __getattribute__
    
    def exec_command(self, cmd, tmp_path, sudo_user=None, sudoable=False, executable='/bin/sh', in_data=None, su=None, su_user=None):
        return self._callmethod('exec_command', [cmd, tmp_path, sudo_user, sudoable, executable, in_data, su, su_user])

class ConnectionManager(SyncManager):
    """Manager for doing proxy interactions"""

connecting = dict(connect='Connection')
ConnectionManager.register('Connection', None, ConnectionProxy, method_to_typeid = connecting)
ConnectionManager.register('Connector', proxied_connector, method_to_typeid = connecting)

connection_manager = ConnectionManager()

runner_props = (
    'su su_pass sudo sudo_pass sudo_exe private_key_file module_name timeout'
).split()

class Data(object):
    def __init__(self, data):
        self.__dict__.update(data)

def MultiConnector(runner):
    runner_data = Data(
        (prop, getattr(runner, prop, None)) for prop in runner_props #if hasattr(runner, prop)
    )
    #connection_manager.start()
    #connection_manager.start = lambda: None     #  only start once
    return connection_manager.Connector(runner_data)

#connection.Connector = MultiConnector
from multiprocessing.util import log_to_stderr
#log_to_stderr(5)
#connection_manager.start()
'''















