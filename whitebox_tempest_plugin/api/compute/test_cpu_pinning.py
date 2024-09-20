# Copyright 2015 Intel Corporation
# Copyright 2018 Red Hat Inc.
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

"""Tests for CPU pinning and CPU thread pinning policies.

Based on tests for the Intel NFV CI.

For more information, refer to:

- https://wiki.openstack.org/wiki/ThirdPartySystems/Intel_NFV_CI
- https://github.com/openstack/intel-nfv-ci-tests
"""

from itertools import chain
import testtools
import xml.etree.ElementTree as ET

from oslo_serialization import jsonutils
from tempest.common import compute
from tempest.common import waiters
from tempest import config
from tempest.exceptions import BuildErrorException
from tempest.lib.common import api_version_request
from tempest.lib import decorators

from whitebox_tempest_plugin.api.compute import base
from whitebox_tempest_plugin.api.compute import numa_helper
from whitebox_tempest_plugin import hardware
from whitebox_tempest_plugin.services import clients
from whitebox_tempest_plugin import utils as whitebox_utils

from oslo_log import log as logging


CONF = config.CONF
LOG = logging.getLogger(__name__)


class BasePinningTest(base.BaseWhiteboxComputeTest,
                      numa_helper.NUMAHelperMixin):
    shared_cpu_policy = {'hw:cpu_policy': 'shared'}
    dedicated_cpu_policy = {'hw:cpu_policy': 'dedicated'}

    def get_server_cell_pinning(self, server_id):
        """Get the host NUMA cell numbers to which the server's virtual NUMA
        cells are pinned.

        :param server_id: The instance UUID to look up.
        :return cpu_pins: A dict of guest cell number -> set(host cell numbers
                          said cell is pinned to)
        """
        root = self.get_server_xml(server_id)

        memnodes = root.findall('./numatune/memnode')
        cell_pins = {}
        for memnode in memnodes:
            cell_pins[int(memnode.get('cellid'))] = \
                hardware.parse_cpu_spec(memnode.get('nodeset'))

        return cell_pins

    # TODO(jparker): Need to clean up this method and similar helper methods.
    # This should either end up in numa_helper or the base compute test class
    def get_server_emulator_threads(self, server_id):
        """Get the host CPU numbers to which the server's emulator threads are
        pinned.

        :param server_id: The instance UUID to look up.
        :return emulator_threads: A set of host CPU numbers.
        """
        root = self.get_server_xml(server_id)

        emulatorpins = root.findall('./cputune/emulatorpin')
        emulator_threads = set()
        for pin in emulatorpins:
            emulator_threads |= \
                hardware.parse_cpu_spec(pin.get('cpuset'))

        return emulator_threads

    def get_cpus_with_sched(self, server_id):
        root = self.get_server_xml(server_id)
        scheds = root.findall('./cputune/vcpusched')
        cpus = [int(each.get('vcpus')) for each in scheds if each is not None]
        return cpus

    def get_server_cpu_pinning(self, server_id):
        """Get the host CPU numbers to which the server's vCPUs are pinned.
        Assumes that cpu_policy=dedicated is in effect so that every vCPU is
        pinned to a single pCPU.

        :param server_id: The instance UUID to look up.
        :return cpu_pins: A int:int dict indicating CPU pins.
        """
        root = self.get_server_xml(server_id)

        vcpupins = root.findall('./cputune/vcpupin')
        # NOTE(artom) This assumes every guest CPU is pinned to a single host
        # CPU - IOW that the 'dedicated' cpu_policy is in effect.
        cpu_pins = {int(pin.get('vcpu')): int(pin.get('cpuset'))
                    for pin in vcpupins if pin is not None}

        return cpu_pins

    def _get_db_numa_topology(self, instance_uuid):
        """Returns an instance's NUMA topology as a JSON object.
        """
        db_client = clients.DatabaseClient()
        db = CONF.whitebox_database.nova_cell1_db_name
        with db_client.cursor(db) as cursor:
            cursor.execute('SELECT numa_topology FROM instance_extra '
                           'WHERE instance_uuid = "%s"' % instance_uuid)
            numa_topology = jsonutils.loads(
                cursor.fetchone()['numa_topology'])
            numa_topology = whitebox_utils.normalize_json(numa_topology)
        return numa_topology

    def _get_host_cpu_dedicated_set(self, host):
        """Return cpu dedicated or shared set configured for the provided host.
        """
        cpu_set = \
            whitebox_utils.get_host_details(host).get('cpu_dedicated_set', [])
        return hardware.parse_cpu_spec(cpu_set)

    def _get_host_cpu_shared_set(self, host):
        """Return cpu dedicated or shared set configured for the provided host.
        """
        cpu_set = \
            whitebox_utils.get_host_details(host).get('cpu_shared_set', [])
        return hardware.parse_cpu_spec(cpu_set)

    def _get_shared_set_size(self):
        gathered_lists = [self._get_host_cpu_shared_set(host)
                          for host in self.hosts_details.keys()]
        return gathered_lists

    def _get_dedicated_set_size(self):
        gathered_lists = [self._get_host_cpu_dedicated_set(host)
                          for host in self.hosts_details.keys()]
        return gathered_lists


