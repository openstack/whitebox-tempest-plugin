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

CONF = config.CONF


class BaseTest(base.BaseTest):

    vcpus = 2

    def get_server_cpu_pinning(self, server):
        instance_name = server['OS-EXT-SRV-ATTR:instance_name']

        with self.get_libvirt_conn(server['OS-EXT-SRV-ATTR:host']) as conn:
            dom0 = conn.lookupByName(instance_name)
            root = ET.fromstring(dom0.XMLDesc())

        vcpupin_nodes = root.findall('./cputune/vcpupin')
        cpu_pinnings = {int(x.get('vcpu')): int(x.get('cpuset'))
                        for x in vcpupin_nodes if x is not None}

        return cpu_pinnings


class CPUPolicyTest(BaseTest):
    """Validate CPU policy support."""

    @classmethod
    def skip_checks(cls):
        super(CPUPolicyTest, cls).skip_checks()
        if not utils.is_extension_enabled('OS-FLV-EXT-DATA', 'compute'):
            msg = "OS-FLV-EXT-DATA extension not enabled."
            raise cls.skipException(msg)

    def create_flavor(self, cpu_policy):
        flavor = super(CPUPolicyTest, self).create_flavor(vcpus=self.vcpus)

        specs = {'hw:cpu_policy': cpu_policy}
        self.flavors_client.set_flavor_extra_spec(flavor['id'], **specs)

        return flavor

    def test_cpu_shared(self):
        """Ensure an instance with an explicit 'shared' policy work."""
        flavor = self.create_flavor(cpu_policy='shared')
        self.create_test_server(flavor=flavor['id'])

    def test_cpu_dedicated(self):
        """Ensure an instance with 'dedicated' pinning policy work.

        This is implicitly testing the 'prefer' policy, given that that's the
        default. However, we check specifics of that later and only assert that
        things aren't overlapping here.
        """
        flavor = self.create_flavor(cpu_policy='dedicated')
        server_a = self.create_test_server(flavor=flavor['id'])
        server_b = self.create_test_server(flavor=flavor['id'])
        cpu_pinnings_a = self.get_server_cpu_pinning(server_a)
        cpu_pinnings_b = self.get_server_cpu_pinning(server_b)

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
        flavor_a = self.create_flavor(cpu_policy='dedicated')
        server = self.create_test_server(flavor=flavor_a['id'])
        cpu_pinnings = self.get_server_cpu_pinning(server)

        self.assertEqual(
            len(cpu_pinnings), self.vcpus,
            "Instance should be pinned but is unpinned")

        flavor_b = self.create_flavor(cpu_policy='shared')
        server = self.resize_server(server['id'], flavor_b['id'])
        cpu_pinnings = self.get_server_cpu_pinning(server)

        self.assertEqual(
            len(cpu_pinnings), 0,
            "Resized instance should be unpinned but is still pinned")

    @testtools.skipUnless(CONF.compute_feature_enabled.resize,
                          'Resize not available.')
    def test_resize_unpinned_server_to_pinned(self):
        """Ensure resizing an instance to pinned actually applies pinning."""
        flavor_a = self.create_flavor(cpu_policy='shared')
        server = self.create_test_server(flavor=flavor_a['id'])
        cpu_pinnings = self.get_server_cpu_pinning(server)

        self.assertEqual(
            len(cpu_pinnings), 0,
            "Instance should be unpinned but is pinned")

        flavor_b = self.create_flavor(cpu_policy='dedicated')
        server = self.resize_server(server['id'], flavor_b['id'])
        cpu_pinnings = self.get_server_cpu_pinning(server)

        self.assertEqual(
            len(cpu_pinnings), self.vcpus,
            "Resized instance should be pinned but is still unpinned")

    def test_reboot_pinned_server(self):
        """Ensure pinning information is persisted after a reboot."""
        flavor = self.create_flavor(cpu_policy='dedicated')
        server = self.create_test_server(flavor=flavor['id'])
        cpu_pinnings = self.get_server_cpu_pinning(server)

        self.assertEqual(
            len(cpu_pinnings), self.vcpus,
            "CPU pinning was not applied to new instance.")

        server = self.reboot_server(server['id'], 'HARD')
        cpu_pinnings = self.get_server_cpu_pinning(server)

        # we don't actually assert that the same pinning information is used
        # because that's not expected. We just care that _some_ pinning is in
        # effect
        self.assertEqual(
            len(cpu_pinnings), self.vcpus,
            "Rebooted instance has lost its pinning information")
