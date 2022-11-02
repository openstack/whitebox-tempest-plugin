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

from oslo_log import log as logging
from tempest import config
import testtools

from whitebox_tempest_plugin.api.compute import base

CONF = config.CONF
LOG = logging.getLogger(__name__)


class TestUEFIBoot(base.BaseWhiteboxComputeTest):
    """Tests checking booting guests with UEFI
    """

    @classmethod
    def skip_checks(cls):
        super(TestUEFIBoot, cls).skip_checks()
        if not CONF.compute_feature_enabled.uefi_boot:
            skip_msg = ("%s skipped as uefi_boot is "
                        "not enabled" % cls.__name__)
            raise cls.skipException(skip_msg)

    def _validate_uefi_os_xml_elements(self, server_id, os_element,
                                       secure_boot):
        """Verifies correct elements present in XML for UEFI boot

        :param server_id: str, the server id being checked
        :param os_element: xml.etree.ElementTree.Element, os element of the
        guest
        :param secure_boot: bool, if secure boot is enabled for guest
        """
        loader = os_element.find('loader')
        self.assertIsNotNone(
            loader, 'Loader element not present in guest %s' % server_id)
        self.assertEqual(
            'yes', loader.get('readonly'),
            'Readonly attribute is not yes for loader element')

        # Confirm secure boot is properly set based on the secure_boot
        # parameter, for RHEL8 the 'no' flag is not present when secure boot
        # is not enabled so add a default 'no' response when checking for the
        # secure parameter
        secure_boot_check = 'yes' if secure_boot else 'no'
        self.assertEqual(
            secure_boot_check, loader.get('secure', 'no'), 'Secure boot '
            'should be set to %s but instead it is %s ' %
            (secure_boot_check, loader.get('secure')))

        # Confirm NVRAM element is present within os element of the guest
        self.assertIsNotNone(
            os_element.find('nvram'),
            'NVRAM element not present in guest %s' % server_id)

    def test_uefi_boot(self):
        """Verify booting guest with UEFI enabled for image property"""

        image_properties = {'hw_firmware_type': 'uefi',
                            'hw_machine_type': 'q35'}

        # Create image with UEFI firmware type
        uefi_image_id = self.copy_default_image(**image_properties)
        server = self.create_test_server(
            image_id=uefi_image_id, wait_until='ACTIVE')
        domain = self.get_server_xml(server['id'])
        os_element = domain.find("./os")

        # Confirm loader element is present and within loader element readonly
        # is set to 'yes' and secure is set to 'no'.
        self._validate_uefi_os_xml_elements(
            server['id'], os_element, secure_boot=False)

    @testtools.skipUnless(CONF.compute_feature_enabled.uefi_secure_boot,
                          "Requires uefi secure boot to be enabled")
    def test_uefi_secure_boot(self):
        """Verify booting guest with UEFI and secure boot enabled enabled"""

        image_properties = {'os_secure_boot': 'required',
                            'hw_firmware_type': 'uefi',
                            'hw_machine_type': 'q35'}

        # Create image with UEFI firmware type and secure boot enabled
        uefi_image_id = self.copy_default_image(**image_properties)
        server = self.create_test_server(
            image_id=uefi_image_id, wait_until='ACTIVE')
        domain = self.get_server_xml(server['id'])
        os_element = domain.find("./os")

        # Confirm loader element is present and within loader element readonly
        # and secure are both set to 'yes'.
        self._validate_uefi_os_xml_elements(
            server['id'], os_element, secure_boot=True)

        # Confirm that the smm element is present in features element of guest
        # and the state is set to 'on'
        features_element = domain.find("./features")
        smm_element = features_element.find('smm')
        self.assertIsNotNone(
            smm_element, 'Loader element not present in guest %s'
            % server['id'])
        self.assertEqual(
            'on', smm_element.get('state'), 'SMM state is not on in guest '
            'features, found %s instead for guest: %s' %
            (smm_element.get('state'), server['id']))