class CPUPolicyTest(BasePinningTest):
    """Validate CPU policy support."""

    @testtools.skipUnless(
        CONF.whitebox_hardware.shared_cpus_per_numa > 0,
        'Need one or more shared cpus per NUMA')
    def test_cpu_shared(self):
        """Ensure an instance with an explicit 'shared' policy work."""
        shared_vcpus = CONF.whitebox_hardware.shared_cpus_per_numa
        flavor = self.create_flavor(
            vcpus=shared_vcpus,
            extra_specs=self.shared_cpu_policy)
        self.create_test_server(flavor=flavor['id'], wait_until='ACTIVE')

    @testtools.skipUnless(
        CONF.whitebox_hardware.dedicated_cpus_per_numa >= 2,
        'Need two or more dedicated cpus per NUMA')
    def test_cpu_dedicated(self):
        """Ensure an instance with 'dedicated' pinning policy work.

        This is implicitly testing the 'prefer' policy, given that that's the
        default. However, we check specifics of that later and only assert that
        things aren't overlapping here.
        """
        dedicated_vcpus_per_guest = \
            CONF.whitebox_hardware.dedicated_cpus_per_numa // 2
        flavor = self.create_flavor(vcpus=dedicated_vcpus_per_guest,
                                    extra_specs=self.dedicated_cpu_policy)
        server_a = self.create_test_server(flavor=flavor['id'],
                                           wait_until='ACTIVE')
        server_b = self.create_test_server(
            flavor=flavor['id'], scheduler_hints={'same_host': server_a['id']},
            wait_until='ACTIVE')
        cpu_pinnings_a = self.get_server_cpu_pinning(server_a['id'])
        cpu_pinnings_b = self.get_server_cpu_pinning(server_b['id'])
        host = self.get_host_for_server(server_a['id'])
        dedicated_vcpus = self._get_host_cpu_dedicated_set(host)
        self.assertTrue(
            set(cpu_pinnings_a.values()).issubset(dedicated_vcpus),
            "Instance A's pinning %s should be a subset of pinning range %s"
            % (cpu_pinnings_a, dedicated_vcpus))
        self.assertTrue(
            set(cpu_pinnings_b.values()).issubset(dedicated_vcpus),
            "Instance B's pinning %s should be a subset of pinning range %s"
            % (cpu_pinnings_b, dedicated_vcpus))

        self.assertTrue(
            set(cpu_pinnings_a.values()).isdisjoint(
                set(cpu_pinnings_b.values())),
            "Unexpected overlap in CPU pinning: {}; {}".format(
                cpu_pinnings_a,
                cpu_pinnings_b))

    @testtools.skipUnless(CONF.whitebox_hardware.realtime_mask,
                          'Realtime mask was not provided.')
    def test_realtime_cpu(self):
        realtime_mask = CONF.whitebox_hardware.realtime_mask
        realtime_set = hardware.parse_cpu_spec(realtime_mask)
        vcpu_count = len(realtime_set) + 1

        specs = self.dedicated_cpu_policy.copy()
        specs.update({
            'hw:cpu_realtime': 'yes',
            'hw:cpu_realtime_mask': realtime_mask,
        })

        flavor = self.create_flavor(vcpus=vcpu_count, extra_specs=specs)
        server = self.create_test_server(
            flavor=flavor['id'], wait_until='ACTIVE')

        cpus = self.get_cpus_with_sched(server['id'])
        expected = list(hardware.parse_cpu_spec(realtime_mask))
        self.assertEqual(expected, cpus)

    @testtools.skipUnless(CONF.compute_feature_enabled.resize,
                          'Resize not available.')
    @testtools.skipUnless(
        CONF.whitebox_hardware.shared_cpus_per_numa > 0,
        'Need one or more shared cpu per NUMA')
    @testtools.skipUnless(
        CONF.whitebox_hardware.dedicated_cpus_per_numa > 0,
        'Need at least one or more dedicated cpu per NUMA')
    def test_resize_pinned_server_to_unpinned(self):
        """Ensure resizing an instance to unpinned actually drops pinning."""
        flavor_a = self.create_flavor(
            vcpus=CONF.whitebox_hardware.dedicated_cpus_per_numa,
            extra_specs=self.dedicated_cpu_policy)
        server = self.create_test_server(flavor=flavor_a['id'],
                                         wait_until='ACTIVE')

        cpu_pinnings = self.get_server_cpu_pinning(server['id'])
        host = self.get_host_for_server(server['id'])
        dedicated_vcpus = self._get_host_cpu_dedicated_set(host)
        self.assertTrue(
            set(cpu_pinnings.values()).issubset(dedicated_vcpus),
            "Instance pinning %s should be a subset of pinning range %s"
            % (cpu_pinnings, dedicated_vcpus))

        flavor_b = self.create_flavor(
            vcpus=CONF.whitebox_hardware.shared_cpus_per_numa,
            extra_specs=self.shared_cpu_policy)
        self.resize_server(server['id'], flavor_b['id'])
        cpu_pinnings = self.get_server_cpu_pinning(server['id'])

        self.assertEqual(
            len(cpu_pinnings), 0,
            "Resized instance should be unpinned but is still pinned")

    @testtools.skipUnless(CONF.compute_feature_enabled.resize,
                          'Resize not available.')
    @testtools.skipUnless(
        CONF.whitebox_hardware.shared_cpus_per_numa > 0,
        'Need one or more shared cpus per NUMA')
    @testtools.skipUnless(
        CONF.whitebox_hardware.dedicated_cpus_per_numa > 0,
        'Need at least one or more dedicated cpus per NUMA')
    def test_resize_unpinned_server_to_pinned(self):
        """Ensure resizing an instance to pinned actually applies pinning."""
        flavor_a = self.create_flavor(
            vcpus=CONF.whitebox_hardware.shared_cpus_per_numa,
            extra_specs=self.shared_cpu_policy)
        server = self.create_test_server(flavor=flavor_a['id'],
                                         wait_until='ACTIVE')
        cpu_pinnings = self.get_server_cpu_pinning(server['id'])

        self.assertEqual(
            len(cpu_pinnings), 0,
            "Instance should be unpinned but is pinned")

        flavor_b = self.create_flavor(
            vcpus=CONF.whitebox_hardware.dedicated_cpus_per_numa,
            extra_specs=self.dedicated_cpu_policy)
        self.resize_server(server['id'], flavor_b['id'])

        cpu_pinnings = self.get_server_cpu_pinning(server['id'])
        host = self.get_host_for_server(server['id'])
        dedicated_vcpus = self._get_host_cpu_dedicated_set(host)
        self.assertTrue(
            set(cpu_pinnings.values()).issubset(dedicated_vcpus),
            "After resize instance %s pinning %s should be a subset of "
            "pinning range %s" % (server['id'], cpu_pinnings, dedicated_vcpus))

    @testtools.skipUnless(
        CONF.whitebox_hardware.dedicated_cpus_per_numa > 0,
        'Need at least one or more dedicated cpus per NUMA')
    def test_reboot_pinned_server(self):
        """Ensure pinning information is persisted after a reboot."""
        flavor = self.create_flavor(
            vcpus=CONF.whitebox_hardware.dedicated_cpus_per_numa,
            extra_specs=self.dedicated_cpu_policy)
        server = self.create_test_server(flavor=flavor['id'],
                                         wait_until='ACTIVE')

        cpu_pinnings = self.get_server_cpu_pinning(server['id'])
        host = self.get_host_for_server(server['id'])
        dedicated_vcpus = self._get_host_cpu_dedicated_set(host)
        self.assertTrue(
            set(cpu_pinnings.values()).issubset(dedicated_vcpus),
            "After resize instance %s pinning %s should be a subset of "
            "pinning range %s" % (server['id'], cpu_pinnings, dedicated_vcpus))

        self.reboot_server(server['id'], 'HARD')
        cpu_pinnings = self.get_server_cpu_pinning(server['id'])

        # we don't actually assert that the same pinning information is used
        # because that's not expected. We just care that _some_ pinning is in
        # effect
        self.assertTrue(
            set(cpu_pinnings.values()).issubset(dedicated_vcpus),
            "Rebooted instance has lost its pinning information")


