# Copyright 2018 Red Hat
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
from tempest import config

from whitebox_tempest_plugin.api.compute import base


CONF = config.CONF
LOG = logging.getLogger(__name__)


class CpuModelExtraFlagsTest(base.BaseWhiteboxComputeTest):

    # Required in /etc/nova/nova.conf
    #    [libvirt]
    #    cpu_mode = custom
    #    cpu_model = Haswell-noTSX
    #    cpu_model_extra_flags = vmx, pdpe1gb
    #    virt_type = kvm
    def test_cpu_model_extra_flags(self):
        server = self.create_test_server(wait_until="ACTIVE")
        root = self.get_server_xml(server['id'])

        # Assert that the correct CPU model as well as the proper flags
        # are correctly defined in the instance XML
        self.assertEqual(
            root.find("cpu[@mode='custom']/model").text,
            "Haswell-noTSX", "Wrong CPU model defined in the instance xml")
        self.assertNotEmpty(
            root.findall('cpu[@mode="custom"]/feature[@name="vmx"]'),
            "Cannot find feature 'vmx' in the instance xml")
        self.assertNotEmpty(
            root.findall('cpu[@mode="custom"]/feature[@name="pdpe1gb"]'),
            "Cannot find feature 'pdpe1gb' in the instance xml")
