# Copyright 2023 Red Hat
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

from tempest.common import waiters
from whitebox_tempest_plugin.api.compute import base
from whitebox_tempest_plugin import hardware
from whitebox_tempest_plugin.services import clients


class TestCPUStateMgmt(base.BaseWhiteboxComputeTest):
    """Test Nova's CPU state management feature, ensuring that CPUs are
    onlined and offlined at the expected times.
    """
    min_microversion = '2.95'

    @classmethod
    def skip_checks(cls):
        super(TestCPUStateMgmt, cls).skip_checks()

    def setUp(self):
        super(TestCPUStateMgmt, self).setUp()
        self.flavor = self.create_flavor(
            vcpus=1,
            extra_specs={'hw:cpu_policy': 'dedicated'})

    def _assert_cpus_initial_state(self, host, shared_cpus, dedicated_cpus,
                                   sysfsclient):
        """Assert that nova-compute disabled dedicated CPUs on startup"""
        # In case we didn't have a full set specified, at least make sure that
        # our shared CPUs are in the subset of online CPUs (i.e. we didn't
        # offline any of the shared ones).
        online = sysfsclient.get_sysfs_value('devices/system/cpu/online')
        self.assertTrue(shared_cpus.issubset(hardware.parse_cpu_spec(online)))

        # All our dedicated CPUs should be offlined at service startup.
        offline = sysfsclient.get_sysfs_value('devices/system/cpu/offline')
        self.assertEqual(dedicated_cpus, hardware.parse_cpu_spec(offline))

    def _assert_cpu_onlined_guest(self, host, dedicated_cpus, sysfsclient):
        offline_before = hardware.parse_cpu_spec(
            sysfsclient.get_sysfs_value('devices/system/cpu/offline'))

        server = self.create_test_server(clients=self.os_admin,
                                         flavor=self.flavor['id'],
                                         host=host,
                                         wait_until='ACTIVE')

        # Our test server should have caused nova to online our dedicated CPU
        offline_after = hardware.parse_cpu_spec(
            sysfsclient.get_sysfs_value('devices/system/cpu/offline'))
        self.assertLess(offline_after, offline_before)

        self.os_admin.servers_client.delete_server(server['id'])
        waiters.wait_for_server_termination(self.os_admin.servers_client,
                                            server['id'])

        # Once it is gone, the dedicated CPU should be offline again
        offline = hardware.parse_cpu_spec(
            sysfsclient.get_sysfs_value('devices/system/cpu/offline'))
        self.assertEqual(offline_before, offline)

    def online_test_cpu(self, cpus, sysfsclient):
        """Put our test CPUs back to online status"""
        for cpu in cpus:
            sysfsclient.set_sysfs_value(
                'devices/system/cpu/cpu%i/online' % cpu, '1')

    def test_cpu_state(self):
        host = self.list_compute_hosts()[0]
        sysfsclient = clients.SysFSClient(host)

        # Check that we don't have any offline CPUs to start with
        offline = sysfsclient.get_sysfs_value('devices/system/cpu/offline')
        self.assertEqual("", offline,
                         'System has offlined CPUs unexpectedly!')

        sm = clients.NovaServiceManager(host, 'nova-compute',
                                        self.os_admin.services_client)
        dedicated_cpus = sm.get_cpu_dedicated_set()
        shared_cpus = sm.get_cpu_shared_set()
        opts = [('libvirt', 'cpu_power_management', 'True'),
                ('libvirt', 'cpu_power_management_strategy', 'cpu_state')]

        if len(dedicated_cpus) < 2:
            raise self.skipException('Multiple dedicated CPUs required')

        # Nova will not online the CPUs it manages on shutdown, so we need
        # to re-online it before we finish here to leave the system as we
        # found it
        self.addCleanup(self.online_test_cpu, dedicated_cpus, sysfsclient)

        with sm.config_options(*tuple(opts)):
            self._assert_cpus_initial_state(host, shared_cpus, dedicated_cpus,
                                            sysfsclient)
            self._assert_cpu_onlined_guest(host, dedicated_cpus, sysfsclient)