class CPUThreadPolicyTest(BasePinningTest):
    """Validate CPU thread policy support."""

    vcpus = 2
    isolate_thread_policy = {'hw:cpu_policy': 'dedicated',
                             'hw:cpu_thread_policy': 'isolate'}
    prefer_thread_policy = {'hw:cpu_policy': 'dedicated',
                            'hw:cpu_thread_policy': 'prefer'}
    require_thread_policy = {'hw:cpu_policy': 'dedicated',
                             'hw:cpu_thread_policy': 'require'}

    @staticmethod
    def get_siblings_list(sib):
        """Parse a list of siblings as used by libvirt.

        List of siblings can consist of comma-separated lists (0,5,6)
        or hyphen-separated ranges (0-3) or both.

        >>> get_siblings_list('0-2,3,4,5-6,9')
        [0, 1, 2, 3, 4, 5, 6, 9]
        """
        siblings = []
        for sub_sib in sib.split(','):
            if '-' in sub_sib:
                start_sib, end_sib = sub_sib.split('-')
                siblings.extend(range(int(start_sib),
                                      int(end_sib) + 1))
            else:
                siblings.append(int(sub_sib))

        return siblings

    def get_host_cpu_siblings(self, host):
        """Return core to sibling mapping of the host CPUs.

            {core_0: [sibling_a, sibling_b, ...],
             core_1: [sibling_a, sibling_b, ...],
             ...}

        `virsh capabilities` is called to get details about the host
        then a list of siblings per CPU is extracted and formatted to single
        level list.
        """
        siblings = {}

        virshxml = clients.VirshXMLClient(host)
        capxml = virshxml.capabilities()
        root = ET.fromstring(capxml)
        cpu_cells = root.findall('./host/topology/cells/cell/cpus')
        for cell in cpu_cells:
            cpus = cell.findall('cpu')
            for cpu in cpus:
                cpu_id = int(cpu.get('id'))
                sib = cpu.get('siblings')
                siblings.update({cpu_id: self.get_siblings_list(sib)})

        return siblings

    def test_threads_isolate(self):
        """Ensure vCPUs *are not* placed on thread siblings."""
        flavor = self.create_flavor(vcpus=self.vcpus,
                                    extra_specs=self.isolate_thread_policy)
        server = self.create_test_server(flavor=flavor['id'],
                                         wait_until='ACTIVE')
        host = self.get_host_for_server(server['id'])

        cpu_pinnings = self.get_server_cpu_pinning(server['id'])
        pcpu_siblings = self.get_host_cpu_siblings(host)

        self.assertEqual(len(cpu_pinnings), self.vcpus)

        # if the 'isolate' policy is used, then when one thread is used
        # the other should never be used.
        for vcpu in set(cpu_pinnings):
            pcpu = cpu_pinnings[vcpu]
            sib = pcpu_siblings[pcpu]
            sib.remove(pcpu)
            self.assertTrue(
                set(sib).isdisjoint(cpu_pinnings.values()),
                "vCPUs siblings should not have been used")

    @testtools.skipUnless(len(CONF.whitebox_hardware.smt_hosts) > 0,
                          'At least 1 SMT-capable compute host is required')
    def test_threads_prefer(self):
        """Ensure vCPUs *are* placed on thread siblings.

        For this to work, we require a host with HyperThreads. Scheduling will
        pass without this, but the test will not.
        """
        flavor = self.create_flavor(vcpus=self.vcpus,
                                    extra_specs=self.prefer_thread_policy)
        server = self.create_test_server(flavor=flavor['id'],
                                         wait_until='ACTIVE')
        host = self.get_host_for_server(server['id'])

        cpu_pinnings = self.get_server_cpu_pinning(server['id'])
        pcpu_siblings = self.get_host_cpu_siblings(host)

        self.assertEqual(len(cpu_pinnings), self.vcpus)

        for vcpu in set(cpu_pinnings):
            pcpu = cpu_pinnings[vcpu]
            sib = pcpu_siblings[pcpu]
            sib.remove(pcpu)
            self.assertFalse(
                set(sib).isdisjoint(cpu_pinnings.values()),
                "vCPUs siblings were required by not used. Does this host "
                "have HyperThreading enabled?")

    @testtools.skipUnless(len(CONF.whitebox_hardware.smt_hosts) > 0,
                          'At least 1 SMT-capable compute host is required')
    def test_threads_require(self):
        """Ensure thread siblings are required and used.

        For this to work, we require a host with HyperThreads. Scheduling will
        fail without this.
        """
        flavor = self.create_flavor(vcpus=self.vcpus,
                                    extra_specs=self.require_thread_policy)
        server = self.create_test_server(flavor=flavor['id'],
                                         wait_until='ACTIVE')
        host = self.get_host_for_server(server['id'])

        cpu_pinnings = self.get_server_cpu_pinning(server['id'])
        pcpu_siblings = self.get_host_cpu_siblings(host)

        self.assertEqual(len(cpu_pinnings), self.vcpus)

        for vcpu in set(cpu_pinnings):
            pcpu = cpu_pinnings[vcpu]
            sib = pcpu_siblings[pcpu]
            sib.remove(pcpu)
            self.assertFalse(
                set(sib).isdisjoint(cpu_pinnings.values()),
                "vCPUs siblings were required and were not used. Does this "
                "host have HyperThreading enabled?")


