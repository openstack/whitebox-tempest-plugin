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

import time

import contextlib
import pymysql
from six import StringIO
import sshtunnel

from oslo_log import log as logging
from tempest import config
from tempest.lib.common import ssh
from tempest.lib import exceptions as tempest_libexc

from whitebox_tempest_plugin import exceptions

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
        LOG.debug('command=%s', command)
        result = ssh_client.exec_command(command)
        LOG.debug('result=%s', result)
        return result


class VirshXMLClient(SSHClient):
    """A client to obtain libvirt XML from a remote host."""

    def dumpxml(self, domain):
        command = 'virsh dumpxml %s' % domain
        return self.execute(command, container_name='nova_libvirt', sudo=True)

    def capabilities(self):
        command = 'virsh capabilities'
        return self.execute(command, container_name='nova_libvirt', sudo=True)


class ServiceManager(SSHClient):
    """A client to manipulate services. Currently supported operations are:
    - configuration changes
    - restarting
    `crudini` is required in the environment.
    """

    def __init__(self, hostname, service):
        """Init the client.

        :param service: The service this manager is managing. Must exist as a
                        whitebox-<service> config section.
        """
        super(ServiceManager, self).__init__(hostname)
        try:
            conf = getattr(CONF, 'whitebox-%s' % service)
        except AttributeError:
            raise exceptions.MissingServiceSectionException(service=service)
        self.config_path = conf.config_path
        self.restart_command = conf.restart_command

    @contextlib.contextmanager
    def config_option(self, section, option, value):
        initial_value = self.get_conf_opt(section, option)
        self.set_conf_opt(section, option, value)
        self.restart()
        try:
            yield
        finally:
            self.set_conf_opt(section, option, initial_value)
            self.restart()

    def get_conf_opt(self, section, option):
        command = 'crudini --get %s %s %s' % (self.config_path, section,
                                              option)
        # NOTE(artom) `crudini` will return 1 when attempting to get an
        # inexisting option or section. This becomes an SSHExecCommandFailed
        # exception (see exec_command() docstring in
        # tempest/lib/common/ssh.py).
        try:
            value = self.execute(command, container_name=None, sudo=True)
            return value.strip()
        except tempest_libexc.SSHExecCommandFailed as e:
            # NOTE(artom) We could also get an SSHExecCommandFailed exception
            # for reasons other than the option or section not existing. Only
            # return None when we're sure `crudini` told us "Parameter not
            # found", otherwise re-raise e.
            if 'not found' in str(e):
                return None
            else:
                raise e

    def set_conf_opt(self, section, option, value):
        """Sets option=value in [section]. If value is None, the effect is the
        same as del_conf_opt(option).
        """
        if value is None:
            command = 'crudini --del %s %s %s' % (self.config_path, section,
                                                  option)
        else:
            command = 'crudini --set %s %s %s %s' % (self.config_path, section,
                                                     option, value)
        return self.execute(command, container_name=None, sudo=True)

    def del_conf_opt(self, section, option):
        command = 'crudini --del %s %s %s' % (self.config_path, section,
                                              option)
        return self.execute(command, container_name=None, sudo=True)

    def restart(self):
        result = self.execute(self.restart_command, sudo=True)
        # TODO(artom) We need to make sure the service has actually started
        # before proceeding. Otherwise, in the case of nova-compute for
        # example, we might go on to boot a server, only for the service to
        # restart in the middle of the boot process. There is no
        # straightforward and uniform way to wait for a service to actually be
        # running after a restart, so we just sleep 5 seconds. This is ugly
        # hax, and we need to find something better.
        time.sleep(5)
        return result


class NUMAClient(SSHClient):
    """A client to get host NUMA information. `numactl` needs to be installed
    in the environment or container(s).
    """

    def get_host_topology(self):
        """Returns the host topology as a dict.

        :return nodes: A dict of CPUs in each host NUMA node, keyed by host
                       node number, for example: {0: [1, 2],
                                                  1: [3, 4]}
        """
        nodes = {}
        numactl = self.execute('numactl -H', sudo=True)
        for line in StringIO(numactl).readlines():
            if 'node' in line and 'cpus' in line:
                cpus = [int(cpu) for cpu in line.split(':')[1].split()]
                node = int(line.split()[1])
                nodes[node] = cpus
        return nodes

    def get_num_cpus(self):
        nodes = self.get_host_topology()
        return sum([len(cpus) for cpus in nodes.values()])

    def get_pagesize(self):
        proc_meminfo = self.execute('cat /proc/meminfo')
        for line in StringIO(proc_meminfo).readlines():
            if line.startswith('Hugepagesize'):
                return int(line.split(':')[1].split()[0])

    def get_hugepages(self):
        """Returns a nested dict of number of total and free pages, keyed by
        NUMA node. For example:

        {0: {'total': 2000, 'free': 2000},
         1: {'total': 2000, 'free': 0}}
        """
        pages = {}
        for node in self.get_host_topology():
            meminfo = self.execute(
                'cat /sys/devices/system/node/node%d/meminfo' % node)
            for line in StringIO(meminfo).readlines():
                if 'HugePages_Total' in line:
                    total = int(line.split(':')[1].lstrip())
                if 'HugePages_Free' in line:
                    free = int(line.split(':')[1].lstrip())
            pages[node] = {'total': total, 'free': free}
        return pages


class DatabaseClient(object):

    def __init__(self):
        self.ssh_key = CONF.whitebox.ctlplane_ssh_private_key_path
        self.ssh_user = CONF.whitebox.ctlplane_ssh_username

    @contextlib.contextmanager
    def cursor(self, database_name, commit=False):
        """Yields a PyMySQL cursor, tunneling to the internal subnet if
        necessary.
        """
        tunnel_local_bind_host = '127.42.42.42'
        tunnel_local_bind_port = 4242
        if CONF.whitebox_database.internal_ip:
            with sshtunnel.SSHTunnelForwarder(
                    (CONF.whitebox_database.host, 3306),
                    ssh_username=self.ssh_user,
                    ssh_pkey=self.ssh_key,
                    remote_bind_address=(CONF.whitebox_database.internal_ip,
                                         3306),
                    local_bind_address=(tunnel_local_bind_host,
                                        tunnel_local_bind_port)):
                conn = pymysql.connect(
                    host=tunnel_local_bind_host, port=tunnel_local_bind_port,
                    user=CONF.whitebox_database.user,
                    password=CONF.whitebox_database.password,
                    database=database_name,
                    cursorclass=pymysql.cursors.DictCursor)
                with conn.cursor() as c:
                    try:
                        yield c
                    finally:
                        if commit:
                            conn.commit()
                        conn.close()
        else:
            conn = pymysql.connect(
                host=CONF.whitebox_database.host, port=3306,
                user=CONF.whitebox_database.user,
                password=CONF.whitebox_database.password,
                database=database_name,
                cursorclass=pymysql.cursors.DictCursor)
            with conn.cursor() as c:
                try:
                    yield c
                finally:
                    if commit:
                        conn.commit()
                    conn.close()
