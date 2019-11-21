# Copyright 2018 Red Hat
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

import mock
import tempfile
import textwrap

from oslo_concurrency import processutils
from tempest.lib import exceptions as tempest_libexc

from whitebox_tempest_plugin import exceptions
from whitebox_tempest_plugin.services import clients
from whitebox_tempest_plugin.tests import base


class SSHClientTestCase(base.WhiteboxPluginTestCase):

    def setUp(self):
        super(SSHClientTestCase, self).setUp()
        self.client = clients.SSHClient('fake-host')

    @mock.patch('tempest.lib.common.ssh.Client.exec_command')
    def test_execute(self, mock_exec):
        # Test "vanilla" execute()
        self.client.execute('fake command')
        mock_exec.assert_called_with('fake command')
        mock_exec.reset_mock()

        # Test sudo without containers
        self.client.execute('fake command', sudo=True)
        mock_exec.assert_called_with('sudo fake command')
        mock_exec.reset_mock()

        # Test that container_name is ignored unless containers is set in CONF
        self.client.execute('fake command', container_name='fake-container')
        mock_exec.assert_called_with('fake command')
        mock_exec.reset_mock()

        # Test that containers in CONF is ignored unless container_name is
        # passed
        self.flags(containers=True, group='whitebox')
        self.client.execute('fake command')
        mock_exec.assert_called_with('fake command')
        mock_exec.reset_mock()

        # Test that container_name is used when containers is set in CONF
        self.client.execute('fake command', container_name='fake-container')
        mock_exec.assert_called_with('sudo docker exec -u root '
                                     'fake-container fake command')
        mock_exec.reset_mock()

        # Test that container_runtime is read from CONF if set
        self.flags(container_runtime='podman', group='whitebox')
        self.client.execute('fake command', container_name='fake-container')
        mock_exec.assert_called_with('sudo podman exec -u root '
                                     'fake-container fake command')
        mock_exec.reset_mock()


class ServiceManagerTestCase(base.WhiteboxPluginTestCase):

    def test_supported_services(self):
        """As more services becomes supported, add them here to make sure their
        config_path has been properly added to CONF.
        """
        clients.ServiceManager('fake-host', 'nova-compute')

    def test_missing_service(self):
        self.assertRaises(
            exceptions.MissingServiceSectionException,
            clients.ServiceManager, 'fake-host', 'missing-service')

    def test_crudini(self):
        """This attempts a full end-to-end test by actually executing crudini
        against a real file were possible, and by faking its output where not
        possible. Because SSHClient needs a real host to SSH to,
        we stub out its execute() method with 3 different variants.
        """
        def local_exec(command, **kwargs):
            """Execute the command locally instead of remotely"""
            out, err = processutils.execute(*command.split())
            return out

        def fake_exec_not_found(command, **kwargs):
            """Don't execute anything and immitate what would happen if crudini was
            executed on a remote host with an option or section that doesn't
            exist in the INI file.
            """
            raise tempest_libexc.SSHExecCommandFailed(
                command=command, exit_status=1, stderr='not found',
                stdout='')

        def fake_exec_other_failure(command, **kwargs):
            """Don't execute anything and immitate what would happen if crudini was
            executed on a remote host with some other failure, for example an
            inexesting INI file.
            """
            raise tempest_libexc.SSHExecCommandFailed(
                command=command, exit_status=1,
                stderr='No such file or directory', stdout='')

        with tempfile.NamedTemporaryFile(mode='r+') as f:
            f.write(textwrap.dedent("""
                [section]
                option = value"""))
            f.flush()
            self.flags(config_path=f.name, group='whitebox-nova-compute')
            service = clients.ServiceManager('fake-host', 'nova-compute')
            service.execute = local_exec
            # Test the config_option context manager
            with mock.patch.object(service, 'restart') as mock_restart:
                with service.config_option('section', 'option', 'new-value'):
                    self.assertEqual('new-value',
                                     service.get_conf_opt('section', 'option'))
                self.assertEqual(2, mock_restart.call_count)
            self.assertEqual('value',
                             service.get_conf_opt('section', 'option'))
            # Test setting an option then getting it
            service.set_conf_opt('section', 'foo', 'bar')
            self.assertEqual('bar', service.get_conf_opt('section', 'foo'))
            # Test deleting an option by setting it to None
            service.set_conf_opt('section', 'option', None)
            self.assertNotIn('option', f.read())
            # Test deleting an option
            service.execute = fake_exec_not_found
            self.assertIsNone(service.get_conf_opt('section', 'option'))
            # Test handling other failures
            service.execute = fake_exec_other_failure
            self.assertRaises(tempest_libexc.SSHExecCommandFailed,
                              service.get_conf_opt, 'section', 'foo')

    def test_restart(self):
        self.flags(restart_command='fake restart command',
                   group='whitebox-nova-compute')
        service = clients.ServiceManager('fake-host', 'nova-compute')
        with mock.patch.object(service, 'execute') as mock_exec:
            service.restart()
            mock_exec.assert_called_with('fake restart command', sudo=True)

    def test_stop(self):
        self.flags(stop_command='fake stop command',
                   group='whitebox-nova-libvirt')
        service = clients.ServiceManager('fake-host', 'nova-libvirt')
        with mock.patch.object(service, 'execute') as mock_exec:
            service.stop()
            mock_exec.assert_called_with('fake stop command', sudo=True)