class EmulatorThreadTest(BasePinningTest, numa_helper.NUMAHelperMixin):

    min_microversion = '2.74'

    def setUp(self):
        super(EmulatorThreadTest, self).setUp()
        self.dedicated_cpus_per_numa = \
            CONF.whitebox_hardware.dedicated_cpus_per_numa
        self.shared_cpus_per_numa = \
            CONF.whitebox_hardware.shared_cpus_per_numa

    @classmethod
    def skip_checks(cls):
        super(EmulatorThreadTest, cls).skip_checks()
        if getattr(CONF.whitebox_hardware, 'cpu_topology', None) is None:
            msg = "cpu_topology in whitebox-hardware is not present"
            raise cls.skipException(msg)

    def create_flavor(self, threads_policy, vcpus):
        flavor = super(EmulatorThreadTest,
                       self).create_flavor(vcpus=vcpus, disk=1)

        specs = {
            'hw:cpu_policy': 'dedicated',
            'hw:emulator_threads_policy': threads_policy
        }
        self.os_admin.flavors_client.set_flavor_extra_spec(flavor['id'],
                                                           **specs)
        return flavor

    def test_policy_share_cpu_shared_set(self):
        """With policy set to share and cpu_share_set set, emulator threads
        should be pinned to cpu_share_set.

        """
        if self.shared_cpus_per_numa == 0:
            raise self.skipException('Test requires cpu_shared_set to be '
                                     'configured on the compute hosts')

        # Create a flavor using the shared threads_policy and create an
        # instance
        flavor = self.create_flavor(threads_policy='share',
                                    vcpus=self.shared_cpus_per_numa)

        server = self.create_test_server(flavor=flavor['id'],
                                         wait_until='ACTIVE')

        # Determine the compute host the guest was scheduled to and gather
        # the cpu shared set from the host
        host = self.get_host_for_server(server['id'])
        cpu_shared_set = self._get_host_cpu_shared_set(host)

        # Gather the emulator threads from the server
        emulator_threads = \
            self.get_server_emulator_threads(server['id'])

        # Confirm the emulator threads from the server is equal to the host's
        self.assertEqual(
            cpu_shared_set, emulator_threads,
            'Emulator threads for server %s is not the same as CPU set '
            '%s' % (emulator_threads, cpu_shared_set))

    def test_policy_share_cpu_shared_unset(self):
        """With policy set to share and cpu_share_set unset, emulator threads
        should float over the instance's pCPUs.
        """
        if self.dedicated_cpus_per_numa < 2:
            raise self.skipException(
                'Need at least 2 or more pCPUs per NUMA allocated to the '
                'cpu_dedicated_set of the compute host')

        with self.config_all_computes(('compute', 'cpu_shared_set', None)):

            # Create a flavor using the shared threads_policy and two instances
            # on the same host
            flavor = self.create_flavor(
                threads_policy='share',
                vcpus=int(self.dedicated_cpus_per_numa / 2))

            server_a = self.create_test_server(flavor=flavor['id'],
                                               wait_until='ACTIVE')
            server_b = self.create_test_server(
                flavor=flavor['id'],
                scheduler_hints={'same_host': server_a['id']},
                wait_until='ACTIVE')

            # Gather the emulator threads from server A and B. Then gather the
            # pinned PCPUs from server A and B.
            emulator_threads_a = \
                self.get_server_emulator_threads(server_a['id'])
            emulator_threads_b = \
                self.get_server_emulator_threads(server_b['id'])

            cpu_pins_a = self.get_pinning_as_set(server_a['id'])
            cpu_pins_b = self.get_pinning_as_set(server_b['id'])

            # Validate emulator threads for server's A and B are pinned to all
            # of server A's and B's pCPUs
            self.assertEqual(
                emulator_threads_a, cpu_pins_a,
                'Threads %s not the same as CPU pins %s' % (emulator_threads_a,
                                                            cpu_pins_a))

            self.assertEqual(
                emulator_threads_b, cpu_pins_b,
                'Threads %s not the same as CPU pins %s' % (emulator_threads_b,
                                                            cpu_pins_b))

            # Confirm the pinned pCPUs from server A do not intersect with
            # the pinned pCPUs of server B
            self.assertTrue(
                cpu_pins_a.isdisjoint(cpu_pins_b),
                'Different server pins overlap: %s and %s' % (cpu_pins_a,
                                                              cpu_pins_b))

    def test_policy_isolate(self):
        """With policy isolate, cpu_shared_set is ignored, and emulator threads
        should be pinned to a pCPU distinct from the instance's pCPUs.
        """
        if self.dedicated_cpus_per_numa < 2:
            raise self.skipException(
                'Need at least 2 or more pCPUs per NUMA allocated to the '
                'cpu_dedicated_set of the compute host')

        # Create a flavor using the isolate threads_policy and then launch
        # an instance with the flavor
        flavor = self.create_flavor(
            threads_policy='isolate',
            vcpus=(self.dedicated_cpus_per_numa - 1)
        )

        server = self.create_test_server(flavor=flavor['id'],
                                         wait_until='ACTIVE')

        # Gather the emulator threads and the pinned PCPUs from the guest
        emulator_threads = \
            self.get_server_emulator_threads(server['id'])
        cpu_pins = self.get_pinning_as_set(server['id'])

        # Determine the compute host the guest was scheduled to and gather
        # the cpu dedicated set from the host
        host = self.get_host_for_server(server['id'])
        cpu_dedicated_set = self._get_host_cpu_dedicated_set(host)

        # Confirm the pinned cpus from the guest are part of the dedicated
        # range of the compute host it is scheduled to
        self.assertTrue(
            cpu_pins.issubset(cpu_dedicated_set), 'Pin set value %s is not '
            'a subset of %s' % (cpu_pins, cpu_dedicated_set))

        # Validate the emulator thread is disjoined from the pinned CPUs of the
        # guest.
        self.assertTrue(
            cpu_pins.isdisjoint(emulator_threads),
            'Threads %s overlap with CPUs %s' % (emulator_threads,
                                                 cpu_pins))

        # Confirm the emulator thread is a subset of the compute host's cpu
        # dedicated set
        self.assertTrue(
            emulator_threads.issubset(cpu_dedicated_set), 'Emulator thread '
            'value %s is not a subset of cpu dedicated set %s' %
            (emulator_threads, cpu_dedicated_set))

    def test_emulator_no_extra_cpu(self):
        """Create a flavor that consumes all available pCPUs for the guest.
        The flavor should also be set to isolate emulator pinning. Instance
        should fail to build, since there are no distinct pCPUs available for
        the emulator thread.
        """

        # Create a dedicated flavor with a vcpu size equal to the number
        # of available pCPUs in the dedicated set. With threads_policy
        # being set to isolate, the build should fail since no more
        # pCPUs will be available.
        flavor = self.create_flavor(threads_policy='isolate',
                                    vcpus=self.dedicated_cpus_per_numa)

        # Confirm the instance cannot be built
        self.assertRaises(BuildErrorException,
                          self.create_test_server,
                          flavor=flavor['id'],
                          wait_until='ACTIVE')


class NUMALiveMigrationBase(BasePinningTest):
    @classmethod
    def skip_checks(cls):
        super(NUMALiveMigrationBase, cls).skip_checks()
        if (CONF.compute.min_compute_nodes < 2 or
                CONF.whitebox.max_compute_nodes > 2):
            raise cls.skipException('Exactly 2 compute nodes required.')

    def _get_cpu_pins_from_db_topology(self, db_topology):
        """Given a JSON object representing a instance's database NUMA
        topology, returns a dict of dicts indicating CPU pinning, for example:
        {0: {'1': 2, '3': 4},
         1: {'2': 6, '7': 8}}
        """
        pins = {}
        cell_count = 0
        for cell in db_topology['nova_object.data']['cells']:
            pins[cell_count] = cell['nova_object.data']['cpu_pinning_raw']
            cell_count += 1
        return pins

    def _get_pcpus_from_cpu_pins(self, cpu_pins):
        """Given a dict of dicts of CPU pins, return just the host pCPU IDs for
        all cells and guest vCPUs.
        """
        pcpus = set()
        for cell, pins in cpu_pins.items():
            pcpus.update(set(pins.values()))
        return pcpus

    def _get_cpus_per_node(self, *args):
        """Given a list of iterables, each containing the CPU IDs for a
        certain NUMA node, return a set containing the number of CPUs in each
        node. This is only used to make sure all NUMA nodes have the same
        number of CPUs - which cannot happen on real hardware, but could happen
        in virtual machines.
        """
        return set([len(cpu_list) for cpu_list in chain(*args)])

    def _get_shared_cpuset(self, server_id):
        """Search the xml vcpu element of the provided server for its cpuset.
        Convert cpuset found into a set of integers.
        """
        root = self.get_server_xml(server_id)
        cpuset = root.find('./vcpu').attrib.get('cpuset', None)
        return hardware.parse_cpu_spec(cpuset)

    def _validate_hugepage_elements(self, server_id, pagesize):
        """Analyze the hugepage xml element(s) from a provided instance. Expect
        to find only one hugepage element in the domain. Return boolean result
        comparing if the found page size is equal to the expected page size.
        """
        huge_pages_list = self._get_hugepage_xml_element(server_id)
        self.assertEqual(len(huge_pages_list), 1, "Expected to find 1 "
                         "hugepage XML element on server %s but found %s"
                         % (server_id, len(huge_pages_list)))
        huge_page_xml = huge_pages_list[0]
        return int(huge_page_xml.attrib['size']) == pagesize


