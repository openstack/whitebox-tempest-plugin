# Copyright 2020 Red Hat Inc.
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

from oslo_log import log as logging
from oslo_utils import strutils
from tempest import config

from whitebox_tempest_plugin.api.compute import base

CONF = config.CONF
LOG = logging.getLogger(__name__)


class NVDIMMTests(base.BaseWhiteboxComputeTest):

    @classmethod
    def skip_checks(cls):
        super(NVDIMMTests, cls).skip_checks()
        if getattr(CONF.whitebox,
                   'pmem_flavor_size', None) is None:
            msg = "pmem_flavor_size value needed to create nvdimm flavor"
            raise cls.skipException(msg)
        if getattr(CONF.whitebox, 'pmem_expected_size', None) is None:
            msg = "pmem_expected_size value needed to accurately compare " \
                  "expected allocated memory"
            raise cls.skipException(msg)

    def test_nvdimm_instance_creation(self):
        # Create a pmem flavor based on the provided flavor size in
        # [whitebox]/pem_flavor_size
        pmem_spec = {'hw:pmem': CONF.whitebox.pmem_flavor_size}
        flavor = self.create_flavor(extra_specs=pmem_spec)
        server = self.create_test_server(flavor=flavor['id'],
                                         wait_until='ACTIVE')

        # Confirm the memory xml model is nvdimm
        root = self.get_server_xml(server['id'])
        pmem_device = root.find("./devices/memory[@model='nvdimm']")
        self.assertIsNotNone(
            pmem_device, "NVDIMM memory device was not found in instace %s XML"
            % server['id']
        )

        # Gather the target size of the xml memory element and convert it to
        # bytes
        target_size_element = pmem_device.find('target/size')
        target_size_str = target_size_element.text + \
            target_size_element.get('unit')
        target_size = strutils.string_to_bytes(target_size_str,
                                               return_int=True)

        # Gather the alignment size in the xml memory element, convert it to
        # bytes, and add it to target size to get the total namespace size
        # allocated to the guest.
        alignment_size_element = pmem_device.find('source/alignsize')
        align_size_str = alignment_size_element.text + \
            alignment_size_element.get('unit')
        align_size = strutils.string_to_bytes(align_size_str, return_int=True)
        total_size = target_size + align_size

        # Convert the expected total memory to bytes
        expected_size = strutils.string_to_bytes(
            CONF.whitebox.pmem_expected_size, return_int=True
        )

        # Confirm the expected memory size and the total memory allocated to
        # the guest (target + alignment) are the same
        self.assertEqual(expected_size, total_size, "The expected config "
                         "of %s or %s bytes was not found on guest %s. "
                         "Instead total size found was %s bytes" % (
                             CONF.whitebox.pmem_expected_size,
                             expected_size, server['id'], total_size))
