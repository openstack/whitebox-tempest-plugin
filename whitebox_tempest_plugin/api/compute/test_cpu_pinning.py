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

import testtools
import xml.etree.ElementTree as ET

from tempest.common import utils
from tempest import config

from whitebox_tempest_plugin.api.compute import base
from whitebox_tempest_plugin import exceptions
from whitebox_tempest_plugin.services import clients

CONF = config.CONF


def parse_cpu_spec(spec):
    """Parse a CPU set specification.

    NOTE(artom): This has been lifted from Nova with minor exceptions-related
    adjustments.

    Each element in the list is either a single CPU number, a range of
    CPU numbers, or a caret followed by a CPU number to be excluded
    from a previous range.

    :param spec: cpu set string eg "1-4,^3,6"

    :returns: a set of CPU indexes
    """
    cpuset_ids = set()
    cpuset_reject_ids = set()
    for rule in spec.split(','):
        rule = rule.strip()
        # Handle multi ','
        if len(rule) < 1:
            continue
        # Note the count limit in the .split() call
        range_parts = rule.split('-', 1)
        if len(range_parts) > 1:
            reject = False
            if range_parts[0] and range_parts[0][0] == '^':
                reject = True
                range_parts[0] = str(range_parts[0][1:])

            # So, this was a range; start by converting the parts to ints
            try:
                start, end = [int(p.strip()) for p in range_parts]
            except ValueError:
                raise exceptions.InvalidCPUSpec(spec=spec)
            # Make sure it's a valid range
            if start > end:
                raise exceptions.InvalidCPUSpec(spec=spec)
            # Add available CPU ids to set
            if not reject:
                cpuset_ids |= set(range(start, end + 1))
            else:
                cpuset_reject_ids |= set(range(start, end + 1))
        elif rule[0] == '^':
            # Not a range, the rule is an exclusion rule; convert to int
            try:
                cpuset_reject_ids.add(int(rule[1:].strip()))
            except ValueError:
                raise exceptions.InvalidCPUSpec(spec=spec)
        else:
            # OK, a single CPU to include; convert to int
            try:
                cpuset_ids.add(int(rule))
            except ValueError:
                raise exceptions.InvalidCPUSpec(spec=spec)

    # Use sets to handle the exclusion rules for us
    cpuset_ids -= cpuset_reject_ids

    return cpuset_ids


class BasePinningTest(base.BaseWhiteboxComputeTest):

    shared_cpu_policy = {'hw:cpu_policy': 'shared'}
    dedicated_cpu_policy = {'hw:cpu_policy': 'dedicated'}

    def get_server_cpu_pinning(self, server_id):
        """Get the host CPU numbers to which the server's vCPUs are pinned.

        :param server_id: The instance UUID to look up.
        :return cpu_pins: A dict of vCPU number -> set(host CPU numbers said
                          vCPU is pinned to)
        """
        root = self.get_server_xml(server_id)

        vcpupins = root.findall('./cputune/vcpupin')
        cpu_pins = {}
        for pin in vcpupins:
            cpu_pins[int(pin.get('vcpu'))] = parse_cpu_spec(pin.get('cpuset'))

        return cpu_pins

    def get_pinning_as_set(self, server_id):
        pinset = set()
        for vcpu, pins in self.get_server_cpu_pinning(server_id).items():
            pinset |= pins
        return pinset