class NUMALiveMigrationTest(NUMALiveMigrationBase):

    # Don't bother with old microversions where disk_over_commit was required
    # for the live migration request.
    min_microversion = '2.25'

    @classmethod
    def skip_checks(cls):
        super(NUMALiveMigrationTest, cls).skip_checks()
        if not compute.is_scheduler_filter_enabled('DifferentHostFilter'):
            raise cls.skipException('DifferentHostFilter required.')

    def test_cpu_pinning_and_emulator_threads(self):
        dedicated_cpus_per_numa = \
            CONF.whitebox_hardware.dedicated_cpus_per_numa
        if dedicated_cpus_per_numa < 2:
            msg = ('Need at least 2 or more pCPUs per NUMA allocated to the '
                   'cpu_dedicated_set of the compute host')
            raise self.skipException(msg)

        shared_cpus_per_numa = \
            CONF.whitebox_hardware.dedicated_cpus_per_numa
        if shared_cpus_per_numa == 0:
            raise self.skipException(
                'Need at least 1 or more pCPUs per NUMA allocated to the '
                'cpu_shared_set of the compute host')

        # Boot 2 servers such that their vCPUs "fill" a NUMA node.
        specs = {'hw:cpu_policy': 'dedicated',
                 'hw:emulator_threads_policy': 'share'}
        flavor = self.create_flavor(vcpus=(int(dedicated_cpus_per_numa / 2)),
                                    extra_specs=specs)
        server_a = self.create_test_server(flavor=flavor['id'],
                                           wait_until='ACTIVE')
        # TODO(artom) As of 2.68 we can no longer force a live-migration,
        # and having the different_host hint in the RequestSpec will
        # prevent live migration. Start enabling/disabling
        # DifferentHostFilter as needed?
        server_b = self.create_test_server(
            flavor=flavor['id'],
            scheduler_hints={'different_host': server_a['id']},
            wait_until='ACTIVE')

        # Iterate over both guests and confirm their pinned vCPUs and emulator
        # threads are correct
        for server in [server_a, server_b]:
            # Determine the compute host of the guest
            host = self.get_host_for_server(server['id'])
            host_sm = clients.NovaServiceManager(host, 'nova-compute',
                                                 self.os_admin.services_client)

            # Gather the cpu_dedicated_set and cpu_shared_set configured for
            # the compute host
            cpu_dedicated_set = host_sm.get_cpu_dedicated_set()
            cpu_shared_set = host_sm.get_cpu_shared_set()

            # Check the nova cells DB and gather the pCPU mapping for the
            # guest. Confirm the pCPUs allocated to the guest as documented in
            # the DB are a subset of the cpu_dedicated_set configured on the
            # host
            db_topo = self._get_db_numa_topology(server['id'])
            pcpus = self._get_pcpus_from_cpu_pins(
                self._get_cpu_pins_from_db_topology(db_topo))
            self.assertTrue(pcpus.issubset(cpu_dedicated_set))

            # Gather the emulator threads configured on the guest. Verify the
            # emulator threads on the guest are a subset of the cpu_shared_set
            # configured on the compute host.
            emulator_threads = self.get_server_emulator_threads(server['id'])
            self.assertEqual(
                cpu_shared_set, emulator_threads,
                'Emulator threads for server %s is not the same as CPU set '
                '%s' % (emulator_threads, cpu_shared_set))

            # Gather the cpu pin set for the guest and confirm it is a subset
            # of its respective compute host
            guest_pin_set = self.get_pinning_as_set(server['id'])
            self.assertTrue(
                guest_pin_set.issubset(cpu_dedicated_set),
                'Server %s\'s cpu dedicated set is not a subset of the '
                'compute host\'s cpu dedicated set %s'.format(
                    guest_pin_set, cpu_dedicated_set))

        # Migrate server B to the same compute host as server A
        host_a = self.get_host_for_server(server_a['id'])
        self.live_migrate(self.os_primary, server_b['id'], 'ACTIVE',
                          target_host=host_a)

        # After migration, guests should have disjoint (non-null) CPU pins in
        # their XML
        pin_a = self.get_pinning_as_set(server_a['id'])
        pin_b = self.get_pinning_as_set(server_b['id'])
        self.assertTrue(pin_a and pin_b,
                        'Pinned servers are actually unpinned: '
                        '%s, %s' % (pin_a, pin_b))
        self.assertTrue(pin_a.isdisjoint(pin_b),
                        'Pins overlap: %s, %s' % (pin_a, pin_b))

        # Same for their topologies in the database
        db_topo_a = self._get_db_numa_topology(server_a['id'])
        pcpus_a = self._get_pcpus_from_cpu_pins(
            self._get_cpu_pins_from_db_topology(db_topo_a))
        db_topo_b = self._get_db_numa_topology(server_b['id'])
        pcpus_b = self._get_pcpus_from_cpu_pins(
            self._get_cpu_pins_from_db_topology(db_topo_b))
        self.assertTrue(pcpus_a and pcpus_b)
        self.assertTrue(
            pcpus_a.isdisjoint(pcpus_b),
            'Expected servers to have disjoint CPU pins in the '
            'database, instead have %s and %s' % (pcpus_a, pcpus_b))

        # Guests emulator threads should still be configured for both guests.
        # Since they are on the same compute host the guest's emulator threads
        # should be the same.
        threads_a = self.get_server_emulator_threads(server_a['id'])
        threads_b = self.get_server_emulator_threads(server_b['id'])
        self.assertTrue(threads_a and threads_b,
                        'Emulator threads should be pinned, are unpinned: '
                        '%s, %s' % (threads_a, threads_b))
        self.assertEqual(threads_a, threads_b, 'After live migration emulator '
                         'threads for both servers should be the same')

    @decorators.skip_because(bug='2009853', bug_type='storyboard')
    def test_hugepages(self):
        host_a, host_b = [whitebox_utils.get_ctlplane_address(host) for host in
                          self.list_compute_hosts()]

        numaclient_a = clients.NUMAClient(host_a)
        numaclient_b = clients.NUMAClient(host_b)

        # Get the first host's topology and hugepages config
        topo_a = numaclient_a.get_host_topology()
        pagesize_a = numaclient_a.get_pagesize()
        pages_a = numaclient_a.get_hugepages()

        # Same for second host
        topo_b = numaclient_b.get_host_topology()
        pagesize_b = numaclient_b.get_pagesize()
        pages_b = numaclient_b.get_hugepages()

        # Need hugepages
        for pages_config in pages_a, pages_b:
            for numa_cell, pages in pages_config.items():
                if pages['total'] == 0:
                    raise self.skipException('Hugepages required')

        # Need at least 2 NUMA nodes per host
        if len(topo_a) < 2 or len(topo_b) < 2:
            raise self.skipException('At least 2 NUMA nodes per host required')

        # The hosts need to have the same pagesize
        if not pagesize_a == pagesize_b:
            raise self.skipException('Hosts must have same pagesize')

        # All NUMA nodes need to have same number of CPUs
        if len(self._get_cpus_per_node(topo_a.values(),
                                       topo_b.values())) != 1:
            raise self.skipException('NUMA nodes must have same number of '
                                     'CPUs')

        # Same idea, but for hugepages total
        pagecounts = chain(pages_a.values(), pages_b.values())
        if not len(set([count['total'] for count in pagecounts])) == 1:
            raise self.skipException('NUMA nodes must have same number of '
                                     'total hugepages')

        # NOTE(jparker) due to the check to validate each NUMA node has the
        # same number of hugepages, the pagecounts iterator becomes empty.
        # 'Resetting' pagecounts to calculate minimum free huge pages
        pagecounts = chain(pages_a.values(), pages_b.values())
        # The smallest available number of hugepages must be bigger than
        # total / 2 to ensure no node can accept more than 1 instance with that
        # many hugepages
        min_free = min([count['free'] for count in pagecounts])
        min_free_required = pages_a[0]['total'] / 2
        if min_free < min_free_required:
            raise self.skipException(
                'Need enough free hugepages to effectively "fill" a NUMA '
                'node. Need: %d. Have: %d' % (min_free_required, min_free))

        # Create a flavor that'll "fill" a NUMA node
        ram = pagesize_a / 1024 * min_free
        specs = {'hw:numa_nodes': '1',
                 'hw:mem_page_size': 'large'}
        flavor = self.create_flavor(vcpus=len(topo_a[0]), ram=int(ram),
                                    extra_specs=specs)

        # Boot two servers
        server_a = self.create_test_server(flavor=flavor['id'],
                                           wait_until='ACTIVE')
        server_b = self.create_test_server(
            flavor=flavor['id'],
            scheduler_hints={'different_host': server_a['id']},
            wait_until='ACTIVE')

        # Assert hugepage XML element is present on both servers and the
        # pagesize is correct
        for server_id in [server_a['id'], server_b['id']]:
            self.assertTrue(
                self._validate_hugepage_elements(server_id, pagesize_a),
                "Expected pagesize of %s not found on server %s before "
                "live-migration" % (pagesize_a, server_id)
            )

        # We expect them to end up with the same cell pin - specifically, guest
        # cell 0 to host cell 0.
        pin_a = self.get_server_cell_pinning(server_a['id'])
        pin_b = self.get_server_cell_pinning(server_b['id'])
        self.assertTrue(pin_a and pin_b,
                        'Cells not actually pinned: %s, %s' % (pin_a, pin_b))
        self.assertEqual(pin_a, pin_b,
                         'Servers ended up on different host cells. '
                         'This is OK, but is unexpected and the test cannot '
                         'continue. Pins: %s, %s' % (pin_a, pin_b))

        # Live migrate server_b
        compute_a = self.get_host_other_than(server_b['id'])
        self.live_migrate(self.os_primary, server_b['id'], 'ACTIVE',
                          target_host=compute_a)

        # Assert hugepage XML element is still present and correct size for
        # server_b after live migration
        self.assertTrue(
            self._validate_hugepage_elements(server_b['id'], pagesize_a),
            "Expected pagesize of %s not found on %s after live-migration" %
            (pagesize_a, server_b['id'])
        )

        # Their guest NUMA node 0 should be on different host nodes
        pin_a = self.get_server_cell_pinning(server_a['id'])
        pin_b = self.get_server_cell_pinning(server_b['id'])
        self.assertTrue(pin_a[0] and pin_b[0],
                        'Cells not actually pinned: %s, %s' % (pin_a, pin_b))
        self.assertTrue(pin_a[0].isdisjoint(pin_b[0]))


