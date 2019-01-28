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

import six.moves.configparser as configparser
from six import StringIO

from oslo_log import log as logging
from tempest import config
from tempest.lib.common import ssh

CONF = config.CONF
LOG = logging.getLogger(__name__)


class SSHClient(object):
    """A client to execute remote commands, based on tempest.lib.common.ssh."""

    def __init__(self, hostname):
        self.ssh_key = CONF.whitebox.ctlplane_ssh_private_key_path
        self.ssh_user = CONF.whitebox.ctlplane_ssh_username
        self.host = hostname

    def execute(self, command, container_name=None, sudo=False):
        ssh_client = ssh.Client(self.host, self.ssh_user,
                                key_filename=self.ssh_key)
        if (CONF.whitebox.containers and container_name):
            executable = CONF.whitebox.container_runtime
            command = 'sudo %s exec -u root %s %s' % (executable,
                                                      container_name, command)
        elif sudo:
            command = 'sudo %s' % command
        LOG.debug("Executing %s", command)
        return ssh_client.exec_command(command)


class VirshXMLClient(SSHClient):
    """A client to obtain libvirt XML from a remote host."""

    def dumpxml(self, domain):
        command = 'virsh dumpxml %s' % domain
        return self.execute(command, container_name='nova_libvirt', sudo=True)

    def capabilities(self):
        command = 'virsh capabilities'
        return self.execute(command, container_name='nova_libvirt', sudo=True)


class NovaConfigClient(SSHClient):
    """A client to obtain config values from nova.conf."""

    def _read_nova_conf(self):
        command = 'cat /etc/nova/nova.conf'
        return self.execute(command, container_name='nova_libvirt', sudo=True)

    def getopt(self, section, option):
        config = configparser.ConfigParser()
        config.readfp(StringIO(self._read_nova_conf()))
        return config.get(section, option)
