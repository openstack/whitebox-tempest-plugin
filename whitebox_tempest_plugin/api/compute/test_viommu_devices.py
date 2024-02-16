# Copyright 2024 Red Hat
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

CONF = config.CONF


class ViommuTestQ35ViaImage(base.BaseWhiteboxComputeTest):
    """Test the creation of guests with attached Virtual IOMMU intel devices.
    Q35 is is configured via adding the parameter to the guest image.
    """
    min_microversion = '2.93'

    def setUp(self):
        super(ViommuTestQ35ViaImage, self).setUp()
        self.viommu_intel_flavor = self.create_flavor(
            extra_specs={"hw:viommu_model": 'intel'})
        self.q35_image_id = self.copy_default_image(hw_machine_type='q35')

    def _get_iommu_xml_element(self, server):
        root = self.get_server_xml(server['id'])
        iommu = root.find(".devices/iommu[@model='intel']")
        return iommu

    def _assert_viommu_model(self, server):
        iommu = self._get_iommu_xml_element(server)
        self.assertTrue(
            iommu, 'vIOMMU element is not present on %s' % server['id'])
        intremap_status = iommu.find('driver').get('intremap')
        self.assertEqual(
            'on', intremap_status, "Expected intremap status to be 'on' but "
            "instead found: %s" % intremap_status)

    def _assert_viommu_not_present(self, server):
        iommu = self._get_iommu_xml_element(server)
        self.assertFalse(
            iommu, 'vIOMMU element should no longer be present on %s'
            % server['id'])

    def test_deploy_intel_viommu_model_q35_via_image(self):
        """Create a guest with viommu intel model and confirm it is present
        """
        server = self.create_test_server(
            image_id=self.q35_image_id,
            flavor=self.viommu_intel_flavor['id'],
            wait_until='ACTIVE'
        )
        self._assert_viommu_model(server)

    @testtools.skipUnless(CONF.compute_feature_enabled.resize,
                          'Resize not available.')
    def test_resize_intel_viommu_via_image(self):
        """Resize guest to use viommu, confirm element is present, revert
        and verify the element has been removed
        """
        server = self.create_test_server(
            wait_until='ACTIVE',
            image_id=self.q35_image_id)
        self.resize_server(server['id'], self.viommu_intel_flavor['id'])

        self._assert_viommu_model(server)
        default_flavor = self.create_flavor()
        self.resize_server(server['id'], default_flavor['id'])
        self._assert_viommu_not_present(server)