class NUMACPUDedicatedLiveMigrationTest(NUMALiveMigrationBase):

    min_microversion = '2.74'
    lp_bug_1869804_fix = '2.96'

    @classmethod
    def skip_checks(cls):
        super(NUMACPUDedicatedLiveMigrationTest, cls).skip_checks()
        dedicated_cpus_per_numa = \
            CONF.whitebox_hardware.dedicated_cpus_per_numa
        if dedicated_cpus_per_numa < 2:
            raise cls.skipException(
                'Need at least 2 or more pCPU\'s per NUMA allocated to the '
                'cpu_dedicated_set of the compute host')

        shared_cpus_per_numa = \
            CONF.whitebox_hardware.shared_cpus_per_numa
        if shared_cpus_per_numa == 0:
            raise cls.skipException(
                'Need at least 1 or more pCPU\'s per NUMA allocated to the '
                'cpu_shared_set of the compute host')

    def test_collocation_migration(self):
        flavor_vcpu_size = 1
        dedicated_flavor = self.create_flavor(
            vcpus=flavor_vcpu_size,
            extra_specs=self.dedicated_cpu_policy
        )
        shared_flavor = self.create_flavor(vcpus=flavor_vcpu_size)

        # Create a total of four instances, with each compute host holding
        # a server with a cpu_dedicated policy and a server that will
        # float across the respective host's cpu_shared_set
        dedicated_server_a = self.create_test_server(
            flavor=dedicated_flavor['id'], wait_until='ACTIVE')
        host_a = self.get_host_for_server(dedicated_server_a['id'])
        shared_server_a = self.create_test_server(
            clients=self.os_admin, flavor=shared_flavor['id'],
            host=host_a, wait_until='ACTIVE')

        dedicated_server_b = self.create_test_server(
            flavor=dedicated_flavor['id'],
            scheduler_hints={'different_host': dedicated_server_a['id']},
            wait_until='ACTIVE')
        host_b = self.get_host_for_server(dedicated_server_b['id'])
        shared_server_b = self.create_test_server(
            clients=self.os_admin, flavor=shared_flavor['id'],
            host=host_b, wait_until='ACTIVE')

        host_sm_a = clients.NovaServiceManager(host_a, 'nova-compute',
                                               self.os_admin.services_client)
        host_sm_b = clients.NovaServiceManager(host_b, 'nova-compute',
                                               self.os_admin.services_client)

        # Iterate over the two servers using the dedicated cpu policy. Based
        # on the host they were scheduled too confirm the guest's dedicated
        # cpus are a subset of their respective hosts cpu_dedicated_set
        for server, host_sm in zip((dedicated_server_a, dedicated_server_b),
                                   (host_sm_a, host_sm_b)):
            cpu_dedicated_set = host_sm.get_cpu_dedicated_set()
            server_dedicated_cpus = self.get_pinning_as_set(server['id'])
            self.assertTrue(
                server_dedicated_cpus.issubset(cpu_dedicated_set), 'Pinned '
                'CPUs %s of server %s is not a subset of %s' %
                (server_dedicated_cpus, server['id'], cpu_dedicated_set))

        # Iterate over the two servers using the shared cpu policy. Based
        # on the host they were scheduled too confirm the guest's shared
        # cpus are the same as their respective hosts cpu_shared_set
        for server, host_sm in zip((shared_server_a, shared_server_b),
                                   (host_sm_a, host_sm_b)):
            cpu_shared_set = host_sm.get_cpu_shared_set()
            server_shared_cpus = self._get_shared_cpuset(server['id'])
            self.assertCountEqual(
                server_shared_cpus, cpu_shared_set, 'Shared CPU Set %s of '
                'shared server %s is not equal to shared set of %s' %
                (server_shared_cpus, server['id'], cpu_shared_set))

        # Live migrate shared server A to the compute node with shared
        # server B. Both servers are using shared vCPU's so migration
        # should be successful
        self.live_migrate(self.os_admin, shared_server_a['id'], 'ACTIVE',
                          target_host=host_b)

        # Validate shared server A now has a shared cpuset that is a equal
        # to it's new host's cpu_shared_set
        shared_set_a = self._get_shared_cpuset(shared_server_a['id'])

        # TODO(jparker) 1869804 has been addressed in master but will not be
        # backported into RHOS 17 or older downstream version. Will be removed
        # when downstream supports the bug fix.
        config_max_version = api_version_request.APIVersionRequest(
            CONF.compute.max_microversion)
        version_fix = \
            api_version_request.APIVersionRequest(self.lp_bug_1869804_fix)
        if config_max_version < version_fix:
            host_shared_set = host_sm_a.get_cpu_shared_set()
        else:
            host_shared_set = host_sm_b.get_cpu_shared_set()
        self.assertCountEqual(
            shared_set_a, host_shared_set, 'After migration of server %s, '
            'shared CPU set %s is not equal to new shared set %s' %
            (shared_server_a['id'], shared_set_a, host_shared_set))

        # Live migrate dedicated server A to the same host holding
        # dedicated server B. End result should be all 4 servers are on
        # the same host.
        self.live_migrate(self.os_admin, dedicated_server_a['id'], 'ACTIVE',
                          target_host=host_b)

        # Dedicated server A should have a CPU pin set that is a subset of
        # it's new host's cpu_dedicated_set and should not intersect with
        # dedicated server B's CPU pin set or the cpu_shared_set of the
        # host
        dedicated_pin_a = self.get_pinning_as_set(dedicated_server_a['id'])
        dedicated_pin_b = self.get_pinning_as_set(dedicated_server_b['id'])
        host_b_dedicated_set = host_sm_b.get_cpu_dedicated_set()
        host_b_shared_set = host_sm_b.get_cpu_shared_set()
        self.assertTrue(
            dedicated_pin_a.issubset(host_b_dedicated_set),
            'Pinned Host CPU\'s %s of server %s is not a subset of %s' %
            (dedicated_pin_a, dedicated_server_a['id'], host_b_dedicated_set))
        self.assertTrue(
            dedicated_pin_a.isdisjoint(dedicated_pin_b),
            'Pinned Host CPU\'s %s of server %s overlaps with %s' %
            (dedicated_pin_a, dedicated_server_a['id'], dedicated_pin_b))
        self.assertTrue(
            dedicated_pin_a.isdisjoint(host_b_shared_set), 'Pinned Host '
            'CPU\'s %s of server %s overlaps with cpu_shared_set %s' %
            (dedicated_pin_a, dedicated_server_a['id'], host_b_shared_set))


