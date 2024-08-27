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

import contextlib
import json
import pymysql
from six import StringIO
import sshtunnel

from oslo_log import log as logging
from tempest import config
from tempest.lib.common import ssh
from tempest.lib import exceptions as tempest_libexc

from whitebox_tempest_plugin.common import waiters
from whitebox_tempest_plugin import exceptions
from whitebox_tempest_plugin import hardware
from whitebox_tempest_plugin import utils as whitebox_utils

CONF = config.CONF
LOG = logging.getLogger(__name__)


class SSHClient(object):
    """A client to execute remote commands, based on tempest.lib.common.ssh."""

    def __init__(self, host):
        self.ssh_key = CONF.whitebox.ctlplane_ssh_private_key_path
        self.ssh_user = CONF.whitebox.ctlplane_ssh_username
        self.host_parameters = whitebox_utils.get_host_details(host)
        self.ctlplane_address = whitebox_utils.get_ctlplane_address(host)

    def execute(self, command, container_name=None, sudo=False):
        ssh_client = ssh.Client(self.ctlplane_address, self.ssh_user,
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

    def __init__(self, host):
        super(VirshXMLClient, self).__init__(host)
        service_dict = self.host_parameters.get('services', {}).get('libvirt')
        if service_dict is None:
            raise exceptions.MissingServiceSectionException(service='libvirt')
        self.container_name = service_dict.get('container_name')

    def dumpxml(self, domain):
        command = 'virsh dumpxml %s' % domain
        return self.execute(
            command, container_name=self.container_name, sudo=True)

    def capabilities(self):
        command = 'virsh capabilities'
        return self.execute(
            command, container_name=self.container_name, sudo=True)

    def domblklist(self, server_id):
        command = 'virsh domblklist %s' % server_id
        return self.execute(
            command, container_name=self.container_name, sudo=True)


class LogParserClient(SSHClient):
    """A client to parse logs"""

    def parse(self, query_string):
        log_query_command = CONF.whitebox_nova_compute.log_query_command
        if log_query_command == 'zgrep':
            command = 'sh -c "zgrep \'%s\' /var/log/nova/*"' % query_string
        else:
            command = 'journalctl -u devstack@n-cpu -g \'%s\'' % query_string
        return self.execute(command, container_name='nova_compute', sudo=True)


class QEMUImgClient(SSHClient):
    """A client to get QEMU image info in json format"""

    def __init__(self, ctlplane_address):
        super(QEMUImgClient, self).__init__(ctlplane_address)
        service_dict = self.host_parameters.get('services', {}).get('libvirt')
        if service_dict is None:
            raise exceptions.MissingServiceSectionException(service='libvirt')
        self.container_name = service_dict.get('container_name')

    def info(self, path):
        command = 'qemu-img info --output=json --force-share %s' % path
        output = self.execute(
            command, container_name=self.container_name, sudo=True)
        return json.loads(output)


class ServiceManager(SSHClient):
    """A client to manipulate services. Currently supported operations are:
    - configuration changes
    - restarting
    `crudini` is required in the environment.
    """

    def __init__(self, hostname, service):
        """Init the client.

        :param service: The service this manager is managing. Must exist as a
                        whitebox-<service> config section. For Nova services,
                        this must match the binary in the Nova os-services API.
        """
        super(ServiceManager, self).__init__(hostname)
        service_dict = self.host_parameters.get('services', {}).get(service)
        if service_dict is None:
            raise exceptions.MissingServiceSectionException(service=service)
        self.service = service
        self.config_path = service_dict.get('config_path')
        self.start_command = service_dict.get('start_command')
        self.stop_command = service_dict.get('stop_command')
        self.mask_command = service_dict.get('mask_command')
        self.unmask_command = service_dict.get('unmask_command')

    @contextlib.contextmanager
    def config_options(self, *opts):
        """Sets config options and restarts the service. Previous values for
        the options are saved before setting the new ones, and restored when
        the context manager exists.

        :param opts: a list of (section, option, value) tuples, each
                     representing a single config option
        """
        initial_values = []
        for section, option, value in opts:
            initial_values.append((section, option,
                                   self.get_conf_opt(section, option)))
            self.set_conf_opt(section, option, value)
        self.restart()
        try:
            yield
        finally:
            for section, option, value in initial_values:
                self.set_conf_opt(section, option, value)
            self.restart()

    @contextlib.contextmanager
    def stopped(self):
        """Stops this service to allow for "destructive" tests to execute with
        the service stopped. The service is started up again after the test
        code has run.
        """
        self.stop()
        try:
            yield
        finally:
            self.start()

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

    def start(self):
        if self.unmask_command:
            self.execute(self.unmask_command, sudo=True)
        self.execute(self.start_command, sudo=True)

    def stop(self):
        self.execute(self.stop_command, sudo=True)
        if self.unmask_command:
            self.execute(self.mask_command, sudo=True)

    def restart(self):
        self.stop()
        self.start()


class NovaServiceManager(ServiceManager):
    """A services manager for Nova services that uses Nova's service API to be
    smarter about stopping and restarting services.
    """

    def __init__(self, host, service, services_client):
        super(NovaServiceManager, self).__init__(host, service)
        self.services_client = services_client
        self.host = host
        self.status_field = 'state'

    def start(self):
        result = self.execute(self.start_command, sudo=True)
        waiters.wait_for_nova_service_state(self.services_client,
                                            self.host,
                                            self.service,
                                            self.status_field,
                                            'up')
        return result

    def stop(self):
        result = self.execute(self.stop_command, sudo=True)
        waiters.wait_for_nova_service_state(self.services_client,
                                            self.host,
                                            self.service,
                                            self.status_field,
                                            'down')
        return result

    def get_cpu_shared_set(self):
        shared_set = self.get_conf_opt('compute', 'cpu_shared_set')
        if not shared_set:
            return set()
        return hardware.parse_cpu_spec(shared_set)

    def get_cpu_dedicated_set(self):
        dedicated_set = self.get_conf_opt('compute', 'cpu_dedicated_set')
        dedicated_set = (dedicated_set if dedicated_set is not None else
                         self.get_conf_opt('DEFAULT', 'vcpu_pin_set'))
        if not dedicated_set:
            return set()
        return hardware.parse_cpu_spec(dedicated_set)


class VirtQEMUdManager(ServiceManager):
    """A services manager for Nova services that uses Nova's service API to be
    smarter about stopping and restarting services.
    """

    def __init__(self, host, service, services_client):
        super(VirtQEMUdManager, self).__init__(host, service)
        self.services_client = services_client
        self.binary = 'nova-compute'
        self.host = host
        self.status_field = 'status'

    def start(self):
        result = self.execute(self.start_command, sudo=True)
        waiters.wait_for_nova_service_state(self.services_client,
                                            self.host,
                                            self.binary,
                                            self.status_field,
                                            'enabled')
        return result

    def stop(self):
        result = self.execute(self.stop_command, sudo=True)
        waiters.wait_for_nova_service_state(self.services_client,
                                            self.host,
                                            self.binary,
                                            self.status_field,
                                            'disabled')
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


class SysFSClient(SSHClient):
    """A client for getting and setting sysfs values"""

    def get_sysfs_values(self, *paths):
        """Fetch multiple values in one shot

        :param paths: A list of paths relative to /sys
        :returns: A dict of path:value
        """
        paths = set('/sys/%s' % p for p in paths)
        result = self.execute('grep -H "" %s' % ' '.join(paths))
        results = {}
        for line in result.strip().split('\n'):
            path, value = line.split(':', 1)
            if path in results or path not in paths:
                raise Exception('Extra or multi-line value found in %s' % (
                    path))
            results[path[5:]] = value.strip()
        LOG.debug('sysfs results: %s', results)
        return results

    def get_sysfs_value(self, path):
        """Fetch a value

        :param path: A path relative to /sys
        :returns: The value
        """
        return self.get_sysfs_values(path)[path]

    def set_sysfs_value(self, path, value):
        self.execute('echo "%s" | sudo tee /sys/%s' % (value, path))


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
                    (CONF.whitebox_database.host,
                     CONF.whitebox_database.ssh_gateway_port),
                    ssh_username=self.ssh_user,
                    ssh_pkey=self.ssh_key,
                    allow_agent=False,
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
