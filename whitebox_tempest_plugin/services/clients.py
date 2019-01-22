# Copyright 2016
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
from contextlib import contextmanager
try:
    from shlex import quote
except ImportError:
    from pipes import quote

from tempest import config
from tempest.lib.common import ssh

CONF = config.CONF


class SSHClient(object):
    """A client to execute remote commands, based on tempest.lib.common.ssh."""

    _prefix_command = '/bin/bash -c'

    def __init__(self):
        self.ssh_key = CONF.whitebox.ctlplane_ssh_private_key_path
        self.ssh_user = CONF.whitebox.ctlplane_ssh_username

    def execute(self, hostname=None, cmd=None):
        ssh_client = ssh.Client(hostname, self.ssh_user,
                                key_filename=self.ssh_key)
        cmd = self._prefix_command + ' ' + quote(cmd)
        return ssh_client.exec_command(cmd)

    @contextmanager
    def prefix_command(self, prefix_command=None):
        saved_prefix = self._prefix_command
        self._prefix_command = prefix_command
        yield self
        self._prefix_command = saved_prefix

    @contextmanager
    def sudo_command(self, user=None):
        if user is not None:
            user_arg = '-u {}'.format(user)
        else:
            user_arg = ''
        cmd = 'sudo {} /bin/bash -c'.format(user_arg)
        with self.prefix_command(cmd) as p:
            yield p

    @contextmanager
    def container_command(self, container_name, user=None):
        if user is not None:
            user_arg = '-u {}'.format(user)
        else:
            user_arg = ''
        cmd = 'sudo docker exec {} -i {} /bin/bash -c'.format(
              user_arg, container_name)
        with self.prefix_command(cmd) as p:
            yield p


class VirshXMLClient(SSHClient):
    """A client to obtain libvirt XML from a remote host."""

    def __init__(self, hostname=None):
        super(VirshXMLClient, self).__init__()
        self.host = hostname

    def dumpxml(self, domain):
        if CONF.whitebox.containers:
            ctx = self.container_command('nova_compute', user='root')
        else:
            ctx = self.sudo_command()
        with ctx:
            command = "virsh dumpxml {}".format(domain)
            return self.execute(self.host, command)

    def capabilities(self):
        if CONF.whitebox.containers:
            ctx = self.container_command('nova_compute', user='root')
        else:
            ctx = self.sudo_command()
        with ctx:
            command = "virsh capabilities"
            return self.execute(self.host, command)
