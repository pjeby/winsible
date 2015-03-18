winsible - a faster Ansible (especially on Cygwin!)
===================================================

winsible is an experimental wrapper for `ansible-playbook` that enhances its multiprocessing and connection persistence, for platforms where OpenSSH can't transparently do its own connection pooling (such as EL5 and Cygwin).

And unlike Ansible's own `accelerate` or `fireball` modes, it doesn't require installing anything on the target computers: you just install it on the machine where you run your playbooks, and use `winsible-playbook` instead of `ansible-playbook`.  


Installation and Use
--------------------

Install winsible with `pip install winsible` or `easy_install winsible`.  If you don't have these commands on your system, try installing your platform's `python-setuptools` package.  (Also, if you're not on Cygwin, you'll need to be root or use sudo, or install them to a virtualenv.)

If you have a current version of `gevent` on your system (1.0.1 or better), winsible can use it to eliminate forking altogether and run plays against all hosts with a single process.  But this is a relatively small performance boost compared to connection pooling (and is somewhat experimental), so it's optional and has to be explicitly activated.  If you want to try it, you can install gevent with `sudo pip install "gevent>=1.0.1"` or `sudo easy_install "gevent>=1.0.1"`.  (Then enable it with `ANSIBLE_PROCESS_MODE=gevent` in the environment or `process_mode=gevent` in your ansible.cfg.) 

Last, but not least, make sure you've got an `ssh` command: if you're on Cygwin, install the `openssh` package, or on Linux distros it might be in an `openssh-clients` package.

Once you have these things installed, you're ready to use `winsible-playbook` in place of `ansible-playbook`, to enjoy faster playbook runs.   (A `winsible` script is also included, for completeness, but it doesn't provide much in the way of acceleration.  It does, however, tweak ansible's defaults so that the `ssh` transport will work correctly on Cygwin.)

Note: At the moment, this project as a whole is still pretty alpha.  (Especially the `gevent` mode.)  In general, winsible has *not* been run on a very wide variety of hosts, modules, or plugins, so experience reports are welcome.  If something breaks, or if it doesn't improve performance in your use case, please file an issue on the github page with some details so I can have a look at it.  Thanks!


How It Works
------------

### Processing Modes

The `winsible` and `winsible-playbook` scripts invoke ansible with a preselected "processing mode", which can be one of `fork`, `gevent`, `pool`, or `smart`.  This mode can be configured using the `process_mode` variable in the `defaults` section of `ansible.cfg`, or via the  `ANSIBLE_PROCESS_MODE` environment variable.  (The default mode is `smart`, which will use `pool` if running a playbook, and `fork` otherwise.)
  
The `fork` mode is Ansible's standard way of multiprocessing, which opens connections in separate processes.  This works fine if you're running a single task or have a `ControlPersist`-capable ssh, but is terribly inefficient otherwise.  

So the `gevent` mode patches Ansible to use a gevent task pool instead of separate processes, so that host connections can be shared (and reused) within a single process.  The `pool` mode works similarly, but uses a `multiprocessing.SyncManager` to create a dedicated pool process, which the Ansible-forked task workers talk to via IPC.  It can be less efficient than the `gevent` mode (due to inter-process communication overhead and locking) but it's a lot less invasive and thus more likely to be compatible with existing plugins, transports, and modules that do any of their own I/O (and whose behavior might thus be affected by gevent's monkeypatching).


### Connection Pooling and Transports

While the `gevent` mode will let an entire playbook run against multiple hosts in parallel without forking the main process even once (instead of once per host per task), the primary performance benefit of winsible comes from its ability to pool SSH connections and reuse them over the lifetime of a playbook run.

Both the `gevent` and `pool` modes support this connection pooling; they just differ as to which process the connection pool lives in.  (In `gevent`, connections are pooled in the main process, while the `pool` mode creates a dedicated `multiprocessing.Manager` process that holds the pool.)  Even Ansible's standard `fork` mode can benefit from connection pooling, in the case of a playbook being run against a single host, or with the Ansible `forks` option set to 1, since such tasks are run in a single process.

In order to take advantage of this feature, however, you have to use a connection type that supports pooling.  Unfortunately, Ansible's built-in transports don't do this, unless you're using ssh on a version and platform that supports ControlPersist.  (Something which is probably never going to be available on Cygwin.) 

So winsible includes three connection-pooling transports: `paramiko_pool` (cross-platform) and `plink` (Cygwin-specific).  These transports are specifically designed to work with winsible's `pool` and `gevent` modes, but they can also speed up Ansible's standard `fork` mode for single-host plays or with `forks=1`.  (On Cygwin, the `plink` transport is also faster than Paramiko, due to being written in C and using the Windows API directly rather than via Cygwin translation.  But it's not as fast as native `ssh` if you're running a single task rather than a playbook.) 

Whenever you use the `gevent` or `pool` modes, winsible remaps Ansible's `ssh` and `paramiko` transports to use its own replacements.  If you need to override this for some reason (e.g. debugging), Ansible's built-in transports can be accessed using the names `_ssh` and `_paramiko` in the appropriate config files, command-line options, environment variables, or playbook settings.


LICENSES
--------

The included `.exe` files (for the Cygwin-specific `plink` transport) are from [Jakub Kotrla's registry-free version of PuTTY](http://jakub.kotrla.net/putty/); see the PUTTY_LICENSE file in the `winsible/` directory for the full credits.  (Basically, though, it's MIT-licensed, and copyright 1997-2015 Simon Tatham, with a long list of additional contributors.)

The rest of Winsible is copyright 2015 PJ Eby, and MIT-licensed as follows:   

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT OWNERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE. 