class NUMARebuildTest(BasePinningTest):
    """Test in-place rebuild of NUMA instances"""

    vcpus = 2
    prefer_thread_policy = {'hw:cpu_policy': 'dedicated',
                            'hw:cpu_thread_policy': 'prefer'}

    @classmethod
    def skip_checks(cls):
        super(NUMARebuildTest, cls).skip_checks()
        if not compute.is_scheduler_filter_enabled('NUMATopologyFilter'):
            raise cls.skipException('NUMATopologyFilter required.')

    def test_in_place_rebuild(self):
        """This test should pass provided no NUMA topology changes occur.

        Steps:
        1. Create a VM with one image
        2. Rebuild the VM with another image
        3. Check NUMA topology remains same after rebuild
        """
        flavor = self.create_flavor(vcpus=self.vcpus,
                                    extra_specs=self.prefer_thread_policy)
        server = self.create_test_server(flavor=flavor['id'],
                                         wait_until='ACTIVE')
        db_topo_orig = self._get_db_numa_topology(server['id'])
        host = self.get_host_for_server(server['id'])
        self.servers_client.rebuild_server(server['id'],
                                           self.image_ref_alt)['server']
        waiters.wait_for_server_status(self.servers_client,
                                       server['id'], 'ACTIVE')
        self.assertEqual(host, self.get_host_for_server(server['id']))
        db_topo_rebuilt = self._get_db_numa_topology(server['id'])
        self.assertEqual(db_topo_orig, db_topo_rebuilt,
                         "NUMA topology doesn't match")


class MixedCPUPolicyTest(BasePinningTest, numa_helper.NUMAHelperMixin):
    vcpus = 2
    mixed_cpu_policy = {'hw:cpu_policy': 'mixed',
                        'hw:cpu_dedicated_mask': '^0'}

    @classmethod
    def skip_checks(cls):
        super(MixedCPUPolicyTest, cls).skip_checks()
        if CONF.whitebox_hardware.shared_cpus_per_numa == 0:
            raise cls.skipException(
                'Need at least 1 or more pCPU\'s per NUMA allocated to the '
                'cpu_shared_set of the compute host')

    def test_shared_pinned_and_unpinned_guest(self):
        flavor = self.create_flavor(vcpus=self.vcpus,
                                    extra_specs=self.mixed_cpu_policy)

        server = self.create_test_server(flavor=flavor['id'],
                                         wait_until='ACTIVE')
        host = self.get_host_for_server(server['id'])
        host_sm = clients.NovaServiceManager(host, 'nova-compute',
                                             self.os_admin.services_client)

        # Gather the current hosts cpu dedicated and shared set values
        host_dedicated_cpus = host_sm.get_cpu_dedicated_set()
        host_shared_cpus = host_sm.get_cpu_shared_set()

        # Find the PCPU's currently mapped to core 0 of the guest
        guest_shared_cpus = self.get_host_pcpus_for_guest_vcpu(
            server['id'], [0])

        # Validate the PCPUs mapped to core 0 are a subset of the cpu shared
        # set of the host and number of shared CPUs are accurate to what
        # is expected for the NUMA node
        self.assertEqual(
            CONF.whitebox_hardware.shared_cpus_per_numa,
            len(guest_shared_cpus),
            'Number of Shared CPUs allocated to guest should be %s but '
            'instead found %s' % (CONF.whitebox_hardware.shared_cpus_per_numa,
                                  len(guest_shared_cpus)))
        self.assertTrue(
            guest_shared_cpus.issubset(host_shared_cpus),
            'Shared CPUs allocated to guest %s is not a subset of the shared '
            'CPUs that compute host is expected to provide %s' %
            (guest_shared_cpus, host_shared_cpus))

        # Find the PCPU pinned to core 1 of the guest
        guest_dedicated_cpus = \
            self.get_host_pcpus_for_guest_vcpu(server['id'], [1])

        # Confirm only one PCPU is mapped to core 1 of the guest
        self.assertEqual(1, len(guest_dedicated_cpus), 'Only one PCPU should '
                         'be pinned to the guest CPU ID 1, but instead '
                         'found %s' % guest_dedicated_cpus)

        # Validate PCPU pinned to core 1 is a subset of the cpu dedicated set
        # of the host
        self.assertTrue(guest_dedicated_cpus.issubset(host_dedicated_cpus),
                        'PCPU %s pinned to CPU id 1 of instance %s located on '
                        'host %s is not a subset of the dedicated set %s' %
                        (guest_dedicated_cpus, server['id'], host,
                         host_dedicated_cpus))


