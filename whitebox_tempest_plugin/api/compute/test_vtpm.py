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

from tempest import config
from tempest.exceptions import BuildErrorException
from whitebox_tempest_plugin.api.compute import base

CONF = config.CONF


class VTPMTest(base.BaseWhiteboxComputeTest):
    """Tests Virtual Trusted Platform Module (vTPM) device support for instance.
    Creating instance with a variety of device versions and module types are
    tested. Tests require creating instance flavor with extra specs about the
    tpm version and model to be specified and Barbican Key manager must enabled
    in the environement to manage the instance secrets.
    """

    @classmethod
    def skip_checks(cls):
        super(VTPMTest, cls).skip_checks()
        if (CONF.compute_feature_enabled.vtpm_device_supported is False):
            msg = "CONF.compute_feature_enabled.vtpm_device_supported must " \
                "be set."
            raise cls.skipException(msg)

    @classmethod
    def setup_clients(cls):
        super(VTPMTest, cls).setup_clients()
        os = getattr(cls, 'os_primary')
        cls.secret_client = os.secret_v1.SecretClient(
            service='key-manager'
        )

    def _vptm_server_creation_check(self, vtpm_model, vtpm_version):
        """Test to verify creating server with vTPM device

        This test creates a server with specific tpm version and model
        and verifies the same is configured by fetching instance xml.
        """

        flavor_specs = {'hw:tpm_version': vtpm_version,
                        'hw:tpm_model': vtpm_model}
        vtpm_flavor = self.create_flavor(extra_specs=flavor_specs)

        # Create server with vtpm device and fetch xml data
        server = self.create_test_server(flavor=vtpm_flavor['id'],
                                         wait_until="ACTIVE")
        server_xml = self.get_server_xml(server['id'])

        # Assert tpm model found in vTPM XML element is correct
        vtpm_element = server_xml.find('./devices/tpm[@model]')
        vtpm_model_found = vtpm_element.get('model')
        self.assertEqual(
            vtpm_model, vtpm_model_found, 'Expected vTPM model %s not found '
            'instead found: %s' % (vtpm_model, vtpm_model_found))

        # Assert tpm version found in vTPM element is correct
        vtpm_version_found = \
            vtpm_element.find('.backend[@version]').get('version')
        self.assertEqual(
            vtpm_version, vtpm_version_found, 'Expeted vTPM version %s not '
            'found instead found: %s' % (vtpm_version, vtpm_version_found))

        # Assert secret is present in the vTPM XML element
        vtpm_secret_element = vtpm_element.find('.backend/encryption')
        self.assertIsNotNone(
            vtpm_secret_element.get('secret'), 'Secret not found on vTPM '
            'element')

        # Get the secret uuid and get secret details from barbican
        secret_uuid = secret_uuid = vtpm_secret_element.get('secret')
        secret_info = self.secret_client.get_secret(secret_uuid)

        # Confirm the secret is ACTIVE and its description mentions the
        # respective server uuid and it is used for vTPM
        self.assertEqual(
            'ACTIVE', secret_info.get('status'), 'Secret is not ACTIVE, '
            'current status: %s' % secret_info.get('status'))
        self.assertTrue(
            server['id'] in secret_info.get('name'), 'Server id not present '
            'in secret key information: %s' % secret_info.get('name'))
        self.assertTrue(
            'vtpm' in secret_info.get('name').lower(), 'No mention of vTPM in '
            'secret description: %s' % secret_info.get('name'))

        # Delete server after test
        self.delete_server(server['id'])

    def test_create_server_with_vtpm_tis(self):
        # Test creating server with tpm-tis model and versions supported
        self._vptm_server_creation_check('tpm-tis', '2.0')

    def test_create_server_with_vtpm_crb(self):
        # Test creating server with tpm-crb model and versions supported
        self._vptm_server_creation_check('tpm-crb', '2.0')

    def test_invalid_model_version_creation(self):
        # Test attempting to create a server with an invalid model/version
        # combination model
        flavor_specs = {'hw:tpm_version': '1.2',
                        'hw:tpm_model': '2.0'}
        vtpm_flavor = self.create_flavor(extra_specs=flavor_specs)
        self.assertRaises(BuildErrorException,
                          self.create_test_server,
                          flavor=vtpm_flavor['id'],
                          wait_until='ACTIVE')
