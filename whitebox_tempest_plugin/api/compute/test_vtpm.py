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

import testtools

import tempest.clients
from tempest import config
from tempest.exceptions import BuildErrorException
import tempest.lib.exceptions
from tempest.lib.exceptions import ServerFault
from tempest.lib.services import clients

from whitebox_tempest_plugin.api.compute import base
from whitebox_tempest_plugin.services import clients as wb_clients

CONF = config.CONF


class VTPMTest(base.BaseWhiteboxComputeTest):
    """Tests Virtual Trusted Platform Module (vTPM) device support for instance.
    Creating instance with a variety of device versions and module types are
    tested. Tests require creating instance flavor with extra specs about the
    tpm version and model to be specified and Barbican Key manager must enabled
    in the environment to manage the instance secrets.
    """

    min_microversion = '2.25'
    max_microversion = 'latest'

    @classmethod
    def skip_checks(cls):
        super(VTPMTest, cls).skip_checks()
        if (CONF.compute_feature_enabled.vtpm_device_supported is False):
            msg = "[compute-feature-enabled]vtpm_device_supported must " \
                "be set."
            raise cls.skipException(msg)

    @classmethod
    def setup_clients(cls):
        super(VTPMTest, cls).setup_clients()
        if CONF.identity.auth_version == 'v3':
            auth_uri = CONF.identity.uri_v3
        else:
            auth_uri = CONF.identity.uri
        service_clients = clients.ServiceClients(cls.os_primary.credentials,
                                                 auth_uri)
        cls.os_primary.secrets_client = service_clients.secret_v1.SecretClient(
            service='key-manager')

    def _vtpm_check(self, server, vtpm_model, vtpm_version,
                    secrets_client=None):
        secrets_client = secrets_client or self.os_primary.secrets_client
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
        secret_uuid = vtpm_secret_element.get('secret')
        secret_info = secrets_client.get_secret_metadata(secret_uuid)

        # Confirm the secret is ACTIVE and its name mentions the respective
        # server UUID and it is used for vTPM
        self.assertEqual(
            'ACTIVE', secret_info.get('status'), 'Secret is not ACTIVE, '
            'current status: %s' % secret_info.get('status'))
        self.assertTrue(
            server['id'] in secret_info.get('name'), 'Server id not present '
            'in secret key information: %s' % secret_info.get('name'))
        self.assertTrue(
            'vtpm' in secret_info.get('name').lower(), 'No mention of vTPM in '
            'secret name: %s' % secret_info.get('name'))

        return secret_uuid

    def _vtpm_server_creation_check(self, vtpm_model, vtpm_version):
        """Test to verify creating server with vTPM device

        This test creates a server with specific tpm version and model
        and verifies the same is configured by fetching instance xml.
        """

        flavor_specs = {'hw:tpm_version': vtpm_version,
                        'hw:tpm_model': vtpm_model}
        vtpm_flavor = self.create_flavor(extra_specs=flavor_specs)

        # Create server with vtpm device
        server = self.create_test_server(flavor=vtpm_flavor['id'],
                                         wait_until="ACTIVE")

        # Verify the server XML against Barbican API
        self._vtpm_check(server, vtpm_model, vtpm_version)

        # Delete server after test
        self.delete_server(server['id'])

    def _secret_check(self, secret_uuid, host):
        secret_xml = self.get_secret_xml(secret_uuid, host)
        self.assertEqual('no', secret_xml.get('ephemeral'))
        self.assertEqual('no', secret_xml.get('private'))

    def test_create_server_with_vtpm_tis(self):
        # Test creating server with tpm-tis model and versions supported
        self._vtpm_server_creation_check('tpm-tis', '2.0')

    def test_create_server_with_vtpm_crb(self):
        # Test creating server with tpm-crb model and versions supported
        self._vtpm_server_creation_check('tpm-crb', '2.0')

    def test_invalid_model_version_creation(self):
        # Test attempting to create a server with an invalid model/version
        # combination model
        flavor_specs = {'hw:tpm_version': '1.2',
                        'hw:tpm_model': '2.0'}

        # Starting with 2.86, Nova validates flavor extra specs. Since the
        # tpm_model in this test is an invalid value for the flavor request
        # it will result in a ServerFault being thrown via Nova-API, instead
        # of failing later in the path and throwing a BuildErrorException.
        vtpm_flavor = self.create_flavor(extra_specs=flavor_specs)

        if not CONF.compute_feature_enabled.unified_limits:
            self.assertRaises(BuildErrorException,
                              self.create_test_server,
                              flavor=vtpm_flavor['id'],
                              wait_until='ACTIVE')
        else:
            self.assertRaises(ServerFault,
                              self.create_test_server,
                              flavor=vtpm_flavor['id'],
                              wait_until='ACTIVE')

    def test_vtpm_creation_after_virtqemud_restart(self):
        # Test validates vTPM instance creation after libvirt service restart
        hosts = self.list_compute_hosts()
        for host in hosts:
            host_svc = wb_clients.VirtQEMUdManager(
                host, 'libvirt', self.os_admin.services_client)
            host_svc.restart()
        self._vtpm_server_creation_check('tpm-crb', '2.0')

    def test_vtpm_live_migration_secret_security_user(self):
        """Test vTPM live migration with secret security 'user'

        The 'user' secret security policy is the same as legacy vTPM secret
        handling where the Barbican secret is owned by the user and live
        migration is disallowed in the API.

        In this case, a cloud admin would not be able to live migrate a user's
        instance anyhow because the user's auth token would be needed for
        accessing the Barbican secret.

        The libvirt secret in this case has ephemeral=yes and private=yes and
        is deleted after the guest is running.
        """
        flavor_specs = {'hw:tpm_version': '1.2',
                        'hw:tpm_model': 'tpm-tis'}
        vtpm_flavor = self.create_flavor(extra_specs=flavor_specs)

        # Create server with vtpm device
        server = self.create_test_server(flavor=vtpm_flavor['id'],
                                         wait_until="ACTIVE")

        ex = self.assertRaises(
            tempest.lib.exceptions.BadRequest, self.live_migrate,
            self.os_admin, server['id'], 'ACTIVE')
        self.assertIn(
            "Operation 'live-migration' not supported for vTPM-enabled "
            "instance", str(ex))

        self.delete_server(server['id'])

    @testtools.skipUnless(
        CONF.compute_feature_enabled.vtpm_live_migration_supported,
        'vTPM live migration is not available')
    def test_vtpm_live_migration_secret_security_host(self):
        """Test vTPM live migration with secret security 'host'

        The 'host' secret security policy has the Barbican secret owned by the
        user but during live migration, the secret is read from libvirt and
        passed to the destination compute host over RPC.

        This enables a cloud admin to live migrate the user's instance without
        needing the user's auth token for accessing the Barbican secret.

        In this case the libvirt secret needs to be ephemeral=no and private=no
        allowing it to be read back from libvirt.
        """
        vtpm_model = 'tpm-tis'
        vtpm_version = '1.2'
        flavor_specs = {'hw:tpm_version': vtpm_version,
                        'hw:tpm_model': vtpm_model,
                        'hw:tpm_secret_security': 'host'}
        vtpm_flavor = self.create_flavor(extra_specs=flavor_specs)

        # Create server with vtpm device
        server = self.create_test_server(flavor=vtpm_flavor['id'],
                                         wait_until="ACTIVE")

        # Check the vtpm before live migration
        secret_uuid = self._vtpm_check(server, vtpm_model, vtpm_version)

        # Check the secret. We should be able to find it because it should have
        # been created with ephemeral=no and private=no and not deleted.
        host = self.get_host_for_server(server['id'])
        self._secret_check(secret_uuid, host)

        self.live_migrate(self.os_admin, server['id'], 'ACTIVE')

        # Check the vtpm again after live migration
        secret_uuid = self._vtpm_check(server, vtpm_model, vtpm_version)

        # Check the secret again
        host = self.get_host_for_server(server['id'])
        self._secret_check(secret_uuid, host)

        self.delete_server(server['id'])
