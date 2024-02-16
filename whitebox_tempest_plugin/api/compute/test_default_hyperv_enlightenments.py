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
from whitebox_tempest_plugin.api.compute import base

CONF = config.CONF


class HyperVEnlightenments(base.BaseWhiteboxComputeTest):
    """Verify default hyperv enlightenments are present with windows os_type
    image.
    """
    min_microversion = '2.93'
    DEFAULT_ATTRIBUTES = ['frequencies', 'ipi', 'relaxed', 'reset', 'runtime',
                          'spinlocks', 'synic', 'tlbflush', 'vapic',
                          'vendor_id', 'vpindex']

    def setUp(self):
        super(HyperVEnlightenments, self).setUp()
        self.windows_image_id = self.copy_default_image(os_type='windows')

    def _confirm_hyperv_elements(self, server):
        """Gather all of the hyperv elements under the feature section of the
        domain's XML and confirm they match the expected defaults
        """
        root = self.get_server_xml(server['id'])
        hyperv = root.find('.features/hyperv')
        self.assertTrue(
            hyperv, 'hyperv element is not present on %s' % server['id'])

        # Collect all attributes set in the instance's hyperv element
        elements = {elem.tag: elem.get('state') for elem in hyperv.iter()
                    if elem.tag != 'hyperv'}

        # Verify all attributes configured for the hyperv element match the
        # expected default attributes.
        self.assertTrue(
            list(elements.keys()).sort() == self.DEFAULT_ATTRIBUTES.sort(),
            'The default elements %s found on %s do not match the expected '
            'default elements %s' % (list(elements.keys()), server['id'],
                                     self.DEFAULT_ATTRIBUTES))

        # Confirm all attributes present are in the 'on' state
        for attribute, state in elements.items():
            self.assertEqual(
                'on', state, 'The attribute %s was expected to be in the on '
                'state but is instead %s' % (attribute, state))

    def test_default_hyperv_enlightenments(self):
        """Confirm default enlightenments are present when deploying a guest
        with image os_type of windows
        """
        server = self.create_test_server(image_id=self.windows_image_id,
                                         wait_until='ACTIVE')
        self._confirm_hyperv_elements(server)

    def test_live_migrate_with_enlightenments(self):
        """Verify a guest with hyper-v enlightenments is able to successfully
        live-migrate between guests
        """
        server = self.create_test_server(image_id=self.windows_image_id,
                                         wait_until='ACTIVE')
        self._confirm_hyperv_elements(server)
        self.live_migrate(self.os_primary, server['id'], 'ACTIVE')
        self._confirm_hyperv_elements(server)
