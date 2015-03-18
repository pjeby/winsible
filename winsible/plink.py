import os, re, subprocess, ansible.utils, ansible.errors, ansible.constants as C
from fcntl import fcntl, F_SETFL, F_GETFL
from select import select
from ansible.callbacks import vvv
from ansible.errors import AnsibleError
from ansible.runner.connection_plugins.ssh import Connection as SSHBase
from multiprocessing.util import Finalize

EXE_PATH = os.path.dirname(
    os.path.realpath(__file__ if __file__.endswith('.py') else __file__[:-1])
)

import atexit
conn_cache = {}

def reap(proc):
    try:
        proc.kill()
    except OSError, e:
        if e.errno == 3:
            return
        raise
    proc.communicate()

def cleanup_cached_connections():
    while conn_cache:
        (cmd, (proc, err, fail)) = conn_cache.popitem()
        if proc.poll() is None:
            reap(proc)
Finalize(None, cleanup_cached_connections, exitpriority=-1)

def shout(cmd):
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    output, unused_err = process.communicate()
    if process.poll():
        raise subprocess.CalledProcessError(retcode, cmd[0], output=output)
    return output

def cygpath(path):
    return shout(['cygpath','-wa',path])[:-1]

fingerprints = {}

FAILED = re.compile(r'Access denied|FATAL ERROR|Fatal: ').search
SUCCESS = re.compile(r'Access granted|Reusing a shared connection').search

def get_ssh_key(hostinfo, path=None):
    """Look up a key fingerprint from a single known_hosts file"""
    cmd = ['ssh-keygen', '-F', hostinfo, '-l']
    if path:
        if not os.path.exists(path):
            return None
        cmd.extend(['-f', path])
    for line in shout(cmd).splitlines():
        if line.startswith('#'): continue
        fields = line.split()
        if len(fields)>2:
            return fields[1]

def get_fingerprint(host, port, default=lambda h: None):
    """Find a cached key fingerprint for a given host/port"""
    if port != 22:
        host = '[%s]:%d' % (host, port)
    try:
        return fingerprints[host]
    except KeyError:
        f = fingerprints[host] = get_ssh_key(host) or \
            get_ssh_key(host, "/etc/ssh/ssh_known_hosts") or \
            get_ssh_key(host, "/etc/ssh/ssh_known_hosts2") or \
            default(host)
        return f

# Make sure executables are executable
for exe in ['plink', 'putty', 'pscp', 'psftp']:
    try:
        os.chmod(os.path.join(EXE_PATH, exe+'.exe'), 0555)
    except:
        pass




class Connection(SSHBase):

    def __init__(self, *args, **kwargs):
        SSHBase.__init__(self, *args, **kwargs)
        self.port = (C.DEFAULT_REMOTE_PORT or 22) if self.port is None else self.port
        self._server_process = None

    def connect(self):
        # This really just sets up options, it doesn't really connect anything

        self.common_args = args = ['-load', 'ansible_cygwin_plink', '-batch']
        add = lambda *a: args.extend(a)

        if self.password:
            add('-pw', self.password)

        fingerprint = get_fingerprint(self.host, self.port, self.fetch_hostkey)
        if fingerprint:
            add('-hostkey', fingerprint)

        if self.port !=22:
            add("-P", str(self.port))

        keyfile = self.private_key_file or self.runner.private_key_file
        if keyfile:
            add("-i", cygpath(os.path.expanduser(keyfile)))

        if ansible.utils.VERBOSITY > 3:
            add("-v")

        if self.ipv6:
            add('-6')

        add("-l", self.user)
        return self

    def not_in_host_file(self, host):
        return not get_fingerprint(host, self.port)



    def fetch_hostkey(self, hkey):
        from ansible.runner.connection_plugins.paramiko_ssh import Connection
        from hashlib import md5
        import re
        paramiko = Connection(
            self.runner, self.host, self.port, self.user, self.password,
            self.private_key_file
        )
        paramiko.connect()
        try:
            for ktyp, key in paramiko.ssh._host_keys.get(hkey, {}).iteritems():
                return re.sub('(..)(?!$)', '\\1:', md5(key.asbytes()).hexdigest())
        finally:
            paramiko.close()

    def _base_command(self):
        ssh_cmd = self._password_cmd()
        ssh_cmd.extend([EXE_PATH+"/plink", "-C"])
        ssh_cmd.extend(self.common_args)
        ssh_cmd.append(self.host)
        return ssh_cmd

    def _run(self, cmd, indata):
        if cmd[0]=='ssh':
            remote_cmd = cmd.pop()
            cmd = self._base_command()
            if not indata:
                cmd.append("-t")
            cmd.append(remote_cmd)
        elif cmd[0] in ('sftp', 'scp'):
            if cmd[0]=='scp' and not ansible.utils.VERBOSITY > 3:
                cmd[1:1] = ['-q']
            if cmd[0]=='sftp' and indata:
                indata = indata[:-1]+'\r\n'
            cmd[0] = EXE_PATH+"/p"+cmd[0]
        #print "EXEC", ' '.join(cmd)
        return SSHBase._run(self, cmd, indata)




    def connect_master(self):
        cmd = tuple(self._base_command()+['-v', '-N'])
        try:
            return conn_cache[cmd]
        except KeyError:
            #print "CONNECTION UP:", ' '.join(cmd)
            vvv("ESTABLISH PLINK FOR USER: %s" % self.user, host=self.host)
            (proc, stdin) = SSHBase._run(self, cmd, True)
            err_output, fail = self._wait_for_master(proc)
            if proc.poll() is None:
                conn_cache[cmd] = proc, err_output, fail
        return proc, err_output, fail

    def exec_command(self, cmd, *args, **kw):
        proc, err_output, fail = self.connect_master()
        ret = proc.poll()
        if ret is not None:
            return (255 if fail else ret), '', err_output, err_output
        return SSHBase.exec_command(self, cmd, *args, **kw)

    def _wait_for_master(self, proc):
        fd = proc.stderr
        fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | os.O_NONBLOCK)
        output = ''
        while True:
            r, w, e = select([fd], [], [], self.runner.timeout)
            if fd in r:
                data = os.read(fd.fileno(), 5000)
                output += data
                if not data or FAILED(output):
                    o, e = proc.communicate()
                    return output + e, True
                elif SUCCESS(output):
                    return output, False
            else:
                reap(proc)
                return output+'\nTimeout during master connection\n', True

    def _password_cmd(self):
        return []

    def _send_password(self):
        return

    def put_file(self, in_path, out_path):
        cpath = cygpath(in_path)
        cpath = cpath.replace('\\','/')
        orig_exists = os.path.exists
        def exists(p):
            if p is cpath:   # only match if it's passed from put_file
                return orig_exists(in_path)
            else:
                return orig_exists(p)
        os.path.exists = exists
        try:
            return SSHBase.put_file(self, cpath, out_path)
        finally:
            os.path.exists = orig_exists

    def fetch_file(self, in_path, out_path):
        out_path = cygpath(out_path)    # this uses Popen, so do it first

        original_popen = subprocess.Popen

        def dummy_popen(cmd, *args, **kw):
            subprocess.Popen = original_popen
            return self._run(cmd, 'n/a')[0]

        try:
            subprocess.Popen = dummy_popen
            return SSHBase.fetch_file(self, in_path, out_path)
        finally:
            subprocess.Popen = original_popen