class CPUPolicyTest(BasePinningTest):
    """Validate CPU policy support."""

    @classmethod
    def skip_checks(cls):
        super(CPUPolicyTest, cls).skip_checks()
        if not utils.is_extension_enabled('OS-FLV-EXT-DATA', 'compute'):
            msg = "OS-FLV-EXT-DATA extension not enabled."
            raise cls.skipException(msg)

    def test_cpu_shared(self):
        """Ensure an instance with an explicit 'shared' policy work."""
        flavor = self.create_flavor(extra_specs=self.shared_cpu_policy)
        self.create_test_server(flavor=flavor['id'])

    @testtools.skipUnless(CONF.whitebox.max_compute_nodes < 2,
                          'Single compute node required.')
    def test_cpu_dedicated(self):
        """Ensure an instance with 'dedicated' pinning policy work.

        This is implicitly testing the 'prefer' policy, given that that's the
        default. However, we check specifics of that later and only assert that
        things aren't overlapping here.
        """
        flavor = self.create_flavor(extra_specs=self.dedicated_cpu_policy)
        server_a = self.create_test_server(flavor=flavor['id'])
        server_b = self.create_test_server(flavor=flavor['id'])
        cpu_pinnings_a = self.get_server_cpu_pinning(server_a['id'])
        cpu_pinnings_b = self.get_server_cpu_pinning(server_b['id'])

        self.assertEqual(
            len(cpu_pinnings_a), self.vcpus,
            "Instance should be pinned but it is unpinned")
        self.assertEqual(
            len(cpu_pinnings_b), self.vcpus,
            "Instance should be pinned but it is unpinned")

        self.assertTrue(
            set(cpu_pinnings_a.values()).isdisjoint(
                set(cpu_pinnings_b.values())),
            "Unexpected overlap in CPU pinning: {}; {}".format(
                cpu_pinnings_a,
                cpu_pinnings_b))

    @testtools.skipUnless(CONF.compute_feature_enabled.resize,
                          'Resize not available.')
    def test_resize_pinned_server_to_unpinned(self):
        """Ensure resizing an instance to unpinned actually drops pinning."""
        flavor_a = self.create_flavor(extra_specs=self.dedicated_cpu_policy)
        server = self.create_test_server(flavor=flavor_a['id'])
        cpu_pinnings = self.get_server_cpu_pinning(server['id'])

        self.assertEqual(
            len(cpu_pinnings), self.vcpus,
            "Instance should be pinned but is unpinned")

        flavor_b = self.create_flavor(extra_specs=self.shared_cpu_policy)
        server = self.resize_server(server['id'], flavor_b['id'])
        cpu_pinnings = self.get_server_cpu_pinning(server['id'])

        self.assertEqual(
            len(cpu_pinnings), 0,
            "Resized instance should be unpinned but is still pinned")

    @testtools.skipUnless(CONF.compute_feature_enabled.resize,
                          'Resize not available.')
    def test_resize_unpinned_server_to_pinned(self):
        """Ensure resizing an instance to pinned actually applies pinning."""
        flavor_a = self.create_flavor(extra_specs=self.shared_cpu_policy)
        server = self.create_test_server(flavor=flavor_a['id'])
        cpu_pinnings = self.get_server_cpu_pinning(server['id'])

        self.assertEqual(
            len(cpu_pinnings), 0,
            "Instance should be unpinned but is pinned")

        flavor_b = self.create_flavor(extra_specs=self.dedicated_cpu_policy)
        server = self.resize_server(server['id'], flavor_b['id'])
        cpu_pinnings = self.get_server_cpu_pinning(server['id'])

        self.assertEqual(
            len(cpu_pinnings), self.vcpus,
            "Resized instance should be pinned but is still unpinned")

    def test_reboot_pinned_server(self):
        """Ensure pinning information is persisted after a reboot."""
        flavor = self.create_flavor(extra_specs=self.dedicated_cpu_policy)
        server = self.create_test_server(flavor=flavor['id'])
        cpu_pinnings = self.get_server_cpu_pinning(server['id'])

        self.assertEqual(
            len(cpu_pinnings), self.vcpus,
            "CPU pinning was not applied to new instance.")

        server = self.reboot_server(server['id'], 'HARD')
        cpu_pinnings = self.get_server_cpu_pinning(server['id'])

        # we don't actually assert that the same pinning information is used
        # because that's not expected. We just care that _some_ pinning is in
        # effect
        self.assertEqual(
            len(cpu_pinnings), self.vcpus,
            "Rebooted instance has lost its pinning information")


class CPUThreadPolicyTest(BasePinningTest):
    """Validate CPU thread policy support."""

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

        try:
            host_address = CONF.whitebox.hypervisors[host]
        except KeyError:
            raise exceptions.MissingHypervisorException(server="",
                                                        host=host)
        virshxml = clients.VirshXMLClient(host_address)
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
        flavor = self.create_flavor(extra_specs=self.isolate_thread_policy)
        server = self.create_test_server(flavor=flavor['id'])
        host = server['OS-EXT-SRV-ATTR:host']

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

    def test_threads_prefer(self):
        """Ensure vCPUs *are* placed on thread siblings.

        For this to work, we require a host with HyperThreads. Scheduling will
        pass without this, but the test will not.
        """
        flavor = self.create_flavor(extra_specs=self.prefer_thread_policy)
        server = self.create_test_server(flavor=flavor['id'])
        host = server['OS-EXT-SRV-ATTR:host']

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

    def test_threads_require(self):
        """Ensure thread siblings are required and used.

        For this to work, we require a host with HyperThreads. Scheduling will
        fail without this.
        """
        flavor = self.create_flavor(extra_specs=self.require_thread_policy)
        server = self.create_test_server(flavor=flavor['id'])
        host = server['OS-EXT-SRV-ATTR:host']

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