class NUMAClientTestCase(base.WhiteboxPluginTestCase):

    fake_numactl_output = textwrap.dedent("""
        available: 2 nodes (0-1)
        node 0 cpus: 0 1 2
        node 0 size: 7793 MB
        node 0 free: 1640 MB
        node 1 cpus: 3 4
        node 1 size: 7875 MB
        node 1 free: 4059 MB
        node distances:
        node   0   1
          0:  10  20
          1:  20  10""")

    fake_proc_meminfo = textwrap.dedent("""
        MemTotal:       16035320 kB
        MemFree:          481884 kB
        MemAvailable:    2489036 kB
        Buffers:            4128 kB
        Cached:          2246912 kB
        SwapCached:          572 kB
        Active:          5348564 kB
        Inactive:        1375316 kB
        Active(anon):    4165752 kB
        Inactive(anon):   347028 kB
        Active(file):    1182812 kB
        Inactive(file):  1028288 kB
        Unevictable:      112816 kB
        Mlocked:          112816 kB
        SwapTotal:        629756 kB
        SwapFree:         625648 kB
        Dirty:                68 kB
        Writeback:             0 kB
        AnonPages:       4429328 kB
        Mapped:           329536 kB
        Shmem:              4052 kB
        KReclaimable:     165572 kB
        Slab:             350468 kB
        SReclaimable:     165572 kB
        SUnreclaim:       184896 kB
        KernelStack:       13616 kB
        PageTables:        26564 kB
        NFS_Unstable:          0 kB
        Bounce:                0 kB
        WritebackTmp:          0 kB
        CommitLimit:     4551416 kB
        Committed_AS:   10445028 kB
        VmallocTotal:   34359738367 kB
        VmallocUsed:           0 kB
        VmallocChunk:          0 kB
        Percpu:             6600 kB
        HardwareCorrupted:     0 kB
        AnonHugePages:         0 kB
        ShmemHugePages:        0 kB
        ShmemPmdMapped:        0 kB
        CmaTotal:              0 kB
        CmaFree:               0 kB
        HugePages_Total:    4000
        HugePages_Free:     4000
        HugePages_Rsvd:        0
        HugePages_Surp:        0
        Hugepagesize:       2048 kB
        Hugetlb:         8192000 kB
        DirectMap4k:      391032 kB
        DirectMap2M:    10749952 kB
        DirectMap1G:     5242880 kB""")

    fake_node0_meminfo = textwrap.dedent("""
        Node 0 MemTotal:        7971444 kB
        Node 0 MemFree:          138612 kB
        Node 0 MemUsed:         7832832 kB
        Node 0 Active:          2832660 kB
        Node 0 Inactive:         586824 kB
        Node 0 Active(anon):    2538412 kB
        Node 0 Inactive(anon):   326172 kB
        Node 0 Active(file):     294248 kB
        Node 0 Inactive(file):   260652 kB
        Node 0 Unevictable:      105392 kB
        Node 0 Mlocked:          105392 kB
        Node 0 Dirty:               136 kB
        Node 0 Writeback:             0 kB
        Node 0 FilePages:        589864 kB
        Node 0 Mapped:           126096 kB
        Node 0 AnonPages:       2855072 kB
        Node 0 Shmem:              2024 kB
        Node 0 KernelStack:        3720 kB
        Node 0 PageTables:        13308 kB
        Node 0 NFS_Unstable:          0 kB
        Node 0 Bounce:                0 kB
        Node 0 WritebackTmp:          0 kB
        Node 0 KReclaimable:      54788 kB
        Node 0 Slab:             142752 kB
        Node 0 SReclaimable:      54788 kB
        Node 0 SUnreclaim:        87964 kB
        Node 0 AnonHugePages:         0 kB
        Node 0 ShmemHugePages:        0 kB
        Node 0 ShmemPmdMapped:        0 kB
        Node 0 HugePages_Total:  4000
        Node 0 HugePages_Free:   3000
        Node 0 HugePages_Surp:      0""")

    fake_node1_meminfo = textwrap.dedent("""
        Node 1 MemTotal:        8063876 kB
        Node 1 MemFree:          323536 kB
        Node 1 MemUsed:         7740340 kB
        Node 1 Active:          2520684 kB
        Node 1 Inactive:         795228 kB
        Node 1 Active(anon):    1632468 kB
        Node 1 Inactive(anon):    20852 kB
        Node 1 Active(file):     888216 kB
        Node 1 Inactive(file):   774376 kB
        Node 1 Unevictable:        7424 kB
        Node 1 Mlocked:            7424 kB
        Node 1 Dirty:               308 kB
        Node 1 Writeback:             0 kB
        Node 1 FilePages:       1668208 kB
        Node 1 Mapped:           206436 kB
        Node 1 AnonPages:       1579356 kB
        Node 1 Shmem:              2052 kB
        Node 1 KernelStack:        9960 kB
        Node 1 PageTables:        13452 kB
        Node 1 NFS_Unstable:          0 kB
        Node 1 Bounce:                0 kB
        Node 1 WritebackTmp:          0 kB
        Node 1 KReclaimable:     112860 kB
        Node 1 Slab:             210308 kB
        Node 1 SReclaimable:     112860 kB
        Node 1 SUnreclaim:        97448 kB
        Node 1 AnonHugePages:         0 kB
        Node 1 ShmemHugePages:        0 kB
        Node 1 ShmemPmdMapped:        0 kB
        Node 1 HugePages_Total:  2000
        Node 1 HugePages_Free:   1000
        Node 1 HugePages_Surp:      0""")

    def test_get_hugepages(self):
        numa_client = clients.NUMAClient('fake-host')
        with mock.patch.object(numa_client, 'execute',
                               side_effect=(self.fake_numactl_output,
                                            self.fake_node0_meminfo,
                                            self.fake_node1_meminfo)):
            self.assertEqual(numa_client.get_hugepages(),
                             {0: {'total': 4000, 'free': 3000},
                              1: {'total': 2000, 'free': 1000}})

    def test_get_pagesize(self):
        numa_client = clients.NUMAClient('fake-host')
        with mock.patch.object(numa_client, 'execute',
                               return_value=self.fake_proc_meminfo):
            self.assertEqual(numa_client.get_pagesize(), 2048)

    def test_get_host_topology(self):
        numa_client = clients.NUMAClient('fake-host')
        with mock.patch.object(numa_client, 'execute',
                               return_value=self.fake_numactl_output):
            self.assertEqual(numa_client.get_host_topology(),
                             {0: [0, 1, 2],
                              1: [3, 4]})

    def test_get_num_cpus(self):
        numa_client = clients.NUMAClient('fake-host')
        with mock.patch.object(numa_client, 'execute',
                               return_value=self.fake_numactl_output):
            self.assertEqual(5, numa_client.get_num_cpus())