class MixedCPUPolicyTestMultiNuma(MixedCPUPolicyTest):

    vcpus = 4
    ram = 1024
    numa_nodes = '2'

    def setUp(self):
        super(MixedCPUPolicyTestMultiNuma, self).setUp()
        self.dedicated_cpus_per_numa = \
            CONF.whitebox_hardware.dedicated_cpus_per_numa
        self.dedicated_guest_cpus_ids = list(range(self.vcpus)[1:])
        self.dedicated_cpu_count = len(self.dedicated_guest_cpus_ids)

    @classmethod
    def skip_checks(cls):
        super(MixedCPUPolicyTestMultiNuma, cls).skip_checks()
        if CONF.whitebox_hardware.dedicated_cpus_per_numa == 0:
            msg = 'Need at least 1 or more pCPU\'s per NUMA allocated to ' \
                  'the cpu_dedicated_set of the compute host'
            raise cls.skipException(msg)
        if getattr(CONF.whitebox_hardware, 'cpu_topology', None) is None:
            msg = "cpu_topology in whitebox-hardware is not present"
            raise cls.skipException(msg)
        cpu_topology = CONF.whitebox_hardware.cpu_topology
        if len(cpu_topology) < 2:
            msg = "Need at least two or more NUMA Nodes to run tests"
            raise cls.skipException(msg)

    def _verify_multi_numa_guest(self, server_id):
        host = self.get_host_for_server(server_id)
        host_sm = clients.NovaServiceManager(host, 'nova-compute',
                                             self.os_admin.services_client)

        # Gather the current hosts cpu dedicated and shared set values
        host_dedicated_cpus = host_sm.get_cpu_dedicated_set()
        host_shared_cpus = host_sm.get_cpu_shared_set()

        # Confirm the number of numa nodes for guest match expected flavor
        # configuration
        numa_nodes = self.get_server_cell_pinning(server_id)
        self.assertEqual(int(self.numa_nodes), len(numa_nodes),
                         'Expected to find %s NUMA Nodes but instead found %s '
                         % (self.numa_nodes, len(numa_nodes)))

        # Find the PCPU's currently mapped to core 0 of the guest
        guest_shared_cpus = self.get_host_pcpus_for_guest_vcpu(
            server_id, [0])

        # Validate the PCPUs mapped to core 0 are a subset of the cpu shared
        # set of the host and number of shared CPUs are accurate to what
        # is expected for the NUMA node
        self.assertEqual(
            CONF.whitebox_hardware.shared_cpus_per_numa,
            len(guest_shared_cpus),
            'Number of Shared CPUs allocated to guest should be %s but '
            'instead found %s' % (CONF.whitebox_hardware.shared_cpus_per_numa,
                                  len(guest_shared_cpus)))
        self.assertTrue(
            guest_shared_cpus.issubset(host_shared_cpus),
            'Shared CPUs allocated to guest %s is not a subset of the shared '
            'CPUs that compute host is expected to provide %s' %
            (guest_shared_cpus, host_shared_cpus))

        # Confirm the dedicated cpus allocated to guest are subset of the
        # hosts dedicated set and the number of dedicated cpus found is equal
        # to what is expected for the mask
        dedicated_pin = self.get_host_pcpus_for_guest_vcpu(
            server_id, self.dedicated_guest_cpus_ids)

        self.assertTrue(
            dedicated_pin.issubset(host_dedicated_cpus),
            'Pinned Host CPU\'s %s of server %s is not a subset of %s' %
            (dedicated_pin, server_id, host_dedicated_cpus))

        # Confirm the expected number of dedicated cpus that should be
        # allocated to the guest due to the mask match what is found on the
        # guest
        self.assertEqual(
            self.dedicated_cpu_count, len(dedicated_pin),
            'Expected to find a total of %s dedicated cpus for guest but '
            'instead found %s' % (self.dedicated_cpu_count, dedicated_pin))

        # Confirm the PCPUs allocated for shared and dedicated found on the
        # host do not intersect.
        self.assertTrue(
            guest_shared_cpus.isdisjoint(dedicated_pin),
            'The shared cpus %s should be disjoint from the dedicated set %s'
            % (guest_shared_cpus, dedicated_pin))

    def test_symmetric_multi_numa(self):
        """Create a multi NUMA guest with a mask and symmetric cpu allocation
        """
        symmetric_cpu_policy = {'hw:cpu_policy': 'mixed',
                                'hw:cpu_dedicated_mask': '^0',
                                'hw:numa_nodes': self.numa_nodes}

        flavor = self.create_flavor(vcpus=self.vcpus,
                                    extra_specs=symmetric_cpu_policy)

        server = self.create_test_server(flavor=flavor['id'],
                                         wait_until='ACTIVE')
        self._verify_multi_numa_guest(server['id'])

    def test_asymmetric_multi_numa(self):
        """Create a multi NUMA guest with a mask and asymmetric cpu allocation
        """
        if self.dedicated_cpus_per_numa < self.dedicated_cpu_count:
            msg = ('Need at least %s or more pCPUs per NUMA allocated to the '
                   'cpu_dedicated_set of the compute host' %
                   self.dedicated_cpu_count)
            raise self.skipException(msg)

        dedicated_str = [str(x) for x in self.dedicated_guest_cpus_ids]
        asymmetric_cpu_policy = {'hw:cpu_policy': 'mixed',
                                 'hw:cpu_dedicated_mask': '^0',
                                 'hw:numa_nodes': self.numa_nodes,
                                 'hw:numa_cpus.0': '0',
                                 'hw:numa_cpus.1': ','.join(dedicated_str),
                                 'hw:numa_mem.0': str(int(self.ram * 0.25)),
                                 'hw:numa_mem.1': str(int(self.ram * 0.75))}

        flavor = self.create_flavor(vcpus=self.vcpus,
                                    ram=self.ram,
                                    extra_specs=asymmetric_cpu_policy)

        server = self.create_test_server(flavor=flavor['id'],
                                         wait_until='ACTIVE')

        self._verify_multi_numa_guest(server['id'])
