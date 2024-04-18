# Copyright 2022 Red Hat Inc.
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

from tempest import config
import testtools
from whitebox_tempest_plugin.api.compute import base

from oslo_log import log as logging

CONF = config.CONF
LOG = logging.getLogger(__name__)


class HugePageResize(base.BaseWhiteboxComputeTest):

    @classmethod
    def skip_checks(cls):
        super(HugePageResize, cls).skip_checks()
        if len(getattr(CONF.whitebox_hardware,
                       'configured_hugepage_sizes')) == 0:
            msg = "configured_hugepage_sizes in whitebox-hardware is not " \
                  "present"
            raise cls.skipException(msg)

    def _get_xml_hugepage_size(self, server_id):
        """Analyze the hugepage xml element(s) from a provided instance. Expect
        to find only one hugepage element in the domain. Return boolean result
        comparing if the found page size is equal to the expected page size.
        """
        huge_pages_list = self._get_hugepage_xml_element(server_id)
        self.assertEqual(1, len(huge_pages_list), "Expected to find 1 "
                         "hugepage XML element on server %s but found %s"
                         % (server_id, len(huge_pages_list)))
        huge_page_xml = huge_pages_list[0]
        return int(huge_page_xml.attrib['size'])

    def test_hugepage_resize_large_to_small(self):
        """Resize a guest with large hugepages to small hugepages and back

        Create a guest using a flavor with hw:mem_page_size:large, resize it
        to a flavor with hw:mem_page_size:small, and then resize it back to
        the original flavor
        """
        flavor_a = self.create_flavor(
            ram=str(CONF.whitebox.hugepage_guest_ram_size),
            extra_specs={'hw:mem_page_size': 'large'})

        server = self.create_test_server(flavor=flavor_a['id'],
                                         wait_until='ACTIVE')

        # Cannot assume the exact pagesize of the guest, verify the backing
        # memory element is present on the guest and the found size is greater
        # than or equal to the smallest potential size configured in the
        # environment
        large_page_size = self._get_xml_hugepage_size(server['id'])
        minimum_pagesize_threshold = \
            min(CONF.whitebox_hardware.configured_hugepage_sizes)
        self.assertTrue(
            large_page_size >= minimum_pagesize_threshold,
            "Pagesize found %s should be greater than or equal to pagesize "
            "of %s for server %s" %
            (large_page_size, minimum_pagesize_threshold, server['id'])
        )

        # Resize the guest using a flavor with hw:mem_page_size:small,
        # memory backing element should not be present on guest currently so
        # no need for XML verification
        flavor_b = self.create_flavor(
            ram=str(CONF.whitebox.hugepage_guest_ram_size),
            extra_specs={'hw:mem_page_size': 'small'})
        self.resize_server(server['id'], flavor_b['id'])

        # Resize instance back to staring flavor size and repeat XML check of
        # the guest
        self.resize_server(server['id'], flavor_a['id'])
        large_page_size = self._get_xml_hugepage_size(server['id'])
        self.assertTrue(
            large_page_size >= minimum_pagesize_threshold,
            "After resizing back to original flavor, pagesize found %s should "
            "be greater than or equal to pagesize of %s for server %s" %
            (large_page_size, minimum_pagesize_threshold, server['id'])
        )

    def test_hugepage_resize_size_to_small(self):
        """Resize a guest with a specified hugepage size to small hugepages

        Create a guest using a flavor with using an explicit hugepage size(s),
        based on what is configured in whitebox_hardware. Resize the guest to a
        flavor with hw:mem_page_size:small, and then resize it back to the
        original flavor. Repeat this process for every hugepage size configured
        in in whitebox_hardware.configured_hugepage_sizes
        """
        flavor_small = self.create_flavor(
            ram=str(CONF.whitebox.hugepage_guest_ram_size),
            extra_specs={'hw:mem_page_size': 'small'})

        # Create a flavor and launch an instance based on every configured
        # hugepage size in the deployment.
        for page_size in CONF.whitebox_hardware.configured_hugepage_sizes:
            flavor_a = self.create_flavor(
                ram=str(CONF.whitebox.hugepage_guest_ram_size),
                extra_specs={'hw:mem_page_size': str(page_size)})

            server = self.create_test_server(flavor=flavor_a['id'],
                                             wait_until='ACTIVE')

            size_found = self._get_xml_hugepage_size(server['id'])
            self.assertTrue(
                page_size == size_found,
                "Expected pagesize of %s not found on server %s instead "
                "found %s" % (page_size, server['id'], size_found)
            )

            # Resize the guest using a flavor with hw:mem_page_size:small,
            # memory backing will not be present in with guest so follow up
            # XML verification is not necessary
            self.resize_server(server['id'], flavor_small['id'])

            # Resize back to its original size and confirm memory backing
            # element is present and has the correct size
            self.resize_server(server['id'], flavor_a['id'])
            size_found = self._get_xml_hugepage_size(server['id'])
            self.assertTrue(
                page_size == size_found,
                "Expected pagesize of %s not found on server %s after "
                "resizing back to original flavor size, instead found %s" %
                (page_size, server['id'], size_found)
            )

            self.delete_server(server['id'])

    @testtools.skipUnless(
        len(CONF.whitebox_hardware.configured_hugepage_sizes) > 1,
        'Need at least 2 configured hugepage sizes to execute test')
    def test_hugepage_resize_size_to_size(self):
        """Resize a guest with a specified hugepage size to another size

        Create two flavors based on the two provided hugepage sizes.  The
        flavors created use explicit sizes Create a
        server using the first flavor, resize the guest to the second flavor,
        and resize back to the original spec
        """
        start_size, target_size = \
            CONF.whitebox_hardware.configured_hugepage_sizes

        flavor_a = self.create_flavor(
            ram=str(CONF.whitebox.hugepage_guest_ram_size),
            extra_specs={'hw:mem_page_size': str(start_size)})

        server = self.create_test_server(flavor=flavor_a['id'],
                                         wait_until='ACTIVE')

        size_found = self._get_xml_hugepage_size(server['id'])
        self.assertTrue(
            start_size == size_found,
            "Expected pagesize of %s not found on server %s instead "
            "found %s" % (start_size, server['id'], size_found)
        )

        flavor_b = self.create_flavor(
            ram=str(CONF.whitebox.hugepage_guest_ram_size),
            extra_specs={'hw:mem_page_size': str(target_size)})

        # Resize to the target size and confirm memory backing element is
        # present and has the correct size
        self.resize_server(server['id'], flavor_b['id'])
        size_found = self._get_xml_hugepage_size(server['id'])
        self.assertTrue(
            target_size == size_found,
            "Expected pagesize of %s not found on server %s after resize "
            "instead found %s" % (target_size, server['id'], size_found)
        )

        # Resize back to its original size and confirm memory backing
        # element is present and has the correct size
        self.resize_server(server['id'], flavor_a['id'])
        size_found = self._get_xml_hugepage_size(server['id'])

        self.assertTrue(
            start_size == size_found,
            "Expected pagesize of %s not found on server %s after resizing "
            "back to original flavor size, instead found %s" %
            (start_size, server['id'], size_found)
        )
